"""Tests for product scaffolding."""
import re
import sys
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import scaffold as scaffold_module
from tools.noctus.dev.scaffold import (
    INTERROGATION_QUESTIONS,
    PROSE_SURFACES,
    RESERVED_RANGES,
    _patch_workspace_docker_files,
    delete_product,
    list_available_ports,
    reserve_port_range,
    scaffold_interrogate,
    scaffold_product,
)


# ─── Autouse fixture: stub the LLM call ────────────────────────────────────
# Default behavior: LLM rewrite returns None (call "failed"). That leaves
# prose surfaces with whatever mechanical substitution produced — ideal for
# tests that verify mechanical/structural behavior. Tests that need to
# verify LLM-was-called or LLM-rewrote-content override this patch with
# their own monkeypatch.
@pytest.fixture(autouse=True)
def _stub_llm_rewrite(monkeypatch):
    async def _no_op_llm(template_content, **_kwargs):
        return None
    monkeypatch.setattr(
        scaffold_module, "llm_rewrite_file_content", _no_op_llm,
    )

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "seed" / "lib" / "backend"))

# Worktree-local template (Phase 3.4 edits live here, not in noc proper).
WORKTREE_TEMPLATE = REPO_ROOT / "templates" / "product-seed"

from noctusai_lib.domain.sql_templates import (
    rls_subquery_policy,
    set_search_path,
)
from noctusai_lib.sql import prelude


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
        assert 8001 in ports["used_backend"]  # ERP Imobiliario


class TestScaffold:
    def test_refuses_existing_product(self):
        result = scaffold_product("Seed", "seed", "seed", 8099, 8199)
        assert "error" in result
        assert "already exists" in result["error"]

    def test_creates_new_product(self, tmp_path):
        # Uses the tmp_path seam (`products_dir=` + `template_dir=`) so the
        # test never touches REPO_ROOT/products or REPO_ROOT/start.sh — the
        # scaffold tool's full set of side-effects (dir copy, seed-row
        # migration, start.sh registry append) are all repo-hygiene-safe
        # under this seam. brief={} ("interrogation attempted, no answers")
        # opts into the mechanical-substitution path so files_processed > 0.
        target = tmp_path / "test-scaffold-temp"
        result = scaffold_product(
            "Test Product",
            "test-scaffold-temp",
            "test_schema",
            8099,
            8199,
            "Zap",
            brief={},
            products_dir=tmp_path,
            template_dir=WORKTREE_TEMPLATE,
        )
        assert result["created"] is True
        assert result["files_processed"] > 0
        assert (target / "backend" / "app" / "main.py").exists()
        assert (target / "frontend" / "src" / "App.tsx").exists()
        assert "next_steps" in result
        # Brief-first ordering: the brief file must exist (durable record).
        assert (target / ".scaffold-brief.md").exists()


class TestSqlTemplatesIntegration:
    """Scaffolded `001_<slug>.sql` must match the canonical helpers from
    `noctusai_lib.domain.sql_templates`. These tests catch drift between
    the template file and the helpers — without forcing the template to be
    runtime-rendered (which would make it a Python module, not SQL).

    Filed by `projects/side-projects-batch/` Phase 1.d
    (`mcp-scaffold-sql-templates-integration`, 2026-05-03). Filename moved
    from `001_seed.sql` → `001_<slug>.sql` and header replaced by
    `noctusai_lib.sql.prelude(schema)` output by
    `projects/scaffold-tool-canonical-emit/` (2026-05-10)."""

    SCAFFOLD_SCHEMA = "ai_chat"
    SCAFFOLD_SLUG = "test-scaffold-sql-temp"

    def _scaffold_and_read_migration(self, products_dir: Path) -> str:
        result = scaffold_product(
            "AI Chat",
            self.SCAFFOLD_SLUG,
            self.SCAFFOLD_SCHEMA,
            8099,
            8199,
            "Zap",
            brief={},  # opt into mechanical substitution
            products_dir=products_dir,
            template_dir=WORKTREE_TEMPLATE,
        )
        assert result["created"] is True, result
        # Canonical filename is `001_<slug>.sql` (was `001_seed.sql`).
        migration = (
            products_dir
            / self.SCAFFOLD_SLUG
            / "backend"
            / "migrations"
            / f"001_{self.SCAFFOLD_SLUG}.sql"
        )
        assert migration.exists(), f"scaffold did not produce {migration}"
        # And the legacy filename MUST be gone (renamed, not duplicated).
        legacy = migration.parent / "001_seed.sql"
        assert not legacy.exists(), (
            f"scaffold left legacy `001_seed.sql` alongside `{migration.name}` — "
            "rename should remove the source."
        )
        # The scaffold result advertises the canonical_migration outcome.
        canonical = result.get("canonical_migration")
        assert canonical is not None, result
        assert canonical.get("renamed") is True, canonical
        assert canonical.get("prelude_injected") is True, canonical
        assert canonical.get("path") == str(migration), canonical
        return migration.read_text()

    def test_set_search_path_matches_helper(self, tmp_path):
        content = self._scaffold_and_read_migration(tmp_path)
        expected_line = set_search_path(self.SCAFFOLD_SCHEMA) + ";"
        assert expected_line in content, (
            f"Scaffolded migration missing canonical search_path prelude.\n"
            f"Expected line: {expected_line!r}\n"
            f"Actual content head:\n{content[:400]}"
        )

    def test_migration_header_is_canonical_prelude(self, tmp_path):
        """The migration must START with `prelude(schema)` output verbatim —
        no hand-rolled header survives the canonicalization pass.

        Closes the N=10 hand-rolled-prelude recurrence Engineer U surfaced
        in the imobi P2 close (commit 31a0833)."""
        content = self._scaffold_and_read_migration(tmp_path)
        canonical_prelude_block = prelude(self.SCAFFOLD_SCHEMA)
        assert content.startswith(canonical_prelude_block), (
            f"Scaffolded migration does not begin with `prelude({self.SCAFFOLD_SCHEMA!r})` "
            f"output.\nExpected head:\n{canonical_prelude_block!r}\n"
            f"Actual head:\n{content[: len(canonical_prelude_block) + 40]!r}"
        )
        # The hand-rolled comment from the template (which mentions
        # PRODUCT_NAME) must NOT survive — the canonical block replaces it.
        assert "{{PRODUCT_NAME}} schema" not in content
        assert " schema\n-- Schema:" not in content, (
            "Hand-rolled `<NAME> schema / -- Schema: <SCHEMA>` header leaked "
            "into the scaffolded migration — canonicalization should have "
            "dropped it."
        )

    def test_migration_filename_uses_slug(self, tmp_path):
        """The migration file MUST land at `001_<slug>.sql` — the legacy
        `001_seed.sql` is rejected (and the assertion in
        `_scaffold_and_read_migration` enforces both files).
        """
        # _scaffold_and_read_migration runs the full assertion suite for us.
        self._scaffold_and_read_migration(tmp_path)

    def test_invitations_rls_policy_matches_helper(self, tmp_path):
        content = self._scaffold_and_read_migration(tmp_path)
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

    def test_schema_placeholder_substitution(self, tmp_path):
        """The template uses `{{SCHEMA_NAME}}` placeholders consistently —
        scaffolded output must NOT carry literal `seed.` qualifiers leaking
        from the template's source product."""
        content = self._scaffold_and_read_migration(tmp_path)
        assert "seed." not in content, (
            f"Scaffolded migration leaked `seed.` literal from the template — "
            f"placeholder substitution incomplete. Should use `{self.SCAFFOLD_SCHEMA}.` everywhere."
        )
        assert f"{self.SCAFFOLD_SCHEMA}.status_pagina" in content
        assert f"{self.SCAFFOLD_SCHEMA}.invitations" in content


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
            brief={},
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
            brief={},
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
            brief={},
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
                          "therapy-platform", "seed", "daily-life", "adconnect"):
            assert must_have in slugs, f"{must_have} missing from RESERVED_RANGES"

    def test_table_includes_both_be_and_fe_ports(self):
        ports = {p for p, _ in RESERVED_RANGES}
        # Backend 8000-range present.
        assert 8000 in ports
        assert 8001 in ports
        # Frontend 5173 + 8080-range.
        assert 5173 in ports
        assert 8080 in ports


class TestScaffoldEmitsProductsSeedRow:
    """Scaffolding a new product MUST emit a numbered seed-row migration at
    `products/core/backend/migrations/NNN_seed_<slug>_product.sql` so the
    product auto-registers in the noc dashboard's `public.products` table
    after migration apply. Mirrors the methodology rule: scaffolding a
    product without registering it in the dashboard is the slip that
    `media-scheduling` revealed.
    """

    def test_emits_seed_row_migration(self, tmp_path):
        # Build a minimal workspace shape: products/core/backend/migrations/
        # already populated with 001 + 002 so we can verify NNN advances.
        products_dir = tmp_path / "products"
        core_migrations = products_dir / "core" / "backend" / "migrations"
        core_migrations.mkdir(parents=True)
        (core_migrations / "001_existing.sql").write_text("-- existing")
        (core_migrations / "002_existing.sql").write_text("-- existing")

        result = scaffold_product(
            "Auto Register",
            "auto-register-test",
            "auto_register",
            8199,
            8299,
            "Bell",
            color="#ff00ff",
            description="Coverage product.",
            products_dir=products_dir,
            template_dir=WORKTREE_TEMPLATE,
        )

        assert result["created"] is True, result
        seed_row = result["seed_row_migration"]
        assert "path" in seed_row, seed_row
        emitted = Path(seed_row["path"])
        assert emitted.exists(), emitted
        # NNN advances past the highest existing.
        assert emitted.name == "003_seed_auto_register_test_product.sql", emitted.name
        body = emitted.read_text()
        # Idempotent + correct shape.
        assert "INSERT INTO public.products" in body
        assert "'auto-register-test'" in body
        assert "'http://localhost:8299'" in body
        assert "'#ff00ff'" in body
        assert "'Bell'" in body
        assert "'Coverage product.'" in body
        assert "ON CONFLICT (slug) DO NOTHING" in body
        # next_steps surfaces the apply-via-MCP follow-up first.
        assert any("Apply seed-row migration" in step for step in result["next_steps"])

    def test_skips_when_no_core_migrations_dir(self, tmp_path):
        # Workspace without products/core/backend/migrations/ (e.g., template
        # workspace, "templates can't modify noc" rule). Scaffold proceeds and
        # surfaces the gap in `next_steps` instead of crashing.
        products_dir = tmp_path / "products"
        products_dir.mkdir()

        result = scaffold_product(
            "Solo",
            "solo-test",
            "solo",
            8198,
            8298,
            "Box",
            products_dir=products_dir,
            template_dir=WORKTREE_TEMPLATE,
        )

        assert result["created"] is True, result
        seed_row = result["seed_row_migration"]
        assert "skipped" in seed_row, seed_row
        assert "path" not in seed_row
        assert any(
            "Manually emit products-seed-row migration" in step
            for step in result["next_steps"]
        )


_FIXTURE_START_SH = """\
#!/bin/bash
# fixture
set -e

# BEGIN_PRODUCTS_REGISTRY
PRODUCTS=(
  "core:Core:8000:5173"
  "sample-app:Sample App:8401:8501"
)
# END_PRODUCTS_REGISTRY

echo "done"
"""


class TestScaffoldRegistersInStartSh:
    """Scaffolding a new product MUST also append the registry entry to
    ``start.sh`` between the BEGIN_PRODUCTS_REGISTRY / END_PRODUCTS_REGISTRY
    sentinels. Closes the gap surfaced 2026-05-05 when adconnect's frontend
    on port 8130 was missing from start.sh and broke the SSO redirect flow.
    """

    def test_appends_entry_between_sentinels(self, tmp_path):
        products_dir = tmp_path / "products"
        products_dir.mkdir()
        start_sh = tmp_path / "start.sh"
        start_sh.write_text(_FIXTURE_START_SH)

        result = scaffold_product(
            "New Thing",
            "new-thing-test",
            "new_thing",
            8197,
            8297,
            "Box",
            products_dir=products_dir,
            template_dir=WORKTREE_TEMPLATE,
        )

        assert result["created"] is True, result
        reg = result["start_sh_registration"]
        assert "path" in reg, reg
        assert reg["entry"] == '"new-thing-test:New Thing:8197:8297"'

        updated = start_sh.read_text()
        # Original entries preserved.
        assert '"core:Core:8000:5173"' in updated
        assert '"sample-app:Sample App:8401:8501"' in updated
        # New entry appended inside the sentinels.
        assert '"new-thing-test:New Thing:8197:8297"' in updated
        # Sentinels intact.
        assert "# BEGIN_PRODUCTS_REGISTRY" in updated
        assert "# END_PRODUCTS_REGISTRY" in updated
        # Manual "Add to start.sh" step no longer surfaced when injection succeeded.
        assert not any(
            step.startswith("Manually add to start.sh") for step in result["next_steps"]
        )

    def test_idempotent_when_slug_already_registered(self, tmp_path):
        products_dir = tmp_path / "products"
        products_dir.mkdir()
        start_sh = tmp_path / "start.sh"
        # Pre-seed the registry with the slug we'll try to scaffold.
        seeded = _FIXTURE_START_SH.replace(
            '"sample-app:Sample App:8401:8501"',
            '"sample-app:Sample App:8401:8501"\n  "dup-slug-test:Old Name:8000:9000"',
        )
        start_sh.write_text(seeded)

        result = scaffold_product(
            "New Name",
            "dup-slug-test",
            "dup_slug",
            8196,
            8296,
            "Box",
            products_dir=products_dir,
            template_dir=WORKTREE_TEMPLATE,
        )

        assert result["created"] is True, result
        reg = result["start_sh_registration"]
        assert "skipped" in reg, reg
        assert "already registered" in reg["skipped"]
        # File body unchanged — the existing line stays as-is, no second entry.
        body = start_sh.read_text()
        assert body.count('"dup-slug-test:') == 1, body

    def test_skips_when_sentinels_missing(self, tmp_path):
        products_dir = tmp_path / "products"
        products_dir.mkdir()
        start_sh = tmp_path / "start.sh"
        start_sh.write_text("#!/bin/bash\necho 'no sentinels here'\n")

        result = scaffold_product(
            "Sentinel Missing",
            "sentinel-missing-test",
            "sentinel_missing",
            8195,
            8295,
            "Box",
            products_dir=products_dir,
            template_dir=WORKTREE_TEMPLATE,
        )

        assert result["created"] is True, result
        reg = result["start_sh_registration"]
        assert "skipped" in reg
        assert "sentinels" in reg["skipped"]
        assert any(
            step.startswith("Manually add to start.sh") for step in result["next_steps"]
        )

    def test_skips_when_start_sh_absent(self, tmp_path):
        products_dir = tmp_path / "products"
        products_dir.mkdir()
        # No start.sh at tmp_path — scaffold should proceed without crashing.

        result = scaffold_product(
            "No Start Sh",
            "no-start-sh-test",
            "no_start_sh",
            8194,
            8294,
            "Box",
            products_dir=products_dir,
            template_dir=WORKTREE_TEMPLATE,
        )

        assert result["created"] is True, result
        reg = result["start_sh_registration"]
        assert "skipped" in reg
        assert "does not exist" in reg["skipped"]


class TestScaffoldInterrogate:
    """Phase 1 of the two-phase scaffold flow — pure data return; the agent
    is the interrogator. The function exists so future agents discover the
    canonical question set automatically rather than improvising."""

    def test_returns_canonical_question_set(self):
        result = scaffold_interrogate("Foo Bar", "foo-bar", "foo_bar")
        assert result["name"] == "Foo Bar"
        assert result["slug"] == "foo-bar"
        assert result["schema"] == "foo_bar"
        questions = result["questions"]
        assert len(questions) == len(INTERROGATION_QUESTIONS)
        # Required questions surface the {key, prompt, required} contract.
        for q in questions:
            assert "key" in q and "prompt" in q and "required" in q
        # Required question keys cover the load-bearing brief axes.
        required_keys = {q["key"] for q in questions if q["required"]}
        assert {"domain", "primary_users", "core_entities", "primary_workflows"}.issubset(required_keys)

    def test_next_step_describes_brief_skip_path(self):
        result = scaffold_interrogate("Foo Bar", "foo-bar", "foo_bar")
        assert "scaffold_product" in result["next_step"]
        assert "brief=None" in result["next_step"]


class TestScaffoldBriefFirstOrdering:
    """Brief is written FIRST, before mechanical substitution and LLM
    rewrite. Per user rule (2026-05-05): the brief is the durable record
    of intent and must survive any subsequent failure."""

    def test_brief_dict_is_written_with_canonical_question_format(self, tmp_path):
        result = scaffold_product(
            "Brief Probe",
            "brief-probe-test",
            "brief_probe",
            8099,
            8199,
            "Box",
            brief={
                "domain": "real estate analytics",
                "primary_users": "brokers",
                "core_entities": "Imovel, Cliente, Negocio",
                "primary_workflows": "Match buyer to property",
                "key_integrations": "TJSP, Vista",
            },
            products_dir=tmp_path,
            template_dir=WORKTREE_TEMPLATE,
        )
        assert result["created"] is True
        assert result["brief_write"]["path"]
        assert result["brief_write"]["skipped_brief"] is False
        brief_md = (tmp_path / "brief-probe-test" / ".scaffold-brief.md").read_text()
        # Each canonical question prompt appears in the rendered brief.
        for q in INTERROGATION_QUESTIONS:
            assert q["prompt"] in brief_md, q["key"]
        # Provided answers appear; unanswered questions show the explicit
        # "_(not answered)_" placeholder so the gap is visible.
        assert "real estate analytics" in brief_md
        assert "_(not answered)_" in brief_md  # success_criteria + naming_conventions

    def test_brief_None_writes_skipped_stub(self, tmp_path):
        result = scaffold_product(
            "Skip Probe",
            "skip-probe-test",
            "skip_probe",
            8099,
            8199,
            "Box",
            brief=None,
            products_dir=tmp_path,
            template_dir=WORKTREE_TEMPLATE,
        )
        assert result["created"] is True
        assert result["brief_write"]["skipped_brief"] is True
        brief_md = (tmp_path / "skip-probe-test" / ".scaffold-brief.md").read_text()
        assert "SKIPPED" in brief_md
        assert "scaffold_interrogate" in brief_md  # recovery instructions
        # Skip path surfaced in next_steps — not silent.
        assert any("Brief was SKIPPED" in step for step in result["next_steps"])

    def test_skip_path_disables_mechanical_substitution(self, tmp_path):
        # Per user rule: "if questions skipped: LLM prose without mechanical".
        result = scaffold_product(
            "Skip Mechanical",
            "skip-mech-test",
            "skip_mech",
            8099,
            8199,
            "Box",
            brief=None,
            products_dir=tmp_path,
            template_dir=WORKTREE_TEMPLATE,
        )
        mechanical = result["mechanical_substitution"]
        assert mechanical["applied"] is False
        assert "questions-skipped" in mechanical["reason"]
        # files_processed reflects the skip — 0 mechanical-touched files.
        assert result["files_processed"] == 0
        # And the literal placeholders should still be present in the
        # template files (mechanical did NOT run to replace them).
        readme_text = (tmp_path / "skip-mech-test" / "README.md").read_text()
        assert "{{PRODUCT_NAME}}" in readme_text or "{{PRODUCT_SLUG}}" in readme_text


class TestScaffoldLLMRewrite:
    """LLM rewrite of prose surfaces. The autouse fixture patches
    `llm_rewrite_file_content` to return None by default — these tests
    override that to verify the call shape and content-write behavior.
    """

    def test_llm_called_per_prose_surface_with_brief(self, tmp_path, monkeypatch):
        captured_calls: list[dict] = []

        async def _capturing_llm(template_content, *, name, slug, schema,
                                  brief, surface_filename, provider="anthropic",
                                  model=None):
            captured_calls.append({
                "name": name,
                "slug": slug,
                "schema": schema,
                "brief": brief,
                "surface_filename": surface_filename,
                "provider": provider,
                "template_content_excerpt": template_content[:200],
            })
            return f"# {name} — bespoke {surface_filename}\n\nGenerated content for {slug}.\n"

        monkeypatch.setattr(scaffold_module, "llm_rewrite_file_content", _capturing_llm)

        brief = {"domain": "social media scheduling", "primary_users": "marketers"}
        result = scaffold_product(
            "LLM Probe",
            "llm-probe-test",
            "llm_probe",
            8099,
            8199,
            "Box",
            brief=brief,
            products_dir=tmp_path,
            template_dir=WORKTREE_TEMPLATE,
        )

        # LLM called for each prose surface (README + MASTER-PROMPT).
        called_surfaces = {c["surface_filename"] for c in captured_calls}
        assert called_surfaces == set(PROSE_SURFACES)
        # Each call carried the brief through.
        for call in captured_calls:
            assert call["brief"] == brief
            assert call["name"] == "LLM Probe"
            assert call["slug"] == "llm-probe-test"
        # Files now contain the LLM-generated content (not seed-template).
        readme = (tmp_path / "llm-probe-test" / "README.md").read_text()
        assert "LLM Probe" in readme
        assert "bespoke README.md" in readme
        # llm_rewrite result dict reflects success per surface.
        for surface in PROSE_SURFACES:
            assert result["llm_rewrite"][surface]["rewritten"] is True

    def test_llm_failure_leaves_seed_content_in_place_and_surfaces(self, tmp_path):
        # Default autouse stub returns None → LLM "failed" for every surface.
        result = scaffold_product(
            "Fail Probe",
            "fail-probe-test",
            "fail_probe",
            8099,
            8199,
            "Box",
            brief={},
            products_dir=tmp_path,
            template_dir=WORKTREE_TEMPLATE,
        )
        # Per surface, the failure is surfaced in the result (not silent).
        for surface in PROSE_SURFACES:
            assert "failed" in result["llm_rewrite"][surface]
        # next_steps surfaces the global LLM failure.
        assert any("LLM rewrite FAILED" in step for step in result["next_steps"])

    def test_llm_called_even_on_skip_path(self, tmp_path, monkeypatch):
        # Per user rule: "if questions skipped: LLM prose [still runs]".
        # The skip path disables MECHANICAL substitution, not the LLM pass.
        captured: list[dict | None] = []

        async def _llm_capture_brief(template_content, *, name, slug, schema,
                                     brief, surface_filename, provider="anthropic",
                                     model=None):
            captured.append(brief)
            return f"Skip-path content for {slug}\n"

        monkeypatch.setattr(scaffold_module, "llm_rewrite_file_content", _llm_capture_brief)

        scaffold_product(
            "Skip With LLM",
            "skip-with-llm-test",
            "skip_with_llm",
            8099,
            8199,
            "Box",
            brief=None,
            products_dir=tmp_path,
            template_dir=WORKTREE_TEMPLATE,
        )

        # LLM called once per prose surface, with brief=None passed through.
        assert len(captured) == len(PROSE_SURFACES)
        assert all(b is None for b in captured)


class TestDeleteProduct:
    """`noctus.dev.delete_product` — cascading delete inverse of
    scaffold_product. Mirrors the scaffold's three side-effects in reverse:
    deactivate-row migration, start.sh unregistration, optional folder
    removal. Hygiene-respecting under tmp_path seam.
    """

    def _seed_workspace_with_product(
        self,
        tmp_path: Path,
        *,
        slug: str = "doomed-test",
        name: str = "Doomed",
        backend_port: int = 8189,
        frontend_port: int = 8289,
    ) -> tuple[Path, Path]:
        """Set up a tmp_path workspace with: products/core/backend/migrations/
        (so seed-row + deactivate migrations have somewhere to land), a
        start.sh fixture with sentinels, and a scaffolded product folder.
        Returns ``(products_dir, start_sh)``.
        """
        products_dir = tmp_path / "products"
        core_migrations = products_dir / "core" / "backend" / "migrations"
        core_migrations.mkdir(parents=True)
        (core_migrations / "001_existing.sql").write_text("-- existing")

        start_sh = tmp_path / "start.sh"
        start_sh.write_text(_FIXTURE_START_SH)

        scaffold_result = scaffold_product(
            name,
            slug,
            slug.replace("-", "_"),
            backend_port,
            frontend_port,
            "Box",
            products_dir=products_dir,
            template_dir=WORKTREE_TEMPLATE,
        )
        assert scaffold_result["created"] is True, scaffold_result
        return products_dir, start_sh

    def test_emits_deactivate_migration(self, tmp_path):
        products_dir, _ = self._seed_workspace_with_product(tmp_path)

        result = delete_product("doomed-test", products_dir=products_dir)

        deact = result["deactivate_migration"]
        assert "path" in deact, deact
        emitted = Path(deact["path"])
        assert emitted.exists(), emitted
        # NNN advances past the highest existing migration (001 + 002 from
        # scaffold's seed-row insert = next is 003).
        assert emitted.name == "003_deactivate_doomed_test_product.sql", emitted.name
        body = emitted.read_text()
        assert "UPDATE public.products SET ativo = false" in body
        assert "WHERE slug = 'doomed-test'" in body
        # next_steps surfaces the apply-via-MCP follow-up.
        assert any(
            "Apply deactivate migration" in step for step in result["next_steps"]
        )

    def test_removes_start_sh_entry(self, tmp_path):
        products_dir, start_sh = self._seed_workspace_with_product(tmp_path)
        # Verify scaffold added the line we're about to delete.
        before = start_sh.read_text()
        assert '"doomed-test:Doomed:8189:8289"' in before, before

        result = delete_product("doomed-test", products_dir=products_dir)

        unreg = result["start_sh_unregistration"]
        assert "path" in unreg, unreg
        assert unreg["removed_entry"] == '"doomed-test:Doomed:8189:8289"'

        after = start_sh.read_text()
        assert '"doomed-test:' not in after, after
        # Pre-existing fixture entries still there — surgical removal.
        assert '"core:Core:8000:5173"' in after
        assert '"sample-app:Sample App:8401:8501"' in after
        # Sentinels intact.
        assert "# BEGIN_PRODUCTS_REGISTRY" in after
        assert "# END_PRODUCTS_REGISTRY" in after

    def test_default_skips_directory_removal(self, tmp_path):
        products_dir, _ = self._seed_workspace_with_product(tmp_path)
        product_dir = products_dir / "doomed-test"
        assert product_dir.is_dir()

        result = delete_product("doomed-test", products_dir=products_dir)

        # Default remove_directory=False → folder still on disk.
        assert product_dir.is_dir(), "default delete_product must NOT rmtree"
        removal = result["directory_removal"]
        assert "skipped" in removal
        assert "opt in" in removal["skipped"].lower()
        # next_steps surfaces the opt-in hint.
        assert any(
            "remove_directory=True" in step for step in result["next_steps"]
        )

    def test_removes_directory_when_opted_in(self, tmp_path):
        products_dir, _ = self._seed_workspace_with_product(tmp_path)
        product_dir = products_dir / "doomed-test"
        assert product_dir.is_dir()

        result = delete_product(
            "doomed-test",
            remove_directory=True,
            products_dir=products_dir,
        )

        removal = result["directory_removal"]
        assert "path" in removal, removal
        assert not product_dir.exists(), "remove_directory=True should rmtree"

    def test_idempotent_when_slug_not_registered(self, tmp_path):
        # Fresh workspace, no scaffold call — slug doesn't exist anywhere.
        products_dir = tmp_path / "products"
        core_migrations = products_dir / "core" / "backend" / "migrations"
        core_migrations.mkdir(parents=True)
        start_sh = tmp_path / "start.sh"
        start_sh.write_text(_FIXTURE_START_SH)

        result = delete_product("never-existed", products_dir=products_dir)

        # Migration still emits (it's just an UPDATE WHERE slug='...' that
        # affects 0 rows on the live DB — idempotent in SQL too).
        assert result["deactivate_migration"].get("path"), result
        # start.sh untouched.
        unreg = result["start_sh_unregistration"]
        assert "skipped" in unreg
        assert "not found" in unreg["skipped"]
        # Folder skipped (it never existed).
        assert "skipped" in result["directory_removal"]

    def test_skips_when_no_core_migrations_dir(self, tmp_path):
        products_dir = tmp_path / "products"
        products_dir.mkdir()
        # No products/core/backend/migrations/ — template-workspace shape.

        result = delete_product("template-workspace-slug", products_dir=products_dir)

        deact = result["deactivate_migration"]
        assert "skipped" in deact, deact
        assert "does not exist" in deact["skipped"]

    def test_skips_when_start_sh_absent(self, tmp_path):
        products_dir = tmp_path / "products"
        core_migrations = products_dir / "core" / "backend" / "migrations"
        core_migrations.mkdir(parents=True)
        # No start.sh file at tmp_path.

        result = delete_product("any-slug", products_dir=products_dir)

        unreg = result["start_sh_unregistration"]
        assert "skipped" in unreg
        assert "does not exist" in unreg["skipped"]

    def test_skips_when_sentinels_missing(self, tmp_path):
        products_dir = tmp_path / "products"
        core_migrations = products_dir / "core" / "backend" / "migrations"
        core_migrations.mkdir(parents=True)
        start_sh = tmp_path / "start.sh"
        start_sh.write_text("#!/bin/bash\necho 'no sentinels'\n")

        result = delete_product("any-slug", products_dir=products_dir)

        unreg = result["start_sh_unregistration"]
        assert "skipped" in unreg
        assert "sentinels" in unreg["skipped"]


class TestDeleteProductRespectsTestSeam:
    """Hygiene regression guard: under tmp_path seam, delete_product must
    NOT touch real start.sh or real products/core/backend/migrations/.
    Same shape as TestScaffoldRespectsTestSeam.
    """

    def test_no_real_start_sh_writes_under_tmp_seam(self, tmp_path):
        real_start_sh = REPO_ROOT / "start.sh"
        before = real_start_sh.read_text() if real_start_sh.exists() else ""

        products_dir = tmp_path / "products"
        core_migrations = products_dir / "core" / "backend" / "migrations"
        core_migrations.mkdir(parents=True)

        delete_product("hygiene-doomed-slug", products_dir=products_dir)

        after = real_start_sh.read_text() if real_start_sh.exists() else ""
        assert before == after, (
            "delete_product wrote to REPO_ROOT/start.sh under the tmp_path seam"
        )

    def test_no_real_core_migration_writes_under_tmp_seam(self, tmp_path):
        core_migrations = REPO_ROOT / "products" / "core" / "backend" / "migrations"
        before = sorted(p.name for p in core_migrations.iterdir())

        products_dir = tmp_path / "products"
        local_core_migrations = products_dir / "core" / "backend" / "migrations"
        local_core_migrations.mkdir(parents=True)

        delete_product("hygiene-doomed-slug-two", products_dir=products_dir)

        after = sorted(p.name for p in core_migrations.iterdir())
        assert before == after, (
            "delete_product wrote to REPO_ROOT/products/core/backend/migrations/ "
            "under the tmp_path seam — leaked:\n"
            f"{set(after) - set(before)}"
        )


class TestScaffoldRespectsTestSeam:
    """Regression guard for the test-hygiene gap surfaced 2026-05-05: when
    `products_dir=tmp_path` is passed, scaffold_product must NOT touch
    REPO_ROOT/start.sh or REPO_ROOT/products/core/backend/migrations/.
    Pre-fix, the older TestScaffold + TestSqlTemplatesIntegration tests
    omitted the seam and silently polluted real files (orphan migrations
    014-039 + start.sh entries) on every run.
    """

    def test_no_real_start_sh_writes_under_tmp_seam(self, tmp_path):
        real_start_sh = REPO_ROOT / "start.sh"
        before = real_start_sh.read_text() if real_start_sh.exists() else ""

        products_dir = tmp_path / "products"
        products_dir.mkdir()
        result = scaffold_product(
            "Hygiene Probe",
            "hygiene-probe-test",
            "hygiene_probe",
            8193,
            8293,
            "Box",
            products_dir=products_dir,
            template_dir=WORKTREE_TEMPLATE,
        )
        assert result["created"] is True, result

        after = real_start_sh.read_text() if real_start_sh.exists() else ""
        assert before == after, (
            "scaffold_product wrote to REPO_ROOT/start.sh while invoked under "
            "the tmp_path seam — the test seam must contain ALL side-effects."
        )

    def test_no_real_core_migration_writes_under_tmp_seam(self, tmp_path):
        core_migrations = REPO_ROOT / "products" / "core" / "backend" / "migrations"
        before = sorted(p.name for p in core_migrations.iterdir())

        products_dir = tmp_path / "products"
        products_dir.mkdir()
        result = scaffold_product(
            "Hygiene Probe Two",
            "hygiene-probe-two-test",
            "hygiene_probe_two",
            8192,
            8292,
            "Box",
            products_dir=products_dir,
            template_dir=WORKTREE_TEMPLATE,
        )
        assert result["created"] is True, result

        after = sorted(p.name for p in core_migrations.iterdir())
        assert before == after, (
            "scaffold_product wrote to REPO_ROOT/products/core/backend/migrations/ "
            "while invoked under the tmp_path seam — leaked orphans:\n"
            f"{set(after) - set(before)}"
        )


class TestWorkspaceDockerPatch:
    """`_patch_workspace_docker_files` substitutes the placeholders that
    `bootstrap-seed-workspace.sh` drops in the workspace-root docker
    artifacts. The convention exists so the user can `docker compose up`
    immediately after `scaffold_product` without hand-authoring compose.
    See KB § PATTERNS/seed-workspace.md § Docker scaffolding."""

    def _seed_docker_files(self, workspace: Path) -> None:
        (workspace / "Dockerfile").write_text(
            "EXPOSE {{BACKEND_PORT}}\nWORKDIR /app/products/{{PRODUCT_SLUG}}\n"
        )
        (workspace / "Dockerfile.frontend").write_text(
            "EXPOSE {{FRONTEND_PORT}}\nCOPY products/{{PRODUCT_SLUG}}/frontend ./\n"
        )
        (workspace / "docker-compose.yml").write_text(
            "# {{PRODUCT_NAME}}\n"
            "services:\n"
            "  app:\n"
            "    image: {{PRODUCT_SLUG}}-app:dev\n"
            "    ports: [\"{{BACKEND_PORT}}:{{BACKEND_PORT}}\"]\n"
            "  frontend:\n"
            "    ports: [\"{{FRONTEND_PORT}}:{{FRONTEND_PORT}}\"]\n"
        )
        (workspace / ".env.example").write_text(
            "# {{PRODUCT_NAME}}\nVITE_API_URL=http://localhost:{{BACKEND_PORT}}\n"
        )
        (workspace / "start.sh").write_text(
            "#!/usr/bin/env bash\n# {{PRODUCT_NAME}} ({{PRODUCT_SLUG}})\nPORT={{BACKEND_PORT}}\n"
        )
        (workspace / "stop.sh").write_text(
            "#!/usr/bin/env bash\n# {{PRODUCT_NAME}} ({{PRODUCT_SLUG}})\n"
        )

    def test_substitutes_all_four_placeholders(self, tmp_path):
        self._seed_docker_files(tmp_path)
        result = _patch_workspace_docker_files(
            workspace_root=tmp_path,
            slug="my-product",
            name="My Product",
            backend_port=8042,
            frontend_port=8142,
        )
        assert sorted(result["patched"]) == [
            ".env.example",
            "Dockerfile",
            "Dockerfile.frontend",
            "docker-compose.yml",
            "start.sh",
            "stop.sh",
        ]
        for fname in ("Dockerfile", "Dockerfile.frontend", "docker-compose.yml", ".env.example", "start.sh", "stop.sh"):
            content = (tmp_path / fname).read_text()
            assert "{{" not in content, f"{fname} still has placeholders"
        assert "8042" in (tmp_path / "Dockerfile").read_text()
        assert "8142" in (tmp_path / "Dockerfile.frontend").read_text()
        assert "my-product" in (tmp_path / "docker-compose.yml").read_text()
        assert "My Product" in (tmp_path / "docker-compose.yml").read_text()
        # start.sh / stop.sh land executable (mode | 0o111).
        for fname in ("start.sh", "stop.sh"):
            mode = (tmp_path / fname).stat().st_mode
            assert mode & 0o111, f"{fname} should be executable after patch"

    def test_no_op_when_files_missing(self, tmp_path):
        # In-noc scaffold: workspace-root docker files don't exist. Function
        # returns gracefully with no patched files; nothing gets created.
        result = _patch_workspace_docker_files(
            workspace_root=tmp_path,
            slug="x",
            name="X",
            backend_port=8000,
            frontend_port=8100,
        )
        assert result["patched"] == []
        assert all("not present" in entry for entry in result["skipped"])
        assert sorted(p.name for p in tmp_path.iterdir()) == []

    def test_idempotent_on_already_patched_files(self, tmp_path):
        # First patch substitutes; second patch is a no-op (placeholders
        # already gone). Files don't change content.
        self._seed_docker_files(tmp_path)
        first = _patch_workspace_docker_files(
            workspace_root=tmp_path,
            slug="my-product",
            name="My Product",
            backend_port=8042,
            frontend_port=8142,
        )
        assert len(first["patched"]) == 6

        snapshot = {
            f.name: f.read_text() for f in tmp_path.iterdir() if f.is_file()
        }
        second = _patch_workspace_docker_files(
            workspace_root=tmp_path,
            slug="other-slug",
            name="Other",
            backend_port=9999,
            frontend_port=9998,
        )
        assert second["patched"] == []
        assert all("already patched" in entry for entry in second["skipped"])
        for f in tmp_path.iterdir():
            if f.is_file():
                assert f.read_text() == snapshot[f.name], f"{f.name} changed on second patch"


class TestWorktreeAwarePathResolution:
    """Regression — `scaffold_product` accepts an explicit `worktree_path`
    so MCP write tools route caller-aware paths, NOT the server's startup
    workspace.

    Filed by ``projects/mcp-worktree-path-resolution/`` (2026-05-10) —
    surfacing slip in ``imobi-scheduling-bot-creation`` Phase 0+1 close
    where ``scaffold_product`` wrote 58+ files to the noc main worktree
    from inside Engineer E's isolated worktree.
    """

    def _make_fake_worktree(self, root: Path) -> Path:
        """Build a directory shaped like a real worktree root: .git file
        + .noctusai-workspace marker + a copy of the seed template at
        ``templates/product-seed`` (so we don't depend on tmp -> noc
        symlinks).
        """
        root.mkdir(parents=True, exist_ok=True)
        (root / ".git").write_text(
            "gitdir: /tmp/fake/.git/worktrees/agent-test\n", encoding="utf-8"
        )
        (root / ".noctusai-workspace").write_text(
            "workspace_kind=primary\n"
            "workspace_name=fake-worktree\n"
            f"noctusai_home={root}\n"
            "bootstrap_version=1\n",
            encoding="utf-8",
        )
        return root

    def test_worktree_path_lands_writes_in_worktree_not_noc(self, tmp_path):
        """Core regression: when `worktree_path` is given, the new product
        folder lands UNDER the worktree, NOT under noc's PRODUCTS_DIR.
        """
        wt = self._make_fake_worktree(tmp_path / "wt")
        slug = "wt-test-product"

        result = scaffold_product(
            "Worktree Test",
            slug,
            "wt_test",
            8099,
            8199,
            "Zap",
            brief={},
            worktree_path=wt,
            template_dir=WORKTREE_TEMPLATE,
        )

        assert result["created"] is True, result
        # MUST land in the worktree, NOT noc.
        assert (wt / "products" / slug / "backend" / "app" / "main.py").exists(), (
            "scaffold_product with worktree_path=<wt> must place the new "
            f"product under {wt}/products/, got result={result}"
        )

    def test_worktree_path_none_keeps_default_behavior(self, tmp_path):
        """When `worktree_path` is None (architect on main noc), the
        explicit `products_dir` seam still wins — back-compat for tests
        and direct callers.
        """
        result = scaffold_product(
            "Default Path",
            "default-path-temp",
            "default_path",
            8099,
            8199,
            "Zap",
            brief={},
            worktree_path=None,
            products_dir=tmp_path,  # explicit seam — wins over both worktree + module-default
            template_dir=WORKTREE_TEMPLATE,
        )
        assert result["created"] is True, result
        assert (tmp_path / "default-path-temp" / "backend").exists()

    def test_invalid_worktree_path_raises_no_silent_fallback(self, tmp_path):
        """The whole point of this arg is to surface worktree-bypass slips.
        Silent fallback would defeat that — an invalid worktree_path MUST
        raise ValueError, not quietly write to noc.
        """
        bad = tmp_path / "not-a-worktree"
        bad.mkdir()
        # No .git, no marker — bad shape.
        with pytest.raises(ValueError, match=r"missing \.git|not a directory"):
            scaffold_product(
                "Bad Path",
                "bad-path-temp",
                "bad_path",
                8099,
                8199,
                "Zap",
                brief={},
                worktree_path=bad,
                template_dir=WORKTREE_TEMPLATE,
            )

    def test_explicit_products_dir_overrides_worktree_path(self, tmp_path):
        """Test-seam priority — explicit `products_dir` wins over
        `worktree_path` resolution. Keeps existing tests stable while
        the new arg surfaces in production.
        """
        wt = self._make_fake_worktree(tmp_path / "wt")
        sink = tmp_path / "sink"
        result = scaffold_product(
            "Sink Test",
            "sink-test-temp",
            "sink_test",
            8099,
            8199,
            "Zap",
            brief={},
            worktree_path=wt,
            products_dir=sink,  # SHOULD win
            template_dir=WORKTREE_TEMPLATE,
        )
        assert result["created"] is True, result
        assert (sink / "sink-test-temp" / "backend").exists()
        # Worktree's products/ should be UNTOUCHED.
        assert not (wt / "products" / "sink-test-temp").exists()

    def test_delete_product_honors_worktree_path(self, tmp_path):
        """`delete_product` mirrors `scaffold_product`'s resolution order."""
        wt = self._make_fake_worktree(tmp_path / "wt")
        slug = "delete-wt-test"
        # First, scaffold into the worktree.
        scaffold_product(
            "Delete WT",
            slug,
            "delete_wt",
            8099,
            8199,
            "Zap",
            brief={},
            worktree_path=wt,
            template_dir=WORKTREE_TEMPLATE,
        )
        target = wt / "products" / slug
        assert target.exists()

        # Now delete with remove_directory=True.
        result = delete_product(
            slug,
            remove_directory=True,
            worktree_path=wt,
        )
        # The product folder under the worktree should be gone.
        assert not target.exists(), f"delete_product did not remove {target}"
        # Result should reference the worktree's directory removal.
        assert "directory_removal" in result


# Minimal root docker-compose.yml carrying the include: block sentinels —
# the house single-container shape (one single-line entry per product, NO
# override files). Mirrors the real repo-root file's structure.
_FIXTURE_ROOT_COMPOSE = """\
# NoctusAI — PRODUCTS orchestrator (compose project: noctusai-products).
name: noctusai-products

include:
  # BEGIN_PRODUCTS_INCLUDE
  # One entry per product compose (single-container). No override files.
  - products/core/docker-compose.yml
  # END_PRODUCTS_INCLUDE

networks:
  noctus-net:
    name: noctus-net
    external: true
"""


class TestScaffoldRegistersInRootCompose:
    """`_register_in_root_compose` MUST append exactly ONE single-line
    `- products/<slug>/docker-compose.yml` entry between the
    BEGIN/END_PRODUCTS_INCLUDE sentinels — the house single-container
    shape: ONE container, ONE shape, NO `docker-compose.override.yml`,
    NO multi-line `- path:` include block.

    This is the regression that would have caught the W0.3-scaffold
    override-drift at author time (SW-SCAFFOLD-FIX): the scaffold template
    once emitted an `include:` registration with an
    `override`-paired/`- path:` block that drifted from the single-env
    house model documented in KB § PATTERNS/containerization.md
    ("NO dev/prod split — ONE container, ONE shape always"). Pin the shape
    so it can never silently regress.
    """

    def _write(self, tmp_path: Path, body: str = _FIXTURE_ROOT_COMPOSE) -> Path:
        compose = tmp_path / "docker-compose.yml"
        compose.write_text(body)
        return compose

    def test_appends_single_line_house_shape_entry(self, tmp_path):
        compose = self._write(tmp_path)

        result = scaffold_module._register_in_root_compose(
            slug="new-thing-test", repo_root=tmp_path
        )

        assert "entry" in result, result
        assert result["entry"] == "- products/new-thing-test/docker-compose.yml"

        updated = compose.read_text()
        # Pre-existing entry preserved.
        assert "  - products/core/docker-compose.yml" in updated
        # New entry is a single line, exactly the house shape.
        assert "  - products/new-thing-test/docker-compose.yml" in updated
        # Sentinels intact + entry landed BETWEEN them.
        begin = updated.index("# BEGIN_PRODUCTS_INCLUDE")
        end = updated.index("# END_PRODUCTS_INCLUDE")
        entry_at = updated.index("- products/new-thing-test/docker-compose.yml")
        assert begin < entry_at < end, updated

    def test_no_override_no_path_block_emitted(self, tmp_path):
        """The house model has NO override files: the registration must
        NOT introduce `docker-compose.override.yml` nor a multi-line
        `- path:` include block (the exact W0.3 override-drift defect)."""
        compose = self._write(tmp_path)

        scaffold_module._register_in_root_compose(
            slug="no-override-test", repo_root=tmp_path
        )

        updated = compose.read_text()
        assert "docker-compose.override.yml" not in updated, updated
        # No YAML mapping-form include entry (`- path:`) — single string only.
        assert "- path:" not in updated, updated
        assert "override:" not in updated, updated
        # Exactly one line for the new slug, and it is the string form.
        slug_lines = [
            ln for ln in updated.splitlines()
            if "no-override-test" in ln
        ]
        assert slug_lines == [
            "  - products/no-override-test/docker-compose.yml"
        ], slug_lines

    def test_idempotent_when_slug_already_registered(self, tmp_path):
        seeded = _FIXTURE_ROOT_COMPOSE.replace(
            "  - products/core/docker-compose.yml",
            "  - products/core/docker-compose.yml\n"
            "  - products/dup-test/docker-compose.yml",
        )
        compose = self._write(tmp_path, seeded)

        result = scaffold_module._register_in_root_compose(
            slug="dup-test", repo_root=tmp_path
        )

        assert "skipped" in result, result
        assert "already registered" in result["skipped"]
        body = compose.read_text()
        assert body.count("- products/dup-test/docker-compose.yml") == 1, body

    def test_skips_when_sentinels_missing(self, tmp_path):
        compose = tmp_path / "docker-compose.yml"
        compose.write_text("name: noctusai-products\ninclude: []\n")

        result = scaffold_module._register_in_root_compose(
            slug="no-sentinels-test", repo_root=tmp_path
        )

        assert "skipped" in result, result
        assert "sentinels" in result["skipped"]

    def test_skips_when_compose_absent(self, tmp_path):
        result = scaffold_module._register_in_root_compose(
            slug="no-compose-test", repo_root=tmp_path
        )

        assert "skipped" in result, result
        assert "does not exist" in result["skipped"]
