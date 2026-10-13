"""The model-routing learning loop, product half (migration 254): every routed
read is recorded per critical field (model, verdict, fallback, agreement,
cost — fingerprints, never values), and a human's later resolution stamps
which read was right."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.modules.card_hub import identidade_extracao_service as svc
from app.modules.card_hub import leitura_resultados as lr
from noctusai_lib.integrations.documents import FakeIdentityExtractor
from noctusai_lib.integrations.documents.confianca import impressao
from noctusai_lib.integrations.documents.types import (
    CustoLeitura,
    DesfechoCampo,
    ExtractionConfidence,
    IdentityFields,
    ResumoRoteamento,
    TextSource,
)
from noctusai_lib.integrations.storage import FakeStorageBackend
from tests.modules.card_hub.conftest import ORG_ID, cliente_row

ORG_UUID = UUID(ORG_ID)
BUCKET = "social-wiring-documentos"
NOME_A, NOME_B = "JOAO CARLOS PEREIRA", "JOAO CARLOS PEREIRA FILHO"


def _resumo(*desfechos: DesfechoCampo, fallback=True) -> ResumoRoteamento:
    return ResumoRoteamento(
        tipo_documento="cnh", modelo_primario="claude-sonnet-5",
        modelo_fallback="claude-opus-5-5", modo="producao", fallback_executado=fallback,
        campos=desfechos,
        custos=(
            CustoLeitura("claude-sonnet-5", "primaria", 1, 5000, 800, 0.018),
            CustoLeitura("claude-opus-5-5", "fallback", 1, 5000, 900, 0.056),
        ),
    )


def _divergente() -> DesfechoCampo:
    return DesfechoCampo(
        campo="nome", veredito="duvidoso", motivos=("ancora_falhou",),
        resultado="divergiu", acordo=False,
        impressao_primaria=impressao("nome", NOME_A), impressao_fallback=impressao("nome", NOME_B),
    )


def _linhas(scoped) -> list[dict]:
    return scoped.table(lr.TABELA).select("*").execute().data


class TestRecording:
    def test_one_row_per_critical_field_without_values(self, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data(lr.TABELA, [])
        fields = IdentityFields(
            source=TextSource.OCR,
            roteamento=_resumo(
                _divergente(),
                DesfechoCampo(campo="cpf", veredito="confiavel", motivos=("dv_verificado",),
                              impressao_primaria=impressao("cpf", "412.954.238-98")),
            ),
        )
        n = lr.registrar_leitura(scoped, ORG_UUID, UUID(cid), uuid4(), "cnh", fields)
        assert n == 2
        rows = {r["campo"]: r for r in _linhas(scoped)}
        assert rows["nome"]["resultado"] == "divergiu" and rows["nome"]["acordo"] is False
        assert rows["cpf"]["veredito"] == "confiavel"
        assert rows["cpf"]["usd_documento"] == pytest.approx(0.074)
        assert rows["nome"]["modelo_fallback"] == "claude-opus-5-5"
        blob = repr(rows)
        assert NOME_A not in blob and "412.954.238-98" not in blob and "41295423898" not in blob

    def test_a_read_without_routing_records_nothing(self, scoped):
        scoped.set_table_data(lr.TABELA, [])
        assert lr.registrar_leitura(scoped, ORG_UUID, None, None, "rg", IdentityFields()) == 0


class TestHumanResolution:
    def _seed(self, scoped) -> str:
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data(lr.TABELA, [])
        fields = IdentityFields(source=TextSource.OCR, roteamento=_resumo(_divergente()))
        lr.registrar_leitura(scoped, ORG_UUID, UUID(cid), uuid4(), "cnh", fields)
        return cid

    def test_accepting_reading_b_marks_the_fallback_right(self, scoped):
        cid = self._seed(scoped)
        conflito_id = str(uuid4())
        scoped.set_table_data("cliente_campo_conflitos", [{
            "id": conflito_id, "org_id": ORG_ID, "cliente_id": cid,
            "campo": "nome_oficial",
            "valor_anterior": NOME_A, "origem_anterior": svc.ORIGEM_LEITURA_A,
            "valor_proposto": NOME_B, "origem_proposto": svc.ORIGEM_LEITURA_B,
            "confianca_proposta": "baixa",
            "fonte_tabela": "cliente_documentos", "fonte_id": str(uuid4()),
            "status": "pendente", "notificado_em": None,
            "decidido_por": None, "decidido_em": None,
        }])
        svc.resolver_conflito(scoped, ORG_UUID, UUID(conflito_id), aceitar=True, decidido_por=uuid4())
        row = _linhas(scoped)[0]
        assert row["resolucao"] == "conflito_aceito"
        assert row["fallback_correto"] is True and row["primario_correto"] is False

    def test_reject_then_manual_edit_settles_the_primary(self, scoped):
        cid = self._seed(scoped)
        lr.registrar_resolucao(scoped, ORG_UUID, UUID(cid), "nome_oficial",
                               resolucao="conflito_rejeitado")
        row = _linhas(scoped)[0]
        assert row["resolucao"] == "conflito_rejeitado" and row["fallback_correto"] is False
        lr.registrar_resolucao(scoped, ORG_UUID, UUID(cid), "nome_oficial",
                               resolucao="edicao_manual", valor_final=NOME_A.title())
        row = _linhas(scoped)[0]
        assert row["resolucao"] == "edicao_manual" and row["primario_correto"] is True

    def test_a_settled_row_is_not_resettled(self, scoped):
        cid = self._seed(scoped)
        lr.registrar_resolucao(scoped, ORG_UUID, UUID(cid), "nome_oficial",
                               resolucao="confirmado", valor_final=NOME_A)
        assert lr.registrar_resolucao(scoped, ORG_UUID, UUID(cid), "nome_oficial",
                                      resolucao="edicao_manual", valor_final=NOME_B) == 0


class TestWiredIntoTheExtraction:
    @pytest.mark.asyncio
    async def test_extrair_identidade_records_the_routed_read(self, client, scoped):
        cid, did = str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        path = f"{ORG_ID}/clientes/{cid}/{did}"
        scoped.set_table_data("cliente_documentos", [{
            "id": did, "org_id": ORG_ID, "cliente_id": cid, "storage_path": path,
            "nome_original": "cnh.pdf", "mime_type": "application/pdf",
            "tipo_documento": "cnh", "deleted_at": None, "extracao_status": "pendente",
        }])
        scoped.set_table_data("cliente_documento_acessos", [])
        scoped.set_table_data(lr.TABELA, [])
        storage = FakeStorageBackend()
        await storage.put(bucket=BUCKET, key=path, data=b"%PDF-1.4 x", content_type="application/pdf")
        fields = IdentityFields(
            source=TextSource.OCR, nome="MARIA DA SILVA SOUZA",
            nome_confianca=ExtractionConfidence.BAIXA,
            roteamento=_resumo(
                DesfechoCampo(campo="nome", veredito="confiavel",
                              impressao_primaria=impressao("nome", "MARIA DA SILVA SOUZA")),
                fallback=False,
            ),
        )
        extractor = FakeIdentityExtractor(fields)
        await svc.extrair_identidade(scoped, storage, ORG_UUID, UUID(cid), UUID(did), extractor=extractor)
        rows = _linhas(scoped)
        assert [r["campo"] for r in rows] == ["nome"]
        assert rows[0]["documento_id"] == did and rows[0]["tipo_documento"] == "cnh"
        # The extractor was offered the cliente's values from OTHER sources.
        assert extractor.confirmados == [{}]
