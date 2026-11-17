"""EST-4a: free-text profile-name resolution (deterministic), the pool (scope / round-robin / seed), and the
Estrutura rendering (estruturas-contract.md sections 8.1-8.3)."""
import uuid

import pytest

from noctusai_lib.testing import MockSupabaseClient

from app.modules.media_creation.prompts import estruturas_contexto as ctx
from app.modules.media_creation.services import estruturas_retrieval as er
from app.modules.media_creation.services.estruturas_retrieval import (
    CacheIndice,
    FiltrosPool,
    PerfilIndexado,
    montar_pool,
    normalizar,
    resolver_perfis_no_texto,
    selecionar_ids,
)

P = PerfilIndexado.criar


def _indice():
    return [
        P("p-fs", "psifernandosegredo", "Fernando Segredo"),
        P("p-fm", "fernando.mendes", "Fernando Mendes"),
        P("p-fl", "fernandolima_oficial", "Fernando Lima"),
        P("p-ma", "mariaclara", "Maria Clara"),
        P("p-jc", "dr.joaocarlos", "João Carlos"),
        P("p-sem", "semestruturas", "Sem Estruturas", sem_estruturas=True),
    ]


def _ids(res):
    return [r.perfil_id for r in res.resolvidos]


# ── normalisation ────────────────────────────────────────────────────────────────────────────────────────────

def test_normalizar_folds_accents_case_and_junk_but_keeps_handle_characters():
    assert normalizar("  Estilo do JOÃO   Carlos!! ") == "estilo do joao carlos |"
    assert normalizar("@Dr.João_Silva") == "@dr.joao_silva"
    assert normalizar("ｆｕｌｌ ＷＩＤＴＨ") == "full width"
    assert normalizar("") == "" and normalizar("😀") == ""


# ── resolver: the contract's pinned examples ─────────────────────────────────────────────────────────────────

def test_pinned_resolved_example():
    r = resolver_perfis_no_texto("um post no estilo do Fernando Segredo", _indice())
    assert _ids(r) == ["p-fs"] and r.resolvidos[0].via == "nome" and r.resolvidos[0].confianca >= 0.8
    assert not r.ambiguos and not r.nao_encontrados


def test_pinned_ambiguous_example_several_fernando():
    r = resolver_perfis_no_texto("no estilo do Fernando", _indice())
    assert not r.resolvidos and len(r.ambiguos) == 1
    assert {c.id for c in r.ambiguos[0].candidatos} == {"p-fs", "p-fm", "p-fl"} and r.ambiguos[0].trecho == "fernando"


def test_pinned_not_found_example():
    r = resolver_perfis_no_texto("estilo do João", [p for p in _indice() if p.id != "p-jc"])
    assert not r.resolvidos and not r.ambiguos and [n.trecho for n in r.nao_encontrados] == ["joao"]


# ── resolver: table-driven ───────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("texto,esperado", [
    ("quero algo como o @psifernandosegredo", ["p-fs"]),                      # @handle
    ("QUERO ALGO COMO O @PsiFernandoSegredo", ["p-fs"]),                      # case
    ("um carrossel parecido com a Maria Clara", ["p-ma"]),                    # nome exact (0.95)
    ("inspirado no João Carlos sobre implantes", ["p-jc"]),                   # trailing words after the name
    ("estilo da MARIA CLARA, mas mais curto", ["p-ma"]),                      # clause break
    ("estilo do joao carlos e estilo da maria clara", ["p-jc", "p-ma"]),      # two spans
    ("baseado em fernando segredo", ["p-fs"]),                                # trigger "baseado em"
    ("faz uma headline do perfil dr.joaocarlos", ["p-jc"]),                   # handle after "do perfil"
    ("estilo do fernando segredo", ["p-fs"]),                                 # accent-free input
    ("me escreva 5 headlines sobre implantes", []),                           # no trigger, no @: nothing resolved
    ("o Fernando Segredo escreveu um livro", []),                             # a name WITHOUT a trigger resolves nothing
    ("", []),
])
def test_table_driven_resolution(texto, esperado):
    r = resolver_perfis_no_texto(texto, _indice())
    assert _ids(r) == esperado
    if not esperado:
        assert not r.ambiguos and not r.nao_encontrados


def test_no_trigger_text_with_a_known_name_never_resolves_even_ambiguously():
    r = resolver_perfis_no_texto("Fernando disse que Maria Clara gosta de cafe", _indice())
    assert r.vazia


def test_a_unique_partial_name_resolves_but_a_weak_single_token_match_only_asks():
    assert _ids(resolver_perfis_no_texto("estilo do carlos", _indice())) == ["p-jc"]  # 0.8, no rival
    r = resolver_perfis_no_texto("estilo da xyz clara", _indice())  # one distinctive token (0.6): never auto-picked
    assert not r.resolvidos and [c.id for c in r.ambiguos[0].candidatos] == ["p-ma"]


def test_the_at_handle_after_a_trigger_is_not_also_reported_as_a_not_found_name():
    r = resolver_perfis_no_texto("quero algo como o @psifernandosegredo", _indice())
    assert _ids(r) == ["p-fs"] and not r.nao_encontrados and r.resolvidos[0].via == "mencao"


def test_unknown_at_handle_is_reported_unless_asked_not_to():
    assert [n.trecho for n in resolver_perfis_no_texto("copia o @naoexiste123", _indice()).nao_encontrados] == ["@naoexiste123"]
    assert resolver_perfis_no_texto("copia o @naoexiste123", _indice(), reportar_arroba_desconhecido=False).vazia


def test_sem_estruturas_profiles_are_indexed_and_flagged():
    r = resolver_perfis_no_texto("estilo do sem estruturas", _indice())
    assert _ids(r) == ["p-sem"] and r.resolvidos[0].sem_estruturas is True


def test_resposta_shape_and_events():
    r = resolver_perfis_no_texto("estilo do Fernando Segredo e no estilo do Fernando", _indice())
    d = r.como_dict()
    assert set(d) == {"resolvidos", "ambiguos", "nao_encontrados"}
    assert set(d["resolvidos"][0]) == {"perfil_id", "handle", "nome", "via", "confianca"}
    assert set(d["ambiguos"][0]) == {"trecho", "candidatos"} and set(d["ambiguos"][0]["candidatos"][0]) == {"perfil_id", "handle", "nome"}
    assert r.eventos() == [{"tipo": "perfil_resolvido", "contagem": 1}, {"tipo": "perfil_ambiguo", "contagem": 1}]


def test_the_resolver_is_deterministic():
    a = resolver_perfis_no_texto("estilo do Fernando", _indice()).como_dict()
    assert all(resolver_perfis_no_texto("estilo do Fernando", _indice()).como_dict() == a for _ in range(3))


# ── the index cache ──────────────────────────────────────────────────────────────────────────────────────────

def _db_com_perfis():
    db = MockSupabaseClient()
    db.from_("cs_perfis_monitorados").insert([
        {"id": "p1", "handle": "fulano", "nome": "Fulano de Tal"}, {"id": "p2", "handle": "ciclano", "nome": None},
    ]).execute()
    db.from_("cs_estruturas").insert([
        {"id": "e1", "perfil_id": "p1", "status": "ativa"}, {"id": "e2", "perfil_id": "p2", "status": "rascunho"},
    ]).execute()
    return db


def test_index_load_flags_profiles_without_an_ativa_estrutura():
    idx = {p.id: p for p in er.carregar_indice(_db_com_perfis())}
    assert idx["p1"].sem_estruturas is False and idx["p2"].sem_estruturas is True


def test_index_is_cached_60s_per_client_and_refreshes_after():
    t = [1000.0]
    cache = CacheIndice(ttl_s=60, relogio=lambda: t[0])
    db = _db_com_perfis()
    primeiro = cache.obter(db)
    db.from_("cs_perfis_monitorados").insert({"id": "p3", "handle": "novo", "nome": "Novo"}).execute()
    t[0] += 59
    assert cache.obter(db) is primeiro and len(primeiro) == 2
    t[0] += 2
    assert len(cache.obter(db)) == 3
    assert len(cache.obter(_db_com_perfis())) == 2  # another client never reads this one's entry


# ── the pool ─────────────────────────────────────────────────────────────────────────────────────────────────

def _linhas(n_por_perfil):
    return [{"id": f"{p}-{i}", "perfil_id": p} for p, n in n_por_perfil.items() for i in range(n)]


def test_selection_is_round_robin_across_profiles():
    ids = selecionar_ids(_linhas({"a": 10, "b": 10, "c": 10}), semente="s", limite=9)
    por_perfil = [i.split("-")[0] for i in ids]
    assert sorted(set(por_perfil)) == ["a", "b", "c"] and all(por_perfil.count(p) == 3 for p in "abc")
    # a rotation: each block of three has one of each profile
    assert all(sorted(por_perfil[i:i + 3]) == ["a", "b", "c"] for i in (0, 3, 6))


def test_selection_is_deterministic_independent_of_input_order_and_varies_with_the_seed():
    linhas = _linhas({"a": 20, "b": 20})
    a = selecionar_ids(linhas, semente="conversa-1", limite=8)
    assert a == selecionar_ids(list(reversed(linhas)), semente="conversa-1", limite=8)
    assert a != selecionar_ids(linhas, semente="conversa-2", limite=8)


def test_a_small_profile_does_not_starve_and_the_cap_holds():
    ids = selecionar_ids(_linhas({"a": 1, "b": 30}), semente="s", limite=12)
    assert len(ids) == 12 and "a-0" in ids and selecionar_ids([], semente="s", limite=12) == []


def _seed_biblioteca(db):
    db.from_("cs_perfis_monitorados").insert([{"id": "pa", "handle": "alfa", "nome": "Alfa"}, {"id": "pb", "handle": "beta", "nome": "Beta"}]).execute()
    db.from_("cs_estrutura_tipos_bloco").insert({"id": "t1", "nome": "Headline", "instrucao_referencia": "Abra forte"}).execute()
    rows = [
        {"id": "e1", "codigo": 1, "perfil_id": "pa", "status": "ativa", "formato": "reels", "objetivos": ["alcance"], "formula_headline": "Pare de [dor]"},
        {"id": "e2", "codigo": 2, "perfil_id": "pa", "status": "ativa", "formato": "carrossel", "objetivos": ["venda"], "formula_headline": "F2"},
        {"id": "e3", "codigo": 3, "perfil_id": "pb", "status": "ativa", "formato": "reels", "objetivos": ["autoridade"], "formula_headline": "F3"},
        {"id": "e4", "codigo": 4, "perfil_id": "pb", "status": "rascunho", "formato": "reels", "objetivos": ["alcance"], "formula_headline": "RASCUNHO"},
        {"id": "e5", "codigo": 5, "perfil_id": "pb", "status": "arquivada", "formato": "reels", "objetivos": ["alcance"], "formula_headline": "ARQUIVADA"},
    ]
    db.from_("cs_estruturas").insert(rows).execute()
    db.from_("cs_estrutura_blocos").insert([
        {"estrutura_id": "e1", "ordem": 2, "tipo_id": "t1", "nome": "Fecho", "tempo": "5s", "instrucao": None, "nota": None, "repeticoes": 2},
        {"estrutura_id": "e1", "ordem": 1, "tipo_id": "t1", "nome": "Abertura", "tempo": None, "instrucao": "Direto ao ponto", "nota": "curto", "repeticoes": 1},
    ]).execute()


def test_pool_offers_only_ativa_and_the_whole_library_when_no_scope():
    db = MockSupabaseClient()
    _seed_biblioteca(db)
    pool = montar_pool(db, FiltrosPool(), semente="s")
    assert {e.codigo for e in pool} == {"1", "2", "3"}  # never a rascunho / arquivada


def test_pool_scope_to_selected_profiles_and_an_empty_scope_is_nothing_not_everything():
    db = MockSupabaseClient()
    _seed_biblioteca(db)
    assert {e.codigo for e in montar_pool(db, FiltrosPool(perfil_ids=["pb"]), semente="s")} == {"3"}
    assert montar_pool(db, FiltrosPool(perfil_ids=[]), semente="s") == []


def test_pool_filters_formato_objetivos_and_explicit_ids():
    db = MockSupabaseClient()
    _seed_biblioteca(db)
    assert {e.codigo for e in montar_pool(db, FiltrosPool(formato="reels"), semente="s")} == {"1", "3"}
    assert {e.codigo for e in montar_pool(db, FiltrosPool(objetivos=["venda"]), semente="s")} == {"2"}
    assert {e.codigo for e in montar_pool(db, FiltrosPool(estrutura_ids=["e3", "e4"]), semente="s")} == {"3"}  # e4 is a rascunho


def test_pool_rows_carry_ordered_blocks_with_the_type_reference_as_instruction_fallback():
    db = MockSupabaseClient()
    _seed_biblioteca(db)
    e1 = next(e for e in montar_pool(db, FiltrosPool(estrutura_ids=["e1"]), semente="s"))
    assert e1.handle == "alfa" and [b.nome for b in e1.blocos] == ["Abertura", "Fecho"]
    assert e1.blocos[0].instrucao == "Direto ao ponto" and e1.blocos[1].instrucao == "Abra forte" and e1.blocos[1].repeticoes == 2


# ── rendering ────────────────────────────────────────────────────────────────────────────────────────────────

def test_render_shape_from_the_contract():
    db = MockSupabaseClient()
    _seed_biblioteca(db)
    e1 = montar_pool(db, FiltrosPool(estrutura_ids=["e1"]), semente="s")[0]
    linha = ctx.renderizar_estrutura(e1)
    assert linha.startswith("estrutura #1 (@alfa) | formato: reels | objetivos: alcance | FÓRMULA: Pare de [dor] | BLOCOS: 1. Headline «Abertura»")
    assert "— Direto ao ponto (curto); 2. Headline «Fecho» [5s] — Abra forte × 2" in linha


def test_render_is_capped_and_truncates_blocks_at_a_boundary_with_a_marker():
    blocos = tuple(er.BlocoPool(i, "Tipo", f"Bloco numero {i}", "10s", "instrução bem longa " * 3, None, 1) for i in range(1, 20))
    e = er.EstruturaPool("x", "7", None, "h", "reels", ("alcance",), "F", blocos)
    linha = ctx.renderizar_estrutura(e)
    assert len(linha) <= ctx.MAX_CHARS_ESTRUTURA and linha.endswith(ctx.MARCADOR_BLOCOS)
    assert "Bloco numero 1 " in linha or "Bloco numero 1«" in linha or "«Bloco numero 1»" in linha
    corpo = linha.removesuffix(ctx.MARCADOR_BLOCOS)
    assert not corpo.endswith(("instruçã", "long")) or corpo.endswith("longa")  # a whole block, never mid-word


def test_render_without_blocks_or_with_a_huge_formula_never_exceeds_the_cap():
    e = er.EstruturaPool("x", "7", None, None, None, (), "F " * 900, ())
    assert len(ctx.renderizar_estrutura(e)) <= ctx.MAX_CHARS_ESTRUTURA
    assert ctx.renderizar_estrutura(er.EstruturaPool("x", "8", None, "h", "post", ("venda",), "F", ())).endswith("FÓRMULA: F")
