"""The corpus backfill (migration 154, `backfill_service`): strip legacy
markers without re-transcribing, move every offset with them, heal the
abertura blocks, feed `imovel_dados`. Idempotent.

WHAT THESE PIN
--------------
- the text comes back marker-free, `possui_marcacao_bruta` false, and the
  markers' bold/underline become `formatacao` (nothing lost);
- acts segmented on the MARKERED text keep their ids and have their offsets
  moved so every act's slice is the same words;
- page-noise spans and the imóvel's título pointer move too;
- the abertura blocks the markers hid now exist, and the imóvel fills;
- a second run changes nothing;
- an extraction something QUOTES keeps its acts when the clean text would
  segment differently (reported, not re-minted);
- the route is admin-only.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from noctusai_lib.integrations.documents import segment_matricula_atos
from noctusai_lib.testing import TEST_USER_ID

from app.modules.matriculas import backfill_service
from app.modules.matriculas import estrutura_service
from tests.modules.matriculas.conftest import (
    CODIGO,
    ORG_ID,
    extracao_row,
    registry_row,
    seed,
)

LEGADO = (
    "**1º OFICIAL DE REGISTRO DE IMÓVEIS DE COTIA - SP**\n"
    "**MATRÍCULA Nº 45.678** — FICHA 01\n"
    "**IMÓVEL:** Apartamento <u>nº 12</u> do Edificio Ficticio.\n"
    "**CADASTRO MUNICIPAL:** Contribuinte nº 123.456.7-8.\n"
    "\n"
    "R-1/45.678 - Em 10 de março de 2001. **COMPRA E VENDA**. Transmitente: "
    "Fulana; adquirente: Beltrano.\n"
    "R-2/45.678 - Em 11 de março de 2001. HIPOTECA em favor do **Banco Imaginario**.\n"
)


def _extracao(scoped, eid) -> dict:
    return [r for r in scoped.table("matricula_extracoes").select("*").execute().data
            if r["id"] == eid][0]


def _atos(scoped, eid) -> list[dict]:
    return sorted(
        (r for r in scoped.table("matricula_atos").select("*").execute().data
         if r["extracao_id"] == eid),
        key=lambda r: r["ordem"],
    )


def _seed_legado(scoped, **extra) -> str:
    eid = str(uuid4())
    seed(
        scoped,
        registry=[registry_row()],
        extracoes=[extracao_row(
            eid, texto=LEGADO, possui_marcacao_bruta=True,
            ruido=[{"start": 60, "end": 70, "kind": "rodape_pagina"}],
        )],
        **extra,
    )
    # Acts exactly as the pre-154 pipeline wrote them: segmented on the
    # MARKERED text.
    estrutura_service.persistir_atos(scoped, eid, ORG_ID, LEGADO)
    return eid


class TestNormalizar:
    def test_markers_leave_formatting_stays_offsets_move(self, client, scoped):
        eid = _seed_legado(scoped)
        antes = {a["id"]: LEGADO[a["char_inicio"]:a["char_fim"]] for a in _atos(scoped, eid)}

        rel = backfill_service.normalizar_extracao(scoped, ORG_ID, eid)

        assert rel["marcacao_removida"] is True
        ext = _extracao(scoped, eid)
        texto = ext["texto_extraido"]
        assert "**" not in texto and "<u>" not in texto
        assert ext["possui_marcacao_bruta"] is False
        negritos = [texto[f["start"]:f["end"]] for f in ext["formatacao"] if f.get("bold")]
        assert "COMPRA E VENDA" in negritos
        # Same act ids, same words (minus the markers).
        for ato in _atos(scoped, eid):
            if ato["id"] in antes:
                limpo = antes[ato["id"]].replace("**", "").replace("<u>", "").replace("</u>", "")
                assert texto[ato["char_inicio"]:ato["char_fim"]] == limpo
        # The noise span moved with the text.
        assert ext["ruido"][0]["start"] < 60
        # The blocks the markers hid now exist.
        campos = {b["campo"] for b in scoped.table("matricula_abertura_blocos").select("*").execute().data}
        assert {"descricao_imovel", "cadastro_municipal"} <= campos

    def test_the_titulo_pointer_moves_with_the_text(self, client, scoped):
        eid = _seed_legado(scoped)
        r1 = [a for a in _atos(scoped, eid) if a["numero"] == 1][0]
        scoped.set_table_data("imovel_dados", [{
            "org_id": ORG_ID, "codigo": CODIGO,
            "titulo_aquisitivo_extracao_id": eid, "titulo_aquisitivo_ato_id": r1["id"],
            "titulo_aquisitivo_char_inicio": r1["char_inicio"],
            "titulo_aquisitivo_char_fim": r1["char_fim"],
            "titulo_aquisitivo_origem": "manual",
            "created_at": "2026-01-01T00:00:00+00:00",
        }])

        backfill_service.normalizar_extracao(scoped, ORG_ID, eid)

        dados = scoped.table("imovel_dados").select("*").execute().data[0]
        r1_novo = [a for a in _atos(scoped, eid) if a["id"] == r1["id"]][0]
        assert dados["titulo_aquisitivo_char_inicio"] == r1_novo["char_inicio"]
        assert dados["titulo_aquisitivo_char_fim"] == r1_novo["char_fim"]

    @pytest.mark.asyncio
    async def test_backfill_fills_the_imovel_and_is_idempotent(self, client, scoped):
        eid = _seed_legado(scoped)

        primeiro = await backfill_service.backfill(scoped, ORG_ID)
        assert primeiro["marcacao_removida"] == 1
        dados = scoped.table("imovel_dados").select("*").execute().data[0]
        assert dados["numero_registro_imoveis"] == "1º OFICIAL DE REGISTRO DE IMÓVEIS DE COTIA - SP"
        assert dados["prefeitura_cadastro_imobiliario"] == "123.456.7-8"
        texto_1 = _extracao(scoped, eid)["texto_extraido"]
        atos_1 = [(a["id"], a["char_inicio"], a["char_fim"]) for a in _atos(scoped, eid)]

        segundo = await backfill_service.backfill(scoped, ORG_ID)

        assert segundo["marcacao_removida"] == 0
        assert _extracao(scoped, eid)["texto_extraido"] == texto_1
        assert [(a["id"], a["char_inicio"], a["char_fim"]) for a in _atos(scoped, eid)] == atos_1
        assert scoped.table("imovel_dados").select("*").execute().data[0] == dados

    def test_a_quoted_extraction_keeps_its_acts_when_segmentation_differs(self, client, scoped):
        """A header the markers hid (`**R-2/...**`) would be a NEW act on the
        clean text — new ids. With a contract quoting this extraction, the
        old acts stay (moved) and the row is reported."""
        texto = LEGADO.replace("R-2/45.678", "**R-2/45.678**")
        eid = str(uuid4())
        seed(scoped, registry=[registry_row()], extracoes=[
            extracao_row(eid, texto=texto, possui_marcacao_bruta=True)
        ])
        estrutura_service.persistir_atos(scoped, eid, ORG_ID, texto)
        antes = {a["id"] for a in _atos(scoped, eid)}
        assert len(antes) != len(segment_matricula_atos(texto.replace("**", "")))
        scoped.set_table_data("atendimento_contrato_matricula_atos", [{
            "id": str(uuid4()), "org_id": ORG_ID, "contrato_id": str(uuid4()),
            "extracao_id": eid, "ato_id": next(iter(antes)), "ordem": 1,
        }])

        rel = backfill_service.normalizar_extracao(scoped, ORG_ID, eid)

        assert rel["atos_divergentes"] is True
        assert {a["id"] for a in _atos(scoped, eid)} == antes

    def test_an_unquoted_divergent_extraction_is_resegmented(self, client, scoped):
        texto = LEGADO.replace("R-2/45.678", "**R-2/45.678**")
        eid = str(uuid4())
        seed(scoped, registry=[registry_row()], extracoes=[
            extracao_row(eid, texto=texto, possui_marcacao_bruta=True)
        ])
        estrutura_service.persistir_atos(scoped, eid, ORG_ID, texto)

        rel = backfill_service.normalizar_extracao(scoped, ORG_ID, eid)

        limpo = _extracao(scoped, eid)["texto_extraido"]
        assert rel["atos_ressegmentados"] == len(segment_matricula_atos(limpo))
        assert [(a["kind"], a["numero"]) for a in _atos(scoped, eid)] == [
            (a.kind, a.numero) for a in segment_matricula_atos(limpo)
        ]


class TestRoute:
    def test_a_member_cannot_run_it(self, client, scoped):
        _seed_legado(scoped)
        r = client.post("/api/matriculas/manutencao/normalizar")
        assert r.status_code == 403, r.text

    def test_an_admin_runs_it(self, client, scoped, fake_notification_service):
        client.mock_supabase.set_table_data(
            "noctus_users", [{"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": "owner"}]
        )
        eid = _seed_legado(scoped)
        r = client.post("/api/matriculas/manutencao/normalizar")
        assert r.status_code == 200, r.text
        assert r.json()["data"]["marcacao_removida"] == 1
        assert _extracao(scoped, eid)["possui_marcacao_bruta"] is False
