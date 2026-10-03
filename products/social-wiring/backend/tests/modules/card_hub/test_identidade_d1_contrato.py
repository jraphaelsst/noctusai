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
from typing import Optional
from uuid import UUID, uuid4

import pytest

from app.modules.card_hub import identidade_extracao_service as svc
from noctusai_lib.integrations.cep import CepEndereco, FakeCepLookupAdapter
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


async def _extrair(scoped, storage, cid, did, fields, notifier=None, cep_lookup=None):
    return await svc.extrair_identidade(
        scoped, storage, ORG_UUID, UUID(cid), UUID(did),
        extractor=FakeIdentityExtractor(fields),
        notification_service=notifier,
        cep_lookup=cep_lookup,
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
    async def test_a_cnh_rg_missing_its_check_digit_is_the_same_rg_not_a_conflict(
        self, client, scoped,
    ):
        """The CNH prints the RG without its trailing DV (measured 39%
        precision) — `30128742` and the matrícula's `30.128.742-9` are ONE
        identifier (owner rule 2026-10-01): nothing to resolve, the on-file
        value (with its DV) and its provenance are untouched."""
        cid, did, storage = await _setup(
            scoped, tipo="cnh",
            cliente={"rg": "30.128.742-9", "rg_origem": "matricula"},
        )
        out = await _extrair(scoped, storage, cid, did, IdentityFields(
            rg="30128742", rg_confianca=A, source=TextSource.TEXT_LAYER,
        ))
        row = _cliente(scoped, cid)
        assert row["rg"] == "30.128.742-9"  # untouched, WITH the DV
        assert row["rg_origem"] == "matricula"
        assert out["conflitos_abertos"] == []
        assert _conflitos(scoped) == []

    @pytest.mark.asyncio
    async def test_a_raw_stored_rg_is_upgraded_to_canonical_without_restamping_provenance(
        self, client, scoped,
    ):
        cid, did, storage = await _setup(
            scoped, tipo="cnh",
            cliente={"rg": "301287429", "rg_origem": "matricula"},
        )
        await _extrair(scoped, storage, cid, did, IdentityFields(
            rg="30.128.742-9", rg_confianca=A, source=TextSource.TEXT_LAYER,
        ))
        row = _cliente(scoped, cid)
        assert row["rg"] == "30.128.742-9"
        assert row["rg_origem"] == "matricula"
        assert _conflitos(scoped) == []

    @pytest.mark.asyncio
    async def test_a_dv_invalid_ocr_rg_on_file_loses_to_the_verifying_reading(
        self, client, scoped,
    ):
        cid, did, storage = await _setup(
            scoped, tipo="rg",
            cliente={"rg": "15.668.564-3", "rg_origem": "matricula"},
        )
        out = await _extrair(scoped, storage, cid, did, IdentityFields(
            rg="16.669.554-3", rg_confianca=A, source=TextSource.TEXT_LAYER,
        ))
        assert _cliente(scoped, cid)["rg"] == "16.669.554-3"
        assert out["conflitos_abertos"] == []
        (c,) = _conflitos(scoped)
        assert "[validador]" in c["motivo_resolucao"]

    @pytest.mark.asyncio
    async def test_a_cpf_read_into_the_rg_field_is_not_written_and_flags_the_document(
        self, client, scoped,
    ):
        cid, did, storage = await _setup(scoped, tipo="rg")
        await _extrair(scoped, storage, cid, did, IdentityFields(
            rg="297.556.088-50", rg_confianca=A, source=TextSource.TEXT_LAYER,
        ))
        assert _cliente(scoped, cid).get("rg") in (None, "")
        doc = scoped.table("cliente_documentos").select("*").eq("id", did).execute().data[0]
        assert doc["extracao_aviso"] == "identificador_de_outro_tipo"
        assert "RG" in doc["extracao_aviso_mensagem"]

    @pytest.mark.asyncio
    async def test_a_cin_rg_equal_to_the_holders_own_cpf_is_stored_canonical(
        self, client, scoped,
    ):
        cid, did, storage = await _setup(scoped, tipo="cin")
        await _extrair(scoped, storage, cid, did, IdentityFields(
            cpf="29755608850", cpf_confianca=A,
            rg="297.556.088-50", rg_confianca=A, source=TextSource.TEXT_LAYER,
        ))
        row = _cliente(scoped, cid)
        assert row["cpf"] == "297.556.088-50"
        assert row["rg"] == "297.556.088-50"

    @pytest.mark.asyncio
    async def test_cpf_and_cnh_rg_are_written_canonical(self, client, scoped):
        cid, did, storage = await _setup(scoped, tipo="cnh")
        await _extrair(scoped, storage, cid, did, IdentityFields(
            cpf="41295423898", cpf_confianca=A,
            rg="30128742", rg_confianca=A, source=TextSource.TEXT_LAYER,
        ))
        row = _cliente(scoped, cid)
        assert row["cpf"] == "412.954.238-98"
        assert row["rg"] == "30.128.742-9"  # DV completed arithmetically

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
    async def test_an_empty_on_file_address_is_re_judged_not_ignored_forever(
        self, client, scoped,
    ):
        """🔴 R2 FIX (owner directive, 2026-09-30, live-test evidence): an
        `endereco` conflict opened against an EMPTY on-file address stores
        `valor_anterior=None` (`aplicar_endereco_ao_cliente`'s own
        `conflito()`) — `_decidir_endereco_pendente` used to read that as
        "not a JSON object, cannot judge" and parked it in
        `ignorado_composto` FOREVER, even once the missing holder evidence
        later landed. It must now be RE-JUDGED like any other pending
        conflict; here there is still no titular info on either side, so it
        correctly lands in `ainda_pendentes` (a human is still needed) —
        never silently dropped."""
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
        assert resultado["ignorado_composto"] == []
        assert len(resultado["ainda_pendentes"]) == 1
        (c,) = _conflitos(scoped)
        assert c["status"] == "pendente"  # untouched — still needs a human

    @pytest.mark.asyncio
    async def test_a_non_dict_proposal_is_still_reported_composite(self, client, scoped):
        """The remaining `ignorado_composto` case: `valor_proposto` itself
        is not a JSON object at all — genuinely not a shape this resolver
        can judge, regardless of `valor_anterior`."""
        cid, did, storage = await _setup(scoped, tipo="comprovante_endereco")
        scoped.table("cliente_campo_conflitos").insert({
            "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": cid, "campo": "endereco",
            "valor_anterior": None, "origem_anterior": None,
            "valor_proposto": "01000-000", "origem_proposto": "cnh",
            "confianca_proposta": "alta", "fonte_tabela": "cliente_documentos",
            "fonte_id": did, "status": "pendente", "notificado_em": None,
            "decidido_por": None, "decidido_em": None, "created_at": _old(3),
        }).execute()

        resultado = svc.backfill_resolver_conflitos_pendentes(scoped, ORG_UUID)

        assert resultado["resolvidos"] == []
        assert resultado["ainda_pendentes"] == []
        assert len(resultado["ignorado_composto"]) == 1


def _doc(cid, tipo, *, deleted=False, **extracao) -> dict:
    return {
        "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": cid,
        "storage_path": f"{ORG_ID}/clientes/{cid}/x", "nome_original": f"{tipo}.pdf",
        "mime_type": "application/pdf", "tipo_documento": tipo,
        "deleted_at": _old(1) if deleted else None, "extracao_status": "ok",
        "extracao_tentativas": 1, "created_at": _old(5), **extracao,
    }


def _pendente(cid, campo, *, anterior, origem_anterior, proposto, origem_proposto,
              fonte_id=None, fonte_tabela="cliente_documentos") -> dict:
    return {
        "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": cid, "campo": campo,
        "valor_anterior": anterior, "origem_anterior": origem_anterior,
        "valor_proposto": proposto, "origem_proposto": origem_proposto,
        "confianca_proposta": "alta", "fonte_tabela": fonte_tabela if fonte_id else None,
        "fonte_id": fonte_id, "status": "pendente", "notificado_em": None,
        "decidido_por": None, "decidido_em": None, "created_at": _old(3),
    }


def _cenario(scoped, cliente: dict, docs: list[dict], conflitos: list[dict], outros=()):
    scoped.set_table_data("clientes", [cliente, *outros])
    scoped.set_table_data("cliente_documentos", docs)
    scoped.set_table_data("cliente_documento_acessos", [])
    scoped.set_table_data("cliente_campo_conflitos", conflitos)


class TestBackfillEvidenciaViva:
    """The prod queue's 10 survivors after the first resolver pass
    (2026-09-29), one test per shape — synthetic values, real shapes."""

    def test_a_re_read_that_dropped_the_value_retracts_it(self, client, scoped):
        cid = str(uuid4())
        cnh = _doc(cid, "cnh", extracao_nome=None, extracao_cpf="41295423898")
        serasa = _doc(cid, "serasa_crednet", extracao_nome="MARIA SOUZA LIMA")
        _cenario(
            scoped,
            cliente_row(cid, cpf="412.954.238-98", nome_oficial="JOANA SOUZA",
                        nome_oficial_origem="cnh", nome_oficial_documento_id=cnh["id"]),
            [cnh, serasa],
            [_pendente(cid, "nome_oficial", anterior="JOANA SOUZA", origem_anterior="cnh",
                       proposto="MARIA SOUZA LIMA", origem_proposto="serasa_crednet",
                       fonte_id=serasa["id"])],
        )
        out = svc.backfill_resolver_conflitos_pendentes(scoped, ORG_UUID)
        assert [r["decisao_regra"] for r in out["resolvidos"]] == ["retratado"]
        assert _cliente(scoped, cid)["nome_oficial"] == "MARIA SOUZA LIMA"
        (c,) = _conflitos(scoped)
        assert c["status"] == "resolvido_automatico"

    def test_a_certidao_flat_value_is_not_this_persons_without_attribution(self, client, scoped):
        cid = str(uuid4())
        cnh = _doc(cid, "cnh", extracao_rg="12345678")
        certidao = _doc(cid, "certidao_casamento", extracao_rg="9876543210", extracao_conjuges=[])
        _cenario(
            scoped,
            cliente_row(cid, rg="12345678", rg_origem="cnh", rg_documento_id=cnh["id"]),
            [cnh, certidao],
            [_pendente(cid, "rg", anterior="12345678", origem_anterior="cnh",
                       proposto="9876543210", origem_proposto="certidao_casamento",
                       fonte_id=certidao["id"])],
        )
        out = svc.backfill_resolver_conflitos_pendentes(scoped, ORG_UUID)
        assert [(r["decisao_regra"], r["decisao_vencedor"]) for r in out["resolvidos"]] == [
            ("retratado", "atual")
        ]
        assert _cliente(scoped, cid)["rg"] == "12345678"

    def test_an_attributed_certidao_entry_is_not_retracted(self, client, scoped):
        cid = str(uuid4())
        certidao = _doc(
            cid, "certidao_casamento", extracao_data_nascimento="1980-05-12",
            extracao_conjuges=[{"nome": "ANA", "data_nascimento": "1980-05-12", "cliente_id": cid}],
        )
        rg = _doc(cid, "rg", extracao_data_nascimento="1980-05-13")
        _cenario(
            scoped,
            cliente_row(cid, data_nascimento="1980-05-13", data_nascimento_origem="rg",
                        data_nascimento_documento_id=rg["id"]),
            [certidao, rg],
            [_pendente(cid, "data_nascimento", anterior="1980-05-13", origem_anterior="rg",
                       proposto="1980-05-12", origem_proposto="certidao_casamento",
                       fonte_id=certidao["id"])],
        )
        out = svc.backfill_resolver_conflitos_pendentes(scoped, ORG_UUID)
        # Both sides supported, no measured tier for data_nascimento: a human.
        assert out["resolvidos"] == []
        assert len(out["ainda_pendentes"]) == 1

    def test_a_human_confirmed_value_is_never_judged_retracted(self, client, scoped):
        cid = str(uuid4())
        cnh = _doc(cid, "cnh", extracao_nome=None)
        serasa = _doc(cid, "serasa_crednet", extracao_nome="MARIA SOUZA LIMA")
        _cenario(
            scoped,
            cliente_row(cid, nome_oficial="JOANA SOUZA", nome_oficial_origem="cnh",
                        nome_oficial_documento_id=cnh["id"],
                        nome_oficial_confirmado_em=_old(2),
                        nome_oficial_confirmado_por=str(uuid4())),
            [cnh, serasa],
            [_pendente(cid, "nome_oficial", anterior="JOANA SOUZA", origem_anterior="cnh",
                       proposto="MARIA SOUZA LIMA", origem_proposto="serasa_crednet",
                       fonte_id=serasa["id"])],
        )
        out = svc.backfill_resolver_conflitos_pendentes(scoped, ORG_UUID)
        assert out["resolvidos"] == []
        assert _cliente(scoped, cid)["nome_oficial"] == "JOANA SOUZA"

    def test_a_live_document_that_agrees_corroborates_a_typed_value(self, client, scoped):
        cid = str(uuid4())
        rg = _doc(cid, "rg", extracao_nome="ANA PAULA SOUZA")
        _cenario(
            scoped,
            cliente_row(cid, nome_oficial="ANA PAULA SOUZA", nome_oficial_origem="manual"),
            [rg],
            [_pendente(cid, "nome_oficial", anterior="ANA PAULA SOUZA", origem_anterior="manual",
                       proposto="ANA P SOUZA", origem_proposto="matricula",
                       fonte_id=str(uuid4()), fonte_tabela="matricula_qualificacoes")],
        )
        out = svc.backfill_resolver_conflitos_pendentes(scoped, ORG_UUID)
        assert [(r["decisao_regra"], r["decisao_vencedor"]) for r in out["resolvidos"]] == [
            ("corroboracao", "atual")
        ]

    def test_an_endereco_conflict_that_is_the_same_address_today_closes(self, client, scoped):
        cid = str(uuid4())
        bill = _doc(cid, "comprovante_endereco", extracao_endereco_titular="OUTRA PESSOA")
        partes = {"cep": "01310-100", "logradouro": "AV PAULISTA", "numero": "1000",
                  "complemento": None, "bairro": "BELA VISTA", "cidade": "SAO PAULO", "uf": "SP"}
        _cenario(
            scoped,
            cliente_row(cid, endereco_origem="comprovante_endereco", endereco_documento_id=bill["id"],
                        **{f"endereco_{k}": v for k, v in {**partes, "logradouro": "AVENIDA PAULISTA"}.items()}),
            [bill],
            [_pendente(cid, "endereco",
                       anterior=json.dumps({**partes, "logradouro": "AVENIDA PAULISTA"}),
                       origem_anterior="comprovante_endereco",
                       proposto=json.dumps({**partes, "titular": "OUTRA PESSOA"}),
                       origem_proposto="comprovante_endereco", fonte_id=bill["id"])],
        )
        out = svc.backfill_resolver_conflitos_pendentes(scoped, ORG_UUID)
        assert [r["decisao_regra"] for r in out["resolvidos"]] == ["mesmo_endereco"]
        (c,) = _conflitos(scoped)
        assert c["status"] == "resolvido_automatico"

    def test_an_endereco_whose_bill_was_deleted_yields_to_the_live_one(self, client, scoped):
        cid = str(uuid4())
        velho = _doc(cid, "comprovante_endereco", deleted=True)
        novo = _doc(cid, "comprovante_endereco", extracao_endereco_titular="ANA")
        antigo = {"cep": "04000-000", "logradouro": "RUA A", "numero": "1", "complemento": None,
                  "bairro": "X", "cidade": "SAO PAULO", "uf": "SP"}
        atual = {"cep": "05000-000", "logradouro": "RUA B", "numero": "2", "complemento": None,
                 "bairro": "Y", "cidade": "SAO PAULO", "uf": "SP"}
        _cenario(
            scoped,
            cliente_row(cid, endereco_origem="comprovante_endereco", endereco_documento_id=velho["id"],
                        **{f"endereco_{k}": v for k, v in antigo.items()}),
            [velho, novo],
            [_pendente(cid, "endereco", anterior=json.dumps(antigo),
                       origem_anterior="comprovante_endereco",
                       proposto=json.dumps({**atual, "titular": "ANA"}),
                       origem_proposto="comprovante_endereco", fonte_id=novo["id"])],
        )
        out = svc.backfill_resolver_conflitos_pendentes(scoped, ORG_UUID)
        assert [(r["decisao_regra"], r["decisao_vencedor"]) for r in out["resolvidos"]] == [
            ("retratado", "proposto")
        ]
        row = _cliente(scoped, cid)
        assert (row["endereco_cep"], row["endereco_documento_id"]) == ("05000-000", novo["id"])

    def test_a_manual_endereco_is_never_resolved_automatically(self, client, scoped):
        cid = str(uuid4())
        novo = _doc(cid, "comprovante_endereco", extracao_endereco_titular="ANA")
        antigo = {"cep": "04000-000", "logradouro": "RUA A", "numero": "1", "complemento": None,
                  "bairro": "X", "cidade": "SAO PAULO", "uf": "SP"}
        _cenario(
            scoped,
            cliente_row(cid, endereco_origem="manual", **{f"endereco_{k}": v for k, v in antigo.items()}),
            [novo],
            [_pendente(cid, "endereco", anterior=json.dumps(antigo), origem_anterior="manual",
                       proposto=json.dumps({**antigo, "cep": "05000-000", "titular": "ANA"}),
                       origem_proposto="comprovante_endereco", fonte_id=novo["id"])],
        )
        out = svc.backfill_resolver_conflitos_pendentes(scoped, ORG_UUID)
        assert out["resolvidos"] == []
        assert _cliente(scoped, cid)["endereco_cep"] == "04000-000"


class TestEnderecoTitularDeOutroMesmoEndereco:
    def test_a_bill_in_someone_elses_name_stating_the_address_on_file_asks_nothing(
        self, client, scoped
    ):
        cid = str(uuid4())
        partes = {"cep": "01310-100", "logradouro": "Avenida Paulista", "numero": "1000",
                  "complemento": None, "bairro": "Bela Vista", "cidade": "Sao Paulo", "uf": "SP"}
        _cenario(
            scoped,
            cliente_row(cid, nome="Ana", nome_oficial="ANA SOUZA", endereco_origem="comprovante_endereco",
                        **{f"endereco_{k}": v for k, v in partes.items()}),
            [], [],
        )
        aplicado, conflito = svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "comprovante_endereco",
            {**partes, "logradouro": "AV PAULISTA"}, titular_documento="CARLOS PEREIRA",
        )
        assert (aplicado, conflito) == (False, None)
        assert _conflitos(scoped) == []


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
            scoped, cliente={"rg": "30.128.742-9", "rg_origem": "manual"}
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


class TestEnderecoCepAuthority:
    """F3 (live prod test, 2026-09-30): CEP is the authority for cidade/uf
    once it resolves; a suspicious `cidade` (too long, or carrying a digit)
    is withheld even with no `cep_lookup` at all."""

    @pytest.mark.asyncio
    async def test_cep_replaces_a_wrong_cidade_uf_from_the_document(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco", cliente={"nome": "Ana Paula Souza"}
        )
        errado = EnderecoLido(
            cep="01454-011", logradouro="R PROF ARTUR RAMOS", numero="123",
            complemento="APTO 12", bairro="JARDIM PAULISTANO",
            cidade="BAIRRO ERRADO", uf="RJ",
            titular="ANA PAULA SOUZA", confianca="alta", rotulo="ENDERECO",
        )
        cep_lookup = FakeCepLookupAdapter({
            "01454-011": CepEndereco(
                cep="01454-011", cidade="SÃO PAULO", uf="SP",
                logradouro="Rua Professor Artur Ramos",
            ),
        })
        await _extrair(scoped, storage, cid, did, _comprovante(errado), cep_lookup=cep_lookup)
        row = _cliente(scoped, cid)
        assert (row["endereco_cidade"], row["endereco_uf"]) == ("SÃO PAULO", "SP")
        # logradouro stays the document's own read even though the CEP's
        # own logradouro differs — only cidade/uf are CEP-authoritative.
        assert row["endereco_logradouro"] == "R PROF ARTUR RAMOS"

    @pytest.mark.asyncio
    async def test_no_cep_lookup_configured_keeps_pre_existing_behaviour(self, client, scoped):
        """`cep_lookup=None` (every pre-existing caller) must reproduce the
        exact pre-F3 result — no enrichment attempted."""
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco", cliente={"nome": "Ana Paula Souza"}
        )
        await _extrair(scoped, storage, cid, did, _comprovante(), cep_lookup=None)
        row = _cliente(scoped, cid)
        assert (row["endereco_cidade"], row["endereco_uf"]) == ("SÃO PAULO", "SP")

    @pytest.mark.asyncio
    async def test_cep_that_does_not_resolve_leaves_document_values_untouched(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco", cliente={"nome": "Ana Paula Souza"}
        )
        cep_lookup = FakeCepLookupAdapter()  # empty — nothing resolves
        await _extrair(scoped, storage, cid, did, _comprovante(), cep_lookup=cep_lookup)
        row = _cliente(scoped, cid)
        assert (row["endereco_cidade"], row["endereco_uf"]) == ("SÃO PAULO", "SP")

    @pytest.mark.asyncio
    async def test_a_suspiciously_long_cidade_is_withheld_even_without_cep_lookup(
        self, client, scoped
    ):
        """Regression: a `comprovante_endereco` read once dumped a 57-char
        whole-address string into `cidade` — this must never persist,
        `cep_lookup` configured or not."""
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco", cliente={"nome": "Ana Paula Souza"}
        )
        suspeito = EnderecoLido(
            cep="01454-011", logradouro="R PROF ARTUR RAMOS", numero="123",
            complemento="APTO 12", bairro="JARDIM PAULISTANO",
            cidade="R PROF ARTUR RAMOS 123 APTO 12 JARDIM PAULISTANO SAO PAULO SP",
            uf="SP", titular="ANA PAULA SOUZA", confianca="alta", rotulo="ENDERECO",
        )
        await _extrair(scoped, storage, cid, did, _comprovante(suspeito))
        row = _cliente(scoped, cid)
        assert row["endereco_cidade"] is None

    @pytest.mark.asyncio
    async def test_a_cidade_carrying_digits_is_withheld(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco", cliente={"nome": "Ana Paula Souza"}
        )
        suspeito = EnderecoLido(
            cep="01454-011", logradouro="R PROF ARTUR RAMOS", numero="123",
            complemento=None, bairro=None, cidade="CEP 01454-011", uf="SP",
            titular="ANA PAULA SOUZA", confianca="alta", rotulo="ENDERECO",
        )
        await _extrair(scoped, storage, cid, did, _comprovante(suspeito))
        row = _cliente(scoped, cid)
        assert row["endereco_cidade"] is None


def _cep_com_bairro(bairro="VILA EXEMPLO") -> FakeCepLookupAdapter:
    return FakeCepLookupAdapter({
        "01454-011": CepEndereco(
            cep="01454-011", cidade="SÃO PAULO", uf="SP",
            logradouro="Rua Professor Artur Ramos", bairro=bairro,
        ),
    })


SEM_BAIRRO = EnderecoLido(
    cep="01454-011", logradouro="R PROF ARTUR RAMOS", numero="123", complemento="APTO 12",
    bairro=None, cidade="SÃO PAULO", uf="SP",
    titular="ANA PAULA SOUZA", confianca="alta", rotulo="ENDERECO",
)


class TestEnderecoBairroViaCep:
    """Extraction defect (live prod test, 2026-10-03): two buyers had every
    address part but the bairro, so the contract gate blocked on "Endereço
    completo". The CEP lookup fills ONLY a missing bairro (`endereco_bairro_
    origem='cep'`, migration 194); a document's own bairro always wins."""

    @pytest.mark.asyncio
    async def test_a_document_without_bairro_gets_the_ceps_bairro(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco", cliente={"nome": "Ana Paula Souza"}
        )
        await _extrair(
            scoped, storage, cid, did, _comprovante(SEM_BAIRRO), cep_lookup=_cep_com_bairro()
        )
        row = _cliente(scoped, cid)
        assert row["endereco_bairro"] == "VILA EXEMPLO"
        assert row["endereco_bairro_origem"] == "cep"
        assert row["endereco_origem"] == "comprovante_endereco"
        # The document row keeps what the document itself printed: nothing.
        assert _documento(scoped, did)["extracao_endereco_bairro"] is None

    @pytest.mark.asyncio
    async def test_the_documents_own_bairro_wins_over_a_different_cep_bairro(
        self, client, scoped
    ):
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco", cliente={"nome": "Ana Paula Souza"}
        )
        await _extrair(
            scoped, storage, cid, did, _comprovante(), cep_lookup=_cep_com_bairro("GENERICO")
        )
        row = _cliente(scoped, cid)
        assert row["endereco_bairro"] == "JARDIM PAULISTANO"
        assert row.get("endereco_bairro_origem") is None

    @pytest.mark.asyncio
    async def test_a_record_missing_only_the_bairro_is_gap_filled_without_a_conflict(
        self, client, scoped
    ):
        """The prod shape: the address is already on file (an earlier
        document) with bairro NULL; a reading of the same address now
        supplies it — a gap-fill, never a second-opinion conflict."""
        outro_doc = str(uuid4())
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco",
            cliente={
                "nome": "Ana Paula Souza",
                "endereco_cep": "01454-011", "endereco_logradouro": "R PROF ARTUR RAMOS",
                "endereco_numero": "123", "endereco_complemento": "APTO 12",
                "endereco_bairro": None, "endereco_cidade": "SÃO PAULO", "endereco_uf": "SP",
                "endereco_origem": "comprovante_endereco",
                "endereco_documento_id": outro_doc,
            },
        )
        await _extrair(
            scoped, storage, cid, did, _comprovante(SEM_BAIRRO), cep_lookup=_cep_com_bairro()
        )
        row = _cliente(scoped, cid)
        assert row["endereco_bairro"] == "VILA EXEMPLO"
        assert row["endereco_bairro_origem"] == "cep"
        # The group's own provenance is untouched — only the bairro moved.
        assert row["endereco_documento_id"] == outro_doc
        assert [c for c in _conflitos(scoped) if c["status"] == "pendente"] == []

    @pytest.mark.asyncio
    async def test_a_cep_bairro_never_disputes_a_recorded_document_bairro(
        self, client, scoped
    ):
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco",
            cliente={
                "nome": "Ana Paula Souza",
                "endereco_cep": "01454-011", "endereco_logradouro": "R PROF ARTUR RAMOS",
                "endereco_numero": "123", "endereco_complemento": "APTO 12",
                "endereco_bairro": "JARDIM PAULISTANO", "endereco_cidade": "SÃO PAULO",
                "endereco_uf": "SP", "endereco_origem": "comprovante_endereco",
                "endereco_documento_id": str(uuid4()),
            },
        )
        await _extrair(
            scoped, storage, cid, did, _comprovante(SEM_BAIRRO), cep_lookup=_cep_com_bairro()
        )
        row = _cliente(scoped, cid)
        assert row["endereco_bairro"] == "JARDIM PAULISTANO"
        assert row.get("endereco_bairro_origem") is None
        assert _conflitos(scoped) == []

    @pytest.mark.asyncio
    async def test_a_printed_bairro_replaces_a_cep_bairro(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco",
            cliente={
                "nome": "Ana Paula Souza",
                "endereco_cep": "01454-011", "endereco_logradouro": "R PROF ARTUR RAMOS",
                "endereco_numero": "123", "endereco_complemento": "APTO 12",
                "endereco_bairro": "GENERICO", "endereco_bairro_origem": "cep",
                "endereco_cidade": "SÃO PAULO", "endereco_uf": "SP",
                "endereco_origem": "comprovante_endereco",
                "endereco_documento_id": str(uuid4()),
                "endereco_confirmado_em": _old(5),
            },
        )
        await _extrair(scoped, storage, cid, did, _comprovante(), cep_lookup=_cep_com_bairro())
        row = _cliente(scoped, cid)
        assert row["endereco_bairro"] == "JARDIM PAULISTANO"
        assert row["endereco_bairro_origem"] == "comprovante_endereco"
        assert [c for c in _conflitos(scoped) if c["status"] == "pendente"] == []

    @pytest.mark.asyncio
    async def test_a_manual_address_is_never_gap_filled(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco",
            cliente={
                "nome": "Ana Paula Souza",
                "endereco_cep": "01454-011", "endereco_logradouro": "R PROF ARTUR RAMOS",
                "endereco_numero": "123", "endereco_complemento": "APTO 12",
                "endereco_bairro": None, "endereco_cidade": "SÃO PAULO", "endereco_uf": "SP",
                "endereco_origem": "manual",
            },
        )
        await _extrair(
            scoped, storage, cid, did, _comprovante(SEM_BAIRRO), cep_lookup=_cep_com_bairro()
        )
        assert _cliente(scoped, cid)["endereco_bairro"] is None

    @pytest.mark.asyncio
    async def test_a_conflict_carries_the_cep_origin_and_resolving_writes_it_back(
        self, client, scoped
    ):
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco",
            cliente={
                "nome": "Ana Paula Souza",
                "endereco_cep": "09999-000", "endereco_logradouro": "RUA OUTRA",
                "endereco_numero": "9", "endereco_cidade": "SANTOS", "endereco_uf": "SP",
                "endereco_origem": "manual",
            },
        )
        await _extrair(
            scoped, storage, cid, did, _comprovante(SEM_BAIRRO), cep_lookup=_cep_com_bairro()
        )
        pendentes = [c for c in _conflitos(scoped) if c["status"] == "pendente"]
        assert len(pendentes) == 1
        assert json.loads(pendentes[0]["valor_proposto"])["bairro_origem"] == "cep"
        svc.resolver_conflito(
            scoped, ORG_UUID, UUID(str(pendentes[0]["id"])), aceitar=True, decidido_por=None,
        )
        row = _cliente(scoped, cid)
        assert (row["endereco_bairro"], row["endereco_bairro_origem"]) == ("VILA EXEMPLO", "cep")


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

    def test_own_bill_vs_bank_form_on_file_needs_a_human(self, client, scoped):
        """🔴 Live prod test 2026-10-01 (deal 875): the buyer's own older
        utility bill (holder verified as the buyer) replaced the bank-form
        address the signed contract used, because the form's holder read as
        `None`. A `ficha_cadastral` address IS the party's own declaration —
        two of the party's own documents disagreeing need a human; the
        on-file address is kept meanwhile (a gap, never a wrong value)."""
        cid, ficha, doc_novo = str(uuid4()), str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(
            cid, nome="Ana Paula Souza",
            endereco_cep="04000-000", endereco_logradouro="RUA B",
            endereco_origem="ficha_cadastral", endereco_documento_id=ficha,
        )])
        scoped.set_table_data("cliente_documentos", [
            {**self._doc(ficha), "tipo_documento": "ficha_cadastral"},
            self._doc(doc_novo, "ANA PAULA SOUZA"),
        ])
        scoped.set_table_data("cliente_campo_conflitos", [])

        aplicado, conflito = svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "comprovante_endereco", self._partes_novas(),
            titular_documento=None, confianca="alta", documento_id=UUID(doc_novo),
        )

        assert aplicado is False
        assert conflito is not None  # pendente — a human decides
        row = _cliente(scoped, cid)
        assert (row["endereco_cep"], row["endereco_logradouro"]) == ("04000-000", "RUA B")

    def test_bank_form_proposal_vs_own_bill_on_file_needs_a_human(self, client, scoped):
        """The reverse order (bill on file, the form re-read proposes)."""
        cid, doc_velho, ficha = str(uuid4()), str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(
            cid, nome="Ana Paula Souza",
            endereco_cep="04000-000", endereco_logradouro="RUA B",
            endereco_origem="comprovante_endereco", endereco_documento_id=doc_velho,
        )])
        scoped.set_table_data("cliente_documentos", [
            self._doc(doc_velho, "ANA PAULA SOUZA"),
            {**self._doc(ficha), "tipo_documento": "ficha_cadastral"},
        ])
        scoped.set_table_data("cliente_campo_conflitos", [])

        aplicado, conflito = svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "ficha_cadastral", self._partes_novas(),
            titular_documento=None, confianca="alta", documento_id=UUID(ficha),
        )

        assert aplicado is False
        assert conflito is not None
        row = _cliente(scoped, cid)
        assert row["endereco_logradouro"] == "RUA B"

    def test_bank_form_beats_a_co_partys_bill(self, client, scoped):
        """A co-party's bill (R2 household evidence) is weaker than the
        party's own bank form — the form on file is kept, automatically."""
        cid, outro, ficha, doc_novo = str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4())
        atendimento = str(uuid4())
        scoped.set_table_data("clientes", [
            cliente_row(
                cid, nome="Ana Paula Souza",
                endereco_cep="04000-000", endereco_logradouro="RUA B",
                endereco_origem="ficha_cadastral", endereco_documento_id=ficha,
            ),
            cliente_row(outro, nome="Carlos Mendes"),
        ])
        scoped.set_table_data("atendimento_partes", [
            {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": atendimento, "cliente_id": cid},
            {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": atendimento, "cliente_id": outro},
        ])
        scoped.set_table_data("cliente_documentos", [
            {**self._doc(ficha), "tipo_documento": "ficha_cadastral"},
            self._doc(doc_novo, "CARLOS MENDES"),
        ])
        scoped.set_table_data("cliente_campo_conflitos", [])

        aplicado, conflito = svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "comprovante_endereco", self._partes_novas(),
            titular_documento=None, confianca="alta", documento_id=UUID(doc_novo),
        )

        assert aplicado is False
        assert conflito is None
        row = _cliente(scoped, cid)
        assert row["endereco_logradouro"] == "RUA B"
        (c,) = _conflitos(scoped)
        assert c["status"] == "resolvido_automatico"

    def test_both_sides_unverified_but_own_address_on_file_auto_rejects(
        self, client, scoped,
    ):
        """🔴 R2 (owner directive, 2026-09-30): neither holder verifies as
        the party, the spouse, or another atendimento party — but the
        on-file address already came from this cliente's OWN document
        (`endereco_origem="comprovante_endereco"`, not the R3 household
        derivative). A definitely-unrelated new holder no longer needs a
        human to reject: the cliente's own document outranks a stranger's."""
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
        assert conflito is None  # resolved automatically, never pendente
        row = _cliente(scoped, cid)
        assert row["endereco_logradouro"] == "RUA B"  # untouched
        (c,) = _conflitos(scoped)
        assert c["status"] == "resolvido_automatico"
        assert "outra_pessoa" in c["motivo_resolucao"]

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


class TestSweepNeverRead:
    """Class 4 of `_candidatos_varredura`: `extracao_status IS NULL` for a
    type that has a reader TODAY — a document uploaded before its reader
    shipped (every `cin` before `fontes.FONTES["cin"]`, prod 2026-09-30)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tipo", ["cin", "rg"])
    async def test_a_never_read_extractable_document_is_read_by_the_sweep(
        self, client, scoped, tipo
    ):
        assert tipo in svc.TIPOS_EXTRAIVEIS
        _cid, did, storage = await _setup(scoped, tipo=tipo, doc_extra={
            "extracao_status": None, "extracao_em": None, "created_at": _old(600),
        })
        out = await svc.varrer_extracoes_pendentes(scoped, storage, extractor_factory=_fabrica)
        assert (out["encontrados"], out["retomados"]) == (1, 1)
        doc = _documento(scoped, did)
        assert doc["extracao_status"] == "ok"
        assert doc["extracao_tentativas"] == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tipo", ["outro", "contrato"])
    async def test_an_intentionally_unread_type_is_never_picked(self, client, scoped, tipo):
        assert tipo not in svc.TIPOS_EXTRAIVEIS
        _cid, did, storage = await _setup(scoped, tipo=tipo, doc_extra={
            "extracao_status": None, "extracao_em": None, "created_at": _old(600),
        })
        out = await svc.varrer_extracoes_pendentes(scoped, storage, extractor_factory=_fabrica)
        assert out["encontrados"] == 0
        assert _documento(scoped, did)["extracao_status"] is None

    @pytest.mark.asyncio
    async def test_a_just_uploaded_never_read_document_is_not_raced(self, client, scoped):
        _cid, _did, storage = await _setup(scoped, tipo="cin", doc_extra={
            "extracao_status": None, "extracao_em": None, "created_at": _old(1),
        })
        out = await svc.varrer_extracoes_pendentes(scoped, storage, extractor_factory=_fabrica)
        assert out["encontrados"] == 0

    @pytest.mark.asyncio
    async def test_a_deleted_never_read_document_is_not_picked(self, client, scoped):
        _cid, _did, storage = await _setup(scoped, tipo="cin", doc_extra={
            "extracao_status": None, "extracao_em": None, "created_at": _old(600),
            "deleted_at": _old(30),
        })
        out = await svc.varrer_extracoes_pendentes(scoped, storage, extractor_factory=_fabrica)
        assert out["encontrados"] == 0

    @pytest.mark.asyncio
    async def test_the_backlog_is_bounded_by_limite_oldest_first(self, client, scoped):
        cid, did, storage = await _setup(scoped, tipo="cin", doc_extra={
            "extracao_status": None, "extracao_em": None, "created_at": _old(600),
        })
        base = _documento(scoped, did)
        linhas, por_idade = [], {}
        for idade in (900, 300, 700):
            outro_id = str(uuid4())
            path = f"{ORG_ID}/clientes/{cid}/{outro_id}"
            await storage.put(
                bucket=BUCKET, key=path, data=b"%PDF-1.4", content_type="application/pdf",
            )
            por_idade[idade] = outro_id
            linhas.append({**base, "id": outro_id, "storage_path": path, "created_at": _old(idade)})
        scoped.set_table_data("cliente_documentos", [base, *linhas])
        candidatos = svc._candidatos_varredura(scoped, 2)
        # The bound holds and the merged list is oldest-first. (The seed
        # `MockSupabaseClient` accepts `.order()` without applying it, so
        # WHICH two of the four the SQL `ORDER BY created_at` keeps is a
        # PostgREST behaviour this mock cannot pin; the ids below are only
        # constrained to be real never-read candidates.)
        assert len(candidatos) == 2
        assert {c["id"] for c in candidatos} <= {did, *por_idade.values()}
        datas = [c["created_at"] for c in candidatos]
        assert datas == sorted(datas)


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


# ─── R1: re-resolution on new evidence (owner directive, 2026-09-30) ────────


class TestR1RevalidacaoAposNovaEvidencia:
    """Live-test evidence, 5 historical deals re-run on prod, 2026-09-30: a
    pending conflict opened with nothing to compare a holder against must
    settle the moment that evidence lands — on THIS cliente or on ANOTHER
    party of the same atendimento — without anyone re-opening the card."""

    @pytest.mark.asyncio
    async def test_a_name_arriving_later_settles_this_persons_own_pending_address(
        self, client, scoped,
    ):
        cid, did_bill, storage = await _setup(
            scoped, tipo="comprovante_endereco", cliente={"nome": "Comprador 1"},
        )
        sem_nome_ainda = EnderecoLido(
            cep="01454-011", logradouro="R PROF ARTUR RAMOS", numero="123",
            complemento=None, bairro=None, cidade=None, uf=None,
            titular="CARLOS PEREIRA", confianca="baixa", rotulo="ENDERECO",
        )
        await _extrair(scoped, storage, cid, did_bill, _comprovante(sem_nome_ainda))
        assert _cliente(scoped, cid).get("endereco_cep") is None
        (pendente,) = _conflitos(scoped)
        assert pendente["status"] == "pendente"

        # The SAME person's CNH arrives later, naming them "CARLOS PEREIRA"
        # — the bill's holder all along, unreadable as a match until now.
        did_cnh = str(uuid4())
        path_cnh = f"{ORG_ID}/clientes/{cid}/{did_cnh}"
        scoped.table("cliente_documentos").insert({
            "id": did_cnh, "org_id": ORG_ID, "cliente_id": cid,
            "storage_path": path_cnh, "nome_original": "cnh.pdf",
            "mime_type": "application/pdf", "tipo_documento": "cnh",
            "deleted_at": None, "extracao_status": "pendente",
            "extracao_tentativas": 0, "created_at": _old(1),
        }).execute()
        await storage.put(bucket=BUCKET, key=path_cnh, data=b"%PDF-1.4", content_type="application/pdf")
        await _extrair(scoped, storage, cid, did_cnh, IdentityFields(
            nome="CARLOS PEREIRA", nome_confianca=A, source=TextSource.TEXT_LAYER,
        ))

        row = _cliente(scoped, cid)
        assert row["nome_oficial"] == "CARLOS PEREIRA"
        assert (row["endereco_cep"], row["endereco_logradouro"]) == (
            "01454-011", "R PROF ARTUR RAMOS",
        )
        estados = {c["campo"]: c["status"] for c in _conflitos(scoped)}
        assert estados["endereco"] == "resolvido_automatico"

    @pytest.mark.asyncio
    async def test_a_co_partys_name_arriving_later_settles_a_bills_holder_check(
        self, client, scoped,
    ):
        """Case (b): the bill's holder is ANOTHER party of the same deal —
        not this cliente, not their spouse — whose own name had not been
        read yet at the time the bill was uploaded."""
        outra, atd = str(uuid4()), str(uuid4())
        cid, did_bill, storage = await _setup(
            scoped, tipo="comprovante_endereco", cliente={"nome": "Comprador 1"},
            outros=[cliente_row(outra, nome="Comprador 2")],
        )
        scoped.set_table_data("atendimentos", [{"id": atd, "org_id": ORG_ID, "cliente_id": cid}])
        scoped.set_table_data("atendimento_partes", [
            {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": atd,
             "cliente_id": outra, "lado": "comprador", "papel": "comprador", "ordem": 0},
        ])
        titular_co_parte = EnderecoLido(
            cep="01454-011", logradouro="R PROF ARTUR RAMOS", numero="123",
            complemento=None, bairro=None, cidade=None, uf=None,
            titular="DANIELA FERREIRA LIMA", confianca="baixa", rotulo="ENDERECO",
        )
        await _extrair(scoped, storage, cid, did_bill, _comprovante(titular_co_parte))
        assert _cliente(scoped, cid).get("endereco_cep") is None
        assert _cliente(scoped, outra).get("endereco_cep") is None
        (pendente,) = _conflitos(scoped)
        assert pendente["status"] == "pendente"

        # The co-party's own CNH arrives later.
        did_cnh = str(uuid4())
        path_cnh = f"{ORG_ID}/clientes/{outra}/{did_cnh}"
        scoped.table("cliente_documentos").insert({
            "id": did_cnh, "org_id": ORG_ID, "cliente_id": outra,
            "storage_path": path_cnh, "nome_original": "cnh.pdf",
            "mime_type": "application/pdf", "tipo_documento": "cnh",
            "deleted_at": None, "extracao_status": "pendente",
            "extracao_tentativas": 0, "created_at": _old(1),
        }).execute()
        await storage.put(bucket=BUCKET, key=path_cnh, data=b"%PDF-1.4", content_type="application/pdf")
        await _extrair(scoped, storage, outra, did_cnh, IdentityFields(
            nome="DANIELA FERREIRA LIMA", nome_confianca=A, source=TextSource.TEXT_LAYER,
        ))

        # The address was opened as a conflict on `cid` (the card it was
        # uploaded onto) — the co-party's arriving name settles THAT row.
        row = _cliente(scoped, cid)
        assert (row["endereco_cep"], row["endereco_logradouro"]) == (
            "01454-011", "R PROF ARTUR RAMOS",
        )
        estados = {c["campo"]: c["status"] for c in _conflitos(scoped) if c["cliente_id"] == cid}
        assert estados["endereco"] == "resolvido_automatico"


# ─── R3: household address propagation (owner directive, 2026-09-30) ───────


class TestR3PropagacaoEnderecoDomicilio:
    def _linkado(self, cid, esposo, **extra) -> dict:
        return cliente_row(cid, conjuge_cliente_id=esposo, **extra)

    def test_a_spouse_with_no_address_inherits_the_others_own_document_address(
        self, client, scoped,
    ):
        cid, esposo = str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [
            self._linkado(cid, esposo, nome="Ana"),
            cliente_row(
                esposo, nome="Bruno", conjuge_cliente_id=cid,
                endereco_cep="01454-011", endereco_logradouro="R PROF ARTUR RAMOS",
                endereco_origem="comprovante_endereco", endereco_documento_id=str(uuid4()),
            ),
        ])
        svc.propagar_endereco_domicilio(scoped, ORG_UUID, UUID(cid))
        row = _cliente(scoped, cid)
        assert (row["endereco_cep"], row["endereco_logradouro"]) == (
            "01454-011", "R PROF ARTUR RAMOS",
        )
        assert row["endereco_origem"] == svc.ORIGEM_CONJUGE_DOMICILIO
        assert row["endereco_confirmado_em"] is None  # machine-pending, like any D1 write

    def test_never_overwrites_a_spouses_own_address(self, client, scoped):
        cid, esposo = str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [
            self._linkado(
                cid, esposo, nome="Ana",
                endereco_cep="04000-000", endereco_logradouro="RUA B",
                endereco_origem="cnh",
            ),
            cliente_row(
                esposo, nome="Bruno", conjuge_cliente_id=cid,
                endereco_cep="01454-011", endereco_logradouro="R PROF ARTUR RAMOS",
                endereco_origem="comprovante_endereco",
            ),
        ])
        svc.propagar_endereco_domicilio(scoped, ORG_UUID, UUID(cid))
        row = _cliente(scoped, cid)
        assert (row["endereco_cep"], row["endereco_logradouro"]) == ("04000-000", "RUA B")
        assert row["endereco_origem"] == "cnh"  # untouched — a real document of their own

    def test_a_derived_address_never_re_propagates_as_a_source(self, client, scoped):
        """Tier: `conjuge_domicilio` is BELOW any own document — a cliente
        whose OWN address is itself a derived copy never becomes another
        spouse's source (a third link, or the same pair re-evaluated)."""
        cid, esposo = str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [
            self._linkado(cid, esposo, nome="Ana"),
            cliente_row(
                esposo, nome="Bruno", conjuge_cliente_id=cid,
                endereco_cep="01454-011", endereco_logradouro="R PROF ARTUR RAMOS",
                endereco_origem=svc.ORIGEM_CONJUGE_DOMICILIO,
            ),
        ])
        svc.propagar_endereco_domicilio(scoped, ORG_UUID, UUID(cid))
        assert _cliente(scoped, cid).get("endereco_cep") is None

    def test_retracts_when_the_source_no_longer_qualifies(self, client, scoped):
        cid, esposo = str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [
            self._linkado(
                cid, esposo, nome="Ana",
                endereco_cep="01454-011", endereco_logradouro="R PROF ARTUR RAMOS",
                endereco_origem=svc.ORIGEM_CONJUGE_DOMICILIO,
            ),
            # The spouse's OWN address was since cleared (retracted).
            cliente_row(esposo, nome="Bruno", conjuge_cliente_id=cid),
        ])
        svc.propagar_endereco_domicilio(scoped, ORG_UUID, UUID(cid))
        row = _cliente(scoped, cid)
        assert row.get("endereco_cep") is None
        assert row.get("endereco_origem") is None

    def test_no_spouse_link_is_a_no_op(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Ana")])
        svc.propagar_endereco_domicilio(scoped, ORG_UUID, UUID(cid))
        assert _cliente(scoped, cid).get("endereco_cep") is None

    @pytest.mark.asyncio
    async def test_end_to_end_via_extraction_the_unrelated_read_still_triggers_propagation(
        self, client, scoped,
    ):
        """R1+R3 together: extracting a document that has NOTHING to do with
        addresses still runs `revalidar_negociacao`, which propagates the
        already-linked spouse's own address onto this empty half."""
        esposo = str(uuid4())
        cid, did, storage = await _setup(
            scoped, tipo="cnh", cliente={"nome": "Ana", "conjuge_cliente_id": esposo},
            outros=[cliente_row(
                esposo, nome="Bruno", conjuge_cliente_id="__PLACEHOLDER__",
                endereco_cep="01454-011", endereco_logradouro="R PROF ARTUR RAMOS",
                endereco_origem="comprovante_endereco",
            )],
        )
        # `_setup` mints `cid` itself (unknown before the call) — patch the
        # spouse's back-link to it now that it's known.
        scoped.table("clientes").update({"conjuge_cliente_id": cid}).eq("id", esposo).execute()
        await _extrair(scoped, storage, cid, did, IdentityFields(
            profissao="engenheira", profissao_confianca=A, source=TextSource.TEXT_LAYER,
        ))
        row = _cliente(scoped, cid)
        assert (row["endereco_cep"], row["endereco_logradouro"]) == (
            "01454-011", "R PROF ARTUR RAMOS",
        )
        assert row["endereco_origem"] == svc.ORIGEM_CONJUGE_DOMICILIO


# ─── R4: cross-party identity rule (owner directive, 2026-09-30) ───────────


class TestR4OutraPessoa:
    @pytest.mark.asyncio
    async def test_a_name_matching_another_party_is_rejected_not_left_pending(
        self, client, scoped,
    ):
        outra, atd = str(uuid4()), str(uuid4())
        cid, did, storage = await _setup(
            scoped, tipo="certidao_nascimento", cliente={"nome": "Comprador 1"},
            outros=[cliente_row(outra, nome="Bruno Alves", nome_oficial="BRUNO ALVES")],
        )
        scoped.set_table_data("atendimentos", [{"id": atd, "org_id": ORG_ID, "cliente_id": cid}])
        scoped.set_table_data("atendimento_partes", [
            {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": atd,
             "cliente_id": outra, "lado": "comprador", "papel": "comprador", "ordem": 0},
        ])
        await _extrair(scoped, storage, cid, did, IdentityFields(
            nome="BRUNO ALVES", nome_confianca=A, source=TextSource.TEXT_LAYER,
        ))
        row = _cliente(scoped, cid)
        assert row.get("nome_oficial") is None  # rejected, never filled
        assert _documento(scoped, did)["extracao_aviso"] == "documento_de_outra_parte"
        estados = {(c["campo"], c["status"]): c["motivo_resolucao"] for c in _conflitos(scoped)}
        motivo = estados[("nome_oficial", "resolvido_automatico")]
        assert "outra_pessoa" in motivo and "comprador" in motivo

    @pytest.mark.asyncio
    async def test_a_cpf_matching_another_partys_cpf_is_rejected(self, client, scoped):
        outra, atd = str(uuid4()), str(uuid4())
        cid, did, storage = await _setup(
            scoped, tipo="rg", cliente={"nome": "Comprador 1"},
            outros=[cliente_row(outra, nome="Bruno Alves", cpf="412.954.238-98")],
        )
        scoped.set_table_data("atendimentos", [{"id": atd, "org_id": ORG_ID, "cliente_id": cid}])
        scoped.set_table_data("atendimento_partes", [
            {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": atd,
             "cliente_id": outra, "lado": "comprador", "papel": "vendedor", "ordem": 0},
        ])
        await _extrair(scoped, storage, cid, did, IdentityFields(
            nome="Comprador 1", cpf="412.954.238-98", cpf_confianca=A,
            source=TextSource.TEXT_LAYER,
        ))
        row = _cliente(scoped, cid)
        assert row.get("cpf") is None
        assert _documento(scoped, did)["extracao_aviso"] == "documento_de_outra_parte"

    @pytest.mark.asyncio
    async def test_no_clash_with_any_other_party_fills_normally(self, client, scoped):
        """Regression: a name that matches NOBODY else in the negotiation
        is unaffected by R4 — the ordinary fill-empty path still runs."""
        outra, atd = str(uuid4()), str(uuid4())
        cid, did, storage = await _setup(
            scoped, tipo="rg", cliente={"nome": "Comprador 1"},
            outros=[cliente_row(outra, nome="Bruno Alves", nome_oficial="BRUNO ALVES")],
        )
        scoped.set_table_data("atendimentos", [{"id": atd, "org_id": ORG_ID, "cliente_id": cid}])
        scoped.set_table_data("atendimento_partes", [
            {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": atd,
             "cliente_id": outra, "lado": "comprador", "papel": "comprador", "ordem": 0},
        ])
        await _extrair(scoped, storage, cid, did, IdentityFields(
            nome="COMPRADOR UM DA SILVA", nome_confianca=A, source=TextSource.TEXT_LAYER,
        ))
        row = _cliente(scoped, cid)
        assert row["nome_oficial"] == "COMPRADOR UM DA SILVA"
        assert _documento(scoped, did).get("extracao_aviso") is None


# ─── R5: two-person documents withhold every per-person field ──────────────


class TestR5DoisConjugesTodosOsCampos:
    @pytest.mark.asyncio
    async def test_titular_unresolved_withholds_every_per_person_field(self, client, scoped):
        """🔴 Regression (live prod test, 2026-09-30): a divorce certidão's
        flat reading carried the EX-SPOUSE's RG onto the wrong card. The
        just-merged fix (950c2c255) withheld only `cpf` when the titular
        attribution can't resolve; R5 extends it to every `CAMPOS_POR_
        PESSOA` field (rg included) — none of a two-person document's
        per-person facts may reach a cliente without attribution."""
        almir = ConjugeLido(
            nome="ALMIR TEIXEIRA DA COSTA", cpf="303.102.653-55", titular=False,
        )
        mariana = ConjugeLido(
            nome="MARIANA PELLEGRINI RANGEL", cpf="478.982.096-30", titular=False,
        )
        cid, did, storage = await _setup(
            scoped, tipo="certidao_casamento", cliente={"nome": "Card sem nome ainda"},
        )
        fields = IdentityFields(
            nome=None, cpf=None,
            rg="9876543210", rg_confianca=A, rg_rotulo="RG",
            genero="Feminino", genero_confianca=A,
            data_nascimento=date(1964, 4, 20), data_nascimento_confianca=A,
            profissao="professora", profissao_confianca=A,
            estado_civil="divorciado", estado_civil_confianca=A,
            regime_bens="comunhao_parcial", regime_bens_confianca=A,
            conjuges=(almir, mariana),
            source=TextSource.TEXT_LAYER,
        )
        await _extrair(scoped, storage, cid, did, fields)
        row = _cliente(scoped, cid)
        assert row.get("nome_oficial") is None
        assert row.get("cpf") is None
        assert row.get("rg") is None
        assert row.get("genero") is None
        assert row.get("data_nascimento") is None
        assert row.get("profissao") is None
        # Couple-level facts (not per-person) still land — the flat reading
        # IS authoritative for those, per `CAMPOS_POR_PESSOA`'s own scope.
        assert row.get("estado_civil") == "divorciado"
        assert row.get("regime_bens") == "comunhao_parcial"
        assert _conflitos(scoped) == []


class TestConflitosPendentesPaginados:
    def test_fila_org_wide_passa_do_teto_de_1000_linhas(self):
        """One unpaged read capped the queue (and the identifier backfill that
        re-resolves it) at PostgREST's 1000 rows — silently."""
        from uuid import uuid4

        from noctusai_lib.testing import MockSupabaseClient

        from app.modules.card_hub import identidade_extracao_service as svc

        org = uuid4()
        db = MockSupabaseClient(schema="social_wiring")
        db.set_table_data(svc.CONFLITOS_TABLE, [
            {"id": f"{i:05d}", "org_id": str(org), "status": "pendente",
             "cliente_id": "c", "campo": "cpf", "created_at": f"2026-01-01T00:{i // 60 % 60:02d}:{i % 60:02d}"}
            for i in range(1205)
        ] + [{"id": "x", "org_id": str(org), "status": "resolvido", "cliente_id": "c", "campo": "cpf"}])
        assert len(svc.conflitos_pendentes(db, org)) == 1205
