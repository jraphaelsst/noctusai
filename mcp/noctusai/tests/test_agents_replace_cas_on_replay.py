"""Agents 040: the atomic optimistic lock of the replace-set writes, proven on the REAL core + agents chain on PGlite.

`agents.replace_draft_conteudo(..., p_expected_hash)` locks the draft row FOR UPDATE and compares the caller's hash with the
draft's `compiled_hash` in the SAME transaction as the replace. A content write NULLs the hash (the re-stamp comes later),
so the loser of a two-editor race -- who still holds the hash it read -- is refused with `conflito_de_versao` and the
winner's rows are untouched. A NULL expected hash keeps the pre-040 behaviour; only ONE overload of the function exists.
Every assertion is a SQL step that RAISES on a mismatch."""
from __future__ import annotations

from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr

_ORG = "a0000000-0000-4000-8000-00000000000a"
_AGENT = "a3000000-0000-4000-8000-0000000000c3"
_TARGET = "products/agents/backend/migrations/040_julia_v2_pin_catalogo.sql"


def _step(name: str, sql: str) -> dict:
    return {"product": "agents", "file": f"step:{name}", "sql": sql, "mode": "file", "twice": False}


def _refused_with(name: str, call: str, code: str) -> dict:
    """A DO block that RAISES unless `call` fails with exactly `code` as the message."""
    return _step(name, f"""
DO $t$ BEGIN
  BEGIN
    {call}
    RAISE EXCEPTION 'ASSERT not refused: {name}';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'ASSERT not refused%' THEN RAISE; END IF;
    IF SQLERRM <> '{code}' THEN RAISE EXCEPTION 'ASSERT wrong refusal for {name}: %', SQLERRM; END IF;
  END;
END $t$;""")


def _replace(tabela_json: str, expected: str | None) -> str:
    exp = "NULL" if expected is None else f"'{expected}'"
    return (f"PERFORM agents.replace_draft_conteudo('{_ORG}', "
            f"(SELECT id FROM agents.agent_versions WHERE agent_id = '{_AGENT}' AND status = 'rascunho'), "
            f"'textos', '{tabela_json}'::jsonb, {exp});")


def _texto(valor: str) -> str:
    return '[{"chave":"a.b","conteudo":"%s"}]' % valor


def _do(call: str) -> str:
    return f"DO $t$ BEGIN {call} END $t$;"


def _check(name: str, condition: str) -> dict:
    return _step(name, f"DO $chk$ BEGIN IF NOT ({condition}) THEN RAISE EXCEPTION 'ASSERT {name}'; END IF; END $chk$;")


_DRAFT = f"(SELECT id FROM agents.agent_versions WHERE agent_id = '{_AGENT}' AND status = 'rascunho')"
_TEXTO = f"(SELECT conteudo FROM agents.agent_version_textos WHERE version_id = {_DRAFT} AND chave = 'a.b')"

STEPS = [
    _step("seed_a_draft", f"""
SET search_path = agents, public;
INSERT INTO agents.agents (id, org_id, key, nome, runtime, ativo) VALUES ('{_AGENT}', '{_ORG}', 'k-cas', 'K', 'claude_sdk', false);
SELECT agents.create_agent_draft('{_ORG}', '{_AGENT}', NULL, '{_ORG}');
UPDATE agents.agent_versions SET compiled_hash = 'h1' WHERE agent_id = '{_AGENT}' AND status = 'rascunho';
"""),
    _check("only_one_overload_remains", "(SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
           "WHERE n.nspname = 'agents' AND p.proname = 'replace_draft_conteudo') = 1"),
    # editor A holds h1 and wins
    _step("editor_a_writes_with_the_hash_it_read", _do(_replace(_texto("A"), 'h1'))),
    _check("a_content_write_nulled_the_hash", f"(SELECT compiled_hash FROM agents.agent_versions WHERE id = {_DRAFT}) IS NULL"),
    # editor B still holds h1: refused, and A's rows are untouched
    _refused_with("editor_b_with_the_stale_hash_is_refused",
                  _replace(_texto("B"), "h1"), "conflito_de_versao"),
    _check("the_winners_rows_survived", f"{_TEXTO} = 'A'"),
    # after the re-stamp the new hash is the one that passes
    _step("restamp", "UPDATE agents.agent_versions SET compiled_hash = 'h2' WHERE status = 'rascunho' AND agent_id = "
          f"'{_AGENT}';"),
    _refused_with("the_old_hash_is_still_refused_after_the_restamp",
                  _replace(_texto("B"), "h1"), "conflito_de_versao"),
    _step("the_current_hash_passes", _do(_replace(_texto("C"), 'h2'))),
    _check("and_wrote", f"{_TEXTO} = 'C'"),
    # no expected hash = no check (the pre-040 call shape still works)
    _step("null_expected_hash_skips_the_check", _do(_replace(_texto("D"), None))),
    _check("null_expected_wrote", f"{_TEXTO} = 'D'"),
    _step("the_four_argument_call_shape_still_resolves", f"""
DO $t$ BEGIN
  PERFORM agents.replace_draft_conteudo('{_ORG}', {_DRAFT}, 'textos', '[{{"chave":"a.b","conteudo":"E"}}]'::jsonb);
END $t$;"""),
    _check("four_arg_wrote", f"{_TEXTO} = 'E'"),
]


def test_the_stale_writer_of_a_two_editor_race_is_refused_atomically_on_the_real_chain(pglite):
    root = Path(REPO_ROOT)
    steps = mr._steps_for(root, "agents", {_TARGET}, "worktree", {})
    steps.extend(STEPS)
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    by_file = {(s["product"], s["file"]): s for s in res["steps"]}
    assert not by_file[("agents", "040_julia_v2_pin_catalogo.sql")]["failures"]
    failed = {name: s["failures"][0]["error"] for (prod, name), s in by_file.items()
              if prod == "agents" and name.startswith("step:") and s["failures"]}
    assert not failed, failed
    ran = [n for (p, n) in by_file if p == "agents" and n.startswith("step:")]
    assert len(ran) == len(STEPS), "every step must have run"
