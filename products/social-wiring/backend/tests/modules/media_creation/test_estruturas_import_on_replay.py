"""The loader's payloads on REAL Postgres (PGlite): migration 350 applied, the EXACT jsonb the loader sends run through the
SECURITY DEFINER RPCs (``cs_estrutura_criar`` / ``_substituir_blocos`` / ``_atualizar``).

The loader tests prove WHAT is sent (a recording double); this proves the RPCs do with it what the contract says:
provenance as mapped, ``importada`` / ``atualizada_import`` events with ``sistema_import`` + the lote id, an
``admin``-origin field untouched by a changed file, and a second identical call changing NOTHING (no version bump, no
event). Payloads come from the real builders (``payload_criar`` / ``montar_patch`` / ``montar_blocos``); ids the SQL
generates are carried as ``@@TOKEN@@`` placeholders substituted in SQL.
"""
from __future__ import annotations

import copy
import json
import shutil
import subprocess

import pytest

from app.modules.media_creation.services import estruturas_import as imp

from ...test_migration_cs_estruturas import HARNESS, MIGRATION, NODE_DIR, PRELUDE, STUBS, _BASE
from ._estruturas_import_fixtures import TIPOS_CATALOGO, bloco_ref, linha_ref

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not HARNESS.exists() or not (NODE_DIR / "node_modules" / "@electric-sql").exists(),
    reason="PGlite replay harness unavailable (needs `node` and mcp/noctusai/node/node_modules)",
)

LOTE = "11111111-1111-1111-1111-111111111111"
LOTE_2 = "22222222-2222-2222-2222-222222222222"
ATOR = "00000000-0000-0000-0000-0000000000a1"
#: every catalog name the synthetic corpus uses is a real seeded type
TIPO_TOKENS = {n: f"@@TIPO:{n}@@" for n in TIPOS_CATALOGO}


def _linha(row):
    (l,) = imp.parse_documento("referencia", [row], TIPOS_CATALOGO).linhas
    return l


def lit(valor) -> str:
    """A jsonb literal with ``@@TOKEN@@`` placeholders resolved in SQL (``tok``)."""
    return f"tok($j${json.dumps(valor, ensure_ascii=False)}$j$)"


#: SQL helper defined per scenario: replaces @@PERFIL@@, @@TIPO:<nome>@@ and @@B<n>@@ (block id by ordem of estrutura e).
TOK = """
  CREATE OR REPLACE FUNCTION pg_temp.tok(txt text, p uuid, e uuid) RETURNS jsonb LANGUAGE plpgsql AS $f$
  DECLARE t record; n int; BEGIN
    txt := replace(txt, '@@PERFIL@@', p::text);
    FOR t IN SELECT id, nome FROM social_wiring.cs_estrutura_tipos_bloco LOOP txt := replace(txt, '@@TIPO:' || t.nome || '@@', t.id::text); END LOOP;
    IF e IS NOT NULL THEN
      FOR n IN 1..9 LOOP txt := replace(txt, '@@B' || n || '@@', coalesce((SELECT id::text FROM social_wiring.cs_estrutura_blocos WHERE estrutura_id = e AND ordem = n), 'x')); END LOOP;
    END IF;
    RETURN txt::jsonb; END $f$;
"""


def sql_json(valor) -> str:
    return f"pg_temp.tok($j${json.dumps(valor, ensure_ascii=False)}$j$, pf, e)"


def _criar_payload(row):
    return imp.payload_criar(_linha(row), perfil_id="@@PERFIL@@", tipo_ids=TIPO_TOKENS, importacao_id=LOTE, ator_id=ATOR)


def _existente_tokens(payload_blocos):
    """What ``blocos_de`` would read back after the create (ids as @@B<n>@@)."""
    return [{"id": f"@@B{i}@@", "ordem": i, **{k: v for k, v in b.items()}} for i, b in enumerate(payload_blocos, 1)]


def _update_calls(row_novo, existente_estrutura, existentes_blocos):
    l = _linha(row_novo)
    blocos, _ = imp.montar_blocos(l, existentes_blocos, TIPO_TOKENS)
    patch = imp.montar_patch(l, existente_estrutura, importacao_id=LOTE_2)
    return blocos, patch


_SEQ = iter(range(5000, 6000))
EX_ESTRUTURA = {"formula_origem": "referencia", "formato_origem": "referencia", "objetivos_origem": "referencia"}


class Ctx:
    """One scenario's own source row: the scenarios share ONE database, so every one needs its own ``(fonte, ref)`` key."""

    def __init__(self):
        self.ref = str(next(_SEQ))
        self.row = linha_ref(1, perfil="criador.um", formula_herdada_de="77", corestudio_id=self.ref)
        self.criar = _criar_payload(self.row)
        self.cria = f"r := cs_estrutura_criar({sql_json(self.criar)}); e := (r->>'id')::uuid;"
        self.existentes = _existente_tokens(self.criar["blocos"])

    def alterado(self):
        novo = copy.deepcopy(self.row)
        novo["formula_headline"] = "ZZ nova fórmula [tema]"
        novo["objetivos"] = ["autoridade"]
        novo["blocos"][0]["nome_original"] = "ZZ novo nome"
        novo["blocos"][0]["instrucao"] = "ZZ nova instrução"
        novo["blocos"].append(bloco_ref(4, tipo="Headline"))
        return novo


def _scenarios() -> dict[str, str]:
    sc: dict[str, str] = {}

    c = Ctx()
    sc["create: provenance as mapped, an importada event by sistema_import carrying the lote id, status ativa, codigo issued"] = (
        TOK + c.cria + f"""
  IF (SELECT (formula_origem, formato_origem, objetivos_origem, origem, status, fonte_externa, ref_externa, referencia_rotulo, formula_herdada_de)::text FROM cs_estruturas WHERE id = e)
     <> '(referencia,referencia,referencia,import_corestudio,ativa,corestudio,{c.ref},referencia-sintetica,77)' THEN RAISE EXCEPTION 'estrutura %', (SELECT row_to_json(x)::text FROM cs_estruturas x WHERE id = e); END IF;
  IF (SELECT count(*) FROM cs_estrutura_blocos WHERE estrutura_id = e AND nome_origem = 'fonte' AND tipo_origem = 'referencia' AND tempo_origem = 'referencia' AND instrucao_origem = 'referencia') <> 3 THEN RAISE EXCEPTION 'block provenance'; END IF;
  IF (SELECT nota FROM cs_estrutura_blocos WHERE estrutura_id = e AND ordem = 1) IS NOT NULL THEN RAISE EXCEPTION 'empty nota must be NULL'; END IF;
  IF (SELECT count(*) FROM cs_estrutura_eventos WHERE estrutura_id = e AND tipo = 'importada' AND ator_tipo = 'sistema_import' AND importacao_id = '{LOTE}') <> 1 THEN RAISE EXCEPTION 'importada event'; END IF;
  IF (SELECT count(*) FROM cs_estrutura_eventos WHERE estrutura_id = e AND tipo = 'ia_preenchida') <> 0 THEN RAISE EXCEPTION 'the load must never record AI provenance'; END IF;
  IF (SELECT campos_pendentes FROM cs_estruturas_resumo WHERE id = e) <> 3 + 3 * 3 THEN RAISE EXCEPTION 'pending count: %', (SELECT campos_pendentes FROM cs_estruturas_resumo WHERE id = e); END IF;""")

    c = Ctx()
    sc["the same key created twice is refused by the unique index (the loader reads first, so this is the race backstop)"] = (
        TOK + c.cria + """
  BEGIN PERFORM cs_estrutura_criar(""" + sql_json(c.criar) + """); RAISE EXCEPTION 'no refusal'; EXCEPTION WHEN unique_violation THEN NULL; END;""")

    # an UNCHANGED re-send: same hash/patch/blocks => nothing changes (the loader skips these via the hash, this is defence in depth)
    c = Ctx()
    blocos_igual, patch_igual = _update_calls(c.row, EX_ESTRUTURA, c.existentes)
    sc["a re-send of the same file changes nothing: no version bump, no event"] = (
        TOK + c.cria + f"""
  r := cs_estrutura_substituir_blocos(e, 1, {sql_json({"blocos": blocos_igual, "ator_tipo": "sistema_import", "evento": "atualizada_import", "importacao_id": LOTE_2})}, '{ATOR}');
  IF (r->>'alterada')::boolean OR (r->>'versao')::int <> 1 THEN RAISE EXCEPTION 'blocks changed: %', r; END IF;
  r := cs_estrutura_atualizar(e, 1, {sql_json(patch_igual)}, '{ATOR}');
  IF (r->>'alterada')::boolean OR (r->>'versao')::int <> 1 THEN RAISE EXCEPTION 'estrutura changed: %', r; END IF;
  IF (SELECT count(*) FROM cs_estrutura_eventos WHERE estrutura_id = e) <> 1 THEN RAISE EXCEPTION 'events written by a no-op'; END IF;""")

    # a CHANGED file: new formula/objetivos/block text + an extra block
    c = Ctx()
    novo = c.alterado()
    blocos_novo, patch_novo = _update_calls(novo, EX_ESTRUTURA, c.existentes)
    sc["a changed file updates fonte/referencia fields, adds the block, stamps the hash last and writes atualizada_import events with the lote id"] = (
        TOK + c.cria + f"""
  r := cs_estrutura_substituir_blocos(e, 1, {sql_json({"blocos": blocos_novo, "ator_tipo": "sistema_import", "evento": "atualizada_import", "importacao_id": LOTE_2})}, '{ATOR}');
  IF NOT (r->>'alterada')::boolean OR (r->>'versao')::int <> 2 THEN RAISE EXCEPTION 'blocks: %', r; END IF;
  r := cs_estrutura_atualizar(e, 2, {sql_json(patch_novo)}, '{ATOR}');
  IF NOT (r->>'alterada')::boolean OR (r->>'versao')::int <> 3 THEN RAISE EXCEPTION 'estrutura: %', r; END IF;
  IF NOT EXISTS (SELECT 1 FROM cs_estruturas WHERE id = e AND formula_headline = 'ZZ nova fórmula [tema]' AND objetivos = ARRAY['autoridade'] AND fonte_hash = '{_linha(novo).hash}') THEN RAISE EXCEPTION 'content'; END IF;
  IF (SELECT count(*) FROM cs_estrutura_blocos WHERE estrutura_id = e) <> 4 THEN RAISE EXCEPTION 'block count'; END IF;
  IF (SELECT count(*) FROM cs_estrutura_eventos WHERE estrutura_id = e AND importacao_id = '{LOTE_2}' AND ator_tipo = 'sistema_import') < 4 THEN RAISE EXCEPTION 'update events'; END IF;
  IF EXISTS (SELECT 1 FROM cs_estrutura_eventos WHERE estrutura_id = e AND importacao_id = '{LOTE_2}' AND tipo NOT IN ('atualizada_import', 'bloco_adicionado')) THEN RAISE EXCEPTION 'unexpected event kinds'; END IF;""")

    # admin-touched fields survive: an admin edits the formula, objetivos and block 1's nome/instrucao/nota BEFORE the changed file arrives
    c = Ctx()
    novo = c.alterado()
    admin_existentes = [dict(b) for b in c.existentes]
    admin_existentes[0].update(nome="NOME DO ADMIN", nome_origem="admin", instrucao="INSTRUCAO DO ADMIN", instrucao_origem="admin", nota="NOTA DO ADMIN", repeticoes=3)
    ex_admin = {"formula_origem": "admin", "formato_origem": "referencia", "objetivos_origem": "admin"}
    blocos_adm, patch_adm = _update_calls(novo, ex_admin, admin_existentes)
    admin_edit = [{"id": "@@B1@@", "nome": "NOME DO ADMIN", "tipo_id": "@@TIPO:Headline@@", "tempo": c.criar["blocos"][0]["tempo"], "instrucao": "INSTRUCAO DO ADMIN",
                   "nota": "NOTA DO ADMIN", "repeticoes": 3, "nome_origem": "admin", "instrucao_origem": "admin"}] + [
        {"id": f"@@B{i}@@", **{k: v for k, v in c.criar["blocos"][i - 1].items()}} for i in (2, 3)]
    sc["an admin-origin field is never overwritten by a changed file (formula, objetivos, block nome/instrucao/nota/repeticoes)"] = (
        TOK + c.cria + f"""
  PERFORM cs_estrutura_atualizar(e, 1, '{{"formula_headline": "FORMULA DO ADMIN", "objetivos": ["venda"]}}'::jsonb, '{ATOR}');
  PERFORM cs_estrutura_substituir_blocos(e, 2, {sql_json(admin_edit)}, '{ATOR}');
  r := cs_estrutura_substituir_blocos(e, 3, {sql_json({"blocos": blocos_adm, "ator_tipo": "sistema_import", "evento": "atualizada_import", "importacao_id": LOTE_2})}, '{ATOR}');
  r := cs_estrutura_atualizar(e, COALESCE((r->>'versao')::int, 3), {sql_json(patch_adm)}, '{ATOR}');
  IF NOT EXISTS (SELECT 1 FROM cs_estruturas WHERE id = e AND formula_headline = 'FORMULA DO ADMIN' AND objetivos = ARRAY['venda'] AND formula_origem = 'admin' AND objetivos_origem = 'admin') THEN
    RAISE EXCEPTION 'admin estrutura fields overwritten: %', (SELECT row_to_json(x)::text FROM cs_estruturas x WHERE id = e); END IF;
  IF NOT EXISTS (SELECT 1 FROM cs_estrutura_blocos WHERE estrutura_id = e AND ordem = 1 AND nome = 'NOME DO ADMIN' AND instrucao = 'INSTRUCAO DO ADMIN' AND nota = 'NOTA DO ADMIN'
                  AND repeticoes = 3 AND nome_origem = 'admin' AND instrucao_origem = 'admin') THEN
    RAISE EXCEPTION 'admin block fields overwritten: %', (SELECT row_to_json(x)::text FROM cs_estrutura_blocos x WHERE estrutura_id = e AND ordem = 1); END IF;
  IF (SELECT count(*) FROM cs_estrutura_blocos WHERE estrutura_id = e) <> 4 THEN RAISE EXCEPTION 'the new block must still arrive'; END IF;
  IF (SELECT fonte_hash FROM cs_estruturas WHERE id = e) IS DISTINCT FROM '{_linha(novo).hash}' THEN RAISE EXCEPTION 'the hash must be stamped even when admin fields are skipped'; END IF;""")

    c = Ctx()
    _, patch_arq = _update_calls(c.alterado(), EX_ESTRUTURA, c.existentes)
    sc["an archived estrutura refuses the loader's writes (estrutura_inativa) and a missing block type is tipo_nao_encontrado"] = (
        TOK + c.cria + f"""
  PERFORM cs_estrutura_arquivar(e, '{ATOR}');
  BEGIN PERFORM cs_estrutura_atualizar(e, 2, {sql_json(patch_arq)}, '{ATOR}'); RAISE EXCEPTION 'no refusal'; EXCEPTION WHEN OTHERS THEN IF SQLERRM <> 'estrutura_inativa' THEN RAISE; END IF; END;
  BEGIN PERFORM cs_estrutura_criar(jsonb_set(jsonb_set({sql_json(c.criar)}, '{{ref_externa}}', '"9999"'), '{{blocos,0,tipo_id}}', to_jsonb(gen_random_uuid()::text))); RAISE EXCEPTION 'no refusal';
  EXCEPTION WHEN OTHERS THEN IF SQLERRM <> 'tipo_nao_encontrado' THEN RAISE; END IF; END;""")

    # the synthetic corpus through the real RPC: every row creates with a unique codigo, its blocks and its lote-stamped event
    corpus = [_linha(r) for r in (linha_ref(i, perfil="criador.um", corestudio_id=str(7000 + i)) for i in range(1, 7))]
    chamadas = [
        f"PERFORM cs_estrutura_criar({sql_json(imp.payload_criar(l, perfil_id='@@PERFIL@@', tipo_ids=TIPO_TOKENS, importacao_id=LOTE, ator_id=ATOR))});"
        for l in corpus
    ]
    sc["a synthetic corpus creates one estrutura per row with a unique codigo and its blocks, every event carrying the lote"] = (
        TOK + "e := NULL;\n  " + "\n  ".join(chamadas) + f"""
  IF (SELECT count(*) FROM cs_estruturas WHERE ref_externa LIKE '70%') <> {len(corpus)} THEN RAISE EXCEPTION 'rows'; END IF;
  IF (SELECT count(DISTINCT codigo) FROM cs_estruturas WHERE ref_externa LIKE '70%') <> {len(corpus)} THEN RAISE EXCEPTION 'codigo'; END IF;
  IF (SELECT count(*) FROM cs_estrutura_blocos b JOIN cs_estruturas e2 ON e2.id = b.estrutura_id WHERE e2.ref_externa LIKE '70%') <> {3 * len(corpus)} THEN RAISE EXCEPTION 'blocks'; END IF;
  IF (SELECT count(*) FROM cs_estrutura_eventos v JOIN cs_estruturas e2 ON e2.id = v.estrutura_id WHERE e2.ref_externa LIKE '70%' AND v.tipo = 'importada' AND v.importacao_id = '{LOTE}') <> {len(corpus)} THEN RAISE EXCEPTION 'events'; END IF;""")
    return sc


SCENARIOS = _scenarios()


@pytest.fixture(scope="module")
def replay() -> dict:
    sql = MIGRATION.read_text(encoding="utf-8")
    steps = [
        {"product": "sw", "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": "sw", "file": "migration", "sql": sql, "mode": "file", "twice": False},
        *(
            {"product": "sw", "file": f"scenario: {name}", "sql": _BASE.replace("{body}", body), "mode": "file", "twice": False}
            for name, body in SCENARIOS.items()
        ),
    ]
    proc = subprocess.run(
        ["node", str(HARNESS)], input=json.dumps({"stubs": STUBS.read_text(encoding="utf-8"), "steps": steps}),
        capture_output=True, text=True, cwd=NODE_DIR, timeout=300,
    )
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"PGlite harness produced no verdict: {(proc.stderr or proc.stdout)[-400:]}")
    assert out.get("ok") or out.get("steps"), out
    return {step["file"]: step for step in out["steps"]}


def test_migration_applies(replay):
    assert replay["prelude"]["failures"] == [] and replay["migration"]["failures"] == []


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_scenario(replay, name):
    assert replay[f"scenario: {name}"]["failures"] == [], replay[f"scenario: {name}"]["failures"]
