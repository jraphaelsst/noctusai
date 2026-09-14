"""`obter_selecao`'s `formatacao` — document-level ranges re-based onto the
selection's own concatenated text (contract
`projects/abnt-formatting-CONTRACT.md` §5, consumed by
`card_hub.contrato_gerador.carregador` for the matrícula quote's
bold/underline).

Standalone file (not appended to `test_matricula_estrutura_service.py`) —
that file is shared with the S3 slice's own `matriculas/**` edits; keeping
this in its own file avoids any merge-conflict surface with that parallel
work. `matricula_extracoes.formatacao` (migration 113, S3's slice) is not
in `conftest.extracao_row()` yet, so every extraction row here adds the
key by hand — exactly what the brief calls for ("seed the fake rows with
it").
"""
from __future__ import annotations

from uuid import UUID, uuid4

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

# `segment_matricula_atos(TEXTO)` boundaries (pinned so this file fails
# loudly, not silently, if the shared fixture text ever changes):
#   abertura [0, 298)  R-1 [298, 441)  R-2 [441, 521)
_ABERTURA = (0, 298)
_R1 = (298, 441)
_R2 = (441, 521)


def _atos_by_kind(scoped, extracao_id: str) -> dict:
    atos = svc.listar_atos(scoped, ORG, UUID(extracao_id))["atos"]
    return {(a["kind"], a["numero"]): a for a in atos}


def _selecionar(contrato_id: str, extracao_id: str, atos_em_ordem: list[dict]) -> list[dict]:
    """Seed `atendimento_contrato_matricula_atos` rows directly (rather
    than via `definir_selecao`) so the CONTRACT order can be set
    explicitly, independent of extraction order — `obter_selecao` must
    rebase against contract order, not extraction order."""
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


def _seed(scoped, *, formatacao=None) -> tuple[dict, dict, dict]:
    ext = extracao_row()
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


class TestObterSelecaoFormatacao:
    def test_no_formatacao_key_at_all_returns_an_empty_list(self, scoped):
        """The pre-113 shape (no column yet / a row written before it
        existed) must not error — `[]`, exactly like an unformatted quote."""
        ext, contrato, atos = _seed(scoped)  # formatacao=None -> key absent/null either way

        scoped.set_table_data(
            "atendimento_contrato_matricula_atos",
            _selecionar(contrato["id"], ext["id"], [atos[("abertura", None)]]),
        )

        out = svc.obter_selecao(scoped, ORG, UUID(contrato["id"]))

        assert out["formatacao"] == []

    def test_an_empty_selection_has_no_formatacao_either(self, scoped):
        ext, contrato, _atos = _seed(scoped, formatacao=[{"start": 0, "end": 5, "bold": True}])
        scoped.set_table_data("atendimento_contrato_matricula_atos", [])

        out = svc.obter_selecao(scoped, ORG, UUID(contrato["id"]))

        assert out["texto"] == "" and out["formatacao"] == []

    def test_a_range_fully_inside_one_selected_act_is_kept_verbatim(self, scoped):
        # A range on the abertura's first 5 chars ("MATRÍ"), abertura selected alone.
        ext, contrato, atos = _seed(scoped, formatacao=[{"start": 0, "end": 5, "bold": True}])
        scoped.set_table_data(
            "atendimento_contrato_matricula_atos",
            _selecionar(contrato["id"], ext["id"], [atos[("abertura", None)]]),
        )

        out = svc.obter_selecao(scoped, ORG, UUID(contrato["id"]))

        assert ranges_from_json(out["formatacao"])[0].start == 0
        assert ranges_from_json(out["formatacao"])[0].end == 5
        assert out["texto"][0:5] == TEXTO[0:5]

    def test_a_range_outside_every_selected_act_is_dropped(self, scoped):
        # The range sits inside R-2 ([441, 521)); only abertura + R-1 are selected.
        ext, contrato, atos = _seed(
            scoped, formatacao=[{"start": _R2[0] + 5, "end": _R2[0] + 15, "underline": True}]
        )
        scoped.set_table_data(
            "atendimento_contrato_matricula_atos",
            _selecionar(
                contrato["id"], ext["id"], [atos[("abertura", None)], atos[("R", 1)]]
            ),
        )

        out = svc.obter_selecao(scoped, ORG, UUID(contrato["id"]))

        assert out["formatacao"] == []
        assert out["texto"] == TEXTO[_ABERTURA[0] : _ABERTURA[1]] + TEXTO[_R1[0] : _R1[1]]

    def test_a_range_crossing_an_act_boundary_is_clipped_per_act(self, scoped):
        # [290, 305) straddles the abertura/R-1 boundary at 298.
        ext, contrato, atos = _seed(
            scoped, formatacao=[{"start": 290, "end": 305, "bold": True}]
        )
        scoped.set_table_data(
            "atendimento_contrato_matricula_atos",
            _selecionar(
                contrato["id"], ext["id"], [atos[("abertura", None)], atos[("R", 1)]]
            ),
        )

        out = svc.obter_selecao(scoped, ORG, UUID(contrato["id"]))
        rebased = sorted(ranges_from_json(out["formatacao"]), key=lambda r: r.start)

        # abertura occupies output [0, 298) unchanged (contract order ==
        # extraction order here) — the boundary at 298 in the SOURCE lands
        # at 298 in the OUTPUT too, so the two clipped halves stay adjacent.
        assert [(r.start, r.end, r.bold) for r in rebased] == [(290, 298, True), (298, 305, True)]
        # Reassembling the quote from the two halves reproduces the source slice.
        assert out["texto"][290:305] == TEXTO[290:305]

    def test_contract_order_different_from_extraction_order_rebases_correctly(self, scoped):
        # Select R-1 THEN abertura (reversed) — output = R-1's text + abertura's text.
        # A range inside R-1 near ITS end, and one inside abertura's start.
        r1_len = _R1[1] - _R1[0]
        ext, contrato, atos = _seed(
            scoped,
            formatacao=[
                {"start": _R1[1] - 5, "end": _R1[1], "bold": True},  # last 5 chars of R-1
                {"start": 0, "end": 5, "underline": True},  # first 5 chars of abertura
            ],
        )
        scoped.set_table_data(
            "atendimento_contrato_matricula_atos",
            _selecionar(
                contrato["id"], ext["id"], [atos[("R", 1)], atos[("abertura", None)]]
            ),
        )

        out = svc.obter_selecao(scoped, ORG, UUID(contrato["id"]))
        rebased = sorted(ranges_from_json(out["formatacao"]), key=lambda r: r.start)

        assert out["texto"] == TEXTO[_R1[0] : _R1[1]] + TEXTO[_ABERTURA[0] : _ABERTURA[1]]
        # R-1's range lands at the END of R-1's own output slice: [r1_len-5, r1_len).
        assert (rebased[0].start, rebased[0].end, rebased[0].bold) == (r1_len - 5, r1_len, True)
        # abertura's range is shifted by r1_len (abertura now comes SECOND).
        assert (rebased[1].start, rebased[1].end, rebased[1].underline) == (
            r1_len,
            r1_len + 5,
            True,
        )
