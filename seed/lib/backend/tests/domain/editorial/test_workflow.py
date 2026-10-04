"""Exhaustive transition table for ``decide_transition`` — every state × action
× grant × separation-of-duties case, derived from the workflow itself so a new
transition cannot ship untested."""
from __future__ import annotations

from itertools import product
from uuid import uuid4

import pytest

from noctusai_lib.domain.editorial import (
    DEFAULT_WORKFLOW,
    Action,
    Code,
    EditorialWorkflow,
    Grant,
    State,
    decide_transition,
)
from noctusai_lib.domain.editorial.workflow import ACTIONS, DEFAULT_TRANSITIONS

STATES_AND_NONE = [None, *[s.value for s in State]]
ALL_GRANTS = [g.value for g in Grant]
AUTHOR, EDITORIAL, SECURITY, PUBLISHER = (uuid4() for _ in range(4))
_IDS = lambda t: f"{t.action.value}:{t.from_state and t.from_state.value}"  # noqa: E731


def _ok_kwargs(t):
    """Arguments under which transition ``t`` is allowed."""
    approvals = {}
    if t.needs_security_signoff or t.not_editorial_approver:
        approvals[Action.APPROVE_EDITORIAL.value] = EDITORIAL
    if t.needs_security_signoff:
        approvals[Action.APPROVE_SECURITY.value] = SECURITY
    return dict(
        action=t.action, state=t.from_state, actor_id=PUBLISHER, grants=ALL_GRANTS,
        author_id=AUTHOR, approvals=approvals, motivo="because", has_content=True,
    )


def test_every_state_action_pair_not_in_the_table_is_illegal():
    seen = 0
    for action, state in product(ACTIONS, STATES_AND_NONE):
        d = decide_transition(
            action=action, state=state, actor_id=PUBLISHER, grants=ALL_GRANTS, author_id=AUTHOR,
            approvals={}, motivo="m", has_content=True,
        )
        if DEFAULT_WORKFLOW.find(action, state) is None:
            seen += 1
            assert (d.allowed, d.code) == (False, Code.ILLEGAL_TRANSITION), (action, state)
    assert seen == len(ACTIONS) * len(STATES_AND_NONE) - len(DEFAULT_TRANSITIONS)


@pytest.mark.parametrize("t", DEFAULT_TRANSITIONS, ids=_IDS)
def test_each_transition_is_allowed_with_its_grant_and_denied_without(t):
    d = decide_transition(**_ok_kwargs(t))
    assert d.allowed and d.code is Code.OK and d.to_state is t.to_state and d.grant is t.grant
    for missing in ALL_GRANTS:
        kw = _ok_kwargs(t)
        kw["grants"] = [g for g in ALL_GRANTS if g != missing]
        d = decide_transition(**kw)
        if missing == t.grant.value:
            assert (d.allowed, d.code) == (False, Code.MISSING_GRANT)
        else:
            assert d.allowed, (t, missing)  # only the named grant matters
    kw = _ok_kwargs(t)
    kw["grants"] = []
    assert decide_transition(**kw).code is Code.MISSING_GRANT


@pytest.mark.parametrize("t", DEFAULT_TRANSITIONS, ids=_IDS)
def test_each_transition_flag_is_enforced_exactly(t):
    kw = _ok_kwargs(t)
    kw["actor_id"] = None
    assert decide_transition(**kw).code is Code.ACTOR_REQUIRED
    for blank in (None, "", "   "):
        kw = _ok_kwargs(t)
        kw["motivo"] = blank
        assert (decide_transition(**kw).code is Code.MOTIVO_REQUIRED) == t.needs_motivo
    kw = _ok_kwargs(t)
    kw["has_content"] = False
    assert (decide_transition(**kw).code is Code.CONTENT_REQUIRED) == t.creates_version
    kw = _ok_kwargs(t)
    kw["actor_id"] = AUTHOR
    assert (decide_transition(**kw).code is Code.SELF_APPROVAL) == t.not_author
    kw = _ok_kwargs(t)
    kw["actor_id"] = EDITORIAL
    kw["approvals"] = {**kw["approvals"], Action.APPROVE_EDITORIAL.value: EDITORIAL}
    assert (decide_transition(**kw).code is Code.SAME_APPROVER) == t.not_editorial_approver
    kw = _ok_kwargs(t)
    kw["approvals"] = {Action.APPROVE_EDITORIAL.value: EDITORIAL}
    assert (decide_transition(**kw).code is Code.SECURITY_SIGNOFF_MISSING) == t.needs_security_signoff


def test_unknown_action_and_unknown_state():
    assert decide_transition(action="nope", state="rascunho", actor_id=AUTHOR, grants=ALL_GRANTS).code is Code.UNKNOWN_ACTION
    assert decide_transition(action="submit", state="bogus", actor_id=AUTHOR, grants=ALL_GRANTS).code is Code.ILLEGAL_TRANSITION


def test_arquivado_is_terminal():
    for a in ACTIONS:
        assert not decide_transition(
            action=a, state="arquivado", actor_id=PUBLISHER, grants=ALL_GRANTS, author_id=AUTHOR,
            approvals={}, motivo="m",
        ).allowed


def test_security_signoff_cannot_be_given_twice_in_a_round():
    d = decide_transition(
        action="approve_security", state="revisao_seguranca", actor_id=PUBLISHER, grants=ALL_GRANTS,
        author_id=AUTHOR, approvals={"approve_editorial": EDITORIAL, "approve_security": SECURITY},
    )
    assert (d.allowed, d.code) == (False, Code.ILLEGAL_TRANSITION)


def test_grants_may_be_enum_or_string():
    assert decide_transition(action="submit", state="rascunho", actor_id=AUTHOR, grants=[Grant.EDITAR]).allowed
    assert decide_transition(action="submit", state="rascunho", actor_id=AUTHOR, grants=["editorial:editar"]).allowed


def test_a_stricter_workflow_subset_drops_the_action():
    wf = EditorialWorkflow(tuple(t for t in DEFAULT_TRANSITIONS if t.action is not Action.ARCHIVE))
    d = decide_transition(wf, action="archive", state="publicado", actor_id=PUBLISHER, grants=ALL_GRANTS, motivo="m")
    assert d.code is Code.UNKNOWN_ACTION


def test_the_state_machine_is_the_five_fixed_states():
    assert [s.value for s in State] == ["rascunho", "revisao_editorial", "revisao_seguranca", "publicado", "arquivado"]
    assert {g.value for g in Grant} == {
        "editorial:editar", "editorial:revisar", "editorial:revisar_seguranca", "editorial:publicar",
    }
