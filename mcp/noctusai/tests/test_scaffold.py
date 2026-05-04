"""Tests for product scaffolding."""
import re
import sys
import shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.scaffold import (
    RESERVED_RANGES,
    list_available_ports,
    reserve_port_range,
    scaffold_product,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "seed" / "lib" / "backend"))

# Worktree-local template (Phase 3.4 edits live here, not in noc proper).
WORKTREE_TEMPLATE = REPO_ROOT / "templates" / "product-seed"

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


class TestSlugPlaceholder:
    """Phase 3.4 — `{{PRODUCT_SLUG}}` placeholder + README path templating.

    The template-side fix lives in the worktree (templates/product-seed/),
    not in noc proper, so the test points scaffold_product at the worktree's
    template via the `template_dir=` seam.
    """

    SLUG = "polish-readme-temp"

    def test_readme_uses_slug_path_not_seed(self, tmp_path):
        result = scaffold_product(
            "Polish Readme",
            self.SLUG,
            "polish_readme",
            8099,
            8199,
            "Zap",
            products_dir=tmp_path,
            template_dir=WORKTREE_TEMPLATE,
        )
        assert result.get("created") is True, result
        readme = (tmp_path / self.SLUG / "README.md").read_text()
        # Substituted path appears.
        assert f"products/{self.SLUG}/backend" in readme, readme
        assert f"products/{self.SLUG}/frontend" in readme, readme
        # Literal `seed/backend` / `seed/frontend` no longer leaks.
        assert "products/seed/backend" not in readme, readme
        assert "products/seed/frontend" not in readme, readme
        # SCHEMA_NAME flowed through too.
        assert "schema: `polish_readme`" in readme, readme
        # No unsubstituted placeholders remain.
        assert "{{PRODUCT_SLUG}}" not in readme
        assert "{{SCHEMA_NAME}}" not in readme
        assert "{{PRODUCT_NAME}}" not in readme

    def test_master_prompt_uses_slug_path_not_seed(self, tmp_path):
        result = scaffold_product(
            "Polish Readme",
            self.SLUG,
            "polish_readme",
            8099,
            8199,
            "Zap",
            products_dir=tmp_path,
            template_dir=WORKTREE_TEMPLATE,
        )
        assert result.get("created") is True, result
        mp = (tmp_path / self.SLUG / "MASTER-PROMPT.md").read_text()
        assert f"products/{self.SLUG}/backend/app/" in mp, mp
        assert f"products/{self.SLUG}/frontend/src/" in mp, mp
        assert "products/seed/backend/app/" not in mp
        assert "products/seed/frontend/src/" not in mp


class TestEnvExampleSurvives:
    """Phase 3.4 — `.env.example` files must get placeholder substitution.

    Pre-fix, the positive-suffix whitelist excluded `.example`, so the
    file was COPIED but placeholders were left unsubstituted. Post-fix
    the substitution loop reads any non-binary file as text.
    """

    def test_env_example_has_substitutions(self, tmp_path):
        slug = "env-example-temp"
        result = scaffold_product(
            "Env Example",
            slug,
            "env_example",
            8201,
            8301,
            "Zap",
            products_dir=tmp_path,
            template_dir=WORKTREE_TEMPLATE,
        )
        assert result.get("created") is True, result
        env_example = tmp_path / slug / "frontend" / ".env.example"
        assert env_example.exists(), "scaffold should preserve .env.example"
        content = env_example.read_text()
        # Pre-fix this read literally as `{{BACKEND_PORT}}`.
        assert "8201" in content, content
        # PRODUCT_NAME placeholder substituted in the comment header.
        assert "Env Example" in content, content
        assert "{{BACKEND_PORT}}" not in content
        assert "{{PRODUCT_NAME}}" not in content


class TestReservePortRange:
    """Phase 3.4 — `reserve_port_range` returns contiguous N-port blocks
    for backend + frontend, never overlapping with `RESERVED_RANGES` or
    ports already wired in start.sh.
    """

    def test_default_count_one_matches_available_ports(self):
        avail = list_available_ports()
        result = reserve_port_range(product_slug="hypothetical")
        assert "error" not in result, result
        # Default count=1: the first backend port equals next_backend_port.
        assert result["backend_ports"] == [avail["next_backend_port"]]
        # Frontend uses next-10-aligned slot — equals next_frontend_port
        # for default count=1.
        assert result["frontend_ports"] == [avail["next_frontend_port"]]

    def test_5_plus_5_block_is_contiguous(self):
        result = reserve_port_range(
            product_slug="big-block",
            count_backend=5,
            count_frontend=5,
        )
        assert "error" not in result, result
        be = result["backend_ports"]
        fe = result["frontend_ports"]
        assert len(be) == 5
        assert len(fe) == 5
        # Contiguous: each port is exactly +1 of the previous.
        for i in range(1, len(be)):
            assert be[i] == be[i - 1] + 1, f"backend block not contiguous: {be}"
        for i in range(1, len(fe)):
            assert fe[i] == fe[i - 1] + 1, f"frontend block not contiguous: {fe}"

    def test_blocks_do_not_overlap_reserved(self):
        result = reserve_port_range(
            product_slug="no-overlap",
            count_backend=3,
            count_frontend=3,
        )
        assert "error" not in result, result
        reserved_ports = {p for p, _ in RESERVED_RANGES}
        for p in result["backend_ports"] + result["frontend_ports"]:
            assert p not in reserved_ports, (
                f"reserved {p} overlaps RESERVED_RANGES table"
            )

    def test_invalid_count_returns_error(self):
        result = reserve_port_range(
            product_slug="bad",
            count_backend=0,
            count_frontend=1,
        )
        assert "error" in result
        assert "must each be" in result["error"]


class TestReservedRangesDocstring:
    """Surface check: `RESERVED_RANGES` enumerates the known products from
    start.sh — Phase 3.4 added it so callers (humans + agents) can read the
    allocation map without parsing start.sh by hand.
    """

    def test_table_contains_known_products(self):
        slugs = {slug for _, slug in RESERVED_RANGES}
        # Spot-check known products from start.sh.
        for must_have in ("core", "erp-imobiliario", "personal-finance",
                          "therapy-platform", "seed", "daily-life", "mailing"):
            assert must_have in slugs, f"{must_have} missing from RESERVED_RANGES"

    def test_table_includes_both_be_and_fe_ports(self):
        ports = {p for p, _ in RESERVED_RANGES}
        # Backend 8000-range present.
        assert 8000 in ports
        assert 8006 in ports
        # Frontend 5173 + 8080-range.
        assert 5173 in ports
        assert 8120 in ports
