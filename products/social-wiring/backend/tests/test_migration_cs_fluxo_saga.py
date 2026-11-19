"""Migration ``cs_fluxo_saga`` (RP-3 of estruturas-contract.md 16.6 / 9.2-9.3) on a REAL Postgres (PGlite).

The prelude is the M6 test's (352's tables + the prod-shaped ``cs_roteiros``), then the REAL 350, 352 and 358 files and
the REAL saga file TWICE (idempotency); the progression RPC's forward-only rule, its once-only event, the ``falhou``
recovery, the terminal ``concluido``, its refusals and its grants are exercised against the result.

Referenced by name (``migration_path``), never by its NNN_ number: integrate renumbers.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from noctusai_lib.testing.migrations import migration_path

from tests.test_migration_cs_roteiro_primeiro import GRAVAR, MIGRATION as M358, PRELUDE, SALVO
from tests.test_migration_cs_unified_chat import (  # the shared harness + SQL helpers (one derivation)
    BACKEND,
    HARNESS,
    M350,
    MIGRATION as M352,
    NODE_DIR,
    STUBS,
    _BASE,
    evt,
    expect,
    refuses,
    sqlstate,
)
from tests.test_migration_cs_unified_chat import pytestmark  # noqa: F401 - same skip when the harness is absent

MIGRATION = migration_path(BACKEND, "cs_fluxo_saga")


def reg(proposta: str, tipo: str, etapa: str = "NULL", erro: str = "NULL", codigo: str = "NULL") -> str:
    return f"r := cs_chat_fluxo_registrar({proposta}, o, u, '{tipo}', {etapa}, {erro}, NULL, NULL, NULL, {codigo});"


#: p1 (a headline proposta) claimed and its headline saved: etapa headline_salva
HEADLINE = GRAVAR + """
  PERFORM cs_chat_proposta_reivindicar(p1, o, c, u, 60);
  PERFORM cs_chat_proposta_salvar_headline(p1, o, u);
"""

ETAPA = "fluxo_etapa FROM cs_chat_propostas WHERE id = {p}"

SCENARIOS: dict[str, str] = {
    "forward: roteiro_criado then card_criado move the etapa, one event each; a retry writes nothing": (
        HEADLINE
        + reg("p1", "roteiro_criado", "'roteiro_criado'")
        + expect("(r->>'mudou')::boolean AND (r->>'registrado')::boolean", "true", "moved")
        + reg("p1", "card_criado", "'card_criado'")
        + reg("p1", "card_criado", "'card_criado'")
        + expect("(r->>'mudou')::boolean OR (r->>'registrado')::boolean", "false", "retry is a no-op")
        + expect(ETAPA.format(p="p1"), "card_criado", "etapa")
        + expect(evt("roteiro_criado", "proposta_id = p1 AND ator_id = u"), "1", "roteiro event")
        + expect(evt("card_criado", "proposta_id = p1"), "1", "card event once")
    ),
    "the etapa never regresses: a late roteiro_criado after card_criado keeps card_criado": (
        HEADLINE
        + reg("p1", "card_criado", "'card_criado'")
        + reg("p1", "roteiro_criado", "'roteiro_criado'")
        + expect(ETAPA.format(p="p1"), "card_criado", "kept")
    ),
    "the roteiro-first etapas rank too: card_criado after headline_gerada moves, roteiro_criado does not": (
        SALVO
        + "PERFORM cs_chat_proposta_salvar_headline(p2, o, u, 'Gerada');"
        + reg("p2", "roteiro_criado", "'roteiro_criado'")
        + expect(ETAPA.format(p="p2"), "headline_gerada", "same rank does not move")
        + reg("p2", "card_criado", "'card_criado'")
        + expect(ETAPA.format(p="p2"), "card_criado", "moved")
        + expect(evt("card_criado", "proposta_id = p2 AND roteiro_id = h AND headline_id IS NOT NULL"), "1", "links from the row")
    ),
    "falhou carries the code once; a forward step recovers and clears it": (
        SALVO
        + reg("p2", "headline_falhou", "'falhou'", "'headline_invalida'", "'headline_invalida'")
        + reg("p2", "headline_falhou", "'falhou'", "'headline_invalida'", "'headline_invalida'")
        + expect("(fluxo_etapa, fluxo_erro_codigo)::text FROM cs_chat_propostas WHERE id = p2", "(falhou,headline_invalida)", "falhou")
        + expect(evt("headline_falhou", "proposta_id = p2"), "1", "once")
        + reg("p2", "card_criado", "'card_criado'")
        + expect("(fluxo_etapa, fluxo_erro_codigo IS NULL)::text FROM cs_chat_propostas WHERE id = p2", "(card_criado,t)", "recovered")
    ),
    "an event without etapa is written once per (tipo, codigo)": (
        SALVO
        + reg("p2", "headline_gerando", codigo="'fluxo-h:a'")
        + reg("p2", "headline_gerando", codigo="'fluxo-h:a'")
        + reg("p2", "headline_gerando", codigo="'fluxo-h:b'")
        + expect(evt("headline_gerando", "proposta_id = p2"), "2", "per codigo")
        + expect(ETAPA.format(p="p2"), "roteiro_salvo", "etapa untouched")
    ),
    "concluido is terminal: a later falhou changes nothing": (
        HEADLINE
        + reg("p1", "fluxo_concluido", "'concluido'")
        + reg("p1", "card_falhou", "'falhou'", "'erro'", "'erro'")
        + expect("(fluxo_etapa, fluxo_erro_codigo IS NULL)::text FROM cs_chat_propostas WHERE id = p1", "(concluido,t)", "terminal")
    ),
    "refusals: unknown tipo/etapa, falhou without a code, a foreign org, an unchosen proposta -- nothing written": (
        HEADLINE
        + refuses("PERFORM cs_chat_fluxo_registrar(p1, o, u, 'inventado', NULL, NULL, NULL, NULL, NULL, NULL)", "evento_invalido")
        + refuses("PERFORM cs_chat_fluxo_registrar(p1, o, u, 'card_criado', 'quase', NULL, NULL, NULL, NULL, NULL)", "etapa_invalida")
        + refuses("PERFORM cs_chat_fluxo_registrar(p1, o, u, 'card_falhou', 'falhou', '  ', NULL, NULL, NULL, NULL)", "erro_obrigatorio")
        + refuses("PERFORM cs_chat_fluxo_registrar(p1, gen_random_uuid(), u, 'card_criado', 'card_criado', NULL, NULL, NULL, NULL, NULL)",
                  "proposta_nao_encontrada")
        + refuses("PERFORM cs_chat_fluxo_registrar(p2, o, u, 'card_criado', 'card_criado', NULL, NULL, NULL, NULL, NULL)",
                  "proposta_nao_escolhida")
        + expect(evt("card_criado"), "0", "no event")
        + expect(ETAPA.format(p="p1"), "headline_salva", "etapa kept")
    ),
    "cs_roteiros.estrutura_ids defaults to empty and holds at most 3": (
        "INSERT INTO cs_roteiros (org_id, marca_id, nome, headline_texto) VALUES (o, m, 'a', 'a') RETURNING id INTO h;"
        + expect("cardinality(estrutura_ids) FROM cs_roteiros WHERE id = h", "0", "default")
        + "UPDATE cs_roteiros SET estrutura_ids = ARRAY[e1, e2, e3]::uuid[] WHERE id = h;"
        + sqlstate("UPDATE cs_roteiros SET estrutura_ids = ARRAY[e1, e2, e3, e4]::uuid[] WHERE id = h", "check_violation")
    ),
    "access: service_role EXECUTEs the RPC, no browser role does; the definer pins its search_path": """
  s := 'social_wiring.cs_chat_fluxo_registrar(uuid,uuid,uuid,text,text,text,uuid,uuid,uuid,text)';
  IF NOT has_function_privilege('service_role', s, 'EXECUTE') THEN RAISE EXCEPTION 'service cannot execute'; END IF;
  IF has_function_privilege('authenticated', s, 'EXECUTE') OR has_function_privilege('anon', s, 'EXECUTE') THEN
    RAISE EXCEPTION 'browser can execute'; END IF;
  SELECT count(*) INTO n FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
   WHERE ns.nspname = 'social_wiring' AND p.proname = 'cs_chat_fluxo_registrar' AND p.prosecdef
     AND p.proconfig::text LIKE '%search_path%';
  IF n <> 1 THEN RAISE EXCEPTION 'definer not pinned'; END IF;""",
}


@pytest.fixture(scope="module")
def replay() -> dict:
    steps = [
        {"product": "sw", "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": "sw", "file": "350", "sql": M350.read_text(encoding="utf-8"), "mode": "file", "twice": False},
        {"product": "sw", "file": "352", "sql": M352.read_text(encoding="utf-8"), "mode": "file", "twice": False},
        {"product": "sw", "file": "358", "sql": M358.read_text(encoding="utf-8"), "mode": "file", "twice": False},
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
    for step in ("prelude", "350", "352", "358", "migration"):
        assert replay[step]["failures"] == [], (step, replay[step]["failures"])


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_scenario(replay, name):
    assert replay[f"scenario: {name}"]["failures"] == [], replay[f"scenario: {name}"]["failures"]


def _code() -> str:
    return "\n".join(line for line in MIGRATION.read_text(encoding="utf-8").splitlines() if not line.strip().startswith("--"))


def test_the_definer_revokes_and_nothing_is_executable_by_a_browser_role():
    code = _code()
    assert code.count("SECURITY DEFINER") == 1
    assert "FROM PUBLIC, anon, authenticated;" in code
    assert "TO authenticated" not in code and "TO anon" not in code


def test_the_migration_is_backward_compatible_with_the_previous_image():
    code = _code()
    assert " DROP COLUMN " not in code and "RENAME" not in code and "ALTER COLUMN" not in code
    assert "DROP FUNCTION" not in code
    assert "ADD COLUMN IF NOT EXISTS estrutura_ids UUID[] NOT NULL DEFAULT '{}'::uuid[]" in code
    assert "lock_timeout" in code
