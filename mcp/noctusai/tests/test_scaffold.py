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
    """Scaffolded `001_<schema>.sql` must match the canonical helpers from
    `noctusai_lib.domain.sql_templates`. These tests catch drift between
    the template file and the helpers — without forcing the template to be
    runtime-rendered (which would make it a Python module, not SQL).

    Filed by `projects/side-projects-batch/` Phase 1.d
    (`mcp-scaffold-sql-templates-integration`, 2026-05-03)."""

    SCAFFOLD_SCHEMA = "ai_chat"

    def _scaffold_and_read_migration(self, products_dir: Path) -> str:
        result = scaffold_product(
            "AI Chat",
            "test-scaffold-sql-temp",
            self.SCAFFOLD_SCHEMA,
            8099,
            8199,
            "Zap",
            brief={},  # opt into mechanical substitution
            products_dir=products_dir,
            template_dir=WORKTREE_TEMPLATE,
        )
        assert result["created"] is True, result
        migration = products_dir / "test-scaffold-sql-temp" / "backend" / "migrations" / "001_seed.sql"
        assert migration.exists(), f"scaffold did not produce {migration}"
        return migration.read_text()

    def test_set_search_path_matches_helper(self, tmp_path):
        content = self._scaffold_and_read_migration(tmp_path)
        expected_line = set_search_path(self.SCAFFOLD_SCHEMA) + ";"
        assert expected_line in content, (
            f"Scaffolded migration missing canonical search_path prelude.\n"
            f"Expected line: {expected_line!r}\n"
            f"Actual content head:\n{content[:400]}"
        )

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
  "mailing:Mailing:8006:8120"
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
        assert '"mailing:Mailing:8006:8120"' in updated
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
            '"mailing:Mailing:8006:8120"',
            '"mailing:Mailing:8006:8120"\n  "dup-slug-test:Old Name:8000:9000"',
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
        assert '"mailing:Mailing:8006:8120"' in after
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
        ]
        for fname in ("Dockerfile", "Dockerfile.frontend", "docker-compose.yml", ".env.example"):
            content = (tmp_path / fname).read_text()
            assert "{{" not in content, f"{fname} still has placeholders"
        assert "8042" in (tmp_path / "Dockerfile").read_text()
        assert "8142" in (tmp_path / "Dockerfile.frontend").read_text()
        assert "my-product" in (tmp_path / "docker-compose.yml").read_text()
        assert "My Product" in (tmp_path / "docker-compose.yml").read_text()

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
        assert len(first["patched"]) == 4

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
