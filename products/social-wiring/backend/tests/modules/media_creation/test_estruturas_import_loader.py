"""The Estruturas LOADER (estruturas-contract.md section 7): mapping, validation, idempotency, provenance, accounting.

Synthetic corpora only (``_estruturas_import_fixtures``): the real files are vendor-derived and never enter git. The
RPC SQL itself runs on PGlite in ``test_estruturas_import_on_replay.py``; here a recording store double stands in.
"""
import ast
from pathlib import Path

import pytest

from app.modules.media_creation.services import estruturas_import as imp

from ._estruturas_import_fake_store import FakeApiError, FakeStore
from ._estruturas_import_fixtures import (
    SENTINELA, TIPOS_CATALOGO, bloco_ref, copia, corpus_maquina, corpus_ref, linha_ref,
)

SERVICE = Path(imp.__file__)


def run(store, fonte, conteudo, *, aplicar=True, limite=1000):
    return imp.executar(store, fonte, conteudo, aplicar=aplicar, importacao_id="imp-1", ator_id="admin-1", limite_perfis=limite)


# ── validation: every coded ignore ───────────────────────────────────────────────────────────────────────


def motivo(row, tipos=TIPOS_CATALOGO):
    p = imp.parse_documento("referencia", [row], tipos)
    assert p.linhas_total == 1
    assert len(p.ignoradas) + len(p.linhas) == 1
    return p.ignoradas[0][1] if p.ignoradas else None


@pytest.mark.parametrize("row,esperado", [
    (linha_ref(1, perfil="Nome Com Espaço"), imp.M_HANDLE),
    (linha_ref(1, perfil="x" * 31), imp.M_HANDLE),
    (linha_ref(1) | {"perfil": 5}, imp.M_HANDLE),
    (linha_ref(1, corestudio_id="12a"), imp.M_ID),
    (linha_ref(1, corestudio_id=12), imp.M_ID),
    (linha_ref(1, formula_herdada_de="abc"), imp.M_ID),
    (linha_ref(1, formula_headline="   "), imp.M_FORMULA_AUSENTE),
    (linha_ref(1, formula_headline="a" * 1001), imp.M_FORMULA_INVALIDA),
    (linha_ref(1, blocos=[]), imp.M_BLOCOS_AUSENTES),
    (linha_ref(1, blocos=[bloco_ref(i) for i in range(1, 62)]), imp.M_BLOCOS_AUSENTES),
    (linha_ref(1, blocos=[bloco_ref(1), bloco_ref(3)]), imp.M_ORDEM),
    (linha_ref(1, blocos=[bloco_ref(2), bloco_ref(2)]), imp.M_ORDEM),
    (linha_ref(1, blocos=[bloco_ref(1, tipo="Tipo Que Não Existe")]), imp.M_TIPO),
    (linha_ref(1, blocos=[bloco_ref(1) | {"repeticoes": 21}]), imp.M_BLOCO),
    (linha_ref(1, blocos=[bloco_ref(1) | {"nome_original": ""}]), imp.M_BLOCO),
    (linha_ref(1, blocos=[bloco_ref(1) | {"tempo": "x" * 41}]), imp.M_BLOCO),
    (linha_ref(1, blocos=[bloco_ref(1, nota="n" * 601)]), imp.M_BLOCO),
    (linha_ref(1, formato="podcast"), imp.M_FORMATO),
    (linha_ref(1, objetivos=[]), imp.M_OBJETIVOS),
    (linha_ref(1, objetivos=["alcance", "alcance"]), imp.M_OBJETIVOS),
    (linha_ref(1, objetivos=["fama"]), imp.M_OBJETIVOS),
    ("não é um objeto", imp.M_LINHA),
])
def test_each_invalid_reference_row_is_ignored_with_its_code(row, esperado):
    assert motivo(row) == esperado


@pytest.mark.parametrize("row,esperado", [
    # (a) a nested [placeholder] inside a (nota) cut the note at the first ]: the name is left with a stray )
    (linha_ref(1, blocos=[bloco_ref(1, nome="Intensificador do Mistério vive e quase ninguém entende)")]), imp.M_BLOCO),
    (linha_ref(1, blocos=[bloco_ref(1, nome="Abertura (nota aberta")]), imp.M_BLOCO),
    (linha_ref(1, blocos=[bloco_ref(1, nome="Abertura [x)")]), imp.M_BLOCO),
    (linha_ref(1, blocos=[bloco_ref(1, nota="nota com [placeholder cortado")]), imp.M_BLOCO),
    (linha_ref(1, blocos=[bloco_ref(1, nota="fecha demais]")]), imp.M_BLOCO),
    (linha_ref(1, formula_headline="Como [x faz y"), imp.M_FORMULA_INVALIDA),
    (linha_ref(1, formula_headline="Como x) faz y"), imp.M_FORMULA_INVALIDA),
    # (b) `Headline (nota)` glued at the end of a formula
    (linha_ref(1, formula_headline="Como [x] faz y Headline"), imp.M_FORMULA_INVALIDA),
    (linha_ref(1, formula_headline="Como [x] faz y Headline (a nota do vídeo)"), imp.M_FORMULA_INVALIDA),
    (linha_ref(1, formula_headline="Headline"), imp.M_FORMULA_INVALIDA),
    # (c) an annotation-only segment produced a nameless block
    (linha_ref(1, blocos=[bloco_ref(1, nome="   ")]), imp.M_BLOCO),
])
def test_the_extraction_defect_class_can_never_load_silently(row, esperado):
    assert motivo(row) == esperado


@pytest.mark.parametrize("formula,nome,nota", [
    ("Como [x] faz [y] em (z)", "Abertura", "nota (com [placeholder] aninhado) ok"),
    ("A palavra Headline no meio de [tema] e mais texto", "Headline", ""),
    ("Fórmula terminando em headline minúsculo", "Abertura [a] (b)", ""),
])
def test_balanced_brackets_and_a_headline_word_inside_a_formula_are_valid(formula, nome, nota):
    assert motivo(linha_ref(1, formula_headline=formula, blocos=[bloco_ref(1, nome=nome, nota=nota)])) is None


def test_the_bracket_balance_and_marker_helpers():
    assert imp.balanceado("a (b [c] d) e") and imp.balanceado("") and not imp.balanceado("a ]") and not imp.balanceado("([)]") and not imp.balanceado("(")
    assert imp.marcador_headline("x Headline") and imp.marcador_headline("x Headline (n)") and not imp.marcador_headline("x Headlines") and not imp.marcador_headline("Headline x")


def test_a_valid_reference_row_maps_every_field_with_the_stated_provenance():
    row = linha_ref(1, perfil="@Criador.Um", formula_herdada_de="77") | {"blocos": [bloco_ref(2, tipo="Revelação", nota="uma nota"), bloco_ref(1, tipo="Outro")]}
    (l,) = imp.parse_documento("referencia", [row], TIPOS_CATALOGO).linhas
    assert (l.fonte_externa, l.ref_externa, l.handle) == ("corestudio", "1001", "criador.um")
    assert l.formula_origem == "referencia" and l.formula_herdada_de == "77"          # inherited formula => referencia
    assert (l.formato, l.formato_origem, l.objetivos_origem, l.rotulo) == ("reels", "referencia", "referencia", "referencia-sintetica")
    assert [b.tipo_nome for b in l.blocos] == ["Outro", "Revelação"]                 # sorted by ordem
    assert l.blocos[1].nota == "uma nota" and l.blocos[0].nota is None                # "" -> None
    b0 = l.blocos[0]
    assert (b0.nome_origem, b0.tipo_origem, b0.tempo_origem, b0.instrucao_origem) == ("fonte", "referencia", "referencia", "referencia")


def test_a_non_inherited_reference_formula_is_fonte():
    (l,) = imp.parse_documento("referencia", [linha_ref(1)], TIPOS_CATALOGO).linhas
    assert l.formula_origem == "fonte" and l.formula_herdada_de is None


def test_a_duplicate_id_inside_the_file_is_ignored_not_double_counted():
    p = imp.parse_documento("referencia", [linha_ref(1), linha_ref(1, perfil="outro.perfil")], TIPOS_CATALOGO)
    assert len(p.linhas) == 1 and p.ignoradas == ((1, imp.M_ID_DUP),)


@pytest.mark.parametrize("fonte,conteudo", [
    ("referencia", {"a": 1}), ("referencia", "x"), ("maquina_de_roteiros", corpus_maquina(2)), ("maquina_de_edicao", []),
    ("nao_existe", []),
])
def test_a_bad_top_level_shape_is_arquivo_invalido(fonte, conteudo):
    with pytest.raises(imp.ArquivoInvalido):
        imp.parse_documento(fonte, conteudo, TIPOS_CATALOGO)


def test_any_other_source_is_fonte_nao_suportada_and_the_reference_is_the_only_one():
    assert imp.FONTES == ("referencia",)
    for fonte in ("maquina_de_roteiros", "maquina_de_edicao", "x"):
        with pytest.raises(imp.ArquivoInvalido) as exc:
            imp.parse_documento(fonte, corpus_maquina(1), TIPOS_CATALOGO)
        assert exc.value.motivo == "fonte_nao_suportada"


def test_the_catalog_must_carry_the_system_type():
    with pytest.raises(imp.ArquivoInvalido):
        imp.parse_documento("referencia", [linha_ref(1)], ("Headline",))


def test_handle_normalisation():
    assert imp.normalizar_handle(" @Foo.Bar_1 ") == "foo.bar_1"
    assert imp.normalizar_handle("a b") is None and imp.normalizar_handle("") is None and imp.normalizar_handle(None) is None


def test_the_file_identity_is_independent_of_key_order_and_whitespace():
    assert imp.sha256_documento({"b": 1, "a": [1, 2]}) == imp.sha256_documento({"a": [1, 2], "b": 1})
    assert imp.sha256_documento([{"a": 1}]) != imp.sha256_documento([{"a": 2}])
    # golden vector: the MCP tool computes the same value (test_sw_estruturas_import.py pins the same literal)
    assert imp.sha256_documento({"é": [1, "x"]}) == "2a90a5462aab643e0a02f1e8d16cd4aa562a95741f31c6111be2f4bd591793dc"


# ── accounting + idempotency ─────────────────────────────────────────────────────────────────────────────


def test_every_row_is_accounted_for_across_created_updated_unchanged_ignored():
    corpus = corpus_ref(20)
    corpus[0]["perfil"] = "inválido!"          # ignored
    corpus[1]["blocos"] = []                   # ignored
    c = run(FakeStore(), "referencia", corpus)
    assert c.linhas_total == 20 and c.estruturas_ignoradas == 2 and c.estruturas_criadas == 18
    assert c.fechado() and c.ignoradas_motivos == {imp.M_BLOCOS_AUSENTES: 1, imp.M_HANDLE: 1}
    assert c.blocos_criados == 18 * 3


def test_the_same_file_twice_is_all_unchanged_and_writes_no_estrutura_the_second_time():
    store = FakeStore()
    run(store, "referencia", corpus_ref(20))
    antes = len(store.calls)
    c = run(store, "referencia", corpus_ref(20))
    assert (c.estruturas_criadas, c.estruturas_atualizadas, c.estruturas_inalteradas, c.estruturas_ignoradas) == (0, 0, 20, 0)
    assert [n for n, _ in store.calls[antes:] if n.startswith("cs_estrutura")] == []  # no estrutura write at all


def test_profiles_are_merged_by_normalised_handle_and_new_ones_are_library_only_with_criado_then_importado():
    store = FakeStore()
    c = run(store, "referencia", [linha_ref(1, perfil="@Criador.Um"), linha_ref(2, perfil="criador.um"), linha_ref(3, perfil="outro.perfil")])
    assert (c.perfis_criados, c.perfis_mesclados, c.estruturas_criadas) == (2, 0, 3)
    assert set(store.perfis_) == {"criador.um", "outro.perfil"}
    assert ("criador.um", "criado") in store.eventos_perfil and ("criador.um", "importado") in store.eventos_perfil
    c2 = run(store, "referencia", [linha_ref(4, perfil="criador.um")])
    assert (c2.perfis_criados, c2.perfis_mesclados) == (0, 1)


def test_an_existing_profile_is_left_untouched():
    store = FakeStore()
    store.perfis_["criador.sintetico0"] = "pf-existente"
    run(store, "referencia", [linha_ref(4, perfil="criador.sintetico0")])
    assert ("criador.sintetico0", "criado") not in store.eventos_perfil and ("criador.sintetico0", "importado") in store.eventos_perfil
    assert "criador.sintetico0" not in store.perfil_nomes


def test_an_opted_out_handle_is_skipped_for_both_files_and_creates_no_profile():
    store = FakeStore(optouts={"criador.sintetico0"})
    c = run(store, "referencia", [linha_ref(1, perfil="criador.sintetico0"), linha_ref(2, perfil="criador.livre")])
    assert c.ignoradas_motivos == {imp.M_OPTOUT: 1} and c.estruturas_criadas == 1 and "criador.sintetico0" not in store.perfis_


def test_the_profile_ceiling_ignores_rows_of_new_profiles_beyond_it():
    store = FakeStore()
    c = run(store, "referencia", [linha_ref(i, perfil=f"perfil.n{i}") for i in range(1, 6)], limite=3)
    assert c.perfis_criados == 3 and c.ignoradas_motivos == {imp.M_LIMITE: 2} and c.fechado()


def test_a_dry_run_reads_and_writes_nothing_but_reports_the_same_numbers_as_the_apply():
    store = FakeStore()
    corpus = corpus_ref(12)
    plano = run(store, "referencia", corpus, aplicar=False)
    assert store.calls == [] and store.estruturas == {} and store.perfis_ == {}
    real = run(store, "referencia", corpus, aplicar=True)
    assert plano.como_dict() == real.como_dict()
    # and after the apply the plan of the same file is all unchanged (what the dry-run would have said)
    assert run(store, "referencia", corpus, aplicar=False).estruturas_inalteradas == 12


# ── the update path: only fonte/referencia fields move; admin never overwritten ──────────────────────────


def _alterado(corpus, n=0):
    corpus = copia(corpus)
    corpus[n]["formula_headline"] = f"{SENTINELA} NOVA fórmula"
    corpus[n]["objetivos"] = ["autoridade"]
    corpus[n]["blocos"][0]["nome_original"] = f"{SENTINELA} NOVO nome"
    corpus[n]["blocos"][0]["instrucao"] = f"{SENTINELA} NOVA instrução"
    corpus[n]["blocos"].append(bloco_ref(4, tipo="Headline"))
    return corpus


def test_a_changed_row_is_updated_blocks_first_and_the_hash_stamp_last():
    store = FakeStore()
    corpus = corpus_ref(3)
    run(store, "referencia", corpus)
    c = run(store, "referencia", _alterado(corpus))
    assert (c.estruturas_atualizadas, c.estruturas_inalteradas, c.blocos_criados) == (1, 2, 1)
    nomes = [n for n, _ in store.calls if n in ("cs_estrutura_substituir_blocos", "cs_estrutura_atualizar")]
    assert nomes == ["cs_estrutura_substituir_blocos", "cs_estrutura_atualizar"]
    sub = next(p for n, p in store.calls if n == "cs_estrutura_substituir_blocos")
    assert sub["p_blocos"]["evento"] == "atualizada_import" and sub["p_blocos"]["ator_tipo"] == "sistema_import"
    assert sub["p_blocos"]["importacao_id"] == "imp-1"
    row = next(e for e in store.estruturas.values() if e["ref_externa"] == "1001")
    assert row["formula_headline"].endswith("NOVA fórmula")
    assert row["fonte_hash"] == imp.parse_documento("referencia", _alterado(corpus), TIPOS_CATALOGO).linhas[0].hash
    assert run(store, "referencia", _alterado(corpus)).estruturas_inalteradas == 3  # and it is stable afterwards


def test_admin_origin_fields_are_never_overwritten_by_a_changed_file():
    store = FakeStore()
    corpus = corpus_ref(3)
    run(store, "referencia", corpus)
    row = next(e for e in store.estruturas.values() if e["ref_externa"] == "1001")
    row.update(formula_origem="admin", formula_headline="EDITADA PELO ADMIN", objetivos_origem="admin", objetivos=["venda"])
    bloco = store.blocos[row["id"]][0]
    bloco.update(nome_origem="admin", nome="NOME DO ADMIN", instrucao_origem="admin", instrucao="INSTRUÇÃO DO ADMIN", nota="NOTA DO ADMIN", repeticoes=3)
    c = run(store, "referencia", _alterado(corpus))
    assert c.estruturas_atualizadas == 1
    assert row["formula_headline"] == "EDITADA PELO ADMIN" and row["objetivos"] == ["venda"]
    novo = store.blocos[row["id"]][0]
    assert (novo["nome"], novo["instrucao"], novo["nota"], novo["repeticoes"]) == ("NOME DO ADMIN", "INSTRUÇÃO DO ADMIN", "NOTA DO ADMIN", 3)
    assert (novo["nome_origem"], novo["instrucao_origem"]) == ("admin", "admin")
    patch = next(p["p_patch"] for n, p in store.calls if n == "cs_estrutura_atualizar")
    assert "formula_headline" not in patch and "objetivos" not in patch and "fonte_hash" in patch  # hash still stamped
    assert run(store, "referencia", _alterado(corpus)).estruturas_inalteradas == 3


def test_an_admin_added_extra_block_survives_a_shorter_file():
    store = FakeStore()
    corpus = corpus_ref(2)
    run(store, "referencia", corpus)
    row = next(e for e in store.estruturas.values() if e["ref_externa"] == "1001")
    store.blocos[row["id"]].append({
        "id": "b-admin", "ordem": 4, "tipo_id": store._tipos["Outro"], "nome": "extra do admin", "tempo": None, "instrucao": None, "nota": None,
        "repeticoes": 1, "nome_origem": "admin", "tipo_origem": "admin", "tempo_origem": "admin", "instrucao_origem": "admin",
    })
    shorter = copia(corpus)
    shorter[0]["blocos"] = shorter[0]["blocos"][:2]
    run(store, "referencia", shorter)
    ids = [b["id"] for b in store.blocos[row["id"]]]
    assert "b-admin" in ids and len(ids) == 3  # 2 from the file + the admin's


def test_a_non_admin_extra_block_is_removed_by_a_shorter_file():
    store = FakeStore()
    corpus = corpus_ref(2)
    run(store, "referencia", corpus)
    shorter = copia(corpus)
    shorter[0]["blocos"] = shorter[0]["blocos"][:2]
    run(store, "referencia", shorter)
    row = next(e for e in store.estruturas.values() if e["ref_externa"] == "1001")
    assert len(store.blocos[row["id"]]) == 2


def test_an_archived_estrutura_is_not_updated_it_is_an_ignore():
    store = FakeStore()
    corpus = corpus_ref(2)
    run(store, "referencia", corpus)
    next(e for e in store.estruturas.values() if e["ref_externa"] == "1001")["status"] = "arquivada"
    c = run(store, "referencia", _alterado(corpus))
    assert c.ignoradas_motivos == {imp.M_INATIVA: 1} and c.fechado()


# ── RPC refusals ─────────────────────────────────────────────────────────────────────────────────────────


def test_a_coded_rpc_refusal_is_a_row_ignore_not_a_failed_run():
    store = FakeStore()
    store.fail_with["cs_estrutura_criar"] = FakeApiError("tipo_nao_encontrado")
    c = run(store, "referencia", corpus_ref(3))
    assert c.ignoradas_motivos == {imp.M_GRAVACAO: 3} and c.estruturas_criadas == 0 and c.fechado()


def test_a_stale_version_on_update_is_a_conflict_ignore():
    store = FakeStore()
    corpus = corpus_ref(2)
    run(store, "referencia", corpus)
    store.fail_with["cs_estrutura_atualizar"] = FakeApiError("versao_desatualizada")
    c = run(store, "referencia", _alterado(corpus))
    assert c.ignoradas_motivos == {imp.M_CONFLITO: 1}


def test_an_unexpected_failure_propagates_so_the_job_retries():
    store = FakeStore()
    store.fail_with["cs_estrutura_criar"] = ConnectionError("boom")
    with pytest.raises(ConnectionError):
        run(store, "referencia", corpus_ref(2))


# ── privacy: nothing from a row leaves the module ────────────────────────────────────────────────────────


def test_no_row_text_in_logs_or_the_report(caplog):
    store = FakeStore()
    store.fail_with["cs_estrutura_criar"] = FakeApiError("tipo_nao_encontrado")
    with caplog.at_level("DEBUG"):
        c = run(store, "referencia", corpus_ref(3))
    assert SENTINELA not in caplog.text and SENTINELA not in str(c.como_dict())


# ── no model call: the module imports no LLM client ──────────────────────────────────────────────────────


def test_the_loader_imports_no_llm_client_no_prompt_and_no_saida_ia():
    tree = ast.parse(SERVICE.read_text(encoding="utf-8"))
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules.append(("." * node.level) + (node.module or ""))
            modules += [(node.module or "") + "." + a.name for a in node.names]
    assert modules, "the AST walk found no imports"
    joined = " ".join(modules).lower()
    for banned in ("llm", "openai", "anthropic", "saida_ia", "prompts", "chat_completion", "gemini", "budget"):
        assert banned not in joined, banned


def test_the_mapper_never_stamps_ai_provenance():
    for fonte, doc in (("referencia", corpus_ref(5)),):
        for l in imp.parse_documento(fonte, doc, TIPOS_CATALOGO).linhas:
            origens = {l.formula_origem, l.formato_origem, l.objetivos_origem} | {
                o for b in l.blocos for o in (b.nome_origem, b.tipo_origem, b.tempo_origem, b.instrucao_origem)
            }
            assert origens <= {"fonte", "referencia"}
