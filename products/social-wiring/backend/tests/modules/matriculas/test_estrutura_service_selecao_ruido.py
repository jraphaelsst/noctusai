"""`obter_selecao` / `_citacao`'s noise subtraction (migration 136) — a page
header/footer detected inside a selected act's span must never reach the
legal quote, while `listar_atos` (the raw-transcription view) keeps showing
it so the FE can highlight it in place.

Standalone file, same rationale as
`test_estrutura_service_selecao_formatacao.py`: keeps this off that file's
merge surface. `matricula_extracoes.ruido` defaults to `[]` in
`conftest.extracao_row()` — every extraction row here that needs furniture
passes its own `ruido=` spans.
"""
from __future__ import annotations

from uuid import UUID, uuid4

from noctusai_lib.integrations.documents import segment_matricula_atos
from noctusai_lib.integrations.documents.formatting import ranges_from_json

from app.modules.matriculas import estrutura_service as svc
from tests.modules.matriculas.conftest import (
    ORG_ID,
    TEXTO,
    contrato_row,
    extracao_row,
    negociacao_row,
    seed,
)

ORG = UUID(ORG_ID)

# `segment_matricula_atos(TEXTO)` boundaries (pinned, same note as the
# formatacao sibling file — fails loudly, not silently, if TEXTO changes):
#   abertura [0, 298)
_ABERTURA = (0, 298)

# TEXTO's very first line ("MATRÍCULA Nº 45.678 — FICHA 01\n") stands in for
# a running page header `detectar_ruido` would find at a REAL page boundary
# — this suite proves SUBTRACTION, not detection (that's the seed's job,
# `seed/lib/backend/tests/integrations/documents/test_matricula_ruido.py`),
# so a hand-picked span in the shape the shape-guard accepts is enough.
_CABECALHO_FIM = TEXTO.index("\n") + 1
_RUIDO = [{"start": 0, "end": _CABECALHO_FIM, "kind": "cabecalho_pagina"}]


def _atos_by_kind(scoped, extracao_id: str) -> dict:
    atos = svc.listar_atos(scoped, ORG, UUID(extracao_id))["atos"]
    return {(a["kind"], a["numero"]): a for a in atos}


def _selecionar(contrato_id: str, extracao_id: str, atos_em_ordem: list[dict]) -> list[dict]:
    """Seed `atendimento_contrato_matricula_atos` rows directly, same helper
    shape as the formatacao sibling file."""
    return [
        {
            "id": str(uuid4()),
            "org_id": ORG_ID,
            "contrato_id": contrato_id,
            "extracao_id": extracao_id,
            "ato_id": ato["id"],
            "ordem": ordem,
            "selecionado_por": None,
            "created_at": "2026-04-01T00:00:00+00:00",
        }
        for ordem, ato in enumerate(atos_em_ordem, start=1)
    ]


def _seed(scoped, *, ruido=None, formatacao=None) -> tuple[dict, dict, dict]:
    ext = extracao_row(ruido=ruido)
    ext["formatacao"] = formatacao
    contrato = contrato_row()
    seed(
        scoped,
        extracoes=[ext],
        contratos=[contrato],
        negociacoes=[negociacao_row(contrato["atendimento_id"])],
    )
    atos = _atos_by_kind(scoped, ext["id"])
    return ext, contrato, atos


class TestCitacaoSubtractsRuido:
    def test_a_header_inside_the_abertura_is_dropped_from_the_quote(self, scoped):
        ext, contrato, atos = _seed(scoped, ruido=_RUIDO)
        scoped.set_table_data(
            "atendimento_contrato_matricula_atos",
            _selecionar(contrato["id"], ext["id"], [atos[("abertura", None)]]),
        )

        out = svc.obter_selecao(scoped, ORG, UUID(contrato["id"]))

        assert TEXTO[0:_CABECALHO_FIM] not in out["texto"]
        assert "IMÓVEL: Apartamento" in out["texto"]
        assert out["texto"] == TEXTO[_CABECALHO_FIM : _ABERTURA[1]]

    def test_listar_atos_keeps_the_furniture_the_quote_drops(self, scoped):
        """`listar_atos` is the raw-transcription view (the FE highlights
        furniture IN the full act) — only the contract quote subtracts."""
        ext, _contrato, atos = _seed(scoped, ruido=_RUIDO)

        assert atos[("abertura", None)]["texto"] == TEXTO[_ABERTURA[0] : _ABERTURA[1]]
        out = svc.listar_atos(scoped, ORG, UUID(ext["id"]))
        assert out["ruido"] == _RUIDO

    def test_formatacao_still_lines_up_with_the_de_noised_text(self, scoped):
        """A bold range straddling the noise boundary (the header's last 3
        chars, the quote's first 4) is clipped per sub-span — same rule an
        act boundary already gets — and the surviving half lands at the
        very START of the de-noised output, not at its old absolute offset."""
        straddle = {"start": _CABECALHO_FIM - 3, "end": _CABECALHO_FIM + 4, "bold": True}
        ext, contrato, atos = _seed(scoped, ruido=_RUIDO, formatacao=[straddle])
        scoped.set_table_data(
            "atendimento_contrato_matricula_atos",
            _selecionar(contrato["id"], ext["id"], [atos[("abertura", None)]]),
        )

        out = svc.obter_selecao(scoped, ORG, UUID(contrato["id"]))
        rebased = ranges_from_json(out["formatacao"])

        # Only the 4 chars AFTER the noise survive — the 3 chars before it
        # were cut out along with the header itself, so they cannot appear
        # in the output's own coordinate system at all.
        assert len(rebased) == 1
        assert (rebased[0].start, rebased[0].end, rebased[0].bold) == (0, 4, True)
        assert out["texto"][0:4] == TEXTO[_CABECALHO_FIM : _CABECALHO_FIM + 4]

    def test_no_ruido_reproduces_the_pre_136_invariant_exactly(self, scoped):
        """`ruido = []` (the default) is the guard this whole feature must
        never break: selecting every act still yields `texto_extraido`
        byte for byte."""
        ext, contrato, atos = _seed(scoped)
        scoped.set_table_data(
            "atendimento_contrato_matricula_atos",
            _selecionar(contrato["id"], ext["id"], list(atos.values())),
        )

        out = svc.obter_selecao(scoped, ORG, UUID(contrato["id"]))

        assert out["texto"].encode("utf-8") == TEXTO.encode("utf-8")


class TestDescricaoImovelBloco:
    def test_the_typed_block_is_exposed_and_excludes_the_label(self, scoped):
        ext, contrato, atos = _seed(scoped)
        scoped.set_table_data(
            "atendimento_contrato_matricula_atos",
            _selecionar(contrato["id"], ext["id"], [atos[("abertura", None)]]),
        )

        out = svc.obter_selecao(scoped, ORG, UUID(contrato["id"]))

        assert out["descricao_imovel"] is not None
        texto = out["descricao_imovel"]["texto"]
        assert texto.startswith("Apartamento nº 12")
        assert "IMÓVEL:" not in texto
        assert "PROPRIETÁRIA" not in texto

    def test_a_pre_136_extraction_has_no_block_and_is_none(self, scoped):
        """No `matricula_abertura_blocos` rows at all (a row segmented before
        migration 136, per the migration's own 'no backfill' contract) reads
        as `None`, not an error — the caller (`contrato_gerador`) falls
        back to the whole selection."""
        ext = extracao_row()
        contrato = contrato_row()
        seed(
            scoped,
            extracoes=[ext],
            contratos=[contrato],
            negociacoes=[negociacao_row(contrato["atendimento_id"])],
            # `atos=[...]` pre-seeded so `persistir_atos` never runs (the
            # only place abertura blocks are written) — simulating a row
            # segmented before this feature shipped.
            atos=svc.linhas_de_atos(ext["id"], ORG_ID, segment_matricula_atos(TEXTO)),
        )

        out = svc.obter_selecao(scoped, ORG, UUID(contrato["id"]))
        # No selection was ever set for this contract -> defaults; assert
        # the abertura block lookup path directly via listar_atos instead.
        assert svc.listar_atos(scoped, ORG, UUID(ext["id"]))["abertura_blocos"] == []
        assert out["descricao_imovel"] is None


class TestPermutaCitacaoMirrorsObjeto:
    """`_citacao` is called once per group — `papel='objeto'` AND every
    `papel='permuta'` group — so a permuta ativo's OWN matrícula quote gets
    the identical noise-subtraction and `descricao_imovel` narrowing the
    top-level objeto quote gets above. These mirror
    `TestCitacaoSubtractsRuido`/`TestDescricaoImovelBloco`, scoped to
    `out["permutas"][0]` instead of the top-level `out`. No objeto
    selection is seeded at all — `obter_selecao` computes `permutas`
    independent of whether an objeto quote exists."""

    def _seed_permuta(self, scoped, *, ruido=None):
        permuta_ext = extracao_row(ruido=ruido)
        contrato = contrato_row()
        seed(
            scoped,
            extracoes=[permuta_ext],
            contratos=[contrato],
            negociacoes=[negociacao_row(contrato["atendimento_id"])],
        )
        atos = _atos_by_kind(scoped, permuta_ext["id"])
        return permuta_ext, contrato, atos

    def _selecionar_permuta(
        self, contrato_id: str, permuta_ativo_id: str, extracao_id: str, atos_em_ordem: list[dict]
    ) -> list[dict]:
        return [
            {
                "id": str(uuid4()),
                "org_id": ORG_ID,
                "contrato_id": contrato_id,
                "extracao_id": extracao_id,
                "ato_id": ato["id"],
                "ordem": ordem,
                "papel": "permuta",
                "permuta_ativo_id": permuta_ativo_id,
                "selecionado_por": None,
                "created_at": "2026-04-01T00:00:00+00:00",
            }
            for ordem, ato in enumerate(atos_em_ordem, start=1)
        ]

    def test_a_permuta_quote_also_drops_its_furniture(self, scoped):
        permuta_ativo_id = str(uuid4())
        permuta_ext, contrato, atos = self._seed_permuta(scoped, ruido=_RUIDO)
        scoped.set_table_data(
            "atendimento_contrato_matricula_atos",
            self._selecionar_permuta(
                contrato["id"], permuta_ativo_id, permuta_ext["id"],
                [atos[("abertura", None)]],
            ),
        )

        out = svc.obter_selecao(scoped, ORG, UUID(contrato["id"]))
        permuta_quote = out["permutas"][0]

        assert permuta_quote["permuta_ativo_id"] == permuta_ativo_id
        assert TEXTO[0:_CABECALHO_FIM] not in permuta_quote["texto"]
        assert "IMÓVEL: Apartamento" in permuta_quote["texto"]
        assert permuta_quote["texto"] == TEXTO[_CABECALHO_FIM : _ABERTURA[1]]

    def test_a_permuta_descricao_imovel_is_exposed_and_excludes_the_label(self, scoped):
        permuta_ativo_id = str(uuid4())
        permuta_ext, contrato, atos = self._seed_permuta(scoped)
        scoped.set_table_data(
            "atendimento_contrato_matricula_atos",
            self._selecionar_permuta(
                contrato["id"], permuta_ativo_id, permuta_ext["id"],
                [atos[("abertura", None)]],
            ),
        )

        out = svc.obter_selecao(scoped, ORG, UUID(contrato["id"]))
        bloco = out["permutas"][0]["descricao_imovel"]

        assert bloco is not None
        assert bloco["texto"].startswith("Apartamento nº 12")
        assert "IMÓVEL:" not in bloco["texto"]
        assert "PROPRIETÁRIA" not in bloco["texto"]

    def test_a_pre_136_permuta_extraction_has_no_block_and_is_none(self, scoped):
        """The identical `None`-fallback contract as the objeto sibling
        test — a permuta extraction segmented before migration 136 has no
        `matricula_abertura_blocos` rows and must never guess one."""
        permuta_ativo_id = str(uuid4())
        permuta_ext = extracao_row()
        contrato = contrato_row()
        seed(
            scoped,
            extracoes=[permuta_ext],
            contratos=[contrato],
            negociacoes=[negociacao_row(contrato["atendimento_id"])],
            atos=svc.linhas_de_atos(permuta_ext["id"], ORG_ID, segment_matricula_atos(TEXTO)),
        )
        atos = _atos_by_kind(scoped, permuta_ext["id"])
        scoped.set_table_data(
            "atendimento_contrato_matricula_atos",
            self._selecionar_permuta(
                contrato["id"], permuta_ativo_id, permuta_ext["id"],
                [atos[("abertura", None)]],
            ),
        )

        out = svc.obter_selecao(scoped, ORG, UUID(contrato["id"]))

        assert svc.listar_atos(scoped, ORG, UUID(permuta_ext["id"]))["abertura_blocos"] == []
        assert out["permutas"][0]["descricao_imovel"] is None
