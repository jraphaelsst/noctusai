"""The approvals contract -- every test runs against the Fake AND the Real ledger (the `service` fixture is parametrized)."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.approvals import ApprovalError, ApprovalsConfig, build_approvals_store

from .conftest import MID, ORG_A, ORG_B, ROT, SCHEMA, U1, U2

K = "roteiro"


def test_nothing_submitted_means_not_approved(service):
    state = service.state(ORG_A, K, ROT)
    assert state.status == "none" and state.versao is None
    assert service.is_approved(ORG_A, K, ROT) is False  # approval is always required: absence is never a pass


def test_submit_then_approve_a_versao(service):
    assert service.submit(ORG_A, K, ROT, 1, actor_id=U1).status == "pending"
    state = service.approve(ORG_A, K, ROT, 1, actor_id=U2)
    assert (state.status, state.versao, state.decided_by) == ("approved", 1, U2)
    assert service.is_approved(ORG_A, K, ROT) is True
    assert service.is_approved(ORG_A, K, ROT, versao=1) is True
    assert service.is_approved(ORG_A, K, ROT, versao=2) is False


def test_any_actor_may_approve_including_the_submitter(service):
    service.submit(ORG_A, K, ROT, 1, actor_id=U1)
    assert service.approve(ORG_A, K, ROT, 1, actor_id=U1).status == "approved"  # owner decision: any org member


def test_reject_requires_a_motivo(service):
    service.submit(ORG_A, K, ROT, 1)
    for bad in (None, "", "   "):
        with pytest.raises(ApprovalError) as err:
            service.reject(ORG_A, K, ROT, 1, actor_id=U2, motivo=bad)
        assert err.value.code == "motivo_obrigatorio"
    assert service.state(ORG_A, K, ROT).status == "pending"  # a refusal leaves nothing behind
    state = service.reject(ORG_A, K, ROT, 1, actor_id=U2, motivo="  gancho fraco  ")
    assert (state.status, state.motivo) == ("rejected", "gancho fraco")
    assert service.is_approved(ORG_A, K, ROT) is False


def test_a_stale_versao_is_refused_for_both_decisions(service):
    service.submit(ORG_A, K, ROT, 1)
    service.submit(ORG_A, K, ROT, 2)  # the subject was edited: v1 is no longer what is on the table
    for call in (
        lambda: service.approve(ORG_A, K, ROT, 1, actor_id=U1),
        lambda: service.reject(ORG_A, K, ROT, 1, actor_id=U1, motivo="x"),
    ):
        with pytest.raises(ApprovalError) as err:
            call()
        assert (err.value.code, err.value.status_code) == ("versao_obsoleta", 409)
    assert service.state(ORG_A, K, ROT).versao == 2 and service.state(ORG_A, K, ROT).status == "pending"


def test_a_future_versao_is_refused_too(service):
    service.submit(ORG_A, K, ROT, 1)
    with pytest.raises(ApprovalError) as err:
        service.approve(ORG_A, K, ROT, 5, actor_id=U1)
    assert err.value.code == "versao_obsoleta"


def test_editing_after_approval_invalidates_it(service):
    service.submit(ORG_A, K, ROT, 1)
    service.approve(ORG_A, K, ROT, 1, actor_id=U1)
    service.submit(ORG_A, K, ROT, 2)
    assert service.is_approved(ORG_A, K, ROT) is False
    assert service.is_approved(ORG_A, K, ROT, versao=1) is False  # only the CURRENT versao can be approved


def test_submit_cannot_go_backwards_and_resubmitting_the_current_versao_is_a_noop(service):
    service.submit(ORG_A, K, ROT, 2)
    service.submit(ORG_A, K, ROT, 2)
    assert [e["event"] for e in service.history(ORG_A, K, ROT)] == ["submitted"]
    with pytest.raises(ApprovalError) as err:
        service.submit(ORG_A, K, ROT, 1)
    assert err.value.code == "versao_obsoleta"


def test_deciding_an_unsubmitted_subject_is_refused(service):
    with pytest.raises(ApprovalError) as err:
        service.approve(ORG_A, K, ROT, 1, actor_id=U1)
    assert err.value.code == "sem_submissao"


def test_a_versao_is_decided_once(service):
    service.submit(ORG_A, K, ROT, 1)
    service.reject(ORG_A, K, ROT, 1, actor_id=U1, motivo="não")
    with pytest.raises(ApprovalError) as err:
        service.approve(ORG_A, K, ROT, 1, actor_id=U2)
    assert (err.value.code, err.value.status_code) == ("ja_decidido", 409)
    assert service.state(ORG_A, K, ROT).status == "rejected"


def test_a_rejected_subject_is_revised_with_a_new_versao_and_can_then_be_approved(service):
    service.submit(ORG_A, K, ROT, 1)
    service.reject(ORG_A, K, ROT, 1, actor_id=U1, motivo="não")
    assert service.submit(ORG_A, K, ROT, 2).status == "pending"
    assert service.approve(ORG_A, K, ROT, 2, actor_id=U2).status == "approved"


def test_decisions_are_append_only_events_with_who_and_when(service):
    service.submit(ORG_A, K, ROT, 1, actor_id=U1)
    service.reject(ORG_A, K, ROT, 1, actor_id=U2, motivo="não")
    service.submit(ORG_A, K, ROT, 2, actor_id=U1)
    service.approve(ORG_A, K, ROT, 2, actor_id=U2)
    history = service.history(ORG_A, K, ROT)
    assert [(e["event"], e["versao"], e["actor_id"]) for e in history] == [
        ("submitted", 1, U1), ("rejected", 1, U2), ("submitted", 2, U1), ("approved", 2, U2),
    ]
    assert history[1]["motivo"] == "não" and all(e["created_at"] for e in history)


def test_subjects_and_orgs_are_isolated(service):
    service.submit(ORG_A, K, ROT, 1)
    service.approve(ORG_A, K, ROT, 1, actor_id=U1)
    assert service.is_approved(ORG_A, K, MID) is False
    assert service.is_approved(ORG_A, "midia", ROT) is False
    assert service.is_approved(ORG_B, K, ROT) is False
    assert service.history(ORG_B, K, ROT) == []


def test_malformed_input_is_refused_before_the_ledger(service):
    for call in (
        lambda: service.submit(ORG_A, "Bad Kind", ROT, 1),
        lambda: service.submit(ORG_A, K, ROT, 0),
        lambda: service.submit(ORG_A, K, "not-a-uuid", 1),
    ):
        with pytest.raises(ApprovalError) as err:
            call()
        assert err.value.status_code == 422


def test_the_fake_is_never_a_silent_default():
    with pytest.raises(RuntimeError):
        build_approvals_store(ApprovalsConfig(schema=SCHEMA))  # no client and not use_fake: loud
