"""Identity extraction feeds the contract — owner decisions D1/D3 (migration 153).

WHAT THESE PIN
--------------
1. **D1 fill-empty.** Any parsed value fills an EMPTY `clientes` field with
   provenance (`_origem` = tipo_documento, `_documento_id`, `_em`) and NO
   confirmation — machine-pending for the contract's validation gate.
2. **D1 never-overwrite + notify.** A value already there (human-typed OR an
   earlier extraction) that the reading contradicts opens a
   `cliente_campo_conflitos` row AND notifies an admin; the record is untouched.
   The same fact spelled differently (`m` vs `Masculino`, CPF punctuation) is
   NOT a contradiction.
3. **New fields**: rg_orgao_expedidor (own provenance, only beside its own RG),
   profissão, the endereço group from a comprovante (holder-checked), both
   spouses of a certidão de casamento (+ reciprocal cônjuge link).
4. **D3**: `erro` retried at most twice by the sweep; a never-started `pendente`
   (NULL `extracao_em`) is finally recovered.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.modules.card_hub import identidade_extracao_service as svc
from noctusai_lib.integrations.documents import (
    ConjugeLido,
    EnderecoLido,
    ExtractionConfidence,
    FakeIdentityExtractor,
    IdentityFields,
    TextSource,
)
from noctusai_lib.integrations.storage import FakeStorageBackend
from tests.modules.card_hub.conftest import (
    ORG_ID,
    cliente_row,
    documento_tipo_row,
    retencao_politica_row,
)
from tests.modules.matriculas.conftest import FakeNotificationService

BUCKET = "social-wiring-documentos"
ORG_UUID = UUID(ORG_ID)
A = ExtractionConfidence.ALTA
B = ExtractionConfidence.BAIXA


def _old(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


async def _setup(scoped, *, tipo="rg", cliente=None, outros=(), doc_extra=None):
    cid, did = str(uuid4()), str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid, **(cliente or {})), *outros])
    path = f"{ORG_ID}/clientes/{cid}/{did}"
    row = {
        "id": did, "org_id": ORG_ID, "cliente_id": cid,
        "storage_path": path, "nome_original": f"{tipo}.pdf",
        "mime_type": "application/pdf", "tipo_documento": tipo,
        "deleted_at": None, "extracao_status": "pendente",
        "extracao_tentativas": 0, "created_at": _old(1),
    }
    row.update(doc_extra or {})
    scoped.set_table_data("cliente_documentos", [row])
    scoped.set_table_data("cliente_documento_acessos", [])
    scoped.set_table_data("cliente_campo_conflitos", [])
    storage = FakeStorageBackend()
    await storage.put(bucket=BUCKET, key=path, data=b"%PDF-1.4", content_type="application/pdf")
    return cid, did, storage


def _cliente(scoped, cid) -> dict:
    return next(r for r in scoped.table("clientes").select("*").execute().data if r["id"] == cid)


def _documento(scoped, did) -> dict:
    return next(
        r for r in scoped.table("cliente_documentos").select("*").execute().data if r["id"] == did
    )


def _conflitos(scoped) -> list[dict]:
    return scoped.table("cliente_campo_conflitos").select("*").execute().data


async def _extrair(scoped, storage, cid, did, fields, notifier=None):
    return await svc.extrair_identidade(
        scoped, storage, ORG_UUID, UUID(cid), UUID(did),
        extractor=FakeIdentityExtractor(fields),
        notification_service=notifier,
    )


# ─── D1 ──────────────────────────────────────────────────────────────────────


class TestD1FillEmpty:
    @pytest.mark.asyncio
    async def test_every_read_field_fills_with_provenance_unconfirmed(self, client, scoped):
        cid, did, storage = await _setup(scoped)
        await _extrair(scoped, storage, cid, did, IdentityFields(
            cpf="412.954.238-98", cpf_confianca=B,
            rg="52.179.965-X", rg_confianca=B, rg_orgao="SSP/SP", rg_orgao_confianca=B,
            rg_rotulo="REGISTRO GERAL",
            profissao="engenheiro", profissao_confianca=A, profissao_rotulo="PROFISSAO",
            source=TextSource.OCR,
        ))
        row = _cliente(scoped, cid)
        for campo, valor in (
            ("cpf", "412.954.238-98"), ("rg", "52.179.965-X"),
            ("rg_orgao_expedidor", "SSP/SP"), ("profissao", "engenheiro"),
        ):
            assert row[campo] == valor
            assert row[f"{campo}_origem"] == "rg"
            assert row[f"{campo}_documento_id"] == did
            assert row[f"{campo}_em"] is not None
            assert row.get(f"{campo}_confirmado_em") is None
            assert row.get(f"{campo}_confirmado_por") is None
        doc = _documento(scoped, did)
        assert doc["extracao_rg_orgao"] == "SSP/SP"
        assert doc["extracao_rg_orgao_confianca"] == "baixa"
        assert doc["extracao_profissao"] == "engenheiro"


class TestD1NeverOverwrite:
    @pytest.mark.asyncio
    async def test_a_human_value_that_differs_opens_a_conflict_and_notifies(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, cliente={"nome": "Ana", "profissao": "médica", "profissao_origem": "manual"}
        )
        notifier = FakeNotificationService()
        out = await _extrair(scoped, storage, cid, did, IdentityFields(
            profissao="advogada", profissao_confianca=A, source=TextSource.TEXT_LAYER,
        ), notifier)
        assert _cliente(scoped, cid)["profissao"] == "médica"
        assert out["conflitos_abertos"] == ["profissao"]
        (c,) = _conflitos(scoped)
        assert (c["valor_anterior"], c["origem_anterior"], c["valor_proposto"]) == (
            "médica", "manual", "advogada",
        )
        assert (c["fonte_tabela"], c["fonte_id"]) == ("cliente_documentos", did)
        assert [n["conflito"]["campo"] for n in notifier.conflitos] == ["profissao"]
        assert notifier.conflitos[0]["cliente_nome"] == "Ana"
        assert c["notificado_em"] is not None

    @pytest.mark.asyncio
    async def test_an_earlier_machine_value_that_differs_is_also_a_conflict(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, cliente={"data_nascimento": "1979-01-01", "data_nascimento_origem": "cnh"}
        )
        notifier = FakeNotificationService()
        await _extrair(scoped, storage, cid, did, IdentityFields(
            data_nascimento=date(1980, 5, 12), data_nascimento_confianca=A,
            source=TextSource.TEXT_LAYER,
        ), notifier)
        assert _cliente(scoped, cid)["data_nascimento"] == "1979-01-01"
        assert [c["campo"] for c in _conflitos(scoped)] == ["data_nascimento"]
        assert len(notifier.conflitos) == 1

    @pytest.mark.asyncio
    async def test_the_same_fact_spelled_differently_is_not_a_conflict(self, client, scoped):
        cid, did, storage = await _setup(scoped, cliente={
            "genero": "m", "genero_origem": "matricula",
            "cpf": "41295423898", "cpf_origem": "manual",
            "nacionalidade": "brasileira", "nacionalidade_origem": "manual",
        })
        out = await _extrair(scoped, storage, cid, did, IdentityFields(
            genero="Masculino", genero_confianca=A,
            cpf="412.954.238-98", cpf_confianca=A,
            nacionalidade="brasileiro", nacionalidade_confianca=A,
            source=TextSource.TEXT_LAYER,
        ))
        assert out["conflitos_abertos"] == []
        assert _conflitos(scoped) == []

    @pytest.mark.asyncio
    async def test_a_conflict_is_not_raised_or_announced_twice(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, cliente={"profissao": "médica", "profissao_origem": "manual"}
        )
        notifier = FakeNotificationService()
        fields = IdentityFields(profissao="advogada", profissao_confianca=A)
        await _extrair(scoped, storage, cid, did, fields, notifier)
        await _extrair(scoped, storage, cid, did, fields, notifier)
        assert len(_conflitos(scoped)) == 1
        assert len(notifier.conflitos) == 1

    @pytest.mark.asyncio
    async def test_no_notifier_still_records_the_conflict(self, client, scoped, caplog):
        cid, did, storage = await _setup(
            scoped, cliente={"profissao": "médica", "profissao_origem": "manual"}
        )
        await _extrair(scoped, storage, cid, did, IdentityFields(
            profissao="advogada", profissao_confianca=A,
        ))
        assert len(_conflitos(scoped)) == 1
        assert "sem notification_service" in caplog.text


class TestSameDocumentReReadReplaces:
    """🔴 Regression (live deal, 2026-09-25): re-extracting a document
    whose earlier reading is STILL machine-pending must REFRESH the
    field instead of opening a conflict with itself — see
    `campo_conflitos.mesmo_documento_pendente`'s own docstring."""

    @pytest.mark.asyncio
    async def test_a_second_read_of_the_same_document_replaces_not_conflicts(
        self, client, scoped
    ):
        cid, did, storage = await _setup(scoped)
        await _extrair(scoped, storage, cid, did, IdentityFields(
            profissao="engenheiro civi", profissao_confianca=B,  # garbled first read
            source=TextSource.OCR,
        ))
        await _extrair(scoped, storage, cid, did, IdentityFields(
            profissao="engenheiro civil", profissao_confianca=A,
            source=TextSource.TEXT_LAYER,
        ))
        row = _cliente(scoped, cid)
        assert row["profissao"] == "engenheiro civil"
        assert row["profissao_documento_id"] == did
        assert _conflitos(scoped) == []

    @pytest.mark.asyncio
    async def test_a_confirmed_field_is_never_silently_replaced_off_the_same_document(
        self, client, scoped
    ):
        cid, did, storage = await _setup(scoped)
        await _extrair(scoped, storage, cid, did, IdentityFields(
            profissao="engenheiro", profissao_confianca=A, source=TextSource.TEXT_LAYER,
        ))
        scoped.table("clientes").update({
            "profissao_confirmado_por": str(uuid4()), "profissao_confirmado_em": _old(0),
        }).eq("id", cid).execute()

        await _extrair(scoped, storage, cid, did, IdentityFields(
            profissao="advogado", profissao_confianca=A, source=TextSource.TEXT_LAYER,
        ))
        row = _cliente(scoped, cid)
        assert row["profissao"] == "engenheiro"  # untouched
        assert [c["campo"] for c in _conflitos(scoped)] == ["profissao"]

    @pytest.mark.asyncio
    async def test_a_different_document_still_conflicts(self, client, scoped):
        cid, did, storage = await _setup(scoped)
        await _extrair(scoped, storage, cid, did, IdentityFields(
            profissao="engenheiro", profissao_confianca=A, source=TextSource.TEXT_LAYER,
        ))
        # A SECOND, DIFFERENT document disagreeing — must still conflict.
        did_outro = str(uuid4())
        path_outro = f"{ORG_ID}/clientes/{cid}/{did_outro}"
        scoped.table("cliente_documentos").insert({
            "id": did_outro, "org_id": ORG_ID, "cliente_id": cid,
            "storage_path": path_outro, "nome_original": "rg2.pdf",
            "mime_type": "application/pdf", "tipo_documento": "rg",
            "deleted_at": None, "extracao_status": "pendente",
            "extracao_tentativas": 0, "created_at": _old(1),
        }).execute()
        await storage.put(
            bucket=BUCKET, key=path_outro, data=b"%PDF-1.4", content_type="application/pdf",
        )
        await _extrair(scoped, storage, cid, did_outro, IdentityFields(
            profissao="advogado", profissao_confianca=A, source=TextSource.TEXT_LAYER,
        ))
        row = _cliente(scoped, cid)
        assert row["profissao"] == "engenheiro"  # untouched
        assert [c["campo"] for c in _conflitos(scoped)] == ["profissao"]


class TestRgOrgao:
    @pytest.mark.asyncio
    async def test_the_issuer_is_never_written_beside_a_different_rg(self, client, scoped):
        """The record holds another RG (the reading's RG becomes a conflict):
        an SSP/SP read beside a number that is NOT the one on file qualifies
        nobody."""
        cid, did, storage = await _setup(
            scoped, cliente={"rg": "11.111.111-1", "rg_origem": "manual"}
        )
        await _extrair(scoped, storage, cid, did, IdentityFields(
            rg="52.179.965-X", rg_confianca=A, rg_orgao="SSP/SP", rg_orgao_confianca=A,
        ))
        row = _cliente(scoped, cid)
        assert row.get("rg_orgao_expedidor") is None
        assert [c["campo"] for c in _conflitos(scoped)] == ["rg"]

    @pytest.mark.asyncio
    async def test_the_issuer_fills_beside_the_same_rg_already_on_file(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, cliente={"rg": "52179965x", "rg_origem": "manual"}
        )
        await _extrair(scoped, storage, cid, did, IdentityFields(
            rg="52.179.965-X", rg_confianca=A, rg_orgao="SSP/SP", rg_orgao_confianca=A,
        ))
        row = _cliente(scoped, cid)
        assert row["rg_orgao_expedidor"] == "SSP/SP"
        assert row["rg_orgao_expedidor_origem"] == "rg"
        assert _conflitos(scoped) == []

    @pytest.mark.asyncio
    async def test_confirming_an_rg_suggestion_carries_its_issuer(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, cliente={"rg": None, "rg_origem": "manual"}
        )
        await _extrair(scoped, storage, cid, did, IdentityFields(
            rg="52.179.965-X", rg_confianca=B, rg_orgao="SSP/SP", rg_orgao_confianca=B,
        ))
        user = uuid4()
        svc.confirmar_sugestao(scoped, ORG_UUID, UUID(cid), UUID(did), item_key="rg", user_id=user)
        row = _cliente(scoped, cid)
        assert (row["rg"], row["rg_orgao_expedidor"]) == ("52.179.965-X", "SSP/SP")
        assert row["rg_orgao_expedidor_confirmado_por"] == str(user)


# ─── endereço ───────────────────────────────────────────────────────────────

ENDERECO = EnderecoLido(
    cep="01454-011", logradouro="R PROF ARTUR RAMOS", numero="123", complemento="APTO 12",
    bairro="JARDIM PAULISTANO", cidade="SÃO PAULO", uf="SP",
    titular="ANA PAULA SOUZA", confianca="alta", rotulo="ENDERECO",
)


def _comprovante(endereco=ENDERECO) -> IdentityFields:
    # The bill also prints a name and a CPF — the HOLDER's, which must never
    # be applied as this cliente's identity.
    return IdentityFields(
        nome="ANA PAULA SOUZA", nome_confianca=A, cpf="412.954.238-98", cpf_confianca=A,
        endereco=endereco, source=TextSource.TEXT_LAYER,
    )


class TestEndereco:
    @pytest.mark.asyncio
    async def test_a_comprovante_in_the_clientes_name_fills_the_group(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco", cliente={"nome": "Ana Paula Souza"}
        )
        out = await _extrair(scoped, storage, cid, did, _comprovante())
        row = _cliente(scoped, cid)
        assert out["aplicado_ao_cliente"]["endereco"] is True
        assert (row["endereco_cep"], row["endereco_logradouro"], row["endereco_numero"]) == (
            "01454-011", "R PROF ARTUR RAMOS", "123",
        )
        assert (row["endereco_complemento"], row["endereco_bairro"]) == ("APTO 12", "JARDIM PAULISTANO")
        assert (row["endereco_cidade"], row["endereco_uf"]) == ("SÃO PAULO", "SP")
        assert row["endereco_origem"] == "comprovante_endereco"
        assert row["endereco_documento_id"] == did
        assert row.get("endereco_confirmado_em") is None
        # 🔴 address only: the bill's name/CPF never touch the identity.
        assert row.get("nome_oficial") is None and row.get("cpf") is None
        doc = _documento(scoped, did)
        assert doc["extracao_endereco_titular"] == "ANA PAULA SOUZA"
        assert doc["extracao_endereco_cep"] == "01454-011"

    @pytest.mark.asyncio
    async def test_a_comprovante_in_a_relatives_name_is_a_conflict_not_a_fill(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco", cliente={"nome": "Carlos Eduardo Lima"}
        )
        notifier = FakeNotificationService()
        await _extrair(scoped, storage, cid, did, _comprovante(), notifier)
        assert _cliente(scoped, cid).get("endereco_cep") is None
        (c,) = _conflitos(scoped)
        assert c["campo"] == "endereco"
        assert c["valor_anterior"] is None
        assert json.loads(c["valor_proposto"])["titular"] == "ANA PAULA SOUZA"
        assert len(notifier.conflitos) == 1

    @pytest.mark.asyncio
    async def test_a_different_address_on_file_is_a_conflict(self, client, scoped):
        cid, did, storage = await _setup(scoped, tipo="comprovante_endereco", cliente={
            "nome": "Ana Paula Souza", "endereco_cep": "04000-000",
            "endereco_logradouro": "RUA B", "endereco_origem": "manual",
        })
        await _extrair(scoped, storage, cid, did, _comprovante())
        assert _cliente(scoped, cid)["endereco_cep"] == "04000-000"
        (c,) = _conflitos(scoped)
        assert json.loads(c["valor_anterior"])["cep"] == "04000-000"

    @pytest.mark.asyncio
    async def test_the_same_address_spelled_differently_is_a_no_op(self, client, scoped):
        cid, did, storage = await _setup(scoped, tipo="comprovante_endereco", cliente={
            "nome": "Ana Paula Souza", "endereco_cep": "01454011",
            "endereco_logradouro": "r prof artur ramos", "endereco_numero": "123",
            "endereco_complemento": "apto 12", "endereco_bairro": "Jardim Paulistano",
            "endereco_cidade": "Sao Paulo", "endereco_uf": "sp", "endereco_origem": "manual",
        })
        await _extrair(scoped, storage, cid, did, _comprovante())
        assert _conflitos(scoped) == []
        assert _cliente(scoped, cid)["endereco_origem"] == "manual"

    @pytest.mark.asyncio
    async def test_a_partial_address_on_file_is_offered_the_complete_one(self, client, scoped):
        """The record holds a street + CEP someone typed; the bill agrees and
        also carries the número/bairro. Never merged into the human's group
        (one provenance per group) — offered to an admin as a conflict whose
        acceptance writes the complete address."""
        cid, did, storage = await _setup(scoped, tipo="comprovante_endereco", cliente={
            "nome": "Ana Paula Souza", "endereco_cep": "01454-011",
            "endereco_logradouro": "R PROF ARTUR RAMOS", "endereco_origem": "manual",
        })
        await _extrair(scoped, storage, cid, did, _comprovante())
        assert _cliente(scoped, cid).get("endereco_numero") is None
        assert [c["campo"] for c in _conflitos(scoped)] == ["endereco"]

    @pytest.mark.asyncio
    async def test_accepting_the_conflict_writes_the_group_with_provenance(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco", cliente={"nome": "Carlos Eduardo Lima"}
        )
        await _extrair(scoped, storage, cid, did, _comprovante())
        (c,) = _conflitos(scoped)
        admin = uuid4()
        svc.resolver_conflito(scoped, ORG_UUID, UUID(c["id"]), aceitar=True, decidido_por=admin)
        row = _cliente(scoped, cid)
        assert (row["endereco_cep"], row["endereco_uf"]) == ("01454-011", "SP")
        assert row["endereco_origem"] == "comprovante_endereco"
        assert row["endereco_documento_id"] == did
        assert row["endereco_confirmado_por"] == str(admin)

    @pytest.mark.asyncio
    async def test_a_human_cleared_address_is_offered_and_confirmable(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco",
            cliente={"nome": "Ana Paula Souza", "endereco_origem": "manual"},
        )
        await _extrair(scoped, storage, cid, did, _comprovante())
        assert _cliente(scoped, cid).get("endereco_cep") is None
        sug = svc.sugestoes_pendentes(scoped, ORG_UUID, UUID(cid))
        assert sug["endereco"]["valor"]["cep"] == "01454-011"
        svc.confirmar_sugestao(
            scoped, ORG_UUID, UUID(cid), UUID(did), item_key="endereco", user_id=uuid4()
        )
        row = _cliente(scoped, cid)
        assert row["endereco_cep"] == "01454-011"
        assert row["endereco_confirmado_em"] is not None

    @pytest.mark.asyncio
    async def test_an_identity_document_never_fills_the_address(self, client, scoped):
        cid, did, storage = await _setup(scoped, tipo="certidao_casamento")
        await _extrair(scoped, storage, cid, did, _comprovante())
        assert _cliente(scoped, cid).get("endereco_cep") is None

    @pytest.mark.asyncio
    async def test_a_second_read_of_the_same_comprovante_replaces_not_conflicts(
        self, client, scoped
    ):
        """🔴 Regression (live deal, 2026-09-25): the FIRST read of a
        comprovante is incomplete (no cidade/UF), the SAME document
        re-read later comes back complete — must REFRESH the group, not
        open a conflict with itself."""
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco", cliente={"nome": "Ana Paula Souza"}
        )
        incompleto = EnderecoLido(
            cep="01454-011", logradouro="R PROF ARTUR RAMOS", numero=None,
            complemento=None, bairro=None, cidade=None, uf=None,
            titular="ANA PAULA SOUZA", confianca="baixa", rotulo="ENDERECO",
        )
        await _extrair(scoped, storage, cid, did, _comprovante(incompleto))
        assert _cliente(scoped, cid).get("endereco_cidade") is None

        await _extrair(scoped, storage, cid, did, _comprovante(ENDERECO))  # SAME did, complete

        row = _cliente(scoped, cid)
        assert row["endereco_numero"] == "123"
        assert row["endereco_bairro"] == "JARDIM PAULISTANO"
        assert row["endereco_cidade"] == "SÃO PAULO"
        assert row["endereco_uf"] == "SP"
        assert row["endereco_documento_id"] == did
        assert _conflitos(scoped) == []

    @pytest.mark.asyncio
    async def test_a_confirmed_address_is_never_silently_replaced(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco", cliente={"nome": "Ana Paula Souza"}
        )
        scoped.table("clientes").update({
            "endereco_cep": "04000-000", "endereco_logradouro": "RUA B",
            "endereco_origem": "comprovante_endereco", "endereco_documento_id": did,
            "endereco_confirmado_em": _old(0), "endereco_confirmado_por": str(uuid4()),
        }).eq("id", cid).execute()

        await _extrair(scoped, storage, cid, did, _comprovante())

        row = _cliente(scoped, cid)
        assert row["endereco_cep"] == "04000-000"  # untouched
        assert [c["campo"] for c in _conflitos(scoped)] == ["endereco"]

    @pytest.mark.asyncio
    async def test_a_manually_typed_address_is_never_silently_replaced(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco", cliente={"nome": "Ana Paula Souza"}
        )
        scoped.table("clientes").update({
            "endereco_cep": "04000-000", "endereco_logradouro": "RUA B",
            "endereco_origem": "manual", "endereco_documento_id": did,
        }).eq("id", cid).execute()

        await _extrair(scoped, storage, cid, did, _comprovante())

        row = _cliente(scoped, cid)
        assert row["endereco_cep"] == "04000-000"  # untouched
        assert [c["campo"] for c in _conflitos(scoped)] == ["endereco"]


# ─── both spouses ──────────────────────────────────────────────────────────


def _certidao(titular_idx: int | None = 0) -> IdentityFields:
    almir = ConjugeLido(
        nome="ALMIR TEIXEIRA DA COSTA", cpf="303.102.653-55", cpf_confianca="alta",
        data_nascimento=date(1961, 10, 4), data_nascimento_confianca="baixa",
        nacionalidade="brasileiro", nacionalidade_confianca="alta",
        profissao="comerciante", profissao_confianca="alta",
        genero="Masculino", genero_confianca="baixa", titular=titular_idx == 0,
    )
    mariana = ConjugeLido(
        nome="MARIANA PELLEGRINI RANGEL", cpf="478.982.096-30", cpf_confianca="alta",
        data_nascimento=date(1964, 4, 20), data_nascimento_confianca="baixa",
        profissao="professora", profissao_confianca="alta",
        genero="Feminino", genero_confianca="baixa", titular=titular_idx == 1,
    )
    eu = (almir, mariana)[titular_idx] if titular_idx is not None else None
    return IdentityFields(
        nome=eu.nome if eu else None, nome_confianca=A if eu else ExtractionConfidence.NENHUMA,
        cpf=eu.cpf if eu else None, cpf_confianca=A if eu else ExtractionConfidence.NENHUMA,
        estado_civil="casado", estado_civil_confianca=A,
        regime_bens="comunhao_parcial", regime_bens_confianca=A,
        data_casamento=date(2011, 7, 30), data_casamento_confianca=A,
        conjuges=(almir, mariana),
        aviso=None if eu else "titulares_multiplos",
        source=TextSource.TEXT_LAYER,
    )


class TestDoisConjuges:
    @pytest.mark.asyncio
    async def test_the_linked_spouse_is_filled_and_both_links_set(self, client, scoped):
        esposa = str(uuid4())
        cid, did, storage = await _setup(
            scoped, tipo="certidao_casamento",
            cliente={"nome": "Almir", "conjuge_cliente_id": esposa, "conjuge_origem": "manual"},
            outros=[cliente_row(esposa, nome="Mariana Pellegrini Rangel")],
        )
        out = await _extrair(scoped, storage, cid, did, _certidao(0))
        eu, ela = _cliente(scoped, cid), _cliente(scoped, esposa)
        assert eu["cpf"] == "303.102.653-55"
        assert ela["cpf"] == "478.982.096-30"
        assert ela["nome_oficial"] == "MARIANA PELLEGRINI RANGEL"
        assert ela["profissao"] == "professora"
        assert ela["genero"] == "Feminino"
        assert ela["data_nascimento"] == "1964-04-20"
        assert ela["cpf_origem"] == "certidao_casamento"
        assert ela["cpf_documento_id"] == did
        # Shared couple facts go to BOTH.
        for p in (eu, ela):
            assert (p["estado_civil"], p["regime_bens"], p["data_casamento"]) == (
                "casado", "comunhao_parcial", "2011-07-30",
            )
        # Reciprocal link: hers was empty -> set with provenance.
        assert ela["conjuge_cliente_id"] == cid
        assert ela["conjuge_origem"] == "certidao_casamento"
        registro = _documento(scoped, did)["extracao_conjuges"]
        assert [(r["titular"], r["cliente_id"]) for r in registro] == [
            (True, cid), (False, esposa),
        ]
        assert out["conflitos_abertos"] == []

    @pytest.mark.asyncio
    async def test_a_card_party_matching_by_name_is_the_spouse(self, client, scoped):
        esposa, atd = str(uuid4()), str(uuid4())
        cid, did, storage = await _setup(
            scoped, tipo="certidao_casamento", cliente={"nome": "Almir"},
            outros=[cliente_row(esposa, nome="Mariana Pellegrini Rangel")],
        )
        scoped.set_table_data("atendimentos", [
            {"id": atd, "org_id": ORG_ID, "cliente_id": cid},
        ])
        scoped.set_table_data("atendimento_partes", [
            {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": atd,
             "cliente_id": esposa, "papel": "vendedor", "ordem": 0},
        ])
        await _extrair(scoped, storage, cid, did, _certidao(0))
        eu, ela = _cliente(scoped, cid), _cliente(scoped, esposa)
        assert ela["cpf"] == "478.982.096-30"
        assert (eu["conjuge_cliente_id"], ela["conjuge_cliente_id"]) == (esposa, cid)
        assert eu["conjuge_origem"] == "certidao_casamento"
        assert eu.get("conjuge_confirmado_em") is None

    @pytest.mark.asyncio
    async def test_no_matching_cliente_is_recorded_never_invented(self, client, scoped):
        cid, did, storage = await _setup(scoped, tipo="certidao_casamento", cliente={"nome": "Almir"})
        await _extrair(scoped, storage, cid, did, _certidao(0))
        assert len(scoped.table("clientes").select("*").execute().data) == 1
        registro = _documento(scoped, did)["extracao_conjuges"]
        assert registro[1]["nome"] == "MARIANA PELLEGRINI RANGEL"
        assert registro[1]["cliente_id"] is None
        assert _cliente(scoped, cid).get("conjuge_cliente_id") is None

    @pytest.mark.asyncio
    async def test_a_linked_spouse_who_is_not_on_the_certidao_is_not_filled(self, client, scoped):
        """A certidão from a PREVIOUS marriage must not fill the current
        spouse's record."""
        atual = str(uuid4())
        cid, did, storage = await _setup(
            scoped, tipo="certidao_casamento",
            cliente={"nome": "Almir", "conjuge_cliente_id": atual, "conjuge_origem": "manual"},
            outros=[cliente_row(atual, nome="Beatriz Nunes")],
        )
        await _extrair(scoped, storage, cid, did, _certidao(0))
        assert _cliente(scoped, atual).get("cpf") is None
        assert _documento(scoped, did)["extracao_conjuges"][1]["cliente_id"] is None

    @pytest.mark.asyncio
    async def test_a_different_existing_link_is_a_conflict(self, client, scoped):
        esposa, outra = str(uuid4()), str(uuid4())
        cid, did, storage = await _setup(
            scoped, tipo="certidao_casamento", cliente={"nome": "Almir"},
            outros=[
                cliente_row(esposa, nome="Mariana Pellegrini Rangel",
                            conjuge_cliente_id=outra, conjuge_origem="manual"),
                cliente_row(outra, nome="Terceiro"),
            ],
        )
        atd = str(uuid4())
        scoped.set_table_data("atendimentos", [{"id": atd, "org_id": ORG_ID, "cliente_id": cid}])
        scoped.set_table_data("atendimento_partes", [
            {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": atd,
             "cliente_id": esposa, "papel": "vendedor", "ordem": 0},
        ])
        await _extrair(scoped, storage, cid, did, _certidao(0))
        assert _cliente(scoped, esposa)["conjuge_cliente_id"] == outra
        assert _cliente(scoped, cid)["conjuge_cliente_id"] == esposa
        assert [c["campo"] for c in _conflitos(scoped)] == ["conjuge_cliente_id"]

    @pytest.mark.asyncio
    async def test_without_a_titular_the_couple_facts_still_land(self, client, scoped):
        cid, did, storage = await _setup(scoped, tipo="certidao_casamento")
        await _extrair(scoped, storage, cid, did, _certidao(None))
        row = _cliente(scoped, cid)
        assert row["estado_civil"] == "casado"
        assert row.get("cpf") is None
        assert all(r["cliente_id"] is None for r in _documento(scoped, did)["extracao_conjuges"])


# ─── D3: bounded retries + the NULL-extracao_em sweep hole ─────────────────


def _alta_nome() -> IdentityFields:
    return IdentityFields(nome="JOAO DA SILVA", nome_confianca=A, source=TextSource.TEXT_LAYER)


def _fabrica(_org, _tipo=None):
    return FakeIdentityExtractor(_alta_nome())


class TestSweepD3:
    @pytest.mark.asyncio
    async def test_a_never_started_pendente_with_null_extracao_em_is_recovered(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, doc_extra={"extracao_em": None, "created_at": _old(60)}
        )
        out = await svc.varrer_extracoes_pendentes(scoped, storage, extractor_factory=_fabrica)
        assert out["retomados"] == 1
        assert _documento(scoped, did)["extracao_status"] == "ok"

    @pytest.mark.asyncio
    async def test_a_just_uploaded_pendente_is_not_raced(self, client, scoped):
        _cid, _did, storage = await _setup(
            scoped, doc_extra={"extracao_em": None, "created_at": _old(1)}
        )
        out = await svc.varrer_extracoes_pendentes(scoped, storage, extractor_factory=_fabrica)
        assert out["encontrados"] == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tentativas", [1, 2])
    async def test_a_failed_extraction_is_retried_while_retries_remain(
        self, client, scoped, tentativas
    ):
        _cid, did, storage = await _setup(scoped, doc_extra={
            "extracao_status": "erro", "extracao_erro": "insufficient_quota: no credit",
            "extracao_em": _old(60), "extracao_tentativas": tentativas,
        })
        out = await svc.varrer_extracoes_pendentes(scoped, storage, extractor_factory=_fabrica)
        assert out["retomados"] == 1
        doc = _documento(scoped, did)
        assert doc["extracao_status"] == "ok"
        assert doc["extracao_tentativas"] == tentativas + 1

    @pytest.mark.asyncio
    async def test_after_two_retries_the_error_stays_for_a_human(self, client, scoped):
        _cid, did, storage = await _setup(scoped, doc_extra={
            "extracao_status": "erro", "extracao_erro": "insufficient_quota",
            "extracao_em": _old(600), "extracao_tentativas": svc.MAX_TENTATIVAS,
        })
        out = await svc.varrer_extracoes_pendentes(scoped, storage, extractor_factory=_fabrica)
        assert out["encontrados"] == 0
        assert _documento(scoped, did)["extracao_status"] == "erro"
        assert svc.MAX_RETENTATIVAS_ERRO == 2

    @pytest.mark.asyncio
    async def test_a_fresh_failure_is_not_retried_immediately(self, client, scoped):
        _cid, _did, storage = await _setup(scoped, doc_extra={
            "extracao_status": "erro", "extracao_em": _old(1), "extracao_tentativas": 1,
        })
        out = await svc.varrer_extracoes_pendentes(scoped, storage, extractor_factory=_fabrica)
        assert out["encontrados"] == 0

    @pytest.mark.asyncio
    async def test_a_retry_that_fails_again_stays_erro_and_counts(self, client, scoped):
        _cid, did, storage = await _setup(scoped, doc_extra={
            "extracao_status": "erro", "extracao_em": _old(60), "extracao_tentativas": 1,
        })
        falha = IdentityFields(error="insufficient_quota", error_message="no credit")
        out = await svc.varrer_extracoes_pendentes(
            scoped, storage, extractor_factory=lambda _o, _t=None: FakeIdentityExtractor(falha),
        )
        assert out["retomados"] == 1
        doc = _documento(scoped, did)
        assert (doc["extracao_status"], doc["extracao_tentativas"]) == ("erro", 2)


# ─── the upload route wires the notifier ─────────────────────────────────────


class TestUploadRouteNotifies:
    def test_a_conflict_from_an_upload_reaches_the_admin_notifier(
        self, client, scoped, fake_storage
    ):
        from app.main import app
        from app.modules.card_hub.deps import (
            get_conflict_notification_service,
            get_identity_extractor_factory,
        )

        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(
            cid, nome="Ana", profissao="médica", profissao_origem="manual",
        )])
        scoped.set_table_data("cliente_documentos", [])
        scoped.set_table_data("cliente_documento_acessos", [])
        scoped.set_table_data("cliente_campo_conflitos", [])
        scoped.set_table_data(
            "cliente_documento_tipos", [documento_tipo_row("certidao_casamento")]
        )
        scoped.set_table_data(
            "documento_retencao_politicas", [retencao_politica_row("certidao_casamento")]
        )
        notifier = FakeNotificationService()
        extractor = FakeIdentityExtractor(
            IdentityFields(profissao="advogada", profissao_confianca=A)
        )
        app.dependency_overrides[get_conflict_notification_service] = lambda: notifier
        app.dependency_overrides[get_identity_extractor_factory] = (
            lambda: (lambda org_id, tipo_documento=None: extractor)
        )
        try:
            resp = client.post(
                f"/api/clientes/{cid}/documentos",
                files={"file": ("certidao.pdf", b"%PDF-1.4", "application/pdf")},
                data={"tipo_documento": "certidao_casamento"},
                headers={"Authorization": "Bearer test-token"},
            )
        finally:
            app.dependency_overrides.pop(get_conflict_notification_service, None)
            app.dependency_overrides.pop(get_identity_extractor_factory, None)
        assert resp.status_code == 201, resp.text
        assert [n["conflito"]["campo"] for n in notifier.conflitos] == ["profissao"]
