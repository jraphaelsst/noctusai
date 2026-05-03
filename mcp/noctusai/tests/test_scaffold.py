"""Tests for product scaffolding."""
import re
import sys
import shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.scaffold import list_available_ports, scaffold_product

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "seed" / "backend" / "lib"))

from noctusai_lib.domain.sql_templates import (
    rls_subquery_policy,
    set_search_path,
)


def _normalize_ws(s: str) -> str:
    """Collapse runs of whitespace to single space + strip ends."""
    return re.sub(r"\s+", " ", s).strip()


class TestAvailablePorts:
    def test_returns_ports(self):
        ports = list_available_ports()
        assert "next_backend_port" in ports
        assert "next_frontend_port" in ports
        assert ports["next_backend_port"] > 8006
        assert ports["next_frontend_port"] > 8120

    def test_used_ports_include_known(self):
        ports = list_available_ports()
        assert 8000 in ports["used_backend"]  # Core
        assert 8006 in ports["used_backend"]  # Mailing


class TestScaffold:
    def test_refuses_existing_product(self):
        result = scaffold_product("Seed", "seed", "seed", 8099, 8199)
        assert "error" in result
        assert "already exists" in result["error"]

    def test_creates_new_product(self):
        target = REPO_ROOT / "products" / "test-scaffold-temp"
        try:
            result = scaffold_product("Test Product", "test-scaffold-temp", "test_schema", 8099, 8199, "Zap")
            assert result["created"] is True
            assert result["files_processed"] > 0
            assert (target / "backend" / "app" / "main.py").exists()
            assert (target / "frontend" / "src" / "App.tsx").exists()
            assert "next_steps" in result
        finally:
            if target.exists():
                shutil.rmtree(target)


class TestSqlTemplatesIntegration:
    """Scaffolded `001_<schema>.sql` must match the canonical helpers from
    `noctusai_lib.domain.sql_templates`. These tests catch drift between
    the template file and the helpers — without forcing the template to be
    runtime-rendered (which would make it a Python module, not SQL).

    Filed by `projects/side-projects-batch/` Phase 1.d
    (`mcp-scaffold-sql-templates-integration`, 2026-05-03)."""

    SCAFFOLD_SCHEMA = "ai_chat"

    def _scaffold_and_read_migration(self, target: Path) -> str:
        result = scaffold_product(
            "AI Chat",
            "test-scaffold-sql-temp",
            self.SCAFFOLD_SCHEMA,
            8099,
            8199,
            "Zap",
        )
        assert result["created"] is True, result
        migration = target / "backend" / "migrations" / "001_seed.sql"
        assert migration.exists(), f"scaffold did not produce {migration}"
        return migration.read_text()

    def test_set_search_path_matches_helper(self):
        target = REPO_ROOT / "products" / "test-scaffold-sql-temp"
        try:
            content = self._scaffold_and_read_migration(target)
            expected_line = set_search_path(self.SCAFFOLD_SCHEMA) + ";"
            assert expected_line in content, (
                f"Scaffolded migration missing canonical search_path prelude.\n"
                f"Expected line: {expected_line!r}\n"
                f"Actual content head:\n{content[:400]}"
            )
        finally:
            if target.exists():
                shutil.rmtree(target)

    def test_invitations_rls_policy_matches_helper(self):
        target = REPO_ROOT / "products" / "test-scaffold-sql-temp"
        try:
            content = self._scaffold_and_read_migration(target)
            expected_policy = rls_subquery_policy(
                self.SCAFFOLD_SCHEMA,
                "invitations",
                "invitations_select_own_org",
                "SELECT",
                using="org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid",
            )
            assert _normalize_ws(expected_policy) in _normalize_ws(content), (
                f"Scaffolded RLS policy doesn't match `rls_subquery_policy` output.\n"
                f"Expected (whitespace-normalized): {_normalize_ws(expected_policy)!r}\n"
                f"Migration head:\n{content[:1200]}"
            )
        finally:
            if target.exists():
                shutil.rmtree(target)

    def test_schema_placeholder_substitution(self):
        """The template uses `{{SCHEMA_NAME}}` placeholders consistently —
        scaffolded output must NOT carry literal `seed.` qualifiers leaking
        from the template's source product."""
        target = REPO_ROOT / "products" / "test-scaffold-sql-temp"
        try:
            content = self._scaffold_and_read_migration(target)
            assert "seed." not in content, (
                f"Scaffolded migration leaked `seed.` literal from the template — "
                f"placeholder substitution incomplete. Should use `{self.SCAFFOLD_SCHEMA}.` everywhere."
            )
            assert f"{self.SCAFFOLD_SCHEMA}.status_pagina" in content
            assert f"{self.SCAFFOLD_SCHEMA}.invitations" in content
        finally:
            if target.exists():
                shutil.rmtree(target)
