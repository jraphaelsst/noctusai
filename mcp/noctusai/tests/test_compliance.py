"""Tests for compliance checks."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (
    check_seed_compliance,
    check_path_references,
    check_all_products,
    check_mock_schema_validation,
    check_ai_feature_completeness,
    check_phase_state_consistency,
    check_no_self_monkeypatch,
    check_silent_errors,
    check_clean_folder_violations,
    check_detector_has_regression_test,
    check_section_7_placeholder_consistency,
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
            ai_service="from noctusai_lib.integrations.llm import chat_completion\n",
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
            ai_service="from noctusai_lib.integrations.llm import chat_completion\n",
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
            ai_service="from noctusai_lib.integrations.llm import chat_completion\n",
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
            ai_service="from noctusai_lib.integrations.llm import chat_completion\n",
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
            ai_service="from noctusai_lib.integrations.llm import chat_completion\n",
            ai_router=None,
            master_prompt="## Key Domains\n### AI and Matching\nDescription.\n",
        )
        issues = check_ai_feature_completeness(product)
        mp_issues = [i for i in issues if i["file"] == "MASTER-PROMPT.md"]
        assert mp_issues == []

    def test_master_prompt_with_ai_service_mention_passes(self):
        product = self._mk_product(
            ai_service="from noctusai_lib.integrations.llm import chat_completion\n",
            ai_router=None,
            master_prompt="## Services\nProduct uses ai_service.py for AI calls.\n",
        )
        issues = check_ai_feature_completeness(product)
        mp_issues = [i for i in issues if i["file"] == "MASTER-PROMPT.md"]
        assert mp_issues == []

    def test_cache_true_without_org_id_flagged(self):
        product = self._mk_product(
            ai_service=(
                "from noctusai_lib.integrations.llm import chat_completion\n"
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
                "from noctusai_lib.integrations.llm import chat_completion\n"
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
                "from noctusai_lib.integrations.llm import chat_completion\n"
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


# ---------------------------------------------------------------------------
# `check_no_self_monkeypatch` — neutering-our-own-symbols detector
# ---------------------------------------------------------------------------

class TestCheckNoSelfMonkeypatch:
    def _mk_repo_with_test(self, content: str, filename: str = "test_x.py") -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="self_patch_test_"))
        (tmp / "products" / "p1" / "backend" / "tests").mkdir(parents=True)
        (tmp / "products" / "p1" / "backend" / "tests" / filename).write_text(content)
        return tmp

    def test_flags_monkeypatch_setattr_on_our_module(self):
        content = (
            "import pytest\n"
            "from app.services import ai_pipeline\n\n"
            "def test_thing(monkeypatch):\n"
            "    monkeypatch.setattr(ai_pipeline, 'require', lambda *a, **k: None)\n"
        )
        repo = self._mk_repo_with_test(content)
        issues = check_no_self_monkeypatch(repo)
        assert len(issues) == 1
        assert "ai_pipeline.require" in issues[0]["issue"]

    def test_flags_patch_object_on_our_module(self):
        content = (
            "from unittest.mock import patch\n"
            "from app.services import ai_pipeline\n\n"
            "def test_thing():\n"
            "    with patch.object(ai_pipeline, 'require', lambda *a, **k: None):\n"
            "        pass\n"
        )
        repo = self._mk_repo_with_test(content)
        issues = check_no_self_monkeypatch(repo)
        assert len(issues) == 1

    def test_flags_string_form_patch_on_our_module(self):
        content = (
            "from unittest.mock import patch\n\n"
            "def test_thing():\n"
            "    with patch('app.services.ai_pipeline.require', lambda *a, **k: None):\n"
            "        pass\n"
        )
        repo = self._mk_repo_with_test(content)
        issues = check_no_self_monkeypatch(repo)
        assert len(issues) == 1

    def test_allows_boundary_accessor_get_client(self):
        # Patching `noctusai_seed.database.DatabaseModule.get_client` is the
        # legitimate way to mock the Supabase boundary — should NOT flag.
        content = (
            "from unittest.mock import patch\n\n"
            "def test_thing():\n"
            "    with patch('noctusai_seed.database.DatabaseModule.get_client', return_value=mock):\n"
            "        pass\n"
        )
        repo = self._mk_repo_with_test(content)
        issues = check_no_self_monkeypatch(repo)
        assert issues == [], f"get_client patch should be allowed, got: {issues}"

    def test_allows_external_lib_via_our_module(self):
        # `app.routers.X.httpx.AsyncClient` — httpx re-imported through our
        # module. Test is patching httpx behavior at the import site (legit).
        content = (
            "from unittest.mock import patch\n\n"
            "def test_thing():\n"
            "    with patch('app.routers.foo.httpx.AsyncClient'):\n"
            "        pass\n"
        )
        repo = self._mk_repo_with_test(content)
        issues = check_no_self_monkeypatch(repo)
        assert issues == [], f"httpx-via-ours patch should be allowed, got: {issues}"

    def test_allowlist_via_self_patch_ok_comment(self):
        content = (
            "from unittest.mock import patch\n\n"
            "def test_thing():\n"
            "    with patch('app.services.foo.bar'):  # self-patch-ok: legitimate edge case\n"
            "        pass\n"
        )
        repo = self._mk_repo_with_test(content)
        issues = check_no_self_monkeypatch(repo)
        assert issues == [], f"Inline allow-comment should suppress, got: {issues}"

    def test_does_not_flag_external_library_patch(self):
        content = (
            "from unittest.mock import patch\n\n"
            "def test_thing():\n"
            "    with patch('openai.OpenAI'):\n"
            "        pass\n"
        )
        repo = self._mk_repo_with_test(content)
        issues = check_no_self_monkeypatch(repo)
        assert issues == []

    def test_severity_is_warning(self):
        content = (
            "import pytest\n"
            "from app.services import ai_pipeline\n\n"
            "def test_thing(monkeypatch):\n"
            "    monkeypatch.setattr(ai_pipeline, 'require', lambda: None)\n"
        )
        repo = self._mk_repo_with_test(content)
        issues = check_no_self_monkeypatch(repo)
        assert all(i["severity"] == "warning" for i in issues)

    # -----------------------------------------------------------------------
    # Allowlist regression tests for boundary accessors added 2026-04-29 by
    # `execution-workflow-codequality-rollout` Phase 3 (therapy cleanup).
    # Each pins a real-world false-positive that motivated the entry.
    # -----------------------------------------------------------------------

    def test_allows_transcribe_audio_llm_boundary(self):
        """`noctusai_lib.integrations.llm.transcribe_audio` is the LLM transcription
        boundary (OpenAI Whisper / similar). Mocking it is the standard
        test pattern for skipping a real audio-API call. Caught 2026-04-29
        in `therapy/test_transcription_service.py` (4 sites)."""
        content = (
            "from unittest.mock import patch\n\n"
            "def test_thing():\n"
            "    with patch('noctusai_lib.integrations.llm.transcribe_audio', return_value='text'):\n"
            "        pass\n"
        )
        repo = self._mk_repo_with_test(content)
        issues = check_no_self_monkeypatch(repo)
        assert issues == [], f"transcribe_audio patch should be allowed, got: {issues}"

    def test_allows_lib_prefix_wrapper(self):
        """`_lib_*`-prefixed in-product wrappers proxy `noctusai_lib.*`
        external integrations. Patching them mocks the boundary, not our
        own logic. Caught 2026-04-29 in
        `therapy/test_therapy_embedding_service.py::_lib_generate_embedding`."""
        content = (
            "from unittest.mock import patch\n\n"
            "def test_thing():\n"
            "    with patch('app.services.therapy_embedding_service._lib_generate_embedding'):\n"
            "        pass\n"
        )
        repo = self._mk_repo_with_test(content)
        issues = check_no_self_monkeypatch(repo)
        assert issues == [], f"_lib_* wrapper patch should be allowed, got: {issues}"

    def test_allows_send_email_helper(self):
        """`send_*_email` are Resend / SMTP outbound-email helpers. Mocking
        the email send is the standard test pattern; the alternative is a
        real provider call. Caught 2026-04-29 in
        `therapy/test_invitations_router.py::send_product_invitation_email`
        (8 sites across invitations + e2e)."""
        content = (
            "from unittest.mock import patch\n\n"
            "def test_thing():\n"
            "    with patch('app.routers.invitations.send_product_invitation_email'):\n"
            "        pass\n"
        )
        repo = self._mk_repo_with_test(content)
        issues = check_no_self_monkeypatch(repo)
        assert issues == [], f"send_*_email patch should be allowed, got: {issues}"

    def test_lib_prefix_does_not_overshoot_to_unrelated(self):
        """Negative case: a function that contains `_lib_` MID-NAME but
        doesn't START with it (e.g. `parse_lib_response`) is NOT a wrapper
        and SHOULD still flag."""
        content = (
            "from unittest.mock import patch\n\n"
            "def test_thing():\n"
            "    with patch('app.services.foo.parse_lib_response'):\n"
            "        pass\n"
        )
        repo = self._mk_repo_with_test(content)
        issues = check_no_self_monkeypatch(repo)
        assert len(issues) == 1, (
            f"parse_lib_response is NOT a wrapper, must flag, got: {issues}"
        )

    def test_send_email_does_not_overshoot_to_other_send_funcs(self):
        """Negative case: `send_message` is NOT an email helper and SHOULD
        still flag (the regex requires `_email` suffix)."""
        content = (
            "from unittest.mock import patch\n\n"
            "def test_thing():\n"
            "    with patch('app.services.foo.send_message'):\n"
            "        pass\n"
        )
        repo = self._mk_repo_with_test(content)
        issues = check_no_self_monkeypatch(repo)
        assert len(issues) == 1, (
            f"send_message is NOT email boundary, must flag, got: {issues}"
        )

    # ---- Severity ratchet (per `KB § PATTERNS/testing.md § Severity ratchet`)

    def _mk_product_test_file(self, product: str, content: str) -> Path:
        """Build a tmp repo with a test file under products/<product>/backend/tests/."""
        tmp = Path(tempfile.mkdtemp(prefix="self_patch_ratchet_"))
        (tmp / "products" / product / "backend" / "tests").mkdir(parents=True)
        (tmp / "products" / product / "backend" / "tests" / "test_x.py").write_text(content)
        return tmp

    def test_severity_warning_for_non_ratcheted_product(self):
        """ERP is still draining historical debt → severity stays `warning`."""
        content = (
            "from unittest.mock import patch\n\n"
            "def test_x():\n"
            "    with patch('app.services.svc.helper'):\n"
            "        pass\n"
        )
        repo = self._mk_product_test_file("erp-imobiliario", content)
        issues = check_no_self_monkeypatch(repo)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning", (
            f"erp-imobiliario is NOT in the ratchet set yet — must stay warning, "
            f"got: {issues[0]['severity']}"
        )

    def test_severity_high_for_ratcheted_product(self):
        """therapy-platform reached 0 self-monkeypatches → ratcheted to `high`.

        Any new violation in therapy-platform must block CI (severity=high)
        so the cleanly-zero state can't drift back into debt.
        """
        content = (
            "from unittest.mock import patch\n\n"
            "def test_x():\n"
            "    with patch('app.services.svc.helper'):\n"
            "        pass\n"
        )
        repo = self._mk_product_test_file("therapy-platform", content)
        issues = check_no_self_monkeypatch(repo)
        assert len(issues) == 1
        assert issues[0]["severity"] == "high", (
            f"therapy-platform is in the ratchet set — must be high, got: "
            f"{issues[0]['severity']}"
        )


# ---------------------------------------------------------------------------
# `check_silent_errors` — silent-failure detector
# ---------------------------------------------------------------------------

class TestCheckSilentErrors:
    def _mk_product_with_file(self, py_content: str, filename: str = "service.py") -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="silent_errors_test_"))
        (tmp / "products" / "p1" / "backend" / "app" / "services").mkdir(parents=True)
        (tmp / "products" / "p1" / "backend" / "app" / "services" / filename).write_text(py_content)
        return tmp

    def test_flags_except_pass(self):
        content = (
            "def foo():\n"
            "    try:\n"
            "        risky()\n"
            "    except Exception:\n"
            "        pass\n"
        )
        repo = self._mk_product_with_file(content)
        issues = check_silent_errors(repo)
        assert len(issues) == 1
        assert "swallows errors silently" in issues[0]["issue"]

    def test_flags_except_return_none(self):
        content = (
            "def foo():\n"
            "    try:\n"
            "        risky()\n"
            "    except Exception:\n"
            "        return None\n"
        )
        repo = self._mk_product_with_file(content)
        issues = check_silent_errors(repo)
        assert len(issues) == 1

    def test_does_not_flag_logged_handler(self):
        content = (
            "import logging\n"
            "logger = logging.getLogger(__name__)\n\n"
            "def foo():\n"
            "    try:\n"
            "        risky()\n"
            "    except Exception as exc:\n"
            "        logger.warning(f'risky failed: {exc}')\n"
        )
        repo = self._mk_product_with_file(content)
        issues = check_silent_errors(repo)
        assert issues == []

    def test_does_not_flag_re_raising_handler(self):
        content = (
            "def foo():\n"
            "    try:\n"
            "        risky()\n"
            "    except Exception:\n"
            "        raise\n"
        )
        repo = self._mk_product_with_file(content)
        issues = check_silent_errors(repo)
        assert issues == []

    def test_silent_ok_comment_does_NOT_suppress(self):
        # The `# silent-ok` escape hatch was retired 2026-04-28 per user
        # directive: "i dont want any silent-ok sign accross the platform".
        # The detector now flags `except: pass` regardless of the comment;
        # the only valid response is a real `logger.<level>(...)` / `raise` /
        # error-bearing return value. This test pins the new behavior so the
        # escape hatch can't sneak back in.
        content = (
            "def foo():\n"
            "    try:\n"
            "        risky()\n"
            "    except Exception:  # silent-ok: this comment used to suppress\n"
            "        pass\n"
        )
        repo = self._mk_product_with_file(content)
        issues = check_silent_errors(repo)
        assert len(issues) == 1
        assert "swallows errors silently" in issues[0]["issue"]
        assert "There is no `# silent-ok` escape hatch" in issues[0]["issue"]

    def test_skips_test_files(self):
        # Even though tests have try/except patterns, the walk excludes them.
        tmp = Path(tempfile.mkdtemp(prefix="silent_skips_tests_"))
        (tmp / "products" / "p1" / "backend" / "tests").mkdir(parents=True)
        (tmp / "products" / "p1" / "backend" / "tests" / "test_x.py").write_text(
            "def test_x():\n    try:\n        x()\n    except Exception: pass\n"
        )
        issues = check_silent_errors(tmp)
        assert issues == []

    def test_severity_is_warning(self):
        content = "def foo():\n    try: x()\n    except: pass\n"
        repo = self._mk_product_with_file(content)
        issues = check_silent_errors(repo)
        assert all(i["severity"] == "warning" for i in issues)

    def test_legacy_logger_warn_alias_recognized(self):
        # `_log.warn(...)` is the deprecated stdlib alias for `_log.warning(...)`.
        # Detector must recognize it so legacy modules don't get false-flagged.
        # Caught in code review 2026-04-28 (item D1).
        content = (
            "import logging\n"
            "_log = logging.getLogger(__name__)\n"
            "def foo():\n"
            "    try:\n"
            "        risky()\n"
            "    except Exception as exc:\n"
            "        _log.warn('legacy alias %s', exc)\n"
        )
        repo = self._mk_product_with_file(content)
        issues = check_silent_errors(repo)
        assert issues == []

    def test_bare_name_warn_does_NOT_suppress(self):
        # A bare-name `warn(exc)` (no logger attribute) is too easy to
        # satisfy by a domain function of the same name. Detector must
        # only accept `print(...)` as a bare-name signal. Caught in code
        # review 2026-04-28 (item D1).
        content = (
            "def warn(*a, **k): pass  # domain function, NOT a logger\n"
            "def foo():\n"
            "    try:\n"
            "        risky()\n"
            "    except Exception as exc:\n"
            "        warn(exc)\n"
        )
        repo = self._mk_product_with_file(content)
        issues = check_silent_errors(repo)
        assert len(issues) == 1
        assert "swallows errors silently" in issues[0]["issue"]

    def test_print_bare_name_is_recognized(self):
        # `print(exc, file=sys.stderr)` is the legitimate CLI-script
        # surface for "logger isn't configured yet". Stays allowlisted.
        content = (
            "import sys\n"
            "def foo():\n"
            "    try:\n"
            "        risky()\n"
            "    except Exception as exc:\n"
            "        print(f'failed: {exc}', file=sys.stderr)\n"
        )
        repo = self._mk_product_with_file(content)
        issues = check_silent_errors(repo)
        assert issues == []


# ---------------------------------------------------------------------------
# `check_clean_folder_violations` — closed-but-not-deleted folder detector
# ---------------------------------------------------------------------------

class TestCheckCleanFolderViolations:
    def _mk_project(self, status_line: str, slug: str = "p1") -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="clean_folder_test_"))
        (tmp / "projects" / slug).mkdir(parents=True)
        (tmp / "projects" / slug / "PROJECT.md").write_text(
            f"# Project\n\n- **Status:** {status_line}\n\n## 6.\n## 11. Change log\n"
        )
        return tmp

    def test_flags_closed_project_with_existing_folder(self):
        repo = self._mk_project("✅ All phases shipped 2026-04-25.")
        issues = check_clean_folder_violations(repo)
        assert len(issues) == 1
        assert "closed (✅) but its folder still exists" in issues[0]["issue"]

    def test_does_not_flag_partial_status(self):
        repo = self._mk_project("⏳ executing")
        issues = check_clean_folder_violations(repo)
        assert issues == []

    def test_does_not_flag_parked_status(self):
        repo = self._mk_project("🅿️ PARKED")
        issues = check_clean_folder_violations(repo)
        assert issues == []

    def test_does_not_flag_mixed_status_with_inflight_marker(self):
        # A project closing via `✅` but ALSO carrying `⏳` in status text
        # (transitional state) should not flag — the user is mid-close.
        repo = self._mk_project("✅ closed but ⏳ awaiting cleanup")
        issues = check_clean_folder_violations(repo)
        assert issues == []

    def test_severity_is_warning(self):
        repo = self._mk_project("✅ done")
        issues = check_clean_folder_violations(repo)
        assert all(i["severity"] == "warning" for i in issues)

    def test_does_not_flag_paused_with_phase_checkmark_in_narrative(self):
        # A status line whose LEADING icon is 📋/⏳ but whose narrative
        # mentions `Phase 0 ✅` should NOT flag — the project isn't closed,
        # an internal phase happens to be done. False positive caught
        # 2026-04-28 against `repo-state-consolidation`.
        repo = self._mk_project(
            "📋 **READY TO RESUME (paused 2026-04-28).** Phase 0 ✅ "
            "executed; will resume on user signal."
        )
        issues = check_clean_folder_violations(repo)
        assert issues == []


# ---------------------------------------------------------------------------
# `check_section_7_placeholder_consistency` — flags PROJECT.md files where
# §7 claims questions are answered but §2 still carries the unfilled
# `_Interrogate the user before filling_` template placeholder.
# ---------------------------------------------------------------------------


class TestCheckSection7PlaceholderConsistency:
    """Surfaced 2026-05-03 from `projects/side-projects-batch/` Phase 0
    audit — three Tier-1 children carried §7 "all answered" while §2 was
    still a placeholder. Detector formalizes the check."""

    def _mk_project(self, section_2: str, section_7: str, slug: str = "p1") -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="s7_placeholder_test_"))
        (tmp / "projects" / slug).mkdir(parents=True)
        body = (
            f"# Project\n\n- **Status:** ⏳\n\n"
            f"## 1. Context\n\nfoo\n\n---\n\n"
            f"## 2. Confirmed constraints\n\n{section_2}\n\n---\n\n"
            f"## 3. Design\n\nfoo\n\n---\n\n"
            f"## 6. Phases\n\nphase\n\n---\n\n"
            f"## 7. Open questions\n\n{section_7}\n\n---\n\n"
            f"## 8. Deps\n\nx\n\n---\n\n"
            f"## 11. Change log\n\n| Date | x | y |\n"
        )
        (tmp / "projects" / slug / "PROJECT.md").write_text(body)
        return tmp

    def test_flags_when_s7_answered_but_s2_placeholder(self):
        repo = self._mk_project(
            section_2="_Interrogate the user before filling. Candidate questions:_\n- one\n- two",
            section_7="See §2 — all answered at interrogation time.",
        )
        issues = check_section_7_placeholder_consistency(repo)
        assert len(issues) == 1
        assert "answered" in issues[0]["issue"].lower()
        assert issues[0]["severity"] == "high"

    def test_does_not_flag_when_both_filled(self):
        repo = self._mk_project(
            section_2=(
                "- **Cadence** — daily, configurable. *(Q3 answered.)*\n"
                "- **Scope** — recording-only v1."
            ),
            section_7=(
                "All §7 questions resolved 2026-05-03. See §2 for answers."
            ),
        )
        issues = check_section_7_placeholder_consistency(repo)
        assert issues == []

    def test_does_not_flag_when_both_placeholders(self):
        """Both unfilled is consistent — the project hasn't been
        interrogated yet, and §7 carries the open-questions list."""
        repo = self._mk_project(
            section_2="_Interrogate the user before filling._",
            section_7=(
                "1. **Q1** — first question. *Recommendation:* foo.\n"
                "2. **Q2** — second question. *Recommendation:* bar."
            ),
        )
        issues = check_section_7_placeholder_consistency(repo)
        assert issues == []

    def test_flags_alternate_placeholder_phrasings(self):
        """The detector recognizes multiple template-default phrasings
        for both §7 ("answered at interrogation time") and §2
        ("_TBD after interrogation_", "(filled at Phase 0 interrogation)")."""
        repo = self._mk_project(
            section_2="_(filled at Phase 0 interrogation)_",
            section_7="See §2 — all answered.",
        )
        issues = check_section_7_placeholder_consistency(repo)
        assert len(issues) == 1

    def test_real_repo_clean(self):
        """The current repo must satisfy this rule — no PROJECT.md should
        carry the placeholder mismatch at HEAD."""
        issues = check_section_7_placeholder_consistency()
        assert issues == [], (
            f"Active §7-placeholder violations: "
            f"{[(i['file'], i['issue']) for i in issues]}"
        )


# ---------------------------------------------------------------------------
# `check_detector_has_regression_test` — every keeper detector ships with a
# colocated test class. The detector is itself a detector, so it tests
# itself by running against the real repo and asserting zero issues.
# ---------------------------------------------------------------------------


class TestCheckDetectorHasRegressionTest:
    """Pin the platform-wide methodology: every `check_*` keeper detector
    in `mcp/noctusai/tools/compliance.py` must have a regression test.
    Per KB § PATTERNS/testing.md § Regression-test-the-detector.

    Origin: 2026-04-29 — `platform-logging-standardization` Phase 6.
    User directive: regression-test-the-detector becomes platform-wide
    methodology, integrated into the code validation system. The new
    detector enforces it; this test pins the contract.
    """

    def test_real_repo_passes(self):
        """The current repo MUST satisfy the rule. If this fails, a new
        detector was added to compliance.py without a regression test —
        either add the test or map it via `_DETECTOR_TEST_OVERRIDES`."""
        issues = check_detector_has_regression_test()
        assert issues == [], (
            f"Detectors missing regression tests: "
            f"{[i['issue'].split('`')[1] for i in issues]}"
        )

    def test_severity_is_high(self):
        """When violated, severity is `high` — a missing detector test is
        the kind of gap that lets a real-world miss ship undetected."""
        # Construct a fake repo where compliance.py exists but tests/ is
        # empty. Every detector becomes a violation; severity must be `high`.
        with tempfile.TemporaryDirectory() as tmp:
            fake_root = Path(tmp)
            (fake_root / "mcp" / "noctusai" / "tools" / "noctus" / "dev").mkdir(parents=True)
            (fake_root / "mcp" / "noctusai" / "tests").mkdir(parents=True)
            # Copy the real compliance.py so `_detector_function_names()`
            # finds the same set of detectors.
            real_compliance = (
                Path(__file__).resolve().parents[1]
                / "tools" / "noctus" / "dev" / "compliance.py"
            )
            (fake_root / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "compliance.py").write_text(
                real_compliance.read_text(encoding="utf-8"), encoding="utf-8"
            )
            # No test files at all — every detector should flag.
            # Note: detector reads its OWN file via `Path(__file__)`, not
            # `repo_root`. So we still get the real list of detectors. The
            # `repo_root` arg only changes where it LOOKS for tests.
            issues = check_detector_has_regression_test(fake_root)
            assert issues, "expected violations when tests dir is empty"
            assert all(i["severity"] == "high" for i in issues), (
                f"severities seen: {set(i['severity'] for i in issues)}"
            )

    def test_message_names_the_detector_and_expected_class(self):
        """The issue message must name (a) the detector and (b) the
        expected test-class name, so the fix is a copy-paste."""
        with tempfile.TemporaryDirectory() as tmp:
            fake_root = Path(tmp)
            (fake_root / "mcp" / "noctusai" / "tools" / "noctus" / "dev").mkdir(parents=True)
            (fake_root / "mcp" / "noctusai" / "tests").mkdir(parents=True)
            real_compliance = (
                Path(__file__).resolve().parents[1]
                / "tools" / "noctus" / "dev" / "compliance.py"
            )
            (fake_root / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "compliance.py").write_text(
                real_compliance.read_text(encoding="utf-8"), encoding="utf-8"
            )
            issues = check_detector_has_regression_test(fake_root)
            for issue in issues:
                msg = issue["issue"]
                # Message contains a detector name in backticks.
                assert "`check_" in msg, msg
                # Message contains an expected `Test*` class name.
                assert "class Test" in msg, msg
                # Message references the platform rule.
                assert "Regression-test-the-detector" in msg, msg
