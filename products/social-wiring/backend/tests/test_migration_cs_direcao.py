"""Migration 373 (the Diretor de Edição trigger data) on a REAL Postgres (PGlite): the route key, the event vocabulary and
the idempotent writer `cs_direcao_evento`. Referenced by name (``migration_path``), never by its NNN_ number.

The prelude holds the minimal prod-shaped ancestors (cs_posts with 362's route CHECK, cs_post_eventos with a narrower CHECK +
342's append-only guard); the REAL file is applied twice (idempotency) and the scenarios run against the result."""
from __future__ import annotations

import json
import re
import subprocess

import pytest

from noctusai_lib.testing.migrations import migration_path

from tests.test_migration_cs_unified_chat import BACKEND, HARNESS, NODE_DIR, STUBS, expect, refuses, sqlstate
from tests.test_migration_cs_unified_chat import pytestmark  # noqa: F401 - same skip when the harness is absent

FILE = migration_path(BACKEND, "cs_direcao_producao")

PRELUDE = """
CREATE SCHEMA IF NOT EXISTS social_wiring;
CREATE TABLE IF NOT EXISTS public.organizations (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), nome text, slug text);
SET search_path = social_wiring, public;
CREATE TABLE cs_posts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL, titulo text NOT NULL DEFAULT 't',
  criacao_rota text,
  CONSTRAINT cs_posts_criacao_rota_check CHECK (criacao_rota IN ('reel_narrado', 'carrossel', 'estatico', 'avatar', 'gravado')));
CREATE TABLE cs_post_eventos (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL, post_id uuid NOT NULL,
  asset_id uuid, publicacao_id uuid, tipo text NOT NULL, de text, para text,
  dados jsonb NOT NULL DEFAULT '{}'::jsonb, ator_id uuid, criado_em timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT cs_post_eventos_tipo_check CHECK (tipo IN ('passo_iniciado', 'criacao_enfileirada')));
CREATE FUNCTION cs_post_eventos_imutavel() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'append-only' USING ERRCODE = 'insufficient_privilege'; END; $$;
CREATE TRIGGER cs_post_eventos_imutavel BEFORE UPDATE OR DELETE ON cs_post_eventos
  FOR EACH ROW EXECUTE FUNCTION cs_post_eventos_imutavel();
"""

_BASE = """
SET search_path = social_wiring, public;
DO $$
DECLARE
  o uuid := gen_random_uuid(); o2 uuid := gen_random_uuid(); p uuid; r boolean; n int;
BEGIN
  INSERT INTO cs_posts (org_id) VALUES (o) RETURNING id INTO p;
  {body}
END $$;
"""

SCENARIOS: dict[str, str] = {
    "the route key reel_dirigido is admitted, an unknown one still is not": f"""
  UPDATE cs_posts SET criacao_rota = 'reel_dirigido' WHERE id = p;
  UPDATE cs_posts SET criacao_rota = 'reel_narrado' WHERE id = p;
  {sqlstate("UPDATE cs_posts SET criacao_rota = 'reel_inventado' WHERE id = p", "check_violation")}
""",
    "direcao_solicitada is written ONCE per chave; the second call returns false and writes nothing": f"""
  r := cs_direcao_evento(o, p, 'direcao_solicitada', 'k1', '{{"rota":"reel_dirigido"}}'::jsonb, NULL);
  {expect("r", "true", "first call writes")}
  r := cs_direcao_evento(o, p, 'direcao_solicitada', 'k1', '{{}}'::jsonb, NULL);
  {expect("r", "false", "same chave is a no-op")}
  r := cs_direcao_evento(o, p, 'direcao_solicitada', 'k2', '{{}}'::jsonb, NULL);
  {expect("r", "true", "a new chave (edited roteiro) is a new request")}
  {expect("count(*) FROM cs_post_eventos WHERE post_id = p AND tipo = 'direcao_solicitada'", "2", "two rows")}
  {expect("dados ->> 'rota' FROM cs_post_eventos WHERE post_id = p AND dados ->> 'chave' = 'k1'", "reel_dirigido", "dados kept")}
""",
    "direcao_recusada is always written (no idempotency) and carries the chave": f"""
  r := cs_direcao_evento(o, p, 'direcao_recusada', 'k1', '{{"codigo":"rota_nao_implementada"}}'::jsonb, NULL);
  r := cs_direcao_evento(o, p, 'direcao_recusada', 'k1', '{{"codigo":"cota"}}'::jsonb, NULL);
  {expect("count(*) FROM cs_post_eventos WHERE post_id = p AND tipo = 'direcao_recusada'", "2", "both recorded")}
  {expect("dados ->> 'chave' FROM cs_post_eventos WHERE post_id = p AND tipo = 'direcao_recusada' LIMIT 1", "k1", "chave kept")}
""",
    "the writer refuses a foreign org, a foreign tipo, a blank chave and non-object dados; events stay append-only": f"""
  {refuses("PERFORM cs_direcao_evento(o2, p, 'direcao_solicitada', 'k', '{}'::jsonb, NULL)", "post_nao_encontrado")}
  {refuses("PERFORM cs_direcao_evento(o, p, 'criacao_enfileirada', 'k', '{}'::jsonb, NULL)", "tipo_invalido")}
  {refuses("PERFORM cs_direcao_evento(o, p, 'direcao_solicitada', '  ', '{}'::jsonb, NULL)", "chave_invalida")}
  {refuses("PERFORM cs_direcao_evento(o, p, 'direcao_solicitada', 'k', '[]'::jsonb, NULL)", "dados_invalidos")}
  PERFORM cs_direcao_evento(o, p, 'direcao_solicitada', 'k', '{{}}'::jsonb, NULL);
  {sqlstate("UPDATE cs_post_eventos SET dados = '{}'::jsonb WHERE post_id = p", "insufficient_privilege")}
  {sqlstate("DELETE FROM cs_post_eventos WHERE post_id = p", "insufficient_privilege")}
""",
}


@pytest.fixture(scope="module")
def replay() -> dict:
    steps = [{"product": "sw", "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False}]
    steps.append({"product": "sw", "file": "373", "sql": FILE.read_text(encoding="utf-8"), "mode": "file", "twice": True})
    steps += [
        {"product": "sw", "file": f"scenario: {name}", "sql": _BASE.replace("{body}", body), "mode": "file", "twice": False}
        for name, body in SCENARIOS.items()
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
    assert replay["prelude"]["failures"] == []
    assert replay["373"]["failures"] == [], replay["373"]["failures"]


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_scenario(replay, name):
    assert replay[f"scenario: {name}"]["failures"] == [], replay[f"scenario: {name}"]["failures"]


def _code(path=FILE) -> str:
    return "\n".join(l for l in path.read_text(encoding="utf-8").splitlines() if not l.strip().startswith("--"))


def test_backward_compatible_and_not_executable_by_a_browser_role():
    code = _code()
    assert " DROP COLUMN " not in code and "RENAME" not in code and "DROP TABLE" not in code and "DROP FUNCTION" not in code
    assert "TO authenticated" not in code and "TO anon" not in code
    assert "FROM PUBLIC, anon, authenticated" in code and "TO service_role" in code


def _vocabulario(code: str) -> set[str]:
    corpo = code.split("CHECK (tipo IN (")[1].split(")) NOT VALID")[0]
    return set(re.findall(r"'([a-z_]+)'", corpo))


def test_the_event_vocabulary_keeps_364_s_names_and_adds_exactly_the_two_direcao_events():
    antes = _vocabulario(_code(migration_path(BACKEND, "cs_post_eventos_criacao")))
    depois = _vocabulario(_code())
    assert antes <= depois and depois - antes == {"direcao_solicitada", "direcao_recusada"}
