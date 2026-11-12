"""Core 121 (one owner number in core) EXECUTED on the REAL core chain on PGlite.

The agents 074 hand-off value is copied into ``public.notification_owner_recipients`` as an ACTIVE recipient, with the
`adicionado` event written by the 118 trigger (actor = the nil UUID, "migration"); a second run changes nothing; a malformed
agents value copies nothing; and on a database with no agents schema (the plain core chain) it is a no-op.
The numbers below are placeholders: the migration itself carries none.
"""
from __future__ import annotations

from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr

_M121 = "121_owner_number_one_source.sql"
_PLACEHOLDER = "+5500000000042"

_AGENTS_ROW = """
CREATE SCHEMA IF NOT EXISTS agents;
CREATE TABLE agents.runtime_settings (key TEXT PRIMARY KEY, value JSONB NOT NULL);
INSERT INTO agents.runtime_settings (key, value) VALUES ('numero_fallback_atendimento', to_jsonb('%PH%'::text));
""".replace("%PH%", _PLACEHOLDER)

_ASSERT_COPIED = """
DO $t$
DECLARE n int; a boolean; ator uuid; ev int;
BEGIN
  SELECT count(*), bool_and(ativo) INTO n, a FROM public.notification_owner_recipients WHERE numero = '%NUM%';
  IF n <> 1 OR a IS NOT TRUE THEN RAISE EXCEPTION 'ASSERT expected ONE active recipient, got % / %', n, a; END IF;
  SELECT count(*), min(e.ator::text)::uuid INTO ev, ator FROM public.notification_owner_recipient_events e
    JOIN public.notification_owner_recipients r ON r.id = e.recipient_id WHERE r.numero = '%NUM%' AND e.evento = 'adicionado';
  IF ev <> 1 OR ator <> '00000000-0000-0000-0000-000000000000'::uuid THEN
    RAISE EXCEPTION 'ASSERT expected ONE adicionado event by the migration actor, got % / %', ev, ator; END IF;
END $t$;
""".replace("%NUM%", _PLACEHOLDER)

_ASSERT_NONE = """
DO $t$
BEGIN
  IF EXISTS (SELECT 1 FROM public.notification_owner_recipients) THEN
    RAISE EXCEPTION 'ASSERT nothing may be copied'; END IF;
END $t$;
"""


def _run(extra_before: list[str], assertion: str, *, twice: bool = False) -> list[dict]:
    steps = mr._steps_for(Path(REPO_ROOT), "core", set(), "worktree", {})
    idx = next(i for i, s in enumerate(steps) if s["file"] == _M121)
    sql121 = steps[idx]["sql"]
    for k, sql in enumerate(extra_before):
        steps.insert(idx + k, {"product": "core", "file": f"fixture:{k}", "sql": sql, "mode": "file", "twice": False})
    idx = next(i for i, s in enumerate(steps) if s["file"] == _M121)
    tail = []
    if twice:
        tail.append({"product": "core", "file": "121-again", "sql": sql121, "mode": "file", "twice": False})
    tail.append({"product": "core", "file": "assert", "sql": assertion, "mode": "file", "twice": False})
    steps[idx + 1:idx + 1] = tail
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    return [st for st in res["steps"] if st["file"] in {_M121, "121-again", "assert"} and st["failures"]]


def test_copies_the_agents_value_as_an_active_attributed_recipient_and_is_idempotent(pglite):
    assert _run([_AGENTS_ROW], _ASSERT_COPIED, twice=True) == []


def test_a_malformed_agents_value_copies_nothing(pglite):
    bad = _AGENTS_ROW.replace(_PLACEHOLDER, "not-a-phone")
    assert _run([bad], _ASSERT_NONE) == []


def test_without_an_agents_schema_it_is_a_noop(pglite):
    assert _run([], _ASSERT_NONE) == []
