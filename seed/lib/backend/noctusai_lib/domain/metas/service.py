"""`MetasService` -- the metas organ's rules over an `OrgTableStore`: periods, teams, goals at three levels, point
rules, scoring events, rankings and period closings.

Every method takes the `org_id` (or an :class:`Actor`, which carries it): a foreign-org id is a 404. Visibility is the
organ's privacy contract -- an admin sees the whole org; a member sees their own events / closings, a team leader those
of the teams they lead; rankings show a member only the teams they belong to. Totals come from ONE SQL aggregate
(`MetasStore.event_totals`), never a Python loop over event rows.

Closing a period is idempotent and crash-safe without a transaction across calls: the snapshots go in with ONE bulk
insert (atomic), THEN the period flips to `closed`; a retry after a crash in between finds the snapshots and finishes
the flip. Goal / closing STATUS HISTORY is not modelled here: it rides the seed transition-log primitive when it lands
(named follow-up, `KB § PATTERNS/backend/metas-seed.md`).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping, Optional, Sequence

from noctusai_lib.domain._organ_common import StoreConflict
from noctusai_lib.domain.metas.config import MetasConfig
from noctusai_lib.domain.metas.errors import (
    CONFIGURACAO_INVALIDA,
    EQUIPE_DUPLICADA,
    EQUIPE_INVALIDA,
    EVENTO_INVALIDO,
    FECHAMENTO_EXISTENTE,
    FILTRO_INVALIDO,
    MEMBRO_DUPLICADO,
    META_DUPLICADA,
    META_INVALIDA,
    PERIODO_FECHADO,
    PERIODO_INVALIDO,
    REGRA_DUPLICADA,
    REGRA_INVALIDA,
    conflict,
    forbidden,
    invalid,
    not_found,
)
from noctusai_lib.domain.metas.goal_repository import goal_from_row, to_date
from noctusai_lib.domain.metas.periods import period_bounds
from noctusai_lib.domain.metas.progress import accumulate_contribution, compute_progress
from noctusai_lib.domain.metas.store import MetasStore
from noctusai_lib.domain.metas.value_objects import Contribution, GoalStatus, PeriodKind, Target

SCOPES = ("individual", "team", "company")
METRICS = ("points", "value", "unified")
USER_SETTABLE_STATUSES = (GoalStatus.PENDING.value, GoalStatus.IN_PROGRESS.value, GoalStatus.ABANDONED.value)
DEFAULT_SETTINGS = {"value_per_point": 10000.0, "weight_points": 1.0, "weight_value": 1.0, "default_ranking_metric": "unified"}


@dataclass(frozen=True)
class Actor:
    """Who is calling: the SELECTED org, the user, and the trusted admin flag of that org."""

    org_id: str
    user_id: str
    is_admin: bool = False


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _iso(value: Optional[date]) -> Optional[str]:
    return value.isoformat() if value else None


def out(row: Mapping[str, Any]) -> dict:
    """A row for the wire: the tenant key stays server-side."""
    return {k: v for k, v in row.items() if k != "org_id"}


def competition_ranks(scores: Sequence[tuple[str, float]]) -> list[tuple[str, float, int]]:
    """Descending `(key, score)` with standard competition ranking (1, 1, 3); ties ordered by key for a stable row order."""
    ordered = sorted(scores, key=lambda kv: (-kv[1], kv[0]))
    result: list[tuple[str, float, int]] = []
    prev: Optional[float] = None
    rank = 0
    for pos, (key, score) in enumerate(ordered, start=1):
        if score != prev:
            rank = pos
        result.append((key, score, rank))
        prev = score
    return result


class MetasService:
    def __init__(self, store: MetasStore, cfg: MetasConfig) -> None:
        self.store = store
        self.cfg = cfg

    # -- shared -------------------------------------------------------------------------------------------------

    def _get(self, table: str, org_id: str, row_id: str, what: str) -> dict:
        row = self.store.get(table, org_id, str(row_id))
        if row is None:
            raise not_found(what)
        return row

    def _led_team_ids(self, org_id: str, user_id: str) -> list[str]:
        led = {str(m["team_id"]) for m in self.store.select("team_members", org_id, eq={"user_id": user_id, "role": "leader"}, is_null=("left_at",))}
        led |= {str(t["id"]) for t in self.store.select("teams", org_id, eq={"leader_id": user_id, "active": True})}
        return sorted(led)

    def _my_team_ids(self, org_id: str, user_id: str) -> list[str]:
        mine = {str(m["team_id"]) for m in self.store.select("team_members", org_id, eq={"user_id": user_id}, is_null=("left_at",))}
        return sorted(mine | set(self._led_team_ids(org_id, user_id)))

    def _members_of(self, org_id: str, team_ids: Sequence[str]) -> set[str]:
        if not team_ids:
            return set()
        rows = self.store.select("team_members", org_id, in_={"team_id": team_ids}, is_null=("left_at",))
        return {str(r["user_id"]) for r in rows}

    def _visible_members(self, actor: Actor, *, led_only: bool) -> Optional[set[str]]:
        """None = everybody (admin); else the member ids this actor may see."""
        if actor.is_admin:
            return None
        teams = self._led_team_ids(actor.org_id, actor.user_id) if led_only else self._my_team_ids(actor.org_id, actor.user_id)
        return {actor.user_id} | self._members_of(actor.org_id, teams)

    @staticmethod
    def _need_admin(actor: Actor, what: str) -> None:
        if not actor.is_admin:
            raise forbidden(f"{what}: restrito a administradores.")

    # -- periods ------------------------------------------------------------------------------------------------

    def list_periods(self, org_id: str, *, kind: Optional[str] = None, status: Optional[str] = None, containing: Optional[date] = None) -> list[dict]:
        rows = self.store.select(
            "periods", org_id, eq={k: v for k, v in (("kind", kind), ("status", status)) if v}, order=(("starts_on", True), ("ends_on", False))
        )
        if containing:
            rows = [r for r in rows if to_date(r["starts_on"]) <= containing <= to_date(r["ends_on"])]
        return [out(r) for r in rows]

    def get_period(self, org_id: str, period_id: str) -> dict:
        return out(self._get("periods", org_id, period_id, "Período"))

    @staticmethod
    def _check_window(kind: str, start: date, end: date) -> None:
        if kind not in {k.value for k in PeriodKind if k is not PeriodKind.OPEN_ENDED}:
            raise invalid("kind", "Tipo de período inválido.", PERIODO_INVALIDO)
        if end < start:
            raise invalid("ends_on", "O fim do período vem antes do início.", PERIODO_INVALIDO)

    def _check_parent(self, org_id: str, parent_id: Optional[str], start: date, end: date, *, self_id: Optional[str] = None) -> None:
        if not parent_id:
            return
        if self_id and str(parent_id) == str(self_id):
            raise invalid("parent_id", "Um período não pode ser pai de si mesmo.", PERIODO_INVALIDO)
        parent = self.store.get("periods", org_id, str(parent_id))
        if parent is None:
            raise invalid("parent_id", "Período pai não encontrado.", PERIODO_INVALIDO)
        if not (to_date(parent["starts_on"]) <= start and end <= to_date(parent["ends_on"])):
            raise invalid("parent_id", "O período pai precisa conter o período filho.", PERIODO_INVALIDO)

    def create_period(self, org_id: str, data: Mapping[str, Any]) -> dict:
        start, end = data["starts_on"], data["ends_on"]
        self._check_window(data["kind"], start, end)
        self._check_parent(org_id, data.get("parent_id"), start, end)
        row = {"name": data["name"].strip(), "kind": data["kind"], "starts_on": _iso(start), "ends_on": _iso(end), "parent_id": data.get("parent_id"), "status": "open"}
        return out(self.store.insert("periods", org_id, [row])[0])

    def update_period(self, org_id: str, period_id: str, patch: Mapping[str, Any]) -> dict:
        cur = self._get("periods", org_id, period_id, "Período")
        if cur["status"] == "closed":
            raise conflict(PERIODO_FECHADO, "Período fechado: não pode ser alterado.")
        if patch.get("status") == "closed":
            raise invalid("status", "Feche o período pelo fechamento (POST /closings/close).", PERIODO_INVALIDO)
        start = patch.get("starts_on") or to_date(cur["starts_on"])
        end = patch.get("ends_on") or to_date(cur["ends_on"])
        kind = patch.get("kind") or cur["kind"]
        self._check_window(kind, start, end)
        self._check_parent(org_id, patch["parent_id"] if "parent_id" in patch else cur.get("parent_id"), start, end, self_id=period_id)
        body = {k: v for k, v in patch.items() if k in ("name", "kind", "parent_id", "status")}
        if "name" in body:
            body["name"] = body["name"].strip()
        if "starts_on" in patch:
            body["starts_on"] = _iso(start)
        if "ends_on" in patch:
            body["ends_on"] = _iso(end)
        return out(self.store.update("periods", org_id, period_id, body) or cur)

    def delete_period(self, org_id: str, period_id: str) -> None:
        self._get("periods", org_id, period_id, "Período")
        if self.store.select("closings", org_id, eq={"period_id": period_id}, limit=1):
            raise conflict(FECHAMENTO_EXISTENTE, "O período tem fechamento: o histórico não se apaga.")
        self.store.delete("periods", org_id, period_id)

    def generate_periods(self, org_id: str, kind: str, start: date, end: date) -> list[dict]:
        """The periods of `kind` covering `[start, end]` that do not exist yet (matched by kind + start date)."""
        self._check_window(kind, start, end)
        pk = PeriodKind(kind)
        existing = {(r["kind"], r["starts_on"]) for r in self.store.select("periods", org_id, eq={"kind": kind})}
        rows: list[dict] = []
        cursor = start
        while cursor <= end:
            p_start, p_end = period_bounds(pk, cursor)
            if (kind, p_start.isoformat()) not in existing:
                rows.append({"name": f"{kind} {p_start.isoformat()}", "kind": kind, "starts_on": p_start.isoformat(), "ends_on": p_end.isoformat(), "status": "open"})
            cursor = p_end + timedelta(days=1)
        if len(rows) > 400:
            raise invalid("ends_on", "Intervalo grande demais para gerar de uma vez.", PERIODO_INVALIDO)
        return [out(r) for r in self.store.insert("periods", org_id, rows)] if rows else []

    def resolve_period(self, org_id: str, day: date) -> Optional[dict]:
        """The narrowest period containing `day` (None when there is none)."""
        rows = [r for r in self.store.select("periods", org_id, lte={"starts_on": day.isoformat()}, gte={"ends_on": day.isoformat()})]
        return min(rows, key=lambda r: (to_date(r["ends_on"]) - to_date(r["starts_on"])).days, default=None)

    # -- teams --------------------------------------------------------------------------------------------------

    def list_teams(self, org_id: str, *, include_inactive: bool = False) -> list[dict]:
        rows = self.store.select("teams", org_id, eq=None if include_inactive else {"active": True}, order=(("name", False),))
        return [out(r) for r in rows]

    def get_team(self, org_id: str, team_id: str) -> dict:
        return out(self._get("teams", org_id, team_id, "Equipe"))

    def create_team(self, org_id: str, data: Mapping[str, Any]) -> dict:
        row = {k: data.get(k) for k in ("name", "color", "icon", "leader_id")}
        row["name"] = data["name"].strip()
        row["active"] = True
        try:
            team = self.store.insert("teams", org_id, [row])[0]
        except StoreConflict:
            raise conflict(EQUIPE_DUPLICADA, "Já existe uma equipe com esse nome.") from None
        if team.get("leader_id"):
            self._ensure_member(org_id, team["id"], str(team["leader_id"]), "leader")
        return out(team)

    def update_team(self, org_id: str, team_id: str, patch: Mapping[str, Any]) -> dict:
        cur = self._get("teams", org_id, team_id, "Equipe")
        if not cur.get("active", True):
            raise invalid("team_id", "Equipe dissolvida.", EQUIPE_INVALIDA)
        body = {k: v for k, v in patch.items() if k in ("name", "color", "icon", "leader_id")}
        if "name" in body:
            body["name"] = body["name"].strip()
        try:
            team = self.store.update("teams", org_id, team_id, body) or cur
        except StoreConflict:
            raise conflict(EQUIPE_DUPLICADA, "Já existe uma equipe com esse nome.") from None
        if body.get("leader_id"):
            self._ensure_member(org_id, team_id, str(body["leader_id"]), "leader")
        return out(team)

    def disband_team(self, org_id: str, team_id: str) -> None:
        """Soft delete: the history of who was on the team (and the events snapshotted to it) stays."""
        self._get("teams", org_id, team_id, "Equipe")
        now = datetime.now(timezone.utc).isoformat()
        for m in self.store.select("team_members", org_id, eq={"team_id": team_id}, is_null=("left_at",)):
            self.store.update("team_members", org_id, m["id"], {"left_at": now})
        self.store.update("teams", org_id, team_id, {"active": False, "disbanded_at": now})

    def list_members(self, org_id: str, team_id: str, *, include_left: bool = False) -> list[dict]:
        self._get("teams", org_id, team_id, "Equipe")
        rows = self.store.select("team_members", org_id, eq={"team_id": team_id}, is_null=() if include_left else ("left_at",), order=(("joined_at", False),))
        return [out(r) for r in rows]

    def _ensure_member(self, org_id: str, team_id: str, user_id: str, role: str) -> dict:
        existing = self.store.select("team_members", org_id, eq={"team_id": team_id, "user_id": user_id}, is_null=("left_at",), limit=1)
        if existing:
            return existing[0] if existing[0]["role"] == role else (self.store.update("team_members", org_id, existing[0]["id"], {"role": role}) or existing[0])
        return self.store.insert("team_members", org_id, [{"team_id": team_id, "user_id": user_id, "role": role, "joined_at": datetime.now(timezone.utc).isoformat()}])[0]

    def add_member(self, org_id: str, team_id: str, user_id: str, role: str = "member") -> dict:
        team = self._get("teams", org_id, team_id, "Equipe")
        if not team.get("active", True):
            raise invalid("team_id", "Equipe dissolvida.", EQUIPE_INVALIDA)
        if self.store.select("team_members", org_id, eq={"team_id": team_id, "user_id": user_id}, is_null=("left_at",), limit=1):
            raise conflict(MEMBRO_DUPLICADO, "O usuário já é membro ativo desta equipe.")
        try:
            row = self.store.insert("team_members", org_id, [{"team_id": team_id, "user_id": user_id, "role": role, "joined_at": datetime.now(timezone.utc).isoformat()}])[0]
        except StoreConflict:
            raise conflict(MEMBRO_DUPLICADO, "O usuário já é membro ativo desta equipe.") from None
        if role == "leader":
            self.store.update("teams", org_id, team_id, {"leader_id": user_id})
        return out(row)

    def update_member(self, org_id: str, team_id: str, member_id: str, role: str) -> dict:
        m = self._get("team_members", org_id, member_id, "Membro")
        if str(m["team_id"]) != str(team_id) or m.get("left_at"):
            raise not_found("Membro")
        row = self.store.update("team_members", org_id, member_id, {"role": role}) or m
        if role == "leader":
            self.store.update("teams", org_id, team_id, {"leader_id": m["user_id"]})
        elif str(self._get("teams", org_id, team_id, "Equipe").get("leader_id")) == str(m["user_id"]):
            self.store.update("teams", org_id, team_id, {"leader_id": None})
        return out(row)

    def remove_member(self, org_id: str, team_id: str, member_id: str) -> None:
        """The member LEAVES (`left_at`); the row stays as history."""
        m = self._get("team_members", org_id, member_id, "Membro")
        if str(m["team_id"]) != str(team_id) or m.get("left_at"):
            raise not_found("Membro")
        self.store.update("team_members", org_id, member_id, {"left_at": datetime.now(timezone.utc).isoformat()})
        if str(self._get("teams", org_id, team_id, "Equipe").get("leader_id")) == str(m["user_id"]):
            self.store.update("teams", org_id, team_id, {"leader_id": None})

    def team_of(self, org_id: str, user_id: str) -> Optional[str]:
        rows = self.store.select("team_members", org_id, eq={"user_id": user_id}, is_null=("left_at",), order=(("joined_at", False),), limit=1)
        return str(rows[0]["team_id"]) if rows else None

    # -- settings / rules ---------------------------------------------------------------------------------------

    def get_settings(self, org_id: str) -> dict:
        rows = self.store.select("settings", org_id, limit=1)
        if not rows:
            return {**DEFAULT_SETTINGS, "is_default": True}
        r = rows[0]
        return {**{k: (float(r[k]) if k != "default_ranking_metric" else r[k]) for k in DEFAULT_SETTINGS}, "is_default": False}

    def put_settings(self, org_id: str, data: Mapping[str, Any]) -> dict:
        body = {k: v for k, v in data.items() if k in DEFAULT_SETTINGS and v is not None}
        if body.get("value_per_point", 1) <= 0:
            raise invalid("value_per_point", "A conversão valor/ponto precisa ser positiva.", CONFIGURACAO_INVALIDA)
        if body.get("default_ranking_metric", "unified") not in METRICS:
            raise invalid("default_ranking_metric", "Métrica de ranking inválida.", CONFIGURACAO_INVALIDA)
        rows = self.store.select("settings", org_id, limit=1)
        try:
            if rows:
                self.store.update("settings", org_id, rows[0]["id"], body)
            else:  # the full row, so the Fake and the DB agree on every column
                self.store.insert("settings", org_id, [{**DEFAULT_SETTINGS, **body}])
        except StoreConflict:  # a concurrent first save: the second one updates
            again = self.store.select("settings", org_id, limit=1)
            if not again:
                raise
            self.store.update("settings", org_id, again[0]["id"], body)
        return self.get_settings(org_id)

    def list_rules(self, org_id: str, *, period_id: Optional[str] = None) -> list[dict]:
        rows = self.store.select("rules", org_id, eq={"period_id": period_id} if period_id else None, order=(("event_type", False), ("modality", False)))
        return [out(r) for r in rows]

    def _check_event_modality(self, event_type: str, modality: str, *, field: str, code: str) -> None:
        if event_type not in self.cfg.event_slugs:
            raise invalid("event_type", "Tipo de evento desconhecido.", code)
        if modality not in self.cfg.modality_slugs:
            raise invalid("modality", "Modalidade desconhecida.", code)

    def upsert_rule(self, org_id: str, data: Mapping[str, Any]) -> dict:
        modality = data.get("modality") or self.cfg.modality_slugs[0]
        self._check_event_modality(data["event_type"], modality, field="event_type", code=REGRA_INVALIDA)
        period_id = data.get("period_id")
        if period_id:
            self._get("periods", org_id, period_id, "Período")
        existing = [
            r for r in self.store.select("rules", org_id, eq={"event_type": data["event_type"], "modality": modality})
            if (str(r["period_id"]) if r.get("period_id") else None) == (str(period_id) if period_id else None)
        ]
        body = {"event_type": data["event_type"], "modality": modality, "points": data["points"], "description": data.get("description"), "period_id": period_id}
        try:
            row = self.store.update("rules", org_id, existing[0]["id"], body) if existing else self.store.insert("rules", org_id, [body])[0]
        except StoreConflict:
            raise conflict(REGRA_DUPLICADA, "Já existe uma regra para esse evento e modalidade.") from None
        return out(row or existing[0])

    def delete_rule(self, org_id: str, rule_id: str) -> None:
        self._get("rules", org_id, rule_id, "Regra")
        self.store.delete("rules", org_id, rule_id)

    def seed_default_rules(self, org_id: str) -> list[dict]:
        """Copy the product's `default_rules` the org does not have yet (org-wide rows). Idempotent."""
        have = {(r["event_type"], r["modality"]) for r in self.store.select("rules", org_id, is_null=("period_id",))}
        rows = [
            {"event_type": r.event_type, "modality": r.modality, "points": r.points, "description": r.description or None, "period_id": None}
            for r in self.cfg.default_rules
            if (r.event_type, r.modality) not in have
        ]
        return [out(r) for r in self.store.insert("rules", org_id, rows)] if rows else []

    def _points_for(self, org_id: str, event_type: str, modality: str, period_id: Optional[str], fraction: float) -> float:
        rules = self.store.select("rules", org_id, eq={"event_type": event_type, "modality": modality})
        specific = next((r for r in rules if period_id and str(r.get("period_id")) == str(period_id)), None)
        general = next((r for r in rules if not r.get("period_id")), None)
        rule = specific or general
        return round(float(rule["points"]) * fraction, 6) if rule else 0.0

    # -- events -------------------------------------------------------------------------------------------------

    def record_event(self, actor: Actor, data: Mapping[str, Any]) -> tuple[dict, bool]:
        """Score one event. Returns `(event, created)`; a replay of a `dedupe_key` returns the first one, `created=False`."""
        org_id = actor.org_id
        member = str(data.get("member_id") or actor.user_id)
        if member != actor.user_id and not actor.is_admin:
            raise forbidden("Só um administrador registra eventos de outro membro.")
        modality = data.get("modality") or self.cfg.modality_slugs[0]
        self._check_event_modality(data["event_type"], modality, field="event_type", code=EVENTO_INVALIDO)
        if data.get("points") is not None and not actor.is_admin:
            raise forbidden("Só um administrador define pontos manualmente.")
        key = data.get("dedupe_key")
        if key:
            seen = self.store.select("events", org_id, eq={"dedupe_key": key}, limit=1)
            if seen:
                return out(seen[0]), False
        day = data.get("occurred_on") or _today()
        period = self.resolve_period(org_id, day)
        if period and period["status"] == "closed":
            raise conflict(PERIODO_FECHADO, "O período deste evento já foi fechado.")
        period_id = str(period["id"]) if period else None
        fraction = float(data.get("fraction") or 1)
        manual = data.get("points") is not None
        points = float(data["points"]) if manual else self._points_for(org_id, data["event_type"], modality, period_id, fraction)
        row = {
            "period_id": period_id, "member_id": member, "team_id": self.team_of(org_id, member), "event_type": data["event_type"],
            "modality": modality, "occurred_on": _iso(day), "value": data.get("value"), "points": points, "fraction": fraction,
            "ref_kind": data.get("ref_kind"), "ref_id": data.get("ref_id"), "notes": data.get("notes"),
            "manual_adjustment": manual, "adjusted_by": actor.user_id if manual else None, "dedupe_key": key,
        }
        try:
            return out(self.store.insert("events", org_id, [row])[0]), True
        except StoreConflict:
            seen = self.store.select("events", org_id, eq={"dedupe_key": key}, limit=1) if key else []
            if not seen:
                raise
            return out(seen[0]), False

    def list_events(
        self, actor: Actor, *, member_id: Optional[str] = None, team_id: Optional[str] = None, period_id: Optional[str] = None,
        event_type: Optional[str] = None, start: Optional[date] = None, end: Optional[date] = None, limit: int = 50, offset: int = 0,
    ) -> list[dict]:
        visible = self._visible_members(actor, led_only=True)
        eq = {k: v for k, v in (("member_id", member_id), ("team_id", team_id), ("period_id", period_id), ("event_type", event_type)) if v}
        in_: Optional[dict] = None
        if visible is not None:
            if member_id and member_id not in visible:
                return []
            in_ = {"member_id": sorted(visible)}
        rows = self.store.select(
            "events", actor.org_id, eq=eq, in_=in_, gte={"occurred_on": start.isoformat()} if start else None,
            lte={"occurred_on": end.isoformat()} if end else None, order=(("occurred_on", True), ("created_at", True)), limit=limit, offset=offset,
        )
        return [out(r) for r in rows]

    def adjust_event(self, actor: Actor, event_id: str, patch: Mapping[str, Any]) -> dict:
        self._need_admin(actor, "Ajuste de evento")
        ev = self._get("events", actor.org_id, event_id, "Evento")
        self._assert_event_period_open(actor.org_id, ev)
        body = {k: patch[k] for k in ("points", "notes", "value") if k in patch}
        if "points" in patch or "value" in patch:
            body.update({"manual_adjustment": True, "adjusted_by": actor.user_id})
        return out(self.store.update("events", actor.org_id, event_id, body) or ev)

    def delete_event(self, actor: Actor, event_id: str) -> None:
        self._need_admin(actor, "Exclusão de evento")
        ev = self._get("events", actor.org_id, event_id, "Evento")
        self._assert_event_period_open(actor.org_id, ev)
        self.store.delete("events", actor.org_id, event_id)

    def _assert_event_period_open(self, org_id: str, ev: Mapping[str, Any]) -> None:
        if ev.get("period_id"):
            period = self.store.get("periods", org_id, str(ev["period_id"]))
            if period and period["status"] == "closed":
                raise conflict(PERIODO_FECHADO, "O período deste evento já foi fechado.")

    # -- goals --------------------------------------------------------------------------------------------------

    def _can_manage_goal(self, actor: Actor, scope: str, subject_id: Optional[str]) -> bool:
        if actor.is_admin:
            return True
        if scope == "individual":
            if subject_id == actor.user_id:
                return True
            return subject_id in self._members_of(actor.org_id, self._led_team_ids(actor.org_id, actor.user_id))
        return False  # team + company goals are the owner's

    def _visible_goal(self, actor: Actor, g: Mapping[str, Any]) -> bool:
        if actor.is_admin or g["scope"] == "company":
            return True
        if g["scope"] == "team":
            return str(g["subject_id"]) in self._my_team_ids(actor.org_id, actor.user_id)
        visible = self._visible_members(actor, led_only=True) or {actor.user_id}
        return str(g["subject_id"]) in visible

    def create_goal(self, actor: Actor, data: Mapping[str, Any]) -> dict:
        org_id, scope = actor.org_id, data["scope"]
        subject = str(data["subject_id"]) if data.get("subject_id") else None
        if scope == "individual" and subject is None:
            subject = actor.user_id
        if scope == "company" and subject is not None:
            raise invalid("subject_id", "Meta da empresa não tem sujeito.", META_INVALIDA)
        if scope == "team":
            if subject is None:
                raise invalid("subject_id", "Informe a equipe da meta.", META_INVALIDA)
            self._get("teams", org_id, subject, "Equipe")
        if data["category"] not in self.cfg.category_slugs:
            raise invalid("category", "Categoria de meta desconhecida.", META_INVALIDA)
        if not self._can_manage_goal(actor, scope, subject):
            raise forbidden("Sem permissão para definir esta meta.")
        starts, ends = data.get("starts_on"), data.get("ends_on")
        period_id = data.get("period_id")
        if period_id:
            period = self._get("periods", org_id, period_id, "Período")
            if period["status"] == "closed":
                raise conflict(PERIODO_FECHADO, "Período fechado: não aceita novas metas.")
            starts, ends = to_date(period["starts_on"]), to_date(period["ends_on"])
        elif starts and ends and ends < starts:
            raise invalid("ends_on", "O fim vem antes do início.", META_INVALIDA)
        row = {
            "scope": scope, "subject_id": subject, "category": data["category"], "title": data.get("title"), "target": data["target"],
            "current": 0, "status": GoalStatus.PENDING.value, "period_id": period_id, "starts_on": _iso(starts), "ends_on": _iso(ends),
            "notes": data.get("notes"), "set_by": actor.user_id,
        }
        try:
            created = self.store.insert("goals", org_id, [row])[0]
        except StoreConflict:
            raise conflict(META_DUPLICADA, "Já existe uma meta dessa categoria para este período.") from None
        return self.present_goal(org_id, created)

    def _goal(self, actor: Actor, goal_id: str) -> dict:
        g = self._get("goals", actor.org_id, goal_id, "Meta")
        if not self._visible_goal(actor, g):
            raise not_found("Meta")  # an invisible goal is indistinguishable from a missing one
        return g

    def list_goals(
        self, actor: Actor, *, scope: Optional[str] = None, subject_id: Optional[str] = None, period_id: Optional[str] = None,
        category: Optional[str] = None, status: Optional[str] = None,
    ) -> list[dict]:
        eq = {k: v for k, v in (("scope", scope), ("subject_id", subject_id), ("period_id", period_id), ("category", category), ("status", status)) if v}
        rows = [g for g in self.store.select("goals", actor.org_id, eq=eq, order=(("created_at", True),)) if self._visible_goal(actor, g)]
        return [self.present_goal(actor.org_id, g) for g in rows]

    def get_goal(self, actor: Actor, goal_id: str) -> dict:
        return self.present_goal(actor.org_id, self._goal(actor, goal_id))

    def update_goal(self, actor: Actor, goal_id: str, patch: Mapping[str, Any]) -> dict:
        g = self._goal(actor, goal_id)
        if not self._can_manage_goal(actor, g["scope"], str(g["subject_id"]) if g.get("subject_id") else None):
            raise forbidden("Sem permissão para alterar esta meta.")
        self._assert_goal_period_open(actor.org_id, g)
        if patch.get("status") is not None and patch["status"] not in USER_SETTABLE_STATUSES:
            raise invalid("status", "Esse status é calculado pelo progresso.", META_INVALIDA)
        body = {k: patch[k] for k in ("title", "notes", "target", "status") if k in patch}
        return self.present_goal(actor.org_id, self.store.update("goals", actor.org_id, goal_id, body) or g)

    def delete_goal(self, actor: Actor, goal_id: str) -> None:
        g = self._goal(actor, goal_id)
        if not self._can_manage_goal(actor, g["scope"], str(g["subject_id"]) if g.get("subject_id") else None):
            raise forbidden("Sem permissão para excluir esta meta.")
        self._assert_goal_period_open(actor.org_id, g)
        self.store.delete("goals", actor.org_id, goal_id)

    def _assert_goal_period_open(self, org_id: str, g: Mapping[str, Any]) -> None:
        if g.get("period_id"):
            period = self.store.get("periods", org_id, str(g["period_id"]))
            if period and period["status"] == "closed":
                raise conflict(PERIODO_FECHADO, "Período fechado: a meta não pode mais ser alterada.")

    def contribute(self, actor: Actor, goal_id: str, amount: float, at: Optional[date] = None, note: Optional[str] = None) -> dict:
        """Add a contribution to a MANUAL goal; `current` and the status follow (`accumulate_contribution`)."""
        g = self._goal(actor, goal_id)
        cat = self.cfg.category(g["category"])
        if cat is not None and cat.source != "manual":
            raise invalid("category", "Meta alimentada por eventos não recebe aportes manuais.", META_INVALIDA)
        if not self._can_manage_goal(actor, g["scope"], str(g["subject_id"]) if g.get("subject_id") else None):
            raise forbidden("Sem permissão para registrar aporte nesta meta.")
        self._assert_goal_period_open(actor.org_id, g)
        transition = accumulate_contribution(float(g["target"]), float(g.get("current") or 0), amount)
        if transition.new_current < 0:
            raise invalid("amount", "O aporte deixaria a meta negativa.", META_INVALIDA)
        self.store.insert("goal_contributions", actor.org_id, [{"goal_id": goal_id, "amount": amount, "at": _iso(at or _today()), "note": note, "created_by": actor.user_id}])
        status = GoalStatus.COMPLETED.value if transition.new_current >= float(g["target"]) else (g["status"] if g["status"] != GoalStatus.PENDING.value else GoalStatus.IN_PROGRESS.value)
        updated = self.store.update("goals", actor.org_id, goal_id, {"current": transition.new_current, "status": status}) or g
        return {**self.present_goal(actor.org_id, updated), "completed_now": transition.completed, "crossed_threshold_pct": transition.crossed_threshold_pct}

    def _realized(self, org_id: str, g: Mapping[str, Any]) -> float:
        cat = self.cfg.category(g["category"])
        start, end = to_date(g.get("starts_on")), to_date(g.get("ends_on"))
        if cat is None or cat.source == "manual" or not (start and end):
            return float(g.get("current") or 0)
        kwargs: dict[str, Any] = {}
        if g["scope"] == "individual":
            kwargs["members"] = [str(g["subject_id"])]
        elif g["scope"] == "team":
            kwargs["team_id"] = str(g["subject_id"])
        rows = self.store.event_totals(org_id, start, end, **kwargs)
        if cat.source == "value":
            return sum(float(r["value"]) for r in rows)
        if cat.source == "points":
            return sum(float(r["points"]) for r in rows)
        etype = cat.source[6:]
        return float(sum(int((r.get("counts") or {}).get(etype, 0)) for r in rows))

    def present_goal(self, org_id: str, g: Mapping[str, Any]) -> dict:
        period = self.store.get("periods", org_id, str(g["period_id"])) if g.get("period_id") else None
        contribs = tuple(
            Contribution(float(c["amount"]), to_date(c["at"]))
            for c in self.store.select("goal_contributions", org_id, eq={"goal_id": g["id"]}, order=(("at", False),))
        )
        realized = self._realized(org_id, g)
        goal = goal_from_row(g, period=period, contributions=contribs)
        remaining_pct = None
        if goal.period.end is not None:
            span = max((goal.period.end - goal.period.start).days, 1)
            remaining_pct = max(0.0, min(100.0, (goal.period.end - _today()).days / span * 100.0))
        progress = compute_progress(Target(float(g["target"])), realized, contributions=contribs, today=_today(), period_remaining_pct=remaining_pct)
        status = g["status"] if g["status"] == GoalStatus.ABANDONED.value else progress.status.value
        return {
            **out(g),
            "realized": realized,
            "progress": {
                "percent_complete": progress.percent_complete,
                "remaining": progress.remaining,
                "projected_completion_date": _iso(progress.projected_completion_date),
                "status": status,
            },
        }

    def summary(self, actor: Actor, period_id: str) -> dict:
        """The cascade for one period: company goals -> team goals -> member goals, each with its realized number."""
        self._get("periods", actor.org_id, period_id, "Período")
        goals = self.list_goals(actor, period_id=period_id)
        teams = {str(t["id"]): t["name"] for t in self.store.select("teams", actor.org_id)}
        return {
            "period_id": period_id,
            "company": [g for g in goals if g["scope"] == "company"],
            "teams": [{**g, "team_name": teams.get(str(g["subject_id"]))} for g in goals if g["scope"] == "team"],
            "members": [g for g in goals if g["scope"] == "individual"],
        }

    # -- scoring / rankings -------------------------------------------------------------------------------------

    @staticmethod
    def _score(points: float, value: float, s: Mapping[str, Any]) -> tuple[float, float]:
        value_points = value / s["value_per_point"] if s["value_per_point"] > 0 else 0.0
        return value_points, points * s["weight_points"] + value_points * s["weight_value"]

    def rankings(
        self, actor: Actor, *, period_id: Optional[str] = None, start: Optional[date] = None, end: Optional[date] = None,
        metric: Optional[str] = None, team_id: Optional[str] = None,
    ) -> dict:
        org_id = actor.org_id
        s = self.get_settings(org_id)
        metric = metric or s["default_ranking_metric"]
        if metric not in METRICS:
            raise invalid("metric", "Métrica de ranking inválida.", FILTRO_INVALIDO)
        period = None
        if period_id:
            period = self._get("periods", org_id, period_id, "Período")
            start, end = to_date(period["starts_on"]), to_date(period["ends_on"])
        if start is None or end is None:
            raise invalid("period_id", "Informe period_id ou from/to.", FILTRO_INVALIDO)
        if end < start:
            raise invalid("to", "A data final vem antes da inicial.", FILTRO_INVALIDO)
        visible = self._visible_members(actor, led_only=False)
        members = sorted(visible) if visible is not None else None
        if period is not None and period["status"] == "closed":  # the snapshot is the truth once closed
            closed = self.store.select("closings", org_id, eq={"period_id": period_id}, in_={"member_id": members} if members is not None else None)
            rows = [
                {"member_id": str(c["member_id"]), "team_id": c.get("team_id"), "points": float(c["activity_points"]), "value": float(c["value_realized"]),
                 "unified": float(c["unified_score"]), "counts": c.get("counts") or {}}
                for c in closed
            ]
            if team_id:
                rows = [r for r in rows if str(r["team_id"]) == str(team_id)]
        else:
            rows = []
            for r in self.store.event_totals(org_id, start, end, members=members, team_id=team_id):
                _vp, unified = self._score(r["points"], r["value"], s)
                rows.append({**r, "unified": unified})
        pick = {"points": "points", "value": "value", "unified": "unified"}[metric]
        by_member = {str(r["member_id"]): r for r in rows}
        entries = [
            {"rank": rank, "member_id": key, "team_id": by_member[key].get("team_id"), "points": by_member[key]["points"], "value": by_member[key]["value"],
             "unified": by_member[key]["unified"], "score": score, "counts": by_member[key]["counts"]}
            for key, score, rank in competition_ranks([(k, float(v[pick])) for k, v in by_member.items()])
        ]
        return {"period_id": period_id, "from": _iso(start), "to": _iso(end), "metric": metric, "closed": bool(period and period["status"] == "closed"), "entries": entries}

    # -- closings -----------------------------------------------------------------------------------------------

    def list_closings(self, actor: Actor, period_id: str) -> list[dict]:
        self._get("periods", actor.org_id, period_id, "Período")
        visible = self._visible_members(actor, led_only=True)
        rows = self.store.select("closings", actor.org_id, eq={"period_id": period_id}, in_={"member_id": sorted(visible)} if visible is not None else None)
        return [out(r) for r in rows]

    def close_period(self, actor: Actor, period_id: str) -> tuple[list[dict], bool]:
        """Snapshot every member's numbers for the period and flip it to `closed`. Returns `(snapshots, reused)`."""
        self._need_admin(actor, "Fechamento de período")
        org_id = actor.org_id
        period = self._get("periods", org_id, period_id, "Período")
        existing = self.store.select("closings", org_id, eq={"period_id": period_id})
        if existing:
            if period["status"] != "closed":  # a crash between the bulk insert and the flip: finish it
                self.store.update("periods", org_id, period_id, {"status": "closed"})
            return [out(r) for r in existing], True
        start, end = to_date(period["starts_on"]), to_date(period["ends_on"])
        s = self.get_settings(org_id)
        value_categories = [c.slug for c in self.cfg.categories if c.source == "value"]
        targets: dict[str, float] = {}
        if value_categories:
            for g in self.store.select("goals", org_id, eq={"period_id": period_id, "scope": "individual"}):
                if g["category"] in value_categories:
                    targets[str(g["subject_id"])] = targets.get(str(g["subject_id"]), 0.0) + float(g["target"])
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for r in self.store.event_totals(org_id, start, end):
            value_points, unified = self._score(r["points"], r["value"], s)
            rows.append({
                "period_id": period_id, "member_id": r["member_id"], "team_id": r.get("team_id"), "value_realized": r["value"],
                "value_target": targets.get(str(r["member_id"]), 0.0), "activity_points": r["points"], "value_points": value_points,
                "unified_score": unified, "counts": r.get("counts") or {}, "snapshot": {"settings": {k: s[k] for k in DEFAULT_SETTINGS}, "from": _iso(start), "to": _iso(end)},
                "closed_at": now, "closed_by": actor.user_id,
            })
        try:
            saved = self.store.insert("closings", org_id, rows) if rows else []
        except StoreConflict:  # a concurrent close won the race: return its snapshots
            return [out(r) for r in self.store.select("closings", org_id, eq={"period_id": period_id})], True
        self.store.update("periods", org_id, period_id, {"status": "closed"})
        return [out(r) for r in saved], False


__all__ = ["Actor", "DEFAULT_SETTINGS", "METRICS", "MetasService", "SCOPES", "competition_ranks", "out"]
