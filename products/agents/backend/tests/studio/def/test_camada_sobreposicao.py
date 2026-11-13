"""Layer overlap check (``app.studio.camada_sobreposicao``): a child section that restates its parent chain.

Deterministic, no LLM, synthetic fixtures only (a platform prompt is IP and never enters git). Thresholds were
calibrated on the real agent layers (counts in the commit); contradiction detection is a deferred LLM follow-up.
"""
from __future__ import annotations

from uuid import uuid4

from app.studio import camada_sobreposicao as cs
from app.studio import prontidao as pr
from app.studio.models import CompiledPrompt

PAI_TEXTO = (
    "Quando a pessoa pedir um reembolso, confirme o pedido, explique o prazo de análise, "
    "peça o número da compra e registre o caso. Nunca prometa valores antes da análise terminar."
)
OUTRO = (
    "Fotografias de paisagens montanhosas exigem paciência, luz suave pela manhã e um tripé firme "
    "para evitar tremores durante exposições longas."
)


def _achados(filho, pai):
    return {(a.codigo, a.chave_filho): a for a in cs.analisar(filho, pai)}


class TestAnalisar:
    def test_same_key_that_restates_the_parent_is_secao_repete_pai(self):
        a = _achados([("reembolso", PAI_TEXTO + " Sempre registre o caso.")], [("reembolso", PAI_TEXTO)])
        assert ("secao_repete_pai", "reembolso") in a
        assert a[("secao_repete_pai", "reembolso")].chave_pai == "reembolso"

    def test_different_key_that_restates_a_parent_section_is_secao_sobrepoe_pai(self):
        a = _achados([("devolucoes", PAI_TEXTO)], [("reembolso", PAI_TEXTO), ("clima", OUTRO)])
        assert a[("secao_sobrepoe_pai", "devolucoes")].chave_pai == "reembolso"

    def test_unrelated_sections_raise_nothing(self):
        assert cs.analisar([("fotos", OUTRO)], [("reembolso", PAI_TEXTO)]) == ()

    def test_stacked_role_key_is_flagged_even_with_no_lexical_overlap(self):
        a = _achados([("identidade", OUTRO)], [("identidade", PAI_TEXTO)])
        assert ("secao_papel_empilhado", "identidade") in a

    def test_topic_synonym_key_is_flagged_even_with_no_lexical_overlap(self):
        a = _achados([("encaminhamento", OUTRO)], [("transferencia", PAI_TEXTO)])
        assert a[("secao_sobrepoe_pai", "encaminhamento")].chave_pai == "transferencia"

    def test_same_key_with_distinct_content_that_is_not_a_role_is_fine(self):
        assert cs.analisar([("reembolso", OUTRO)], [("reembolso", PAI_TEXTO)]) == ()

    def test_one_finding_per_child_section_and_blank_or_short_sections_are_ignored(self):
        a = cs.analisar([("reembolso", PAI_TEXTO), ("vazia", "   "), ("curta", "reembolso prazo")], [("reembolso", PAI_TEXTO), ("curta", "reembolso prazo")])
        assert [x.chave_filho for x in a] == ["reembolso"]

    def test_findings_carry_keys_and_a_score_never_text(self):
        (a,) = cs.analisar([("reembolso", PAI_TEXTO)], [("reembolso", PAI_TEXTO)])
        assert set(a.to_dict()) == {"codigo", "chave_filho", "chave_pai", "similaridade", "motivo"}
        assert PAI_TEXTO not in str(a.to_dict())


class TestProntidao:
    def _entrada(self, achados):
        return pr.Entrada(agent_key="a", version_id=uuid4(), compiled=CompiledPrompt(texto="x", hash="h", manifest=[], tokens_estimados=1, sob_demanda=[], avisos=[]),
                          limiar=0.8, usa_canais=False, sobreposicoes_camada=achados)

    def test_findings_become_advisory_items_naming_both_keys_and_never_block(self):
        achados = cs.analisar([("reembolso", PAI_TEXTO), ("identidade", OUTRO)], [("reembolso", PAI_TEXTO), ("identidade", PAI_TEXTO)])
        p = pr.compor(self._entrada(achados))
        itens = [i for i in p.itens if i.codigo.startswith("secao_")]
        assert {i.codigo for i in itens} == {"secao_repete_pai", "secao_papel_empilhado"}
        assert all(i.severidade == "aviso" and i.recusa_publicacao is None and i.grupo == "conteudo" for i in itens)
        assert any("reembolso" in i.mensagem and "não impede a publicação" in i.mensagem for i in itens)
        assert p.bloqueantes == pr.compor(self._entrada(())).bloqueantes  # the findings add no blocker

    def test_no_findings_adds_no_item(self):
        assert not [i for i in pr.compor(self._entrada(())).itens if i.codigo.startswith("secao_")]
