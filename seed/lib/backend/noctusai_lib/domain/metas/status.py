"""Goal status state machine.

Maps the cross-product status vocabulary to/from `GoalStatus`:

| Product   | Their string         | Seed `GoalStatus`              |
|-----------|----------------------|--------------------------------|
| PF        | "ativa"              | IN_PROGRESS                    |
| PF        | "concluida"          | COMPLETED                      |
| PF        | "pausada"            | ABANDONED (or PENDING)         |
| ERP       | "no_prazo"           | ON_TRACK                       |
| ERP       | "atrasada"           | AT_RISK / OVERDUE              |
| Daily L.  | (implicit; computed) | computed from progress + period|

Mapping helpers `from_pt_string` / `to_pt_string` are provided as a
convenience but products that prefer to keep their string vocabulary
can ignore them — the seed never persists status.
"""

from __future__ import annotations

from noctusai_lib.domain.metas.value_objects import GoalStatus

# ── Canonical PT-BR ↔ seed mapping ──────────────────────────────────

_PT_TO_STATUS = {
    "ativa": GoalStatus.IN_PROGRESS,
    "em_andamento": GoalStatus.IN_PROGRESS,
    "no_prazo": GoalStatus.ON_TRACK,
    "atrasada": GoalStatus.AT_RISK,
    "vencida": GoalStatus.OVERDUE,
    "concluida": GoalStatus.COMPLETED,
    "completada": GoalStatus.COMPLETED,
    "pausada": GoalStatus.ABANDONED,
    "abandonada": GoalStatus.ABANDONED,
    "pendente": GoalStatus.PENDING,
}

_STATUS_TO_PT = {
    GoalStatus.PENDING: "pendente",
    GoalStatus.IN_PROGRESS: "ativa",
    GoalStatus.ON_TRACK: "no_prazo",
    GoalStatus.AT_RISK: "atrasada",
    GoalStatus.OVERDUE: "vencida",
    GoalStatus.COMPLETED: "concluida",
    GoalStatus.ABANDONED: "abandonada",
}


def from_pt_string(s: str) -> GoalStatus:
    """Map a PT-BR string to `GoalStatus`. Unknown strings raise.

    Products that already persist `GoalStatus.value` strings (the enum's
    underlying string value) should use `GoalStatus(s)` directly.
    """
    key = s.strip().lower()
    if key in _PT_TO_STATUS:
        return _PT_TO_STATUS[key]
    raise ValueError(f"Unknown PT-BR goal status: {s!r}")


def to_pt_string(status: GoalStatus) -> str:
    """Map `GoalStatus` to the canonical PT-BR string."""
    return _STATUS_TO_PT[status]


# ── Transitions ──────────────────────────────────────────────────────

# Allowed direct transitions. Used by `next_status` for guard rails;
# computed-status from progress always passes through this gate.
_ALLOWED_TRANSITIONS: dict[GoalStatus, set[GoalStatus]] = {
    GoalStatus.PENDING: {
        GoalStatus.IN_PROGRESS,
        GoalStatus.ON_TRACK,
        GoalStatus.AT_RISK,
        GoalStatus.OVERDUE,
        GoalStatus.COMPLETED,
        GoalStatus.ABANDONED,
    },
    GoalStatus.IN_PROGRESS: {
        GoalStatus.ON_TRACK,
        GoalStatus.AT_RISK,
        GoalStatus.OVERDUE,
        GoalStatus.COMPLETED,
        GoalStatus.ABANDONED,
    },
    GoalStatus.ON_TRACK: {
        GoalStatus.IN_PROGRESS,
        GoalStatus.AT_RISK,
        GoalStatus.OVERDUE,
        GoalStatus.COMPLETED,
        GoalStatus.ABANDONED,
    },
    GoalStatus.AT_RISK: {
        GoalStatus.IN_PROGRESS,
        GoalStatus.ON_TRACK,
        GoalStatus.OVERDUE,
        GoalStatus.COMPLETED,
        GoalStatus.ABANDONED,
    },
    GoalStatus.OVERDUE: {
        # Once overdue, the only way out is completion or abandonment —
        # explicit "we missed the window but caught up" requires the
        # caller to bypass this guard.
        GoalStatus.COMPLETED,
        GoalStatus.ABANDONED,
    },
    GoalStatus.COMPLETED: set(),
    GoalStatus.ABANDONED: {GoalStatus.PENDING, GoalStatus.IN_PROGRESS},
}


def can_transition(current: GoalStatus, target: GoalStatus) -> bool:
    """Whether `current → target` is an allowed direct transition.

    `current → current` (self-transition) always returns True.
    """
    if current == target:
        return True
    return target in _ALLOWED_TRANSITIONS.get(current, set())


def next_status(
    current_status: GoalStatus,
    *,
    percent_complete: float,
    period_remaining_pct: float | None = None,
) -> GoalStatus:
    """Compute the next status from current state + progress signals.

    `period_remaining_pct` is the % of the period's time still ahead
    (100 = period just started; 0 = period ended). When None, the
    on-track / at-risk distinction is skipped (matches PF/daily-life
    semantics where status is just completed / in-progress).

    Terminal states (`COMPLETED`, `ABANDONED`) are sticky — they only
    transition out via explicit caller intent (no auto-transition from
    completion data).
    """
    if current_status in (GoalStatus.COMPLETED, GoalStatus.ABANDONED):
        return current_status

    if percent_complete >= 100.0:
        return GoalStatus.COMPLETED

    if percent_complete <= 0.0:
        return GoalStatus.PENDING

    if period_remaining_pct is None:
        return GoalStatus.IN_PROGRESS

    if percent_complete >= (100.0 - period_remaining_pct):
        return GoalStatus.ON_TRACK

    if period_remaining_pct <= 0.0:
        return GoalStatus.OVERDUE

    return GoalStatus.AT_RISK


__all__ = [
    "can_transition",
    "from_pt_string",
    "next_status",
    "to_pt_string",
]
