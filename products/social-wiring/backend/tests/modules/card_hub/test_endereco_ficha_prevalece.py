"""Ficha prevalece — the residential-address precedence (owner decision,
2026-10-13).

WHAT THESE PIN
--------------
The ficha cadastral (filled in by the client) is the AUTHORITATIVE source
for a party's residential address; a comprovante only CONFIRMS it (CEP and
cidade/UF must match). Real case: a seller in a gated condominium whose
Enel bill is addressed to the condominium gate ("Rua Gal. Fernando V.
Cavalcanti Albuquerque, 1135, Bosque do Viana") with the same CEP 06711-020
as her ficha ("Al. Liverpool, 81, Reserva do Vianna") — the address in the
signed contract.

1. Same CEP + cidade, different street -> the ficha's address is kept, NO
   pending conflict, the comprovante's document row carries the
   corroboration note (also when the bill is in the condominium's name).
2. A comprovante on file, the ficha arriving later with the same CEP ->
   the ficha's address replaces it.
3. Different CEP -> a real divergence: the normal pending conflict, never
   an automatic pick.
4. No ficha -> the comprovante is the source, as before.
5. A manual / human-confirmed value is never touched.
6. The backfill settles a pre-rule pending conflict the same way.

Exercised through `extrair_identidade` (the live pipeline) with the seed's
`FakeIdentityExtractor` injected — DI, never a monkeypatch.
"""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.modules.card_hub import identidade_extracao_service as svc
from noctusai_lib.integrations.documents import (
    EnderecoLido,
    ExtractionConfidence,
    FakeIdentityExtractor,
    IdentityFields,
)
from noctusai_lib.integrations.documents.types import TextSource
from noctusai_lib.integrations.storage import FakeStorageBackend
from tests.modules.card_hub.conftest import ORG_ID, cliente_row

BUCKET = "social-wiring-documentos"
ORG_UUID = UUID(ORG_ID)
A = ExtractionConfidence.ALTA

#: The ficha's address — what the signed contract carries.
FICHA = {
    "endereco_cep": "06711-020", "endereco_logradouro": "AL. LIVERPOOL",
    "endereco_numero": "81", "endereco_complemento": None,
    "endereco_bairro": "RESERVA DO VIANNA", "endereco_cidade": "COTIA",
    "endereco_uf": "SP", "endereco_origem": "ficha_cadastral",
}

#: The Enel bill — addressed to the condominium gate, same CEP.
PORTARIA = EnderecoLido(
    cep="06711-020", logradouro="RUA GAL. FERNANDO V. CAVALCANTI ALBUQUERQUE",
    numero="1135", complemento=None, bairro="BOSQUE DO VIANA",
    cidade="COTIA", uf="SP", titular="MARIA HELENA ROCHA",
    confianca="alta", rotulo="ENDERECO",
)


def _old(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


async def _setup(scoped, *, cliente: dict, extra_docs=()):
    cid, did = str(uuid4()), str(uuid4())
    scoped.set_table_data(
        "clientes", [cliente_row(cid, nome="Maria Helena Rocha", **cliente)]
    )
    path = f"{ORG_ID}/clientes/{cid}/{did}"
    scoped.set_table_data("cliente_documentos", [{
        "id": did, "org_id": ORG_ID, "cliente_id": cid,
        "storage_path": path, "nome_original": "enel.pdf",
        "mime_type": "application/pdf", "tipo_documento": "comprovante_endereco",
        "deleted_at": None, "extracao_status": "pendente",
        "extracao_tentativas": 0, "created_at": _old(1),
    }, *extra_docs])
    scoped.set_table_data("cliente_documento_acessos", [])
    scoped.set_table_data("cliente_campo_conflitos", [])
    storage = FakeStorageBackend()
    await storage.put(bucket=BUCKET, key=path, data=b"%PDF-1.4", content_type="application/pdf")
    return cid, did, storage


async def _extrair(scoped, storage, cid, did, endereco=PORTARIA):
    fields = IdentityFields(endereco=endereco, source=TextSource.TEXT_LAYER)
    return await svc.extrair_identidade(
        scoped, storage, ORG_UUID, UUID(cid), UUID(did),
        extractor=FakeIdentityExtractor(fields),
    )


def _cliente(scoped, cid) -> dict:
    return next(r for r in scoped.table("clientes").select("*").execute().data if r["id"] == cid)


def _documento(scoped, did) -> dict:
    return next(
        r for r in scoped.table("cliente_documentos").select("*").execute().data if r["id"] == did
    )


def _conflitos(scoped, status: str | None = None) -> list[dict]:
    rows = scoped.table("cliente_campo_conflitos").select("*").execute().data
    return [r for r in rows if status is None or r.get("status") == status]


def _endereco_de(row: dict) -> tuple:
    return (row["endereco_cep"], row["endereco_logradouro"], row["endereco_numero"],
            row["endereco_bairro"], row["endereco_origem"])


FICHA_TUPLA = ("06711-020", "AL. LIVERPOOL", "81", "RESERVA DO VIANNA", "ficha_cadastral")


class TestComprovanteConfirmaFicha:
    @pytest.mark.asyncio
    async def test_the_real_case_keeps_the_ficha_and_opens_no_conflict(self, client, scoped):
        cid, did, storage = await _setup(scoped, cliente=FICHA)
        out = await _extrair(scoped, storage, cid, did)
        assert out["aplicado_ao_cliente"]["endereco"] is False
        assert _endereco_de(_cliente(scoped, cid)) == FICHA_TUPLA
        assert _conflitos(scoped, "pendente") == []
        # Recorded as corroboration: the audit row names the rule …
        [auditoria] = _conflitos(scoped)
        assert auditoria["status"] == "resolvido_automatico"
        assert auditoria["motivo_resolucao"].startswith(f"[{svc.REGRA_FICHA_PREVALECE}]")
        # … and the note stays on the comprovante's own document row.
        doc = _documento(scoped, did)
        assert svc.AVISO_COMPROVANTE_CONFIRMA_FICHA in doc["extracao_aviso"].split("+")
        assert svc.MENSAGEM_COMPROVANTE_CONFIRMA_FICHA in doc["extracao_aviso_mensagem"]
        # Not a review item: nothing offered for substitution.
        assert "endereco" not in svc.sugestoes_pendentes(scoped, ORG_UUID, UUID(cid))

    @pytest.mark.asyncio
    async def test_a_bill_in_the_condominiums_name_is_a_note_not_a_suggestion(
        self, client, scoped
    ):
        cid, did, storage = await _setup(scoped, cliente=FICHA)
        condominio = replace(PORTARIA, titular="CONDOMINIO RESERVA DO VIANNA")
        await _extrair(scoped, storage, cid, did, condominio)
        assert _endereco_de(_cliente(scoped, cid)) == FICHA_TUPLA
        assert _conflitos(scoped, "pendente") == []
        aviso = _documento(scoped, did)["extracao_aviso"].split("+")
        assert svc.AVISO_COMPROVANTE_CONFIRMA_FICHA in aviso
        assert svc.AVISO_TITULAR_NAO_CONFERE not in aviso
        assert "endereco" not in svc.sugestoes_pendentes(scoped, ORG_UUID, UUID(cid))

    def test_a_ficha_arriving_after_the_comprovante_replaces_it(self, client, scoped):
        cid, doc_comprovante, doc_ficha = str(uuid4()), str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(
            cid, nome="Maria Helena Rocha",
            endereco_cep="06711-020",
            endereco_logradouro="RUA GAL. FERNANDO V. CAVALCANTI ALBUQUERQUE",
            endereco_numero="1135", endereco_bairro="BOSQUE DO VIANA",
            endereco_cidade="COTIA", endereco_uf="SP",
            endereco_origem="comprovante_endereco", endereco_documento_id=doc_comprovante,
        )])
        scoped.set_table_data("cliente_documentos", [])
        scoped.set_table_data("cliente_campo_conflitos", [])
        aplicado, conflito = svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "ficha_cadastral",
            {"cep": "06711-020", "logradouro": "AL. LIVERPOOL", "numero": "81",
             "complemento": None, "bairro": "RESERVA DO VIANNA",
             "cidade": "COTIA", "uf": "SP"},
            confianca="alta", documento_id=UUID(doc_ficha),
        )
        assert (aplicado, conflito) == (True, None)
        row = _cliente(scoped, cid)
        assert _endereco_de(row) == FICHA_TUPLA
        assert row["endereco_documento_id"] == doc_ficha
        assert _conflitos(scoped, "pendente") == []


class TestDivergenciaReal:
    @pytest.mark.asyncio
    async def test_a_different_cep_opens_the_normal_conflict(self, client, scoped):
        cid, did, storage = await _setup(scoped, cliente=FICHA)
        outro_cep = replace(PORTARIA, cep="06700-000")
        out = await _extrair(scoped, storage, cid, did, outro_cep)
        assert out["aplicado_ao_cliente"]["endereco"] is False
        assert _endereco_de(_cliente(scoped, cid)) == FICHA_TUPLA
        [pendente] = _conflitos(scoped, "pendente")
        assert pendente["campo"] == "endereco"
        assert pendente["origem_anterior"] == "ficha_cadastral"
        assert pendente["origem_proposto"] == "comprovante_endereco"
        assert json.loads(pendente["valor_proposto"])["cep"] == "06700-000"
        aviso = _documento(scoped, did).get("extracao_aviso") or ""
        assert svc.AVISO_COMPROVANTE_CONFIRMA_FICHA not in aviso.split("+")

    @pytest.mark.asyncio
    async def test_a_different_cidade_opens_the_normal_conflict(self, client, scoped):
        cid, did, storage = await _setup(scoped, cliente=FICHA)
        outra_cidade = replace(PORTARIA, cidade="CARAPICUIBA")
        await _extrair(scoped, storage, cid, did, outra_cidade)
        assert _endereco_de(_cliente(scoped, cid)) == FICHA_TUPLA
        assert len(_conflitos(scoped, "pendente")) == 1


class TestSemFicha:
    @pytest.mark.asyncio
    async def test_without_a_ficha_the_comprovante_is_the_source(self, client, scoped):
        cid, did, storage = await _setup(scoped, cliente={})
        out = await _extrair(scoped, storage, cid, did)
        assert out["aplicado_ao_cliente"]["endereco"] is True
        row = _cliente(scoped, cid)
        assert row["endereco_logradouro"] == "RUA GAL. FERNANDO V. CAVALCANTI ALBUQUERQUE"
        assert row["endereco_origem"] == "comprovante_endereco"
        assert row["endereco_documento_id"] == did
        assert _conflitos(scoped) == []


class TestValorHumano:
    @pytest.mark.asyncio
    async def test_a_manual_value_is_never_touched(self, client, scoped):
        cid, did, storage = await _setup(scoped, cliente={**FICHA, "endereco_origem": "manual"})
        await _extrair(scoped, storage, cid, did)
        row = _cliente(scoped, cid)
        assert row["endereco_logradouro"] == "AL. LIVERPOOL"
        assert row["endereco_origem"] == "manual"
        # The ficha rule never decides against a human — a human does.
        [pendente] = _conflitos(scoped)
        assert pendente["status"] == "pendente"

    @pytest.mark.asyncio
    async def test_a_confirmed_comprovante_is_never_replaced_by_a_later_ficha(self, client, scoped):
        """A comprovante on file that a HUMAN confirmed is not replaced by a
        later ficha either — the ficha opens a conflict instead."""
        cid, doc_ficha = str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(
            cid, nome="Maria Helena Rocha",
            endereco_cep="06711-020",
            endereco_logradouro="RUA GAL. FERNANDO V. CAVALCANTI ALBUQUERQUE",
            endereco_numero="1135", endereco_cidade="COTIA", endereco_uf="SP",
            endereco_origem="comprovante_endereco",
            endereco_confirmado_em="2026-10-01T00:00:00+00:00",
        )])
        scoped.set_table_data("cliente_documentos", [])
        scoped.set_table_data("cliente_campo_conflitos", [])
        aplicado, conflito = svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "ficha_cadastral",
            {"cep": "06711-020", "logradouro": "AL. LIVERPOOL", "numero": "81",
             "complemento": None, "bairro": None, "cidade": "COTIA", "uf": "SP"},
            confianca="alta", documento_id=UUID(doc_ficha),
        )
        assert aplicado is False and conflito is not None
        row = _cliente(scoped, cid)
        assert row["endereco_logradouro"] == "RUA GAL. FERNANDO V. CAVALCANTI ALBUQUERQUE"


class TestBackfill:
    def test_a_pre_rule_pending_conflict_settles_keeping_the_ficha(self, client, scoped):
        cid, doc_comprovante = str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Maria Helena Rocha", **FICHA)])
        scoped.set_table_data("cliente_documentos", [{
            "id": doc_comprovante, "org_id": ORG_ID, "cliente_id": cid,
            "tipo_documento": "comprovante_endereco", "deleted_at": None,
        }])
        scoped.set_table_data("cliente_campo_conflitos", [{
            "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": cid, "campo": "endereco",
            "valor_anterior": json.dumps({"cep": "06711-020", "logradouro": "AL. LIVERPOOL"}),
            "origem_anterior": "ficha_cadastral",
            "valor_proposto": json.dumps({
                "cep": "06711-020", "logradouro": PORTARIA.logradouro, "numero": "1135",
                "bairro": "BOSQUE DO VIANA", "cidade": "COTIA", "uf": "SP",
            }),
            "origem_proposto": "comprovante_endereco", "confianca_proposta": "alta",
            "fonte_tabela": svc.DOCUMENTOS_TABLE, "fonte_id": doc_comprovante,
            "status": "pendente", "notificado_em": None, "decidido_por": None,
            "decidido_em": None, "created_at": _old(60),
        }])
        out = svc.backfill_resolver_conflitos_pendentes(scoped, ORG_UUID)
        [resolvido] = out["resolvidos"]
        assert (resolvido["decisao_regra"], resolvido["decisao_vencedor"]) == (
            svc.REGRA_FICHA_PREVALECE, "atual",
        )
        assert _endereco_de(_cliente(scoped, cid)) == FICHA_TUPLA
        assert _conflitos(scoped, "pendente") == []


def test_cnh_estrangeiro_is_not_read_as_a_nationality():
    """876 real-doc scorecard (2026-10-13): a foreign national's CNH prints
    only "ESTRANGEIRO" — a category, never the contract's gentílico."""
    from noctusai_lib.integrations.documents.types import IdentityFields

    from app.modules.card_hub.identidade_extracao_service import _valores_lidos

    generico = IdentityFields(nacionalidade="estrangeiro", nacionalidade_confianca="alta")
    assert _valores_lidos(generico)["nacionalidade"][0] is None
    especifico = IdentityFields(nacionalidade="italiano", nacionalidade_confianca="alta")
    assert _valores_lidos(especifico)["nacionalidade"][0] == "italiano"
