"""`AssignmentService` -- teams, members, rules, settings, the assign / reassign / release verbs, workload, events.

Every method names the org; the store filters on it (a foreign id is a 404). The decision itself is the pure
`strategy.decide`; the write is the atomic `AssignmentLedger.commit` (capacity re-checked under a lock, so two concurrent
assigns cannot both take a member's last seat -- the loser is retried on a fresh snapshot).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional

from noctusai_lib.domain._organ_common import StoreConflict, not_found

from .config import AssignmentConfig
from .directory import UserDirectory
from .errors import (
    CAPACIDADE_ESGOTADA,
    ESTRATEGIA_INVALIDA,
    EQUIPE_DUPLICADA,
    EQUIPE_INVALIDA,
    FILTRO_INVALIDO,
    MEMBRO_DUPLICADO,
    MEMBRO_INVALIDO,
    ORDEM_INVALIDA,
    REGRA_INVALIDA,
    AssignmentError,
    CapacityFull,
    SubjectNotFound,
    conflict,
    invalid,
)
from .store import (
    T_ASSIGNMENTS,
    T_CURSORS,
    T_EVENTS,
    T_MEMBERS,
    T_RULES,
    T_SETTINGS,
    T_TEAMS,
    AssignmentStore,
)
from .strategy import (
    AssignContext,
    HookPickError,
    MemberState,
    NoPick,
    Pick,
    Rule,
    Settings,
    Snapshot,
    StrategyHook,
    TeamState,
    decide,
    parse_ts,
)
from .types import (
    BUILTIN_STRATEGIES,
    CRITERION_MANUAL,
    EVENT_CLOSED,
    EVENT_NO_CANDIDATE,
    EVENT_UNASSIGNED,
    NO_PICK_MANUAL,
    RULE_KINDS,
    STRATEGY_MANUAL,
    STRATEGY_NAME_RE,
    SUBJECT_KIND_RE,
)

PAGE = 1000
MAX_ASSIGN_ATTEMPTS = 3
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Actor:
    org_id: str
    user_id: str
    is_admin: bool = False


class AssignmentService:
    def __init__(
        self,
        store: AssignmentStore,
        directory: UserDirectory,
        cfg: AssignmentConfig,
        *,
        hooks: Optional[Mapping[str, StrategyHook]] = None,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self._s = store
        self._dir = directory
        self._cfg = cfg
        self._hooks = dict(hooks or {})
        self._clock = clock
        for name in self._hooks:
            if not STRATEGY_NAME_RE.match(name) or name in BUILTIN_STRATEGIES:
                raise ValueError(f"custom strategy name {name!r} must be a lowercase slug that is not a builtin ({BUILTIN_STRATEGIES})")

    # -- reads shared by everything ------------------------------------------------------------------------------

    def _all(self, table: str, org_id: str, **filters: Any) -> list[dict]:
        """EVERY matching row, paged (PostgREST caps an unbounded read at 1 000 rows -- silently)."""
        out: list[dict] = []
        while True:
            page = self._s.tables.select(table, org_id, order=[("id", False)], limit=PAGE, offset=len(out), **filters)
            out += page
            if len(page) < PAGE:
                return out

    def _people(self, org_id: str) -> dict[str, dict]:
        return {m["id"]: m for m in self._dir.members(org_id)}

    def _team(self, org_id: str, team_id: str) -> dict:
        row = self._s.tables.get(T_TEAMS, org_id, str(team_id))
        if row is None:
            raise not_found("Equipe")
        return row

    @staticmethod
    def _uuid(value: Any, field: str) -> str:
        if not _UUID_RE.match(str(value or "")):
            raise invalid(field, "Identificador inválido.", FILTRO_INVALIDO)
        return str(value).lower()

    # -- settings ------------------------------------------------------------------------------------------------

    def strategies(self) -> dict[str, list[str]]:
        return {"builtin": list(BUILTIN_STRATEGIES), "custom": sorted(self._hooks)}

    def get_settings(self, org_id: str) -> dict:
        row = next(iter(self._s.tables.select(T_SETTINGS, org_id, limit=1)), None) or {}
        return {
            "strategy": row.get("strategy", Settings().strategy),
            "default_team_id": row.get("default_team_id"),
            "keep_last": row.get("keep_last", True),
            **self.strategies(),
        }

    def put_settings(self, org_id: str, patch: Mapping[str, Any]) -> dict:
        body: dict[str, Any] = {}
        if patch.get("strategy") is not None:
            name = str(patch["strategy"])
            if name not in BUILTIN_STRATEGIES and name not in self._hooks:
                raise invalid("strategy", f"Estratégia desconhecida: {name}.", ESTRATEGIA_INVALIDA)
            body["strategy"] = name
        if "default_team_id" in patch:
            team = patch["default_team_id"]
            if team is not None:
                self._team(org_id, str(team))
            body["default_team_id"] = str(team) if team is not None else None
        if patch.get("keep_last") is not None:
            body["keep_last"] = bool(patch["keep_last"])
        existing = next(iter(self._s.tables.select(T_SETTINGS, org_id, limit=1)), None)
        if existing:
            self._s.tables.update(T_SETTINGS, org_id, existing["id"], body)
        else:
            self._s.tables.insert(T_SETTINGS, org_id, [body])
        return self.get_settings(org_id)

    # -- teams ---------------------------------------------------------------------------------------------------

    @staticmethod
    def _team_name(name: Optional[str]) -> str:
        clean = (name or "").strip()
        if not 1 <= len(clean) <= 60:
            raise invalid("name", "O nome da equipe deve ter de 1 a 60 caracteres.", EQUIPE_INVALIDA)
        return clean

    def _name_taken(self, org_id: str, name: str, *, except_id: Optional[str] = None) -> bool:
        wanted = name.strip().lower()
        return any(
            str(t["name"]).strip().lower() == wanted and t["id"] != except_id for t in self._all(T_TEAMS, org_id)
        )

    def create_team(self, org_id: str, *, name: str, auto: bool = True, org_unit_id: Optional[str] = None) -> dict:
        clean = self._team_name(name)
        if self._name_taken(org_id, clean):
            raise conflict(EQUIPE_DUPLICADA, "Já existe uma equipe com esse nome.")
        try:
            row = self._s.tables.insert(T_TEAMS, org_id, [{"name": clean, "auto": bool(auto), "org_unit_id": org_unit_id}])[0]
        except StoreConflict:
            raise conflict(EQUIPE_DUPLICADA, "Já existe uma equipe com esse nome.") from None
        return self.get_team(org_id, row["id"])

    def update_team(self, org_id: str, team_id: str, patch: Mapping[str, Any]) -> dict:
        self._team(org_id, team_id)
        body: dict[str, Any] = {}
        if patch.get("name") is not None:
            body["name"] = self._team_name(patch["name"])
            if self._name_taken(org_id, body["name"], except_id=str(team_id)):
                raise conflict(EQUIPE_DUPLICADA, "Já existe uma equipe com esse nome.")
        if patch.get("auto") is not None:
            body["auto"] = bool(patch["auto"])
        if "org_unit_id" in patch:
            body["org_unit_id"] = patch["org_unit_id"]
        if body:
            try:
                self._s.tables.update(T_TEAMS, org_id, str(team_id), body)
            except StoreConflict:
                raise conflict(EQUIPE_DUPLICADA, "Já existe uma equipe com esse nome.") from None
        return self.get_team(org_id, team_id)

    def delete_team(self, org_id: str, team_id: str) -> None:
        self._team(org_id, team_id)
        self._s.tables.delete(T_TEAMS, org_id, str(team_id))  # members / rules / cursor cascade; history keeps the team id

    def _team_out(self, team: dict, members: list[dict], people: dict[str, dict], open_counts: dict[str, int], now: datetime) -> dict:
        out = []
        for m in sorted(members, key=lambda r: (int(r.get("position") or 0), str(r["user_id"]))):
            state = self._member_state(m, open_counts, now)
            out.append({
                "user_id": m["user_id"], "name": (people.get(m["user_id"]) or {}).get("name"),
                "in_org": m["user_id"] in people, "active": bool(m["active"]), "position": int(m.get("position") or 0),
                "capacity": m.get("capacity"), "ooo_from": m.get("ooo_from"), "ooo_until": m.get("ooo_until"),
                "open_count": open_counts.get(m["user_id"], 0),
                "unavailable_reason": state.unavailable_reason(now) if m["user_id"] in people else "left_org",
            })
        return {"id": team["id"], "name": team["name"], "auto": bool(team["auto"]), "org_unit_id": team.get("org_unit_id"), "members": out}

    def _open_counts(self, org_id: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for a in self._all(T_ASSIGNMENTS, org_id, is_null=["closed_at"]):
            counts[a["user_id"]] = counts.get(a["user_id"], 0) + 1
        return counts

    @staticmethod
    def _member_state(row: Mapping[str, Any], open_counts: Mapping[str, int], now: datetime) -> MemberState:
        return MemberState(
            user_id=row["user_id"], team_id=row["team_id"], position=int(row.get("position") or 0), active=bool(row.get("active", True)),
            capacity=row.get("capacity"), open_count=open_counts.get(row["user_id"], 0),
            ooo_from=parse_ts(row.get("ooo_from")), ooo_until=parse_ts(row.get("ooo_until")),
        )

    def list_teams(self, org_id: str) -> list[dict]:
        now, people, counts = self._clock(), self._people(org_id), self._open_counts(org_id)
        members = self._all(T_MEMBERS, org_id)
        teams = sorted(self._all(T_TEAMS, org_id), key=lambda t: (str(t["name"]).lower(), t["id"]))
        return [self._team_out(t, [m for m in members if m["team_id"] == t["id"]], people, counts, now) for t in teams]

    def get_team(self, org_id: str, team_id: str) -> dict:
        team = self._team(org_id, team_id)
        members = self._s.tables.select(T_MEMBERS, org_id, eq={"team_id": team["id"]})
        return self._team_out(team, members, self._people(org_id), self._open_counts(org_id), self._clock())

    # -- members -------------------------------------------------------------------------------------------------

    def _window(self, ooo_from: Any, ooo_until: Any) -> None:
        start, end = parse_ts(ooo_from), parse_ts(ooo_until)
        for label, raw, parsed in (("ooo_from", ooo_from, start), ("ooo_until", ooo_until, end)):
            if raw and parsed is None:
                raise invalid(label, "Data inválida.", MEMBRO_INVALIDO)
        if start and end and end <= start:
            raise invalid("ooo_until", "O fim da ausência deve ser depois do início.", MEMBRO_INVALIDO)

    @staticmethod
    def _capacity(value: Any) -> Optional[int]:
        if value is None:
            return None
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise invalid("capacity", "A capacidade deve ser um número maior que zero (ou vazio, sem limite).", MEMBRO_INVALIDO)
        return value

    def add_member(self, org_id: str, team_id: str, user_id: str, *, active: bool = True, capacity: Optional[int] = None,
                   ooo_from: Any = None, ooo_until: Any = None) -> dict:
        self._team(org_id, team_id)
        uid = self._uuid(user_id, "user_id")
        if uid not in self._people(org_id):
            raise invalid("user_id", "O membro precisa ser um usuário ativo da organização.", MEMBRO_INVALIDO)
        self._window(ooo_from, ooo_until)
        siblings = self._s.tables.select(T_MEMBERS, org_id, eq={"team_id": str(team_id)})
        if any(m["user_id"] == uid for m in siblings):
            raise conflict(MEMBRO_DUPLICADO, "Esse usuário já está na equipe.")
        position = max((int(m.get("position") or 0) for m in siblings), default=-1) + 1
        try:
            self._s.tables.insert(T_MEMBERS, org_id, [{
                "team_id": str(team_id), "user_id": uid, "active": bool(active), "position": position,
                "capacity": self._capacity(capacity), "ooo_from": ooo_from, "ooo_until": ooo_until,
            }])
        except StoreConflict:
            raise conflict(MEMBRO_DUPLICADO, "Esse usuário já está na equipe.") from None
        return self.get_team(org_id, team_id)

    def _seat(self, org_id: str, team_id: str, user_id: str) -> dict:
        self._team(org_id, team_id)
        seat = next(iter(self._s.tables.select(T_MEMBERS, org_id, eq={"team_id": str(team_id), "user_id": str(user_id)})), None)
        if seat is None:
            raise not_found("Membro da equipe")
        return seat

    def update_member(self, org_id: str, team_id: str, user_id: str, patch: Mapping[str, Any]) -> dict:
        seat = self._seat(org_id, team_id, user_id)
        body: dict[str, Any] = {}
        if patch.get("active") is not None:
            body["active"] = bool(patch["active"])
        if "capacity" in patch:
            body["capacity"] = self._capacity(patch["capacity"])
        if "ooo_from" in patch or "ooo_until" in patch:
            start = patch["ooo_from"] if "ooo_from" in patch else seat.get("ooo_from")
            end = patch["ooo_until"] if "ooo_until" in patch else seat.get("ooo_until")
            self._window(start, end)
            body.update({"ooo_from": start, "ooo_until": end})
        if body:
            self._s.tables.update(T_MEMBERS, org_id, seat["id"], body)
        return self.get_team(org_id, team_id)

    def remove_member(self, org_id: str, team_id: str, user_id: str) -> None:
        self._s.tables.delete(T_MEMBERS, org_id, self._seat(org_id, team_id, user_id)["id"])

    def order_members(self, org_id: str, team_id: str, order: list[str]) -> dict:
        """`order` = the member user ids in the wanted rotation order; it must be exactly the team's current members."""
        self._team(org_id, team_id)
        seats = {m["user_id"]: m for m in self._s.tables.select(T_MEMBERS, org_id, eq={"team_id": str(team_id)})}
        wanted = [str(u).lower() for u in order]
        if len(set(wanted)) != len(wanted) or set(wanted) != set(seats):
            raise invalid("order", "A ordem deve listar exatamente os membros da equipe, sem repetir.", ORDEM_INVALIDA)
        for i, uid in enumerate(wanted):
            self._s.tables.update(T_MEMBERS, org_id, seats[uid]["id"], {"position": i})
        return self.get_team(org_id, team_id)

    # -- rules ---------------------------------------------------------------------------------------------------

    def list_rules(self, org_id: str) -> list[dict]:
        return sorted(self._all(T_RULES, org_id), key=lambda r: (r["kind"], r["match_value"]))

    def put_rule(self, org_id: str, *, kind: str, match_value: str, team_id: str) -> dict:
        if kind not in RULE_KINDS:
            raise invalid("kind", f"Tipo de regra inválido (use {', '.join(RULE_KINDS)}).", REGRA_INVALIDA)
        value = (match_value or "").strip()
        if not value:
            raise invalid("match_value", "Informe o valor da regra.", REGRA_INVALIDA)
        self._team(org_id, team_id)
        existing = next(iter(self._s.tables.select(T_RULES, org_id, eq={"kind": kind, "match_value": value})), None)
        if existing:
            return self._s.tables.update(T_RULES, org_id, existing["id"], {"team_id": str(team_id)}) or existing
        return self._s.tables.insert(T_RULES, org_id, [{"kind": kind, "match_value": value, "team_id": str(team_id)}])[0]

    def delete_rule(self, org_id: str, rule_id: str) -> None:
        if not self._s.tables.delete(T_RULES, org_id, str(rule_id)):
            raise not_found("Regra")

    # -- the decision --------------------------------------------------------------------------------------------

    def snapshot(self, org_id: str) -> Snapshot:
        now = self._clock()
        settings_row = self.get_settings(org_id)
        counts = self._open_counts(org_id)
        members = self._all(T_MEMBERS, org_id)
        cursors = {c["team_id"]: c for c in self._all(T_CURSORS, org_id)}
        people = self._people(org_id)
        teams = []
        for t in self._all(T_TEAMS, org_id):
            cur = cursors.get(t["id"]) or {}
            states = tuple(
                self._member_state(m, counts, now) for m in members if m["team_id"] == t["id"] and m["user_id"] in people
            )  # a user who left the org is not a candidate, whatever a stale seat says
            teams.append(TeamState(
                id=t["id"], name=t["name"], auto=bool(t["auto"]), org_unit_id=t.get("org_unit_id"), members=states,
                cursor_user_id=cur.get("last_user_id"), cursor_moved_at=parse_ts(cur.get("moved_at")), created_at=str(t.get("created_at") or ""),
            ))
        rules = tuple(Rule(r["kind"], r["match_value"], r["team_id"]) for r in self._all(T_RULES, org_id))
        return Snapshot(
            settings=Settings(settings_row["strategy"], settings_row["default_team_id"], bool(settings_row["keep_last"])),
            teams=tuple(sorted(teams, key=lambda t: (t.created_at, t.id))), rules=rules, now=now,
        )

    def _subject(self, subject_kind: str, subject_id: str) -> tuple[str, str]:
        if not SUBJECT_KIND_RE.match(subject_kind or ""):
            raise invalid("subject_kind", "Tipo de registro inválido.", FILTRO_INVALIDO)
        return subject_kind, self._uuid(subject_id, "subject_id")

    def _current(self, org_id: str, kind: str, subject: str) -> Optional[dict]:
        return next(iter(self._s.tables.select(T_ASSIGNMENTS, org_id, eq={"subject_kind": kind, "subject_id": subject}, limit=1)), None)

    def get_assignment(self, org_id: str, subject_kind: str, subject_id: str) -> Optional[dict]:
        kind, subject = self._subject(subject_kind, subject_id)
        return self._current(org_id, kind, subject)

    def assign(
        self, org_id: str, *, subject_kind: str, subject_id: str, source: Optional[str] = None, org_unit_id: Optional[str] = None,
        team_id: Optional[str] = None, actor_id: Optional[str] = None, note: Optional[str] = None,
    ) -> dict:
        """Pick an owner with the org's strategy and record it. `{assigned, ...}`: no candidate is an outcome, not an error
        (the subject stays unowned for a human; the `no_candidate` event says why)."""
        kind, subject = self._subject(subject_kind, subject_id)
        for _attempt in range(MAX_ASSIGN_ATTEMPTS):
            snap = self.snapshot(org_id)
            current = self._current(org_id, kind, subject)
            ctx = AssignContext(
                subject_kind=kind, subject_id=subject, source=source, org_unit_id=org_unit_id, team_id=team_id,
                current_user_id=current["user_id"] if current and current.get("closed_at") is None else None,
            )
            try:
                decision = decide(snap, ctx, self._hooks)
            except HookPickError as exc:
                raise AssignmentError(ESTRATEGIA_INVALIDA, str(exc), 500) from exc
            if isinstance(decision, NoPick):
                if decision.reason != NO_PICK_MANUAL:
                    self._s.tables.insert(T_EVENTS, org_id, [{
                        "subject_kind": kind, "subject_id": subject, "event": EVENT_NO_CANDIDATE, "strategy": snap.settings.strategy,
                        "criterion": decision.reason, "team_id": team_id, "org_unit_id": org_unit_id, "actor_id": actor_id, "note": note,
                    }])
                return {"assigned": False, "reason": decision.reason, "strategy": snap.settings.strategy}
            assert isinstance(decision, Pick)
            try:
                res = self._s.ledger.commit(org_id, {
                    "subject_kind": kind, "subject_id": subject, "user_id": decision.user_id, "team_id": decision.team_id,
                    "org_unit_id": org_unit_id, "strategy": snap.settings.strategy, "criterion": decision.criterion,
                    "actor_id": actor_id, "note": note, "advance_cursor": decision.advance_cursor, "enforce_capacity": True,
                })
            except CapacityFull:
                continue  # someone else took the member's last seat between snapshot and commit: decide again on fresh facts
            except SubjectNotFound:
                raise not_found("Registro") from None
            return {"assigned": True, "user_id": decision.user_id, "team_id": decision.team_id, "criterion": decision.criterion,
                    "strategy": snap.settings.strategy, "changed": bool(res.get("changed")), "event": res.get("event")}
        raise conflict(CAPACIDADE_ESGOTADA, "Todos os candidatos atingiram a capacidade enquanto a distribuição rodava; tente de novo.")

    def reassign(self, org_id: str, *, subject_kind: str, subject_id: str, to_user_id: str, actor_id: Optional[str] = None,
                 team_id: Optional[str] = None, note: Optional[str] = None) -> dict:
        """A human gives the subject to a named person (capacity is advisory for a human: `criterion=manual`)."""
        kind, subject = self._subject(subject_kind, subject_id)
        uid = self._uuid(to_user_id, "to_user_id")
        if uid not in self._people(org_id):
            raise invalid("to_user_id", "O destinatário precisa ser um usuário ativo da organização.", MEMBRO_INVALIDO)
        if team_id is not None:
            self._team(org_id, team_id)
        else:
            seat = next(iter(self._s.tables.select(T_MEMBERS, org_id, eq={"user_id": uid}, order=[("position", False)], limit=1)), None)
            team_id = seat["team_id"] if seat else None
        try:
            res = self._s.ledger.commit(org_id, {
                "subject_kind": kind, "subject_id": subject, "user_id": uid, "team_id": team_id, "org_unit_id": None,
                "strategy": STRATEGY_MANUAL, "criterion": CRITERION_MANUAL, "actor_id": actor_id, "note": note,
                "advance_cursor": False, "enforce_capacity": False,
            })
        except SubjectNotFound:
            raise not_found("Registro") from None
        return {"assigned": True, "user_id": uid, "team_id": team_id, "criterion": CRITERION_MANUAL, "strategy": STRATEGY_MANUAL,
                "changed": bool(res.get("changed")), "event": res.get("event")}

    def _release(self, org_id: str, subject_kind: str, subject_id: str, event: str, actor_id: Optional[str], note: Optional[str]) -> dict:
        kind, subject = self._subject(subject_kind, subject_id)
        res = self._s.ledger.release(org_id, {"subject_kind": kind, "subject_id": subject, "event": event, "actor_id": actor_id, "note": note})
        return {"changed": bool(res.get("changed")), "event": res.get("event")}

    def unassign(self, org_id: str, *, subject_kind: str, subject_id: str, actor_id: Optional[str] = None, note: Optional[str] = None) -> dict:
        return self._release(org_id, subject_kind, subject_id, EVENT_UNASSIGNED, actor_id, note)

    def close(self, org_id: str, *, subject_kind: str, subject_id: str, actor_id: Optional[str] = None, note: Optional[str] = None) -> dict:
        """The work on the subject is done (won / lost / archived): the owner stays as history, the member's seat is freed."""
        return self._release(org_id, subject_kind, subject_id, EVENT_CLOSED, actor_id, note)

    # -- reads for the UI / measurement --------------------------------------------------------------------------

    def workload(self, org_id: str) -> list[dict]:
        """Per org member: open subjects, capacity, availability now, the team(s) they sit in."""
        now, counts, people = self._clock(), self._open_counts(org_id), self._people(org_id)
        seats = self._all(T_MEMBERS, org_id)
        out = []
        for uid, person in people.items():
            mine = [self._member_state(s, counts, now) for s in seats if s["user_id"] == uid]
            out.append({
                "user_id": uid, "name": person.get("name"), "open_count": counts.get(uid, 0), "teams": [s["team_id"] for s in seats if s["user_id"] == uid],
                "available": any(m.unavailable_reason(now) is None for m in mine),
                "unavailable_reasons": sorted({r for m in mine if (r := m.unavailable_reason(now))}),
            })
        return sorted(out, key=lambda r: (-r["open_count"], str(r["name"] or ""), r["user_id"]))

    def events(self, org_id: str, *, subject_kind: Optional[str] = None, subject_id: Optional[str] = None, limit: int = 50, offset: int = 0) -> list[dict]:
        eq: dict[str, Any] = {}
        if subject_kind:
            eq["subject_kind"] = subject_kind
        if subject_id:
            eq["subject_id"] = self._uuid(subject_id, "subject_id")
        return self._s.tables.select(T_EVENTS, org_id, eq=eq or None, order=[("created_at", True), ("id", True)], limit=limit, offset=offset)


__all__ = ["Actor", "AssignmentService", "MAX_ASSIGN_ATTEMPTS"]
