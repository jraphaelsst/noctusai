"""Migration ``cs_roteiro_primeiro`` (M6 of estruturas-contract.md section 16.2) on a REAL Postgres (PGlite).

The prelude is the 352 test's (the 229/241/marcas tables 352 references) with ``cs_roteiros`` completed to its prod
shape (status / conteudo / fonte / versao / created_by / finished_at, NOT NULL nome + headline_texto). Then the REAL 350
and 352 files, a pre-M6 headline proposta (a row the N-1 image wrote), and the REAL M6 file TWICE (idempotency); every
RPC / CHECK / UNIQUE / grant M6 adds is exercised against the result.

Referenced by name (``migration_path``), never by its NNN_ number: integrate renumbers.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from noctusai_lib.testing.migrations import migration_path

from tests.test_migration_cs_unified_chat import (  # the shared harness + SQL helpers of the 352 test (one derivation)
    BACKEND,
    HARNESS,
    M350,
    MIGRATION as M352,
    NODE_DIR,
    PRELUDE as PRELUDE_352,
    STUBS,
    _BASE,
    evt,
    expect,
    refuses,
    resposta,
    sqlstate,
)
from tests.test_migration_cs_unified_chat import pytestmark  # noqa: F401 - same skip when the harness is absent

MIGRATION = migration_path(BACKEND, "cs_roteiro_primeiro")

PRELUDE = PRELUDE_352 + """
ALTER TABLE cs_roteiros
  ADD COLUMN created_by uuid,
  ADD COLUMN fonte text NOT NULL DEFAULT 'ia' CHECK (fonte IN ('ia', 'web', 'link')),
  ADD COLUMN duracao text NOT NULL DEFAULT 'auto' CHECK (duracao IN ('auto', '1', '2', '3')),
  ADD COLUMN status text NOT NULL DEFAULT 'criando' CHECK (status IN ('criando', 'perguntas', 'processando', 'completo', 'falha')),
  ADD COLUMN conteudo text NOT NULL DEFAULT '' CHECK (char_length(conteudo) <= 30000),
  ADD COLUMN versao integer NOT NULL DEFAULT 1,
  ADD COLUMN finished_at timestamptz,
  ADD COLUMN created_at timestamptz NOT NULL DEFAULT now();
UPDATE cs_roteiros SET nome = 'n', headline_texto = 'h';
ALTER TABLE cs_roteiros ALTER COLUMN nome SET NOT NULL, ALTER COLUMN headline_texto SET NOT NULL,
  ADD CONSTRAINT cs_roteiros_nome_check CHECK (char_length(nome) BETWEEN 1 AND 160),
  ADD CONSTRAINT cs_roteiros_headline_texto_check CHECK (char_length(headline_texto) BETWEEN 1 AND 1000);
"""

#: A headline proposta written by the N-1 image BEFORE M6 (no tipo column yet).
PRE_M6 = """
SET search_path = social_wiring, public;
DO $$
DECLARE c uuid; msg uuid;
BEGIN
  INSERT INTO cs_chat_conversas (org_id, marca_id, user_id, agente, titulo)
    VALUES ('00000000-0000-0000-0000-0000000000f0', '00000000-0000-0000-0000-0000000000f1', gen_random_uuid(), 'unificado', 'legacy')
    RETURNING id INTO c;
  INSERT INTO cs_chat_mensagens (org_id, conversa_id, role, conteudo, tipo)
    VALUES ('00000000-0000-0000-0000-0000000000f0', c, 'assistant', 'x', 'texto') RETURNING id INTO msg;
  INSERT INTO cs_chat_propostas (id, org_id, marca_id, conversa_id, mensagem_id, ordem, texto)
    VALUES ('00000000-0000-0000-0000-0000000000e1', '00000000-0000-0000-0000-0000000000f0',
            '00000000-0000-0000-0000-0000000000f1', c, msg, 1, 'Headline legada');
END $$;
"""

#: one headline proposta (#1, cites e1) and one carrossel roteiro proposta (#2, cites e2 principal + e3)
MISTA = (
    "jsonb_build_array("
    "jsonb_build_object('ordem', 1, 'tipo', 'headline', 'texto', 'Headline um', 'estrutura_ids', jsonb_build_array(e1)), "
    "jsonb_build_object('ordem', 2, 'tipo', 'roteiro', 'texto', '**Slide 1 — Gancho**' || chr(10) || repeat('a', 4000), "
    "'titulo', 'O erro que custa caro', 'formato', 'carrossel', 'estrutura_ids', jsonb_build_array(e2, e3)))"
)

GRAVAR = f"""
  r := {resposta(MISTA)};
  msg := (r->>'mensagem_id')::uuid;
  SELECT id INTO p1 FROM cs_chat_propostas WHERE mensagem_id = msg AND ordem = 1;
  SELECT id INTO p2 FROM cs_chat_propostas WHERE mensagem_id = msg AND ordem = 2;
"""

#: p2 claimed and its roteiro saved; `h` = the roteiro id
SALVO = GRAVAR + """
  PERFORM cs_chat_proposta_reivindicar(p2, o, c, u, 60);
  r := cs_chat_proposta_salvar_roteiro(p2, o, u); h := (r->>'roteiro_id')::uuid;
"""


def _proposta(ordem: int, tipo: str, texto: str, titulo: str = "NULL", formato: str = "NULL") -> str:
    return (f"INSERT INTO cs_chat_propostas (org_id, marca_id, conversa_id, mensagem_id, ordem, tipo, texto, titulo, formato) "
            f"VALUES (o, m, c, msg, {ordem}, '{tipo}', {texto}, {titulo}, {formato})")


SCENARIOS: dict[str, str] = {
    # ── the N-1 rows and the widened CHECKs ─────────────────────────────────────────────────────────────
    "a proposta written before M6 reads as a headline with no titulo/formato/roteiro": (
        expect("(tipo, titulo IS NULL, formato IS NULL, roteiro_id IS NULL)::text FROM cs_chat_propostas "
               "WHERE id = '00000000-0000-0000-0000-0000000000e1'", "(headline,t,t,t)", "legacy")
    ),
    "resposta_gravar persists both kinds in order: tipo, titulo, formato, the long script, the Estrutura links": (
        GRAVAR
        + expect("(tipo, titulo IS NULL, formato IS NULL)::text FROM cs_chat_propostas WHERE id = p1", "(headline,t,t)", "headline")
        + expect("(tipo, titulo, formato, char_length(texto) > 4000, status, fluxo_etapa IS NULL)::text FROM cs_chat_propostas WHERE id = p2",
                 "(roteiro,\"O erro que custa caro\",carrossel,t,proposta,t)", "roteiro")
        + expect("string_agg(ordem || ':' || principal::text, ',' ORDER BY ordem) FROM cs_chat_proposta_estruturas WHERE proposta_id = p2",
                 "1:true,2:false", "links")
        + expect(evt("propostas_geradas", "contagem = 2"), "1", "one event for both")
    ),
    "a proposta without tipo in the payload is a headline (the N-1 payload shape)": (
        "r := " + resposta("jsonb_build_array(jsonb_build_object('ordem', 1, 'texto', 'Sem tipo', 'estrutura_ids', jsonb_build_array(e1)))") + ";"
        + expect("tipo FROM cs_chat_propostas WHERE conversa_id = c", "headline", "default")
    ),
    "the tipo/titulo/formato/texto CHECKs: a roteiro needs both, a headline neither; 1000 vs 12000 chars": (
        GRAVAR
        + sqlstate(_proposta(9, "outro", "'x'"), "check_violation")
        + sqlstate(_proposta(9, "roteiro", "'corpo'", formato="'reels'"), "check_violation")  # no titulo
        + sqlstate(_proposta(9, "roteiro", "'corpo'", titulo="'T'"), "check_violation")  # no formato
        + sqlstate(_proposta(9, "headline", "'h'", titulo="'T'"), "check_violation")
        + sqlstate(_proposta(9, "headline", "'h'", formato="'reels'"), "check_violation")
        + sqlstate(_proposta(9, "roteiro", "'corpo'", "'T'", "'short'"), "check_violation")
        + sqlstate(_proposta(9, "roteiro", "'corpo'", "repeat('t', 121)", "'reels'"), "check_violation")
        + sqlstate(_proposta(9, "headline", "repeat('h', 1001)"), "check_violation")
        + sqlstate(_proposta(9, "roteiro", "repeat('r', 12001)", "'T'", "'reels'"), "check_violation")
        + sqlstate(_proposta(9, "roteiro", "''", "'T'", "'reels'"), "check_violation")
        + _proposta(9, "roteiro", "repeat('r', 12000)", "'T'", "'post'") + ";"
        + _proposta(10, "headline", "repeat('h', 1000)") + ";"
    ),
    "fluxo_etapa accepts roteiro_salvo and headline_gerada (and still refuses anything else)": (
        GRAVAR
        + "UPDATE cs_chat_propostas SET fluxo_etapa = 'roteiro_salvo' WHERE id = p2;"
        + "UPDATE cs_chat_propostas SET fluxo_etapa = 'headline_gerada' WHERE id = p2;"
        + sqlstate("UPDATE cs_chat_propostas SET fluxo_etapa = 'quase_la' WHERE id = p2", "check_violation")
    ),
    "the ledger accepts the roteiro-first vocabulary, still refuses unknown tipos and stays append-only": (
        "INSERT INTO cs_fluxo_eventos (org_id, marca_id, conversa_id, tipo) VALUES (o, m, c, 'roteiro_salvo'), "
        "(o, m, c, 'headline_gerando'), (o, m, c, 'headline_gerada'), (o, m, c, 'headline_falhou'), (o, m, c, 'roteiro_invalido');"
        + sqlstate("INSERT INTO cs_fluxo_eventos (org_id, marca_id, conversa_id, tipo) VALUES (o, m, c, 'inventado')", "check_violation")
        + refuses("UPDATE cs_fluxo_eventos SET tipo = 'roteiro_salvo' WHERE org_id = o",
                  "cs_fluxo_eventos_imutavel: cs_fluxo_eventos is append-only (UPDATE refused)")
    ),
    "cs_headlines.modo accepts do_roteiro and still refuses anything else": (
        "INSERT INTO cs_headlines (org_id, marca_id, texto, modo) VALUES (o, m, 'a', 'do_roteiro'), (o, m, 'b', 'manual'), (o, m, 'c', NULL);"
        + sqlstate("INSERT INTO cs_headlines (org_id, marca_id, texto, modo) VALUES (o, m, 'd', 'inventado')", "check_violation")
    ),
    "cs_roteiros: (conversa, proposta) is unique; a NULL proposta is unconstrained": (
        GRAVAR
        + "INSERT INTO cs_roteiros (org_id, marca_id, nome, headline_texto, conversa_id, proposta_id) VALUES (o, m, 'a', 'a', c, p2);"
        + sqlstate("INSERT INTO cs_roteiros (org_id, marca_id, nome, headline_texto, conversa_id, proposta_id) VALUES (o, m, 'b', 'b', c, p2)", "unique_violation")
        + "INSERT INTO cs_roteiros (org_id, marca_id, nome, headline_texto, conversa_id) VALUES (o, m, 'c', 'c', c), (o, m, 'd', 'd', c);"
    ),
    # ── salvar_roteiro ──────────────────────────────────────────────────────────────────────────────────
    "salvar_roteiro: the script saved as-is (completo, nome = titulo, formato, links), usos per Estrutura, etapa, ONE event": (
        SALVO
        + expect("(r->>'criado')::boolean", "true", "criado")
        + expect("(status, nome, headline_texto, formato, fonte, versao, conteudo = (SELECT texto FROM cs_chat_propostas WHERE id = p2), "
                 "conversa_id = c, proposta_id = p2, created_by = u, finished_at IS NOT NULL, headline_id IS NULL)::text FROM cs_roteiros WHERE id = h",
                 "(completo,\"O erro que custa caro\",\"O erro que custa caro\",carrossel,ia,1,t,t,t,t,t,t)", "roteiro")
        + expect("(roteiro_id = h, fluxo_etapa, headline_id IS NULL)::text FROM cs_chat_propostas WHERE id = p2", "(t,roteiro_salvo,t)", "proposta")
        + expect("string_agg(papel || ':' || ordem || ':' || contexto || ':' || (headline_id IS NULL)::text, ',' ORDER BY ordem) "
                 "FROM cs_estrutura_usos WHERE proposta_id = p2 AND roteiro_id = h", "principal:1:chat:true,mistura:2:chat:true", "usos")
        + expect(evt("roteiro_salvo", "proposta_id = p2 AND roteiro_id = h AND ator_id = u"), "1", "event")
        + expect("count(*) FROM cs_headlines WHERE conversa_id = c", "0", "no headline yet")
    ),
    "salvar_roteiro: a retry is a lookup -- one roteiro, no second uso, no second event, etapa never regresses": (
        SALVO
        + "UPDATE cs_chat_propostas SET fluxo_etapa = 'card_criado' WHERE id = p2;"
        + "r2 := cs_chat_proposta_salvar_roteiro(p2, o, u);"
        + expect("(r2->>'roteiro_id')::uuid = h AND NOT (r2->>'criado')::boolean", "true", "lookup")
        + expect("count(*) FROM cs_roteiros WHERE conversa_id = c", "1", "one roteiro")
        + expect("count(*) FROM cs_estrutura_usos WHERE proposta_id = p2", "2", "usos")
        + expect(evt("roteiro_salvo"), "1", "one event")
        + expect("fluxo_etapa FROM cs_chat_propostas WHERE id = p2", "card_criado", "etapa kept")
    ),
    "salvar_roteiro: a crash after the roteiro INSERT but before proposta.roteiro_id is repaired by the UNIQUE lookup": (
        GRAVAR
        + "PERFORM cs_chat_proposta_reivindicar(p2, o, c, u, 60);"
        + "INSERT INTO cs_roteiros (org_id, marca_id, nome, headline_texto, conversa_id, proposta_id) VALUES (o, m, 'x', 'x', c, p2) RETURNING id INTO h;"
        + "r := cs_chat_proposta_salvar_roteiro(p2, o, u);"
        + expect("(r->>'roteiro_id')::uuid = h", "true", "relinked to the existing row")
        + expect("count(*) FROM cs_roteiros WHERE conversa_id = c", "1", "still one")
    ),
    "salvar_roteiro: refuses a headline proposta, an unclaimed one and a foreign user, writing nothing": (
        GRAVAR
        + "PERFORM cs_chat_proposta_reivindicar(p1, o, c, u, 60);"
        + refuses("PERFORM cs_chat_proposta_salvar_roteiro(p1, o, u)", "proposta_nao_e_roteiro")
        + refuses("PERFORM cs_chat_proposta_salvar_roteiro(p2, o, u)", "proposta_nao_escolhida")
        + "PERFORM cs_chat_proposta_reivindicar(p2, o, c, u, 60);"
        + refuses("PERFORM cs_chat_proposta_salvar_roteiro(p2, o, v_u2)", "proposta_nao_encontrada")
        + refuses("PERFORM cs_chat_proposta_salvar_roteiro(p2, gen_random_uuid(), u)", "proposta_nao_encontrada")
        + expect("count(*) FROM cs_roteiros WHERE conversa_id = c", "0", "no roteiro written")
        + expect(evt("roteiro_salvo"), "0", "no event")
    ),
    # ── salvar_headline, roteiro-first branch ───────────────────────────────────────────────────────────
    "salvar_headline(p_texto): the generated headline (do_roteiro, favorite) linked to proposta + roteiro; etapa; ONE event": (
        SALVO
        + "r := cs_chat_proposta_salvar_headline(p2, o, u, '  O erro que ninguém te conta  ');"
        + expect("(r->>'criada')::boolean", "true", "criada")
        + expect("(texto, modo, favorita, favoritada_em IS NOT NULL, conversa_id = c, proposta_id = p2, created_by = u)::text "
                 "FROM cs_headlines WHERE id = (r->>'headline_id')::uuid",
                 "(\"O erro que ninguém te conta\",do_roteiro,t,t,t,t,t)", "headline")
        + expect("(headline_id = (r->>'headline_id')::uuid, headline_texto)::text FROM cs_roteiros WHERE id = h",
                 "(t,\"O erro que ninguém te conta\")", "roteiro linked")
        + expect("(headline_id = (r->>'headline_id')::uuid, fluxo_etapa)::text FROM cs_chat_propostas WHERE id = p2",
                 "(t,headline_gerada)", "proposta")
        + expect(evt("headline_gerada", "proposta_id = p2 AND roteiro_id = h AND headline_id = (r->>'headline_id')::uuid"), "1", "event")
        + expect("count(*) FROM cs_estrutura_usos WHERE proposta_id = p2", "2", "no extra usos (the roteiro usos stand)")
    ),
    "salvar_headline(p_texto): a retry is a lookup (the FIRST headline wins), no second event, etapa never regresses": (
        SALVO
        + "r := cs_chat_proposta_salvar_headline(p2, o, u, 'Primeira');"
        + "UPDATE cs_chat_propostas SET fluxo_etapa = 'card_criado' WHERE id = p2;"
        + "r2 := cs_chat_proposta_salvar_headline(p2, o, u, 'Segunda');"
        + expect("(r2->>'headline_id') = (r->>'headline_id') AND NOT (r2->>'criada')::boolean", "true", "lookup")
        + expect("count(*) FROM cs_headlines WHERE conversa_id = c", "1", "one headline")
        + expect("texto FROM cs_headlines WHERE conversa_id = c", "Primeira", "first wins")
        + expect(evt("headline_gerada"), "1", "one event")
        + expect("fluxo_etapa FROM cs_chat_propostas WHERE id = p2", "card_criado", "etapa kept")
    ),
    "salvar_headline(p_texto): after headline_falhou the retried headline recovers the flow (falhou -> headline_gerada)": (
        SALVO
        + "UPDATE cs_chat_propostas SET fluxo_etapa = 'falhou', fluxo_erro_codigo = 'headline_invalida' WHERE id = p2;"
        + "r := cs_chat_proposta_salvar_headline(p2, o, u, 'Agora vai');"
        + expect("(fluxo_etapa, fluxo_erro_codigo IS NULL)::text FROM cs_chat_propostas WHERE id = p2", "(headline_gerada,t)", "recovered")
    ),
    "salvar_headline(p_texto): refuses before the roteiro is saved, without a text, and for a foreign user": (
        GRAVAR
        + "PERFORM cs_chat_proposta_reivindicar(p2, o, c, u, 60);"
        + refuses("PERFORM cs_chat_proposta_salvar_headline(p2, o, u, 'H')", "roteiro_nao_salvo")
        + "PERFORM cs_chat_proposta_salvar_roteiro(p2, o, u);"
        + refuses("PERFORM cs_chat_proposta_salvar_headline(p2, o, u, '   ')", "headline_texto_ausente")
        + refuses("PERFORM cs_chat_proposta_salvar_headline(p2, o, u)", "headline_texto_ausente")  # the 3-arg form on a roteiro
        + refuses("PERFORM cs_chat_proposta_salvar_headline(p2, o, v_u2, 'H')", "proposta_nao_encontrada")
        + expect("count(*) FROM cs_headlines WHERE conversa_id = c", "0", "no headline written")
    ),
    # ── salvar_headline, forward branch: the 352 contract kept ──────────────────────────────────────────
    "salvar_headline: the 3-arg form keeps the forward behaviour; the 4-arg form refuses a text for a headline proposta": (
        GRAVAR
        + "PERFORM cs_chat_proposta_reivindicar(p1, o, c, u, 60);"
        + refuses("PERFORM cs_chat_proposta_salvar_headline(p1, o, u, 'outra')", "headline_texto_inesperado")
        + "r := cs_chat_proposta_salvar_headline(p1, o, u);"
        + expect("(texto, modo, favorita)::text FROM cs_headlines WHERE id = (r->>'headline_id')::uuid", "(\"Headline um\",manual,t)", "headline")
        + expect("fluxo_etapa FROM cs_chat_propostas WHERE id = p1", "headline_salva", "etapa")
        + expect(evt("headline_salva", "proposta_id = p1"), "1", "event")
        + "r2 := cs_chat_proposta_salvar_headline(p1, o, u, NULL);"
        + expect("(r2->>'headline_id') = (r->>'headline_id') AND NOT (r2->>'criada')::boolean", "true", "4-arg NULL = lookup")
    ),
    # ── privileges ──────────────────────────────────────────────────────────────────────────────────────
    "access: service_role EXECUTEs the new/changed RPCs, no browser role does; every definer pins its search_path": """
  FOR s IN SELECT unnest(ARRAY[
      'cs_chat_resposta_gravar(jsonb)', 'cs_chat_proposta_salvar_roteiro(uuid,uuid,uuid)',
      'cs_chat_proposta_salvar_headline(uuid,uuid,uuid)', 'cs_chat_proposta_salvar_headline(uuid,uuid,uuid,text)']) LOOP
    IF NOT has_function_privilege('service_role', 'social_wiring.' || s, 'EXECUTE') THEN RAISE EXCEPTION 'service cannot execute %', s; END IF;
    IF has_function_privilege('authenticated', 'social_wiring.' || s, 'EXECUTE') OR has_function_privilege('anon', 'social_wiring.' || s, 'EXECUTE') THEN
      RAISE EXCEPTION 'browser can execute %', s; END IF;
  END LOOP;
  IF has_table_privilege('service_role', 'social_wiring.cs_chat_propostas', 'INSERT')
     OR has_table_privilege('service_role', 'social_wiring.cs_chat_propostas', 'UPDATE') THEN
    RAISE EXCEPTION 'service writes propostas directly'; END IF;
  SELECT count(*) INTO n FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
   WHERE ns.nspname = 'social_wiring' AND p.proname LIKE 'cs\\_chat\\_%' AND p.prosecdef AND p.proconfig::text NOT LIKE '%search_path%';
  IF n <> 0 THEN RAISE EXCEPTION 'unpinned definer functions: %', n; END IF;""",
}


@pytest.fixture(scope="module")
def replay() -> dict:
    steps = [
        {"product": "sw", "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": "sw", "file": "350", "sql": M350.read_text(encoding="utf-8"), "mode": "file", "twice": False},
        {"product": "sw", "file": "352", "sql": M352.read_text(encoding="utf-8"), "mode": "file", "twice": False},
        {"product": "sw", "file": "pre-m6", "sql": PRE_M6, "mode": "file", "twice": False},
        {"product": "sw", "file": "migration", "sql": MIGRATION.read_text(encoding="utf-8"), "mode": "file", "twice": True},
        *(
            {"product": "sw", "file": f"scenario: {name}", "sql": _BASE.replace("{body}", body), "mode": "file", "twice": False}
            for name, body in SCENARIOS.items()
        ),
    ]
    proc = subprocess.run(
        ["node", str(HARNESS)],
        input=json.dumps({"stubs": STUBS.read_text(encoding="utf-8"), "steps": steps}),
        capture_output=True, text=True, cwd=NODE_DIR, timeout=600,
    )
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"PGlite harness produced no verdict: {(proc.stderr or proc.stdout)[-400:]}")
    assert out.get("ok"), out
    return {step["file"]: step for step in out["steps"]}


def test_migration_applies_twice_without_failures(replay):
    for step in ("prelude", "350", "352", "pre-m6", "migration"):
        assert replay[step]["failures"] == [], (step, replay[step]["failures"])


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_scenario(replay, name):
    assert replay[f"scenario: {name}"]["failures"] == [], replay[f"scenario: {name}"]["failures"]


# ── static pins (no database) ────────────────────────────────────────────────────────────────────────────


def _code() -> str:
    return "\n".join(line for line in MIGRATION.read_text(encoding="utf-8").splitlines() if not line.strip().startswith("--"))


def test_every_definer_revokes_and_nothing_is_executable_by_a_browser_role():
    code = _code()
    assert code.count("SECURITY DEFINER") == 4
    assert code.count("FROM PUBLIC, anon, authenticated;") >= 4
    assert "TO authenticated" not in code and "TO anon" not in code


def test_the_migration_is_backward_compatible_with_the_previous_image():
    """N-1 writes headline propostas without tipo and calls the 3-arg salvar_headline: both keep working (pinned on
    PGlite above). Nothing drops/renames/retypes a column; every new NOT NULL column has a default; no backfill UPDATE."""
    code = _code()
    assert " DROP COLUMN " not in code and "RENAME" not in code and "ALTER COLUMN" not in code
    assert "DROP FUNCTION" not in code
    assert "ADD COLUMN IF NOT EXISTS tipo TEXT NOT NULL DEFAULT 'headline'" in code
    assert "cs_chat_proposta_salvar_headline(p_proposta UUID, p_org UUID, p_user UUID)" in code
    assert "UPDATE social_wiring.cs_chat_propostas SET" not in code.split("CREATE OR REPLACE FUNCTION")[0]


def test_the_event_vocabulary_gains_exactly_the_contract_s_five():
    code = _code().replace("\n", " ")
    for tipo in ("roteiro_salvo", "headline_gerando", "headline_gerada", "headline_falhou", "roteiro_invalido"):
        assert f"'{tipo}'" in code, tipo
