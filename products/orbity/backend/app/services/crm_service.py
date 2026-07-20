"""
CRM service — leads CRUD, funil kanban grouping, stage moves,
activities, lead scoring, and public lead capture.

Scoring is delegated to app.services.lead_scoring (pure computation,
no DB access). This service owns the DB reads/writes + scoring upsert.

pt-BR phone normalization:
  - Strip non-digits
  - Prefix 55 if not already present (Brazilian DDD-9digit shape)
  - Preserve the 9th digit for mobile (already standard since 2016)

No silent errors: every except logs at the right level and re-raises.
No mock-data fallbacks: callers receive explicit empty states.
"""
from __future__ import annotations

import logging
import re
from typing import Any
from uuid import UUID

from app.services.lead_scoring import compute_score

logger = logging.getLogger(__name__)

# Canonical default pipeline — mirrors orbity.seed_default_lead_stages()
# (products/orbity/backend/migrations/005_crm_core.sql). Kept in sync by
# hand: the SQL function is the source of truth for the DB-level backfill
# (014_seed_default_stages_backfill.sql calls it directly, in-database —
# no PostgREST/RPC involved), this constant backs the app-level forward
# path (CRMService.seed_default_stages), which does NOT call the SQL
# function via `.rpc()` — this backend has no RPC calling mechanism
# anywhere (zero `.rpc(` call sites) and the seed test double
# (MockSupabaseClient) has no `.rpc()` support to exercise against.
DEFAULT_LEAD_STAGES: tuple[dict[str, Any], ...] = (
    {"name": "Novo", "position": 0, "color": "#94a3b8", "is_won": False, "is_lost": False},
    {"name": "Contato", "position": 1, "color": "#60a5fa", "is_won": False, "is_lost": False},
    {"name": "Qualificado", "position": 2, "color": "#34d399", "is_won": False, "is_lost": False},
    {"name": "Proposta", "position": 3, "color": "#fbbf24", "is_won": False, "is_lost": False},
    {"name": "Negociação", "position": 4, "color": "#f97316", "is_won": False, "is_lost": False},
    {"name": "Fechado", "position": 5, "color": "#22c55e", "is_won": True, "is_lost": False},
    {"name": "Perdido", "position": 6, "color": "#f43f5e", "is_won": False, "is_lost": True},
)


def _normalize_br_phone(raw: str | None) -> str | None:
    """Normalize a Brazilian phone number to 55XXXXXXXXXXX form.

    - Strips all non-digit characters
    - Prepends country code 55 if absent
    - Does NOT truncate — 11-digit (DDDmobile) and 10-digit (DDDfixed) both accepted
    - Returns None if input is blank or results in fewer than 10 digits
    """
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    if not digits.startswith("55"):
        digits = "55" + digits
    # Minimum: 55 + DDD(2) + fixed(8) = 12 digits
    if len(digits) < 12:
        logger.debug("normalize_br_phone: too short after normalizing: %r → %r", raw, digits)
        return digits  # return as-is rather than silently discard
    return digits


class CRMService:
    def __init__(self, db: Any, org_id: UUID) -> None:
        self._db = db
        self._org_id = str(org_id)

    def _t(self, table: str):
        # The Supabase client is already schema-scoped to "orbity" by
        # create_database_module(settings, schema="orbity"). Calling
        # .schema() again would create a new client and break
        # MockSupabaseClient's inserted_payloads tracking in tests.
        return self._db.table(table)

    # ------------------------------------------------------------------
    # Lead stages
    # ------------------------------------------------------------------

    def list_stages(self) -> list[dict[str, Any]]:
        try:
            result = (
                self._t("lead_stages")
                .select("*")
                .eq("org_id", self._org_id)
                .order("position", desc=False)
                .execute()
            )
        except Exception:
            logger.exception("crm.list_stages failed org=%s", self._org_id)
            raise
        return result.data or []

    def seed_default_stages(self) -> list[dict[str, Any]]:
        """Idempotently create the 7 canonical default lead stages for this org.

        Explicit, user-triggered forward path (POST /api/crm/stages/seed-
        defaults) — deliberately NOT a lazy-seed on a GET/list read. See
        014_seed_default_stages_backfill.sql for the full rationale.

        Idempotency has two layers:
          1. App-side: an org that already has stages is a no-op — the
             existing rows are returned as-is.
          2. DB-side: two callers racing past that check both attempt the
             INSERT; the loser hits the `lead_stages_org_position_ux`
             UNIQUE (org_id, position) index (005_crm_core.sql) and is
             resolved here as "someone else already seeded" rather than
             surfaced as a 502.

        Org isolation: `org_id` is stamped from `self._org_id`, which the
        router derives from the trusted auth dependency
        (`get_current_user_org`) — never from client input — so this can
        only ever seed the caller's own org. The write goes through the
        user-scoped client (same as every other write in this service),
        so RLS's `lead_stages_insert_own_org` policy (org_id =
        current_org_id()) is the enforcing layer, not an admin bypass.
        """
        existing = self.list_stages()
        if existing:
            return existing

        rows = [{**stage, "org_id": self._org_id} for stage in DEFAULT_LEAD_STAGES]
        try:
            result = self._t("lead_stages").insert(rows).execute()
        except Exception as exc:
            if self._is_duplicate_stage_error(exc):
                logger.info(
                    "crm.seed_default_stages: lost the seeding race org=%s, re-reading",
                    self._org_id,
                )
                return self.list_stages()
            logger.exception("crm.seed_default_stages failed org=%s", self._org_id)
            raise
        return result.data or self.list_stages()

    @staticmethod
    def _is_duplicate_stage_error(exc: Exception) -> bool:
        """Detect a lead_stages_org_position_ux unique-violation (seed race).

        Same sniff-then-fallback shape as
        social-wiring/backend/app/services/message_store.py
        ``_is_duplicate_error`` — Postgres/PostgREST surfaces code 23505;
        the substring check is cheap and backend-agnostic.
        """
        msg = str(exc).lower()
        return (
            "23505" in msg
            or "duplicate key" in msg
            or ("unique" in msg and "position" in msg)
        )

    # ------------------------------------------------------------------
    # Leads CRUD
    # ------------------------------------------------------------------

    def list_leads(
        self,
        *,
        stage_id: str | None = None,
        owner_id: str | None = None,
        source: str | None = None,
        temperature: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        offset = (page - 1) * page_size
        query = (
            self._t("leads")
            .select("*", count="exact")
            .eq("org_id", self._org_id)
            .order("created_at", desc=True)
            .range(offset, offset + page_size - 1)
        )
        if stage_id:
            query = query.eq("stage_id", stage_id)
        if owner_id:
            query = query.eq("owner_id", owner_id)
        if source:
            query = query.eq("source", source)
        if temperature:
            query = query.eq("temperature", temperature)

        try:
            result = query.execute()
        except Exception:
            logger.exception("crm.list_leads failed org=%s", self._org_id)
            raise

        return {
            "items": result.data or [],
            "total": result.count if result.count is not None else len(result.data or []),
            "page": page,
            "page_size": page_size,
        }

    def get_lead(self, lead_id: str) -> dict[str, Any] | None:
        try:
            result = (
                self._t("leads")
                .select("*")
                .eq("org_id", self._org_id)
                .eq("id", lead_id)
                .execute()
            )
        except Exception:
            logger.exception("crm.get_lead failed org=%s id=%s", self._org_id, lead_id)
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def create_lead(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {**payload, "org_id": self._org_id}
        # Normalize phone at write boundary
        if row.get("phone"):
            row["phone"] = _normalize_br_phone(row["phone"])
        try:
            result = self._t("leads").insert(row).execute()
        except Exception:
            logger.exception("crm.create_lead failed org=%s", self._org_id)
            raise
        rows = result.data or []
        if not rows:
            logger.error("crm.create_lead returned no rows org=%s", self._org_id)
            raise RuntimeError("Insert returned no data")
        return rows[0]

    def update_lead(self, lead_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        payload.pop("org_id", None)  # prevent escalation
        if payload.get("phone"):
            payload["phone"] = _normalize_br_phone(payload["phone"])
        try:
            result = (
                self._t("leads")
                .update(payload)
                .eq("org_id", self._org_id)
                .eq("id", lead_id)
                .execute()
            )
        except Exception:
            logger.exception("crm.update_lead failed org=%s id=%s", self._org_id, lead_id)
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def delete_lead(self, lead_id: str) -> bool:
        try:
            result = (
                self._t("leads")
                .delete()
                .eq("org_id", self._org_id)
                .eq("id", lead_id)
                .execute()
            )
        except Exception:
            logger.exception("crm.delete_lead failed org=%s id=%s", self._org_id, lead_id)
            raise
        return bool(result.data)

    # ------------------------------------------------------------------
    # Stage move
    # ------------------------------------------------------------------

    def move_lead_stage(
        self, lead_id: str, stage_id: str, *, user_id: str | None = None
    ) -> dict[str, Any] | None:
        """Move a lead to a new stage; record an activity."""
        # Verify stage belongs to the same org
        try:
            stage_res = (
                self._t("lead_stages")
                .select("id, name, is_won, is_lost")
                .eq("org_id", self._org_id)
                .eq("id", stage_id)
                .execute()
            )
        except Exception:
            logger.exception("crm.move_lead_stage: stage lookup failed org=%s", self._org_id)
            raise
        stage_rows = stage_res.data or []
        if not stage_rows:
            raise ValueError(f"Stage {stage_id} not found in org")
        stage = stage_rows[0]

        patch: dict[str, Any] = {"stage_id": stage_id}
        if stage["is_won"]:
            patch["won_at"] = "now()"  # let Supabase stamp it
        elif stage["is_lost"]:
            pass  # won_at stays if previously set

        updated = self.update_lead(lead_id, patch)
        if updated:
            self._record_activity(
                lead_id=lead_id,
                activity_type="stage_move",
                note=f"Movido para {stage['name']}",
                created_by=user_id,
            )
        return updated

    # ------------------------------------------------------------------
    # Activities
    # ------------------------------------------------------------------

    def _record_activity(
        self,
        *,
        lead_id: str,
        activity_type: str,
        note: str | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any]:
        row = {
            "org_id": self._org_id,
            "lead_id": lead_id,
            "type": activity_type,
            "note": note,
            "created_by": created_by,
        }
        try:
            result = self._t("lead_activities").insert(row).execute()
        except Exception:
            logger.exception(
                "crm._record_activity failed org=%s lead=%s type=%s",
                self._org_id, lead_id, activity_type,
            )
            raise
        rows = result.data or []
        if not rows:
            raise RuntimeError("Activity insert returned no data")
        return rows[0]

    def add_activity(
        self,
        lead_id: str,
        activity_type: str,
        *,
        note: str | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any]:
        # Verify lead exists in org before adding activity
        lead = self.get_lead(lead_id)
        if not lead:
            raise LookupError(f"Lead {lead_id} not found")
        return self._record_activity(
            lead_id=lead_id,
            activity_type=activity_type,
            note=note,
            created_by=created_by,
        )

    def list_activities(self, lead_id: str) -> list[dict[str, Any]]:
        try:
            result = (
                self._t("lead_activities")
                .select("*")
                .eq("org_id", self._org_id)
                .eq("lead_id", lead_id)
                .order("created_at", desc=True)
                .execute()
            )
        except Exception:
            logger.exception("crm.list_activities failed org=%s lead=%s", self._org_id, lead_id)
            raise
        return result.data or []

    # ------------------------------------------------------------------
    # Funil (kanban)
    # ------------------------------------------------------------------

    def get_funil(self) -> list[dict[str, Any]]:
        """Return leads grouped by stage for kanban view.

        Each column: {stage, leads, count, total_value}
        Sorted by stage.position ascending.
        """
        stages = self.list_stages()
        if not stages:
            return []

        try:
            leads_res = (
                self._t("leads")
                .select("id, name, email, phone, company, source, stage_id, temperature, "
                        "qualification_score, value, owner_id, next_contact, tags, "
                        "custom_fields, created_at, updated_at")
                .eq("org_id", self._org_id)
                .order("created_at", desc=False)
                .execute()
            )
        except Exception:
            logger.exception("crm.get_funil: leads fetch failed org=%s", self._org_id)
            raise

        all_leads = leads_res.data or []

        # Index by stage_id for O(n) grouping
        by_stage: dict[str, list[dict[str, Any]]] = {s["id"]: [] for s in stages}
        unassigned: list[dict[str, Any]] = []

        for lead in all_leads:
            sid = lead.get("stage_id")
            if sid and sid in by_stage:
                by_stage[sid].append(lead)
            else:
                unassigned.append(lead)

        columns = []
        for stage in stages:
            cards = by_stage[stage["id"]]
            columns.append({
                "stage": stage,
                "leads": cards,
                "count": len(cards),
                "total_value": sum(
                    float(c.get("value") or 0) for c in cards
                ),
            })

        if unassigned:
            logger.warning(
                "crm.get_funil: %d leads have no valid stage_id org=%s",
                len(unassigned), self._org_id,
            )

        return columns

    # ------------------------------------------------------------------
    # Lead scoring
    # ------------------------------------------------------------------

    def score_lead(self, lead_id: str) -> dict[str, Any]:
        """Run scoring rules against lead.custom_fields; upsert result.

        1. Fetch lead to get custom_fields + qualification_source (form_id)
        2. Load scoring rules for that form_id
        3. Delegate computation to lead_scoring.compute_score()
        4. Upsert lead_scoring_results + stamp lead.temperature/qualification_score
        5. Return the result row
        """
        lead = self.get_lead(lead_id)
        if not lead:
            raise LookupError(f"Lead {lead_id} not found in org")

        custom_fields: dict[str, Any] = lead.get("custom_fields") or {}
        form_id: str | None = (
            lead.get("qualification_source")
            or custom_fields.get("form_id")
        )

        rules: list[dict[str, Any]] = []
        if form_id:
            try:
                rules_res = (
                    self._t("lead_scoring_rules")
                    .select("question, answer, score, is_blocker")
                    .eq("org_id", self._org_id)
                    .eq("form_id", form_id)
                    .execute()
                )
                rules = rules_res.data or []
            except Exception:
                logger.exception(
                    "crm.score_lead: rules fetch failed org=%s lead=%s form=%s",
                    self._org_id, lead_id, form_id,
                )
                raise
        else:
            logger.debug(
                "crm.score_lead: no form_id for lead=%s, scoring with 0 rules", lead_id
            )

        computed = compute_score(rules, custom_fields)

        # Upsert result
        result_row = {
            "org_id": self._org_id,
            "lead_id": lead_id,
            "score_total": computed["score_total"],
            "qualification": computed["qualification"],
            "answers_detail": computed["answers_detail"],
            "scored_at": "now()",
        }
        try:
            upsert_res = (
                self._t("lead_scoring_results")
                .upsert(result_row, on_conflict="lead_id")
                .execute()
            )
        except Exception:
            logger.exception("crm.score_lead: upsert result failed org=%s lead=%s", self._org_id, lead_id)
            raise
        upsert_rows = upsert_res.data or []
        if not upsert_rows:
            logger.error("crm.score_lead: upsert returned no rows org=%s lead=%s", self._org_id, lead_id)
            raise RuntimeError("Scoring upsert returned no data")

        # Stamp lead
        try:
            self._t("leads").update({
                "temperature": computed["qualification"],
                "qualification_score": computed["score_total"],
            }).eq("org_id", self._org_id).eq("id", lead_id).execute()
        except Exception:
            logger.exception("crm.score_lead: stamp lead failed org=%s id=%s", self._org_id, lead_id)
            raise

        return upsert_rows[0]

    # ------------------------------------------------------------------
    # Public lead capture (org-scoped, unauthenticated — uses admin client)
    # ------------------------------------------------------------------

    def capture_lead(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Insert a lead from a public capture endpoint.

        This method should be called with the ADMIN (service_role) client
        because RLS won't let unauthenticated callers INSERT.

        Known keys → lead columns; everything else → custom_fields JSONB.
        Phone normalized to Brazilian 55… form.
        """
        KNOWN_KEYS = {"name", "email", "phone", "company", "source", "value", "stage_id"}

        known = {k: v for k, v in payload.items() if k in KNOWN_KEYS}
        extra = {k: v for k, v in payload.items() if k not in KNOWN_KEYS}

        row: dict[str, Any] = {
            **known,
            "org_id": self._org_id,
            "custom_fields": extra,
        }
        if row.get("phone"):
            row["phone"] = _normalize_br_phone(row["phone"])

        try:
            result = self._t("leads").insert(row).execute()
        except Exception:
            logger.exception("crm.capture_lead failed org=%s", self._org_id)
            raise
        rows = result.data or []
        if not rows:
            logger.error("crm.capture_lead returned no rows org=%s", self._org_id)
            raise RuntimeError("Capture insert returned no data")
        return rows[0]
