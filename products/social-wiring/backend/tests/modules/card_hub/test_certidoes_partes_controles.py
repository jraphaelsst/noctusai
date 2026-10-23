"""The card's Certidões tab owns every emission control (the standalone
/certidoes screen is retired): cancel an emission in progress, retry only the
failed cells in place, discard a wrong emission, skip what is already valid on
"emitir todas", and download a party's PDFs as one ZIP.

Service-level tests run the REAL `certidoes.service` functions the card
service is handed (DRY: no second implementation to drift); route tests mount
the real router like `test_certidoes_partes_router`.
"""
from __future__ import annotations

import asyncio
import dataclasses
import io
import zipfile
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.primitives.exceptions import AppException, NotFoundError

from app.modules.card_hub import certidoes_partes_router
from app.modules.card_hub import certidoes_partes_service as svc
from app.modules.certidoes import service as certidoes_svc
from app.modules.certidoes.deps import (
    build_default_service,
    get_certidoes_service,
    get_storage_backend,
)
from app.modules.certidoes.registry import CERTIDOES_CONFIG
from tests.modules.card_hub.conftest import ORG_ID
from tests.modules.card_hub.test_certidoes_partes_service import (
    _card,
    _dados,
    _sem_credencial_faltando,
)
from tests.modules.card_hub.test_certidoes_matriz import _consulta, _resultado

HOJE = date.today()
AUTH = {"Authorization": "Bearer test-token"}
BASE = "/api/clientes"


def _seed(scoped, vid, resultados, *, consulta_origem=None):
    """One consulta of the vendedor holding `resultados` [(id, tipo, over)]."""
    scoped.set_table_data("certidao_consultas", [
        {**_consulta("c1", cliente_id=vid), "origem": consulta_origem}
    ])
    scoped.set_table_data("certidao_resultados", [
        _resultado(i, "c1", tipo, **over) for i, tipo, over in resultados
    ])


def _celula(scoped, cid, tipo, rotulo="VEND 1"):
    out = svc.montar(scoped, ORG_ID, cid, hoje=HOJE)
    return next(p for p in out["partes"] if p["rotulo"] == rotulo)["celulas"][tipo]


def _status(scoped, rid):
    return next(r for r in _dados(scoped, "certidao_resultados") if r["id"] == rid)


class TestCancelar:
    def test_cancela_so_o_que_esta_em_voo_e_devolve_a_parte(self, scoped):
        cid, aid, [vid] = _card(scoped)
        _seed(scoped, vid, [
            ("r1", "cnd_federal", {"status": "processando"}),
            ("r2", "trf3", {"status": "na_fila"}),
            ("r3", "cnd_trabalhista", {"status": "sucesso", "resultado": "negativa",
                                       "emitida_em": HOJE.isoformat()}),
            ("r4", "cenprot", {"status": "pendente"}),
        ])
        out = svc.cancelar_emissao_da_parte(
            scoped, ORG_ID, cid, "pessoa", vid, atendimento_id=None,
            cancelar=certidoes_svc.cancelar_processamento,
        )
        assert out["cancelados"] == 2
        assert (_status(scoped, "r1")["status"], _status(scoped, "r2")["status"]) == ("erro", "erro")
        assert _status(scoped, "r3")["status"] == "sucesso"
        assert _status(scoped, "r4")["status"] == "pendente"
        assert out["parte"]["celulas"]["cnd_federal"]["status_processamento"] == "erro"
        assert out["parte"]["totais"]["erros"] == 2

    def test_celula_de_consulta_manual_nunca_e_cancelada(self, scoped):
        cid, aid, [vid] = _card(scoped)
        _seed(scoped, vid, [("r1", "cnd_federal", {"status": "processando"})], consulta_origem="manual")
        out = svc.cancelar_emissao_da_parte(
            scoped, ORG_ID, cid, "pessoa", vid, atendimento_id=None,
            cancelar=certidoes_svc.cancelar_processamento,
        )
        assert out["cancelados"] == 0 and _status(scoped, "r1")["status"] == "processando"
        with pytest.raises(AppException) as exc:
            svc.cancelar_emissao_do_resultado(
                scoped, ORG_ID, cid, "r1", cancelar=certidoes_svc.cancelar_processamento,
            )
        assert exc.value.status_code == 409 and exc.value.code == "NAO_CANCELAVEL"

    def test_por_celula_cancela_apenas_aquela(self, scoped):
        cid, aid, [vid] = _card(scoped)
        _seed(scoped, vid, [
            ("r1", "cnd_federal", {"status": "processando"}),
            ("r2", "trf3", {"status": "processando"}),
        ])
        out = svc.cancelar_emissao_do_resultado(
            scoped, ORG_ID, cid, "r1", cancelar=certidoes_svc.cancelar_processamento,
        )
        assert out["cancelados"] == 1
        assert (_status(scoped, "r1")["status"], _status(scoped, "r2")["status"]) == ("erro", "processando")

    def test_resultado_de_fora_do_card_404(self, scoped):
        cid, aid, [vid] = _card(scoped)
        _seed(scoped, vid, [])
        with pytest.raises(NotFoundError):
            svc.cancelar_emissao_do_resultado(
                scoped, ORG_ID, cid, str(uuid4()), cancelar=certidoes_svc.cancelar_processamento,
            )


class TestReemitirComErro:
    def _chamar(self, scoped, cid, vid, **over):
        return svc.reemitir_com_erro(
            scoped, ORG_ID, cid, "pessoa", vid, atendimento_id=None,
            check_credentials=over.pop("check_credentials", _sem_credencial_faltando),
            reprocessar=certidoes_svc.reprocessar_resultados,
        )

    def test_so_as_celulas_com_erro_voltam_no_mesmo_resultado(self, scoped):
        cid, aid, [vid] = _card(scoped)
        _seed(scoped, vid, [
            ("r1", "cnd_federal", {"status": "erro", "erro_mensagem": "boom"}),
            ("r2", "trf3", {"status": "sucesso", "resultado": "negativa", "emitida_em": HOJE.isoformat()}),
            ("r3", "cenprot", {"status": "erro", "erro_mensagem": "boom"}),
        ])
        out = self._chamar(scoped, cid, vid)
        assert out["reemitidos"] == 2 and out["consultas"] == ["c1"]
        # in place: same rows, no new consulta/resultado — and the paid one untouched
        assert len(_dados(scoped, "certidao_resultados")) == 3
        assert len(_dados(scoped, "certidao_consultas")) == 1
        assert (_status(scoped, "r1")["status"], _status(scoped, "r1")["erro_mensagem"]) == ("pendente", None)
        assert _status(scoped, "r2")["status"] == "sucesso"
        assert _status(scoped, "r3")["status"] == "pendente"
        assert out["parte"]["totais"]["erros"] == 0

    def test_tjsp_vai_para_a_fila_e_sinaliza(self, scoped):
        cid, aid, [vid] = _card(scoped)
        _seed(scoped, vid, [("r1", "tjsp", {"status": "erro", "erro_mensagem": "x"})])
        out = self._chamar(scoped, cid, vid)
        assert _status(scoped, "r1")["status"] == "na_fila" and out["tem_tjsp"] is True

    def test_nada_com_erro_nao_exige_credencial_nem_agenda(self, scoped):
        cid, aid, [vid] = _card(scoped)
        _seed(scoped, vid, [("r1", "cnd_federal", {"status": "sucesso", "resultado": "negativa"})])
        out = self._chamar(scoped, cid, vid, check_credentials=lambda _o: ["sem token"])
        assert out["reemitidos"] == 0 and out["consultas"] == []

    def test_erro_de_consulta_manual_nao_e_reemitido(self, scoped):
        cid, aid, [vid] = _card(scoped)
        _seed(scoped, vid, [("r1", "cnd_federal", {"status": "erro", "erro_mensagem": "pdf ruim"})],
              consulta_origem="manual")
        assert self._chamar(scoped, cid, vid)["reemitidos"] == 0
        assert _status(scoped, "r1")["status"] == "erro"

    def test_credencial_ausente_422_antes_de_escrever(self, scoped):
        cid, aid, [vid] = _card(scoped)
        _seed(scoped, vid, [("r1", "cnd_federal", {"status": "erro", "erro_mensagem": "x"})])
        with pytest.raises(AppException) as exc:
            self._chamar(scoped, cid, vid, check_credentials=lambda _o: ["Falta o token."])
        assert exc.value.code == "CREDENCIAIS_AUSENTES"
        assert _status(scoped, "r1")["status"] == "erro"


class TestDescartar:
    def test_o_descarte_devolve_a_celula_a_evidencia_anterior(self, scoped):
        cid, aid, [vid] = _card(scoped)
        _seed(scoped, vid, [
            ("old", "cnd_federal", {"status": "sucesso", "resultado": "negativa",
                                    "emitida_em": (HOJE - timedelta(days=3)).isoformat()}),
            ("bad", "cnd_federal", {"status": "sucesso", "resultado": "positiva",
                                    "emitida_em": HOJE.isoformat(), "created_at": "2026-02-01T00:00:00+00:00"}),
        ])
        assert _celula(scoped, cid, "cnd_federal")["resultado_id"] == "bad"
        out = svc.descartar_emissao(
            scoped, ORG_ID, cid, "bad", user_id=str(uuid4()),
            descartar=certidoes_svc.soft_delete_resultado,
        )
        assert out["parte"]["celulas"]["cnd_federal"]["resultado_id"] == "old"
        assert _celula(scoped, cid, "cnd_federal")["resultado_id"] == "old"
        row = _status(scoped, "bad")
        assert row["excluida_em"] is not None  # soft: the row (and its blob) stay

    def test_ultimo_resultado_da_consulta_leva_a_consulta(self, scoped):
        cid, aid, [vid] = _card(scoped)
        _seed(scoped, vid, [("only", "cnd_federal", {"status": "sucesso", "resultado": "negativa"})])
        out = svc.descartar_emissao(
            scoped, ORG_ID, cid, "only", user_id="u", descartar=certidoes_svc.soft_delete_resultado,
        )
        assert out["parte"]["celulas"]["cnd_federal"]["resultado_id"] is None
        assert _dados(scoped, "certidao_consultas")[0]["excluida_em"] is not None

    def test_em_andamento_409(self, scoped):
        cid, aid, [vid] = _card(scoped)
        _seed(scoped, vid, [("r1", "cnd_federal", {"status": "processando"})])
        with pytest.raises(AppException) as exc:
            svc.descartar_emissao(
                scoped, ORG_ID, cid, "r1", user_id="u", descartar=certidoes_svc.soft_delete_resultado,
            )
        assert exc.value.code == "EMISSAO_EM_ANDAMENTO"
        assert _status(scoped, "r1").get("excluida_em") is None

    def test_resultado_inexistente_404(self, scoped):
        cid, aid, [vid] = _card(scoped)
        _seed(scoped, vid, [])
        with pytest.raises(NotFoundError):
            svc.descartar_emissao(
                scoped, ORG_ID, cid, str(uuid4()), user_id="u",
                descartar=certidoes_svc.soft_delete_resultado,
            )


class TestEmitirTodasPulaVigentes:
    def _todas(self, scoped, cid, vid):
        return svc.solicitar_emissao(
            scoped, ORG_ID, cid, "pessoa", vid, tipos=None, atendimento_id=None,
            user_id=str(uuid4()), check_credentials=_sem_credencial_faltando,
        )

    def test_sucesso_em_dia_e_em_andamento_nao_sao_recompradas(self, scoped):
        cid, aid, [vid] = _card(scoped)
        _seed(scoped, vid, [
            ("r1", "cnd_federal", {"status": "sucesso", "resultado": "negativa", "emitida_em": HOJE.isoformat()}),
            ("r2", "trf3", {"status": "processando"}),
        ])
        out = self._todas(scoped, cid, vid)
        pedidos = {r["tipo"] for r in out["resultados"]}
        assert sorted(out["ignoradas"]) == ["cnd_federal", "trf3"]
        assert not pedidos & {"cnd_federal", "trf3"}
        esperados = {c["tipo"] for c in CERTIDOES_CONFIG if c["tipo"] != "tjsp"} - {"cnd_federal", "trf3"}
        assert pedidos == esperados

    def test_vencida_e_com_erro_sao_recompradas(self, scoped):
        cid, aid, [vid] = _card(scoped)
        _seed(scoped, vid, [
            ("r1", "cnd_federal", {"status": "sucesso", "resultado": "negativa",
                                   "emitida_em": (HOJE - timedelta(days=400)).isoformat()}),
            ("r2", "trf3", {"status": "erro", "erro_mensagem": "x"}),
        ])
        out = self._todas(scoped, cid, vid)
        assert out["ignoradas"] == []
        assert {"cnd_federal", "trf3"} <= {r["tipo"] for r in out["resultados"]}

    def test_tudo_vigente_409_sem_escrever(self, scoped):
        cid, aid, [vid] = _card(scoped)
        _seed(scoped, vid, [
            (f"r{i}", c["tipo"], {"status": "sucesso", "resultado": "negativa", "emitida_em": HOJE.isoformat()})
            for i, c in enumerate(c for c in CERTIDOES_CONFIG if c["tipo"] != "tjsp")
        ])
        antes = len(_dados(scoped, "certidao_consultas"))
        with pytest.raises(AppException) as exc:
            self._todas(scoped, cid, vid)
        assert exc.value.code == "NADA_A_EMITIR" and exc.value.status_code == 409
        assert len(_dados(scoped, "certidao_consultas")) == antes

    def test_tipo_escolhido_por_nome_passa_mesmo_vigente(self, scoped):
        cid, aid, [vid] = _card(scoped)
        _seed(scoped, vid, [
            ("r1", "cnd_federal", {"status": "sucesso", "resultado": "negativa", "emitida_em": HOJE.isoformat()}),
        ])
        out = svc.solicitar_emissao(
            scoped, ORG_ID, cid, "pessoa", vid, tipos=["cnd_federal"], atendimento_id=None,
            user_id="u", check_credentials=_sem_credencial_faltando,
        )
        assert [r["tipo"] for r in out["resultados"]] == ["cnd_federal"] and out["ignoradas"] == []


class TestTotaisErros:
    def test_erros_e_overlay_da_cor(self, scoped):
        cid, aid, [vid] = _card(scoped)
        _seed(scoped, vid, [("r1", "cnd_federal", {"status": "erro", "erro_mensagem": "falhou"})])
        out = svc.montar(scoped, ORG_ID, cid, hoje=HOJE)
        vend = next(p for p in out["partes"] if p["rotulo"] == "VEND 1")
        assert vend["totais"]["erros"] == 1 and vend["totais"]["pendente"] == 12


class TestArquivosDaParte:
    def test_so_os_vencedores_com_pdf(self, scoped):
        cid, aid, [vid] = _card(scoped)
        _seed(scoped, vid, [
            ("r1", "cnd_federal", {"status": "sucesso", "arquivo_url": "k/a.pdf", "arquivo_nome": "a.pdf",
                                   "nome_display": "CND Federal"}),
            ("r2", "trf3", {"status": "sucesso"}),
        ])
        parte, items = svc.arquivos_da_parte(scoped, ORG_ID, cid, "pessoa", vid, atendimento_id=None)
        assert parte["rotulo"] == "VEND 1"
        assert items == [{"arquivo_url": "k/a.pdf", "arquivo_nome": "a.pdf", "nome_display": "CND Federal"}]


# ─── HTTP ───────────────────────────────────────────────────────────────


@pytest.fixture
def agendar_tjsp():
    return MagicMock()


@pytest.fixture
def storage():
    return FakeStorageBackend()


@pytest.fixture
def api(client, scoped, agendar_tjsp, storage):
    from app.main import app as base_app

    local = FastAPI()
    local.exception_handlers.update(base_app.exception_handlers)
    local.include_router(certidoes_partes_router.router, prefix=BASE)
    processar = AsyncMock()
    fake = dataclasses.replace(
        build_default_service(),
        check_required_credentials=lambda _o: [],
        processar_consulta=processar,
        schedule_tjsp_for_org=agendar_tjsp,
    )
    local.dependency_overrides[get_certidoes_service] = lambda: fake
    local.dependency_overrides[get_storage_backend] = lambda: storage
    api = TestClient(local)
    api.processar = processar
    return api


class TestHttp:
    @pytest.mark.parametrize("metodo,caminho,corpo", [
        ("post", "resultados/{rid}/cancelar", {}),
        ("post", "partes/pessoa/{rid}/cancelar", {}),
        ("post", "partes/pessoa/{rid}/reemitir-erros", {}),
        ("delete", "resultados/{rid}", None),
        ("get", "partes/pessoa/{rid}/download-zip", None),
    ])
    def test_sem_token_401(self, api, metodo, caminho, corpo):
        url = f"{BASE}/{uuid4()}/certidoes/" + caminho.format(rid=uuid4())
        kw = {"json": corpo} if corpo is not None else {}
        assert getattr(api, metodo)(url, **kw).status_code == 401

    def test_cancelar_celula(self, api, scoped):
        cid, aid, [vid] = _card(scoped)
        r1 = str(uuid4())
        _seed(scoped, vid, [(r1, "cnd_federal", {"status": "processando"})])
        resp = api.post(f"{BASE}/{cid}/certidoes/resultados/{r1}/cancelar", json={}, headers=AUTH)
        assert resp.status_code == 200, resp.text
        assert resp.json()["cancelados"] == 1
        assert resp.json()["parte"]["celulas"]["cnd_federal"]["status_processamento"] == "erro"

    def test_cancelar_parte(self, api, scoped):
        cid, aid, [vid] = _card(scoped)
        _seed(scoped, vid, [("r1", "cnd_federal", {"status": "na_fila"})])
        resp = api.post(f"{BASE}/{cid}/certidoes/partes/pessoa/{vid}/cancelar", json={}, headers=AUTH)
        assert resp.status_code == 200 and resp.json()["cancelados"] == 1

    def test_reemitir_erros_agenda_o_processamento_da_consulta(self, api, scoped, agendar_tjsp):
        cid, aid, [vid] = _card(scoped)
        _seed(scoped, vid, [("r1", "cnd_federal", {"status": "erro", "erro_mensagem": "x"})])
        resp = api.post(f"{BASE}/{cid}/certidoes/partes/pessoa/{vid}/reemitir-erros", json={}, headers=AUTH)
        assert resp.status_code == 200, resp.text
        assert resp.json()["reemitidos"] == 1
        api.processar.assert_awaited_once()
        assert api.processar.await_args.args[0] == "c1"
        agendar_tjsp.assert_not_called()

    def test_reemitir_erros_tjsp_agenda_a_fila(self, api, scoped, agendar_tjsp):
        cid, aid, [vid] = _card(scoped)
        _seed(scoped, vid, [("r1", "tjsp", {"status": "erro", "erro_mensagem": "x"})])
        api.post(f"{BASE}/{cid}/certidoes/partes/pessoa/{vid}/reemitir-erros", json={}, headers=AUTH)
        agendar_tjsp.assert_called_once()

    def test_descartar(self, api, scoped):
        cid, aid, [vid] = _card(scoped)
        old, bad = str(uuid4()), str(uuid4())
        _seed(scoped, vid, [
            (old, "cnd_federal", {"status": "sucesso", "resultado": "negativa",
                                  "emitida_em": (HOJE - timedelta(days=2)).isoformat()}),
            (bad, "cnd_federal", {"status": "sucesso", "resultado": "positiva",
                                    "emitida_em": HOJE.isoformat()}),
        ])
        resp = api.delete(f"{BASE}/{cid}/certidoes/resultados/{bad}", headers=AUTH)
        assert resp.status_code == 200, resp.text
        assert resp.json()["parte"]["celulas"]["cnd_federal"]["resultado_id"] == old

    def test_download_zip(self, api, scoped, storage):
        cid, aid, [vid] = _card(scoped)
        key = f"{ORG_ID}/certidoes/c1/a.pdf"
        asyncio.run(storage.put(bucket=certidoes_svc.BUCKET, key=key, data=b"%PDF-1"))
        _seed(scoped, vid, [("r1", "cnd_federal", {
            "status": "sucesso", "arquivo_url": key, "arquivo_nome": "cnd.pdf", "nome_display": "CND"})])
        resp = api.get(f"{BASE}/{cid}/certidoes/partes/pessoa/{vid}/download-zip", headers=AUTH)
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == "application/zip"
        assert zipfile.ZipFile(io.BytesIO(resp.content)).namelist() == ["cnd.pdf"]

    def test_download_zip_sem_pdf_404(self, api, scoped):
        cid, aid, [vid] = _card(scoped)
        _seed(scoped, vid, [("r1", "cnd_federal", {"status": "sucesso"})])
        resp = api.get(f"{BASE}/{cid}/certidoes/partes/pessoa/{vid}/download-zip", headers=AUTH)
        assert resp.status_code == 404 and resp.json()["error"]["code"] == "SEM_ARQUIVOS"
