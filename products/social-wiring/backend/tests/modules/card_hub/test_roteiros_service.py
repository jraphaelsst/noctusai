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
from app.modules.card_hub.roteiro_erros import RoteiroErro
from noctusai_lib.testing.mocks import MockSupabaseClient
from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.card_hub import roteiro_rpc
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
    mock.set_table_data("cliente_imovel_interesses", [])
    mock.set_table_data("pipeline_stages", [])
    roteiro_rpc.instalar(mock)
    return mock, UUID(cid)


class TestCriar:
    def test_order_and_date_are_persisted_on_a_draft(self, db):
        mock, cid = db
        r = svc.criar(mock, ORG, cid, imoveis=["ONE9003", "one9001", "ONE9002"],
                      data_visita=date(2026, 10, 15))
        assert [v["codigo"] for v in r["visitas"]] == ["ONE9003", "ONE9001", "ONE9002"]
        assert [v["ordem"] for v in r["visitas"]] == [0, 1, 2]
        assert r["data_visita"] == "2026-10-15"
        assert r["status"] == "rascunho" and r["gerado_em"] is None

    def test_past_date_is_allowed(self, db):
        mock, cid = db
        assert svc.criar(mock, ORG, cid, imoveis=["ONE9001"],
                         data_visita=date(2020, 1, 1))["data_visita"] == "2020-01-01"

    def test_nothing_is_required_to_start_a_draft(self, db):
        """R2: the editor creates the draft on the first meaningful edit — it may be a date alone, or an imóvel alone."""
        mock, cid = db
        so_data = svc.criar(mock, ORG, cid, data_visita=date(2026, 10, 15))
        assert so_data["visitas"] == [] and so_data["data_visita"] == "2026-10-15"
        so_imovel = svc.criar(mock, ORG, cid, imoveis=["ONE9001"])
        assert so_imovel["data_visita"] is None and len(so_imovel["visitas"]) == 1
        vazio = svc.criar(mock, ORG, cid)
        assert vazio["status"] == "rascunho" and vazio["contagem"]["total"] == 0

    def test_garbage_date_is_the_typed_422_and_nothing_is_written(self, db):
        mock, cid = db
        with pytest.raises(RoteiroErro) as exc:
            svc.criar(mock, ORG, cid, imoveis=["ONE9001"], data_visita="not-a-date")
        assert exc.value.code == "roteiro_sem_data" and exc.value.status_code == 422
        assert mock.table("roteiros").select("*").execute().data == []

    def test_creator_is_recorded_and_the_funil_is_not_touched(self, db):
        mock, cid = db
        uid = uuid4()
        r = svc.criar(mock, ORG, cid, imoveis=["ONE9001"], usuario_id=uid)
        assert r["criado_por"] == str(uid)
        assert "funil" not in r


class TestAtualizar:
    def test_patch_date_and_reorder_keep_working_on_a_draft(self, db):
        mock, cid = db
        r = svc.criar(mock, ORG, cid, imoveis=["ONE9001", "ONE9002"], data_visita=date(2026, 10, 15))
        rid = UUID(r["id"])
        out = svc.atualizar(mock, ORG, cid, rid, data_visita=date(2026, 11, 1))
        assert out["data_visita"] == "2026-11-01" and out["titulo"] is None
        ids = [UUID(v["id"]) for v in reversed(out["visitas"])]
        re = svc.reordenar(mock, ORG, cid, rid, ids)
        assert [v["codigo"] for v in re["visitas"]] == ["ONE9002", "ONE9001"]

    def test_explicit_null_date_clears_it_on_a_draft(self, db):
        mock, cid = db
        r = svc.criar(mock, ORG, cid, imoveis=["ONE9001"], data_visita=date(2026, 10, 15))
        assert svc.atualizar(mock, ORG, cid, UUID(r["id"]), data_visita=None)["data_visita"] is None

    def test_explicit_null_date_is_422_on_a_gerado_roteiro(self, db):
        mock, cid = db
        r = svc.criar(mock, ORG, cid, imoveis=["ONE9001"], data_visita=date(2026, 10, 15))
        svc.gerar(mock, ORG, cid, UUID(r["id"]))
        with pytest.raises(RoteiroErro) as exc:
            svc.atualizar(mock, ORG, cid, UUID(r["id"]), data_visita=None)
        assert exc.value.code == "roteiro_sem_data" and exc.value.status_code == 422
        assert MSG_DATA_OBRIGATORIA in exc.value.message

    def test_unset_date_is_untouched(self, db):
        mock, cid = db
        r = svc.criar(mock, ORG, cid, imoveis=["ONE9001"], data_visita=date(2026, 10, 15))
        out = svc.atualizar(mock, ORG, cid, UUID(r["id"]), titulo="Manhã")
        assert out["data_visita"] == "2026-10-15" and out["titulo"] == "Manhã"

    def test_every_autosave_bumps_updated_at(self, db):
        mock, cid = db
        r = svc.criar(mock, ORG, cid, imoveis=["ONE9001"], data_visita=date(2026, 10, 15))
        rid = UUID(r["id"])
        mock.table("roteiros").update({"updated_at": "2000-01-01T00:00:00+00:00"}).eq("id", str(rid)).execute()
        assert svc.atualizar(mock, ORG, cid, rid, titulo="x")["updated_at"] > "2000-01-01"
        mock.table("roteiros").update({"updated_at": "2000-01-01T00:00:00+00:00"}).eq("id", str(rid)).execute()
        assert [v["codigo"] for v in svc.adicionar_visita(mock, ORG, cid, rid, "ONE9002")["visitas"]] == ["ONE9001", "ONE9002"]
        assert svc.obter(mock, ORG, cid, rid)["updated_at"] > "2000-01-01"


class TestSchemas:
    def test_create_has_no_required_field_and_bounds_the_list(self):
        assert RoteiroCreateBodyV2().imoveis == []
        ok = {"imoveis": ["A"], "data_visita": "2026-10-15"}
        assert RoteiroCreateBodyV2(**ok).data_visita == date(2026, 10, 15)
        assert RoteiroCreateBodyV2(imoveis=[]).data_visita is None
        with pytest.raises(ValidationError):
            RoteiroCreateBodyV2(imoveis=["A"] * 51)
        with pytest.raises(ValidationError):
            RoteiroCreateBodyV2(**ok, bogus=1)

    def test_patch_accepts_an_explicit_null_date_the_service_decides(self):
        assert RoteiroPatchBodyV2(data_visita=None).model_dump(exclude_unset=True) == {"data_visita": None}
        assert RoteiroPatchBodyV2(titulo="x").model_dump(exclude_unset=True) == {"titulo": "x"}
        with pytest.raises(ValidationError):
            RoteiroPatchBodyV2(bogus=1)


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
