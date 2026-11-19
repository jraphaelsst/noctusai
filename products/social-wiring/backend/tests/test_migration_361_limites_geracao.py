"""Migration 361 (per-org daily generation limits) on a REAL Postgres (PGlite).

Pins what a mock cannot show: `cs_limite_geracao_definir` writes the `public.org_settings` override AND its
`cs_limite_geracao_eventos` row in ONE transaction, records the old and new value and who, writes no event for a
no-op, refuses an unknown key / a value < 1, and the event table is append-only. The SQL key list must equal the
Python `LIMITES` table (the two halves of one contract). Same harness as `test_migration_338_roteiro_ciclo.py`.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from noctusai_lib.testing.migrations import migration_path
from noctusai_lib.testing.pglite import pglite_replay_skipif

from app.modules.media_creation.limites_geracao import CHAVES

ROOT = Path(__file__).resolve().parents[4]
NODE_DIR = ROOT / "mcp" / "noctusai" / "node"
HARNESS = NODE_DIR / "migration_replay" / "replay.mjs"
STUBS = NODE_DIR / "migration_replay" / "stubs.sql"
MIGRATION = migration_path(Path(__file__).resolve().parents[1], "cs_limites_geracao")

O = "00000000-0000-0000-0000-00000000000f"
O2 = "00000000-0000-0000-0000-0000000000f2"
USER = "00000000-0000-0000-0000-0000000000a1"

#: The two core tables 361 reads/writes (core 001/002, only the columns it touches).
PRELUDE = f"""
CREATE SCHEMA IF NOT EXISTS social_wiring;
CREATE TABLE IF NOT EXISTS public.organizations (id uuid PRIMARY KEY);
CREATE TABLE IF NOT EXISTS public.org_settings (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  org_id uuid NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
  key text NOT NULL, value text NOT NULL, is_secret boolean DEFAULT false, updated_at timestamptz DEFAULT now(),
  UNIQUE (org_id, key));
INSERT INTO public.organizations (id) VALUES ('{O}'), ('{O2}');
"""

_DO = """
DO $$
DECLARE n int; r jsonb; v text;
BEGIN
  {body}
END $$;
"""


def _count(where: str, expect: int, what: str) -> str:
    return (f"SELECT count(*) INTO n FROM social_wiring.cs_limite_geracao_eventos WHERE {where}; "
            f"IF n <> {expect} THEN RAISE EXCEPTION '{what}: got %', n; END IF;")


def _refused(stmt: str, what: str) -> str:
    return (f"BEGIN {stmt}; RAISE EXCEPTION '{what}: not refused'; "
            f"EXCEPTION WHEN invalid_parameter_value OR insufficient_privilege THEN NULL; END;")


SCENARIOS: dict[str, str] = {
    "set writes the override and one event with who, old and new": f"""
      r := social_wiring.cs_limite_geracao_definir('{O}', 'roteiros_dia_usuario', 50, '{USER}');
      SELECT value INTO v FROM public.org_settings WHERE org_id = '{O}' AND key = 'roteiros_dia_usuario';
      IF v <> '50' THEN RAISE EXCEPTION 'override not written: %', v; END IF;
      IF (r->>'mudou')::boolean IS NOT TRUE OR r->'anterior' <> 'null'::jsonb THEN RAISE EXCEPTION 'answer %', r; END IF;
      {_count(f"org_id = '{O}' AND chave = 'roteiros_dia_usuario' AND evento = 'limite_definido' AND valor_anterior IS NULL AND valor_novo = 50 AND ator_id = '{USER}'", 1, "first event")}
    """,
    "a raise records the previous value": f"""
      PERFORM social_wiring.cs_limite_geracao_definir('{O}', 'legendas_dia_usuario', 60, '{USER}');
      r := social_wiring.cs_limite_geracao_definir('{O}', 'legendas_dia_usuario', 90, '{USER}');
      IF (r->>'anterior')::int <> 60 THEN RAISE EXCEPTION 'anterior %', r; END IF;
      {_count(f"org_id = '{O}' AND chave = 'legendas_dia_usuario' AND valor_anterior = 60 AND valor_novo = 90", 1, "raise event")}
    """,
    "the same value again is a no-op (no event)": f"""
      PERFORM social_wiring.cs_limite_geracao_definir('{O}', 'chat_mensagens_dia_org', 800, NULL);
      r := social_wiring.cs_limite_geracao_definir('{O}', 'chat_mensagens_dia_org', 800, NULL);
      IF (r->>'mudou')::boolean THEN RAISE EXCEPTION 'no-op reported as a change'; END IF;
      {_count(f"org_id = '{O}' AND chave = 'chat_mensagens_dia_org'", 1, "no-op wrote an event")}
    """,
    "reset deletes the override and records limite_restaurado": f"""
      PERFORM social_wiring.cs_limite_geracao_definir('{O}', 'chat_mensagens_dia_usuario', 300, '{USER}');
      PERFORM social_wiring.cs_limite_geracao_definir('{O}', 'chat_mensagens_dia_usuario', NULL, '{USER}');
      SELECT count(*) INTO n FROM public.org_settings WHERE org_id = '{O}' AND key = 'chat_mensagens_dia_usuario';
      IF n <> 0 THEN RAISE EXCEPTION 'override survived the reset'; END IF;
      {_count(f"org_id = '{O}' AND chave = 'chat_mensagens_dia_usuario' AND evento = 'limite_restaurado' AND valor_anterior = 300 AND valor_novo IS NULL", 1, "reset event")}
      PERFORM social_wiring.cs_limite_geracao_definir('{O}', 'chat_mensagens_dia_usuario', NULL, '{USER}');
      {_count(f"org_id = '{O}' AND chave = 'chat_mensagens_dia_usuario'", 2, "a reset of nothing wrote an event")}
    """,
    "one org never touches another": f"""
      PERFORM social_wiring.cs_limite_geracao_definir('{O2}', 'headline_lotes_dia_usuario', 45, NULL);
      SELECT count(*) INTO n FROM public.org_settings WHERE org_id = '{O}' AND key = 'headline_lotes_dia_usuario';
      IF n <> 0 THEN RAISE EXCEPTION 'cross-org write'; END IF;
    """,
    "unknown key and values below 1 are refused, nothing written": f"""
      {_refused(f"PERFORM social_wiring.cs_limite_geracao_definir('{O}', 'qualquer_coisa', 5, NULL)", "unknown key")}
      {_refused(f"PERFORM social_wiring.cs_limite_geracao_definir('{O}', 'roteiros_dia_usuario', 0, NULL)", "zero")}
      {_refused(f"PERFORM social_wiring.cs_limite_geracao_definir('{O}', 'roteiros_dia_usuario', -3, NULL)", "negative")}
      SELECT count(*) INTO n FROM public.org_settings WHERE key = 'qualquer_coisa';
      IF n <> 0 THEN RAISE EXCEPTION 'unknown key written'; END IF;
    """,
    "the event table is append-only": f"""
      PERFORM social_wiring.cs_limite_geracao_definir('{O}', 'headlines_sugeridas_por_dia_marca', 7, NULL);
      {_refused("UPDATE social_wiring.cs_limite_geracao_eventos SET valor_novo = 1", "update")}
      {_refused("DELETE FROM social_wiring.cs_limite_geracao_eventos", "delete")}
    """,
}


@pytest.fixture(scope="module")
def replay() -> dict:
    steps = [
        {"product": "sw", "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": "sw", "file": "migration", "sql": MIGRATION.read_text(encoding="utf-8"), "mode": "file", "twice": True},
        *({"product": "sw", "file": f"scenario: {name}", "sql": _DO.replace("{body}", body), "mode": "file", "twice": False}
          for name, body in SCENARIOS.items()),
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


@pytest.mark.skipif(**pglite_replay_skipif())
def test_migration_applies_twice_without_failures(replay):
    assert replay["prelude"]["failures"] == [], replay["prelude"]["failures"]
    assert replay["migration"]["failures"] == [], replay["migration"]["failures"]


@pytest.mark.skipif(**pglite_replay_skipif())
@pytest.mark.parametrize("name", list(SCENARIOS))
def test_scenario(replay, name):
    assert replay[f"scenario: {name}"]["failures"] == [], replay[f"scenario: {name}"]["failures"]


def test_the_sql_key_lists_equal_the_python_table():
    """The event CHECK and the function's allow-list name exactly the keys `LIMITES` resolves."""
    sql = MIGRATION.read_text(encoding="utf-8")
    listas = re.findall(r"IN \(\s*('headline_lotes_dia_usuario'[^)]*)\)", sql)
    assert len(listas) == 2, listas
    for lista in listas:
        assert set(re.findall(r"'([a-z_]+)'", lista)) == set(CHAVES)


def test_the_write_is_service_role_only():
    code = MIGRATION.read_text(encoding="utf-8")
    assert "SECURITY DEFINER" in code
    assert "REVOKE ALL ON FUNCTION social_wiring.cs_limite_geracao_definir(UUID, TEXT, INTEGER, UUID) FROM PUBLIC, anon, authenticated;" in code
    assert "GRANT EXECUTE ON FUNCTION social_wiring.cs_limite_geracao_definir(UUID, TEXT, INTEGER, UUID) TO service_role;" in code
    assert "REVOKE ALL ON social_wiring.cs_limite_geracao_eventos FROM PUBLIC, anon, authenticated;" in code
