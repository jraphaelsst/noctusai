"""Meta Lead-Ads (Instant Form) ingest — pull forms + leads from Graph
and upsert them into ``meta_ads_lead_forms`` / ``meta_ads_leads``
(migration 033).

Complements ``ads_sync_service`` (which owns the campaign/insight/activity
tables). Kept a SEPARATE service because leads are Page-scoped (enumerated
via ``list_facebook_pages`` → ``list_leadgen_forms`` → ``list_leads``),
not ad-account-scoped, and the lead RECORDS are gated on the distinct
``leads_retrieval`` scope — a gate this service SURFACES (skips records,
still syncs forms) rather than letting it fail the whole run.

DATA MODEL (migration 033, "typed core + JSONB tail"): the always-present
contact fields (``full_name``/``email``/``phone``) are promoted to typed
columns by mapping each ``field_data`` entry to its owning form question's
TYPE (FULL_NAME / EMAIL / PHONE) — robust to the label-vs-key variance
across forms. Every answered field (including hidden ones Meta injects
like ``REF``, which are NOT in the form's question list) is kept in the
``answers`` JSONB object, so the record is lossless AND the typed columns
stay a queryable projection.

Admin client for ALL writes (service role) — same convention as
``AdsSyncService``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from noctusai_lib.integrations.meta import MetaAdapter, MetaGraphError
from noctusai_lib.primitives.phone import normalize_phone

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"

# Meta question types whose answer we promote to a typed column.
_PROMOTE_BY_TYPE = {
    "FULL_NAME": "full_name",
    "EMAIL": "email",
    "PHONE": "phone",
}


def _iso(dt: Any) -> str | None:
    return dt.isoformat() if isinstance(dt, datetime) else None


def _answer_value(values: list[str]) -> Any:
    """A field's stored value: the scalar when single-valued (the common
    case), else the full list — never lossy."""
    if not values:
        return None
    return values[0] if len(values) == 1 else list(values)


class LeadsSyncService:
    """Per-call lead ingest worker."""

    def __init__(self, *, admin_supabase: Any) -> None:
        self._admin = admin_supabase

    # ─── forms ─────────────────────────────────────────────────────────
    def sync_forms(
        self, *, org_id: UUID, adapter: MetaAdapter
    ) -> tuple[list[Any], dict[str, dict[str, str]]]:
        """Enumerate the workspace Pages → upsert every lead-gen form (with
        its field schema) into ``meta_ads_lead_forms``.

        Returns ``(forms, key_type_by_form)`` — the enumerated
        ``LeadgenForm`` list (so callers don't re-hit Graph) and
        ``key_type_by_form[form_id][question_key] = question_type``, the map
        :meth:`sync_leads` uses to promote contact columns."""
        now_iso = datetime.now(timezone.utc).isoformat()
        key_type_by_form: dict[str, dict[str, str]] = {}
        all_forms: list[Any] = []
        for page in adapter.list_facebook_pages():
            forms = adapter.list_leadgen_forms(page.id, with_questions=True)
            for form in forms:
                all_forms.append(form)
                key_type_by_form[form.id] = {
                    q.key: q.type for q in form.questions if q.key
                }
                row = {
                    "id": form.id,
                    "org_id": str(org_id),
                    "page_id": form.page_id or page.id,
                    "name": form.name,
                    "status": form.status,
                    "locale": form.locale,
                    "leads_count": form.leads_count,
                    "questions": [
                        {
                            "key": q.key,
                            "label": q.label,
                            "type": q.type,
                            "options": list(q.options),
                        }
                        for q in form.questions
                    ],
                    "created_time": _iso(form.created_time),
                    "synced_at": now_iso,
                }
                (
                    self._admin.schema(_SCHEMA)
                    .table("meta_ads_lead_forms")
                    .upsert(row, on_conflict="id")
                    .execute()
                )
        return all_forms, key_type_by_form

    # ─── leads ─────────────────────────────────────────────────────────
    def sync_leads(
        self,
        *,
        org_id: UUID,
        adapter: MetaAdapter,
        key_type_by_form: dict[str, dict[str, str]],
        forms: list[Any],
        per_form_limit: int = 500,
    ) -> dict[str, Any]:
        """Fetch + upsert the RECORDS for every form that has leads.

        ``forms`` is the list of ``LeadgenForm`` (from
        :meth:`sync_forms`'s enumeration or a DB read). Records are gated
        on ``leads_retrieval``: a permission error is SURFACED into the
        return (``gated=True``) and the run continues to the next form —
        never a faked-empty success, never a hard failure that loses the
        forms already synced."""
        upserted = 0
        gated = False
        forms_with_leads = [f for f in forms if int(f.leads_count or 0) > 0]
        for form in forms_with_leads:
            try:
                leads = adapter.list_leads(
                    form.id, page_id=form.page_id, limit=per_form_limit
                )
            except MetaGraphError as exc:
                if exc.is_permission:
                    gated = True
                    logger.info(
                        "meta ads leads: records gated (leads_retrieval) — "
                        "form %s skipped", form.id,
                    )
                    continue
                raise
            key_types = key_type_by_form.get(form.id, {})
            for lead in leads:
                self._upsert_lead(
                    lead, org_id=org_id, form=form, key_types=key_types
                )
                upserted += 1
        return {"leads_upserted": upserted, "records_gated": gated}

    def _upsert_lead(
        self, lead: Any, *, org_id: UUID, form: Any, key_types: dict[str, str]
    ) -> None:
        answers: dict[str, Any] = {}
        promoted: dict[str, str] = {}
        for fd in lead.field_data:
            if not fd.name:
                continue
            val = _answer_value(fd.values)
            answers[fd.name] = val
            col = _PROMOTE_BY_TYPE.get(key_types.get(fd.name, ""))
            if col and fd.values:
                promoted[col] = fd.values[0]
        row = {
            "id": lead.id,
            "org_id": str(org_id),
            "form_id": lead.form_id or form.id,
            "form_name": form.name,
            "ad_id": lead.ad_id,
            "adset_id": lead.adset_id,
            "campaign_id": lead.campaign_id,
            "campaign_name": lead.campaign_name,
            "platform": lead.platform,
            "is_organic": lead.is_organic,
            "created_time": _iso(lead.created_time),
            "full_name": promoted.get("full_name"),
            "email": promoted.get("email"),
            # Meta already delivers E.164 for ~92% of leads, which is exactly
            # why that shape was chosen as the platform canon — so this is a
            # no-op on the common path and a repair on the rest (missing
            # country code, stray formatting). `normalize_phone` returns None
            # rather than guessing at a malformed number, so fall back to what
            # Meta sent: a number a human can see is a number a human can fix.
            # The untouched original is in `raw` either way.
            "phone": normalize_phone(promoted.get("phone")) or promoted.get("phone"),
            "answers": answers,
            "raw": [
                {"name": fd.name, "values": list(fd.values)}
                for fd in lead.field_data
            ],
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
        (
            self._admin.schema(_SCHEMA)
            .table("meta_ads_leads")
            .upsert(row, on_conflict="id")
            .execute()
        )

    # ─── orchestration ─────────────────────────────────────────────────
    def sync_all(
        self, *, org_id: UUID, adapter: MetaAdapter, per_form_limit: int = 500
    ) -> dict[str, Any]:
        """Full lead ingest: forms (always) → records (when the scope is
        granted). One call behind the ``POST /leads/sync`` trigger."""
        forms, key_type_by_form = self.sync_forms(org_id=org_id, adapter=adapter)
        leads_result = self.sync_leads(
            org_id=org_id,
            adapter=adapter,
            key_type_by_form=key_type_by_form,
            forms=forms,
            per_form_limit=per_form_limit,
        )
        return {"forms_upserted": len(forms), **leads_result}
