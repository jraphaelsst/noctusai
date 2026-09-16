from __future__ import annotations

from datetime import datetime, timezone

import pytest

from noctusai_lib.domain.photo_editing.types import (
    JobType,
    Photo,
    PhotoStatus,
    batch_state_signature,
    can_transition,
    debounce_bucket,
    dedupe_edit,
    dedupe_ingest,
    dedupe_lote_pronto,
    dedupe_propor_regras,
    dedupe_regen_guia,
    dedupe_submit,
    sources_for,
)

P = PhotoStatus


@pytest.mark.parametrize(
    "path",
    [
        [P.RECEBIDA, P.NORMALIZANDO, P.PRONTA, P.EDITANDO, P.EDITADA, P.AVALIANDO,
         P.AGUARDANDO_DECISAO, P.APROVADA, P.REJEITADA, P.APROVADA],
    ],
)
def test_happy_path_is_legal(path) -> None:
    for a, b in zip(path, path[1:]):
        assert can_transition(a, b), (a, b)


@pytest.mark.parametrize(
    "a,b",
    [
        (P.RECEBIDA, P.EDITANDO),
        (P.PRONTA, P.AGUARDANDO_DECISAO),
        (P.AGUARDANDO_DECISAO, P.FALHOU),
        (P.APROVADA, P.FALHOU),
        (P.FALHOU, P.EDITANDO),
        (P.APROVADA, P.AGUARDANDO_DECISAO),
    ],
)
def test_illegal_transitions(a, b) -> None:
    assert not can_transition(a, b)


def test_every_in_flight_state_can_fail_and_failure_resumes() -> None:
    assert sources_for(P.FALHOU) == {
        P.RECEBIDA, P.NORMALIZANDO, P.PRONTA, P.EDITANDO,
        P.EM_LOTE_OPENAI, P.EDITADA, P.AVALIANDO,
    }
    assert can_transition(P.FALHOU, P.PRONTA) and can_transition(P.FALHOU, P.RECEBIDA)


def test_status_literals_match_the_sql_check() -> None:
    assert [s.value for s in PhotoStatus] == [
        "recebida", "normalizando", "pronta", "editando", "em_lote_openai",
        "editada", "avaliando", "aguardando_decisao", "aprovada", "rejeitada", "falhou",
    ]


def test_job_types_exclude_the_c8_batch_poller() -> None:
    assert "fotos.poll_openai_batch" not in JobType.ALL
    assert len(JobType.ALL) == 8


def test_dedupe_keys_are_stable_and_distinct() -> None:
    keys = {
        dedupe_ingest("f1"),
        dedupe_ingest("f1", 1),
        dedupe_submit("l1"),
        dedupe_edit("f1", 0),
        dedupe_edit("f1", 1),
        dedupe_regen_guia(7),
        dedupe_propor_regras("o1", 7),
        dedupe_propor_regras("o2", 7),
    }
    assert len(keys) == 8
    assert dedupe_edit("f1", 0) == "fotos.edit:f1:0"


def _photo(pid: str, status: PhotoStatus, tentativas: int = 0) -> Photo:
    return Photo(id=pid, org_id="o", lote_id="l", ordem=1, storage_path_original="x",
                 status=status, tentativas=tentativas)


def test_batch_signature_changes_with_any_photo_completion() -> None:
    a = [_photo("1", P.AGUARDANDO_DECISAO), _photo("2", P.EDITANDO)]
    b = [_photo("1", P.AGUARDANDO_DECISAO), _photo("2", P.AGUARDANDO_DECISAO)]
    c = [_photo("2", P.AGUARDANDO_DECISAO), _photo("1", P.AGUARDANDO_DECISAO)]
    assert batch_state_signature(a) != batch_state_signature(b)
    assert batch_state_signature(b) == batch_state_signature(c)  # order-free
    retried = [_photo("1", P.AGUARDANDO_DECISAO), _photo("2", P.AGUARDANDO_DECISAO, 1)]
    assert batch_state_signature(b) != batch_state_signature(retried)
    assert dedupe_lote_pronto("l", "abc") == "fotos.lote_pronto:l:abc"


def test_debounce_bucket() -> None:
    t = datetime(2026, 9, 16, 15, 0, tzinfo=timezone.utc)
    assert debounce_bucket(t, 600) == int(t.timestamp()) // 600
    with pytest.raises(ValueError):
        debounce_bucket(t, 0)
