"""Migration 207 — per-clause special conditions (`termos.clausulas_extras`)
and the per-deal posse multa override.

NEW tests only; V1..V6 (`contrato_gerador_fixtures`) are reused as bases and
never edited. The empty-field golden guarantee is `test_contrato_golden.py`
(unchanged) plus the explicit empty-equals-absent check below. Every name and
number here is synthetic.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from noctusai_lib.integrations.docx_render import get_docx_render_adapter

from app.modules.card_hub.contrato_gerador import derivacao, documento, lint, modelo_texto
from app.modules.card_hub.contrato_gerador.dados import ClausulaExtra
from app.modules.card_hub.contrato_gerador.numeracao import (
    CLAUSULA_CONDICIONAL,
    ORDEM_CLAUSULAS,
    TITULO_CLAUSULA,
    rotulo_clausula,
)
from tests.modules.card_hub import contrato_gerador_fixtures as fx


def _avaliar(n, d):
    pol = fx.politica_variante(n)
    sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
    return derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)


def _render(n, d):
    pol = fx.politica_variante(n)
    sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
    av = derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)
    assert av.pronto, (av.faltando, av.bloqueios)
    r = documento.renderizar(get_docx_render_adapter(real=True), d, sw, pol, fx.ASSINATURA)
    assert lint.lint(r.paragrafos, referencias=r.referencias, clausulas=r.clausulas) == []
    return r


def _com(n, **extras):
    d = fx.variante(n)
    return replace(d, termos=replace(d.termos, clausulas_extras={
        k: v if isinstance(v, ClausulaExtra) else ClausulaExtra(texto=v) for k, v in extras.items()
    }))


def _corpo(paragrafos, chave):
    """The paragraphs of one clause: from its heading to the next heading."""
    titulo = TITULO_CLAUSULA[chave]
    i = next(k for k, p in enumerate(paragrafos) if p.startswith("CLÁUSULA") and titulo in p)
    j = next((k for k in range(i + 1, len(paragrafos)) if paragrafos[k].startswith("CLÁUSULA")), len(paragrafos))
    return paragrafos[i:j]


def _codigos(itens):
    return {i["codigo"] for i in itens}


class TestClausulaRegistry:
    def test_every_generator_clause_has_a_marker_pair_in_the_template(self):
        # The import already refuses a missing/duplicated pair; this proves the
        # expansion reached the compiled template for EVERY clause key.
        for chave in ORDEM_CLAUSULAS:
            assert f"substitui.{chave} %}}" in modelo_texto.TEMPLATE
            assert f"for t in extras.{chave} %}}" in modelo_texto.TEMPLATE
        assert "⟪" not in modelo_texto.TEMPLATE

    def test_a_clause_without_markers_fails_the_import_not_the_document(self):
        bruto = modelo_texto._TEMPLATE_BRUTO.replace("⟪CLAUSULA_FIM:mora⟫", "")
        with pytest.raises(RuntimeError, match="mora"):
            modelo_texto._aplicar_clausulas_extras(bruto)

    def test_labels_are_read_off_the_clause_titles(self):
        assert rotulo_clausula("preco") == "Do preço e condições de pagamento"
        assert set(CLAUSULA_CONDICIONAL) <= set(ORDEM_CLAUSULAS)


class TestRenderizacao:
    def test_empty_extras_render_identically_to_none(self):
        base = _render(1, fx.variante(1)).paragrafos
        vazio = _render(1, _com(1, objeto="   ", posse="")).paragrafos
        assert vazio == base

    def test_append_prints_numbered_paragraphs_after_the_standard_ones(self):
        base = _corpo(_render(1, fx.variante(1)).paragrafos, "objeto")
        # V1's objeto carries ONE standard paragraph (itens integrantes): alone it
        # is "Único".
        assert [p.split(":")[0] for p in base if p.startswith("Parágrafo")] == ["Parágrafo Único"]
        corpo = _corpo(_render(1, _com(1, objeto="Primeira condição.\nSegunda condição.")).paragrafos, "objeto")
        # Standard wording first, untouched except the label — with company the
        # "Único" becomes "Primeiro" (the numbering is measured, never typed).
        assert corpo[:3] == base[:3]
        assert corpo[3] == base[3].replace("Parágrafo Único:", "Parágrafo Primeiro:")
        assert corpo[4].startswith("Parágrafo Segundo: Primeira condição.")
        assert corpo[5].startswith("Parágrafo Terceiro: Segunda condição.")
        assert len(corpo) == len(base) + 2

    def test_append_continues_the_clause_numbering_and_lone_one_is_unico(self):
        r = _render(1, _com(1, vistoria="O imóvel foi vistoriado por fotos (Anexo 1)."))
        corpo = _corpo(r.paragrafos, "vistoria")
        assert corpo[-1] == "Parágrafo Único: O imóvel foi vistoriado por fotos (Anexo 1)."

        r = _render(1, _com(1, tributos="Condição extra de tributos."))
        paragrafos = [p for p in _corpo(r.paragrafos, "tributos") if p.startswith("Parágrafo")]
        rotulos = [p.split(":")[0] for p in paragrafos]
        assert rotulos == ["Parágrafo Primeiro", "Parágrafo Segundo", "Parágrafo Terceiro"]
        assert paragrafos[-1].endswith("Condição extra de tributos.")

    def test_replace_drops_the_standard_body_keeps_heading_and_number(self):
        padrao = _render(1, fx.variante(1))
        r = _render(1, _com(1, vistoria=ClausulaExtra(
            texto="Texto próprio da vistoria.\nSegundo parágrafo próprio.", modo="substituir")))
        corpo = _corpo(r.paragrafos, "vistoria")
        assert corpo[0] == _corpo(padrao.paragrafos, "vistoria")[0]  # same heading + ordinal
        assert corpo[1:] == [
            "Texto próprio da vistoria.",  # the clause body: unlabelled, like every caput
            "Parágrafo Único: Segundo parágrafo próprio.",
        ]
        assert r.clausulas == padrao.clausulas  # numbering untouched
        assert "pessoalmente vistoriado" not in "\n".join(r.paragrafos)

    def test_replace_of_a_clause_other_clauses_cross_reference_keeps_the_references(self):
        r = _render(1, _com(1, objeto=ClausulaExtra(texto="Objeto reescrito.", modo="substituir")))
        assert "descrito na Cláusula Primeira" in "\n".join(r.paragrafos)

    def test_conditional_clause_off_is_refused_not_dropped(self):
        d = _com(1, assinatura_digital="Texto para uma cláusula que não existe.")
        d = replace(d, modalidade_assinatura="fisica")
        av = _avaliar(1, d)
        assert "CLAUSULA_EXTRA_SEM_CLAUSULA" in _codigos(av.bloqueios)

    def test_conditional_clause_on_accepts_extras(self):
        r = _render(1, _com(1, assinatura_digital="Anexo técnico da plataforma."))
        assert _corpo(r.paragrafos, "assinatura_digital")[-1].endswith("Anexo técnico da plataforma.")


class TestAvisosERevisao:
    def test_append_raises_an_aviso_and_a_review_item_per_clause(self):
        av = _avaliar(1, _com(1, objeto="A.", preco="B."))
        assert {"CLAUSULA_EXTRA_OBJETO", "CLAUSULA_EXTRA_PRECO"} <= _codigos(av.avisos)
        assert {"CLAUSULA_EXTRA_OBJETO", "CLAUSULA_EXTRA_PRECO"} <= _codigos(av.itens_revisao)
        item = next(i for i in av.itens_revisao if i["codigo"] == "CLAUSULA_EXTRA_OBJETO")
        assert item["texto"] == "A."

    def test_replace_is_a_stronger_aviso_with_its_own_code(self):
        av = _avaliar(1, _com(1, posse=ClausulaExtra(texto="Posse reescrita.", modo="substituir")))
        assert "CLAUSULA_SUBSTITUIDA_POSSE" in _codigos(av.avisos)
        assert "CLAUSULA_EXTRA_POSSE" not in _codigos(av.avisos)
        aviso = next(a for a in av.avisos if a["codigo"] == "CLAUSULA_SUBSTITUIDA_POSSE")
        assert "NÃO será impresso" in aviso["mensagem"]
        assert "CLAUSULA_SUBSTITUIDA_POSSE" in _codigos(av.itens_revisao)

    def test_no_extras_no_aviso(self):
        av = _avaliar(1, fx.variante(1))
        assert not [c for c in _codigos(av.avisos) | _codigos(av.itens_revisao) if c.startswith("CLAUSULA_")]

    def test_unknown_key_invalid_mode_and_markup_block(self):
        d = fx.variante(1)
        d = replace(d, termos=replace(d.termos, clausulas_extras={
            "clausula_x": ClausulaExtra(texto="x"),
            "posse": ClausulaExtra(texto="y", modo="apagar"),
            "objeto": ClausulaExtra(texto="com **negrito**"),
        }))
        bloqueios = _codigos(_avaliar(1, d).bloqueios)
        assert {"CLAUSULA_EXTRA_DESCONHECIDA", "CLAUSULA_EXTRA_MODO_INVALIDO",
                "TEXTO_LIVRE_COM_MARCACAO"} <= bloqueios


class TestPosseMultaDiaria:
    def test_override_beats_the_office_default_in_the_text(self):
        d = fx.variante(1)
        assert d.imobiliaria.posse_multa_diaria == Decimal("500.00")
        padrao = "\n".join(_render(1, d).paragrafos)
        assert "R$ 500,00 (quinhentos reais) por dia de atraso" in padrao
        d2 = replace(d, termos=replace(d.termos, posse_multa_diaria=Decimal("250.00")))
        texto = "\n".join(_render(1, d2).paragrafos)
        assert "R$ 250,00 (duzentos e cinquenta reais) por dia de atraso" in texto
        assert "R$ 500,00" not in texto

    def test_override_satisfies_a_missing_office_value(self):
        d = fx.variante(1)
        sem_escritorio = replace(d, imobiliaria=replace(d.imobiliaria, posse_multa_diaria=None))
        av = _avaliar(1, sem_escritorio)
        assert "imobiliaria.posse_multa_diaria" in {f["campo"] for f in av.faltando}
        com = replace(sem_escritorio, termos=replace(sem_escritorio.termos, posse_multa_diaria=Decimal("100")))
        assert "imobiliaria.posse_multa_diaria" not in {f["campo"] for f in _avaliar(1, com).faltando}
        assert "R$ 100,00 (cem reais) por dia de atraso" in "\n".join(_render(1, com).paragrafos)

    def test_a_non_positive_override_blocks(self):
        d = fx.variante(1)
        d = replace(d, termos=replace(d.termos, posse_multa_diaria=Decimal("0")))
        assert "MULTA_DIARIA_POSSE_INVALIDA" in _codigos(_avaliar(1, d).bloqueios)
