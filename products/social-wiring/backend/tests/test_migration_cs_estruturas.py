"""Migration ``cs_estruturas`` (M1 of estruturas-contract.md section 3.1) on a REAL Postgres (PGlite).

The prelude creates only the 229/marcas tables the migration references (id columns and the few columns the
scenarios touch); the REAL migration file is applied TWICE (idempotency) and every RPC / guard / grant is exercised
against the result. Same harness as ``test_migration_338_roteiro_ciclo.py``: a Python test over a mock cannot show a
transaction, a deferred unique, an FK action running inside a guard trigger or a privilege, PGlite can.

Referenced by name (``migration_path``), never by its NNN_ number: integrate renumbers.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from noctusai_lib.testing.migrations import migration_path

from app.modules.media_creation import estruturas_formatos as fmt
from app.modules.media_creation import estruturas_tipos_bloco as catalogo

ROOT = Path(__file__).resolve().parents[4]
NODE_DIR = ROOT / "mcp" / "noctusai" / "node"
HARNESS = NODE_DIR / "migration_replay" / "replay.mjs"
STUBS = NODE_DIR / "migration_replay" / "stubs.sql"
MIGRATION = migration_path(Path(__file__).resolve().parents[1], "cs_estruturas")

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not HARNESS.exists() or not (NODE_DIR / "node_modules" / "@electric-sql").exists(),
    reason="PGlite replay harness unavailable (needs `node` and mcp/noctusai/node/node_modules)",
)

PRELUDE = """
CREATE SCHEMA IF NOT EXISTS social_wiring;
CREATE TABLE IF NOT EXISTS public.organizations (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), nome text, slug text);
SET search_path = social_wiring, public;
CREATE TABLE marcas (id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE, name text);
CREATE TABLE cs_perfis_monitorados (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), handle text NOT NULL);
CREATE TABLE cs_virais (id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  perfil_id uuid NOT NULL REFERENCES cs_perfis_monitorados (id) ON DELETE CASCADE);
CREATE TABLE cs_headlines (id uuid PRIMARY KEY DEFAULT gen_random_uuid());
CREATE TABLE cs_roteiros (id uuid PRIMARY KEY DEFAULT gen_random_uuid());
"""

#: Every scenario starts from: an org + marca, a perfil, two catalog types, an actor.
_BASE = """
SET search_path = social_wiring, public;
DO $$
DECLARE
  o uuid := gen_random_uuid(); m uuid; pf uuid; vi uuid; v_th uuid; v_tr uuid; v_to uuid;
  u uuid := '00000000-0000-0000-0000-0000000000a1'; r jsonb; e uuid; e2 uuid; n int; s text; caught boolean := false;
  b1 uuid; b2 uuid; b3 uuid; he uuid; ro uuid;
BEGIN
  INSERT INTO public.organizations (id, nome, slug) VALUES (o, 'o', 'o-' || o::text);
  INSERT INTO marcas (org_id, name) VALUES (o, 'm') RETURNING id INTO m;
  INSERT INTO cs_perfis_monitorados (handle) VALUES ('perfil.' || gen_random_uuid()::text) RETURNING id INTO pf;
  INSERT INTO cs_virais (perfil_id) VALUES (pf) RETURNING id INTO vi;
  SELECT id INTO v_th FROM cs_estrutura_tipos_bloco WHERE nome = 'Headline';
  SELECT id INTO v_tr FROM cs_estrutura_tipos_bloco WHERE nome = 'Revelação';
  SELECT id INTO v_to FROM cs_estrutura_tipos_bloco WHERE nome = 'Outro';
  {body}
END $$;
"""


def refuses(call: str, code: str) -> str:
    """A SQL fragment: ``call`` must raise EXACTLY the coded exception ``code`` (anything else, or no refusal, fails)."""
    return (
        f"BEGIN {call}; RAISE EXCEPTION 'no refusal (expected {code})'; "
        f"EXCEPTION WHEN OTHERS THEN IF SQLERRM <> '{code}' THEN RAISE; END IF; END;"
    )


def sqlstate(call: str, state: str) -> str:
    """``call`` must fail with SQLSTATE ``state`` (name form, e.g. check_violation)."""
    return (
        f"BEGIN {call}; RAISE EXCEPTION 'no refusal (expected {state})'; "
        f"EXCEPTION WHEN {state} THEN NULL; END;"
    )


def expect(sql_scalar: str, want: str, what: str) -> str:
    return (
        f"IF (SELECT {sql_scalar})::text IS DISTINCT FROM '{want}' THEN "
        f"RAISE EXCEPTION '{what}: got %', (SELECT {sql_scalar})::text; END IF;"
    )


def ev(where: str) -> str:
    return f"(SELECT count(*) FROM cs_estrutura_eventos WHERE estrutura_id = e AND {where})"


def n_ev(where: str, want: int, what: str) -> str:
    return f"IF {ev(where)} <> {want} THEN RAISE EXCEPTION '{what}: got %', {ev(where)}; END IF;"


def blocos(*itens: str) -> str:
    """A jsonb literal of blocks; each item is ``"<nome>|<tipo var>"`` (+ optional extra json keys after a ``|``)."""
    parts = []
    for it in itens:
        nome, tipo, *extra = it.split("|")
        more = (", " + extra[0]) if extra else ""
        parts.append(f"jsonb_build_object('nome', '{nome}', 'tipo_id', {tipo}{more})")
    return "jsonb_build_array(" + ", ".join(parts) + ")"


def criar(blocos_sql: str, extra: str = "", *, status: str = "ativa", formato: str = "reels", ator: bool = True) -> str:
    ator_sql = "'ator_id', u, " if ator else ""
    return (
        "cs_estrutura_criar(jsonb_build_object('perfil_id', pf, 'formula_headline', 'Como [x] faz y', "
        f"'formato', '{formato}', 'objetivos', jsonb_build_array('alcance'), 'status', '{status}', {ator_sql}"
        f"'blocos', {blocos_sql}{extra}))"
    )


SCENARIOS: dict[str, str] = {
    # ── catalog ──────────────────────────────────────────────────────────────────
    "seed: 22 types (21 + Outro), ordem 1..22, Outro is the only sistema, every row has a criado event": """
  SELECT count(*) INTO n FROM cs_estrutura_tipos_bloco;
  IF n <> 22 THEN RAISE EXCEPTION 'count %', n; END IF;
  IF (SELECT array_agg(ordem ORDER BY ordem) FROM cs_estrutura_tipos_bloco) <> (SELECT array_agg(g) FROM generate_series(1, 22) g) THEN
    RAISE EXCEPTION 'ordem'; END IF;
  IF (SELECT array_agg(nome) FROM cs_estrutura_tipos_bloco WHERE sistema) <> ARRAY['Outro'] THEN RAISE EXCEPTION 'sistema'; END IF;
  IF (SELECT count(*) FROM cs_estrutura_tipo_eventos WHERE tipo = 'criado') <> 22 THEN RAISE EXCEPTION 'eventos'; END IF;""",
    "tipo_salvar creates at the end by default, at `ordem` shifting the others, and writes a criado event": """
  r := cs_estrutura_tipo_salvar(jsonb_build_object('nome', 'Novo', 'instrucao_referencia', 'faça x', 'ator_id', u));
  IF (SELECT ordem FROM cs_estrutura_tipos_bloco WHERE id = (r->>'id')::uuid) <> 23 THEN RAISE EXCEPTION 'last'; END IF;
  r := cs_estrutura_tipo_salvar(jsonb_build_object('nome', 'Novo2', 'instrucao_referencia', 'faça y', 'ordem', 1, 'ator_id', u));
  IF (SELECT ordem FROM cs_estrutura_tipos_bloco WHERE id = (r->>'id')::uuid) <> 1 THEN RAISE EXCEPTION 'first'; END IF;
  IF (SELECT ordem FROM cs_estrutura_tipos_bloco WHERE nome = 'Headline') <> 2 THEN RAISE EXCEPTION 'shifted'; END IF;
  IF (SELECT count(*) FROM cs_estrutura_tipo_eventos WHERE tipo = 'criado' AND ator_id = u) <> 2 THEN RAISE EXCEPTION 'events'; END IF;""",
    "tipo_salvar edit: one event per changed field, activate/deactivate are their own events, no change = no bump": """
  r := cs_estrutura_tipo_salvar(jsonb_build_object('id', v_th, 'expected_versao', 1, 'instrucao_referencia', 'nova instrução', 'ativo', false, 'ator_id', u));
  IF (r->>'versao')::int <> 2 OR NOT (r->>'alterada')::boolean THEN RAISE EXCEPTION 'bump %', r; END IF;
  IF (SELECT count(*) FROM cs_estrutura_tipo_eventos WHERE tipo_id = v_th AND tipo = 'editado' AND campo = 'instrucao_referencia') <> 1 THEN RAISE EXCEPTION 'editado'; END IF;
  IF (SELECT count(*) FROM cs_estrutura_tipo_eventos WHERE tipo_id = v_th AND tipo = 'desativado') <> 1 THEN RAISE EXCEPTION 'desativado'; END IF;
  r := cs_estrutura_tipo_salvar(jsonb_build_object('id', v_th, 'expected_versao', 2, 'instrucao_referencia', 'nova instrução', 'ativo', false));
  IF (r->>'versao')::int <> 2 OR (r->>'alterada')::boolean THEN RAISE EXCEPTION 'noop bumped %', r; END IF;
  r := cs_estrutura_tipo_salvar(jsonb_build_object('id', v_th, 'ativo', true));
  IF (SELECT count(*) FROM cs_estrutura_tipo_eventos WHERE tipo_id = v_th AND tipo = 'ativado') <> 1 THEN RAISE EXCEPTION 'ativado'; END IF;"""
    + refuses("PERFORM cs_estrutura_tipo_salvar(jsonb_build_object('id', v_th, 'expected_versao', 1, 'ativo', false))", "versao_desatualizada"),
    "tipo: a duplicate nome is a unique violation (the API answers 422)": sqlstate(
        "PERFORM cs_estrutura_tipo_salvar(jsonb_build_object('nome', 'Headline', 'instrucao_referencia', 'x'))", "unique_violation"),
    "Outro is protected in the RPC and in the table: no rename/deactivate/unflag/delete by any path": (
        refuses("PERFORM cs_estrutura_tipo_salvar(jsonb_build_object('id', v_to, 'instrucao_referencia', 'outra'))", "tipo_protegido")
        + refuses("PERFORM cs_estrutura_tipo_excluir(v_to, u)", "tipo_protegido")
        + """
  BEGIN UPDATE cs_estrutura_tipos_bloco SET nome = 'Outros' WHERE id = v_to; RAISE EXCEPTION 'renamed';
  EXCEPTION WHEN raise_exception THEN IF SQLERRM NOT LIKE 'cs_estrutura_tipos_bloco_protegido%' THEN RAISE; END IF; END;
  BEGIN UPDATE cs_estrutura_tipos_bloco SET ativo = false WHERE id = v_to; RAISE EXCEPTION 'deactivated';
  EXCEPTION WHEN raise_exception THEN IF SQLERRM NOT LIKE 'cs_estrutura_tipos_bloco_protegido%' THEN RAISE; END IF; END;
  BEGIN UPDATE cs_estrutura_tipos_bloco SET sistema = false WHERE id = v_to; RAISE EXCEPTION 'unflagged';
  EXCEPTION WHEN raise_exception THEN IF SQLERRM NOT LIKE 'cs_estrutura_tipos_bloco_protegido%' THEN RAISE; END IF; END;
  BEGIN DELETE FROM cs_estrutura_tipos_bloco WHERE id = v_to; RAISE EXCEPTION 'deleted';
  EXCEPTION WHEN raise_exception THEN IF SQLERRM NOT LIKE 'cs_estrutura_tipos_bloco_protegido%' THEN RAISE; END IF; END;"""),
    "tipo_excluir: refused while a block uses it (tipo_em_uso), else deleted with an excluido event": (
        "r := " + criar(blocos("a|v_th")) + ";"
        + refuses("PERFORM cs_estrutura_tipo_excluir(v_th, u)", "tipo_em_uso")
        + """
  r := cs_estrutura_tipo_salvar(jsonb_build_object('nome', 'Livre', 'instrucao_referencia', 'x', 'ator_id', u));
  PERFORM cs_estrutura_tipo_excluir((r->>'id')::uuid, u);
  IF (SELECT count(*) FROM cs_estrutura_tipos_bloco WHERE nome = 'Livre') <> 0 THEN RAISE EXCEPTION 'not deleted'; END IF;
  IF (SELECT count(*) FROM cs_estrutura_tipo_eventos WHERE tipo = 'excluido' AND ator_id = u) <> 1 THEN RAISE EXCEPTION 'event'; END IF;"""),
    # ── criar ────────────────────────────────────────────────────────────────────
    "criar (admin): returns id/codigo/versao 1; ativa + publicada_em; all provenance admin; blocks ordered; ONE criada event": (
        "r := " + criar(blocos("Abertura|v_th", "Virada|v_tr|'tempo', '3–7s', 'nota', 'obs', 'repeticoes', 2")) + """;
  e := (r->>'id')::uuid;
  IF (r->>'versao')::int <> 1 OR (r->>'codigo')::bigint < 1 THEN RAISE EXCEPTION 'ret %', r; END IF;"""
        + expect("(status, publicada_em IS NOT NULL, formula_origem, formato_origem, objetivos_origem, created_by = u)::text FROM cs_estruturas WHERE id = e",
                 "(ativa,t,admin,admin,admin,t)", "row")
        + expect("string_agg(ordem || ':' || nome || ':' || coalesce(tempo, '-') || ':' || repeticoes, ',' ORDER BY ordem) FROM cs_estrutura_blocos WHERE estrutura_id = e",
                 "1:Abertura:-:1,2:Virada:3–7s:2", "blocks")
        + n_ev("true", 1, "exactly one event")
        + n_ev("tipo = 'criada' AND ator_tipo = 'admin' AND ator_id = u AND versao = 1 AND importacao_id IS NULL", 1, "criada")),
    "criar: ativa needs formato, an objetivo and a block (estrutura_incompleta + the missing list); a rascunho may be empty": (
        refuses("PERFORM cs_estrutura_criar(jsonb_build_object('perfil_id', pf, 'formula_headline', 'x', 'status', 'ativa', 'blocos', jsonb_build_array()))", "estrutura_incompleta")
        + """
  BEGIN
    PERFORM cs_estrutura_criar(jsonb_build_object('perfil_id', pf, 'formula_headline', 'x', 'status', 'ativa', 'blocos', jsonb_build_array()));
  EXCEPTION WHEN raise_exception THEN
    GET STACKED DIAGNOSTICS s = PG_EXCEPTION_DETAIL;
    IF s <> 'formato,objetivos,blocos' THEN RAISE EXCEPTION 'detail %', s; END IF;
  END;
  r := cs_estrutura_criar(jsonb_build_object('perfil_id', pf, 'formula_headline', 'x', 'status', 'rascunho', 'blocos', jsonb_build_array()));
  IF (SELECT status FROM cs_estruturas WHERE id = (r->>'id')::uuid) <> 'rascunho' THEN RAISE EXCEPTION 'rascunho'; END IF;"""),
    "criar is all-or-nothing: an unknown tipo / perfil / viral leaves no Estrutura, block or event behind": (
        refuses("PERFORM " + criar(blocos("a|gen_random_uuid()")), "tipo_nao_encontrado")
        + refuses("PERFORM cs_estrutura_criar(jsonb_build_object('perfil_id', gen_random_uuid(), 'formula_headline', 'x', 'status', 'rascunho'))", "perfil_nao_encontrado")
        + refuses("PERFORM " + criar(blocos("a|v_th"), ", 'viral_id', gen_random_uuid()"), "viral_nao_encontrado")
        + """
  IF (SELECT count(*) FROM cs_estruturas WHERE perfil_id = pf) <> 0
     OR (SELECT count(*) FROM cs_estrutura_eventos WHERE perfil_id = pf) <> 0
    THEN RAISE EXCEPTION 'partial write survived'; END IF;"""),
    "criar (import): the event is `importada` by sistema_import with the importacao id; created_by is NULL; (fonte_externa, ref_externa) is unique": (
        "r := " + criar(blocos("a|v_th|'tipo_origem', 'referencia', 'nome_origem', 'fonte'"),
                         ", 'origem', 'import_corestudio', 'fonte_externa', 'corestudio', 'ref_externa', '123', 'formato_origem', 'referencia', "
                         "'objetivos_origem', 'referencia', 'formula_origem', 'fonte', 'ator_tipo', 'sistema_import', "
                         "'importacao_id', '00000000-0000-0000-0000-00000000bb01', 'referencia_rotulo', 'ref-2026', 'formula_herdada_de', '99'",
                         ator=False) + """;
  e := (r->>'id')::uuid;"""
        + expect("(origem, created_by IS NULL, referencia_rotulo, formula_herdada_de) FROM cs_estruturas WHERE id = e", "(import_corestudio,t,ref-2026,99)", "row")
        + n_ev("tipo = 'importada' AND ator_tipo = 'sistema_import' AND importacao_id = '00000000-0000-0000-0000-00000000bb01' AND ator_id IS NULL", 1, "importada")
        + n_ev("tipo = 'ia_preenchida'", 0, "no ia event for a reference load")
        + sqlstate("PERFORM " + criar(blocos("a|v_th"), ", 'origem', 'import_corestudio', 'fonte_externa', 'corestudio', 'ref_externa', '123'"), "unique_violation")),
    "criar (auto-draft): events criada_automatica + ia_preenchida by sistema_ia; one auto-draft per video": (
        "r := " + criar(blocos("a|v_th|'nome_origem', 'ia_sugerido'"),
                         ", 'origem', 'viral_auto', 'viral_id', vi, 'formula_origem', 'ia_sugerido', 'status', 'rascunho'", status="rascunho") + """;
  e := (r->>'id')::uuid;"""
        + n_ev("tipo = 'criada_automatica' AND ator_tipo = 'sistema_ia'", 1, "automatica")
        + n_ev("tipo = 'ia_preenchida' AND ator_tipo = 'sistema_ia'", 1, "ia")
        + sqlstate("PERFORM " + criar(blocos("a|v_th"), ", 'origem', 'viral_auto', 'viral_id', vi, 'status', 'rascunho'", status="rascunho"), "unique_violation")),
    # ── atualizar ────────────────────────────────────────────────────────────────
    "atualizar: a stale versao is refused; an edit flips the field to admin, bumps versao, writes campo_editado with the previous origin": (
        "r := " + criar(blocos("a|v_th"), ", 'formula_origem', 'referencia'") + """;
  e := (r->>'id')::uuid;"""
        + refuses("PERFORM cs_estrutura_atualizar(e, 7, jsonb_build_object('formula_headline', 'outra'), u)", "versao_desatualizada")
        + """
  r := cs_estrutura_atualizar(e, 1, jsonb_build_object('formula_headline', 'Outra fórmula [y]'), u);
  IF (r->>'versao')::int <> 2 OR NOT (r->>'alterada')::boolean THEN RAISE EXCEPTION 'ret %', r; END IF;"""
        + expect("(formula_headline, formula_origem, versao, updated_by = u) FROM cs_estruturas WHERE id = e", '("Outra fórmula [y]",admin,2,t)', "row")
        + n_ev("tipo = 'campo_editado' AND campo = 'formula_headline' AND origem_anterior = 'referencia' AND origem_nova = 'admin' AND versao = 2", 1, "edit")),
    "atualizar: an unchanged patch writes no event and does not bump; an untouched field keeps its origin": (
        "r := " + criar(blocos("a|v_th"), ", 'formato_origem', 'referencia'") + """;
  e := (r->>'id')::uuid;
  r := cs_estrutura_atualizar(e, 1, jsonb_build_object('formula_headline', 'Como [x] faz y', 'formato', 'reels'), u);
  IF (r->>'versao')::int <> 1 OR (r->>'alterada')::boolean THEN RAISE EXCEPTION 'bumped %', r; END IF;
  r := cs_estrutura_atualizar(e, 1, jsonb_build_object('objetivos', jsonb_build_array('venda')), u);"""
        + expect("(formato_origem, objetivos_origem, objetivos::text) FROM cs_estruturas WHERE id = e", "(referencia,admin,{venda})", "origins")
        + n_ev("tipo = 'campo_editado'", 1, "one edit event")),
    "atualizar: viral_id is validated and changeable (null clears it); an ativa can never lose its formato / objetivos": (
        "r := " + criar(blocos("a|v_th")) + """;
  e := (r->>'id')::uuid;"""
        + refuses("PERFORM cs_estrutura_atualizar(e, 1, jsonb_build_object('viral_id', gen_random_uuid()), u)", "viral_nao_encontrado")
        + refuses("PERFORM cs_estrutura_atualizar(e, 1, jsonb_build_object('formato', NULL), u)", "estrutura_incompleta")
        + refuses("PERFORM cs_estrutura_atualizar(e, 1, jsonb_build_object('objetivos', jsonb_build_array()), u)", "estrutura_incompleta")
        + refuses("PERFORM cs_estrutura_atualizar(e, 1, jsonb_build_object('formula_headline', '   '), u)", "formula_invalida")
        + """
  PERFORM cs_estrutura_atualizar(e, 1, jsonb_build_object('viral_id', vi), u);
  IF (SELECT viral_id FROM cs_estruturas WHERE id = e) <> vi THEN RAISE EXCEPTION 'not set'; END IF;
  PERFORM cs_estrutura_atualizar(e, 2, jsonb_build_object('viral_id', NULL), u);
  IF (SELECT viral_id FROM cs_estruturas WHERE id = e) IS NOT NULL THEN RAISE EXCEPTION 'not cleared'; END IF;"""),
    "atualizar (import path): _evento atualizada_import by sistema_import; a metadata-only change writes ONE event with no campo": (
        "r := " + criar(blocos("a|v_th"), ", 'formula_origem', 'fonte', 'fonte_hash', 'h1'") + """;
  e := (r->>'id')::uuid;
  PERFORM cs_estrutura_atualizar(e, 1, jsonb_build_object('fonte_hash', 'h2', '_evento', 'atualizada_import', '_ator_tipo', 'sistema_import'), NULL);"""
        + n_ev("tipo = 'atualizada_import' AND campo IS NULL AND ator_tipo = 'sistema_import' AND ator_id IS NULL AND versao = 2", 1, "metadata event")
        + """
  PERFORM cs_estrutura_atualizar(e, 2, jsonb_build_object('formula_headline', 'Nova [x]', 'formula_origem', 'fonte', '_evento', 'atualizada_import', '_ator_tipo', 'sistema_import'), NULL);"""
        + n_ev("tipo = 'atualizada_import' AND campo = 'formula_headline' AND origem_nova = 'fonte'", 1, "field event")
        + expect("(formula_origem, fonte_hash, updated_by IS NULL) FROM cs_estruturas WHERE id = e", "(fonte,h2,t)", "row")),
    "atualizar: an archived Estrutura is estrutura_inativa": (
        "r := " + criar(blocos("a|v_th")) + """;
  e := (r->>'id')::uuid;
  PERFORM cs_estrutura_arquivar(e, u);"""
        + refuses("PERFORM cs_estrutura_atualizar(e, 2, jsonb_build_object('formula_headline', 'x'), u)", "estrutura_inativa")
        + refuses("PERFORM cs_estrutura_substituir_blocos(e, 2, " + blocos("a|v_th") + ", u)", "estrutura_inativa")),
    # ── blocos ───────────────────────────────────────────────────────────────────
    "substituir_blocos: reorder keeps ids (deferred unique), writes blocos_reordenados, ordem stays contiguous": (
        "r := " + criar(blocos("A|v_th", "B|v_tr", "C|v_th")) + """;
  e := (r->>'id')::uuid;
  SELECT id INTO b1 FROM cs_estrutura_blocos WHERE estrutura_id = e AND nome = 'A';
  SELECT id INTO b2 FROM cs_estrutura_blocos WHERE estrutura_id = e AND nome = 'B';
  SELECT id INTO b3 FROM cs_estrutura_blocos WHERE estrutura_id = e AND nome = 'C';
  r := cs_estrutura_substituir_blocos(e, 1, jsonb_build_array(
        jsonb_build_object('id', b3, 'nome', 'C', 'tipo_id', v_th), jsonb_build_object('id', b1, 'nome', 'A', 'tipo_id', v_th),
        jsonb_build_object('id', b2, 'nome', 'B', 'tipo_id', v_tr)), u);
  IF (r->>'versao')::int <> 2 THEN RAISE EXCEPTION 'versao %', r; END IF;"""
        + expect("string_agg(nome, ',' ORDER BY ordem) FROM cs_estrutura_blocos WHERE estrutura_id = e", "C,A,B", "order")
        + expect("count(*) FROM cs_estrutura_blocos WHERE estrutura_id = e AND id IN (b1, b2, b3)", "3", "identity kept")
        + n_ev("tipo = 'blocos_reordenados' AND versao = 2", 1, "reordenados")
        + n_ev("tipo <> 'criada' AND tipo <> 'blocos_reordenados'", 0, "nothing else")),
    "substituir_blocos: add / remove / edit write exactly their events; unchanged fields keep their provenance, a changed one becomes admin": (
        "r := " + criar(blocos("A|v_th|'tempo', '1s', 'tempo_origem', 'referencia', 'instrucao', 'i', 'instrucao_origem', 'referencia'", "B|v_tr")) + """;
  e := (r->>'id')::uuid;
  SELECT id INTO b1 FROM cs_estrutura_blocos WHERE estrutura_id = e AND nome = 'A';
  SELECT id INTO b2 FROM cs_estrutura_blocos WHERE estrutura_id = e AND nome = 'B';
  r := cs_estrutura_substituir_blocos(e, 1, jsonb_build_array(
        jsonb_build_object('id', b1, 'nome', 'A', 'tipo_id', v_th, 'tempo', '2s', 'instrucao', 'i', 'nota', 'obs'),
        jsonb_build_object('nome', 'Novo', 'tipo_id', v_to)), u);"""
        + expect("(tempo, tempo_origem, instrucao_origem, nota) FROM cs_estrutura_blocos WHERE id = b1", "(2s,admin,referencia,obs)", "provenance")
        + n_ev("tipo = 'bloco_removido' AND campo = 'bloco.' || b2::text", 1, "removido")
        + n_ev("tipo = 'bloco_adicionado' AND campo LIKE 'bloco.%'", 1, "adicionado")
        + n_ev("tipo = 'campo_editado' AND campo = 'bloco.' || b1::text || '.tempo' AND origem_anterior = 'referencia' AND origem_nova = 'admin'", 1, "tempo")
        + n_ev("tipo = 'campo_editado' AND campo = 'bloco.' || b1::text || '.nota' AND origem_anterior IS NULL", 1, "nota (no provenance)")
        + n_ev("tipo = 'campo_editado' AND campo LIKE '%.instrucao'", 0, "unchanged instrucao writes nothing")
        + expect("count(*) FROM cs_estrutura_blocos WHERE estrutura_id = e", "2", "count")
        + expect("string_agg(ordem::text, ',' ORDER BY ordem) FROM cs_estrutura_blocos WHERE estrutura_id = e", "1,2", "ordem contiguous")),
    "substituir_blocos: an unchanged list is a no-op (no bump, no event); empty/oversized/unknown/duplicate ids are refused": (
        "r := " + criar(blocos("A|v_th")) + """;
  e := (r->>'id')::uuid;
  SELECT id INTO b1 FROM cs_estrutura_blocos WHERE estrutura_id = e;
  r := cs_estrutura_substituir_blocos(e, 1, jsonb_build_array(jsonb_build_object('id', b1, 'nome', 'A', 'tipo_id', v_th)), u);
  IF (r->>'versao')::int <> 1 OR (r->>'alterada')::boolean THEN RAISE EXCEPTION 'noop bumped %', r; END IF;"""
        + n_ev("tipo <> 'criada'", 0, "no event")
        + refuses("PERFORM cs_estrutura_substituir_blocos(e, 1, jsonb_build_array(), u)", "blocos_invalidos")
        + refuses("PERFORM cs_estrutura_substituir_blocos(e, 1, jsonb_build_array(jsonb_build_object('id', gen_random_uuid(), 'nome', 'x', 'tipo_id', v_th)), u)", "bloco_nao_encontrado")
        + refuses("PERFORM cs_estrutura_substituir_blocos(e, 1, jsonb_build_array(jsonb_build_object('id', b1, 'nome', 'x', 'tipo_id', v_th), jsonb_build_object('id', b1, 'nome', 'y', 'tipo_id', v_th)), u)", "blocos_invalidos")
        + refuses("PERFORM cs_estrutura_substituir_blocos(e, 1, jsonb_build_array(jsonb_build_object('nome', 'x', 'tipo_id', gen_random_uuid())), u)", "tipo_nao_encontrado")
        + refuses("PERFORM cs_estrutura_substituir_blocos(e, 9, " + blocos("a|v_th") + ", u)", "versao_desatualizada")
        + refuses("PERFORM cs_estrutura_substituir_blocos(e, 1, (SELECT jsonb_agg(jsonb_build_object('nome', 'b' || g, 'tipo_id', v_th)) FROM generate_series(1, 61) g), u)", "blocos_invalidos")),
    "substituir_blocos (import path, object form): ator_tipo / evento / importacao_id are honoured": (
        "r := " + criar(blocos("A|v_th")) + """;
  e := (r->>'id')::uuid;
  SELECT id INTO b1 FROM cs_estrutura_blocos WHERE estrutura_id = e;
  PERFORM cs_estrutura_substituir_blocos(e, 1, jsonb_build_object('ator_tipo', 'sistema_import', 'evento', 'atualizada_import',
     'importacao_id', '00000000-0000-0000-0000-00000000bb02',
     'blocos', jsonb_build_array(jsonb_build_object('id', b1, 'nome', 'A', 'tipo_id', v_th, 'tempo', '5s', 'tempo_origem', 'referencia'))), NULL);"""
        + n_ev("tipo = 'atualizada_import' AND ator_tipo = 'sistema_import' AND importacao_id = '00000000-0000-0000-0000-00000000bb02' AND origem_nova = 'referencia'", 1, "import event")
        + expect("(tempo_origem) FROM cs_estrutura_blocos WHERE id = b1", "referencia", "explicit origin")),
    # ── confirmar ────────────────────────────────────────────────────────────────
    "confirmar: referencia/ia_sugerido -> admin without touching content; one campo_confirmado per field; fonte/admin are no-ops": (
        "r := " + criar(blocos("A|v_th|'tipo_origem', 'referencia', 'nome_origem', 'fonte', 'instrucao_origem', 'ia_sugerido', 'instrucao', 'x'"),
                         ", 'formula_origem', 'fonte', 'formato_origem', 'referencia', 'objetivos_origem', 'ia_sugerido'") + """;
  e := (r->>'id')::uuid;
  SELECT id INTO b1 FROM cs_estrutura_blocos WHERE estrutura_id = e;
  r := cs_estrutura_confirmar(e, 1, ARRAY['formato', 'formula_headline', 'bloco.' || b1::text || '.tipo'], u);
  IF (r->>'confirmados')::int <> 2 OR (r->>'versao')::int <> 2 THEN RAISE EXCEPTION 'ret %', r; END IF;"""
        + expect("(formato_origem, formula_origem, objetivos_origem, formato, formula_headline) FROM cs_estruturas WHERE id = e",
                 '(admin,fonte,ia_sugerido,reels,"Como [x] faz y")', "content untouched")
        + expect("tipo_origem FROM cs_estrutura_blocos WHERE id = b1", "admin", "block tipo")
        + n_ev("tipo = 'campo_confirmado' AND campo = 'formato' AND origem_anterior = 'referencia' AND origem_nova = 'admin' AND versao = 2", 1, "formato")
        + n_ev("tipo = 'campo_confirmado'", 2, "two events (the fonte field is not pending)")
        + """
  r := cs_estrutura_confirmar(e, 2, ARRAY['formato'], u);
  IF (r->>'versao')::int <> 2 OR (r->>'confirmados')::int <> 0 THEN RAISE EXCEPTION 'noop bumped %', r; END IF;"""),
    "confirmar '*' confirms every pending field; an unknown field / a foreign bloco / an empty list is campo_desconhecido": (
        "r := " + criar(blocos("A|v_th|'tipo_origem', 'referencia', 'tempo_origem', 'referencia'", "B|v_tr|'instrucao_origem', 'ia_sugerido'"),
                         ", 'formato_origem', 'referencia', 'objetivos_origem', 'referencia'") + """;
  e := (r->>'id')::uuid;
  IF (SELECT campos_pendentes FROM cs_estruturas_resumo WHERE id = e) <> 5 THEN RAISE EXCEPTION 'pendentes %', (SELECT campos_pendentes FROM cs_estruturas_resumo WHERE id = e); END IF;
  r := cs_estrutura_confirmar(e, 1, ARRAY['*'], u);
  IF (r->>'confirmados')::int <> 5 THEN RAISE EXCEPTION 'ret %', r; END IF;
  IF (SELECT campos_pendentes FROM cs_estruturas_resumo WHERE id = e) <> 0 THEN RAISE EXCEPTION 'still pending'; END IF;"""
        + refuses("PERFORM cs_estrutura_confirmar(e, 2, ARRAY['status'], u)", "campo_desconhecido")
        + refuses("PERFORM cs_estrutura_confirmar(e, 2, ARRAY['bloco.' || gen_random_uuid()::text || '.tipo'], u)", "campo_desconhecido")
        + refuses("PERFORM cs_estrutura_confirmar(e, 2, ARRAY[]::text[], u)", "campo_desconhecido")
        + refuses("PERFORM cs_estrutura_confirmar(e, 1, ARRAY['formato'], u)", "versao_desatualizada")),
    # ── publicar / arquivar / restaurar / excluir ────────────────────────────────
    "publicar: refuses an incomplete draft with the missing list; publishes a complete one (ativa, publicada_em, event); only a rascunho": (
        "r := cs_estrutura_criar(jsonb_build_object('perfil_id', pf, 'formula_headline', 'x', 'status', 'rascunho', 'blocos', jsonb_build_array())); e := (r->>'id')::uuid;"
        + refuses("PERFORM cs_estrutura_publicar(e, 1, u)", "rascunho_incompleto")
        + """
  BEGIN PERFORM cs_estrutura_publicar(e, 1, u); EXCEPTION WHEN raise_exception THEN
    GET STACKED DIAGNOSTICS s = PG_EXCEPTION_DETAIL; IF s <> 'formato,objetivos,blocos' THEN RAISE EXCEPTION 'detail %', s; END IF; END;
  PERFORM cs_estrutura_atualizar(e, 1, jsonb_build_object('formato', 'post', 'objetivos', jsonb_build_array('venda')), u);
  PERFORM cs_estrutura_substituir_blocos(e, 2, """ + blocos("a|v_th") + """, u);
  r := cs_estrutura_publicar(e, 3, u);"""
        + expect("(status, publicada_em IS NOT NULL, versao) FROM cs_estruturas WHERE id = e", "(ativa,t,4)", "published")
        + n_ev("tipo = 'publicada' AND ator_id = u AND versao = 4", 1, "publicada")
        + refuses("PERFORM cs_estrutura_publicar(e, 4, u)", "estrutura_inativa")),
    "arquivar / restaurar: a published one returns to ativa, a never-published draft to rascunho; both are idempotent": (
        "r := " + criar(blocos("a|v_th")) + "; e := (r->>'id')::uuid;"
        "r := cs_estrutura_criar(jsonb_build_object('perfil_id', pf, 'formula_headline', 'rasc', 'status', 'rascunho')); e2 := (r->>'id')::uuid;"
        """
  r := cs_estrutura_arquivar(e, u);
  IF NOT (r->>'alterada')::boolean OR (r->>'versao')::int <> 2 THEN RAISE EXCEPTION 'archive %', r; END IF;
  IF (SELECT (status, arquivada_em IS NOT NULL)::text FROM cs_estruturas WHERE id = e) <> '(arquivada,t)' THEN RAISE EXCEPTION 'archived'; END IF;
  r := cs_estrutura_arquivar(e, u);
  IF (r->>'alterada')::boolean OR (r->>'versao')::int <> 2 THEN RAISE EXCEPTION 'archive twice bumped %', r; END IF;
  r := cs_estrutura_restaurar(e, u);
  IF (SELECT (status, arquivada_em IS NULL)::text FROM cs_estruturas WHERE id = e) <> '(ativa,t)' THEN RAISE EXCEPTION 'restored'; END IF;
  r := cs_estrutura_restaurar(e, u);
  IF (r->>'alterada')::boolean THEN RAISE EXCEPTION 'restore twice'; END IF;
  PERFORM cs_estrutura_arquivar(e2, u);
  PERFORM cs_estrutura_restaurar(e2, u);
  IF (SELECT status FROM cs_estruturas WHERE id = e2) <> 'rascunho' THEN RAISE EXCEPTION 'draft restored as ativa (bypasses publish)'; END IF;
  IF (SELECT count(*) FROM cs_estrutura_eventos WHERE estrutura_id = e AND tipo IN ('arquivada', 'restaurada')) <> 2 THEN RAISE EXCEPTION 'events'; END IF;"""),
    "excluir: refused while a use exists (estrutura_em_uso); else deletes row + blocks, and the excluida event (no FK) survives": (
        "r := " + criar(blocos("a|v_th")) + "; e := (r->>'id')::uuid;"
        """
  INSERT INTO cs_headlines DEFAULT VALUES RETURNING id INTO he;
  INSERT INTO cs_estrutura_usos (org_id, marca_id, estrutura_id, contexto, papel, ordem, headline_id) VALUES (o, m, e, 'chat', 'principal', 1, he);"""
        + refuses("PERFORM cs_estrutura_excluir(e, u)", "estrutura_em_uso")
        + """
  IF (SELECT count(*) FROM cs_estruturas WHERE id = e) <> 1 THEN RAISE EXCEPTION 'deleted anyway'; END IF;
  r := cs_estrutura_criar(jsonb_build_object('perfil_id', pf, 'formula_headline', 'x', 'status', 'rascunho', 'blocos', jsonb_build_array(jsonb_build_object('nome', 'z', 'tipo_id', v_th))));
  e2 := (r->>'id')::uuid;
  PERFORM cs_estrutura_excluir(e2, u);
  IF (SELECT count(*) FROM cs_estruturas WHERE id = e2) <> 0 OR (SELECT count(*) FROM cs_estrutura_blocos WHERE estrutura_id = e2) <> 0 THEN RAISE EXCEPTION 'not deleted'; END IF;
  IF (SELECT count(*) FROM cs_estrutura_eventos WHERE estrutura_id = e2 AND tipo = 'excluida' AND ator_id = u) <> 1 THEN RAISE EXCEPTION 'event lost'; END IF;
  IF (SELECT count(*) FROM cs_estrutura_eventos WHERE estrutura_id = e2) <> 2 THEN RAISE EXCEPTION 'history lost'; END IF;"""),
    "atomicity: a failure in the LAST step of an RPC rolls the whole call back (the event table refuses the event)": (
        "r := " + criar(blocos("A|v_th")) + """; e := (r->>'id')::uuid;
  CREATE OR REPLACE FUNCTION social_wiring.zz_boom() RETURNS trigger LANGUAGE plpgsql AS $f$
    BEGIN IF NEW.tipo = 'publicada' THEN RAISE EXCEPTION 'forced'; END IF; RETURN NEW; END $f$;
  CREATE TRIGGER zz_boom BEFORE INSERT ON cs_estrutura_eventos FOR EACH ROW EXECUTE FUNCTION social_wiring.zz_boom();
  PERFORM cs_estrutura_arquivar(e, u);
  UPDATE cs_estruturas SET status = 'rascunho', arquivada_em = NULL WHERE id = e;
  BEGIN
    PERFORM cs_estrutura_publicar(e, 2, u);
    RAISE EXCEPTION 'publicar did not fail';
  EXCEPTION WHEN raise_exception THEN IF SQLERRM <> 'forced' THEN RAISE; END IF; caught := true; END;
  DROP TRIGGER zz_boom ON cs_estrutura_eventos; DROP FUNCTION social_wiring.zz_boom();
  IF NOT caught THEN RAISE EXCEPTION 'no failure'; END IF;
  IF (SELECT (status, versao)::text FROM cs_estruturas WHERE id = e) <> '(rascunho,2)' THEN RAISE EXCEPTION 'status flip survived the failed event'; END IF;"""),
    # ── table guards ─────────────────────────────────────────────────────────────
    "CHECKs: ativa needs formato+objetivos, formato/status/objetivos are closed vocabularies, no duplicate objetivos, trimmed formula": (
        "r := " + criar(blocos("A|v_th")) + "; e := (r->>'id')::uuid;"
        + sqlstate("UPDATE cs_estruturas SET formato = NULL WHERE id = e", "check_violation")
        + sqlstate("UPDATE cs_estruturas SET objetivos = '{}' WHERE id = e", "check_violation")
        + sqlstate("UPDATE cs_estruturas SET formato = 'video' WHERE id = e", "check_violation")
        + sqlstate("UPDATE cs_estruturas SET status = 'publicada' WHERE id = e", "check_violation")
        + sqlstate("UPDATE cs_estruturas SET objetivos = ARRAY['alcance', 'alcance'] WHERE id = e", "check_violation")
        + sqlstate("UPDATE cs_estruturas SET objetivos = ARRAY['fama'] WHERE id = e", "check_violation")
        + sqlstate("UPDATE cs_estruturas SET formula_headline = ' com espaço ' WHERE id = e", "check_violation")
        + sqlstate("UPDATE cs_estruturas SET fonte_externa = 'corestudio' WHERE id = e", "check_violation")
        + sqlstate("UPDATE cs_estruturas SET formula_origem = 'ia' WHERE id = e", "check_violation")
        + """
  UPDATE cs_estruturas SET objetivos = ARRAY['alcance', 'autoridade', 'conexao', 'venda'] WHERE id = e;"""),
    "blocks: tipo FK restricts, nota/tempo are NULL-or-non-empty, repeticoes 1..20, ordem is unique per Estrutura (deferred)": (
        "r := " + criar(blocos("A|v_th", "B|v_tr")) + "; e := (r->>'id')::uuid;"
        + sqlstate("UPDATE cs_estrutura_blocos SET repeticoes = 21 WHERE estrutura_id = e", "check_violation")
        + sqlstate("UPDATE cs_estrutura_blocos SET nota = '' WHERE estrutura_id = e", "check_violation")
        + sqlstate("UPDATE cs_estrutura_blocos SET tempo = repeat('x', 41) WHERE estrutura_id = e", "check_violation")
        + sqlstate("DELETE FROM cs_estrutura_tipos_bloco WHERE id = v_th", "foreign_key_violation")
        + """
  UPDATE cs_estrutura_blocos SET ordem = 2 WHERE estrutura_id = e AND nome = 'A';
  SET CONSTRAINTS ALL IMMEDIATE;
  RAISE EXCEPTION 'unreachable';
EXCEPTION WHEN unique_violation THEN NULL;
  WHEN OTHERS THEN RAISE;"""),
    "events are append-only (UPDATE, DELETE and TRUNCATE refused) for estrutura, tipo and usos": (
        "r := " + criar(blocos("A|v_th")) + "; e := (r->>'id')::uuid;"
        + sqlstate("UPDATE cs_estrutura_eventos SET tipo = 'excluida' WHERE estrutura_id = e", "insufficient_privilege")
        + sqlstate("DELETE FROM cs_estrutura_eventos WHERE estrutura_id = e", "insufficient_privilege")
        + sqlstate("TRUNCATE cs_estrutura_eventos", "insufficient_privilege")
        + sqlstate("UPDATE cs_estrutura_tipo_eventos SET tipo = 'excluido'", "insufficient_privilege")
        + sqlstate("DELETE FROM cs_estrutura_tipo_eventos", "insufficient_privilege")
        + sqlstate("TRUNCATE cs_estrutura_tipo_eventos", "insufficient_privilege")
        + sqlstate("TRUNCATE cs_estrutura_usos", "insufficient_privilege")
        + sqlstate("INSERT INTO cs_estrutura_eventos (estrutura_id, tipo, ator_tipo, versao) VALUES (e, 'inventado', 'admin', 1)", "check_violation")
        + sqlstate("INSERT INTO cs_estrutura_eventos (estrutura_id, tipo, ator_tipo, versao) VALUES (e, 'criada', 'robo', 1)", "check_violation")),
    "usos: append-only (UPDATE/DELETE refused) with the FK-action carve-outs: SET NULL of headline/roteiro, CASCADE of estrutura/marca/org": (
        "r := " + criar(blocos("A|v_th")) + "; e := (r->>'id')::uuid;"
        """
  INSERT INTO cs_headlines DEFAULT VALUES RETURNING id INTO he;
  INSERT INTO cs_roteiros DEFAULT VALUES RETURNING id INTO ro;
  INSERT INTO cs_estrutura_usos (org_id, marca_id, estrutura_id, contexto, papel, ordem, headline_id, roteiro_id, bloco_ids)
  VALUES (o, m, e, 'chat', 'principal', 1, he, ro, ARRAY[(SELECT id FROM cs_estrutura_blocos WHERE estrutura_id = e)]);"""
        + sqlstate("UPDATE cs_estrutura_usos SET papel = 'mistura' WHERE estrutura_id = e", "insufficient_privilege")
        + sqlstate("UPDATE cs_estrutura_usos SET headline_id = NULL WHERE estrutura_id = e", "insufficient_privilege")
        + sqlstate("DELETE FROM cs_estrutura_usos WHERE estrutura_id = e", "insufficient_privilege")
        + """
  DELETE FROM cs_headlines WHERE id = he;
  IF (SELECT (headline_id IS NULL, roteiro_id IS NOT NULL, papel)::text FROM cs_estrutura_usos WHERE estrutura_id = e) <> '(t,t,principal)' THEN
    RAISE EXCEPTION 'headline carve-out'; END IF;
  DELETE FROM cs_roteiros WHERE id = ro;
  IF (SELECT (roteiro_id IS NULL, org_id = o)::text FROM cs_estrutura_usos WHERE estrutura_id = e) <> '(t,t)' THEN RAISE EXCEPTION 'roteiro carve-out'; END IF;
  -- the use survived both SET NULLs; the marca cascade removes it
  DELETE FROM marcas WHERE id = m;
  IF (SELECT count(*) FROM cs_estrutura_usos WHERE estrutura_id = e) <> 0 THEN RAISE EXCEPTION 'marca cascade'; END IF;"""),
    "usos: deleting the profile cascades Estruturas AND their usos (the LGPD opt-out purge), leaving only content-free events": (
        "r := " + criar(blocos("A|v_th")) + "; e := (r->>'id')::uuid;"
        """
  INSERT INTO cs_estrutura_usos (org_id, marca_id, estrutura_id, contexto, papel, ordem, proposta_id)
  VALUES (o, m, e, 'chat', 'principal', 1, gen_random_uuid());
  DELETE FROM cs_perfis_monitorados WHERE id = pf;
  IF (SELECT count(*) FROM cs_estruturas WHERE id = e) <> 0 OR (SELECT count(*) FROM cs_estrutura_blocos WHERE estrutura_id = e) <> 0
     OR (SELECT count(*) FROM cs_estrutura_usos WHERE estrutura_id = e) <> 0 THEN RAISE EXCEPTION 'purge left rows behind'; END IF;
  IF (SELECT count(*) FROM cs_estrutura_eventos WHERE estrutura_id = e) <> 1 THEN RAISE EXCEPTION 'history'; END IF;
  -- org deletion cascades usos too
  r := cs_estrutura_criar(jsonb_build_object('perfil_id', (SELECT id FROM cs_perfis_monitorados LIMIT 1), 'formula_headline', 'x', 'status', 'rascunho'));
  e2 := (r->>'id')::uuid;
  INSERT INTO cs_estrutura_usos (org_id, marca_id, estrutura_id, contexto, papel, ordem, proposta_id) VALUES (o, m, e2, 'chat', 'principal', 1, gen_random_uuid());
  DELETE FROM public.organizations WHERE id = o;
  IF (SELECT count(*) FROM cs_estrutura_usos WHERE estrutura_id = e2) <> 0 THEN RAISE EXCEPTION 'org cascade'; END IF;"""),
    "usos: a retry never double-counts (unique per estrutura x roteiro / headline) and the vocabularies are closed": (
        "r := " + criar(blocos("A|v_th")) + "; e := (r->>'id')::uuid;"
        """
  INSERT INTO cs_headlines DEFAULT VALUES RETURNING id INTO he;
  INSERT INTO cs_roteiros DEFAULT VALUES RETURNING id INTO ro;
  INSERT INTO cs_estrutura_usos (org_id, marca_id, estrutura_id, contexto, papel, ordem, headline_id) VALUES (o, m, e, 'lote_headlines', 'principal', 1, he);
  INSERT INTO cs_estrutura_usos (org_id, marca_id, estrutura_id, contexto, papel, ordem, roteiro_id) VALUES (o, m, e, 'roteiro_avancado', 'mistura', 2, ro);"""
        + sqlstate("INSERT INTO cs_estrutura_usos (org_id, marca_id, estrutura_id, contexto, papel, ordem, headline_id) VALUES (o, m, e, 'chat', 'principal', 1, he)", "unique_violation")
        + sqlstate("INSERT INTO cs_estrutura_usos (org_id, marca_id, estrutura_id, contexto, papel, ordem, roteiro_id) VALUES (o, m, e, 'chat', 'principal', 1, ro)", "unique_violation")
        + sqlstate("INSERT INTO cs_estrutura_usos (org_id, marca_id, estrutura_id, contexto, papel, ordem) VALUES (o, m, e, 'outro', 'principal', 1)", "check_violation")
        + sqlstate("INSERT INTO cs_estrutura_usos (org_id, marca_id, estrutura_id, contexto, papel, ordem) VALUES (o, m, e, 'chat', 'dono', 1)", "check_violation")
        + sqlstate("INSERT INTO cs_estrutura_usos (org_id, marca_id, estrutura_id, contexto, papel, ordem) VALUES (o, m, e, 'chat', 'principal', 0)", "check_violation")),
    "importacoes: one em_andamento at a time (unique), counters never negative, status/fonte are closed vocabularies": (
        "INSERT INTO cs_estrutura_importacoes (fonte, arquivo_sha256, status) VALUES ('referencia', repeat('a', 64), 'em_andamento');"
        + sqlstate("INSERT INTO cs_estrutura_importacoes (fonte, arquivo_sha256, status) VALUES ('maquina_de_roteiros', repeat('b', 64), 'em_andamento')", "unique_violation")
        + """
  INSERT INTO cs_estrutura_importacoes (fonte, arquivo_sha256, status) VALUES ('referencia', repeat('a', 64), 'simulada');
  INSERT INTO cs_estrutura_importacoes (fonte, arquivo_sha256, status) VALUES ('referencia', repeat('a', 64), 'simulada');"""
        + sqlstate("INSERT INTO cs_estrutura_importacoes (fonte, arquivo_sha256, status, blocos_criados) VALUES ('referencia', repeat('c', 64), 'concluida', -1)", "check_violation")
        + sqlstate("INSERT INTO cs_estrutura_importacoes (fonte, arquivo_sha256, status) VALUES ('csv', repeat('c', 64), 'concluida')", "check_violation")
        + sqlstate("INSERT INTO cs_estrutura_importacoes (fonte, arquivo_sha256, status) VALUES ('referencia', repeat('c', 64), 'rodando')", "check_violation")
        + sqlstate("INSERT INTO cs_estrutura_importacoes (fonte, arquivo_sha256, status) VALUES ('referencia', 'curto', 'concluida')", "check_violation")
        + sqlstate("INSERT INTO cs_estrutura_importacoes (fonte, arquivo_sha256, status, ignoradas_motivos) VALUES ('referencia', repeat('c', 64), 'concluida', '[]'::jsonb)", "check_violation")),
    "one auto-draft per video and one (fonte_externa, ref_externa); a NULL pair is unconstrained": (
        "r := " + criar(blocos("A|v_th"), ", 'fonte_externa', 'maquina_de_roteiros', 'ref_externa', 'm1'") + ";"
        + sqlstate("PERFORM " + criar(blocos("A|v_th"), ", 'fonte_externa', 'maquina_de_roteiros', 'ref_externa', 'm1'"), "unique_violation")
        + "r := " + criar(blocos("A|v_th"), ", 'fonte_externa', 'corestudio', 'ref_externa', 'm1'") + ";"
        "r := " + criar(blocos("A|v_th")) + "; r := " + criar(blocos("A|v_th")) + ";"),
    # ── access / tiers / view ────────────────────────────────────────────────────
    "access: no browser privilege on any table / view / function; service_role reads the library but writes only through the RPCs": """
  FOR s IN SELECT unnest(ARRAY['cs_estruturas', 'cs_estrutura_blocos', 'cs_estrutura_eventos', 'cs_estrutura_importacoes',
      'cs_estrutura_tipos_bloco', 'cs_estrutura_tipo_eventos', 'cs_estrutura_usos', 'cs_estruturas_resumo']) LOOP
    IF has_table_privilege('authenticated', 'social_wiring.' || s, 'SELECT') OR has_table_privilege('anon', 'social_wiring.' || s, 'SELECT')
       OR has_table_privilege('authenticated', 'social_wiring.' || s, 'INSERT') OR has_table_privilege('anon', 'social_wiring.' || s, 'INSERT')
      THEN RAISE EXCEPTION 'browser role has a grant on %', s; END IF;
    IF NOT has_table_privilege('service_role', 'social_wiring.' || s, 'SELECT') THEN RAISE EXCEPTION 'service cannot read %', s; END IF;
  END LOOP;
  FOR s IN SELECT unnest(ARRAY['cs_estruturas', 'cs_estrutura_blocos', 'cs_estrutura_eventos', 'cs_estrutura_tipos_bloco', 'cs_estrutura_tipo_eventos']) LOOP
    IF has_table_privilege('service_role', 'social_wiring.' || s, 'INSERT') OR has_table_privilege('service_role', 'social_wiring.' || s, 'UPDATE')
       OR has_table_privilege('service_role', 'social_wiring.' || s, 'DELETE') THEN RAISE EXCEPTION 'service can write % directly', s; END IF;
  END LOOP;
  IF has_table_privilege('service_role', 'social_wiring.cs_estrutura_usos', 'UPDATE') OR has_table_privilege('service_role', 'social_wiring.cs_estrutura_usos', 'DELETE')
    THEN RAISE EXCEPTION 'usos is append-only'; END IF;
  IF NOT has_table_privilege('service_role', 'social_wiring.cs_estrutura_usos', 'INSERT')
     OR NOT has_table_privilege('service_role', 'social_wiring.cs_estrutura_importacoes', 'UPDATE') THEN RAISE EXCEPTION 'service lost a grant'; END IF;
  FOR s IN SELECT p.oid::regprocedure::text FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
            WHERE ns.nspname = 'social_wiring' AND p.proname LIKE 'cs\\_estrutura\\_%' AND p.prokind = 'f' LOOP
    IF has_function_privilege('authenticated', s, 'EXECUTE') OR has_function_privilege('anon', s, 'EXECUTE') THEN RAISE EXCEPTION 'browser can execute %', s; END IF;
  END LOOP;
  IF NOT has_function_privilege('service_role', 'social_wiring.cs_estrutura_criar(jsonb)', 'EXECUTE')
     OR has_function_privilege('service_role', 'social_wiring.cs_estrutura_travar(uuid,integer)', 'EXECUTE') THEN RAISE EXCEPTION 'service EXECUTE surface'; END IF;
  IF (SELECT count(*) FROM pg_policies WHERE schemaname = 'social_wiring' AND tablename LIKE 'cs\\_estrutura%' AND roles <> '{service_role}') <> 0 THEN
    RAISE EXCEPTION 'a non-service policy exists'; END IF;""",
    "tiers: the library is tier:platform, usos tier:org; every definer function pins search_path": """
  FOR s IN SELECT unnest(ARRAY['cs_estruturas', 'cs_estrutura_blocos', 'cs_estrutura_eventos', 'cs_estrutura_importacoes', 'cs_estrutura_tipos_bloco', 'cs_estrutura_tipo_eventos', 'cs_estruturas_resumo']) LOOP
    IF obj_description(('social_wiring.' || s)::regclass) <> 'tier:platform' THEN RAISE EXCEPTION 'tier of %', s; END IF;
  END LOOP;
  IF obj_description('social_wiring.cs_estrutura_usos'::regclass) <> 'tier:org' THEN RAISE EXCEPTION 'usos tier'; END IF;
  SELECT count(*) INTO n FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
   WHERE ns.nspname = 'social_wiring' AND p.proname LIKE 'cs\\_estrutura\\_%' AND p.prosecdef AND p.proconfig::text NOT LIKE '%search_path%';
  IF n <> 0 THEN RAISE EXCEPTION 'unpinned definer functions: %', n; END IF;""",
    "view cs_estruturas_resumo: blocos_total, campos_pendentes and a Portuguese full-text `busca` over formula + block names": (
        "r := " + criar(blocos("Abertura forte|v_th|'tipo_origem', 'referencia'", "Prova social|v_tr"), ", 'formula_origem', 'referencia'") + "; e := (r->>'id')::uuid;"
        + expect("(blocos_total, campos_pendentes) FROM cs_estruturas_resumo WHERE id = e", "(2,2)", "counts")
        + """
  IF NOT EXISTS (SELECT 1 FROM cs_estruturas_resumo WHERE id = e AND busca @@ websearch_to_tsquery('portuguese', 'prova social')) THEN RAISE EXCEPTION 'block name search'; END IF;
  IF NOT EXISTS (SELECT 1 FROM cs_estruturas_resumo WHERE id = e AND busca @@ websearch_to_tsquery('portuguese', 'fórmula OR faz')) THEN RAISE EXCEPTION 'formula search'; END IF;
  IF EXISTS (SELECT 1 FROM cs_estruturas_resumo WHERE id = e AND busca @@ websearch_to_tsquery('portuguese', 'inexistente')) THEN RAISE EXCEPTION 'false hit'; END IF;
  IF (SELECT count(*) FROM pg_class WHERE relname = 'cs_estruturas_resumo' AND reloptions::text LIKE '%security_invoker=true%') <> 1 THEN RAISE EXCEPTION 'not security_invoker'; END IF;"""),
}


@pytest.fixture(scope="module")
def replay() -> dict:
    sql = MIGRATION.read_text(encoding="utf-8")
    steps = [
        {"product": "sw", "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": "sw", "file": "migration", "sql": sql, "mode": "file", "twice": True},
        *(
            {"product": "sw", "file": f"scenario: {name}", "sql": _BASE.replace("{body}", body), "mode": "file", "twice": False}
            for name, body in SCENARIOS.items()
        ),
    ]
    proc = subprocess.run(
        ["node", str(HARNESS)],
        input=json.dumps({"stubs": STUBS.read_text(encoding="utf-8"), "steps": steps}),
        capture_output=True, text=True, cwd=NODE_DIR, timeout=300,
    )
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"PGlite harness produced no verdict: {(proc.stderr or proc.stdout)[-400:]}")
    assert out.get("ok"), out
    return {step["file"]: step for step in out["steps"]}


def test_migration_applies_twice_without_failures(replay):
    assert replay["prelude"]["failures"] == [], replay["prelude"]["failures"]
    assert replay["migration"]["failures"] == [], replay["migration"]["failures"]


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_scenario(replay, name):
    assert replay[f"scenario: {name}"]["failures"] == [], replay[f"scenario: {name}"]["failures"]


# ── static pins (no database) ────────────────────────────────────────────────────────────────────────────


def _code() -> str:
    return "\n".join(line for line in MIGRATION.read_text(encoding="utf-8").splitlines() if not line.strip().startswith("--"))


def test_every_enum_in_the_migration_is_the_python_vocabulary():
    code = _code()
    for vocab in (fmt.FORMATOS, fmt.OBJETIVOS, fmt.STATUS, fmt.ORIGENS, fmt.EVENTO_TIPOS, fmt.TIPO_EVENTO_TIPOS, fmt.ATOR_TIPOS):
        assert "(" + ", ".join(f"'{v}'" for v in vocab) + ")" in code.replace("\n", " ").replace("  ", " ") or all(
            f"'{v}'" in code for v in vocab
        ), vocab
    assert "'fonte', 'referencia', 'ia_sugerido', 'admin'" in code


def test_no_function_is_executable_by_a_browser_role_and_every_definer_revokes():
    code = _code()
    definers = code.count("SECURITY DEFINER")
    assert definers == 10
    assert code.count("FROM PUBLIC, anon, authenticated;") >= definers + 2 + 5  # + the two internal helpers + the five trigger functions
    assert "TO authenticated" not in code and "TO anon" not in code


def test_the_library_has_no_browser_policy_and_no_org_id():
    code = _code()
    assert "TO authenticated" not in code
    for table in ("cs_estruturas", "cs_estrutura_blocos", "cs_estrutura_tipos_bloco", "cs_estrutura_eventos"):
        block = code.split(f"CREATE TABLE IF NOT EXISTS social_wiring.{table} (")[1].split("\n);")[0]
        assert "org_id" not in block, table
