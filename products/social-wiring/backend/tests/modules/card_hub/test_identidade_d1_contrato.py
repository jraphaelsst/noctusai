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


# ─── Automatic divergence resolution (owner directive, 2026-09-29) ─────────


class TestResolucaoAutomaticaDeDivergencia:
    @pytest.mark.asyncio
    async def test_a_higher_tier_source_wins_with_no_human_conflict(self, client, scoped):
        """cnh (100%, n=19) outranks certidao_casamento (67%, n=3) for cpf —
        the record is updated straight through, no `pendente` row, and the
        automatic decision is still written back auditable."""
        cid, did, storage = await _setup(
            scoped, tipo="cnh",
            cliente={"cpf": "303.102.653-55", "cpf_origem": "certidao_casamento"},
        )
        out = await _extrair(scoped, storage, cid, did, IdentityFields(
            cpf="412.954.238-98", cpf_confianca=A, source=TextSource.TEXT_LAYER,
        ))
        assert _cliente(scoped, cid)["cpf"] == "412.954.238-98"
        assert _cliente(scoped, cid)["cpf_origem"] == "cnh"
        assert out["conflitos_abertos"] == []
        (c,) = _conflitos(scoped)
        assert c["status"] == "resolvido_automatico"
        assert c["decidido_por"] is None
        assert "[tier]" in c["motivo_resolucao"]

    @pytest.mark.asyncio
    async def test_a_same_tier_disagreement_still_needs_a_human(self, client, scoped):
        """cnh and matricula are BOTH measured at 100% for `nacionalidade` —
        no validator, no corroboration, no tier separation: still an
        ordinary `pendente` conflict, unchanged from before this directive."""
        cid, did, storage = await _setup(
            scoped, tipo="cnh",
            cliente={"nacionalidade": "italiano", "nacionalidade_origem": "matricula"},
        )
        out = await _extrair(scoped, storage, cid, did, IdentityFields(
            nacionalidade="brasileiro", nacionalidade_confianca=A, source=TextSource.TEXT_LAYER,
        ))
        assert _cliente(scoped, cid)["nacionalidade"] == "italiano"
        assert out["conflitos_abertos"] == ["nacionalidade"]
        (c,) = _conflitos(scoped)
        assert c["status"] == "pendente"

    @pytest.mark.asyncio
    async def test_an_invalid_cpf_on_file_loses_to_a_valid_reading(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="certidao_casamento",
            cliente={"cpf": "111.111.111-11", "cpf_origem": "manual"},
        )
        out = await _extrair(scoped, storage, cid, did, IdentityFields(
            cpf="412.954.238-98", cpf_confianca=A, source=TextSource.TEXT_LAYER,
        ))
        assert _cliente(scoped, cid)["cpf"] == "412.954.238-98"
        assert out["conflitos_abertos"] == []
        (c,) = _conflitos(scoped)
        assert "[validador]" in c["motivo_resolucao"]

    @pytest.mark.asyncio
    async def test_a_cnh_rg_missing_its_check_digit_loses_to_the_fuller_reading(
        self, client, scoped,
    ):
        """The CNH prints the RG without its trailing DV (measured 39%
        precision) — a matrícula qualification's fuller reading, WITH the
        DV, already on file wins automatically."""
        cid, did, storage = await _setup(
            scoped, tipo="cnh",
            cliente={"rg": "1234567890", "rg_origem": "matricula"},
        )
        out = await _extrair(scoped, storage, cid, did, IdentityFields(
            rg="123456789", rg_confianca=A, source=TextSource.TEXT_LAYER,
        ))
        assert _cliente(scoped, cid)["rg"] == "1234567890"  # untouched, WITH the DV
        assert out["conflitos_abertos"] == []
        (c,) = _conflitos(scoped)
        assert "rg_prefixo_dv" in c["motivo_resolucao"]

    def test_married_name_adoption_requires_cpf_corroboration_when_both_present(self):
        """Owner directive, 2026-09-29: `_nome_anterior_confirma_adocao`'s
        pure decision, tested directly. A certidão's own `nome_oficial`
        reading is only 60% precise — the adoption rule may still fire, but
        a CPF on file that actively CONTRADICTS this same reading's CPF now
        refuses it, falling through to the ordinary conflict path. Either
        side ABSENT is unaffected — the tests `TestNomeAnteriorConfirmaAdocao`
        already pin (no cpf carried into those calls) keep firing."""
        base = dict(
            estado_civil="casado", presente="MARIANA PELLEGRINI",
            nome_anterior="MARIANA PELLEGRINI",
            origem_atual="rg", confirmado_em_atual=None,
        )
        # No CPF on either side — the pre-existing, still-green behaviour.
        assert svc._nome_anterior_confirma_adocao(**base) is True
        # Both present and AGREEING — still fires.
        assert svc._nome_anterior_confirma_adocao(
            **base, cpf_atual="478.982.096-30", cpf_lido="478.982.096-30",
        ) is True
        # Both present and DISAGREEING — refused.
        assert svc._nome_anterior_confirma_adocao(
            **base, cpf_atual="478.982.096-30", cpf_lido="303.102.653-55",
        ) is False
        # Only one side present — not enough to contradict, unaffected.
        assert svc._nome_anterior_confirma_adocao(
            **base, cpf_atual="478.982.096-30", cpf_lido=None,
        ) is True
        assert svc._nome_anterior_confirma_adocao(
            **base, cpf_atual=None, cpf_lido="303.102.653-55",
        ) is True


class TestBackfillResolverConflitosPendentes:
    @pytest.mark.asyncio
    async def test_an_existing_pendente_conflict_is_resolved_on_backfill(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="certidao_casamento",
            cliente={"cpf": "303.102.653-55", "cpf_origem": "certidao_casamento"},
        )
        # A 67%-precision value already sits on file; a same-tier-ambiguous
        # nacionalidade fight is NOT what we want here — force a genuine
        # PENDING row the live path could not resolve at the time (an
        # unmeasured origem back then), then confirm the backfill settles
        # it once the resolver can compare it against a measured one.
        scoped.table("cliente_campo_conflitos").insert({
            "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": cid, "campo": "cpf",
            "valor_anterior": "303.102.653-55", "origem_anterior": "certidao_casamento",
            "valor_proposto": "412.954.238-98", "origem_proposto": "cnh",
            "confianca_proposta": "alta", "fonte_tabela": "cliente_documentos",
            "fonte_id": did, "status": "pendente", "notificado_em": None,
            "decidido_por": None, "decidido_em": None, "created_at": _old(3),
        }).execute()

        resultado = svc.backfill_resolver_conflitos_pendentes(scoped, ORG_UUID)

        assert len(resultado["resolvidos"]) == 1
        assert resultado["resolvidos"][0]["decisao_regra"] == "tier"
        assert resultado["ainda_pendentes"] == []
        assert _cliente(scoped, cid)["cpf"] == "412.954.238-98"
        (c,) = _conflitos(scoped)
        assert c["status"] == "resolvido_automatico"

    @pytest.mark.asyncio
    async def test_a_still_ambiguous_conflict_stays_pendente(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="cnh",
            cliente={"nacionalidade": "italiano", "nacionalidade_origem": "matricula"},
        )
        scoped.table("cliente_campo_conflitos").insert({
            "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": cid, "campo": "nacionalidade",
            "valor_anterior": "italiano", "origem_anterior": "matricula",
            "valor_proposto": "brasileiro", "origem_proposto": "cnh",
            "confianca_proposta": "alta", "fonte_tabela": "cliente_documentos",
            "fonte_id": did, "status": "pendente", "notificado_em": None,
            "decidido_por": None, "decidido_em": None, "created_at": _old(3),
        }).execute()

        resultado = svc.backfill_resolver_conflitos_pendentes(scoped, ORG_UUID)

        assert resultado["resolvidos"] == []
        assert len(resultado["ainda_pendentes"]) == 1
        (c,) = _conflitos(scoped)
        assert c["status"] == "pendente"

    @pytest.mark.asyncio
    async def test_a_composite_endereco_conflict_is_reported_not_mis_applied(
        self, client, scoped,
    ):
        cid, did, storage = await _setup(scoped, tipo="comprovante_endereco")
        scoped.table("cliente_campo_conflitos").insert({
            "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": cid, "campo": "endereco",
            "valor_anterior": None, "origem_anterior": None,
            "valor_proposto": json.dumps({"cep": "01000-000"}), "origem_proposto": "cnh",
            "confianca_proposta": "alta", "fonte_tabela": "cliente_documentos",
            "fonte_id": did, "status": "pendente", "notificado_em": None,
            "decidido_por": None, "decidido_em": None, "created_at": _old(3),
        }).execute()

        resultado = svc.backfill_resolver_conflitos_pendentes(scoped, ORG_UUID)

        assert resultado["resolvidos"] == []
        assert resultado["ainda_pendentes"] == []
        assert len(resultado["ignorado_composto"]) == 1


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


class TestEnderecoAttribution:
    """P2 (2026-09-28), measured against 9 real comprovantes vs 10 signed
    contracts: 7/9 bills named a deal party as the holder, and in every such
    case the contract used that bill's address for that party AND their
    spouse. `EnderecoLido.titular` (once `address.py` can actually read
    Sacado/Pagador labels — see that module's own P2 comment) is what makes
    the attribution below possible; these tests pin the identidade_extracao_
    service half: given a titular, decide WHOSE card gets the address."""

    @pytest.mark.asyncio
    async def test_own_name_fills_self_and_the_linked_spouse(self, client, scoped):
        esposa = str(uuid4())
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco",
            cliente={"nome": "Ana Paula Souza", "conjuge_cliente_id": esposa},
            outros=[cliente_row(esposa, nome="Bruno Souza")],
        )
        await _extrair(scoped, storage, cid, did, _comprovante())
        eu, ele = _cliente(scoped, cid), _cliente(scoped, esposa)
        for p in (eu, ele):
            assert (p["endereco_cep"], p["endereco_logradouro"]) == (
                "01454-011", "R PROF ARTUR RAMOS",
            )
            assert p["endereco_origem"] == "comprovante_endereco"
            assert p["endereco_documento_id"] == did
        assert _conflitos(scoped) == []

    @pytest.mark.asyncio
    async def test_a_card_party_matching_the_titular_by_name_gets_the_address(
        self, client, scoped
    ):
        """Uploaded onto Carlos's card, but the bill names Ana — who is
        ANOTHER party on the same atendimento, not Carlos's linked spouse.
        The address goes to Ana (+ her own spouse, if any), never a conflict
        on Carlos, and the write carries this document's own provenance."""
        outra, atd = str(uuid4()), str(uuid4())
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco", cliente={"nome": "Carlos Eduardo Lima"},
            outros=[cliente_row(outra, nome="Ana Paula Souza")],
        )
        scoped.set_table_data("atendimentos", [
            {"id": atd, "org_id": ORG_ID, "cliente_id": cid},
        ])
        scoped.set_table_data("atendimento_partes", [
            {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": atd,
             "cliente_id": outra, "papel": "comprador", "ordem": 0},
        ])
        out = await _extrair(scoped, storage, cid, did, _comprovante())
        assert _cliente(scoped, cid).get("endereco_cep") is None
        row = _cliente(scoped, outra)
        assert (row["endereco_cep"], row["endereco_logradouro"]) == (
            "01454-011", "R PROF ARTUR RAMOS",
        )
        assert row["endereco_documento_id"] == did
        assert _conflitos(scoped) == []
        # `aplicado_ao_cliente` still reads off `cliente_id`'s own dict key —
        # the caller passed `cid`, and the redirect is an internal detail.
        assert out["aplicado_ao_cliente"]["endereco"] is True

    @pytest.mark.asyncio
    async def test_a_titular_matching_nobody_on_the_card_is_still_a_review_conflict(
        self, client, scoped
    ):
        """No card link at all between Carlos and Ana — unchanged from the
        pre-P2 behaviour: never applied, opened as a conflict an admin
        reviews (the JSON payload carries the bill's own titular)."""
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco", cliente={"nome": "Carlos Eduardo Lima"}
        )
        await _extrair(scoped, storage, cid, did, _comprovante())
        assert _cliente(scoped, cid).get("endereco_cep") is None
        (c,) = _conflitos(scoped)
        assert json.loads(c["valor_proposto"])["titular"] == "ANA PAULA SOUZA"

    @pytest.mark.asyncio
    async def test_an_unreadable_titular_still_fills_the_uploaded_to_card(
        self, client, scoped, caplog
    ):
        """No holder name could be read at all (P2: 9/9 real bills) — the
        pre-existing behaviour (fill whoever the file was uploaded onto,
        unattended) is preserved, but the read is logged so an operator
        auditing the extraction knows attribution was never verified."""
        sem_titular = EnderecoLido(
            cep="01454-011", logradouro="R PROF ARTUR RAMOS", numero="123",
            complemento=None, bairro=None, cidade=None, uf=None,
            titular=None, confianca="baixa", rotulo="CEP",
        )
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco", cliente={"nome": "Qualquer Nome"}
        )
        with caplog.at_level("INFO"):
            await _extrair(scoped, storage, cid, did, _comprovante(sem_titular))
        row = _cliente(scoped, cid)
        assert (row["endereco_cep"], row["endereco_logradouro"]) == (
            "01454-011", "R PROF ARTUR RAMOS",
        )
        assert "sem titular legivel" in caplog.text
        assert _conflitos(scoped) == []


class TestEnderecoResolucaoAutomaticaPorTitular:
    """Owner directive, 2026-09-29 follow-up: a genuine comprovante-vs-
    comprovante disagreement resolves by HOLDER when exactly one side's
    printed titular verifies as the party or their linked spouse — else a
    human. Exercised directly against `aplicar_endereco_ao_cliente` (the
    per-document titular EARLY guard the live `extrair_identidade` pipeline
    also runs would otherwise intercept a genuinely mismatched titular
    before this logic is ever reached — see that guard's own docstring)."""

    def _doc(self, doc_id: str, titular: Optional[str] = None) -> dict:
        return {
            "id": doc_id, "org_id": ORG_ID, "cliente_id": "irrelevant",
            "tipo_documento": "comprovante_endereco",
            "extracao_endereco_titular": titular,
        }

    def _partes_novas(self) -> dict:
        return {
            "cep": "01454-011", "logradouro": "R PROF ARTUR RAMOS", "numero": "123",
            "complemento": None, "bairro": None, "cidade": None, "uf": None,
        }

    def test_a_verified_new_holder_wins_over_an_unverified_one_on_file(self, client, scoped):
        cid, doc_velho, doc_novo = str(uuid4()), str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(
            cid, nome="Ana Paula Souza",
            endereco_cep="04000-000", endereco_logradouro="RUA B",
            endereco_origem="comprovante_endereco", endereco_documento_id=doc_velho,
        )])
        scoped.set_table_data("cliente_documentos", [
            self._doc(doc_velho, "OUTRA PESSOA"), self._doc(doc_novo, "ANA PAULA SOUZA"),
        ])
        scoped.set_table_data("cliente_campo_conflitos", [])

        aplicado, conflito = svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "comprovante_endereco", self._partes_novas(),
            titular_documento=None, confianca="alta", documento_id=UUID(doc_novo),
        )

        assert aplicado is True
        assert conflito is None
        row = _cliente(scoped, cid)
        assert (row["endereco_cep"], row["endereco_logradouro"]) == (
            "01454-011", "R PROF ARTUR RAMOS",
        )
        (c,) = _conflitos(scoped)
        assert c["status"] == "resolvido_automatico"
        assert "endereco_titular" in c["motivo_resolucao"]

    def test_a_verified_holder_on_file_beats_an_unverified_new_one(self, client, scoped):
        cid, doc_velho, doc_novo = str(uuid4()), str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(
            cid, nome="Ana Paula Souza",
            endereco_cep="04000-000", endereco_logradouro="RUA B",
            endereco_origem="comprovante_endereco", endereco_documento_id=doc_velho,
        )])
        scoped.set_table_data("cliente_documentos", [
            self._doc(doc_velho, "ANA PAULA SOUZA"), self._doc(doc_novo, "OUTRA PESSOA"),
        ])
        scoped.set_table_data("cliente_campo_conflitos", [])

        aplicado, conflito = svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "comprovante_endereco", self._partes_novas(),
            titular_documento=None, confianca="alta", documento_id=UUID(doc_novo),
        )

        assert aplicado is False
        assert conflito is None  # resolved, not a pendente conflict
        row = _cliente(scoped, cid)
        assert (row["endereco_cep"], row["endereco_logradouro"]) == ("04000-000", "RUA B")
        (c,) = _conflitos(scoped)
        assert c["status"] == "resolvido_automatico"

    def test_the_spouse_link_counts_as_a_verified_holder(self, client, scoped):
        esposo = str(uuid4())
        cid, doc_velho, doc_novo = str(uuid4()), str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(
            cid, nome="Ana Paula Souza", conjuge_cliente_id=esposo,
            endereco_cep="04000-000", endereco_logradouro="RUA B",
            endereco_origem="comprovante_endereco", endereco_documento_id=doc_velho,
        )])
        scoped.set_table_data(
            "clientes",
            scoped.table("clientes").select("*").execute().data
            + [cliente_row(esposo, nome="Bruno Souza")],
        )
        scoped.set_table_data("cliente_documentos", [
            self._doc(doc_velho, "OUTRA PESSOA"), self._doc(doc_novo, "BRUNO SOUZA"),
        ])
        scoped.set_table_data("cliente_campo_conflitos", [])

        aplicado, conflito = svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "comprovante_endereco", self._partes_novas(),
            titular_documento=None, confianca="alta", documento_id=UUID(doc_novo),
        )

        assert aplicado is True
        row = _cliente(scoped, cid)
        assert row["endereco_logradouro"] == "R PROF ARTUR RAMOS"

    def test_both_sides_unverified_still_needs_a_human(self, client, scoped):
        cid, doc_velho, doc_novo = str(uuid4()), str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(
            cid, nome="Ana Paula Souza",
            endereco_cep="04000-000", endereco_logradouro="RUA B",
            endereco_origem="comprovante_endereco", endereco_documento_id=doc_velho,
        )])
        scoped.set_table_data("cliente_documentos", [
            self._doc(doc_velho, "OUTRA PESSOA"), self._doc(doc_novo, "MAIS OUTRA PESSOA"),
        ])
        scoped.set_table_data("cliente_campo_conflitos", [])

        aplicado, conflito = svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "comprovante_endereco", self._partes_novas(),
            titular_documento=None, confianca="alta", documento_id=UUID(doc_novo),
        )

        assert aplicado is False
        assert conflito is not None
        assert conflito["status"] == "pendente"
        row = _cliente(scoped, cid)
        assert row["endereco_logradouro"] == "RUA B"  # untouched

    def test_a_manually_typed_address_is_never_auto_overridden_by_the_holder_rule(
        self, client, scoped,
    ):
        cid, doc_novo = str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(
            cid, nome="Ana Paula Souza",
            endereco_cep="04000-000", endereco_logradouro="RUA B",
            endereco_origem="manual",
        )])
        scoped.set_table_data("cliente_documentos", [self._doc(doc_novo, "ANA PAULA SOUZA")])
        scoped.set_table_data("cliente_campo_conflitos", [])

        aplicado, conflito = svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "comprovante_endereco", self._partes_novas(),
            titular_documento=None, confianca="alta", documento_id=UUID(doc_novo),
        )

        assert aplicado is False
        assert conflito is not None
        assert conflito["status"] == "pendente"
        assert _cliente(scoped, cid)["endereco_logradouro"] == "RUA B"


# ─── both spouses ──────────────────────────────────────────────────────────


def _certidao(
    titular_idx: int | None = 0,
    *,
    nome_anterior_almir: str | None = None,
    nome_anterior_mariana: str | None = None,
    estado_civil: str = "casado",
) -> IdentityFields:
    almir = ConjugeLido(
        nome="ALMIR TEIXEIRA DA COSTA", nome_anterior=nome_anterior_almir,
        cpf="303.102.653-55", cpf_confianca="alta",
        data_nascimento=date(1961, 10, 4), data_nascimento_confianca="baixa",
        nacionalidade="brasileiro", nacionalidade_confianca="alta",
        profissao="comerciante", profissao_confianca="alta",
        genero="Masculino", genero_confianca="baixa", titular=titular_idx == 0,
    )
    mariana = ConjugeLido(
        nome="MARIANA PELLEGRINI RANGEL", nome_anterior=nome_anterior_mariana,
        cpf="478.982.096-30", cpf_confianca="alta",
        data_nascimento=date(1964, 4, 20), data_nascimento_confianca="baixa",
        profissao="professora", profissao_confianca="alta",
        genero="Feminino", genero_confianca="baixa", titular=titular_idx == 1,
    )
    eu = (almir, mariana)[titular_idx] if titular_idx is not None else None
    return IdentityFields(
        nome=eu.nome if eu else None, nome_confianca=A if eu else ExtractionConfidence.NENHUMA,
        cpf=eu.cpf if eu else None, cpf_confianca=A if eu else ExtractionConfidence.NENHUMA,
        estado_civil=estado_civil, estado_civil_confianca=A,
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


# ─── same-side fallback (owner directive, 2026-09-29): a name/CPF match on
# the certidão's OTHER spouse fails because the party row has no usable name
# yet (a placeholder like "Comprador 2") or no identity document of their own
# — the only other party on the SAME side of the SAME atendimento IS that
# spouse, provided nothing about them disagrees. ───────────────────────────


class TestConjugePorLadoUnico:
    @pytest.mark.asyncio
    async def test_lead_and_placeholder_comprador_2_are_paired_and_filled(
        self, client, scoped,
    ):
        comprador2 = str(uuid4())
        cid, did, storage = await _setup(
            scoped, tipo="certidao_casamento", cliente={"nome": "Almir"},
            outros=[cliente_row(comprador2, nome="Comprador 2")],
        )
        atd = str(uuid4())
        scoped.set_table_data("atendimentos", [{"id": atd, "org_id": ORG_ID, "cliente_id": cid}])
        scoped.set_table_data("atendimento_partes", [
            {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": atd,
             "cliente_id": comprador2, "lado": "comprador", "papel": "comprador", "ordem": 0},
        ])
        out = await _extrair(scoped, storage, cid, did, _certidao(0))
        eu, ela = _cliente(scoped, cid), _cliente(scoped, comprador2)
        assert ela["nome_oficial"] == "MARIANA PELLEGRINI RANGEL"
        assert ela["cpf"] == "478.982.096-30"
        assert ela["profissao"] == "professora"
        assert ela["genero"] == "Feminino"
        assert ela["data_nascimento"] == "1964-04-20"
        assert ela["cpf_origem"] == "certidao_casamento"
        for p in (eu, ela):
            assert (p["estado_civil"], p["regime_bens"], p["data_casamento"]) == (
                "casado", "comunhao_parcial", "2011-07-30",
            )
        # Recorded durably both ways, so a later comprovante propagates too.
        assert (eu["conjuge_cliente_id"], ela["conjuge_cliente_id"]) == (comprador2, cid)
        assert ela["conjuge_origem"] == "certidao_casamento"
        registro = _documento(scoped, did)["extracao_conjuges"]
        assert [(r["titular"], r["cliente_id"]) for r in registro] == [
            (True, cid), (False, comprador2),
        ]
        assert out["conflitos_abertos"] == []

    @pytest.mark.asyncio
    async def test_seller_side_pairs_when_the_certidao_is_on_vendedor_um(
        self, client, scoped,
    ):
        vendedor2 = str(uuid4())
        cid, did, storage = await _setup(
            scoped, tipo="certidao_casamento", cliente={"nome": "Vendedor 1"},
            outros=[cliente_row(vendedor2, nome="Vendedor 2")],
        )
        atd, comprador_lead = str(uuid4()), str(uuid4())
        scoped.set_table_data(
            "atendimentos", [{"id": atd, "org_id": ORG_ID, "cliente_id": comprador_lead}],
        )
        scoped.set_table_data("atendimento_partes", [
            {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": atd,
             "cliente_id": cid, "lado": "vendedor", "papel": "proprietario", "ordem": 0},
            {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": atd,
             "cliente_id": vendedor2, "lado": "vendedor", "papel": "conjuge", "ordem": 1},
        ])
        await _extrair(scoped, storage, cid, did, _certidao(0))
        eu, ela = _cliente(scoped, cid), _cliente(scoped, vendedor2)
        assert ela["nome_oficial"] == "MARIANA PELLEGRINI RANGEL"
        assert ela["cpf"] == "478.982.096-30"
        assert (eu["conjuge_cliente_id"], ela["conjuge_cliente_id"]) == (vendedor2, cid)

    @pytest.mark.asyncio
    async def test_a_disagreeing_cpf_on_the_only_candidate_is_left_for_review(
        self, client, scoped,
    ):
        comprador2 = str(uuid4())
        cid, did, storage = await _setup(
            scoped, tipo="certidao_casamento", cliente={"nome": "Almir"},
            outros=[cliente_row(comprador2, nome="Comprador 2", cpf="111.111.111-11")],
        )
        atd = str(uuid4())
        scoped.set_table_data("atendimentos", [{"id": atd, "org_id": ORG_ID, "cliente_id": cid}])
        scoped.set_table_data("atendimento_partes", [
            {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": atd,
             "cliente_id": comprador2, "lado": "comprador", "papel": "comprador", "ordem": 0},
        ])
        await _extrair(scoped, storage, cid, did, _certidao(0))
        ela = _cliente(scoped, comprador2)
        assert ela["cpf"] == "111.111.111-11"  # untouched — no silent overwrite
        assert ela.get("conjuge_cliente_id") is None
        assert _cliente(scoped, cid).get("conjuge_cliente_id") is None
        registro = _documento(scoped, did)["extracao_conjuges"]
        assert next(r for r in registro if not r["titular"])["cliente_id"] is None

    @pytest.mark.asyncio
    async def test_three_parties_on_a_side_is_never_auto_paired(self, client, scoped):
        comprador2, comprador3 = str(uuid4()), str(uuid4())
        cid, did, storage = await _setup(
            scoped, tipo="certidao_casamento", cliente={"nome": "Almir"},
            outros=[
                cliente_row(comprador2, nome="Comprador 2"),
                cliente_row(comprador3, nome="Comprador 3"),
            ],
        )
        atd = str(uuid4())
        scoped.set_table_data("atendimentos", [{"id": atd, "org_id": ORG_ID, "cliente_id": cid}])
        scoped.set_table_data("atendimento_partes", [
            {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": atd,
             "cliente_id": comprador2, "lado": "comprador", "papel": "comprador", "ordem": 0},
            {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": atd,
             "cliente_id": comprador3, "lado": "comprador", "papel": "comprador", "ordem": 1},
        ])
        await _extrair(scoped, storage, cid, did, _certidao(0))
        for outro in (comprador2, comprador3):
            row = _cliente(scoped, outro)
            assert row.get("cpf") is None
            assert row.get("conjuge_cliente_id") is None
        assert _cliente(scoped, cid).get("conjuge_cliente_id") is None
        registro = _documento(scoped, did)["extracao_conjuges"]
        assert next(r for r in registro if not r["titular"])["cliente_id"] is None


# ─── nome_anterior confirms a marriage name adoption (owner decision,
# 2026-09-28) ────────────────────────────────────────────────────────────


class TestNomeAnteriorConfirmaAdocao:
    @pytest.mark.asyncio
    async def test_cnh_maiden_and_certidao_married_is_no_conflict_married_chosen(
        self, client, scoped,
    ):
        """The RG/CNH reading fills `nome_oficial` with the maiden name
        first; the certidão de casamento, read later, states CASADO and
        that this exact value is the name the spouse LEFT BEHIND — the
        married name replaces it, no conflict opens."""
        esposa = str(uuid4())
        cid, did_rg, storage = await _setup(
            scoped, tipo="certidao_casamento",
            cliente={"nome": "Almir", "conjuge_cliente_id": esposa, "conjuge_origem": "manual"},
            outros=[cliente_row(esposa, nome="Mariana")],
        )
        # First document: her own RG, maiden name.
        did_rg2 = str(uuid4())
        scoped.table("cliente_documentos").insert({
            "id": did_rg2, "org_id": ORG_ID, "cliente_id": esposa,
            "storage_path": f"{ORG_ID}/clientes/{esposa}/{did_rg2}",
            "nome_original": "rg.pdf", "mime_type": "application/pdf",
            "tipo_documento": "rg", "deleted_at": None,
            "extracao_status": "pendente", "extracao_tentativas": 0,
            "created_at": _old(2),
        }).execute()
        await storage.put(
            bucket=BUCKET, key=f"{ORG_ID}/clientes/{esposa}/{did_rg2}",
            data=b"%PDF-1.4", content_type="application/pdf",
        )
        await _extrair(scoped, storage, esposa, did_rg2, IdentityFields(
            nome="MARIANA PELLEGRINI", nome_confianca=A, source=TextSource.OCR,
        ))
        assert _cliente(scoped, esposa)["nome_oficial"] == "MARIANA PELLEGRINI"

        # Second document: the certidão, read against the titular's (Almir's)
        # card — states Mariana adopted "RANGEL" and left "MARIANA
        # PELLEGRINI" behind.
        out = await _extrair(scoped, storage, cid, did_rg, _certidao(
            0, nome_anterior_mariana="MARIANA PELLEGRINI",
        ))
        ela = _cliente(scoped, esposa)
        assert ela["nome_oficial"] == "MARIANA PELLEGRINI RANGEL"
        assert ela["nome_oficial_origem"] == "certidao_casamento"
        assert ela["nome_oficial_documento_id"] == did_rg
        assert ela.get("nome_oficial_confirmado_em") is None
        assert out["conflitos_abertos"] == []
        assert _conflitos(scoped) == []
        registro = _documento(scoped, did_rg)["extracao_conjuges"]
        mariana_registro = next(r for r in registro if r["nome"] == "MARIANA PELLEGRINI RANGEL")
        assert mariana_registro["nome_anterior"] == "MARIANA PELLEGRINI"

    @pytest.mark.asyncio
    async def test_married_keeping_the_name_is_an_ordinary_disagreement(self, client, scoped):
        """No `nome_anterior` (the certidão states she KEPT her name) — a
        genuinely different on-file value is still an ordinary conflict,
        never silently suppressed by this rule."""
        esposa = str(uuid4())
        cid, did, storage = await _setup(
            scoped, tipo="certidao_casamento",
            cliente={"nome": "Almir", "conjuge_cliente_id": esposa, "conjuge_origem": "manual"},
            outros=[cliente_row(
                esposa, nome="Mariana",
                nome_oficial="MARIANA PELLEGRINI", nome_oficial_origem="rg",
                nome_oficial_documento_id=str(uuid4()), nome_oficial_em=_old(2),
            )],
        )
        await _extrair(scoped, storage, cid, did, _certidao(0))  # no nome_anterior
        ela = _cliente(scoped, esposa)
        assert ela["nome_oficial"] == "MARIANA PELLEGRINI"  # untouched
        assert [c["campo"] for c in _conflitos(scoped)] == ["nome_oficial"]

    @pytest.mark.asyncio
    async def test_a_human_confirmed_maiden_name_is_never_overwritten(self, client, scoped):
        esposa = str(uuid4())
        cid, did, storage = await _setup(
            scoped, tipo="certidao_casamento",
            cliente={"nome": "Almir", "conjuge_cliente_id": esposa, "conjuge_origem": "manual"},
            outros=[cliente_row(
                esposa, nome="Mariana",
                nome_oficial="MARIANA PELLEGRINI", nome_oficial_origem="rg",
                nome_oficial_documento_id=str(uuid4()), nome_oficial_em=_old(2),
                nome_oficial_confirmado_em=_old(1), nome_oficial_confirmado_por=str(uuid4()),
            )],
        )
        await _extrair(scoped, storage, cid, did, _certidao(
            0, nome_anterior_mariana="MARIANA PELLEGRINI",
        ))
        ela = _cliente(scoped, esposa)
        assert ela["nome_oficial"] == "MARIANA PELLEGRINI"  # untouched
        assert [c["campo"] for c in _conflitos(scoped)] == ["nome_oficial"]

    @pytest.mark.asyncio
    async def test_a_divorced_party_still_conflicts_not_auto_adopted(self, client, scoped):
        """`NOC-REMEDIATE[nome-anterior-pos-averbacao]` — divorciado/
        separado/viúvo has no equivalent auto-resolution yet; this rule
        only ever fires past `casado`."""
        esposa = str(uuid4())
        cid, did, storage = await _setup(
            scoped, tipo="certidao_casamento",
            cliente={"nome": "Almir", "conjuge_cliente_id": esposa, "conjuge_origem": "manual"},
            outros=[cliente_row(
                esposa, nome="Mariana",
                nome_oficial="MARIANA PELLEGRINI", nome_oficial_origem="rg",
                nome_oficial_documento_id=str(uuid4()), nome_oficial_em=_old(2),
            )],
        )
        await _extrair(scoped, storage, cid, did, _certidao(
            0, nome_anterior_mariana="MARIANA PELLEGRINI", estado_civil="divorciado",
        ))
        ela = _cliente(scoped, esposa)
        assert ela["nome_oficial"] == "MARIANA PELLEGRINI"  # untouched
        assert [c["campo"] for c in _conflitos(scoped)] == ["nome_oficial"]

    @pytest.mark.asyncio
    async def test_the_titulars_own_maiden_name_is_also_adopted(self, client, scoped):
        """Symmetric with the OTHER spouse: the titular's OWN card
        benefits from the same rule when their own RG's maiden name
        matches what THEIR certidão entry says they left behind."""
        cid, did, storage = await _setup(
            scoped, tipo="certidao_casamento",
            cliente={
                "nome": "Almir",
                "nome_oficial": "ALMIR TEIXEIRA", "nome_oficial_origem": "rg",
                "nome_oficial_documento_id": str(uuid4()), "nome_oficial_em": _old(2),
            },
        )
        out = await _extrair(scoped, storage, cid, did, _certidao(
            0, nome_anterior_almir="ALMIR TEIXEIRA",
        ))
        eu = _cliente(scoped, cid)
        assert eu["nome_oficial"] == "ALMIR TEIXEIRA DA COSTA"
        assert eu["nome_oficial_origem"] == "certidao_casamento"
        assert out["conflitos_abertos"] == []


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
