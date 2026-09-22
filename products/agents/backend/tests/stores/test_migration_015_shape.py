"""Structural tests for `015_haiku_model.sql` — parse-based, no database
needed. Mirrors the style of `test_migration_014_shape.py`.

This migration does NOT edit `006_agents.sql` / `012_agent_studio_
definitions.sql` in place (both are already applied in prod, their
migration-ledger hashes recorded) — it DROPs + re-ADDs the two `model`
CHECK constraints those files left unnamed, widening the allowlist to
include `claude-haiku-4-5` without touching either file.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "migrations" / "015_haiku_model.sql"
)
MIGRATION_006_PATH = (
    Path(__file__).resolve().parents[2] / "migrations" / "006_agents.sql"
)
MIGRATION_012_PATH = (
    Path(__file__).resolve().parents[2] / "migrations" / "012_agent_studio_definitions.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.exists(), f"missing migration: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


class TestDoesNotEdit006Or012InPlace:
    def test_006_still_has_its_original_two_value_inline_check(self):
        block = MIGRATION_006_PATH.read_text(encoding="utf-8")
        assert "CHECK (model IN ('claude-opus-5', 'claude-sonnet-5'))" in block

    def test_012_still_has_its_original_two_value_inline_check(self):
        block = MIGRATION_012_PATH.read_text(encoding="utf-8")
        assert "CHECK (model IN ('claude-opus-5', 'claude-sonnet-5'))" in block


class TestIdempotency:
    def test_every_add_constraint_is_preceded_by_a_drop_if_exists(self, sql):
        names = re.findall(r"ADD CONSTRAINT (\w+)", sql)
        assert names  # sanity: the migration does add constraints
        for name in names:
            assert f"DROP CONSTRAINT IF EXISTS {name}" in sql, name


class TestWidenedAllowlists:
    def test_agent_personas_model_check_gains_haiku(self, sql):
        block = sql[sql.index("ADD CONSTRAINT agent_personas_model_check") :]
        block = block[: block.index(";") + 1]
        for value in ("claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"):
            assert f"'{value}'" in block, value

    def test_agent_versions_model_check_gains_haiku(self, sql):
        block = sql[sql.index("ADD CONSTRAINT agent_versions_model_check") :]
        block = block[: block.index(";") + 1]
        for value in ("claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"):
            assert f"'{value}'" in block, value

    def test_alters_only_the_two_named_constraints(self, sql):
        assert set(re.findall(r"ADD CONSTRAINT (\w+)", sql)) == {
            "agent_personas_model_check",
            "agent_versions_model_check",
        }


class TestSearchPath:
    def test_search_path_set_at_top(self, sql):
        assert re.search(r"^SET search_path = agents, public;$", sql, re.M)
