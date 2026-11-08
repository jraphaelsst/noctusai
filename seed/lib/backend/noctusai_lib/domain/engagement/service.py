"""`EngagementService` -- owner-tunable point rules + badges, scoring events into the org ledger, leaderboard, member card.

Wires the pure `rules.evaluate` / `evaluate_badges` / `leaderboard` to the org's rows: rules and badges are DATA in the
database (nothing hardcoded -- `KB § CONTEXT/07-GAMIFICATION.md § 8`), the ledger is append-only and idempotent, totals are a
SQL SUM. A member scores their OWN actions; only an admin records for someone else, edits rules, or erases a member.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Mapping, Optional

from noctusai_lib.domain._organ_common import OrgTableStore, StoreConflict
from noctusai_lib.domain.engagement.errors import EngagementRuleError
from noctusai_lib.domain.engagement.leaderboard import leaderboard
from noctusai_lib.domain.engagement.organ_errors import (
    REGRA_DUPLICADA,
    REGRA_INVALIDA,
    conflict,
    forbidden,
    invalid,
    not_found,
)
from noctusai_lib.domain.engagement.rules import evaluate, evaluate_badges
from noctusai_lib.domain.engagement.value_objects import (
    BadgeRule,
    DuplicateEvent,
    EngagementEvent,
    PointRule,
    RuleSet,
)
from noctusai_lib.domain.metas import Period, PeriodKind


@dataclass(frozen=True)
class Actor:
    org_id: str
    user_id: str
    is_admin: bool = False


def _out(row: Mapping[str, Any]) -> dict:
    return {k: v for k, v in row.items() if k != "org_id"}


def _day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


class EngagementService:
    def __init__(self, store: OrgTableStore, ledger_for: Callable[[str], Any], *, member_scope: Optional[Callable[[Actor], Optional[set[str]]]] = None) -> None:
        self.store = store
        self._ledger_for = ledger_for
        #: product seam: the member ids an actor may see on a leaderboard (None = everybody). Default = the whole org.
        self._member_scope = member_scope

    # -- rules --------------------------------------------------------------------------------------------------

    def list_rules(self, org_id: str) -> list[dict]:
        return [_out(r) for r in self.store.select("point_rules", org_id, order=(("source", False), ("action", False)))]

    def upsert_rule(self, org_id: str, data: Mapping[str, Any]) -> dict:
        try:  # the pure value object is the validator (positive points, caps coherent)
            PointRule(data["source"], data["action"], data["points"], data.get("daily_cap"), data.get("period_cap"))
        except EngagementRuleError as exc:
            raise invalid("points", str(exc), REGRA_INVALIDA) from None
        body = {k: data.get(k) for k in ("source", "action", "points", "daily_cap", "period_cap")}
        existing = self.store.select("point_rules", org_id, eq={"source": data["source"], "action": data["action"]}, limit=1)
        try:
            row = self.store.update("point_rules", org_id, existing[0]["id"], body) if existing else self.store.insert("point_rules", org_id, [body])[0]
        except StoreConflict:
            raise conflict(REGRA_DUPLICADA, "Já existe uma regra para essa ação.") from None
        return _out(row or existing[0])

    def delete_rule(self, org_id: str, rule_id: str) -> None:
        if not self.store.delete("point_rules", org_id, rule_id):
            raise not_found("Regra")

    def list_badges(self, org_id: str) -> list[dict]:
        return [_out(r) for r in self.store.select("badge_rules", org_id, order=(("badge_id", False),))]

    def upsert_badge(self, org_id: str, data: Mapping[str, Any]) -> dict:
        try:
            BadgeRule(data["badge_id"], data["metric"], data["threshold"])
        except EngagementRuleError as exc:
            raise invalid("badge_id", str(exc), REGRA_INVALIDA) from None
        body = {k: data.get(k) for k in ("badge_id", "metric", "threshold", "label", "description")}
        existing = self.store.select("badge_rules", org_id, eq={"badge_id": data["badge_id"]}, limit=1)
        try:
            row = self.store.update("badge_rules", org_id, existing[0]["id"], body) if existing else self.store.insert("badge_rules", org_id, [body])[0]
        except StoreConflict:
            raise conflict(REGRA_DUPLICADA, "Já existe um selo com esse id.") from None
        return _out(row or existing[0])

    def delete_badge(self, org_id: str, badge_row_id: str) -> None:
        if not self.store.delete("badge_rules", org_id, badge_row_id):
            raise not_found("Selo")

    def _rule_set(self, org_id: str) -> RuleSet:
        rows = self.store.select("point_rules", org_id)
        return RuleSet.from_rules([PointRule(r["source"], r["action"], int(r["points"]), r.get("daily_cap"), r.get("period_cap")) for r in rows])

    # -- events -------------------------------------------------------------------------------------------------

    def record(self, actor: Actor, data: Mapping[str, Any]) -> dict:
        """Score one action. A replay (same `idempotency_key`) is `{"duplicate": true}`, never a second award."""
        member = str(data.get("member_id") or actor.user_id)
        if member != actor.user_id and not actor.is_admin:
            raise forbidden("Só um administrador registra ações de outro membro.")
        occurred = data.get("occurred_at") or datetime.now(timezone.utc)
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=timezone.utc)
        event = EngagementEvent(member_id=member, source=data["source"], action=data["action"], occurred_at=occurred, idempotency_key=data["idempotency_key"])
        ledger = self._ledger_for(actor.org_id)
        result = evaluate(event, self._rule_set(actor.org_id), ledger.history(member, source=event.source, action=event.action))
        if isinstance(result, DuplicateEvent):
            return {"duplicate": True, "awards": []}
        recorded = [a for a in result if ledger.record(a)]  # False = lost an idempotency race: not an error, not a second award
        return {"duplicate": not recorded and bool(result), "awards": [_award(a) for a in recorded]}

    # -- reads --------------------------------------------------------------------------------------------------

    def leaderboard(self, actor: Actor, *, kind: str, start: Optional[date], end: Optional[date], limit: int) -> dict:
        today = datetime.now(timezone.utc).date()
        if start is None or end is None:
            start, end = _window(kind, today)
        if end < start:
            raise invalid("to", "A data final vem antes da inicial.", "filtro_invalido")
        scope = self._member_scope(actor) if self._member_scope else None
        ledger = self._ledger_for(actor.org_id)
        totals = ledger.totals(sorted(scope) if scope is not None else None, since=_day_start(start), until=_day_start(end + timedelta(days=1)))
        result = leaderboard(totals, Period(PeriodKind(kind if kind in {k.value for k in PeriodKind} else "open_ended"), start, end))
        return {
            "from": start.isoformat(), "to": end.isoformat(), "kind": kind,
            "entries": [{"member_id": e.member_id, "points": e.points, "rank": e.rank} for e in result.entries[:limit]],
        }

    def member_card(self, actor: Actor, member_id: Optional[str] = None) -> dict:
        member = member_id or actor.user_id
        if member != actor.user_id and not actor.is_admin:
            raise forbidden("Só um administrador vê o cartão de outro membro.")
        ledger = self._ledger_for(actor.org_id)
        history = ledger.history(member)
        total = sum(a.points for a in history)
        metrics: dict[str, int] = {"points": total}
        for a in history:
            key = f"count:{a.source}.{a.action}"
            metrics[key] = metrics.get(key, 0) + 1
        rules = [BadgeRule(b["badge_id"], b["metric"], int(b["threshold"])) for b in self.store.select("badge_rules", actor.org_id)]
        earned = set(evaluate_badges(metrics, rules))
        labels = {b["badge_id"]: b for b in self.list_badges(actor.org_id)}
        return {
            "member_id": member, "points": total, "metrics": metrics,
            "badges": [{**labels[b], "earned": b in earned} for b in labels],
            "recent": [_award(a) for a in sorted(history, key=lambda a: a.occurred_at, reverse=True)[:20]],
        }

    def erase_member(self, actor: Actor, member_id: str) -> int:
        """LGPD delete-by-subject (admin): the only path that removes ledger rows."""
        if not actor.is_admin:
            raise forbidden("Só um administrador apaga os dados de um membro.")
        return int(self._ledger_for(actor.org_id).erase_member(member_id))


def _award(a: Any) -> dict:
    return {"member_id": a.member_id, "source": a.source, "action": a.action, "points": a.points, "occurred_at": a.occurred_at.isoformat(), "idempotency_key": a.idempotency_key}


def _window(kind: str, today: date) -> tuple[date, date]:
    from noctusai_lib.domain.metas import period_bounds

    if kind in ("open_ended", "all"):
        return date(1970, 1, 1), today
    return period_bounds(PeriodKind(kind), today)


__all__ = ["Actor", "EngagementService"]
