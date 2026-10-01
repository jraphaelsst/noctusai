"""`roteiros_service` + `roteiro_schemas` for CONTRACT §5.1 — data_visita and ordering.

Service-level on the scoped mock (no HTTP app boot); the 401 check mounts the
real card_hub router alone in a bare FastAPI app.
"""
from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.modules.card_hub import roteiros_service as svc
from app.modules.card_hub.roteiro_schemas import (
    MSG_DATA_OBRIGATORIA, RoteiroCreateBodyV2, RoteiroPatchBodyV2,
)
from noctusai_lib.primitives.exceptions import ValidationError_
from noctusai_lib.testing.mocks import MockSupabaseClient
from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.card_hub.test_agendamentos import atendimento_row
from tests.modules.card_hub.test_roteiros import imovel_row, registry_row

ORG = UUID(ORG_ID)


@pytest.fixture
def db():
    mock = MockSupabaseClient()
    cid, aid = str(uuid4()), str(uuid4())
    codigos = ("ONE9001", "ONE9002", "ONE9003")
    mock.set_table_data("clientes", [cliente_row(cid)])
    mock.set_table_data("atendimentos", [atendimento_row(aid, cid)])
    mock.set_table_data("imovel_registry", [registry_row(c) for c in codigos])
    mock.set_table_data("imoveis", [imovel_row(c) for c in codigos])
    mock.set_table_data("imovel_dados", [])
    mock.set_table_data("roteiros", [])
    mock.set_table_data("visitas", [])
    return mock, UUID(cid)


class TestCriar:
    def test_order_and_date_are_persisted(self, db):
        mock, cid = db
        r = svc.criar(mock, ORG, cid, imoveis=["ONE9003", "one9001", "ONE9002"],
                      data_visita=date(2026, 10, 15))
        assert [v["codigo"] for v in r["visitas"]] == ["ONE9003", "ONE9001", "ONE9002"]
        assert [v["ordem"] for v in r["visitas"]] == [0, 1, 2]
        assert r["data_visita"] == "2026-10-15"

    def test_past_date_is_allowed(self, db):
        mock, cid = db
        assert svc.criar(mock, ORG, cid, imoveis=["ONE9001"],
                         data_visita=date(2020, 1, 1))["data_visita"] == "2020-01-01"

    @pytest.mark.parametrize("valor", [None, "", "not-a-date"])
    def test_date_required_typed_error_and_nothing_written(self, db, valor):
        mock, cid = db
        with pytest.raises(ValidationError_) as exc:
            svc.criar(mock, ORG, cid, imoveis=["ONE9001"], data_visita=valor)
        assert MSG_DATA_OBRIGATORIA in str(exc.value)
        assert mock.table("roteiros").select("*").execute().data == []

    def test_omitting_data_visita_is_the_same_typed_error(self, db):
        mock, cid = db
        with pytest.raises(ValidationError_):
            svc.criar(mock, ORG, cid, imoveis=["ONE9001"])


class TestAtualizar:
    def test_patch_date_and_reorder_keep_working(self, db):
        mock, cid = db
        r = svc.criar(mock, ORG, cid, imoveis=["ONE9001", "ONE9002"], data_visita=date(2026, 10, 15))
        rid = UUID(r["id"])
        out = svc.atualizar(mock, ORG, cid, rid, data_visita=date(2026, 11, 1))
        assert out["data_visita"] == "2026-11-01" and out["titulo"] is None
        ids = [UUID(v["id"]) for v in reversed(out["visitas"])]
        re = svc.reordenar(mock, ORG, cid, rid, ids)
        assert [v["codigo"] for v in re["visitas"]] == ["ONE9002", "ONE9001"]

    def test_explicit_null_date_is_refused(self, db):
        mock, cid = db
        r = svc.criar(mock, ORG, cid, imoveis=["ONE9001"], data_visita=date(2026, 10, 15))
        with pytest.raises(ValidationError_):
            svc.atualizar(mock, ORG, cid, UUID(r["id"]), data_visita=None)

    def test_unset_date_is_untouched(self, db):
        mock, cid = db
        r = svc.criar(mock, ORG, cid, imoveis=["ONE9001"], data_visita=date(2026, 10, 15))
        out = svc.atualizar(mock, ORG, cid, UUID(r["id"]), titulo="Manhã")
        assert out["data_visita"] == "2026-10-15" and out["titulo"] == "Manhã"


class TestSchemas:
    def test_create_requires_date_with_the_contract_message(self):
        for body in ({"imoveis": ["A"]}, {"imoveis": ["A"], "data_visita": None}):
            with pytest.raises(ValidationError) as exc:
                RoteiroCreateBodyV2(**body)
            assert MSG_DATA_OBRIGATORIA in str(exc.value)

    def test_create_bounds_and_extra_forbidden(self):
        ok = {"imoveis": ["A"], "data_visita": "2026-10-15"}
        assert RoteiroCreateBodyV2(**ok).data_visita == date(2026, 10, 15)
        with pytest.raises(ValidationError):
            RoteiroCreateBodyV2(imoveis=[], data_visita="2026-10-15")
        with pytest.raises(ValidationError):
            RoteiroCreateBodyV2(imoveis=["A"] * 51, data_visita="2026-10-15")
        with pytest.raises(ValidationError):
            RoteiroCreateBodyV2(**ok, bogus=1)

    def test_patch_null_date_refused_absent_ok(self):
        with pytest.raises(ValidationError) as exc:
            RoteiroPatchBodyV2(data_visita=None)
        assert MSG_DATA_OBRIGATORIA in str(exc.value)
        assert RoteiroPatchBodyV2(titulo="x").model_dump(exclude_unset=True) == {"titulo": "x"}


class TestAuth:
    def test_create_and_pdf_without_token_are_strictly_401(self, anon_client):
        """`anon_client` sends no Authorization header (see conftest) — the only
        fixture that can produce a 401. Strict `==`, never `in (401, 404|422)`."""
        cid, rid = uuid4(), uuid4()
        r = anon_client.post(
            f"/api/clientes/{cid}/roteiros",
            json={"imoveis": ["ONE9001"], "titulo": None},
        )
        assert r.status_code == 401
        assert anon_client.get(f"/api/clientes/{cid}/roteiros/{rid}/pdf").status_code == 401
