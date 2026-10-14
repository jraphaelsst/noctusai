"""Pure clustering tests: variants collapse, different cities / numbers don't."""
from __future__ import annotations

from app.modules.condominios import normalizacao as n


def obs(alias, total=1, cidade="Cotia", bairro=None):
    o = n.Observacao(alias=alias, chave=n.alias_key(alias), total=total)
    if cidade:
        o.cidades[cidade] += total
    if bairro:
        o.bairros[bairro] += total
    return o


def test_alias_key_is_upper_btrim_collapsed_and_keeps_accents():
    assert n.alias_key("  Vila   Verde ") == "VILA VERDE"
    assert n.alias_key("Granja Viana São") == "GRANJA VIANA SÃO"
    assert n.alias_key("   ") is None and n.alias_key(None) is None


def test_match_key_strips_accents_punctuation_and_prefixes():
    assert n.match_key("Cond. Residencial Vila-Verde") == "VILA VERDE"
    assert n.match_key("CONDOMÍNIO Vila Verde") == "VILA VERDE"
    assert n.match_key("Residencial") is None


def test_variants_collapse_into_one_cluster():
    cs = n.agrupar([
        obs("VILA VERDE", 10), obs("Condominio Vila Verde", 3), obs("COND. VILA VERDE", 2),
        obs("Vila Verd", 1), obs("Chácara Ipê", 4),
    ])
    nomes = sorted(sorted(m.alias for m in c.membros) for c in cs)
    assert len(cs) == 2
    assert any(len(x) == 4 for x in nomes)
    assert next(c for c in cs if len(c.membros) == 4).principal.alias == "VILA VERDE"


def test_different_cities_do_not_collapse():
    cs = n.agrupar([obs("Vila Verde", 5, cidade="Cotia"), obs("Vila Verde ", 5, cidade="Carapicuíba")])
    assert len(cs) == 2


def test_numbered_siblings_stay_apart():
    cs = n.agrupar([obs("Vila Verde 1", 5), obs("Vila Verde 2", 5)])
    assert len(cs) == 2
