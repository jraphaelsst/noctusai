"""HTTP surface of the per-party Certidões tab (CONTRACT §1.1-§1.4).

`certidoes_partes_router.router` is mounted here in a LOCAL `FastAPI()` under
`/api/clientes` — `card_hub/router.py` includes it only in the Wave C0
integration patch (CONTRACT §10), so the real app does not serve it yet. The
local app borrows the real app's exception handlers (the error envelope) and
the same patched DB module, and resolves auth through the REAL
`get_current_user_org`: the auth tests are the real dependency's answer, not a
stub's.
"""
from __future__ import annotations

import asyncio
import dataclasses
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from noctusai_lib.integrations.storage import FakeStorageBackend

from app.modules.card_hub import certidoes_partes_router
from app.modules.certidoes.deps import (
    build_default_service,
    get_certidoes_service,
    get_storage_backend,
)
from app.modules.certidoes.registry import CERTIDOES_CONFIG
from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.card_hub.test_certidoes_matriz import (
    _atendimento,
    _consulta,
    _parte,
    _resultado,
    _seed_tables,
)

CPF = "41295423898"
AUTH = {"Authorization": "Bearer test-token"}
BASE = "/api/clientes"


@pytest.fixture
def processar():
    return AsyncMock()


@pytest.fixture
def credenciais():
    """Mutable holder: tests set `.faltando` to simulate a missing token."""
    class _C:
        faltando: list[str] = []

        def __call__(self, _org):
            return list(self.faltando)

    return _C()


@pytest.fixture
def api(client, scoped, processar, credenciais):
    from app.main import app as base_app

    local = FastAPI()
    local.exception_handlers.update(base_app.exception_handlers)
    local.include_router(certidoes_partes_router.router, prefix=BASE)
    fake = dataclasses.replace(
        build_default_service(),
        check_required_credentials=credenciais,
        processar_consulta=processar,
    )
    local.dependency_overrides[get_certidoes_service] = lambda: fake
    local.dependency_overrides[get_storage_backend] = lambda: FakeStorageBackend()
    return TestClient(local)


def _card(scoped):
    cid, aid, vid = str(uuid4()), str(uuid4()), str(uuid4())
    _seed_tables(scoped)
    scoped.set_table_data("clientes", [
        cliente_row(cid, nome="Titular", cpf=CPF),
        cliente_row(vid, nome="Vendedor", cpf="52998224725"),
    ])
    scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
    scoped.set_table_data("atendimento_partes", [_parte(aid, vid)])
    return cid, aid, vid


class TestAuth:
    """Strict `== 401` — never `in (401, 404, 422)`: a non-401 branch would
    be a false green (route absent, or validation before auth)."""

    def test_get_sem_token_401(self, api):
        assert api.get(f"{BASE}/{uuid4()}/certidoes/partes").status_code == 401

    def test_emissao_sem_token_401(self, api):
        resp = api.post(f"{BASE}/{uuid4()}/certidoes/partes/pessoa/{uuid4()}/emissao", json={})
        assert resp.status_code == 401

    def test_reemitir_sem_token_401(self, api):
        resp = api.post(f"{BASE}/{uuid4()}/certidoes/resultados/{uuid4()}/reemitir", json={})
        assert resp.status_code == 401

    def test_ciencia_pcen_sem_token_401(self, api):
        resp = api.post(
            f"{BASE}/{uuid4()}/certidoes/resultados/{uuid4()}/ciencia-pcen", json={"acao": "entendi"},
        )
        assert resp.status_code == 401

    def test_reler_sem_token_401(self, api):
        assert api.post(f"{BASE}/{uuid4()}/certidoes/reler", json={}).status_code == 401

    def test_celulas_sem_token_401(self, api):
        body = {"kind": "pessoa", "alvo_id": str(uuid4()), "linha_chave": "serasa"}
        assert api.post(f"{BASE}/{uuid4()}/certidoes/celulas", json=body).status_code == 401


class TestGetPartes:
    def test_200_raw_dict_sem_envelope_e_campos_do_contrato(self, api, scoped):
        cid, aid, vid = _card(scoped)
        resp = api.get(f"{BASE}/{cid}/certidoes/partes", headers=AUTH)
        assert resp.status_code == 200
        body = resp.json()
        assert "data" not in body
        assert set(body) == {"atendimento_id", "data_referencia", "max_dias", "linhas", "partes"}
        assert body["atendimento_id"] == aid
        assert [p["rotulo"] for p in body["partes"]] == ["COMP 1", "VEND 1"]
        assert all("automatico" in l for l in body["linhas"])
        celula = body["partes"][0]["celulas"]["cnd_federal"]
        assert celula["status"] == "pendente" and celula["stale_para_contrato"] is False

    def test_atendimento_id_explicito(self, api, scoped):
        cid, aid, vid = _card(scoped)
        resp = api.get(f"{BASE}/{cid}/certidoes/partes", params={"atendimento_id": aid}, headers=AUTH)
        assert resp.status_code == 200 and resp.json()["atendimento_id"] == aid

    def test_cliente_desconhecido_404(self, api, scoped):
        _seed_tables(scoped)
        resp = api.get(f"{BASE}/{uuid4()}/certidoes/partes", headers=AUTH)
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    def test_ambiguo_e_200_vazio_nunca_409(self, api, scoped):
        cid = str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Solo")])
        resp = api.get(f"{BASE}/{cid}/certidoes/partes", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["atendimento_id"] is None and resp.json()["partes"] == []

    def test_celula_segue_a_pessoa(self, api, scoped):
        cid, aid, vid = _card(scoped)
        scoped.set_table_data("certidao_consultas", [_consulta("c1", cliente_id=vid)])
        scoped.set_table_data("certidao_resultados", [
            _resultado("r1", "c1", "cnd_federal", status="sucesso", resultado="negativa",
                       emitida_em="2020-01-01"),
        ])
        body = api.get(f"{BASE}/{cid}/certidoes/partes", headers=AUTH).json()
        vend = body["partes"][1]
        assert vend["celulas"]["cnd_federal"]["stale_para_contrato"] is True
        assert vend["totais"]["vencidas"] == 1


class TestEmissao:
    def test_201_cria_consulta_e_agenda_o_processamento(self, api, scoped, processar):
        cid, aid, vid = _card(scoped)
        resp = api.post(
            f"{BASE}/{cid}/certidoes/partes/pessoa/{vid}/emissao", json={}, headers=AUTH,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert set(body) == {"consulta_id", "resultados"}
        assert len(body["resultados"]) == len(CERTIDOES_CONFIG) - 1  # no tjsp
        assert set(body["resultados"][0]) == {"resultado_id", "tipo", "status_processamento"}
        processar.assert_awaited_once()
        assert processar.await_args.args[0] == body["consulta_id"]

    def test_tipos_selecionados(self, api, scoped, processar):
        cid, aid, vid = _card(scoped)
        resp = api.post(
            f"{BASE}/{cid}/certidoes/partes/pessoa/{vid}/emissao",
            json={"tipos": ["cnd_federal", "trf3"]}, headers=AUTH,
        )
        assert resp.status_code == 201
        assert sorted(r["tipo"] for r in resp.json()["resultados"]) == ["cnd_federal", "trf3"]

    def test_corpo_com_campo_desconhecido_422(self, api, scoped, processar):
        cid, aid, vid = _card(scoped)
        resp = api.post(
            f"{BASE}/{cid}/certidoes/partes/pessoa/{vid}/emissao",
            json={"tipo": ["cnd_federal"]}, headers=AUTH,
        )
        assert resp.status_code == 422
        processar.assert_not_awaited()

    def test_tipo_nao_automatico_422_com_codigo(self, api, scoped, processar):
        cid, aid, vid = _card(scoped)
        resp = api.post(
            f"{BASE}/{cid}/certidoes/partes/pessoa/{vid}/emissao",
            json={"tipos": ["serasa"]}, headers=AUTH,
        )
        assert resp.status_code == 422
        err = resp.json()["error"]
        assert err["code"] == "TIPO_NAO_AUTOMATICO"
        assert err["message"] == "Serasa é registrada manualmente — envie o PDF na célula."
        processar.assert_not_awaited()

    def test_credencial_ausente_422_sem_escrita_nem_agendamento(
        self, api, scoped, processar, credenciais
    ):
        credenciais.faltando = ["Token InfoSimples não configurado."]
        cid, aid, vid = _card(scoped)
        resp = api.post(
            f"{BASE}/{cid}/certidoes/partes/pessoa/{vid}/emissao", json={}, headers=AUTH,
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["message"].endswith(
            "Configure em Configurações → Chaves de API."
        )
        assert scoped.table("certidao_consultas").inserted_payloads == []
        processar.assert_not_awaited()

    def test_kind_invalido_404(self, api, scoped):
        cid, aid, vid = _card(scoped)
        resp = api.post(
            f"{BASE}/{cid}/certidoes/partes/pessoas/{vid}/emissao", json={}, headers=AUTH,
        )
        assert resp.status_code == 404

    def test_parte_estranha_404(self, api, scoped):
        cid, aid, vid = _card(scoped)
        resp = api.post(
            f"{BASE}/{cid}/certidoes/partes/pessoa/{uuid4()}/emissao", json={}, headers=AUTH,
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["message"] == "Parte não encontrada neste atendimento."

    def test_documento_ausente_422(self, api, scoped):
        cid, aid, vid = _card(scoped)
        scoped.set_table_data("clientes", [
            cliente_row(cid, nome="Titular", cpf=CPF), cliente_row(vid, nome="V", cpf=None),
        ])
        resp = api.post(
            f"{BASE}/{cid}/certidoes/partes/pessoa/{vid}/emissao", json={}, headers=AUTH,
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "DOCUMENTO_AUSENTE"

    def test_atendimento_ambiguo_409(self, api, scoped):
        cid = str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Solo", cpf=CPF)])
        resp = api.post(
            f"{BASE}/{cid}/certidoes/partes/pessoa/{cid}/emissao", json={}, headers=AUTH,
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "AMBIGUOUS_ATENDIMENTO"


class TestReemitir:
    def test_201_uma_nova_consulta_um_resultado(self, api, scoped, processar):
        cid, aid, vid = _card(scoped)
        scoped.set_table_data("certidao_consultas", [_consulta("c0", cliente_id=vid)])
        scoped.set_table_data("certidao_resultados", [
            _resultado(str(uuid4()), "c0", "cnd_federal", status="sucesso", emitida_em="2026-06-23"),
        ])
        rid = scoped.table("certidao_resultados").select("id").execute().data[0]["id"]
        resp = api.post(
            f"{BASE}/{cid}/certidoes/resultados/{rid}/reemitir", json={}, headers=AUTH,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert set(body) == {"consulta_id", "resultados"} and len(body["resultados"]) == 1
        assert body["resultados"][0]["tipo"] == "cnd_federal"
        processar.assert_awaited_once()

    def test_resultado_inexistente_404(self, api, scoped):
        cid, aid, vid = _card(scoped)
        resp = api.post(
            f"{BASE}/{cid}/certidoes/resultados/{uuid4()}/reemitir", json={}, headers=AUTH,
        )
        assert resp.status_code == 404

    def test_corpo_nao_vazio_422(self, api, scoped):
        cid, aid, vid = _card(scoped)
        resp = api.post(
            f"{BASE}/{cid}/certidoes/resultados/{uuid4()}/reemitir",
            json={"x": 1}, headers=AUTH,
        )
        assert resp.status_code == 422


class TestCelulas:
    def _body(self, vid, chave="serasa", **over):
        return {"kind": "pessoa", "alvo_id": vid, "linha_chave": chave, **over}

    def test_201_quando_cria_e_200_quando_ja_existe(self, api, scoped):
        cid, aid, vid = _card(scoped)
        criou = api.post(f"{BASE}/{cid}/certidoes/celulas", json=self._body(vid), headers=AUTH)
        assert criou.status_code == 201
        assert set(criou.json()) == {"resultado_id", "consulta_id", "criado"}
        assert criou.json()["criado"] is True
        # The placeholder is now the party's winning serasa cell.
        existe = api.post(f"{BASE}/{cid}/certidoes/celulas", json=self._body(vid), headers=AUTH)
        assert existe.status_code == 200
        assert existe.json()["criado"] is False
        assert existe.json()["resultado_id"] == criou.json()["resultado_id"]

    def test_placeholder_le_origem_manual_no_get(self, api, scoped):
        cid, aid, vid = _card(scoped)
        api.post(f"{BASE}/{cid}/certidoes/celulas", json=self._body(vid), headers=AUTH)
        body = api.get(f"{BASE}/{cid}/certidoes/partes", headers=AUTH).json()
        celula = body["partes"][1]["celulas"]["serasa"]
        assert (celula["origem"], celula["status_processamento"]) == ("manual", "pendente")

    def test_nao_aplicavel_422(self, api, scoped):
        cid, aid, vid = _card(scoped)
        resp = api.post(
            f"{BASE}/{cid}/certidoes/celulas",
            json=self._body(vid, "fgts_regularidade"), headers=AUTH,
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "CELULA_NAO_APLICAVEL"

    def test_kind_fora_do_enum_422(self, api, scoped):
        cid, aid, vid = _card(scoped)
        resp = api.post(
            f"{BASE}/{cid}/certidoes/celulas", json=self._body(vid, kind="pj"), headers=AUTH,
        )
        assert resp.status_code == 422


class TestCienciaPcen:
    """Receita PCEN 2ª via acknowledgment (owner amendment 2026-10-01)."""

    VALIDADE = "2099-12-31"
    RID = str(uuid4())

    def _pcen(self, scoped, vid, **over):
        base = dict(
            status="sucesso", resultado="positiva_com_efeito_de_negativa",
            emitida_em="2026-08-01", validade_ate=self.VALIDADE, numero="X1",
            api_response={"noctus_segunda_via": {"preferencia_emissao": "2via"}},
        )
        base.update(over)
        scoped.set_table_data("certidao_consultas", [_consulta("c1", cliente_id=vid)])
        scoped.set_table_data("certidao_resultados", [_resultado(self.RID, "c1", "cnd_federal", **base)])

    def _post(self, api, cid, acao="entendi", rid=None):
        rid = rid or self.RID
        return api.post(
            f"{BASE}/{cid}/certidoes/resultados/{rid}/ciencia-pcen",
            json={"acao": acao}, headers=AUTH,
        )

    def test_entendi_grava_quem_quando_e_a_validade(self, api, scoped):
        cid, aid, vid = _card(scoped)
        self._pcen(scoped, vid)
        resp = self._post(api, cid)
        assert resp.status_code == 200, resp.text
        assert resp.json()["pcen"]["ciente"] is True
        (row,) = scoped.table("certidao_resultados").updated_payloads
        assert row["pcen_ciente_em"] and row["pcen_ciente_por"]
        assert row["pcen_ciente_validade"] == self.VALIDADE

    def test_duvida_registra_e_nao_da_ciencia_e_aponta_o_contato_configurado(self, api, scoped):
        cid, aid, vid = _card(scoped)
        self._pcen(scoped, vid)
        scoped.set_table_data("org_dados_cadastrais", [{
            "org_id": ORG_ID, "suporte_nome": "Suporte Noctus",
            "suporte_whatsapp": "+5511999990000", "suporte_email": "suporte@x.z",
        }])
        body = self._post(api, cid, "duvida").json()
        assert body["pcen"]["ciente"] is False and body["pcen"]["duvida_em"]
        assert body["suporte"] == {
            "nome": "Suporte Noctus", "whatsapp": "+5511999990000", "email": "suporte@x.z",
        }
        (row,) = scoped.table("certidao_resultados").updated_payloads
        assert "pcen_ciente_em" not in row and row["pcen_duvida_em"]

    def test_sem_contato_configurado_suporte_e_nulo_nao_inventado(self, api, scoped):
        cid, aid, vid = _card(scoped)
        self._pcen(scoped, vid)
        scoped.set_table_data("org_dados_cadastrais", [])
        assert self._post(api, cid, "duvida").json()["suporte"] is None

    def test_suporte_nunca_cai_nos_destinatarios_de_notificacao(self, api, scoped):
        """Owner decision 2026-10-02: support is SEPARATE from the notification
        number — an org with recipients but no support contact gets `None`."""
        cid, aid, vid = _card(scoped)
        self._pcen(scoped, vid)
        scoped.set_table_data("org_dados_cadastrais", [{"org_id": ORG_ID, "suporte_nome": "Só nome"}])
        scoped.set_table_data("notification_recipients", [{
            "id": "n1", "org_id": ORG_ID, "name": "Escritório", "email": "x@y.z",
            "whatsapp_number": "+5511999990000", "is_active": True, "created_at": "2026-01-01T00:00:00+00:00",
        }])
        assert self._post(api, cid, "duvida").json()["suporte"] is None

    def test_outra_certidao_409_nada_e_gravado(self, api, scoped):
        cid, aid, vid = _card(scoped)
        self._pcen(scoped, vid, api_response=None)  # not a 2ª via
        resp = self._post(api, cid)
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CIENCIA_PCEN_NAO_APLICAVEL"
        assert scoped.table("certidao_resultados").updated_payloads == []

    def test_validade_vencida_409(self, api, scoped):
        cid, aid, vid = _card(scoped)
        self._pcen(scoped, vid, validade_ate="2020-01-01")
        assert self._post(api, cid).status_code == 409

    def test_resultado_de_outro_card_404(self, api, scoped):
        cid, aid, vid = _card(scoped)
        scoped.set_table_data("certidao_consultas", [_consulta("c1", cliente_id=str(uuid4()))])
        scoped.set_table_data("certidao_resultados", [_resultado(self.RID, "c1", "cnd_federal", status="sucesso")])
        assert self._post(api, cid).status_code == 404

    def test_corpo_invalido_422(self, api, scoped):
        cid, aid, vid = _card(scoped)
        self._pcen(scoped, vid)
        resp = api.post(
            f"{BASE}/{cid}/certidoes/resultados/{self.RID}/ciencia-pcen", json={"acao": "x"}, headers=AUTH,
        )
        assert resp.status_code == 422


class TestRelerCard:
    """`POST …/certidoes/reler` — every stored certidão PDF of the card's
    parties (titular + vendedor here; upload or live receipt), re-read on the
    bytes already stored; a fileless row is `sem_arquivo`, never touched."""

    @pytest.fixture
    def reler(self, client, scoped):
        from app.main import app as base_app
        from app.modules.certidoes import service as certidoes_service

        storage = FakeStorageBackend()
        extrair = AsyncMock()
        local = FastAPI()
        local.exception_handlers.update(base_app.exception_handlers)
        local.include_router(certidoes_partes_router.router, prefix=BASE)
        fake = dataclasses.replace(build_default_service(), executar_releitura=extrair)
        local.dependency_overrides[get_certidoes_service] = lambda: fake
        local.dependency_overrides[get_storage_backend] = lambda: storage

        def _blob(key):
            asyncio.run(storage.put(bucket=certidoes_service.BUCKET, key=key, data=b"%PDF-" + key.encode()))

        return TestClient(local), extrair, _blob

    def test_conta_e_agenda_todo_pdf_armazenado(self, reler, scoped):
        api, extrair, blob = reler
        cid, aid, vid = _card(scoped)
        k_tit, k_vend, k_sumiu = (f"{ORG_ID}/certidoes/c{i}/x.pdf" for i in range(3))
        blob(k_tit)
        blob(k_vend)
        scoped.set_table_data("certidao_consultas", [
            _consulta("c1", cliente_id=cid), _consulta("c2", cliente_id=vid),
        ])
        scoped.set_table_data("certidao_resultados", [
            _resultado("manual-tit", "c1", "cenprot", status="sucesso", arquivo_url=k_tit,
                       api_response=None, confirmado_por="user-1", resultado_origem="ia"),
            _resultado("manual-vend", "c2", "serasa", status="sucesso", arquivo_url=k_vend,
                       api_response=None),
            _resultado("ao-vivo", "c2", "cnd_federal", status="sucesso", arquivo_url=k_vend,
                       api_response={"code": 200}),
            _resultado("vazio", "c2", "trf3", status="pendente", arquivo_url=None, api_response=None),
            _resultado("lendo", "c1", "serasa", status="processando", arquivo_url=k_tit,
                       api_response=None),
            _resultado("sumiu", "c1", "tjsp_esaj", status="sucesso", arquivo_url=k_sumiu,
                       api_response=None),
        ])

        resp = api.post(f"{BASE}/{cid}/certidoes/reler", json={"atendimento_id": aid}, headers=AUTH)

        assert resp.status_code == 200
        assert resp.json() == {"relidos": 3, "sem_arquivo": 1, "em_andamento": 1, "erros": 1}
        agendados = {c.kwargs["resultado_id"]: c.kwargs for c in extrair.await_args_list}
        assert set(agendados) == {"manual-tit", "manual-vend", "ao-vivo"}
        assert agendados["manual-tit"]["pdf_bytes"] == b"%PDF-" + k_tit.encode()
        # D1: the confirmed row's lock rides along — the extraction keeps it.
        assert agendados["manual-tit"]["confirmado_por_atual"] == "user-1"
        assert agendados["ao-vivo"]["manual"] is False
        status = {r["id"]: r["status"] for r in scoped.table("certidao_resultados").select("*").execute().data}
        assert status["manual-tit"] == status["manual-vend"] == "processando"
        # A live emission's re-read never flips its status (the stale sweep).
        assert status["ao-vivo"] == "sucesso" and status["sumiu"] == "sucesso"
        acessos = scoped.table("certidao_resultado_acessos").select("*").execute().data
        assert sorted(a["documento_id"] for a in acessos) == ["ao-vivo", "manual-tit", "manual-vend"]
        assert all(a["acao"] == "releitura" and a["usuario_id"] for a in acessos)

    def test_sem_certidoes_tudo_zero(self, reler, scoped):
        api, extrair, _ = reler
        cid, aid, vid = _card(scoped)
        resp = api.post(f"{BASE}/{cid}/certidoes/reler", json={}, headers=AUTH)
        assert resp.status_code == 200
        assert resp.json() == {"relidos": 0, "sem_arquivo": 0, "em_andamento": 0, "erros": 0}
        extrair.assert_not_awaited()

    def test_cliente_de_outra_org_404(self, reler, scoped):
        api, _, _ = reler
        _seed_tables(scoped)
        assert api.post(f"{BASE}/{uuid4()}/certidoes/reler", json={}, headers=AUTH).status_code == 404

    def test_corpo_com_campo_desconhecido_422(self, reler, scoped):
        api, _, _ = reler
        cid, aid, vid = _card(scoped)
        resp = api.post(f"{BASE}/{cid}/certidoes/reler", json={"x": 1}, headers=AUTH)
        assert resp.status_code == 422
