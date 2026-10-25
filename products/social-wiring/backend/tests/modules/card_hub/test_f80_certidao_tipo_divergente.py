"""F80 (prod, 2026-10-24) — a certidão de NASCIMENTO filed as
`certidao_casamento` wrote `estado_civil='casado'` (origem
certidao_casamento) onto the party, and deleting the document left it there.

End to end through the REAL seed extractor (`LadderIdentityExtractor`, its
vision rung a DI stub returning synthetic OCR-shaped text) and the product's
`extrair_identidade` apply step; the delete through the mounted route.
Every name/number below is invented.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.modules.card_hub import identidade_extracao_service as svc
from noctusai_lib.integrations.documents import AVISO_TIPO_DOCUMENTO_DIVERGENTE
from noctusai_lib.integrations.documents.real import LadderIdentityExtractor
from noctusai_lib.integrations.storage import FakeStorageBackend
from tests.modules.card_hub.conftest import ORG_ID, cliente_row, documento_row

BUCKET = "social-wiring-documentos"
ORG_UUID = UUID(ORG_ID)
NOME = "CARLOS EDUARDO FICTICIO SANTOS"

NASCIMENTO_OCR = f"""
REPUBLICA FEDERATIVA DO BRASIL
REGISTRO CIVIL DAS PESSOAS NATURAIS
CERTIDÃO DE NASCIMENTO
NOME
{NOME}
DATA DE NASCIMENTO
DOZE DE MARÇO DE MIL NOVECENTOS E OITENTA   12/03/1980
SEXO
MASCULINO
AVERBAÇÕES/ANOTAÇÕES À ACRESCER
À MARGEM DO TERMO NADA CONSTA
São Paulo, 15 de abril de 2009
"""

CASAMENTO_SO_TITULAR_OCR = f"""
REPUBLICA FEDERATIVA DO BRASIL
REGISTRO CIVIL DAS PESSOAS NATURAIS
CERTIDÃO DE CASAMENTO
NOMES
{NOME}
CPF
529.982.247-25
"""

CASAMENTO_COMPLETO_OCR = f"""
REPUBLICA FEDERATIVA DO BRASIL
REGISTRO CIVIL DAS PESSOAS NATURAIS
CERTIDÃO DE CASAMENTO
NOMES
{NOME}
CPF
529.982.247-25
ANA PAULA FICTICIA LIMA
CPF
111.444.777-35
DATA DE REGISTRO DO CASAMENTO POR EXTENSO
DEZ DE JUNHO DE DOIS MIL E DEZ
DIA
10
MÊS
06
ANO
2010
AVERBAÇÕES/ANOTAÇÕES À ACRESCER
NADA CONSTA
"""


class _StubResolved:
    def __init__(self, text: str):
        self.text, self.error, self.error_message = text, None, None


class _StubResolver:
    """DI stand-in for the seed ladder's vision rung (never a patch)."""

    def __init__(self, text: str):
        self._resolved = _StubResolved(text)

    async def resolve(self, media):
        return self._resolved


async def _setup(scoped, *, tipo="certidao_casamento", cliente=None):
    cid, did = str(uuid4()), str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid, nome=NOME, **(cliente or {}))])
    path = f"{ORG_ID}/clientes/{cid}/{did}"
    scoped.set_table_data("cliente_documentos", [{
        "id": did, "org_id": ORG_ID, "cliente_id": cid,
        "storage_path": path, "nome_original": "certidao_casamento.jpg",
        "mime_type": "image/jpeg", "tipo_documento": tipo,
        "deleted_at": None, "extracao_status": "pendente",
        "extracao_tentativas": 0, "extracao_descartada_em": None,
        "created_at": "2026-10-01T00:00:00+00:00",
    }])
    scoped.set_table_data("cliente_documento_acessos", [])
    scoped.set_table_data("cliente_campo_conflitos", [])
    storage = FakeStorageBackend()
    await storage.put(bucket=BUCKET, key=path, data=b"\xff\xd8\xff\xe0jpeg", content_type="image/jpeg")
    return cid, did, storage


async def _extrair(scoped, storage, cid, did, texto):
    return await svc.extrair_identidade(
        scoped, storage, ORG_UUID, UUID(cid), UUID(did),
        extractor=LadderIdentityExtractor(resolver=_StubResolver(texto)),
    )


def _row(scoped, table, id_) -> dict:
    return next(r for r in scoped.table(table).select("*").execute().data if r["id"] == id_)


class TestNascimentoFiledAsCasamento:
    @pytest.mark.asyncio
    async def test_flagged_never_casado_nothing_applied(self, client, scoped):
        cid, did, storage = await _setup(scoped)
        await _extrair(scoped, storage, cid, did, NASCIMENTO_OCR)

        cliente = _row(scoped, "clientes", cid)
        assert cliente.get("estado_civil") is None
        assert cliente.get("estado_civil_origem") is None
        # A misfiled document applies nothing unattended — every reading
        # waits on the row for the operator who re-files it.
        assert cliente.get("data_nascimento") is None

        doc = _row(scoped, "cliente_documentos", did)
        assert AVISO_TIPO_DOCUMENTO_DIVERGENTE in (doc["extracao_aviso"] or "").split("+")
        assert "reenvie com o tipo certo" in doc["extracao_aviso_mensagem"]
        assert doc["extracao_estado_civil"] != "casado"
        # Read as the birth certificate it is; the emission date rides on the
        # row. F103: issued in 2009 => older than the estado-civil window, so
        # NO solteiro suggestion (an old certidão proves nothing current).
        assert doc["extracao_estado_civil"] is None
        assert doc["extracao_data_emissao"].startswith("2009")


class TestCasadoWithoutTheMarriageRead:
    @pytest.mark.asyncio
    async def test_one_spouse_no_core_is_a_suggestion_not_applied(self, client, scoped):
        cid, did, storage = await _setup(scoped)
        await _extrair(scoped, storage, cid, did, CASAMENTO_SO_TITULAR_OCR)

        assert _row(scoped, "clientes", cid).get("estado_civil") is None
        doc = _row(scoped, "cliente_documentos", did)
        assert doc["extracao_estado_civil"] == "casado"
        assert doc["extracao_estado_civil_confianca"] != "alta"
        sug = svc.sugestoes_pendentes(scoped, ORG_UUID, UUID(cid))
        assert sug["estado_civil"]["valor"] == "casado"

    @pytest.mark.asyncio
    async def test_a_real_casamento_still_applies_casado(self, client, scoped):
        cid, did, storage = await _setup(scoped)
        await _extrair(scoped, storage, cid, did, CASAMENTO_COMPLETO_OCR)

        cliente = _row(scoped, "clientes", cid)
        assert cliente["estado_civil"] == "casado"
        assert cliente["estado_civil_origem"] == "certidao_casamento"
        assert cliente["estado_civil_documento_id"] == did


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


class TestDeletingTheDocumentRevertsWhatItApplied:
    def _seed(self, scoped, *, confirmado_em=None, outro_doc=None):
        cid, did = str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(
            cid,
            estado_civil="casado",
            estado_civil_origem="certidao_casamento",
            estado_civil_documento_id=did,
            estado_civil_em="2026-10-24T00:00:00+00:00",
            estado_civil_confirmado_em=confirmado_em,
        )])
        docs = [documento_row(
            did, cid, tipo_documento="certidao_casamento",
            extracao_estado_civil="casado", extracao_descartada_em=None,
        )]
        if outro_doc:
            docs.append(documento_row(str(uuid4()), cid, extracao_descartada_em=None, **outro_doc))
        scoped.set_table_data("cliente_documentos", docs)
        scoped.set_table_data("cliente_documento_acessos", [])
        return cid, did

    def test_delete_route_clears_the_machine_value(self, client, scoped, fake_storage):
        cid, did = self._seed(scoped)
        resp = client.delete(f"/api/clientes/{cid}/documentos/{did}?motivo=tipo%20errado", headers=_auth())
        assert resp.status_code == 204
        cliente = _row(scoped, "clientes", cid)
        assert cliente["estado_civil"] is None
        assert cliente["estado_civil_origem"] is None
        assert cliente["estado_civil_documento_id"] is None

    def test_a_human_confirmed_value_is_kept(self, client, scoped, fake_storage):
        cid, did = self._seed(scoped, confirmado_em="2026-10-24T01:00:00+00:00")
        client.delete(f"/api/clientes/{cid}/documentos/{did}?motivo=x", headers=_auth())
        assert _row(scoped, "clientes", cid)["estado_civil"] == "casado"

    def test_another_live_document_with_the_same_value_keeps_it(self, client, scoped, fake_storage):
        cid, did = self._seed(scoped, outro_doc={
            "tipo_documento": "certidao_casamento", "extracao_estado_civil": "casado",
        })
        client.delete(f"/api/clientes/{cid}/documentos/{did}?motivo=x", headers=_auth())
        cliente = _row(scoped, "clientes", cid)
        assert cliente["estado_civil"] == "casado"
        assert cliente["estado_civil_documento_id"] != did

    def test_the_deleted_documents_suggestions_disappear(self, client, scoped, fake_storage):
        """F81 — a soft-deleted row never feeds a pending suggestion."""
        cid, did = str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data("cliente_documentos", [documento_row(
            did, cid, tipo_documento="certidao_casamento",
            extracao_genero="masculino", extracao_estado_civil="casado",
            extracao_descartada_em=None, extracao_em="2026-10-24T00:00:00+00:00",
        )])
        scoped.set_table_data("cliente_documento_acessos", [])
        assert "genero" in svc.sugestoes_pendentes(scoped, ORG_UUID, UUID(cid))
        client.delete(f"/api/clientes/{cid}/documentos/{did}?motivo=x", headers=_auth())
        sug = svc.sugestoes_pendentes(scoped, ORG_UUID, UUID(cid))
        assert "genero" not in sug and "estado_civil" not in sug
