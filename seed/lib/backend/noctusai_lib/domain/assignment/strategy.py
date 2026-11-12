"""The pure assignment engine: `decide(snapshot, ctx, hooks) -> Pick | NoPick`. No IO, no clock (`now` rides the context).

Mechanics lifted from social-wiring `julia_equipes_service` (keep-last-responsible, a per-team round-robin cursor, fairness
across teams by the team whose cursor moved least recently, inactive members skipped) and erp-imobiliario `distribuicao`
(mode switch, rule maps with a round-robin fallback); capacity and out-of-office are new (a real team needs them).

Strategies (org-wide, `Settings.strategy`):

    round_robin   every `auto` team takes its turn; inside a team the member after the cursor
    by_team       the team named by the caller (`ctx.team_id`) or `Settings.default_team_id`
    by_source     the team the `source` rule names for `ctx.source`, else the default team
    by_unit       the team the `unit` rule names for `ctx.org_unit_id` (else a team stamped with that unit), else the default
    manual        never auto-picks (a human assigns)
    <custom>      a host hook registered by name -- the declared seam for "who owns a lead" rules no market shares

`keep_last` (a setting, on by default) comes first for every non-manual strategy: a returning subject whose current owner is
still an eligible member goes back to the same person.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Mapping, Optional, Sequence, Union

from .types import (
    CRITERION_CUSTOM_PREFIX,
    CRITERION_KEEP_LAST,
    NO_PICK_HOOK_DECLINED,
    NO_PICK_MANUAL,
    NO_PICK_NO_MEMBER,
    NO_PICK_NO_TEAM,
    RULE_SOURCE,
    RULE_UNIT,
    STRATEGY_BY_SOURCE,
    STRATEGY_BY_TEAM,
    STRATEGY_BY_UNIT,
    STRATEGY_MANUAL,
    STRATEGY_ROUND_ROBIN,
    UNAVAILABLE_AT_CAPACITY,
    UNAVAILABLE_INACTIVE,
    UNAVAILABLE_OUT_OF_OFFICE,
)


def parse_ts(value: object) -> Optional[datetime]:
    """An ISO timestamp (or datetime) as an aware datetime; None for empty / unparsable (never raises)."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class MemberState:
    user_id: str
    team_id: str
    position: int = 0
    active: bool = True
    capacity: Optional[int] = None
    open_count: int = 0
    ooo_from: Optional[datetime] = None
    ooo_until: Optional[datetime] = None

    def unavailable_reason(self, now: datetime) -> Optional[str]:
        """None when the member may take a new subject right now, else why not (the UI shows it)."""
        if not self.active:
            return UNAVAILABLE_INACTIVE
        if self.ooo_until is not None and (self.ooo_from is None or self.ooo_from <= now) and now < self.ooo_until:
            return UNAVAILABLE_OUT_OF_OFFICE
        if self.capacity is not None and self.open_count >= self.capacity:
            return UNAVAILABLE_AT_CAPACITY
        return None


@dataclass(frozen=True)
class TeamState:
    id: str
    name: str
    auto: bool = True
    org_unit_id: Optional[str] = None
    members: tuple[MemberState, ...] = ()
    cursor_user_id: Optional[str] = None
    cursor_moved_at: Optional[datetime] = None
    created_at: str = ""


@dataclass(frozen=True)
class Rule:
    kind: str  # `source` | `unit`
    match_value: str
    team_id: str


@dataclass(frozen=True)
class Settings:
    strategy: str = STRATEGY_ROUND_ROBIN
    default_team_id: Optional[str] = None
    keep_last: bool = True


@dataclass(frozen=True)
class Snapshot:
    """Everything a decision reads, loaded once per assign (a hook sees the same facts the builtin strategies do)."""

    settings: Settings
    teams: tuple[TeamState, ...]
    rules: tuple[Rule, ...] = ()
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def team(self, team_id: Optional[str]) -> Optional[TeamState]:
        return next((t for t in self.teams if t.id == team_id), None) if team_id else None


@dataclass(frozen=True)
class AssignContext:
    subject_kind: str
    subject_id: str
    source: Optional[str] = None
    org_unit_id: Optional[str] = None
    team_id: Optional[str] = None
    #: the subject's current owner, when it has one (drives `keep_last`)
    current_user_id: Optional[str] = None


@dataclass(frozen=True)
class Pick:
    user_id: str
    team_id: str
    #: `round_robin` | `by_team` | `by_source` | `by_unit` | `keep_last` | `custom:<name>`
    criterion: str
    #: only a rotation moves the team's cursor (keep-last and a hook's own choice do not)
    advance_cursor: bool = False


@dataclass(frozen=True)
class NoPick:
    reason: str


Decision = Union[Pick, NoPick]
#: A host strategy: `hook(snapshot, ctx) -> Pick | None` (None = decline; the result is NoPick(hook_declined)). A Pick must
#: name an ELIGIBLE member of a team in the snapshot -- the engine rejects anything else (a hook cannot assign to a stranger).
StrategyHook = Callable[[Snapshot, AssignContext], Optional[Pick]]


class HookPickError(ValueError):
    """A custom strategy returned a Pick that is not an eligible member of a snapshot team."""


def _ordered(team: TeamState) -> list[MemberState]:
    return sorted(team.members, key=lambda m: (m.position, m.user_id))


def _next_member(team: TeamState, now: datetime) -> Optional[MemberState]:
    """The first eligible member AFTER the cursor, wrapping (a cursor on someone now unavailable still advances past them)."""
    order = _ordered(team)
    if not order:
        return None
    start = 0
    for i, m in enumerate(order):
        if m.user_id == team.cursor_user_id:
            start = i + 1
            break
    for offset in range(len(order)):
        m = order[(start + offset) % len(order)]
        if m.unavailable_reason(now) is None:
            return m
    return None


def _rotate(teams: Sequence[TeamState], now: datetime, criterion: str) -> Decision:
    """Fairness across teams: the team whose cursor moved least recently goes next; inside it, the next member."""
    live = [(t, _next_member(t, now)) for t in teams]
    candidates = [(t, m) for t, m in live if m is not None]
    if not candidates:
        return NoPick(NO_PICK_NO_MEMBER if teams else NO_PICK_NO_TEAM)
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    team, member = min(candidates, key=lambda tm: (tm[0].cursor_moved_at or epoch, tm[0].created_at, tm[0].id))
    return Pick(user_id=member.user_id, team_id=team.id, criterion=criterion, advance_cursor=True)


def _by_rule(snapshot: Snapshot, kind: str, value: Optional[str]) -> Optional[TeamState]:
    if not value:
        return None
    for rule in snapshot.rules:
        if rule.kind == kind and rule.match_value == value:
            return snapshot.team(rule.team_id)
    return None


def _check_hook_pick(snapshot: Snapshot, pick: Pick, name: str) -> Pick:
    team = snapshot.team(pick.team_id)
    member = next((m for m in team.members if m.user_id == pick.user_id), None) if team else None
    if member is None or member.unavailable_reason(snapshot.now) is not None:
        raise HookPickError(f"strategy {name!r} picked {pick.user_id!r} in team {pick.team_id!r}, who is not an eligible member")
    return Pick(pick.user_id, pick.team_id, f"{CRITERION_CUSTOM_PREFIX}{name}", advance_cursor=False)


def decide(snapshot: Snapshot, ctx: AssignContext, hooks: Optional[Mapping[str, StrategyHook]] = None) -> Decision:
    strategy = snapshot.settings.strategy
    now = snapshot.now
    if strategy == STRATEGY_MANUAL:
        return NoPick(NO_PICK_MANUAL)

    if snapshot.settings.keep_last and ctx.current_user_id:
        for team in snapshot.teams:
            if not team.auto:
                continue
            m = next((x for x in team.members if x.user_id == ctx.current_user_id), None)
            if m is not None and m.unavailable_reason(now) is None:
                return Pick(m.user_id, team.id, CRITERION_KEEP_LAST)

    hook = (hooks or {}).get(strategy)
    if hook is not None:
        picked = hook(snapshot, ctx)
        return _check_hook_pick(snapshot, picked, strategy) if picked is not None else NoPick(NO_PICK_HOOK_DECLINED)

    default = snapshot.team(snapshot.settings.default_team_id)
    if strategy == STRATEGY_ROUND_ROBIN:
        return _rotate([t for t in snapshot.teams if t.auto], now, STRATEGY_ROUND_ROBIN)
    if strategy == STRATEGY_BY_TEAM:
        team = snapshot.team(ctx.team_id) or default
    elif strategy == STRATEGY_BY_SOURCE:
        team = _by_rule(snapshot, RULE_SOURCE, ctx.source) or default
    elif strategy == STRATEGY_BY_UNIT:
        team = (
            _by_rule(snapshot, RULE_UNIT, ctx.org_unit_id)
            or next((t for t in snapshot.teams if ctx.org_unit_id and t.org_unit_id == ctx.org_unit_id), None)
            or default
        )
    else:
        raise ValueError(f"unknown strategy {strategy!r} (no builtin, no registered hook)")
    return _rotate([team] if team else [], now, strategy)


__all__ = [
    "AssignContext", "Decision", "HookPickError", "MemberState", "NoPick", "Pick", "Rule", "Settings", "Snapshot",
    "StrategyHook", "TeamState", "decide", "parse_ts",
]
