"""Migration 367 (criação projection + its events, one transaction),
replayed on a real Postgres (PGlite) on top of 362-366, twice, plus behaviour scenarios.

Shares the harness of ``test_migration_cs_criacao`` (one derivation of the prelude, the stubs and the SQL helpers).
"""
from __future__ import annotations

import json
import subprocess

import pytest

from noctusai_lib.testing.migrations import migration_path

from tests.test_migration_cs_criacao import _BASE, FILES, NAMES, PRELUDE
from tests.test_migration_cs_unified_chat import (
    BACKEND,
    HARNESS,
    NODE_DIR,
    STUBS,
    expect,
    sqlstate,
)
from tests.test_migration_cs_unified_chat import pytestmark  # noqa: F401 - same skip when the harness is absent

NEW = ("cs_post_criacao_projetar",)
NEW_FILES = {n: migration_path(BACKEND, n) for n in NEW}

SCENARIOS: dict[str, str] = {
    "367: projection + events in one call; idempotent; falha only with falhou; somente_de gates": (
        """
  r := cs_post_criacao_projetar(o, p, 'na_fila', NULL,
         '[{"tipo":"criacao_enfileirada","dados":{"rota":"reel_narrado"}}]'::jsonb, NULL);
  IF NOT (r->>'mudou')::boolean THEN RAISE EXCEPTION 'first move: %', r; END IF;
  r := cs_post_criacao_projetar(o, p, 'na_fila', NULL,
         '[{"tipo":"criacao_enfileirada","dados":{}}]'::jsonb, NULL);
  IF (r->>'mudou')::boolean THEN RAISE EXCEPTION 'replay must be a no-op: %', r; END IF;
  """
        + expect("count(*) FROM cs_post_eventos WHERE post_id = p AND tipo = 'criacao_enfileirada'", "1", "no double event")
        + expect("(de, para)::text FROM cs_post_eventos WHERE post_id = p AND tipo = 'criacao_enfileirada'", '(,na_fila)', "de/para")
        + """
  r := cs_post_criacao_projetar(o, p, 'gerando', NULL, '[]'::jsonb, ARRAY['na_fila']);
  IF NOT (r->>'mudou')::boolean THEN RAISE EXCEPTION 'na_fila -> gerando: %', r; END IF;
  r := cs_post_criacao_projetar(o, p, 'falhou', 'cota', '[]'::jsonb, NULL);
  """
        + expect("criacao_estado || '/' || falha_codigo FROM cs_posts WHERE id = p", "falhou/cota", "failure code shown")
        + """
  r := cs_post_criacao_projetar(o, p, 'gerando', NULL, '[]'::jsonb, ARRAY['na_fila']);
  IF (r->>'mudou')::boolean THEN RAISE EXCEPTION 'gerando must not overwrite falhou: %', r; END IF;
  r := cs_post_criacao_projetar(o, p, 'aguardando_aprovacao_midia', NULL,
         '[{"tipo":"criacao_concluida","dados":{}},{"tipo":"card_movido_automaticamente","dados":{"motivo":"auto:criacao_concluida"}}]'::jsonb, NULL);
  """
        + expect("criacao_estado || '/' || coalesce(falha_codigo, '-') FROM cs_posts WHERE id = p",
                 "aguardando_aprovacao_midia/-", "code cleared when leaving falhou")
        + expect("count(*) FROM cs_post_eventos WHERE post_id = p AND tipo IN ('criacao_concluida', 'card_movido_automaticamente')",
                 "2", "both events, same call")
        + sqlstate("SELECT cs_post_criacao_projetar(o, p, 'falhou', NULL, '[]'::jsonb, NULL)", "raise_exception")
        + sqlstate("SELECT cs_post_criacao_projetar(o, p, 'inventado', NULL, '[]'::jsonb, NULL)", "raise_exception")
        + sqlstate("SELECT cs_post_criacao_projetar(o, gen_random_uuid(), 'na_fila', NULL, '[]'::jsonb, NULL)", "raise_exception")
        + sqlstate("SELECT cs_post_criacao_projetar(o, p, 'na_fila', NULL, '[{\"tipo\":\"evento_inventado\"}]'::jsonb, NULL)", "check_violation")
    ),
    "367: only service_role executes it": """
  IF NOT has_function_privilege('service_role', 'social_wiring.cs_post_criacao_projetar(uuid,uuid,text,text,jsonb,text[])', 'EXECUTE') THEN
    RAISE EXCEPTION 'service cannot execute'; END IF;
  IF has_function_privilege('authenticated', 'social_wiring.cs_post_criacao_projetar(uuid,uuid,text,text,jsonb,text[])', 'EXECUTE')
     OR has_function_privilege('anon', 'social_wiring.cs_post_criacao_projetar(uuid,uuid,text,text,jsonb,text[])', 'EXECUTE') THEN
    RAISE EXCEPTION 'browser executes the definer'; END IF;
""",
}


@pytest.fixture(scope="module")
def replay() -> dict:
    steps = [{"product": "sw", "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False}]
    steps += [{"product": "sw", "file": n, "sql": FILES[n].read_text(encoding="utf-8"), "mode": "file", "twice": True} for n in NAMES]
    steps += [
        {"product": "sw", "file": n, "sql": NEW_FILES[n].read_text(encoding="utf-8"), "mode": "file", "twice": True} for n in NEW
    ]
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


@pytest.mark.parametrize("name", NEW)
def test_new_migrations_apply_twice_without_failures(replay, name):
    assert replay[name]["failures"] == [], (name, replay[name]["failures"])


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_scenario(replay, name):
    assert replay[f"scenario: {name}"]["failures"] == [], replay[f"scenario: {name}"]["failures"]


@pytest.mark.parametrize("name", NEW)
def test_new_functions_pin_search_path_and_never_grant_a_browser_role(name):
    code = "\n".join(l for l in NEW_FILES[name].read_text(encoding="utf-8").splitlines() if not l.strip().startswith("--"))
    assert "TO authenticated" not in code and "TO anon" not in code
    if "SECURITY DEFINER" in code:
        assert "SET search_path" in code
