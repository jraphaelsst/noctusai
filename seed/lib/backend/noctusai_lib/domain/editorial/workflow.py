"""Editorial workflow — the FIXED state machine + the pure ``decide_transition``.

States are code-defined (``rascunho → revisao_editorial → revisao_seguranca →
publicado → arquivado``), never user-editable rows: a workflow whose stages a
tenant can rewrite cannot promise "nobody publishes alone". Every transition
names the grant it needs (``editorial:editar`` / ``revisar`` /
``revisar_seguranca`` / ``publicar``) and the separation-of-duties rules it
carries. ``decide_transition`` is PURE (no IO) so the Fake store, the Supabase
store and the router all ask the same question; the SQL template
(``domain/sql_templates.py::editorial_tables``) is GENERATED from
``DEFAULT_WORKFLOW.transitions`` so the DB re-check cannot drift from this file.

Shape of a review round (per VERSION, never per item):

    create            -> rascunho            (editar)
    edit              rascunho/publicado -> rascunho   (editar; new immutable version)
    submit            rascunho -> revisao_editorial    (editar)
    approve_editorial revisao_editorial -> revisao_seguranca   (revisar; approver != author)
    approve_security  revisao_seguranca (sign-off, state unchanged)
                      (revisar_seguranca; approver != author AND != editorial approver)
    publish           revisao_seguranca -> publicado   (publicar; needs the sign-off; != author)
    send_back         revisao_* -> rascunho            (the stage's grant; ``motivo`` required)
    archive           any non-arquivado -> arquivado   (publicar; ``motivo`` required)

A sign-off belongs to the version AND to the review round: ``approvals`` only
counts what happened after that version's latest ``submit``, so a send-back
and re-submit starts the round over.

KB § PATTERNS/backend/seed-fake-real-adapter.md · projects/seed-editorial-workflow/PROJECT.md §5.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping


class State(str, Enum):
    RASCUNHO = "rascunho"
    REVISAO_EDITORIAL = "revisao_editorial"
    REVISAO_SEGURANCA = "revisao_seguranca"
    PUBLICADO = "publicado"
    ARQUIVADO = "arquivado"


class Grant(str, Enum):
    EDITAR = "editorial:editar"
    REVISAR = "editorial:revisar"
    REVISAR_SEGURANCA = "editorial:revisar_seguranca"
    PUBLICAR = "editorial:publicar"


class Action(str, Enum):
    CREATE = "create"
    EDIT = "edit"
    SUBMIT = "submit"
    APPROVE_EDITORIAL = "approve_editorial"
    APPROVE_SECURITY = "approve_security"
    PUBLISH = "publish"
    SEND_BACK = "send_back"
    ARCHIVE = "archive"


class Code(str, Enum):
    """Machine codes — the SAME strings the DB function raises
    (``editorial_<code>``) so a router can map either source to one error."""

    OK = "ok"
    UNKNOWN_ACTION = "unknown_action"
    ILLEGAL_TRANSITION = "illegal_transition"
    ACTOR_REQUIRED = "actor_required"
    MISSING_GRANT = "missing_grant"
    MOTIVO_REQUIRED = "motivo_required"
    SELF_APPROVAL = "self_approval"
    SAME_APPROVER = "same_approver"
    SECURITY_SIGNOFF_MISSING = "security_signoff_missing"
    CONTENT_REQUIRED = "content_required"


@dataclass(frozen=True)
class Transition:
    action: Action
    from_state: State | None  # None only for CREATE
    to_state: State
    grant: Grant
    needs_motivo: bool = False
    not_author: bool = False  # actor must differ from the version's author
    not_editorial_approver: bool = False  # actor must differ from the round's editorial approver
    needs_security_signoff: bool = False  # an approve_security must exist this round
    creates_version: bool = False  # CREATE / EDIT carry content and mint version n


@dataclass(frozen=True)
class TransitionDecision:
    allowed: bool
    code: Code
    to_state: State | None = None
    grant: Grant | None = None
    transition: Transition | None = None
    detail: str = ""


_A, _S, _G = Action, State, Grant

DEFAULT_TRANSITIONS: tuple[Transition, ...] = (
    Transition(_A.CREATE, None, _S.RASCUNHO, _G.EDITAR, creates_version=True),
    Transition(_A.EDIT, _S.RASCUNHO, _S.RASCUNHO, _G.EDITAR, creates_version=True),
    Transition(_A.EDIT, _S.PUBLICADO, _S.RASCUNHO, _G.EDITAR, creates_version=True),
    Transition(_A.SUBMIT, _S.RASCUNHO, _S.REVISAO_EDITORIAL, _G.EDITAR),
    Transition(_A.APPROVE_EDITORIAL, _S.REVISAO_EDITORIAL, _S.REVISAO_SEGURANCA, _G.REVISAR, not_author=True),
    Transition(
        _A.APPROVE_SECURITY, _S.REVISAO_SEGURANCA, _S.REVISAO_SEGURANCA, _G.REVISAR_SEGURANCA,
        not_author=True, not_editorial_approver=True,
    ),
    Transition(
        _A.PUBLISH, _S.REVISAO_SEGURANCA, _S.PUBLICADO, _G.PUBLICAR,
        not_author=True, needs_security_signoff=True,
    ),
    Transition(_A.SEND_BACK, _S.REVISAO_EDITORIAL, _S.RASCUNHO, _G.REVISAR, needs_motivo=True),
    Transition(_A.SEND_BACK, _S.REVISAO_SEGURANCA, _S.RASCUNHO, _G.REVISAR_SEGURANCA, needs_motivo=True),
    Transition(_A.ARCHIVE, _S.RASCUNHO, _S.ARQUIVADO, _G.PUBLICAR, needs_motivo=True),
    Transition(_A.ARCHIVE, _S.REVISAO_EDITORIAL, _S.ARQUIVADO, _G.PUBLICAR, needs_motivo=True),
    Transition(_A.ARCHIVE, _S.REVISAO_SEGURANCA, _S.ARQUIVADO, _G.PUBLICAR, needs_motivo=True),
    Transition(_A.ARCHIVE, _S.PUBLICADO, _S.ARQUIVADO, _G.PUBLICAR, needs_motivo=True),
)


@dataclass(frozen=True)
class EditorialWorkflow:
    """The (fixed) machine. States and grants are not configurable — see the
    module docstring; ``transitions`` exists so tests (and a future stricter
    consumer) can pass a subset."""

    transitions: tuple[Transition, ...] = DEFAULT_TRANSITIONS

    def rows_for(self, action: str) -> tuple[Transition, ...]:
        return tuple(t for t in self.transitions if t.action.value == action)

    def find(self, action: str, state: str | None) -> Transition | None:
        for t in self.rows_for(action):
            if (t.from_state.value if t.from_state else None) == state:
                return t
        return None


DEFAULT_WORKFLOW = EditorialWorkflow()
STATES: tuple[str, ...] = tuple(s.value for s in State)
ACTIONS: tuple[str, ...] = tuple(a.value for a in Action)
GRANTS: tuple[str, ...] = tuple(g.value for g in Grant)


def _val(x: Any) -> Any:
    return x.value if isinstance(x, Enum) else x


def _deny(code: Code, detail: str, t: Transition | None = None) -> TransitionDecision:
    return TransitionDecision(False, code, None, t.grant if t else None, t, detail)


def decide_transition(
    workflow: EditorialWorkflow = DEFAULT_WORKFLOW,
    *,
    action: Action | str,
    state: State | str | None,
    actor_id: Any,
    grants: Iterable[Grant | str],
    author_id: Any = None,
    approvals: Mapping[str, Any] | None = None,
    motivo: str | None = None,
    has_content: bool = True,
) -> TransitionDecision:
    """Pure allow/deny for ONE attempted transition. Never raises.

    ``author_id`` is the author of the version under review; ``approvals`` maps
    an action name (``approve_editorial`` / ``approve_security``) to the actor
    who performed it THIS review round. Check order (first failure wins; the
    SQL function uses the same order): unknown action → illegal transition →
    actor → grant → motivo → content → self-approval → same approver → missing
    security sign-off.
    """
    act, st = _val(action), _val(state)
    if not workflow.rows_for(act):
        return _deny(Code.UNKNOWN_ACTION, f"unknown action {act!r}")
    t = workflow.find(act, st)
    if t is None:
        return _deny(Code.ILLEGAL_TRANSITION, f"{act!r} is not allowed from state {st!r}")
    approvals = approvals or {}
    if act == Action.APPROVE_SECURITY.value and approvals.get(act) is not None:
        return _deny(Code.ILLEGAL_TRANSITION, "security sign-off already given this round", t)
    if actor_id is None:
        return _deny(Code.ACTOR_REQUIRED, "an actor is required", t)
    if t.grant.value not in {_val(g) for g in grants}:
        return _deny(Code.MISSING_GRANT, f"{act!r} needs {t.grant.value}", t)
    if t.needs_motivo and not (motivo or "").strip():
        return _deny(Code.MOTIVO_REQUIRED, f"{act!r} needs a motivo", t)
    if t.creates_version and not has_content:
        return _deny(Code.CONTENT_REQUIRED, f"{act!r} needs content", t)
    if t.not_author and author_id is not None and actor_id == author_id:
        return _deny(Code.SELF_APPROVAL, "the author of this version cannot approve it", t)
    if t.not_editorial_approver and actor_id == approvals.get(Action.APPROVE_EDITORIAL.value):
        return _deny(Code.SAME_APPROVER, "the editorial approver cannot also give the security sign-off", t)
    if t.needs_security_signoff and approvals.get(Action.APPROVE_SECURITY.value) is None:
        return _deny(Code.SECURITY_SIGNOFF_MISSING, "publish needs this round's security sign-off", t)
    return TransitionDecision(True, Code.OK, t.to_state, t.grant, t, "")


__all__ = [
    "ACTIONS", "Action", "Code", "DEFAULT_TRANSITIONS", "DEFAULT_WORKFLOW", "EditorialWorkflow",
    "GRANTS", "Grant", "STATES", "State", "Transition", "TransitionDecision", "decide_transition",
]
