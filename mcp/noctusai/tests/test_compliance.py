"""Tests for compliance checks."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.compliance import (
    check_seed_compliance,
    check_path_references,
    check_all_products,
    check_mock_schema_validation,
    check_ai_feature_completeness,
    check_phase_state_consistency,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PRODUCTS_DIR = REPO_ROOT / "products"


class TestSeedCompliance:
    def test_seed_product_is_compliant(self):
        issues = check_seed_compliance(PRODUCTS_DIR / "seed")
        assert len(issues) == 0, f"Seed has issues: {issues}"

    def test_mailing_is_compliant(self):
        issues = check_seed_compliance(PRODUCTS_DIR / "mailing")
        assert len(issues) == 0, f"Mailing has issues: {issues}"

    def test_all_products_compliant(self):
        score, issues = check_all_products()
        assert score == 100, f"Platform score {score}/100, issues: {issues}"

    def test_detects_boilerplate_router(self):
        """If a product had its own health.py, compliance would flag it."""
        # Create a temporary health.py
        health_file = PRODUCTS_DIR / "seed" / "backend" / "app" / "routers" / "health.py"
        health_file.write_text("# test")
        try:
            issues = check_seed_compliance(PRODUCTS_DIR / "seed")
            health_issues = [i for i in issues if "health.py" in i.get("file", "")]
            assert len(health_issues) > 0, "Should detect boilerplate health.py"
        finally:
            health_file.unlink()  # cleanup


class TestPathReferences:
    def test_no_old_shared_paths(self):
        for d in sorted(PRODUCTS_DIR.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            issues = check_path_references(d)
            assert len(issues) == 0, f"{d.name} has old paths: {issues}"


class TestMockSchemaValidation:
    """Detector for `validate_schema=False` without rationale comment."""

    def _mk_product(self, conftest_content: str) -> Path:
        """Build a fake product tree with a backend/tests/conftest.py."""
        tmp = Path(tempfile.mkdtemp(prefix="mock_schema_test_"))
        (tmp / "backend" / "tests").mkdir(parents=True)
        (tmp / "backend" / "tests" / "conftest.py").write_text(conftest_content)
        return tmp

    def test_no_mock_supabase_client_means_no_issue(self):
        product = self._mk_product("# empty conftest")
        assert check_mock_schema_validation(product) == []

    def test_default_instantiation_is_clean(self):
        """`MockSupabaseClient()` — default is now True, no flag needed, no issue."""
        product = self._mk_product(
            "from noctusai_lib.testing import MockSupabaseClient\n"
            "mock = MockSupabaseClient()\n"
        )
        assert check_mock_schema_validation(product) == []

    def test_validate_schema_true_explicit_is_clean(self):
        """Explicit True is fine (redundant but clean)."""
        product = self._mk_product(
            "mock = MockSupabaseClient(validate_schema=True)\n"
        )
        assert check_mock_schema_validation(product) == []

    def test_silent_opt_out_is_flagged(self):
        """`validate_schema=False` without rationale → high-severity issue."""
        product = self._mk_product(
            "mock = MockSupabaseClient(validate_schema=False)\n"
        )
        issues = check_mock_schema_validation(product)
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"
        assert "conftest" in issues[0]["file"]

    def test_opt_out_with_rationale_is_accepted(self):
        """`validate_schema=False` WITH a rationale comment → accepted."""
        product = self._mk_product(
            "# schema-drift: tracked by follow-up reconciliation project\n"
            "mock = MockSupabaseClient(validate_schema=False)\n"
        )
        assert check_mock_schema_validation(product) == []

    def test_opt_out_with_todo_rationale_accepted(self):
        """A TODO comment also counts as rationale."""
        product = self._mk_product(
            "# TODO: flip back to True once <project> lands\n"
            "mock = MockSupabaseClient(validate_schema=False)\n"
        )
        assert check_mock_schema_validation(product) == []

    def test_therapy_and_erp_opt_outs_pass(self):
        """The two real opt-outs landed by mock-supabase Phase 3 must pass."""
        for name in ("therapy-platform", "erp-imobiliario"):
            issues = check_mock_schema_validation(PRODUCTS_DIR / name)
            assert issues == [], f"{name} opt-out is flagged: {issues}"


# ---------------------------------------------------------------------------
# Tier 1.5 G3 — AI-feature wiring completeness
# ---------------------------------------------------------------------------

class TestAIFeatureCompleteness:
    """Detector for AI-feature wiring: router-registered, MASTER-PROMPT entry,
    cache=True calls thread org_id."""

    def _mk_product(self, *, ai_service: str = "", ai_router: str | None = "",
                    main_py: str = "", master_prompt: str = "") -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="ai_feat_test_"))
        # Always create the directory tree so the absence of one specific file
        # is meaningful (vs. the directory itself missing).
        (tmp / "backend" / "app" / "services").mkdir(parents=True)
        (tmp / "backend" / "app" / "routers").mkdir(parents=True)
        if ai_service:
            (tmp / "backend" / "app" / "services" / "ai_service.py").write_text(ai_service)
        if ai_router is not None:
            (tmp / "backend" / "app" / "routers" / "ai.py").write_text(ai_router or "# router")
        if main_py:
            (tmp / "backend" / "app" / "main.py").write_text(main_py)
        if master_prompt:
            (tmp / "MASTER-PROMPT.md").write_text(master_prompt)
        return tmp

    def test_no_ai_service_means_no_issue(self):
        """Products without AI features are skipped."""
        product = self._mk_product()  # nothing
        assert check_ai_feature_completeness(product) == []

    def test_router_not_wired_in_main_is_high_severity(self):
        product = self._mk_product(
            ai_service="from noctusai_lib.llm import chat_completion\n",
            ai_router="from fastapi import APIRouter\nrouter = APIRouter()\n",
            main_py=(
                "from app.routers import contacts, lists\n"
                "app = create_product_app(routers=[contacts.router, lists.router])\n"
            ),
            master_prompt="## AI Features\nUses ai_service.py.\n",
        )
        issues = check_ai_feature_completeness(product)
        # Only the wiring issue should fire (AI section + cache None).
        wiring = [i for i in issues if "main.py" in i["file"]]
        assert len(wiring) == 1
        assert wiring[0]["severity"] == "high"

    def test_router_wired_via_dotted_form(self):
        product = self._mk_product(
            ai_service="from noctusai_lib.llm import chat_completion\n",
            ai_router="from fastapi import APIRouter\nrouter = APIRouter()\n",
            main_py=(
                "from app.routers import contacts, ai\n"
                "app = create_product_app(routers=[contacts.router, ai.router])\n"
            ),
            master_prompt="## AI Features\n",
        )
        # Router wired → no wiring issue.
        issues = check_ai_feature_completeness(product)
        wiring = [i for i in issues if "main.py" in i["file"]]
        assert wiring == []

    def test_router_wired_via_alias_form(self):
        product = self._mk_product(
            ai_service="from noctusai_lib.llm import chat_completion\n",
            ai_router="from fastapi import APIRouter\nrouter = APIRouter()\n",
            main_py=(
                "from app.routers import ai as ai_router\n"
                "app = create_product_app(routers=[ai_router.router])\n"
            ),
            master_prompt="## AI Features\n",
        )
        issues = check_ai_feature_completeness(product)
        wiring = [i for i in issues if "main.py" in i["file"]]
        assert wiring == []

    def test_master_prompt_missing_ai_section(self):
        product = self._mk_product(
            ai_service="from noctusai_lib.llm import chat_completion\n",
            ai_router=None,  # no router
            master_prompt="## Purpose\n## Architecture\n",
        )
        issues = check_ai_feature_completeness(product)
        mp_issues = [i for i in issues if i["file"] == "MASTER-PROMPT.md"]
        assert len(mp_issues) == 1
        assert mp_issues[0]["severity"] == "warning"

    def test_master_prompt_with_subsection_passes(self):
        """`### AI and Matching` (subsection) should also pass — ERP shape."""
        product = self._mk_product(
            ai_service="from noctusai_lib.llm import chat_completion\n",
            ai_router=None,
            master_prompt="## Key Domains\n### AI and Matching\nDescription.\n",
        )
        issues = check_ai_feature_completeness(product)
        mp_issues = [i for i in issues if i["file"] == "MASTER-PROMPT.md"]
        assert mp_issues == []

    def test_master_prompt_with_ai_service_mention_passes(self):
        product = self._mk_product(
            ai_service="from noctusai_lib.llm import chat_completion\n",
            ai_router=None,
            master_prompt="## Services\nProduct uses ai_service.py for AI calls.\n",
        )
        issues = check_ai_feature_completeness(product)
        mp_issues = [i for i in issues if i["file"] == "MASTER-PROMPT.md"]
        assert mp_issues == []

    def test_cache_true_without_org_id_flagged(self):
        product = self._mk_product(
            ai_service=(
                "from noctusai_lib.llm import chat_completion\n"
                "async def f():\n"
                "    return await chat_completion(\n"
                "        messages=[],\n"
                "        cache=True,\n"
                "    )\n"
            ),
            ai_router=None,
            master_prompt="## AI Features\n",
        )
        issues = check_ai_feature_completeness(product)
        cache_issues = [i for i in issues if "ai_service.py" in i["file"]]
        assert len(cache_issues) == 1
        assert cache_issues[0]["severity"] == "high"

    def test_cache_true_with_org_id_passes(self):
        product = self._mk_product(
            ai_service=(
                "from noctusai_lib.llm import chat_completion\n"
                "async def f(org_id):\n"
                "    return await chat_completion(\n"
                "        messages=[],\n"
                "        cache=True,\n"
                "        org_id=org_id,\n"
                "    )\n"
            ),
            ai_router=None,
            master_prompt="## AI Features\n",
        )
        issues = check_ai_feature_completeness(product)
        assert [i for i in issues if "ai_service.py" in i["file"]] == []

    def test_cache_false_skips_org_id_check(self):
        """`cache=False` calls don't need org_id (no shared cache key risk)."""
        product = self._mk_product(
            ai_service=(
                "from noctusai_lib.llm import chat_completion\n"
                "async def f():\n"
                "    return await chat_completion(messages=[], cache=False)\n"
            ),
            ai_router=None,
            master_prompt="## AI Features\n",
        )
        issues = check_ai_feature_completeness(product)
        assert [i for i in issues if "ai_service.py" in i["file"]] == []

    def test_real_products_pass_validate(self):
        """All 8 live products pass the new detector — verifies the detector
        doesn't false-positive on the actually-shipped Tier 1 features."""
        score, issues = check_all_products()
        # The detector contributes per-product issues; whole-platform must stay 100.
        assert score == 100, f"Score dropped: {score}/100, issues: {issues}"


# ---------------------------------------------------------------------------
# Phase-state consistency — §6 ↔ §11 drift detector
# ---------------------------------------------------------------------------

class TestPhaseStateConsistency:
    """Detector for §6 ↔ §11 drift in PROJECT.md files.

    Slip pattern: agent writes a §11 entry saying "Phase N ✅ shipped" but
    leaves §6 sub-task checkboxes / phase header in pre-close state. The
    user reads §6 as a real-time dashboard; the mismatch is a documented
    lie about progress. Per `KB § PATTERNS/project-execution.md § 2`.
    """

    def _mk_repo(self, project_md_content: str, slug: str = "test-slug") -> Path:
        """Create a temporary repo with a single PROJECT.md at root projects/<slug>/."""
        tmp = Path(tempfile.mkdtemp(prefix="phase_state_test_"))
        (tmp / "projects" / slug).mkdir(parents=True)
        (tmp / "projects" / slug / "PROJECT.md").write_text(project_md_content)
        return tmp

    def test_clean_project_no_issues(self):
        """A project with all phases ✅, all sub-tasks `- [x]`, Improvements blocks
        present, and §11 entries → zero issues."""
        content = (
            "# Test Project\n\n"
            "## 6. Implementation phases\n\n"
            "### Phase 0 — Foo ✅\n"
            "- [x] Did the thing\n\n"
            "**Improvements:** none identified.\n\n"
            "## 11. Change log\n\n"
            "| 2026-04-28 | Phase 0 ✅ shipped | agent |\n"
        )
        repo = self._mk_repo(content)
        issues = check_phase_state_consistency(repo)
        assert issues == [], f"Should be clean, got: {issues}"

    def test_header_unflipped_but_changelog_says_shipped(self):
        """Rule 1: §11 says shipped, §6 header lacks ✅."""
        content = (
            "# Test\n\n"
            "## 6. Implementation phases\n\n"
            "### Phase 1 — Foo\n"
            "- [x] Did it\n\n"
            "**Improvements:** ok.\n\n"
            "## 11. Change log\n\n"
            "| 2026-04-28 | Phase 1 ✅ shipped | agent |\n"
        )
        repo = self._mk_repo(content)
        issues = check_phase_state_consistency(repo)
        assert any("lacks the `✅` icon" in i["issue"] for i in issues), issues
        assert all(i["severity"] == "high" for i in issues)

    def test_header_flipped_but_subtasks_unticked(self):
        """Rule 2: header has ✅ but some `- [ ]` sub-tasks remain."""
        content = (
            "# Test\n\n"
            "## 6. Implementation phases\n\n"
            "### Phase 1 — Foo ✅\n"
            "- [x] Did one\n"
            "- [ ] Forgot one\n\n"
            "**Improvements:** ok.\n\n"
            "## 11. Change log\n\n"
        )
        repo = self._mk_repo(content)
        issues = check_phase_state_consistency(repo)
        assert any("sub-task(s) remain `- [ ]`" in i["issue"] for i in issues), issues

    def test_header_flipped_but_no_improvements_block(self):
        """Rule 3: header has ✅ but no `**Improvements:**` block."""
        content = (
            "# Test\n\n"
            "## 6. Implementation phases\n\n"
            "### Phase 1 — Foo ✅\n"
            "- [x] Did it\n\n"
            "## 11. Change log\n\n"
        )
        repo = self._mk_repo(content)
        issues = check_phase_state_consistency(repo)
        assert any("lacks an `**Improvements:**` block" in i["issue"] for i in issues), issues

    def test_partial_or_blocked_icons_legitimate(self):
        """Phases marked ⏳, ❌, or 🅿️ are legitimate non-shipped states; not flagged."""
        content = (
            "# Test\n\n"
            "## 6. Implementation phases\n\n"
            "### Phase 1 — Foo ⏳ (executing)\n"
            "- [ ] Still going\n\n"
            "### Phase 2 — Bar ❌\n"
            "- [ ] Blocked\n\n"
            "### Phase 3 — Baz 🅿️ PARKED\n"
            "- [ ] Parked\n\n"
            "## 11. Change log\n\n"
        )
        repo = self._mk_repo(content)
        issues = check_phase_state_consistency(repo)
        assert issues == [], f"Non-shipped icons should not flag, got: {issues}"

    def test_pending_phase_with_no_icon_no_changelog_no_issue(self):
        """Pending phase (no icon, no §11 shipped claim) → no issue."""
        content = (
            "# Test\n\n"
            "## 6. Implementation phases\n\n"
            "### Phase 1 — Foo\n"
            "- [ ] Pending\n\n"
            "## 11. Change log\n\n"
        )
        repo = self._mk_repo(content)
        issues = check_phase_state_consistency(repo)
        assert issues == [], f"Pending phase should not flag, got: {issues}"

    def test_walks_product_scoped_projects(self):
        """Detector must walk `products/<product>/projects/<slug>/PROJECT.md` too."""
        tmp = Path(tempfile.mkdtemp(prefix="phase_state_prod_"))
        (tmp / "products" / "erp" / "projects" / "foo-bar").mkdir(parents=True)
        content = (
            "# Test\n\n"
            "## 6. Implementation phases\n\n"
            "### Phase 1 — Foo\n"
            "- [x] Done\n\n"
            "**Improvements:** ok.\n\n"
            "## 11. Change log\n\n"
            "| 2026-04-28 | Phase 1 ✅ closed | agent |\n"
        )
        (tmp / "products" / "erp" / "projects" / "foo-bar" / "PROJECT.md").write_text(content)
        issues = check_phase_state_consistency(tmp)
        # Phase 1 ✅ in §11 but header has no icon → rule 1 fires.
        assert any("foo-bar" in i["file"] for i in issues), issues
        assert any(i["product"] == "erp" for i in issues), issues

    def test_bare_phase_mention_in_changelog_does_not_count_as_shipped(self):
        """A passing mention like 'Phase 0 audit found X' should NOT count as 'shipped'.

        Without this guard, bare 'Phase N' references in narrative text would
        false-positive the rule-1 check.
        """
        content = (
            "# Test\n\n"
            "## 6. Implementation phases\n\n"
            "### Phase 0 — Audit\n"
            "- [ ] Run audit\n\n"
            "## 11. Change log\n\n"
            "| 2026-04-28 | Phase 0 audit found unrelated drift in another project | agent |\n"
        )
        repo = self._mk_repo(content)
        issues = check_phase_state_consistency(repo)
        # No "Phase 0 ✅" / "Phase 0 shipped" / "Phase 0 closed" — should not flag.
        assert issues == [], f"Bare mention should not count, got: {issues}"
