"""A hand-edited certidão cell can go back to the automatic pipeline, a
complete typed cell counts as done, a consulta without a printed date takes
the PDF CreationDate (marked as inferred), and a cell being read is counted
apart from the pendentes. Everything here is SYNTHETIC (counting-sequence
numbers, a generated PDF)."""
from __future__ import annotations

from datetime import date
from uuid import uuid4

import fitz
import httpx
import pytest
from noctusai_lib.integrations.storage import FakeStorageBackend

from app.modules.card_hub import certidoes_partes_service as partes
from app.modules.certidoes import cenprot, service
from tests.modules.test_certidoes_p0c import (
    ORG, RESULTADOS, _client, _consulta, _doc, _RECENTE, _resultado,
)

CONSULTAS = service.CONSULTAS
HOJE = date(2026, 10, 22)


def _pdf(creation: str | None) -> bytes:
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Protocolo da Consulta: 0123456789")
    if creation:
        doc.set_metadata({"creationDate": creation})
    return doc.tobytes()


class TestDataDosMetadados:
    def test_le_o_creation_date_do_pdf(self):
        assert cenprot.data_dos_metadados_pdf(_pdf("D:20260210090409-03'00'")) == date(2026, 2, 10)

    def test_sem_metadado_ou_pdf_ilegivel_e_none(self):
        assert cenprot.data_dos_metadados_pdf(b"nao e pdf") is None

    def test_fora_da_janela_do_cenprot_nao_e_plausivel(self):
        pdf = _pdf("D:20240101000000Z")
        assert cenprot.data_plausivel_dos_metadados(pdf, date(2026, 6, 20)) is None
        assert cenprot.data_plausivel_dos_metadados(_pdf("D:20260210090409Z"), date(2026, 6, 20)) == date(2026, 2, 10)

    def test_sem_data_de_referencia_nao_ha_como_julgar(self):
        assert cenprot.data_plausivel_dos_metadados(_pdf("D:20260210090409Z"), None) is None


class TestAplicarDataDosMetadados:
    def _db(self):
        return _client(**{CONSULTAS: [_consulta(created_at="2026-06-20T10:00:00+00:00")]})

    def test_consulta_sem_data_impressa_usa_o_creation_date_e_marca(self):
        db = self._db()
        c = db.table(CONSULTAS).select("*").execute().data[0]
        destino = {"numero": "0123456789"}
        service._aplicar_data_dos_metadados(
            destino, _pdf("D:20260210090409-03'00'"), "cenprot", c["id"], db,
        )
        assert destino["emitida_em"] == "2026-02-10"
        assert destino["emitida_em_origem"] == "metadados_pdf"

    def test_data_lida_nunca_e_sobrescrita_e_zera_a_marca(self):
        db = self._db()
        c = db.table(CONSULTAS).select("*").execute().data[0]
        destino = {"numero": "1", "emitida_em": "2026-03-01", "emitida_em_origem": "metadados_pdf"}
        service._aplicar_data_dos_metadados(destino, _pdf("D:20260210000000Z"), "serasa", c["id"], db)
        assert destino["emitida_em"] == "2026-03-01"
        assert destino["emitida_em_origem"] is None

    def test_sem_identidade_lida_nao_ganha_data(self):
        db = self._db()
        c = db.table(CONSULTAS).select("*").execute().data[0]
        destino: dict = {}
        service._aplicar_data_dos_metadados(destino, _pdf("D:20260210000000Z"), "cenprot", c["id"], db)
        assert "emitida_em" not in destino

    def test_outros_tipos_nao_usam_o_metadado(self):
        db = self._db()
        c = db.table(CONSULTAS).select("*").execute().data[0]
        destino = {"numero": "1"}
        service._aplicar_data_dos_metadados(destino, _pdf("D:20260210000000Z"), "cnd_federal", c["id"], db)
        assert "emitida_em" not in destino


class TestCelulaManualCompletaEConcluida:
    def test_confirmar_completo_vira_sucesso(self):
        r = _resultado(status="pendente")
        db = _client(**{RESULTADOS: [r]})
        out = service.confirmar_resultado(
            db, ORG, r["id"],
            {"resultado": "negativa", "numero": "123", "emitida_em": "2026-10-01"}, "user-1",
        )
        assert out["status"] == "sucesso"
        assert out["resultado_origem"] == "manual"

    def test_incompleto_continua_pendente(self):
        r = _resultado(status="pendente")
        db = _client(**{RESULTADOS: [r]})
        out = service.confirmar_resultado(db, ORG, r["id"], {"numero": "123"}, "user-1")
        assert out["status"] == "pendente"

    def test_celula_lendo_nao_e_promovida(self):
        r = _resultado(status="processando")
        db = _client(**{RESULTADOS: [r]})
        out = service.confirmar_resultado(
            db, ORG, r["id"],
            {"resultado": "negativa", "numero": "1", "emitida_em": "2026-10-01"}, "user-1",
        )
        assert out["status"] == "processando"

    def test_digitar_data_limpa_a_marca_de_inferida(self):
        r = _resultado(emitida_em="2026-02-10", emitida_em_origem="metadados_pdf")
        db = _client(**{RESULTADOS: [r]})
        out = service.confirmar_resultado(db, ORG, r["id"], {"emitida_em": "2026-02-11"}, "u")
        assert out["emitida_em_origem"] is None

    def test_leitura_da_celula_ja_gravada_pendente_conta_como_ok(self):
        row = {
            "id": "r", "status": "pendente", "resultado_origem": "manual",
            "resultado": "negativa", "numero": "1", "emitida_em": "2026-10-01",
        }
        c = partes.montar_celula("serasa", row, HOJE, 30)
        assert c["status"] == "nao_constam"
        incompleta = partes.montar_celula("serasa", {**row, "numero": None}, HOJE, 30)
        assert incompleta["status"] == "pendente"


class TestTotaisRelendo:
    def _parte(self):
        return {
            "chave": "c:1", "kind": "pessoa", "tipo_pessoa": "PF", "rotulo": "COMP 1",
            "lado": "comprador", "grupo": "comprador", "papel": "comprador",
            "titular": True, "nome": "X", "documento": None, "cliente_id": "1",
            "empresa_id": None, "parte_id": None,
        }

    def _totais(self, rows):
        linhas = [
            {"tipo": r["tipo"], "chave": r["tipo"], "custom": False, "id": None,
             "linha": "1", "rotulo": r["tipo"]}
            for r in rows
        ]
        return partes.montar_parte(self._parte(), linhas, rows, HOJE, 30)

    def test_processando_sem_valor_nao_e_pendente(self):
        out = self._totais([
            {"id": "a", "tipo": "cnd_federal", "status": "processando", "resultado": None, "created_at": "1"},
            {"id": "b", "tipo": "trf3", "status": "pendente", "resultado": None, "created_at": "1"},
        ])
        assert out["totais"]["processando"] == 1
        assert out["totais"]["pendente"] == 1

    def test_releitura_mantem_o_valor_anterior_e_conta_como_relendo(self):
        out = self._totais([
            {"id": "a", "tipo": "cnd_federal", "status": "processando",
             "resultado": "negativa", "created_at": "1"},
        ])
        assert out["celulas"]["cnd_federal"]["status"] == "nao_constam"
        assert out["totais"]["nao_constam"] == 1
        assert out["totais"]["pendente"] == 0
        assert out["totais"]["relendo"] == 1


class TestVoltarALeituraAutomatica:
    async def _voltar(self, db, resultado_id, storage=None):
        async with httpx.AsyncClient() as http:
            return await service.voltar_a_leitura_automatica(
                db, ORG, resultado_id, storage=storage or FakeStorageBackend(),
                http_client=http, usuario_id="u1",
            )

    @pytest.mark.asyncio
    async def test_desconhecido_e_none(self):
        assert await self._voltar(_client(**{RESULTADOS: []}), str(uuid4())) is None

    @pytest.mark.asyncio
    async def test_serasa_reaplica_o_crednet_como_numa_celula_nova(self):
        cliente_id = str(uuid4())
        consulta = _consulta(cliente_id=cliente_id)
        manual = _resultado(
            consulta_id=consulta["id"], tipo="serasa", status="sucesso",
            resultado_origem="manual", resultado="positiva", numero="999",
            emitida_em="2020-01-01", confirmado_por="u0",
            confirmado_em="2026-10-01T00:00:00+00:00",
        )
        db = _client(**{
            CONSULTAS: [consulta], RESULTADOS: [manual],
            "cliente_documentos": [{
                "id": str(uuid4()), "storage_path": f"{ORG}/clientes/{cliente_id}/c",
                "org_id": ORG, "cliente_id": cliente_id, "tipo_documento": "serasa_crednet",
                "extracao_status": "ok", "deleted_at": None,
                "extracao_crednet": {
                    "cpf": consulta["documento"], "protocolo": "1111111",
                    "consulta_em": _RECENTE.isoformat(), "ocorrencias_constam": False,
                },
            }],
        })
        row, kwargs = await self._voltar(db, manual["id"])
        assert kwargs is None
        got = db.table(RESULTADOS).select("*").eq("id", manual["id"]).execute().data[0]
        assert got["numero"] == "1111111"
        assert got["resultado"] == "negativa"
        assert got["resultado_origem"] == "ia"
        assert got["confirmado_por"] is None and got["confirmado_em"] is None
        assert got["emitida_em"] == _RECENTE.date().isoformat()

    @pytest.mark.asyncio
    async def test_com_pdf_limpa_o_lock_e_agenda_a_releitura_que_agora_grava(self):
        storage = FakeStorageBackend()
        chave = f"{ORG}/certidoes/c/cenprot.pdf"
        await storage.put(bucket=service.BUCKET, key=chave, data=_pdf(None), content_type="application/pdf")
        consulta = _consulta()
        manual = _resultado(
            consulta_id=consulta["id"], tipo="cenprot", status="sucesso",
            arquivo_url=chave, resultado_origem="manual", resultado="positiva",
            numero="999", emitida_em="2020-01-01", confirmado_por="u0",
        )
        db = _client(**{CONSULTAS: [consulta], RESULTADOS: [manual]})
        row, kwargs = await self._voltar(db, manual["id"], storage)
        got = db.table(RESULTADOS).select("*").eq("id", manual["id"]).execute().data[0]
        assert got["resultado_origem"] is None and got["confirmado_por"] is None
        assert got["numero"] is None and got["resultado"] is None
        assert got["status"] == "processando"
        # The re-read now sees an UNLOCKED row: it writes, it does not just diverge.
        assert kwargs["resultado_origem_atual"] is None
        assert kwargs["confirmado_por_atual"] is None

    @pytest.mark.asyncio
    async def test_sem_fonte_automatica_volta_a_pendente(self):
        consulta = _consulta()
        manual = _resultado(
            consulta_id=consulta["id"], tipo="trf3", status="sucesso",
            resultado_origem="manual", resultado="negativa", numero="1",
            emitida_em="2026-10-01", confirmado_por="u0",
        )
        db = _client(**{CONSULTAS: [consulta], RESULTADOS: [manual]})
        row, kwargs = await self._voltar(db, manual["id"])
        assert kwargs is None
        got = db.table(RESULTADOS).select("*").eq("id", manual["id"]).execute().data[0]
        assert got["status"] == "pendente" and got["resultado"] is None

    @pytest.mark.asyncio
    async def test_celula_em_leitura_e_recusada(self):
        consulta = _consulta()
        r = _resultado(consulta_id=consulta["id"], status="processando")
        db = _client(**{CONSULTAS: [consulta], RESULTADOS: [r]})
        with pytest.raises(service.ReleituraRecusada):
            await self._voltar(db, r["id"])


#: Synthetic mirror of a browser print of a CENPROT consulta: a protocol, NO
#: emission line, and only the print footer (time line, blank line, date line).
_PAGINA_IMPRESSA = (
    "Consulta de Protesto\nProtocolo da Consulta: 0123456789\n"
    "Nenhum protesto encontrado.\nComo posso ajudá-lo hoje?\n\n09:01\n\n10/02/2026"
)


class TestCadeiaDeDataDaConsulta:
    """Printed date > PDF metadata > (LIVE only) consulta day (F56)."""

    def _db(self):
        # The consulta row is created at UPLOAD time — months after the print.
        return _client(**{CONSULTAS: [_consulta(created_at="2026-10-22T10:00:00+00:00")]})

    def _cid(self, db):
        return db.table(CONSULTAS).select("*").execute().data[0]["id"]

    def test_rodape_de_impressao_do_navegador_e_a_data_impressa(self):
        db = self._db()
        destino = {"numero": "0123456789"}
        service._aplicar_data_dos_metadados(
            destino, _pdf(None), "cenprot", self._cid(db), db, (_PAGINA_IMPRESSA,),
        )
        assert destino["emitida_em"] == "2026-02-10"
        assert destino["emitida_em_origem"] is None

    def test_rodape_so_com_a_data_e_no_inicio_da_pagina(self):
        db = self._db()
        destino = {"numero": "1"}
        service._aplicar_data_dos_metadados(
            destino, _pdf(None), "serasa", self._cid(db), db, ("10/02/2026\nResto da pagina",),
        )
        assert destino["emitida_em"] == "2026-02-10"

    def test_data_impressa_vence_o_metadado(self):
        db = self._db()
        destino = {"numero": "1"}
        service._aplicar_data_dos_metadados(
            destino, _pdf("D:20260301090409Z"), "cenprot", self._cid(db), db,
            ("Data da consulta: 15/05/2026",),
        )
        assert destino["emitida_em"] == "2026-05-15"

    def test_upload_sem_data_em_lugar_nenhum_fica_nulo_nunca_o_dia_do_upload(self):
        db = self._db()
        destino = {"numero": "0123456789"}
        service._aplicar_data_dos_metadados(
            destino, _pdf(None), "cenprot", self._cid(db), db, ("Protocolo da Consulta: 0123456789",),
        )
        assert "emitida_em" not in destino or destino["emitida_em"] is None

    def test_upload_com_data_no_futuro_ou_antiquissima_e_ignorada(self):
        db = self._db()
        for texto in ("Data da consulta: 01/01/2099", "Data da consulta: 01/01/2001"):
            destino = {"numero": "1"}
            service._aplicar_data_dos_metadados(
                destino, _pdf(None), "cenprot", self._cid(db), db, (texto,),
            )
            assert not destino.get("emitida_em")

    def test_emissao_viva_sem_data_usa_o_dia_da_consulta(self):
        db = self._db()
        destino = {"numero": "1"}
        service._aplicar_data_dos_metadados(
            destino, _pdf(None), "cenprot", self._cid(db), db, (), viva=True,
        )
        assert destino["emitida_em"] == "2026-10-22"
        assert destino["emitida_em_origem"] == "data_da_consulta"

    @pytest.mark.asyncio
    async def test_releitura_completa_do_pdf_impresso_grava_a_data_do_rodape(self):
        from unittest.mock import AsyncMock

        consulta = _consulta(created_at="2026-10-22T10:00:00+00:00")
        chave = f"{ORG}/certidoes/c/cenprot.pdf"
        resultado = _resultado(
            consulta_id=consulta["id"], tipo="cenprot", status="sucesso",
            arquivo_url=chave, resultado_origem="ia", numero="0123456789",
        )
        db = _client(**{CONSULTAS: [consulta], RESULTADOS: [resultado]})
        patch = await service.executar_releitura(
            pdf_bytes=_pdf(None), resultado_id=resultado["id"], consulta_id=consulta["id"],
            nome_display="CENPROT", org_id=ORG, db=db, tipo="cenprot", manual=True,
            resultado_origem_atual="ia", confirmado_por_atual=None,
            valores_atuais={"numero": "0123456789"},
            extract_text=AsyncMock(return_value=service.ExtractedPdfText(
                para_ia=_PAGINA_IMPRESSA, texto_extraido=_PAGINA_IMPRESSA,
                paginas_texto=(_PAGINA_IMPRESSA,),
            )),
            analyze=AsyncMock(return_value="resumo"),
            analyze_estrutura=AsyncMock(return_value={"resultado": "negativa"}),
            estruturar_cenprot_fn=AsyncMock(return_value=cenprot.CenprotEstrutura(numero="0123456789")),
        )
        got = db.table(RESULTADOS).select("*").eq("id", resultado["id"]).execute().data[0]
        assert got["emitida_em"] == "2026-02-10" == patch["emitida_em"]

    @pytest.mark.asyncio
    async def test_releitura_completa_sem_data_deixa_nulo(self):
        from unittest.mock import AsyncMock

        consulta = _consulta(created_at="2026-10-22T10:00:00+00:00")
        resultado = _resultado(
            consulta_id=consulta["id"], tipo="cenprot", status="sucesso",
            arquivo_url=f"{ORG}/certidoes/c/cenprot.pdf", resultado_origem="ia",
        )
        db = _client(**{CONSULTAS: [consulta], RESULTADOS: [resultado]})
        texto = "Protocolo da Consulta: 0123456789"
        await service.executar_releitura(
            pdf_bytes=_pdf(None), resultado_id=resultado["id"], consulta_id=consulta["id"],
            nome_display="CENPROT", org_id=ORG, db=db, tipo="cenprot", manual=True,
            resultado_origem_atual="ia", confirmado_por_atual=None, valores_atuais={},
            extract_text=AsyncMock(return_value=service.ExtractedPdfText(
                para_ia=texto, texto_extraido=texto, paginas_texto=(texto,),
            )),
            analyze=AsyncMock(return_value="resumo"),
            analyze_estrutura=AsyncMock(return_value={"resultado": "negativa"}),
            estruturar_cenprot_fn=AsyncMock(return_value=cenprot.CenprotEstrutura(numero="0123456789")),
        )
        got = db.table(RESULTADOS).select("*").eq("id", resultado["id"]).execute().data[0]
        assert got["numero"] == "0123456789" and not got["emitida_em"]
