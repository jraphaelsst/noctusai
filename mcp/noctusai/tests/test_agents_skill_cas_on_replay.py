"""Agents 041: the draft-skill PATCH has the same atomic optimistic lock as the replace-set writes (Julia v2 A-polish
#11), proven on the REAL core + agents chain on PGlite.

`agents.update_draft_skill(..., p_expected_hash)` locks the parent draft FOR UPDATE, compares the caller's hash with its
`compiled_hash` and only then updates the skill -- one transaction. The 012 child guard NULLs the hash on the write, so
the loser of a two-editor race (still holding the hash it read) is refused with `conflito_de_versao` and the winner's
body survives. A published version's skill stays immutable; an unknown field is `invalid_payload`; a duplicate name is
`skill_exists`. Every assertion is a SQL step that RAISES on a mismatch."""
from __future__ import annotations

from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr

_ORG = "a0000000-0000-4000-8000-00000000000a"
_AGENT = "a3000000-0000-4000-8000-0000000000d4"
_SKILL = "a5000000-0000-4000-8000-0000000000d5"
_SKILL2 = "a5000000-0000-4000-8000-0000000000d6"
_TARGET = "products/agents/backend/migrations/041_julia_v2_skill_cas.sql"
_DRAFT = f"(SELECT id FROM agents.agent_versions WHERE agent_id = '{_AGENT}' AND status = 'rascunho')"
_CORPO = f"(SELECT corpo FROM agents.agent_skills WHERE id = '{_SKILL}')"


def _step(name: str, sql: str) -> dict:
    return {"product": "agents", "file": f"step:{name}", "sql": sql, "mode": "file", "twice": False}


def _refused_with(name: str, call: str, code: str) -> dict:
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


def _patch(campos: str, expected: str | None, skill: str = _SKILL) -> str:
    exp = "NULL" if expected is None else f"'{expected}'"
    return f"PERFORM agents.update_draft_skill('{_ORG}', '{skill}', '{campos}'::jsonb, {exp});"


def _do(call: str) -> str:
    return f"DO $t$ BEGIN {call} END $t$;"


def _check(name: str, condition: str) -> dict:
    return _step(name, f"DO $chk$ BEGIN IF NOT ({condition}) THEN RAISE EXCEPTION 'ASSERT {name}'; END IF; END $chk$;")


STEPS = [
    _step("seed_a_draft_with_two_skills", f"""
SET search_path = agents, public;
INSERT INTO agents.agents (id, org_id, key, nome, runtime, ativo) VALUES ('{_AGENT}', '{_ORG}', 'k-skill-cas', 'K', 'claude_sdk', false);
SELECT agents.create_agent_draft('{_ORG}', '{_AGENT}', NULL, '{_ORG}');
INSERT INTO agents.agent_skills (id, org_id, version_id, nome, descricao, corpo) VALUES
  ('{_SKILL}', '{_ORG}', {_DRAFT}, 'ofertar', 'Quando ofertar.', 'v0'),
  ('{_SKILL2}', '{_ORG}', {_DRAFT}, 'outra', 'Outra.', 'x');
UPDATE agents.agent_versions SET compiled_hash = 'h1' WHERE id = {_DRAFT};
"""),
    _step("editor_a_writes_with_the_hash_it_read", _do(_patch('{"corpo":"A"}', "h1"))),
    _check("the_skill_write_nulled_the_hash", f"(SELECT compiled_hash FROM agents.agent_versions WHERE id = {_DRAFT}) IS NULL"),
    _refused_with("editor_b_with_the_stale_hash_is_refused", _patch('{"corpo":"B"}', "h1"), "conflito_de_versao"),
    _check("the_winners_body_survived", f"{_CORPO} = 'A'"),
    _step("restamp", f"UPDATE agents.agent_versions SET compiled_hash = 'h2' WHERE id = {_DRAFT};"),
    _step("the_current_hash_passes", _do(_patch('{"corpo":"C","ordem":3,"ativo":false}', "h2"))),
    _check("and_wrote_every_field", f"{_CORPO} = 'C' AND (SELECT ordem = 3 AND NOT ativo FROM agents.agent_skills WHERE id = '{_SKILL}')"),
    _step("null_expected_hash_skips_the_check", _do(_patch('{"corpo":"D"}', None))),
    _check("null_expected_wrote", f"{_CORPO} = 'D'"),
    _refused_with("an_unknown_field_is_refused", _patch('{"version_id":"x"}', None), "invalid_payload"),
    _refused_with("a_duplicate_name_is_skill_exists", _patch('{"nome":"outra"}', None), "skill_exists"),
    _step("publish_the_version", f"UPDATE agents.agent_versions SET status = 'ativa', published_at = now(), "
          f"published_by = '{_ORG}' WHERE id = {_DRAFT};"),
    _refused_with("a_published_versions_skill_is_immutable",
                  _patch('{"corpo":"E"}', None), "version_immutable"),
]


def test_the_stale_skill_editor_is_refused_atomically_on_the_real_chain(pglite):
    root = Path(REPO_ROOT)
    steps = mr._steps_for(root, "agents", {_TARGET}, "worktree", {})
    steps.extend(STEPS)
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    by_file = {(s["product"], s["file"]): s for s in res["steps"]}
    assert not by_file[("agents", "041_julia_v2_skill_cas.sql")]["failures"]
    failed = {name: s["failures"][0]["error"] for (prod, name), s in by_file.items()
              if prod == "agents" and name.startswith("step:") and s["failures"]}
    assert not failed, failed
    ran = [n for (p, n) in by_file if p == "agents" and n.startswith("step:")]
    assert len(ran) == len(STEPS), "every step must have run"
