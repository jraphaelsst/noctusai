"""Activities vocabulary -- the four activity KINDS, the lifecycle intents, the event names, the outcomes.

The KIND is the behavioural family (a task is done, a call has an outcome, a meeting / visit happens at a time);
the market's `activity_types` are DATA layered on it (rows in `act_types`, each with a `kind`; a market adds types
by shipping preset data, never by a code branch). Event names are business intents in the past tense
(`KB § PATTERNS/architect/event-oriented-architecture.md` §5.2).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

KIND_TASK: Final = "task"
KIND_CALL: Final = "call"
KIND_MEETING: Final = "meeting"
KIND_VISIT: Final = "visit"
ACTIVITY_KINDS: Final[tuple[str, ...]] = (KIND_TASK, KIND_CALL, KIND_MEETING, KIND_VISIT)

#: What a finished activity came to (an enum, never free text, so completion is measurable).
OUTCOME_DONE: Final = "realizada"
OUTCOME_NOT_DONE: Final = "nao_realizada"
OUTCOME_NO_ANSWER: Final = "sem_resposta"
ACTIVITY_OUTCOMES: Final[tuple[str, ...]] = (OUTCOME_DONE, OUTCOME_NOT_DONE, OUTCOME_NO_ANSWER)

#: Lifecycle intents the `act_apply` RPC takes, and the immutable event each one appends.
INTENT_COMPLETE: Final = "concluir"
INTENT_REOPEN: Final = "reabrir"
INTENT_REASSIGN: Final = "reatribuir"
INTENT_RESCHEDULE: Final = "reagendar"
INTENT_EDIT: Final = "editar"
INTENT_CANCEL: Final = "cancelar"
INTENT_EVENT: Final[dict[str, str]] = {
    INTENT_COMPLETE: "atividade_concluida",
    INTENT_REOPEN: "atividade_reaberta",
    INTENT_REASSIGN: "atividade_reatribuida",
    INTENT_RESCHEDULE: "atividade_reagendada",
    INTENT_EDIT: "atividade_editada",
    INTENT_CANCEL: "atividade_cancelada",
}
EVENT_CREATED: Final = "atividade_criada"
ACTIVITY_EVENTS: Final[tuple[str, ...]] = (EVENT_CREATED, *INTENT_EVENT.values())

SLUG_RE: Final = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class ActivityTypeSpec:
    """One market activity type: a stable `slug`, a label the org may edit, and the behavioural `kind`."""

    slug: str
    label: str
    kind: str = KIND_TASK

    def __post_init__(self) -> None:
        if not SLUG_RE.match(self.slug or ""):
            raise ValueError(f"ActivityTypeSpec.slug must be a lowercase identifier, got {self.slug!r}")
        if not (self.label or "").strip():
            raise ValueError(f"ActivityTypeSpec {self.slug!r}: label must not be empty")
        if self.kind not in ACTIVITY_KINDS:
            raise ValueError(f"ActivityTypeSpec {self.slug!r}: kind must be one of {ACTIVITY_KINDS}, got {self.kind!r}")


#: What an org gets when its market declares no `activity_types`: one type per everyday kind.
GENERIC_ACTIVITY_TYPES: Final[tuple[ActivityTypeSpec, ...]] = (
    ActivityTypeSpec("tarefa", "Tarefa", KIND_TASK),
    ActivityTypeSpec("ligacao", "Ligação", KIND_CALL),
    ActivityTypeSpec("reuniao", "Reunião", KIND_MEETING),
)

__all__ = [
    "ACTIVITY_EVENTS",
    "ACTIVITY_KINDS",
    "ACTIVITY_OUTCOMES",
    "ActivityTypeSpec",
    "EVENT_CREATED",
    "GENERIC_ACTIVITY_TYPES",
    "INTENT_CANCEL",
    "INTENT_COMPLETE",
    "INTENT_EDIT",
    "INTENT_EVENT",
    "INTENT_REASSIGN",
    "INTENT_REOPEN",
    "INTENT_RESCHEDULE",
    "KIND_CALL",
    "KIND_MEETING",
    "KIND_TASK",
    "KIND_VISIT",
    "OUTCOME_DONE",
    "OUTCOME_NOT_DONE",
    "OUTCOME_NO_ANSWER",
    "SLUG_RE",
]
