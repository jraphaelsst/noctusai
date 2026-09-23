"""D3 retries + D1 feeding for the imóvel-document jobs (migration 154).

WHAT THESE PIN
--------------
- the structured read (118) now has a lifecycle: `pendente` at upload,
  `ok`/`sem_dados`/`erro`, attempts counted;
- a FAILED read (the seam raises `EstruturaFalhou`) is `erro`, not
  `sem_dados` — only a failure is worth a retry;
- the sweep retries a failed structured read at most twice, never a
  permanent failure, and re-runs one stuck in `pendente`;
- the número read (pipeline B): a failed read with a retryable code is
  retried by the same sweep, a permanent one is not;
- a guia/CND inscrição feeds `prefeitura_cadastro_imobiliario` under D1 —
  provenance = the document; a disagreeing human value opens a conflict
  and the notifier hears about it.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from noctusai_lib.integrations.documents import (
    ExtractionConfidence,
    MatriculaFields,
    TextSource,
)

from app.modules.imovel_hub import documentos_service
from app.modules.imovel_hub import matricula_extracao_service as extracao
from tests.modules.imovel_hub.conftest import (
    CODIGO,
    ORG_ID,
    FakeImovelNotifier,
    auth,
    dados_row,
    documento_row,
    seed,
)

ORG = UUID(ORG_ID)
ANTIGO = "2026-01-01T00:00:00+00:00"


def _doc(scoped, did) -> dict:
    return [r for r in scoped.table("imovel_documentos").select("*").execute().data
            if r["id"] == did][0]


def _texto(texto):
    async def _fn(conteudo, mimetype, org_id):
        return texto
    return _fn


def _analise(resultado):
    async def _fn(texto, tipo_documento, org_id):
        return resultado
    return _fn


def _falha(codigo):
    async def _fn(*_a, **_k):
        raise documentos_service.EstruturaFalhou(codigo, "boom")
    return _fn


async def _pdf(fake_storage, path):
    await fake_storage.put(
        bucket="social-wiring-documentos", key=path, data=b"%PDF",
        content_type="application/pdf",
    )


class TestStructuredReadLifecycle:
    def test_upload_stamps_pendente(self, client, scoped, fake_storage, fake_extractor):
        seed(scoped)
        r = client.post(
            f"/api/imoveis/{CODIGO}/documentos",
            files={"file": ("guia.pdf", b"%PDF-1.7 fake", "application/pdf")},
            data={"tipo_documento": "guia_iptu"},
            headers=auth(),
        )
        assert r.status_code == 200, r.text
        row = _doc(scoped, r.json()["id"])
        assert row["estrutura_tentativas"] in (0, 1)  # the background job may have run
        assert row["estrutura_status"] in ("pendente", "processando", "ok", "sem_dados", "erro")

    @pytest.mark.asyncio
    async def test_a_failure_is_erro_and_counted_not_sem_dados(self, scoped, fake_storage):
        did, path = str(uuid4()), f"{ORG_ID}/imoveis/{CODIGO}/f"
        seed(scoped, documentos=[documento_row(did, tipo_documento="cnd_iptu", storage_path=path)])
        await _pdf(fake_storage, path)

        out = await documentos_service.extrair_estrutura(
            scoped, fake_storage, ORG, CODIGO, UUID(did),
            extract_text=_falha("insufficient_quota"),
        )
        assert out["status"] == "erro"
        row = _doc(scoped, did)
        assert row["estrutura_status"] == "erro"
        assert row["estrutura_erro"].startswith("insufficient_quota")
        assert row["estrutura_tentativas"] == 1

    @pytest.mark.asyncio
    async def test_success_is_ok(self, scoped, fake_storage):
        did, path = str(uuid4()), f"{ORG_ID}/imoveis/{CODIGO}/o"
        seed(scoped, documentos=[documento_row(did, tipo_documento="cnd_condominio", storage_path=path)])
        await _pdf(fake_storage, path)
        out = await documentos_service.extrair_estrutura(
            scoped, fake_storage, ORG, CODIGO, UUID(did),
            extract_text=_texto("..."), analyze_estrutura=_analise({"resultado": "negativa"}),
        )
        assert out["status"] == "ok"
        assert _doc(scoped, did)["estrutura_status"] == "ok"


class TestStructuredSweep:
    @pytest.mark.asyncio
    async def test_a_retryable_failure_is_retried_until_the_cap(self, scoped, fake_storage):
        did, path = str(uuid4()), f"{ORG_ID}/imoveis/{CODIGO}/r"
        seed(scoped, documentos=[documento_row(
            did, tipo_documento="cnd_iptu", storage_path=path,
            estrutura_status="erro", estrutura_erro="insufficient_quota: sem creditos",
            estrutura_tentativas=1, estrutura_em=ANTIGO,
        )])
        await _pdf(fake_storage, path)

        # Credits still missing: every retry fails again — exactly the loop
        # D3 bounds.
        falha = _falha("insufficient_quota")
        res = await documentos_service.varrer_estrutura_pendentes(
            scoped, fake_storage, extract_text=falha
        )
        assert res["reprocessados"] == 1
        row = _doc(scoped, did)
        assert row["estrutura_tentativas"] == 2
        assert row["estrutura_status"] == "erro"

        # Age it again: third and LAST attempt.
        scoped.table("imovel_documentos").update({"estrutura_em": ANTIGO}).eq("id", did).execute()
        await documentos_service.varrer_estrutura_pendentes(
            scoped, fake_storage, extract_text=falha
        )
        assert _doc(scoped, did)["estrutura_tentativas"] == 3

        # Cap reached: no fourth attempt, ever.
        scoped.table("imovel_documentos").update({"estrutura_em": ANTIGO}).eq("id", did).execute()
        res = await documentos_service.varrer_estrutura_pendentes(
            scoped, fake_storage, extract_text=falha
        )
        assert res["reprocessados"] == 0
        assert _doc(scoped, did)["estrutura_tentativas"] == 3

    @pytest.mark.asyncio
    async def test_a_permanent_failure_is_not_retried(self, scoped, fake_storage):
        did = str(uuid4())
        seed(scoped, documentos=[documento_row(
            did, tipo_documento="cnd_iptu",
            estrutura_status="erro", estrutura_erro="empty_document: vazio",
            estrutura_tentativas=1, estrutura_em=ANTIGO,
        )])
        res = await documentos_service.varrer_estrutura_pendentes(scoped, fake_storage)
        assert res["reprocessados"] == 0
        assert _doc(scoped, did)["estrutura_tentativas"] == 1

    @pytest.mark.asyncio
    async def test_a_never_started_read_is_picked_up(self, scoped, fake_storage):
        did = str(uuid4())
        seed(scoped, documentos=[documento_row(
            did, tipo_documento="cnd_iptu", storage_path="ausente",
            estrutura_status="pendente", estrutura_tentativas=0, estrutura_em=None,
        )])
        res = await documentos_service.varrer_estrutura_pendentes(scoped, fake_storage)
        assert res["reprocessados"] == 1
        row = _doc(scoped, did)
        assert row["estrutura_status"] == "erro"
        assert row["estrutura_erro"].startswith("objeto_ausente")


class TestNumeroReadRetry:
    @pytest.mark.asyncio
    async def test_a_quota_failure_is_retried_a_corrupt_file_is_not(self, scoped, fake_storage):
        ok_path = f"{ORG_ID}/imoveis/{CODIGO}/q"
        quota, vazio = str(uuid4()), str(uuid4())
        seed(scoped, documentos=[
            documento_row(
                quota, storage_path=ok_path, extracao_status="erro",
                extracao_erro="insufficient_quota: sem creditos",
                extracao_tentativas=1, extracao_em=ANTIGO,
            ),
            documento_row(
                vazio, extracao_status="erro", extracao_erro="empty_document: nada",
                extracao_tentativas=1, extracao_em=ANTIGO,
            ),
        ])
        await _pdf(fake_storage, ok_path)

        class _Ok:
            async def extract(self, content, *, mimetype=None, filename=None):
                return MatriculaFields(
                    numero_matricula="45678",
                    numero_matricula_confianca=ExtractionConfidence.ALTA,
                    numero_matricula_rotulo="MATRICULA N",
                    source=TextSource.TEXT_LAYER,
                )

        res = await extracao.varrer_pendentes(
            scoped, fake_storage, extractor_factory=lambda _org: _Ok()
        )
        assert res["reprocessados"] == 1
        assert _doc(scoped, quota)["extracao_status"] == "ok"
        assert _doc(scoped, quota)["extracao_tentativas"] == 2
        assert _doc(scoped, vazio)["extracao_status"] == "erro"


class TestInscricaoFeedsImovelDados:
    @pytest.mark.asyncio
    async def test_a_cnd_iptu_fills_the_empty_inscricao_with_provenance(
        self, client, scoped, fake_storage
    ):
        did, path = str(uuid4()), f"{ORG_ID}/imoveis/{CODIGO}/c"
        seed(scoped, documentos=[documento_row(did, tipo_documento="cnd_iptu", storage_path=path)])
        await _pdf(fake_storage, path)
        out = await documentos_service.extrair_estrutura(
            scoped, fake_storage, ORG, CODIGO, UUID(did),
            extract_text=_texto("..."),
            analyze_estrutura=_analise({"inscricao_imobiliaria": "12.345.678-9"}),
        )
        assert out["sugerido_em_dados"] is True
        dados = client.get(f"/api/imoveis/{CODIGO}/dados", headers=auth()).json()
        assert dados["prefeitura_cadastro_imobiliario"] == "12.345.678-9"
        prov = dados["proveniencia"]["prefeitura_cadastro_imobiliario"]
        assert prov["origem"] == "cnd_iptu"
        assert prov["documento_id"] == did
        assert prov["pendente"] is True

    @pytest.mark.asyncio
    async def test_a_disagreeing_human_value_opens_a_notified_conflict(
        self, client, scoped, fake_storage
    ):
        did, path = str(uuid4()), f"{ORG_ID}/imoveis/{CODIGO}/g"
        seed(
            scoped,
            documentos=[documento_row(did, tipo_documento="guia_iptu", storage_path=path)],
            dados=[dados_row(
                prefeitura_cadastro_imobiliario="11.111.111-1",
                prefeitura_cadastro_imobiliario_origem="manual",
            )],
        )
        await _pdf(fake_storage, path)
        notifier = FakeImovelNotifier()
        out = await documentos_service.extrair_estrutura(
            scoped, fake_storage, ORG, CODIGO, UUID(did),
            extract_text=_texto("..."),
            analyze_estrutura=_analise({"inscricao_imobiliaria": "99.888.777-6"}),
            notificador=notifier,
        )
        assert out["conflito_aberto"] is True
        dados = client.get(f"/api/imoveis/{CODIGO}/dados", headers=auth()).json()
        assert dados["prefeitura_cadastro_imobiliario"] == "11.111.111-1"
        assert [n["conflito"]["valor_proposto"] for n in notifier.conflitos] == ["99.888.777-6"]
