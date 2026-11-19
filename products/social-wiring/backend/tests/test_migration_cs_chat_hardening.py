"""Migration ``cs_chat_hardening`` (prod findings + agents-security audit, 2026-11-19) on a REAL Postgres (PGlite).

The prelude is the M6 test's (352's tables + the prod-shaped ``cs_roteiros``); the REAL 350, 352, 358 and 360 files run,
then rows the N-1 image wrote BEFORE this migration (user messages without a ledger row, a roteiro saved from a roteiro
proposta with ``estrutura_ids = {}``), then the REAL file TWICE (idempotency). Pinned against the result:

* every user message records ``mensagem_enviada`` in the same INSERT, and deleting the conversation never removes it
  (the daily cap's source: delete-and-repeat no longer resets it); the backfill covers the pre-migration messages once;
* ``cs_chat_proposta_salvar_roteiro`` writes ``cs_roteiros.estrutura_ids`` (principal first); the pre-migration roteiro
  is backfilled;
* the ledger accepts ``mensagem_enviada`` / ``headline_invalida`` and keeps refusing anything else.

Referenced by name (``migration_path``), never by its NNN_ number: integrate renumbers.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from noctusai_lib.testing.migrations import migration_path

from tests.test_migration_cs_fluxo_saga import MIGRATION as M360
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

MIGRATION = migration_path(BACKEND, "cs_chat_hardening")

_ORG, _MARCA = "'00000000-0000-0000-0000-0000000000f0'", "'00000000-0000-0000-0000-0000000000f1'"
_CONV, _USER = "'00000000-0000-0000-0000-0000000000c1'", "'00000000-0000-0000-0000-0000000000b1'"
_PROP = "'00000000-0000-0000-0000-0000000000d1'"

#: Written by the N-1 image BEFORE this migration: two user messages (no ledger row) and a roteiro proposta citing two
#: Estruturas, chosen and saved by the 358 RPC (estrutura_ids stays {}).
PRE = f"""
SET search_path = social_wiring, public;
DO $$
DECLARE pf uuid; ea uuid; eb uuid; msg uuid; r jsonb;
BEGIN
  INSERT INTO cs_perfis_monitorados (handle, nome) VALUES ('pre.370', 'Pre') RETURNING id INTO pf;
  INSERT INTO cs_estruturas (perfil_id, formula_headline, status, origem) VALUES (pf, 'fa', 'rascunho', 'manual') RETURNING id INTO ea;
  INSERT INTO cs_estruturas (perfil_id, formula_headline, status, origem) VALUES (pf, 'fb', 'rascunho', 'manual') RETURNING id INTO eb;
  INSERT INTO cs_chat_conversas (id, org_id, marca_id, user_id, agente, titulo)
    VALUES ({_CONV}, {_ORG}, {_MARCA}, {_USER}, 'unificado', 'pre');
  INSERT INTO cs_chat_mensagens (org_id, conversa_id, role, conteudo, created_at)
    VALUES ({_ORG}, {_CONV}, 'user', 'antes 1', now() - interval '2 hours'), ({_ORG}, {_CONV}, 'user', 'antes 2', now());
  INSERT INTO cs_chat_mensagens (org_id, conversa_id, role, conteudo) VALUES ({_ORG}, {_CONV}, 'assistant', 'x') RETURNING id INTO msg;
  INSERT INTO cs_chat_propostas (id, org_id, marca_id, conversa_id, mensagem_id, ordem, texto, tipo, titulo, formato)
    VALUES ({_PROP}, {_ORG}, {_MARCA}, {_CONV}, msg, 1, 'Fala um.', 'roteiro', 'Pré', 'reels');
  INSERT INTO cs_chat_proposta_estruturas (proposta_id, estrutura_id, ordem, principal)
    VALUES ({_PROP}, eb, 2, false), ({_PROP}, ea, 1, true);
  PERFORM cs_chat_proposta_reivindicar({_PROP}, {_ORG}, {_CONV}, {_USER}, 60);
  r := cs_chat_proposta_salvar_roteiro({_PROP}, {_ORG}, {_USER});
  IF (SELECT cardinality(estrutura_ids) FROM cs_roteiros WHERE proposta_id = {_PROP}) <> 0 THEN
    RAISE EXCEPTION 'pre-370 premise: the 358 RPC must leave estrutura_ids empty';
  END IF;
END $$;
"""

ENVIADAS = "(SELECT count(*) FROM cs_fluxo_eventos WHERE tipo = 'mensagem_enviada' AND {w})"

SCENARIOS: dict[str, str] = {
    "a user message records mensagem_enviada (who / which message / no content) in the same INSERT": (
        expect(ENVIADAS.format(w="org_id = o AND mensagem_id = mu AND ator_id = u AND marca_id = m AND conversa_id = c"),
               "1", "the base message ledger row")
        + "INSERT INTO cs_chat_mensagens (org_id, conversa_id, role, conteudo) VALUES (o, c, 'user', 'outra'), (o, c, 'assistant', 'resp');"
        + expect(ENVIADAS.format(w="org_id = o"), "2", "assistant messages are not counted")
        + expect("count(*) FROM cs_fluxo_eventos WHERE org_id = o AND tipo = 'mensagem_enviada' AND codigo IS NULL "
                 "AND contagem IS NULL", "2", "content-free")
    ),
    "deleting the conversation (messages hard-deleted) keeps the count: delete-and-repeat never resets the cap": (
        "INSERT INTO cs_chat_mensagens (org_id, conversa_id, role, conteudo) VALUES (o, c, 'user', 'dois'), (o, c, 'user', 'tres');"
        + "DELETE FROM cs_chat_mensagens WHERE conversa_id = c;"
        + "DELETE FROM cs_chat_conversas WHERE id = c;"
        + expect("count(*) FROM cs_chat_mensagens WHERE org_id = o", "0", "messages gone")
        + expect(ENVIADAS.format(w="org_id = o AND ator_id = u AND created_at >= now() - interval '24 hours'"), "3", "count kept")
    ),
    "one ledger row per message: a second mensagem_enviada for the same message is refused": (
        sqlstate("INSERT INTO cs_fluxo_eventos (org_id, marca_id, conversa_id, mensagem_id, ator_id, tipo) "
                 "VALUES (o, m, c, mu, u, 'mensagem_enviada')", "unique_violation")
    ),
    "the ledger accepts mensagem_enviada / headline_invalida, refuses unknown tipos and stays append-only": (
        "INSERT INTO cs_fluxo_eventos (org_id, marca_id, conversa_id, tipo, contagem) VALUES (o, m, c, 'headline_invalida', 2), "
        "(o, m, c, 'publicacao_invalida', 1), (o, m, c, 'opcoes_selecionadas', 3);"
        + sqlstate("INSERT INTO cs_fluxo_eventos (org_id, marca_id, conversa_id, tipo) VALUES (o, m, c, 'inventado')", "check_violation")
        + refuses("UPDATE cs_fluxo_eventos SET tipo = 'headline_invalida' WHERE mensagem_id = mu",
                  "cs_fluxo_eventos_imutavel: cs_fluxo_eventos is append-only (UPDATE refused)")
    ),
    "the pre-migration user messages were backfilled once, with their own created_at": (
        expect(ENVIADAS.format(w=f"conversa_id = {_CONV} AND ator_id = {_USER}"), "2", "two, not four (ran twice)")
        + expect(ENVIADAS.format(w=f"conversa_id = {_CONV} AND created_at < now() - interval '1 hour'"), "1", "own created_at")
    ),
    "salvar_roteiro writes estrutura_ids, principal first": (
        SALVO
        + expect("estrutura_ids = ARRAY[e2, e3] FROM cs_roteiros WHERE id = h", "true", "principal first")
        + expect("(r->>'criado')::boolean", "true", "criado")
    ),
    "salvar_roteiro: a retry is still a lookup and keeps the Estruturas": (
        SALVO
        + "r2 := cs_chat_proposta_salvar_roteiro(p2, o, u);"
        + expect("(r2->>'roteiro_id')::uuid = h AND NOT (r2->>'criado')::boolean", "true", "lookup")
        + expect("estrutura_ids = ARRAY[e2, e3] FROM cs_roteiros WHERE id = h", "true", "kept")
        + expect(evt("roteiro_salvo"), "1", "one event")
    ),
    "salvar_roteiro: the crash-repair lookup fills an empty estrutura_ids": (
        GRAVAR
        + "PERFORM cs_chat_proposta_reivindicar(p2, o, c, u, 60);"
        + "INSERT INTO cs_roteiros (org_id, marca_id, nome, headline_texto, conversa_id, proposta_id) VALUES (o, m, 'x', 'x', c, p2) RETURNING id INTO h;"
        + "r := cs_chat_proposta_salvar_roteiro(p2, o, u);"
        + expect("(r->>'roteiro_id')::uuid = h", "true", "relinked")
        + expect("estrutura_ids = ARRAY[e2, e3] FROM cs_roteiros WHERE id = h", "true", "filled")
    ),
    "salvar_roteiro: the refusals are unchanged": (
        GRAVAR
        + refuses("PERFORM cs_chat_proposta_salvar_roteiro(p2, o, u)", "proposta_nao_escolhida")
        + "PERFORM cs_chat_proposta_reivindicar(p1, o, c, u, 60);"
        + refuses("PERFORM cs_chat_proposta_salvar_roteiro(p1, o, u)", "proposta_nao_e_roteiro")
        + expect("count(*) FROM cs_roteiros WHERE conversa_id = c", "0", "nothing written")
    ),
    "the roteiro saved before the migration was backfilled from its proposta (principal first)": (
        expect(f"estrutura_ids = (SELECT array_agg(estrutura_id ORDER BY ordem) FROM cs_chat_proposta_estruturas "
               f"WHERE proposta_id = {_PROP}) AND cardinality(estrutura_ids) = 2 FROM cs_roteiros WHERE proposta_id = {_PROP}",
               "true", "backfilled")
    ),
    "access: service_role EXECUTEs salvar_roteiro, no browser role does; the trigger function is not callable by one": """
  IF NOT has_function_privilege('service_role', 'social_wiring.cs_chat_proposta_salvar_roteiro(uuid,uuid,uuid)', 'EXECUTE') THEN
    RAISE EXCEPTION 'service cannot execute salvar_roteiro'; END IF;
  FOR s IN SELECT unnest(ARRAY['cs_chat_proposta_salvar_roteiro(uuid,uuid,uuid)', 'cs_chat_mensagem_enviada()']) LOOP
    IF has_function_privilege('authenticated', 'social_wiring.' || s, 'EXECUTE') OR has_function_privilege('anon', 'social_wiring.' || s, 'EXECUTE') THEN
      RAISE EXCEPTION 'browser can execute %', s; END IF;
  END LOOP;""",
}


@pytest.fixture(scope="module")
def replay() -> dict:
    steps = [
        {"product": "sw", "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": "sw", "file": "350", "sql": M350.read_text(encoding="utf-8"), "mode": "file", "twice": False},
        {"product": "sw", "file": "352", "sql": M352.read_text(encoding="utf-8"), "mode": "file", "twice": False},
        {"product": "sw", "file": "358", "sql": M358.read_text(encoding="utf-8"), "mode": "file", "twice": False},
        {"product": "sw", "file": "360", "sql": M360.read_text(encoding="utf-8"), "mode": "file", "twice": False},
        {"product": "sw", "file": "pre-370", "sql": PRE, "mode": "file", "twice": False},
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
    for step in ("prelude", "350", "352", "358", "360", "pre-370", "migration"):
        assert replay[step]["failures"] == [], (step, replay[step]["failures"])


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_scenario(replay, name):
    assert replay[f"scenario: {name}"]["failures"] == [], replay[f"scenario: {name}"]["failures"]


# ── static pins (no database) ────────────────────────────────────────────────────────────────────────────


def _code() -> str:
    return "\n".join(line for line in MIGRATION.read_text(encoding="utf-8").splitlines() if not line.strip().startswith("--"))


def test_every_function_revokes_and_nothing_is_granted_to_a_browser_role():
    code = _code()
    assert code.count("SECURITY DEFINER") == 1
    assert code.count("FROM PUBLIC, anon, authenticated;") == 2
    assert "TO authenticated" not in code and "TO anon" not in code


def test_the_migration_is_backward_compatible_with_the_previous_image():
    code = _code()
    assert " DROP COLUMN " not in code and "RENAME" not in code and "ALTER COLUMN" not in code and "DROP FUNCTION" not in code
    assert "cs_chat_proposta_salvar_roteiro(p_proposta UUID, p_org UUID, p_user UUID)" in code  # same signature
    assert "cardinality(r.estrutura_ids) = 0" in code  # the backfill never overwrites a recorded value
