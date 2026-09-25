"""`crednet_service.aplicar_leitura` — the whole §C4 sequence (P0c contract).

WHAT THESE PIN
--------------
- (a) the document is marked BEFORE the cliente is touched;
- (b) D1 apply: empty fields fill machine-pending, a disagreeing field opens
  a `cliente_campo_conflitos` row and never overwrites;
- `cpf` is gated on `cpf_valido` — an invalid check digit is recorded on the
  document but never applied to `clientes.cpf`;
- (c) a valid-CNPJ participação upserts `empresas` (insert-only razao_social,
  `dados_origem='serasa_crednet'`, NEVER `situacao_cadastral`) and a
  `cliente_empresa_participacoes` row (`origem='serasa_crednet'`); an
  invalid-CNPJ participação is never linked, only recorded in
  `extracao_crednet.participacoes_rejeitadas`;
- a SECOND read for the same CNPJ never touches an existing empresa;
- (d) `certidoes.service.registrar_serasa_de_crednet` runs off the same doc.

Imports the seed's real `serasa_crednet` dataclasses (S1, merged) — the
extractor is injected via `FakeCrednetExtractor(result=...)`
(`tests/support/document_fakes.py`), per DI, never a monkeypatch.
"""
from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

import pytest
from noctusai_lib.testing.mocks import MockSupabaseClient

from app.dependencies import coerce_org_uuid
from app.modules.card_hub import crednet_service
from tests.support.document_fakes import (
    ALTA,
    CNPJ_INVALIDO,
    CNPJ_VALIDO,
    CNPJ_VALIDO_OUTRO,
    CPF_VALIDO,
    CrednetFields,
    FakeCrednetExtractor,
    NENHUMA,
    OcorrenciaCrednet,
    ParticipacaoCrednet,
)

ORG_ID = coerce_org_uuid("test-org-crednet")

SEM_OCORRENCIA = OcorrenciaCrednet(constam=False, quantidade=0)


@pytest.fixture
def client():
    mock = MockSupabaseClient()
    scoped = mock.schema("social_wiring")
    for table in (
        "clientes", "cliente_documentos", "empresas",
        "cliente_empresa_participacoes", "cliente_campo_conflitos",
        "empresa_campo_conflitos", "certidao_consultas", "certidao_resultados",
    ):
        scoped.set_table_data(table, [])
    return scoped


def _cliente(cid, **extra) -> dict:
    row = {
        "id": cid, "org_id": str(ORG_ID), "nome": "Fulana",
        "nome_oficial": None, "nome_oficial_origem": None,
        "cpf": None, "cpf_origem": None,
        "data_nascimento": None, "data_nascimento_origem": None,
        "nome_mae": None, "nome_mae_origem": None,
        "nome_mae_confirmado_em": None,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    row.update(extra)
    return row


def _documento(did, cid, **extra) -> dict:
    row = {
        "id": did, "org_id": str(ORG_ID), "cliente_id": cid,
        "storage_path": f"{ORG_ID}/clientes/{cid}/{did}",
        "nome_original": "crednet.pdf", "mime_type": "application/pdf",
        "tamanho_bytes": 1024, "tipo_documento": "serasa_crednet",
        "deleted_at": None, "created_at": "2026-01-01T00:00:00+00:00",
    }
    row.update(extra)
    return row


def _fields(**overrides) -> CrednetFields:
    base = dict(
        consulta_em=datetime(2026, 9, 1, 10, 0, 0),
        protocolo="1234567",
        cpf=CPF_VALIDO, cpf_valido=True,
        nome="FULANA DE TESTE", nome_mae="CICLANA DE TESTE",
        data_nascimento=date(1990, 1, 1),
        pendencias_internas=SEM_OCORRENCIA,
        pendencias_financeiras=SEM_OCORRENCIA,
        protesto_estadual=SEM_OCORRENCIA,
        cheques_sem_fundo=SEM_OCORRENCIA,
        participacoes=(),
        confiancas={"nome_oficial": ALTA, "cpf": ALTA, "data_nascimento": ALTA, "nome_mae": ALTA},
        rotulos={},
    )
    base.update(overrides)
    return CrednetFields(**base)


async def _aplicar(client, cid, did, fields) -> dict:
    doc = client.table("cliente_documentos").select("*").eq("id", did).execute().data[0]
    return await crednet_service.aplicar_leitura(
        client, ORG_ID, cid, did, doc, b"%PDF-1.4 fake bytes",
        extractor=FakeCrednetExtractor(result=fields),
        notification_service=None,
    )


class TestDocumentMarkedFirst:
    @pytest.mark.asyncio
    async def test_extracao_fields_written_before_cliente_touched(self, client):
        cid, did = str(uuid4()), str(uuid4())
        client.table("clientes").insert(_cliente(cid)).execute()
        client.table("cliente_documentos").insert(_documento(did, cid)).execute()

        await _aplicar(client, cid, did, _fields())

        doc = client.table("cliente_documentos").select("*").eq("id", did).execute().data[0]
        assert doc["extracao_status"] == "ok"
        assert doc["extracao_nome"] == "FULANA DE TESTE"
        assert doc["extracao_cpf"] == CPF_VALIDO
        assert doc["extracao_nome_mae"] == "CICLANA DE TESTE"
        assert doc["extracao_crednet"]["protocolo"] == "1234567"
        assert doc["extracao_crednet"]["ocorrencias_constam"] is False


class TestD1Apply:
    @pytest.mark.asyncio
    async def test_empty_fields_fill_machine_pending(self, client):
        cid, did = str(uuid4()), str(uuid4())
        client.table("clientes").insert(_cliente(cid)).execute()
        client.table("cliente_documentos").insert(_documento(did, cid)).execute()

        await _aplicar(client, cid, did, _fields())

        cliente = client.table("clientes").select("*").eq("id", cid).execute().data[0]
        assert cliente["nome_oficial"] == "FULANA DE TESTE"
        assert cliente["nome_oficial_origem"] == "serasa_crednet"
        assert cliente["cpf"] == CPF_VALIDO
        assert cliente["nome_mae"] == "CICLANA DE TESTE"
        assert cliente["nome_mae_origem"] == "serasa_crednet"
        assert cliente["nome_mae_confirmado_em"] is None  # machine-pending

    @pytest.mark.asyncio
    async def test_a_disagreeing_value_opens_a_conflict_never_overwrites(self, client):
        cid, did = str(uuid4()), str(uuid4())
        client.table("clientes").insert(
            _cliente(cid, nome_mae="OUTRO NOME", nome_mae_origem="manual")
        ).execute()
        client.table("cliente_documentos").insert(_documento(did, cid)).execute()

        result = await _aplicar(client, cid, did, _fields())

        cliente = client.table("clientes").select("*").eq("id", cid).execute().data[0]
        assert cliente["nome_mae"] == "OUTRO NOME"  # untouched
        conflitos = client.table("cliente_campo_conflitos").select("*").execute().data
        assert len(conflitos) == 1
        assert conflitos[0]["campo"] == "nome_mae"
        assert conflitos[0]["valor_proposto"] == "CICLANA DE TESTE"
        assert result["conflitos"] == 1

    @pytest.mark.asyncio
    async def test_invalid_cpf_check_digit_recorded_but_never_applied(self, client):
        cid, did = str(uuid4()), str(uuid4())
        client.table("clientes").insert(_cliente(cid)).execute()
        client.table("cliente_documentos").insert(_documento(did, cid)).execute()

        await _aplicar(client, cid, did, _fields(cpf="00000000000", cpf_valido=False))

        doc = client.table("cliente_documentos").select("*").eq("id", did).execute().data[0]
        assert doc["extracao_cpf"] == "00000000000"  # recorded
        cliente = client.table("clientes").select("*").eq("id", cid).execute().data[0]
        assert cliente["cpf"] is None  # never applied


class TestEmpresasUpsert:
    @pytest.mark.asyncio
    async def test_valid_cnpj_participacao_creates_empresa_and_link(self, client):
        cid, did = str(uuid4()), str(uuid4())
        client.table("clientes").insert(_cliente(cid)).execute()
        client.table("cliente_documentos").insert(_documento(did, cid)).execute()
        participacao = ParticipacaoCrednet(
            razao_social="EMPRESA TESTE LTDA", cnpj=CNPJ_VALIDO, cnpj_valido=True,
            participacao_pct=50, confianca=ALTA,
        )

        result = await _aplicar(client, cid, did, _fields(participacoes=(participacao,)))

        empresas = client.table("empresas").select("*").execute().data
        assert len(empresas) == 1
        assert empresas[0]["cnpj"] == CNPJ_VALIDO
        assert empresas[0]["razao_social"] == "EMPRESA TESTE LTDA"
        assert empresas[0]["dados_origem"] == "serasa_crednet"
        assert empresas[0].get("situacao_cadastral") is None  # NEVER written (contract §H4)
        # P1/883 live bug (2026-09-24): `empresas.dados_documento_id`'s FK
        # targets `empresa_documentos` (a Cartão CNPJ), never
        # `cliente_documentos` (this Crednet PDF) — writing `did` here 500s
        # on a real DB with a 23503, which `MockSupabaseClient` does not
        # catch (it does not enforce FKs), so this assertion is the only
        # thing that pins it. The Crednet provenance lives on the
        # participação's own `fonte_documento_id` instead — asserted below.
        assert empresas[0]["dados_documento_id"] is None
        participacoes = client.table("cliente_empresa_participacoes").select("*").execute().data
        assert len(participacoes) == 1
        assert participacoes[0]["origem"] == "serasa_crednet"
        assert participacoes[0]["cliente_id"] == cid
        assert participacoes[0]["empresa_id"] == empresas[0]["id"]
        assert participacoes[0]["fonte_documento_id"] == did
        assert result["empresas"] == [empresas[0]["id"]]

    @pytest.mark.asyncio
    async def test_a_garbled_pct_on_one_participacao_never_takes_down_the_others(self, client):
        """P1/883 follow-up (2026-09-24): a single unparseable
        `participacao_pct` used to raise uncaught inside `_serializar_
        crednet`, poisoning the WHOLE raw-reading write before it even
        landed — every other field on the same document (nome/cpf/data_
        nascimento), the OTHER participação, and both empresa/participação
        upserts silently never happened either. The garbled field alone
        must degrade to `None`; nothing else may be collateral damage."""
        cid, did = str(uuid4()), str(uuid4())
        client.table("clientes").insert(_cliente(cid)).execute()
        client.table("cliente_documentos").insert(_documento(did, cid)).execute()
        garbled = ParticipacaoCrednet(
            razao_social="EMPRESA GARBLED LTDA", cnpj=CNPJ_VALIDO, cnpj_valido=True,
            participacao_pct="cerca de 50%",
        )
        boa = ParticipacaoCrednet(
            razao_social="EMPRESA BOA LTDA", cnpj=CNPJ_VALIDO_OUTRO, cnpj_valido=True,
            participacao_pct=30,
        )

        result = await _aplicar(client, cid, did, _fields(participacoes=(garbled, boa)))

        # Never crashed, never ended in `erro` — this is not a failure.
        assert result["status"] == "ok"
        doc = client.table("cliente_documentos").select("*").eq("id", did).execute().data[0]
        assert doc["extracao_status"] == "ok"
        # The OTHER fields on the same document still landed.
        assert doc["extracao_nome"] == "FULANA DE TESTE"
        cliente = client.table("clientes").select("*").eq("id", cid).execute().data[0]
        assert cliente["nome_oficial"] == "FULANA DE TESTE"
        # Both empresas + both participações upserted.
        empresas = {e["cnpj"]: e for e in client.table("empresas").select("*").execute().data}
        assert set(empresas) == {CNPJ_VALIDO, CNPJ_VALIDO_OUTRO}
        participacoes = {
            p["empresa_id"]: p
            for p in client.table("cliente_empresa_participacoes").select("*").execute().data
        }
        garbled_participacao = participacoes[empresas[CNPJ_VALIDO]["id"]]
        boa_participacao = participacoes[empresas[CNPJ_VALIDO_OUTRO]["id"]]
        assert garbled_participacao["participacao_pct"] is None  # degraded, not crashed
        assert boa_participacao["participacao_pct"] == 30.0
        # The raw JSON reading carries the same degradation, not an omission.
        raw_participacoes = doc["extracao_crednet"]["participacoes"]
        raw_por_cnpj = {p["cnpj"]: p for p in raw_participacoes}
        assert raw_por_cnpj[CNPJ_VALIDO]["participacao_pct"] is None
        assert raw_por_cnpj[CNPJ_VALIDO_OUTRO]["participacao_pct"] == 30.0

    @pytest.mark.asyncio
    async def test_invalid_cnpj_participacao_is_rejected_not_linked(self, client):
        cid, did = str(uuid4()), str(uuid4())
        client.table("clientes").insert(_cliente(cid)).execute()
        client.table("cliente_documentos").insert(_documento(did, cid)).execute()
        participacao = ParticipacaoCrednet(
            razao_social="INVALIDA LTDA", cnpj=CNPJ_INVALIDO, cnpj_valido=False,
        )

        result = await _aplicar(client, cid, did, _fields(participacoes=(participacao,)))

        assert client.table("empresas").select("*").execute().data == []
        assert client.table("cliente_empresa_participacoes").select("*").execute().data == []
        assert result["participacoes_rejeitadas"] == 1
        doc = client.table("cliente_documentos").select("*").eq("id", did).execute().data[0]
        rejeitadas = doc["extracao_crednet"]["participacoes_rejeitadas"]
        assert len(rejeitadas) == 1
        assert rejeitadas[0]["cnpj"] == CNPJ_INVALIDO

    @pytest.mark.asyncio
    async def test_a_second_read_never_touches_an_existing_empresa(self, client):
        cid1, cid2 = str(uuid4()), str(uuid4())
        did1, did2 = str(uuid4()), str(uuid4())
        client.table("clientes").insert(_cliente(cid1)).execute()
        client.table("clientes").insert(_cliente(cid2)).execute()
        client.table("cliente_documentos").insert(_documento(did1, cid1)).execute()
        client.table("cliente_documentos").insert(_documento(did2, cid2)).execute()
        participacao = ParticipacaoCrednet(
            razao_social="EMPRESA TESTE LTDA", cnpj=CNPJ_VALIDO, cnpj_valido=True,
        )

        await _aplicar(client, cid1, did1, _fields(participacoes=(participacao,)))
        await _aplicar(
            client, cid2, did2,
            _fields(
                cpf="52998224725",
                participacoes=(
                    ParticipacaoCrednet(
                        razao_social="NOME DIFERENTE LTDA", cnpj=CNPJ_VALIDO, cnpj_valido=True,
                    ),
                ),
            ),
        )

        empresas = client.table("empresas").select("*").execute().data
        assert len(empresas) == 1  # same (org, cnpj) — never duplicated
        assert empresas[0]["razao_social"] == "EMPRESA TESTE LTDA"  # untouched
        participacoes = client.table("cliente_empresa_participacoes").select("*").execute().data
        assert {p["cliente_id"] for p in participacoes} == {cid1, cid2}

    @pytest.mark.asyncio
    async def test_two_different_cnpjs_create_two_empresas(self, client):
        cid, did = str(uuid4()), str(uuid4())
        client.table("clientes").insert(_cliente(cid)).execute()
        client.table("cliente_documentos").insert(_documento(did, cid)).execute()
        p1 = ParticipacaoCrednet(razao_social="A LTDA", cnpj=CNPJ_VALIDO, cnpj_valido=True)
        p2 = ParticipacaoCrednet(razao_social="B LTDA", cnpj=CNPJ_VALIDO_OUTRO, cnpj_valido=True)

        await _aplicar(client, cid, did, _fields(participacoes=(p1, p2)))

        empresas = client.table("empresas").select("*").execute().data
        assert {e["cnpj"] for e in empresas} == {CNPJ_VALIDO, CNPJ_VALIDO_OUTRO}


class TestErrorPath:
    @pytest.mark.asyncio
    async def test_extractor_error_is_recorded_never_raises(self, client):
        cid, did = str(uuid4()), str(uuid4())
        client.table("clientes").insert(_cliente(cid)).execute()
        client.table("cliente_documentos").insert(_documento(did, cid)).execute()

        result = await _aplicar(
            client, cid, did,
            CrednetFields(error="empty_document", error_message="no bytes to read"),
        )

        assert result["status"] == "erro"
        doc = client.table("cliente_documentos").select("*").eq("id", did).execute().data[0]
        assert doc["extracao_status"] == "erro"
        cliente = client.table("clientes").select("*").eq("id", cid).execute().data[0]
        assert cliente["nome_oficial"] is None  # nothing applied


class TestSideEffectFailuresAreVisible:
    """P1/883 live bug (2026-09-24): a crash inside the D1 apply / empresas
    upsert / certidão-9 fill — a real one was the FK violation §6 of this
    same pass fixed — used to leave `extracao_status='ok'` (stamped in the
    old step (a), before those ran) and propagate uncaught out of a
    BackgroundTask: the UI showed success while the side effects silently
    never landed, and the D3 sweep never re-touches an `ok` row."""

    @pytest.mark.asyncio
    async def test_a_crash_past_the_raw_write_keeps_the_reading_and_marks_erro(self, client):
        """A crash strictly AFTER the raw reading lands (a malformed
        `cliente_documentos` row missing `storage_path` — (d)'s
        `registrar_serasa_de_crednet` reads it by key, not `.get`): the raw
        reading survives, `extracao_status` still ends `erro`, and nothing
        raises out of `aplicar_leitura`."""
        cid, did, consulta_id = str(uuid4()), str(uuid4()), str(uuid4())
        client.table("clientes").insert(_cliente(cid)).execute()
        doc_row = _documento(did, cid)
        # A consulta this Crednet's CPF matches — reaches `_aplicar_crednet_
        # a_resultado`, which is where the missing key is read.
        client.table("certidao_consultas").insert({
            "id": consulta_id, "org_id": str(ORG_ID), "cliente_id": cid,
            "tipo_documento": "cpf", "documento": CPF_VALIDO, "excluida_em": None,
        }).execute()
        client.table("certidao_resultados").insert({
            "id": str(uuid4()), "org_id": str(ORG_ID), "consulta_id": consulta_id,
            "tipo": "serasa", "status": "pendente", "resultado_origem": None,
        }).execute()
        del doc_row["storage_path"]
        client.table("cliente_documentos").insert(doc_row).execute()

        try:
            result = await _aplicar(client, cid, did, _fields())
        except Exception as exc:  # noqa: BLE001 - the assertion IS "this never happens"
            pytest.fail(f"aplicar_leitura raised {exc!r} instead of recording erro")

        assert result == {"status": "erro", "erro": "side_effects_failed"}
        doc = client.table("cliente_documentos").select("*").eq("id", did).execute().data[0]
        assert doc["extracao_status"] == "erro"
        # The RAW reading still landed — (b)/(c) ran fine before the crash.
        assert doc["extracao_nome"] == "FULANA DE TESTE"
        assert doc["extracao_crednet"]["protocolo"] == "1234567"
        cliente = client.table("clientes").select("*").eq("id", cid).execute().data[0]
        assert cliente["nome_oficial"] == "FULANA DE TESTE"  # (b) D1 apply landed too
