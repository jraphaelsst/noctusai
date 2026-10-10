"""`pipeline.aceite.aceitar_proposta` — the callable behind
`POST /api/atendimentos-venda/{id}/aceitar-proposta` (CONTRACT §5.4).

The route is a thin wrapper (its own behaviour is pinned, unchanged, by
`test_pipeline_routers.py::TestAceitarProposta`); these tests drive the callable
directly with an injected client — the way the funnel event does."""
from __future__ import annotations

import pytest

from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.modules.pipeline.aceite import aceitar_proposta
from .conftest import ORG_A as ORG, PROC_STAGE_ID, atendimento, processo


def test_returns_processo_atendimento_and_flag(http_client):
    db = http_client.scoped
    db.set_table_data("atendimentos", [atendimento("neg-1", "proposta")])
    out = aceitar_proposta(db, ORG, "neg-1", None)
    assert set(out) == {"processo", "already_accepted", "atendimento"}
    assert out["already_accepted"] is False
    assert db.table("processos_venda").inserted_payloads[0]["etapa_id"] == PROC_STAGE_ID["contrato"]
    assert out["atendimento"]["id"] == "neg-1"


def test_second_call_is_idempotent(http_client):
    db = http_client.scoped
    db.set_table_data("atendimentos", [atendimento("neg-1", "proposta")])
    db.set_table_data("processos_venda", [processo("proc-1")])
    out = aceitar_proposta(db, ORG, "neg-1", None)
    assert out["already_accepted"] is True
    assert db.table("processos_venda").inserted_payloads == []


def test_raises_the_same_errors_as_the_route(http_client):
    db = http_client.scoped
    db.set_table_data("atendimentos", [atendimento("neg-1", "novo")])
    with pytest.raises(ValidationError_):
        aceitar_proposta(db, ORG, "neg-1", None)
    with pytest.raises(NotFoundError):
        aceitar_proposta(db, ORG, "nope", None)
    assert db.table("processos_venda").inserted_payloads == []
