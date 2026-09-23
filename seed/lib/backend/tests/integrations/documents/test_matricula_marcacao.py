"""`remover_marcacao` — lossless marker strip for legacy transcriptions, with
the offset map every stored span is rewritten through."""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents.matricula_abertura import segmentar_abertura
from noctusai_lib.integrations.documents.matricula_atos import segment_matricula_atos
from noctusai_lib.integrations.documents.matricula_marcacao import (
    remover_boilerplate,
    remover_marcacao,
)
from noctusai_lib.integrations.documents.transcription import has_raw_markup

LEGADO = (
    "**MATRÍCULA Nº 45.678**\n"
    "**IMÓVEL:** Apartamento <u>nº 12</u> do Edifício Ficticio.\n"
    "**CADASTRO MUNICIPAL:** Contribuinte 123.456.7-8.\n"
    "R-1/45.678 - Em 10 de março de 2001. **COMPRA E VENDA**.\n"
    "AV-2/45.678 - CANCELAMENTO do R-1.\n"
)


def test_strips_every_balanced_marker_and_keeps_formatting():
    r = remover_marcacao(LEGADO)
    assert not has_raw_markup(r.texto)
    assert r.alterou
    negritos = [r.texto[f.start : f.end] for f in r.formatacao if f.bold]
    assert "MATRÍCULA Nº 45.678" in negritos
    assert "COMPRA E VENDA" in negritos
    assert any(r.texto[f.start : f.end] == "nº 12" for f in r.formatacao if f.underline)


def test_every_mapped_offset_points_at_the_same_character():
    r = remover_marcacao(LEGADO)
    removido = set()
    for s, e in r.removidos:
        removido.update(range(s, e))
    for i, ch in enumerate(LEGADO):
        if i in removido:
            continue
        assert r.texto[r.mapear(i)] == ch


def test_mapped_act_spans_equal_fresh_segmentation_of_clean_text():
    """The offsets we REWRITE must equal what segmenting the clean text
    would have produced — that is what keeps act ids stable."""
    r = remover_marcacao(LEGADO)
    antes = segment_matricula_atos(LEGADO)
    depois = segment_matricula_atos(r.texto)
    assert [(a.kind, a.numero) for a in antes] == [(a.kind, a.numero) for a in depois]
    for a, d in zip(antes, depois):
        if a.kind == "abertura":
            continue
        assert r.mapear(a.start) == d.start


def test_clean_text_unlocks_abertura_blocks():
    r = remover_marcacao(LEGADO)
    abertura = segment_matricula_atos(r.texto)[0]
    campos = [b.campo for b in segmentar_abertura(r.texto, abertura.start, abertura.end)]
    assert "descricao_imovel" in campos
    assert "cadastro_municipal" in campos
    # ...which the markered text could not do.
    ab_legado = segment_matricula_atos(LEGADO)[0]
    assert segmentar_abertura(LEGADO, ab_legado.start, ab_legado.end) == ()


def test_offset_inside_a_marker_lands_on_its_start():
    r = remover_marcacao("ab**cd**")
    assert r.texto == "abcd"
    assert r.mapear(3) == 2  # inside the first `**`
    assert r.mapear(8) == 4  # end of text


def test_unbalanced_marker_is_kept_literal_like_parse_markup():
    r = remover_marcacao("a **b** c **d")
    assert r.texto == "a b c **d"
    assert has_raw_markup(r.texto)


def test_clean_text_is_a_noop():
    r = remover_marcacao("sem marcas")
    assert not r.alterou
    assert r.mapear(4) == 4


@pytest.mark.parametrize("texto", ["", "**", "<u></u>", "**x**<u>y</u>"])
def test_edge_shapes_never_raise(texto):
    remover_marcacao(texto)


# ── `remover_boilerplate` — registry provenance stamps, offset-tracked ──

EUROVILLE_PAGINA_1 = (
    "```\n"
    "Valide aqui\n"
    "este documento\n"
    "\n"
    "Mat. 3917 - Página 1/3 - PROT. 89.029\n"
    "\n"
    "CNM: 148429.2.0003917-55\n"
    "\n"
    "LIVRO Nº 2 - REGISTRO GERAL\n"
    "\n"
    "IMOVEL: Terreno situado na Alameda Alemanha.\n"
)


def test_the_eurovile_stamp_comes_out_and_offsets_still_land_on_the_same_char():
    r = remover_boilerplate(EUROVILLE_PAGINA_1)
    assert r.alterou
    assert "Valide aqui" not in r.texto
    assert "```" not in r.texto
    assert "Mat. 3917 - Página 1/3 - PROT. 89.029" in r.texto
    # Nothing was trimmed OUTSIDE `removidos` — every surviving character
    # maps back onto itself, the same invariant `remover_marcacao` pins.
    removido = set()
    for s, e in r.removidos:
        removido.update(range(s, e))
    for i, ch in enumerate(EUROVILLE_PAGINA_1):
        if i in removido:
            continue
        assert r.texto[r.mapear(i)] == ch


def test_a_page_with_no_boilerplate_is_a_noop():
    r = remover_boilerplate("IMOVEL: Terreno na Alameda Alemanha.\n")
    assert not r.alterou
    assert r.texto == "IMOVEL: Terreno na Alameda Alemanha.\n"


def test_composes_with_remover_marcacao_the_way_normalizar_extracao_does():
    """The shape `backfill_service.normalizar_extracao` relies on: run
    `remover_marcacao` first, `remover_boilerplate` on ITS clean text
    second, then chain the two maps for every downstream offset."""
    bruto = "Valide aqui\neste documento\n\n**IMÓVEL:** Apartamento nº 12.\n"
    r1 = remover_marcacao(bruto)
    r2 = remover_boilerplate(r1.texto)

    assert "Valide aqui" not in r2.texto
    assert not has_raw_markup(r2.texto)
    assert "IMÓVEL: Apartamento nº 12." in r2.texto

    # An offset into the ORIGINAL (markered, stamped) text still lands on
    # the same character after both passes.
    alvo = bruto.index("Apartamento")
    assert r2.texto[r2.mapear(r1.mapear(alvo))] == bruto[alvo]


@pytest.mark.parametrize("texto", ["", "Valide aqui\n", "sem marcas\n"])
def test_edge_shapes_never_raise_boilerplate(texto):
    remover_boilerplate(texto)
