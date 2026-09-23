"""A concluded matrícula transcription → `imovel_dados` under D1 (migration
154, `preenchimento_service`).

WHAT THESE PIN
--------------
- every field the matrícula can supply fills an EMPTY imóvel, with
  provenance, machine-pending (número, cartório, inscrição, título pointer,
  ônus acts + creditor, situação de ônus);
- a second run is a no-op (idempotent);
- a HUMAN value that disagrees is never overwritten — a conflict opens and
  the notifier hears about it;
- an unlinked extraction fills nothing; linking it LATER (`PUT
  .../imovel`) runs the same fill;
- raw-markup text is refused (the backfill cleans it first);
- `processar_extracao` runs the fill after the text lands;
- `derivar_situacao_onus`: released encumbrances do not count, typed
  readings win over the text heuristic.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.modules.matriculas import preenchimento_service as preench
from app.modules.matriculas import service as matriculas_service
from tests.modules.matriculas.conftest import (
    CODIGO,
    ORG_ID,
    FakeNotificationService,
    StubTranscriber,
    extracao_row,
    registry_row,
    seed,
)

ATOS = (
    "R-1/45.678 - Em 10 de março de 2001. COMPRA E VENDA. Transmitente: Fulana de "
    "Teste Exemplar; adquirente: Beltrano Modelo. Valor R$ 100.000,00.\n"
    "R-2/45.678 - Em 11 de março de 2001. HIPOTECA em favor do Banco Imaginario S/A.\n"
    "AV-3/45.678 - Em 5 de maio de 2010. CANCELAMENTO da hipoteca objeto do R-2, "
    "por quitaçao.\n"
    "R-4/45.678 - Em 1 de junho de 2015. VENDA E COMPRA. Transmitente: Beltrano "
    "Modelo; adquirente: Cicrana Amostra.\n"
    "R-5/45.678 - Em 1 de junho de 2015. ALIENAÇÃO FIDUCIÁRIA em garantia ao "
    "Banco Ficticio.\n"
)

TEXTO = (
    "1º OFICIAL DE REGISTRO DE IMÓVEIS DE COTIA - SP\n"
    "MATRÍCULA Nº 45.678 — FICHA 01\n"
    "IMÓVEL: Apartamento nº 12 do Edificio Jacarandá Ficticio, situado a Rua das "
    "Amostras, 99.\n"
    "CADASTRO MUNICIPAL: Contribuinte nº 123.456.7-8.\n"
    "PROPRIETÁRIA: Fulana de Teste Exemplar, brasileira, CPF 000.000.000-00.\n"
    "\n" + ATOS
)


def _dados(scoped) -> dict:
    rows = [r for r in scoped.table("imovel_dados").select("*").execute().data
            if r["codigo"] == CODIGO]
    return rows[0] if rows else {}


def _conflitos(scoped) -> list[dict]:
    return scoped.table("imovel_campo_conflitos").select("*").execute().data


class TestFillFromATranscription:
    @pytest.mark.asyncio
    async def test_every_suppliable_field_fills_an_empty_imovel(self, client, scoped):
        eid = str(uuid4())
        seed(scoped, registry=[registry_row()], extracoes=[extracao_row(eid, texto=TEXTO)])

        resumo = await preench.preencher_imovel(scoped, ORG_ID, eid)

        assert resumo["status"] == "ok"
        row = _dados(scoped)
        assert row["numero_matricula"] == "45678"
        assert row["numero_matricula_origem"] == "matricula"
        assert row["numero_registro_imoveis"] == "1º OFICIAL DE REGISTRO DE IMÓVEIS DE COTIA - SP"
        assert row["numero_registro_imoveis_documento_id"] == eid
        assert row["prefeitura_cadastro_imobiliario"] == "123.456.7-8"
        # R-2's hipoteca is released by AV-3; R-5's alienação is not.
        assert row["situacao_onus"] == "alienacao_fiduciaria"
        assert row["situacao_onus_origem"] == "matricula"
        # The latest transfer act (R-4) is the título pointer, machine-pending.
        atos = {
            (a["kind"], a["numero"]): a["id"]
            for a in scoped.table("matricula_atos").select("*").execute().data
        }
        assert row["titulo_aquisitivo_ato_id"] == atos[("R", 4)]
        assert row["titulo_aquisitivo_origem"] == "sugerido"
        assert row["titulo_aquisitivo_confirmado_em"] is None
        assert [a["ato_id"] for a in row["onus_fonte_atos"]] == [atos[("R", 5)]]
        assert row["onus_credor"] == "Banco Ficticio"
        assert row["onus_credor_origem"] == "matricula"
        for campo in ("numero_matricula", "numero_registro_imoveis", "situacao_onus"):
            assert row[f"{campo}_confirmado_em"] is None
        assert _conflitos(scoped) == []

    @pytest.mark.asyncio
    async def test_titulo_aquisitivo_texto_fills_machine_pending_when_the_act_has_an_instrumento(
        self, client, scoped
    ):
        """🔴 The missing coverage migration 166 was written to close: `ATOS`
        above never gives the título act (R-4) enough for `seed.
        frase_titulo_aquisitivo` to return non-`None` (no instrumento —
        tipo/data/tabelionato/livro/folhas — anywhere in its text), so
        `preencher_sincrono`'s `aplicar("titulo_aquisitivo_texto", frase)`
        call (line ~297) never actually fired in this suite before now —
        exactly the gap that let migration 115's stale, confirmed-only
        `imovel_dados_titulo_aquisitivo_texto_confirmado` CHECK ship
        unnoticed against 154's D1 machine-pending write policy until a
        real prod imóvel (E2E-IMV-LIVRE) hit it. This fixture's R-4 line
        DOES carry a full instrumento, so the write branch fires here."""
        eid = str(uuid4())
        texto = TEXTO.replace(
            "R-4/45.678 - Em 1 de junho de 2015. VENDA E COMPRA. Transmitente: Beltrano "
            "Modelo; adquirente: Cicrana Amostra.\n",
            "R-4/45.678 - Em 1 de junho de 2015. COMPRA E VENDA por Escritura Pública "
            "lavrada em 20 de maio de 2015 no 2º Tabelionato de Notas de Cotia, "
            "Livro 300, fls. 45. Transmitente: Beltrano Modelo; adquirente: "
            "Cicrana Amostra.\n",
        )
        assert texto != TEXTO  # the .replace() actually matched
        seed(scoped, registry=[registry_row()], extracoes=[extracao_row(eid, texto=texto)])

        resumo = await preench.preencher_imovel(scoped, ORG_ID, eid)

        assert resumo["status"] == "ok"
        row = _dados(scoped)
        # Machine-pending — origem set, confirmado_em NULL (D2) — exactly the
        # state migration 115's confirmado_em-paired CHECK used to refuse and
        # 166's origem-paired CHECK now explicitly permits.
        assert row["titulo_aquisitivo_texto"] == (
            "por Escritura Pública lavrada em 20/05/2015 no 2º Tabelionato de "
            "Notas de Cotia, Livro 300, fls. 45, registrada sob o R-4"
        )
        assert row["titulo_aquisitivo_texto_origem"] == "matricula"
        assert row["titulo_aquisitivo_texto_confirmado_por"] is None
        assert row["titulo_aquisitivo_texto_confirmado_em"] is None
        assert _conflitos(scoped) == []

    @pytest.mark.asyncio
    async def test_a_second_run_changes_nothing(self, client, scoped):
        eid = str(uuid4())
        seed(scoped, registry=[registry_row()], extracoes=[extracao_row(eid, texto=TEXTO)])
        await preench.preencher_imovel(scoped, ORG_ID, eid)
        antes = dict(_dados(scoped))

        resumo = await preench.preencher_imovel(scoped, ORG_ID, eid)

        assert {v for k, v in resumo.items() if k not in ("status", "conflitos_abertos")} == {
            "igual"
        }
        assert _dados(scoped) == antes
        assert _conflitos(scoped) == []

    @pytest.mark.asyncio
    async def test_a_human_value_opens_a_notified_conflict(self, client, scoped):
        eid = str(uuid4())
        seed(
            scoped,
            registry=[registry_row()],
            extracoes=[extracao_row(eid, texto=TEXTO)],
            dados=[{
                "org_id": ORG_ID, "codigo": CODIGO,
                "numero_registro_imoveis": "2º Registro de Imóveis de Barueri",
                "numero_registro_imoveis_origem": "manual",
                "created_at": "2026-01-01T00:00:00+00:00",
            }],
        )
        fake = FakeNotificationService()

        resumo = await preench.preencher_imovel(scoped, ORG_ID, eid, notificador=fake)

        assert resumo["numero_registro_imoveis"] == "conflito"
        assert resumo["conflitos_abertos"] == ["numero_registro_imoveis"]
        assert _dados(scoped)["numero_registro_imoveis"] == "2º Registro de Imóveis de Barueri"
        [n] = fake.conflitos
        assert n["codigo"] == CODIGO
        assert n["conflito"]["valor_proposto"].startswith("1º OFICIAL")
        assert _conflitos(scoped)[0]["notificado_em"]

    @pytest.mark.asyncio
    async def test_raw_markup_text_is_not_read(self, client, scoped):
        eid = str(uuid4())
        seed(scoped, registry=[registry_row()], extracoes=[
            extracao_row(eid, texto="**" + TEXTO, possui_marcacao_bruta=True)
        ])
        resumo = await preench.preencher_imovel(scoped, ORG_ID, eid)
        assert resumo["status"] == "marcacao_bruta"
        assert _dados(scoped) == {}


class TestLinkLater:
    @pytest.mark.asyncio
    async def test_unlinked_fills_nothing(self, client, scoped):
        eid = str(uuid4())
        seed(scoped, registry=[registry_row()], extracoes=[extracao_row(eid, texto=TEXTO, codigo=None)])
        resumo = await preench.preencher_imovel(scoped, ORG_ID, eid)
        assert resumo["status"] == "sem_imovel"
        assert _dados(scoped) == {}

    def test_linking_later_runs_the_same_fill(self, client, scoped, fake_notification_service):
        eid = str(uuid4())
        seed(scoped, registry=[registry_row()], extracoes=[extracao_row(eid, texto=TEXTO, codigo=None)])
        r = client.put(f"/api/matriculas/extracoes/{eid}/imovel", json={"codigo": CODIGO})
        assert r.status_code == 200, r.text
        row = _dados(scoped)
        assert row["numero_matricula"] == "45678"
        assert row["prefeitura_cadastro_imobiliario"] == "123.456.7-8"
        assert row["numero_registro_imoveis_documento_id"] == eid


class TestTranscriptionRunsTheFill:
    @pytest.mark.asyncio
    async def test_processar_extracao_fills_after_the_text_lands(self, client, scoped):
        eid = str(uuid4())
        row = extracao_row(eid, status="processando")
        seed(scoped, registry=[registry_row()], extracoes=[row])

        await matriculas_service.processar_extracao(
            eid, b"%PDF", ORG_ID, scoped, transcriber=StubTranscriber(TEXTO)
        )

        assert _dados(scoped)["numero_matricula"] == "45678"

    @pytest.mark.asyncio
    async def test_a_failure_records_the_machine_code(self, client, scoped):
        from noctusai_lib.integrations.documents.transcription import Transcription

        class _SemCredito:
            async def transcribe(self, content, *, mimetype=None, filename=None):
                return Transcription(
                    pages=(), num_paginas=0, error="insufficient_quota",
                    error_message="quota",
                )

        eid = str(uuid4())
        seed(scoped, registry=[registry_row()], extracoes=[extracao_row(eid, status="processando")])
        await matriculas_service.processar_extracao(
            eid, b"%PDF", ORG_ID, scoped, transcriber=_SemCredito()
        )
        row = [r for r in scoped.table("matricula_extracoes").select("*").execute().data
               if r["id"] == eid][0]
        assert row["status"] == "erro"
        assert row["erro_codigo"] == "insufficient_quota"


def _ato(i, kind, numero):
    return {"id": f"a{i}", "ordem": i, "kind": kind, "numero": numero}


class TestDerivarSituacaoOnus:
    def test_nothing_encumbering_is_livre(self):
        assert preench.derivar_situacao_onus(
            [_ato(0, "abertura", None), _ato(1, "R", 1)],
            {"a1": {"natureza": "compra_e_venda"}}, [],
        ) == "livre"

    def test_a_typed_cancellation_releases_the_hipoteca(self):
        atos = [_ato(1, "R", 2), _ato(2, "AV", 3)]
        detalhes = {
            "a1": {"natureza": "hipoteca"},
            "a2": {"natureza": "cancelamento", "atos_referidos": [{"kind": "R", "numero": 2}]},
        }
        assert preench.derivar_situacao_onus(atos, detalhes, []) == "livre"

    def test_an_unreleased_alienacao_is_that_value(self):
        assert preench.derivar_situacao_onus(
            [_ato(1, "R", 5)], {"a1": {"natureza": "alienacao_fiduciaria"}}, []
        ) == "alienacao_fiduciaria"

    def test_two_kinds_is_outro(self):
        atos = [_ato(1, "R", 5), _ato(2, "AV", 6)]
        detalhes = {"a1": {"natureza": "hipoteca"}, "a2": {"natureza": "penhora"}}
        assert preench.derivar_situacao_onus(atos, detalhes, []) == "outro"

    def test_the_text_heuristic_fills_in_only_without_a_typed_reading(self):
        atos = [_ato(1, "R", 2), _ato(2, "R", 3)]
        sugestoes = [
            {"ato_id": "a1", "tipo": "hipoteca", "sugerido": True, "cancelamento_citado_por": []},
            {"ato_id": "a2", "tipo": "penhora", "sugerido": True, "cancelamento_citado_por": []},
        ]
        # a1 has a typed nature that is NOT an encumbrance — it wins.
        detalhes = {"a1": {"natureza": "compra_e_venda"}}
        assert preench.derivar_situacao_onus(atos, detalhes, sugestoes) == "penhora"

    def test_a_text_cited_cancellation_releases_even_a_typed_encumbrance(self):
        atos = [_ato(1, "R", 2)]
        sugestoes = [{
            "ato_id": "a1", "tipo": "hipoteca", "sugerido": False,
            "cancelamento_citado_por": ["a9"],
        }]
        assert preench.derivar_situacao_onus(
            atos, {"a1": {"natureza": "hipoteca"}}, sugestoes
        ) == "livre"


class TestTranscriptionRetry:
    """D3: a failed transcription whose PDF was kept is retried in place at
    most twice by the hourly sweep — never one a retry cannot fix."""

    async def _setup(self, scoped, fake_storage, **extra):
        from tests.modules.matriculas.conftest import documento_row

        did = str(uuid4())
        doc = documento_row(did)
        eid = str(uuid4())
        row = {
            **extracao_row(eid, status="erro", imovel_documento_id=did),
            "erro_codigo": "insufficient_quota",
            "erro_mensagem": "sem créditos",
            "retentativas": 0,
            "updated_at": "2026-01-01T00:00:00+00:00",
            **extra,
        }
        seed(scoped, registry=[registry_row()], extracoes=[row], documentos=[doc])
        await fake_storage.put(
            bucket="social-wiring-documentos", key=doc["storage_path"], data=b"%PDF",
            content_type="application/pdf",
        )
        return eid

    def _row(self, scoped, eid):
        return [r for r in scoped.table("matricula_extracoes").select("*").execute().data
                if r["id"] == eid][0]

    @pytest.mark.asyncio
    async def test_a_quota_failure_is_retried_and_lands(self, client, scoped, fake_storage):
        eid = await self._setup(scoped, fake_storage)
        stub = StubTranscriber(TEXTO)

        res = await matriculas_service.varrer_pendentes(
            scoped, fake_storage, transcriber_factory=lambda _org: stub
        )

        assert res["retentadas"] == 1
        row = self._row(scoped, eid)
        assert row["status"] == "concluida"
        assert row["retentativas"] == 1
        assert _dados(scoped)["numero_matricula"] == "45678"

    @pytest.mark.asyncio
    async def test_the_cap_is_two(self, client, scoped, fake_storage):
        eid = await self._setup(scoped, fake_storage, retentativas=2)
        res = await matriculas_service.varrer_pendentes(
            scoped, fake_storage, transcriber_factory=lambda _org: StubTranscriber(TEXTO)
        )
        assert res["retentadas"] == 0
        assert self._row(scoped, eid)["status"] == "erro"

    @pytest.mark.asyncio
    async def test_a_permanent_failure_leaves_the_pool(self, client, scoped, fake_storage):
        eid = await self._setup(scoped, fake_storage, erro_codigo="empty_document")
        stub = StubTranscriber(TEXTO)
        res = await matriculas_service.varrer_pendentes(
            scoped, fake_storage, transcriber_factory=lambda _org: stub
        )
        assert res == {**res, "retentadas": 0, "esgotadas": 1}
        assert stub.calls == 0
        row = self._row(scoped, eid)
        assert row["status"] == "erro"
        assert row["retentativas"] == 2
