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
    check_conflict_markers,
    check_detector_has_regression_test,
    check_migration_number_collision,
    check_postgrest_schema_qualified_table,
    check_primary_checkout_commit,
    check_section_7_placeholder_consistency,
    check_slowapi_with_pep563,
    check_seed_canonical_default,
    check_query_fn_returns_undefined,
    check_derives_from_dev_only_artifact,
    check_root_requirements_superset,
    check_limiter_conftest_import,
    check_playwright_supabase_env,
    check_rls_policy_self_reference,
    check_auth_session_mutation_on_shared_client,
    check_product_service_worker,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PRODUCTS_DIR = REPO_ROOT / "products"


# ---------------------------------------------------------------------------
# Regression-gate helpers (Option A — `projects/platform-compliance-baseline`
# §7(A), locked 2026-05-18). The 2 platform-health gate tests assert "no NEW
# high/critical vs the committed baseline"; the absolute score is informational.
# `fingerprint` / `is_env_artifact` / `live_high_critical_fingerprints` are
# imported from the colocated regenerator so the gate and the baseline-refresh
# compute the live set identically (single source of truth — no drift).
# ---------------------------------------------------------------------------
import importlib.util as _ilu
import json as _json

# Load the colocated regenerator by explicit file path WITHOUT mutating the
# global sys.path — a tests/-dir sys.path insert shadows the real `google`
# SDK for sibling llm test modules (caught 2026-05-18). importlib keeps the
# import contained to this module.
_rcb_spec = _ilu.spec_from_file_location(
    "refresh_compliance_baseline",
    str(Path(__file__).resolve().parent / "refresh_compliance_baseline.py"),
)
_rcb = _ilu.module_from_spec(_rcb_spec)
_rcb_spec.loader.exec_module(_rcb)
_BASELINE_PATH = _rcb.BASELINE_PATH
fingerprint = _rcb.fingerprint
is_env_artifact = _rcb.is_env_artifact
live_high_critical_fingerprints = _rcb.live_high_critical_fingerprints


def _load_baseline_fingerprints() -> set[str]:
    data = _json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
    return set(data["fingerprints"])


class TestEnvArtifactExclusion:
    """`is_env_artifact` excludes non-deterministic / worktree-specific issue
    classes from BOTH the committed baseline and the live regression gate, so
    the gate cannot flap on stamp-lag / wall-clock / fresh-worktree state.
    Per `KB § PATTERNS/compliance/compliance-regression-baseline.md`.
    """

    def test_seed_drift_prefix_excluded(self):
        assert is_env_artifact(
            "Seed drift: installed `noctusai_seed.__seed_version__` is 'abc' but …"
        )

    def test_archive_and_dispatcher_prefixes_excluded(self):
        assert is_env_artifact("Archive entry `projects/x` is 99 days old …")
        assert is_env_artifact("Dispatcher pending entry `…` is stale …")

    def test_seed_version_stamp_absent_excluded(self):
        """The gitignored `_version_static.py` stamp is ABSENT in a fresh
        worktree ⇒ a worktree-scoped scan flags it as a false `critical`. It is
        an environment artifact (where the scan ran), NOT a code regression, so
        it must be excluded — even though the package name (not a prefix)
        LEADS the issue text (substring class, added 2026-05-25)."""
        absent = (
            "`noctusai_seed` has no `_version_static.py` stamp AND is not "
            "installed in this venv. Run `python mcp/noctusai/cli.py "
            "--stamp-seed-version` to write the stamp, or `pip install -e …`."
        )
        assert is_env_artifact(absent), absent
        # The lib sibling variant is equally excluded.
        assert is_env_artifact(
            "`noctusai_lib` has no `_version_static.py` stamp AND is not installed …"
        )

    def test_normal_high_critical_issue_not_excluded(self):
        """A real wiring/code issue is NOT treated as an env artifact (the
        exclusion is narrow — it must not swallow genuine regressions)."""
        real = (
            "FE calls `api.get('/api/subscriptions')` but no backend route "
            "matches (method=GET, normalized=/api/subscriptions)."
        )
        assert not is_env_artifact(real), real

    def test_seed_stamp_not_in_committed_baseline(self):
        """Belt-and-suspenders: no `_version_static.py` fingerprint leaked into
        the committed baseline (it is excluded, so it must never be pinned)."""
        for fp in _load_baseline_fingerprints():
            assert "_version_static.py" not in fp, fp


class TestSeedCompliance:
    def test_seed_product_is_compliant(self):
        issues = check_seed_compliance(PRODUCTS_DIR / "seed")
        assert len(issues) == 0, f"Seed has issues: {issues}"

    def test_mailing_is_compliant(self):
        issues = check_seed_compliance(PRODUCTS_DIR / "mailing")
        assert len(issues) == 0, f"Mailing has issues: {issues}"
    def test_all_products_compliant(self):
        """Platform-wide compliance REGRESSION gate (Option A — locked
        2026-05-18 by the user, ``projects/platform-compliance-baseline``
        §7(A)).

        The old ``score == 100`` gate was aspirational, not a regression
        detector: every new keeper detector retroactively surfaces old
        pre-existing debt and would red CI. Re-spec:

          * GATE = **no NEW high/critical issue** vs the committed
            ``tests/compliance_baseline.json`` fingerprint set.
          * The absolute platform score is tracked **informationally**
            (printed via ``capsys``/stdout, NEVER asserted).

        Refresh the baseline only via
        ``tests/refresh_compliance_baseline.py`` when debt is intentionally
        resolved (shrink) or a new class is triaged-accepted (grow, with a
        cited decision). See that file's header.
        """
        score, live_fps = live_high_critical_fingerprints()
        baseline = _load_baseline_fingerprints()
        new_high_critical = sorted(set(live_fps) - baseline)
        # Informational only — the absolute score is NOT a gate under (A).
        print(
            f"[compliance][informational] platform absolute score={score} "
            f"high/critical-fingerprints live={len(live_fps)} "
            f"baseline={len(baseline)} regressions={len(new_high_critical)}"
        )
        assert not new_high_critical, (
            "NEW high/critical compliance issue(s) vs the committed baseline "
            "(regression — fix the new issue, do NOT silently grow the "
            f"baseline): {new_high_critical}. Absolute score (informational): "
            f"{score}."
        )

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
        """All live products pass the AI-feature-completeness detector, AND
        no NEW high/critical compliance regression vs the committed baseline.

        Re-spec 2026-05-18 (Option A — ``projects/platform-compliance-
        baseline`` §7(A)): the broad ``score == 100`` assertion is replaced
        by the regression gate (no NEW high/critical vs
        ``tests/compliance_baseline.json``); the absolute score is
        informational. The narrow AI-feature intent is unchanged.
        """
        score, issues = check_all_products()
        # Narrow intent (unchanged): AI-feature-completeness detector finds
        # no issues in shipped Tier 1 features.
        ai_feature_issues = [
            i for i in issues
            if "Tier 1" in i.get("issue", "")
            or "ai_feature" in i.get("issue", "").lower()
        ]
        assert ai_feature_issues == [], (
            f"AI feature completeness issues: {ai_feature_issues}"
        )
        # Broad intent (re-spec): regression semantics, not score==100.
        live_fps = sorted({
            fingerprint(i) for i in issues
            if i.get("severity") in ("high", "critical")
            and not is_env_artifact(i.get("issue", ""))
        })
        baseline = _load_baseline_fingerprints()
        new_high_critical = sorted(set(live_fps) - baseline)
        print(
            f"[compliance][informational] platform absolute score={score} "
            f"regressions={len(new_high_critical)}"
        )
        assert not new_high_critical, (
            "NEW high/critical compliance issue(s) vs the committed baseline "
            f"(regression — investigate): {new_high_critical}. Absolute "
            f"score (informational): {score}."
        )


# ---------------------------------------------------------------------------
# Phase-state consistency — §6 ↔ §11 drift detector
# ---------------------------------------------------------------------------

class TestPhaseStateConsistency:
    """Detector for §6 ↔ §11 drift in PROJECT.md files.

    Slip pattern: agent writes a §11 entry saying "Phase N ✅ shipped" but
    leaves §6 sub-task checkboxes / phase header in pre-close state. The
    user reads §6 as a real-time dashboard; the mismatch is a documented
    lie about progress. Per `KB § PATTERNS/architect/project-execution.md § 2`.
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

    def test_header_flipped_but_improvements_block_unfilled_placeholder(self):
        """Rule 5: header has ✅ AND an `**Improvements:**` block, but the block
        still carries the template's unfilled `NOC-FILL-IMPROVEMENTS` placeholder —
        i.e. the obligatory block shipped but was never filled."""
        content = (
            "# Test\n\n"
            "## 6. Implementation phases\n\n"
            "### Phase 1 — Foo ✅\n"
            "- [x] Did it\n\n"
            "**Improvements:** _NOC-FILL-IMPROVEMENTS — REQUIRED before this phase "
            "flips ✅: replace with the improvements spotted, or \"none identified.\"_\n\n"
            "## 11. Change log\n\n"
        )
        repo = self._mk_repo(content)
        issues = check_phase_state_consistency(repo)
        assert any("unfilled" in i["issue"] and "placeholder" in i["issue"] for i in issues), issues
        assert all(i["severity"] == "high" for i in issues if "placeholder" in i["issue"])

    def test_improvements_block_filled_none_identified_is_clean(self):
        """A ✅ phase whose Improvements block is filled with the sanctioned
        `none identified.` (NOT the placeholder) is clean under Rule 5."""
        content = (
            "# Test\n\n"
            "## 6. Implementation phases\n\n"
            "### Phase 1 — Foo ✅\n"
            "- [x] Did it\n\n"
            "**Improvements:** none identified.\n\n"
            "## 11. Change log\n\n"
            "| 2026-05-25 | Phase 1 ✅ shipped | agent |\n"
        )
        repo = self._mk_repo(content)
        issues = check_phase_state_consistency(repo)
        assert not any("placeholder" in i["issue"] for i in issues), issues

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

    def test_backticked_cross_file_phase_reference_does_not_self_claim(self):
        """Backticked references describe ANOTHER file's state — not a self-claim.

        Slip pattern this guards: while authoring a §11 entry that describes
        another project's state (e.g. "flagged `Phase 0 ✅` in erp-imobiliario-
        wiring"), the bare regex used to false-positive the reference as a
        self-claim. Wrapping in backticks per markdown convention now suppresses
        the match. See `_strip_code_spans` in compliance.py.
        """
        content = (
            "# Test\n\n"
            "## 6. Implementation phases\n\n"
            "### Phase 0 — Audit\n"
            "- [ ] Pre-flight\n\n"
            "## 11. Change log\n\n"
            "| 2026-05-03 | Investigation flagged `Phase 0 ✅` of "
            "`products/erp-imobiliario/projects/erp-imobiliario-wiring/PROJECT.md` "
            "as missing the Improvements block. Cross-file reference, not self-claim. | agent |\n"
        )
        repo = self._mk_repo(content)
        issues = check_phase_state_consistency(repo)
        # The backticked `Phase 0 ✅` describes another file — should not trigger
        # rule 1 (header-missing-✅-but-§11-says-shipped) on THIS file's Phase 0.
        assert issues == [], f"Backticked cross-file ref should not self-claim, got: {issues}"

    def test_backticked_phase_n_closed_does_not_self_claim(self):
        """Same guard as above, but for 'Phase N closed' / 'Phase N shipped'."""
        content = (
            "# Test\n\n"
            "## 6. Implementation phases\n\n"
            "### Phase 1 — Foo\n"
            "- [ ] Pending\n\n"
            "## 11. Change log\n\n"
            "| 2026-05-03 | Comparing approach against `Phase 1 closed` of sister-project; "
            "lessons folded in. | agent |\n"
        )
        repo = self._mk_repo(content)
        issues = check_phase_state_consistency(repo)
        assert issues == [], f"Backticked 'Phase 1 closed' ref should not self-claim, got: {issues}"

    def test_mixed_self_claim_and_backticked_reference(self):
        """A §11 entry can BOTH self-claim Phase N AND reference another file's Phase M.

        The self-claim must still trigger; the backticked ref must not.
        """
        content = (
            "# Test\n\n"
            "## 6. Implementation phases\n\n"
            "### Phase 2 — Bar\n"
            "- [x] Done\n\n"
            "**Improvements:** ok.\n\n"
            "## 11. Change log\n\n"
            "| 2026-05-03 | Phase 2 ✅ shipped here. Approach borrowed from "
            "`Phase 0 ✅` of sister-project. | agent |\n"
        )
        repo = self._mk_repo(content)
        issues = check_phase_state_consistency(repo)
        # Phase 2 is in §11 (self-claim, unbacked) but §6 lacks ✅ — rule 1 fires.
        # Phase 0 is in §11 backticked (reference) — must NOT trigger rule 1.
        rule1_issues = [i for i in issues if "lacks the `✅` icon" in i["issue"]]
        assert any("Phase 2" in i["issue"] for i in rule1_issues), \
            f"Phase 2 self-claim should fire rule 1, got: {issues}"
        assert not any("Phase 0" in i["issue"] for i in rule1_issues), \
            f"Phase 0 backticked reference must not self-claim, got: {issues}"

    def test_strip_code_spans_helper_isolated(self):
        """_strip_code_spans replaces inline code spans with a single space.

        Direct unit test of the helper to lock its behavior independent of the
        composite phase-state detector.
        """
        from tools.noctus.dev.compliance import _strip_code_spans
        # Self-claim survives.
        assert "Phase 0 ✅" in _strip_code_spans("Phase 0 ✅ shipped")
        # Backticked reference is stripped (replaced with space).
        assert "Phase 0 ✅" not in _strip_code_spans("ref `Phase 0 ✅` here")
        # Multi-line backtick (markdown forbids spanning lines) — survives.
        # The regex only matches single-line spans; a backtick at end-of-line
        # without a closing backtick on the same line is left untouched.
        assert "Phase 1" in _strip_code_spans("Phase 1 ✅\n`only-on-next-line`")
        # Empty input.
        assert _strip_code_spans("") == ""
        # Code span at boundaries.
        assert _strip_code_spans("`x` y `z`").strip() == "y"


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

    # ---- Severity ratchet (per `KB § PATTERNS/compliance/testing.md § Severity ratchet`)

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
# `check_no_self_monkeypatch` — connector-namespace blind spot (Finding #10,
# found `mcp/n8n/build`). Pre-fix, NO `mcp/<vendor>` connector namespace
# (`n8n.*`, `waha.*`, `github.*`, ...) was ever "ours" — a test could
# monkeypatch a connector's own business logic (e.g.
# `n8n.tools.credential.credential_create`, bypassing the real adapter
# seam) and the detector stayed silent. These pin the fix: the connector
# namespace IS "ours" (patches to connector business logic flag), while the
# per-connector HTTP/subprocess/env-config BOUNDARY accessors stay allowed
# (the sanctioned "mock the network, not our logic" pattern every connector
# docstring documents) — and the `mcp/supabase` / `mcp/google` collision
# with the real external SDK top-level names is deliberately NOT swept in.
# ---------------------------------------------------------------------------

class TestCheckNoSelfMonkeypatchConnectorNamespaces:
    def _mk_connector_repo(
        self, vendor: str, content: str, filename: str = "test_x.py"
    ) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="self_patch_connector_"))
        (tmp / "mcp" / vendor).mkdir(parents=True)
        (tmp / "mcp" / vendor / "__init__.py").write_text("")
        (tmp / "mcp" / vendor / "tests").mkdir(parents=True)
        (tmp / "mcp" / vendor / "tests" / filename).write_text(content)
        return tmp

    def test_flags_connector_business_logic_string_patch(self):
        """Reproduces the blind spot: `n8n.tools.credential.credential_create`
        is the connector's own tool implementation (not the HTTP boundary) —
        patching it defeats the Fake/Real seam and must be flagged."""
        content = (
            "from unittest.mock import patch\n\n"
            "def test_thing():\n"
            "    with patch('n8n.tools.credential.credential_create'):\n"
            "        pass\n"
        )
        repo = self._mk_connector_repo("n8n", content)
        issues = check_no_self_monkeypatch(repo)
        assert len(issues) == 1, f"connector business-logic patch must flag, got: {issues}"
        assert "n8n.tools.credential.credential_create" in issues[0]["issue"]

    def test_flags_connector_business_logic_monkeypatch_setattr_via_import_map(self):
        """Same gap via `monkeypatch.setattr` + a local import alias — the
        import-map resolution must also see the connector namespace as ours."""
        content = (
            "from n8n.tools import credential\n\n"
            "def test_thing(monkeypatch):\n"
            "    monkeypatch.setattr(credential, 'credential_create', lambda *a, **k: None)\n"
        )
        repo = self._mk_connector_repo("n8n", content)
        issues = check_no_self_monkeypatch(repo)
        assert len(issues) == 1, f"must flag via import-map resolution too, got: {issues}"
        assert "n8n.tools.credential.credential_create" in issues[0]["issue"]

    def test_allows_n8n_http_boundary_request_json(self):
        """`n8n.api.request_json` is the connector's single HTTP boundary
        (every `mcp/<vendor>/api.py` docstring sanctions mocking it) — must
        stay allowed even though `n8n.*` is now "ours"."""
        content = (
            "from unittest.mock import patch\n\n"
            "def test_thing():\n"
            "    with patch('n8n.api.request_json'):\n"
            "        pass\n"
        )
        repo = self._mk_connector_repo("n8n", content)
        issues = check_no_self_monkeypatch(repo)
        assert issues == [], f"request_json boundary patch should be allowed, got: {issues}"

    def test_allows_cloudflare_request_envelope_boundary(self):
        """`request_envelope` is cloudflare's sibling HTTP boundary (the
        pagination-envelope variant of `request_json`)."""
        content = (
            "from unittest.mock import patch\n\n"
            "def test_thing():\n"
            "    with patch('cloudflare.api.request_envelope'):\n"
            "        pass\n"
        )
        repo = self._mk_connector_repo("cloudflare", content)
        issues = check_no_self_monkeypatch(repo)
        assert issues == [], f"request_envelope boundary patch should be allowed, got: {issues}"

    def test_allows_connector_get_settings_boundary(self):
        """`get_settings()` is the shared `_kit.settings.make_get_settings`
        env/.env reader every connector's tools module imports — no business
        logic, same category as `get_whatsapp_config_from_env`."""
        content = (
            "from unittest.mock import patch\n\n"
            "def test_thing():\n"
            "    with patch('waha.tools.message.get_settings'):\n"
            "        pass\n"
        )
        repo = self._mk_connector_repo("waha", content)
        issues = check_no_self_monkeypatch(repo)
        assert issues == [], f"get_settings boundary patch should be allowed, got: {issues}"

    def test_allows_github_subprocess_boundary_run_gh(self):
        """`github.gh.run_gh` is the GitHub connector's subprocess boundary
        (shells out to the `gh` CLI instead of HTTP) — same sanctioned
        external-service-mock category as `request_json`."""
        content = (
            "from unittest.mock import patch\n\n"
            "def test_thing():\n"
            "    with patch('github.gh.run_gh'):\n"
            "        pass\n"
        )
        repo = self._mk_connector_repo("github", content)
        issues = check_no_self_monkeypatch(repo)
        assert issues == [], f"run_gh boundary patch should be allowed, got: {issues}"

    def test_allows_shared_kit_transport_urlopen_boundary(self):
        """`_kit.transport.urlopen` — the raw stdlib `urlopen` call site one
        level below the per-vendor `request_json` (patched directly by
        `mcp/hostinger` + `mcp/supabase` test_smoke.py)."""
        content = (
            "from unittest.mock import patch\n\n"
            "def test_thing():\n"
            "    with patch('_kit.transport.urlopen'):\n"
            "        pass\n"
        )
        repo = self._mk_connector_repo("_kit", content)
        issues = check_no_self_monkeypatch(repo)
        assert issues == [], f"_kit.transport.urlopen boundary patch should be allowed, got: {issues}"

    def test_does_not_treat_supabase_connector_dir_as_ours(self):
        """`mcp/supabase` shares its top-level import name with the REAL
        `supabase-py` SDK (already in `_EXTERNAL_LIB_NAMES`) — deliberately
        excluded from the "ours" prefix set to avoid misrouting genuine
        external-SDK patches into false-positive self-monkeypatch flags.
        Pins the exclusion so a future edit doesn't silently widen the
        connector-prefix discovery to a colliding name."""
        content = (
            "from unittest.mock import patch\n\n"
            "def test_thing():\n"
            "    with patch('supabase.some_internal_helper'):\n"
            "        pass\n"
        )
        repo = self._mk_connector_repo("supabase", content)
        issues = check_no_self_monkeypatch(repo)
        assert issues == [], (
            f"mcp/supabase must NOT be classified 'ours' (collides with the "
            f"real supabase-py SDK import name), got: {issues}"
        )

    def test_new_connector_directory_is_picked_up_without_code_change(self):
        """Derived-not-hand-maintained: a brand-new `mcp/<vendor>/` package
        (no code change to the detector) is immediately covered."""
        content = (
            "from unittest.mock import patch\n\n"
            "def test_thing():\n"
            "    with patch('brandnewvendor.tools.widget.do_the_thing'):\n"
            "        pass\n"
        )
        repo = self._mk_connector_repo("brandnewvendor", content)
        issues = check_no_self_monkeypatch(repo)
        assert len(issues) == 1, f"newly-added connector dir must be covered, got: {issues}"


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
# `check_seed_canonical_default` — seed fallback literals must be canonical-
# shared answers, never per-product-port coincidences. N=3 codification
# (2026-05-20). See compliance.py docstring + KB seed-canonical-defaults.md.
# ---------------------------------------------------------------------------

class TestCheckSeedCanonicalDefault:
    def _mk(self, content: str, rel_path: str) -> Path:
        """Build a fake repo with `start.sh` (registry) + one seed file."""
        tmp = Path(tempfile.mkdtemp(prefix="seed_canonical_default_test_"))
        # Minimal `start.sh` registry — just enough for the parser to find
        # the sentinels and one product row carrying port 8000.
        (tmp / "start.sh").write_text(
            "#!/bin/bash\n"
            "# BEGIN_PRODUCTS_REGISTRY\n"
            "PRODUCTS=(\n"
            '  "core:Core:8000:5173"\n'
            '  "erp-imobiliario:ERP:8001:8080"\n'
            ")\n"
            "# END_PRODUCTS_REGISTRY\n"
        )
        target = tmp / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return tmp

    # ── Pattern A: URL form ────────────────────────────────────────────

    def test_flags_url_fallback_with_double_pipe(self):
        repo = self._mk(
            'const url = env.X || "http://localhost:8000";\n',
            "seed/framework/frontend/src/infra.tsx",
        )
        issues = check_seed_canonical_default(repo)
        assert len(issues) == 1
        assert "URL literal as `||`/`??` fallback" in issues[0]["issue"]
        assert issues[0]["severity"] == "warning"
        assert issues[0]["product"] == "<seed>"

    def test_flags_url_fallback_with_nullish_coalescing(self):
        repo = self._mk(
            'const url = env.X ?? "http://localhost:8001";\n',
            "seed/framework/frontend/src/infra.tsx",
        )
        issues = check_seed_canonical_default(repo)
        assert len(issues) == 1
        assert "URL literal as `||`/`??` fallback" in issues[0]["issue"]

    def test_flags_python_or_url_fallback(self):
        # Pattern A is language-agnostic (both `or "url"` Python syntax and
        # JS `|| "url"` look identical at the regex level).
        repo = self._mk(
            'base = os.environ.get("X") or "http://localhost:8000"\n',
            "seed/lib/backend/noctusai_lib/example.py",
        )
        # Python uses `or`, not `||`, so Pattern A specifically should NOT
        # fire (the regex looks for `||`/`??`). This documents the intent:
        # the Python `or "url"` case is a *separate* gap — call this out.
        issues = check_seed_canonical_default(repo)
        assert issues == []

    # ── Pattern B: numeric port-literal fallback ───────────────────────

    def test_flags_numeric_port_fallback_from_registry(self):
        # 8000 IS in the test registry's backend ports → flagged.
        repo = self._mk(
            "const port = config.backend || 8000;\n",
            "seed/framework/frontend/vite.config.factory.ts",
        )
        issues = check_seed_canonical_default(repo)
        assert any(
            "registered backend port number as `||` fallback" in i["issue"]
            for i in issues
        )

    def test_does_not_flag_port_not_in_registry(self):
        # 9999 is not in any registered product → not flagged. The
        # detector is registry-derived on purpose so it follows the fleet.
        repo = self._mk(
            "const port = config.backend || 9999;\n",
            "seed/framework/frontend/vite.config.factory.ts",
        )
        issues = check_seed_canonical_default(repo)
        assert issues == []

    # ── Skip rules ─────────────────────────────────────────────────────

    def test_skips_product_code(self):
        # Detector scope is seed-only — products legitimately hardcode
        # their own port.
        repo = self._mk(
            'const url = env.X || "http://localhost:8000";\n',
            "products/core/frontend/src/api.ts",
        )
        issues = check_seed_canonical_default(repo)
        assert issues == []

    def test_skips_node_modules(self):
        repo = self._mk(
            'const url = env.X || "http://localhost:8000";\n',
            "seed/framework/frontend/node_modules/foo/index.js",
        )
        issues = check_seed_canonical_default(repo)
        assert issues == []

    def test_skips_in_comment(self):
        # Comments are stripped before regex scan — the fix recommendation
        # below the actual fix should not re-trigger the detector.
        repo = self._mk(
            '// Was: env.X || "http://localhost:8000" — replaced by same-origin.\n'
            'const url = env.X ?? "";\n',
            "seed/framework/frontend/src/infra.tsx",
        )
        issues = check_seed_canonical_default(repo)
        assert issues == []

    def test_rationale_escape_hatch_same_line(self):
        # `canonical-default-ok` on the same line waives the flag (used by
        # test fixtures binding to a known port).
        repo = self._mk(
            'const url = "http://localhost:8000"; // canonical-default-ok: fixture\n',
            "seed/framework/frontend/tests/fixtures.ts",
        )
        # The pattern requires `||`/`??` before the URL, so a bare literal
        # already wouldn't match. Use the actual fallback form here.
        # Real test:
        repo = self._mk(
            'const url = env.X || "http://localhost:8000"; // canonical-default-ok: test fixture\n',
            "seed/framework/frontend/src/test_helpers.ts",
        )
        issues = check_seed_canonical_default(repo)
        assert issues == []

    def test_rationale_escape_hatch_preceding_line(self):
        repo = self._mk(
            "// canonical-default-ok: test harness pins to this port\n"
            'const url = env.X || "http://localhost:8000";\n',
            "seed/framework/frontend/src/test_helpers.ts",
        )
        issues = check_seed_canonical_default(repo)
        assert issues == []

    def test_no_crash_on_missing_start_sh(self):
        # Detector degrades to URL-form-only when the registry is
        # unreadable. Build a repo with no start.sh, only a seed file.
        tmp = Path(tempfile.mkdtemp(prefix="seed_canonical_no_registry_"))
        seed = tmp / "seed" / "framework" / "frontend" / "src" / "infra.tsx"
        seed.parent.mkdir(parents=True)
        seed.write_text('const url = env.X || "http://localhost:8000";\n')
        issues = check_seed_canonical_default(tmp)
        # URL form still fires; numeric form skipped.
        assert any("URL literal as `||`/`??` fallback" in i["issue"] for i in issues)


# ---------------------------------------------------------------------------
# `check_query_fn_returns_undefined` — TanStack v5 contract; `queryFn` body
# may not return `undefined` (B3 in KB § PATTERNS/backend/boundary-contract-tests.md).
# ---------------------------------------------------------------------------


class TestCheckQueryFnReturnsUndefined:
    def _mk(self, content: str, rel_path: str) -> Path:
        """Drop a fake FE file at ``rel_path`` and return the temp repo root."""
        tmp = Path(tempfile.mkdtemp(prefix="query_fn_undefined_test_"))
        target = tmp / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return tmp

    # ── Flag cases ─────────────────────────────────────────────────────

    def test_flags_literal_return_undefined(self):
        repo = self._mk(
            "import { useQuery } from '@tanstack/react-query';\n"
            "export function useThing() {\n"
            "  return useQuery({\n"
            "    queryKey: ['thing'],\n"
            "    queryFn: async () => {\n"
            "      try {\n"
            "        return await api.get('/thing');\n"
            "      } catch (err) {\n"
            "        return undefined;\n"
            "      }\n"
            "    },\n"
            "  });\n"
            "}\n",
            "seed/lib/frontend/src/useThing.ts",
        )
        issues = check_query_fn_returns_undefined(repo)
        assert len(issues) == 1
        assert "literal `return undefined`" in issues[0]["issue"]
        assert issues[0]["severity"] == "warning"
        assert issues[0]["product"] == "<seed>"

    def test_flags_bare_return_in_query_fn(self):
        repo = self._mk(
            "import { useQuery } from '@tanstack/react-query';\n"
            "export function useThing() {\n"
            "  return useQuery({\n"
            "    queryKey: ['thing'],\n"
            "    queryFn: async () => {\n"
            "      if (!orgId) {\n"
            "        return;\n"
            "      }\n"
            "      return await api.get('/thing');\n"
            "    },\n"
            "  });\n"
            "}\n",
            "seed/lib/frontend/src/useThing.ts",
        )
        issues = check_query_fn_returns_undefined(repo)
        assert len(issues) == 1
        assert "bare `return;`" in issues[0]["issue"]

    def test_flags_async_with_typed_params(self):
        # `queryFn: async (params) => { ... }` shape — the param list
        # must not throw off the opener regex.
        repo = self._mk(
            "useQuery({\n"
            "  queryKey: ['x'],\n"
            "  queryFn: async (ctx: QueryFunctionContext) => {\n"
            "    return undefined;\n"
            "  },\n"
            "});\n",
            "seed/lib/frontend/src/useThing.tsx",
        )
        issues = check_query_fn_returns_undefined(repo)
        assert len(issues) == 1

    def test_flags_inside_product_fe(self):
        repo = self._mk(
            "useQuery({\n"
            "  queryKey: ['x'],\n"
            "  queryFn: async () => { return undefined; },\n"
            "});\n",
            "products/social-wiring/frontend/src/hooks/useThing.ts",
        )
        issues = check_query_fn_returns_undefined(repo)
        assert len(issues) == 1
        assert issues[0]["product"] == "social-wiring"

    # ── No-flag cases ──────────────────────────────────────────────────

    def test_does_not_flag_return_null(self):
        repo = self._mk(
            "useQuery({\n"
            "  queryKey: ['x'],\n"
            "  queryFn: async () => {\n"
            "    try { return await api.get('/x'); }\n"
            "    catch (err) { return null; }\n"
            "  },\n"
            "});\n",
            "seed/lib/frontend/src/useThing.ts",
        )
        issues = check_query_fn_returns_undefined(repo)
        assert issues == []

    def test_does_not_flag_sentinel_object(self):
        repo = self._mk(
            "const EMPTY = { items: [] };\n"
            "useQuery({\n"
            "  queryKey: ['x'],\n"
            "  queryFn: async () => {\n"
            "    try { return await api.get('/x'); }\n"
            "    catch (err) { return EMPTY; }\n"
            "  },\n"
            "});\n",
            "seed/lib/frontend/src/useThing.ts",
        )
        issues = check_query_fn_returns_undefined(repo)
        assert issues == []

    def test_does_not_flag_expression_body(self):
        # `queryFn: () => api.get(...)` — no braces, can't return
        # undefined literally; out of scope.
        repo = self._mk(
            "useQuery({\n"
            "  queryKey: ['x'],\n"
            "  queryFn: () => api.get('/x'),\n"
            "});\n",
            "seed/lib/frontend/src/useThing.ts",
        )
        issues = check_query_fn_returns_undefined(repo)
        assert issues == []

    def test_does_not_flag_return_undefined_in_comment(self):
        repo = self._mk(
            "useQuery({\n"
            "  queryKey: ['x'],\n"
            "  queryFn: async () => {\n"
            "    // historical bug: used to `return undefined` here\n"
            "    return null;\n"
            "  },\n"
            "});\n",
            "seed/lib/frontend/src/useThing.ts",
        )
        issues = check_query_fn_returns_undefined(repo)
        assert issues == []

    def test_does_not_flag_return_undefined_in_string(self):
        # An error-message string mentioning the rule should not trip
        # the detector.
        repo = self._mk(
            "useQuery({\n"
            "  queryKey: ['x'],\n"
            "  queryFn: async () => {\n"
            "    throw new Error('do not return undefined here');\n"
            "  },\n"
            "});\n",
            "seed/lib/frontend/src/useThing.ts",
        )
        issues = check_query_fn_returns_undefined(repo)
        assert issues == []

    def test_does_not_flag_non_query_fn_arrow(self):
        # A `return undefined` inside an arrow function that is NOT a
        # `queryFn:` body is fine — only the v5 contract is at stake.
        repo = self._mk(
            "const helper = () => {\n"
            "  return undefined;\n"
            "};\n"
            "useQuery({\n"
            "  queryKey: ['x'],\n"
            "  queryFn: () => api.get('/x'),\n"
            "});\n",
            "seed/lib/frontend/src/useThing.ts",
        )
        issues = check_query_fn_returns_undefined(repo)
        assert issues == []

    def test_skips_node_modules(self):
        repo = self._mk(
            "useQuery({\n"
            "  queryKey: ['x'],\n"
            "  queryFn: async () => { return undefined; },\n"
            "});\n",
            "seed/lib/frontend/node_modules/foo/index.ts",
        )
        issues = check_query_fn_returns_undefined(repo)
        assert issues == []

    def test_skips_backend_python(self):
        # Detector scopes to FE; a Python file is never scanned even if
        # it textually contains `queryFn`.
        repo = self._mk(
            'queryFn = "noise"  # return undefined\n',
            "seed/lib/backend/noctusai_lib/example.py",
        )
        issues = check_query_fn_returns_undefined(repo)
        assert issues == []

    # ── Rationale escape hatch ─────────────────────────────────────────

    def test_rationale_same_line_accepted(self):
        repo = self._mk(
            "useQuery({\n"
            "  queryKey: ['x'],\n"
            "  queryFn: async () => {\n"
            "    return undefined; // query-fn-undefined-ok: legacy, see #123\n"
            "  },\n"
            "});\n",
            "seed/lib/frontend/src/useThing.ts",
        )
        issues = check_query_fn_returns_undefined(repo)
        assert issues == []

    def test_rationale_preceding_line_accepted(self):
        repo = self._mk(
            "useQuery({\n"
            "  queryKey: ['x'],\n"
            "  queryFn: async () => {\n"
            "    // query-fn-undefined-ok: defensible reason\n"
            "    return undefined;\n"
            "  },\n"
            "});\n",
            "seed/lib/frontend/src/useThing.ts",
        )
        issues = check_query_fn_returns_undefined(repo)
        assert issues == []


# ---------------------------------------------------------------------------
# `check_limiter_conftest_import` — products with app/rate_limit.py must
# import the seed `reset_rate_limiter` autouse fixture into tests/conftest.py
# (fleet-limiter-conftest-adoption Stage-4, 2026-05-23).
# ---------------------------------------------------------------------------


class TestCheckLimiterConftestImport:
    def _mk_product(
        self,
        slug: str,
        *,
        has_rate_limit: bool,
        conftest_text: str | None,
    ) -> Path:
        """Build a temp repo with one product and return the repo root.

        - ``has_rate_limit`` controls whether ``backend/app/rate_limit.py``
          exists (the predicate's gate).
        - ``conftest_text=None`` ⇒ no ``tests/conftest.py`` file at all;
          otherwise the file is written with that content.
        """
        tmp = Path(tempfile.mkdtemp(prefix="limiter_conftest_test_"))
        backend = tmp / "products" / slug / "backend"
        backend.mkdir(parents=True, exist_ok=True)
        if has_rate_limit:
            (backend / "app").mkdir(parents=True, exist_ok=True)
            (backend / "app" / "rate_limit.py").write_text(
                "from noctusai_lib.api import create_product_limiter\n"
                "limiter = create_product_limiter(settings)\n"
            )
        if conftest_text is not None:
            (backend / "tests").mkdir(parents=True, exist_ok=True)
            (backend / "tests" / "conftest.py").write_text(conftest_text)
        return tmp

    # ── No-flag: product imports the fixture ───────────────────────────
    def test_product_with_import_passes(self):
        repo = self._mk_product(
            "good",
            has_rate_limit=True,
            conftest_text=(
                "from noctusai_lib.testing import MockSupabaseClient  # noqa: F401\n"
                "from noctusai_lib.testing.fixtures import reset_rate_limiter  # noqa: F401\n"
            ),
        )
        issues = check_limiter_conftest_import(repo)
        assert issues == []

    # ── Flag: rate_limit.py present, conftest lacks the import ──────────
    def test_product_with_rate_limit_but_no_import_warns(self):
        repo = self._mk_product(
            "bad",
            has_rate_limit=True,
            conftest_text=(
                "from noctusai_lib.testing import MockSupabaseClient  # noqa: F401\n"
            ),
        )
        issues = check_limiter_conftest_import(repo)
        assert len(issues) == 1
        assert issues[0]["product"] == "bad"
        assert issues[0]["file"] == "backend/tests/conftest.py"
        assert issues[0]["severity"] == "warning"
        assert "reset_rate_limiter" in issues[0]["issue"]

    # ── Flag: rate_limit.py present, conftest missing entirely ─────────
    def test_product_with_rate_limit_but_no_conftest_warns(self):
        repo = self._mk_product("noconf", has_rate_limit=True, conftest_text=None)
        issues = check_limiter_conftest_import(repo)
        assert len(issues) == 1
        assert issues[0]["product"] == "noconf"

    # ── No-flag: no rate_limit.py ⇒ leak class can't occur ─────────────
    def test_product_without_rate_limit_is_skipped(self):
        repo = self._mk_product(
            "nolimiter",
            has_rate_limit=False,
            conftest_text="# no noctusai_lib import\n",
        )
        issues = check_limiter_conftest_import(repo)
        assert issues == []

    # ── No products dir ⇒ empty, no crash ──────────────────────────────
    def test_missing_products_dir_returns_empty(self):
        tmp = Path(tempfile.mkdtemp(prefix="limiter_conftest_empty_"))
        assert check_limiter_conftest_import(tmp) == []


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
    Per KB § PATTERNS/compliance/testing.md § Regression-test-the-detector.

    Origin: 2026-04-29 — `platform-logging-standardization` Phase 6.
    User directive: regression-test-the-detector becomes platform-wide
    methodology, integrated into the code validation system. The new
    detector enforces it; this test pins the contract.
    """

    def test_real_repo_passes(self):
        """The current repo MUST satisfy the rule. If this fails, a new
        detector was added to compliance.py without a regression test —
        either add the test or map it via `_DETECTOR_TEST_OVERRIDES`.

        Pass `REPO_ROOT` from THIS test file (parents[3]) so the meta-detector
        searches THIS workspace's tests/ — important for worktrees where the
        compliance.py being parsed lives at a different repo root than the
        cached `REPO_ROOT` (which resolves to the canonical noc home and may
        lag behind worktree-local detector additions).
        """
        issues = check_detector_has_regression_test(repo_root=REPO_ROOT)
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


# ---------------------------------------------------------------------------
# `check_slowapi_with_pep563` — flags the slowapi `@limiter.limit` +
# `from __future__ import annotations` combination that crashes products
# at app import via `PydanticUndefinedAnnotation`.
# N=3 formalization 2026-05-11 — AUTH-RL + LLM-RL-TRIO + DT-FORWARD-REF.
# ---------------------------------------------------------------------------


class TestCheckSlowapiWithPep563:
    """Regression suite for the slowapi-PEP563 gotcha keeper.

    Pins true-positive and false-positive shapes so the detector cannot
    silently regress. Per KB § PATTERNS/compliance/testing.md § Regression-test-the-detector.
    """

    def _mk_product_with_router(
        self,
        py_content: str,
        *,
        filename: str = "example.py",
        sub: str = "routers",
        slug: str = "p1",
    ) -> Path:
        """Build a tmp product tree with a single router/api file.

        Returns the path to ``<tmp>/<slug>`` (the *product* path, i.e. what
        the detector expects as its argument). The detector walks
        ``<product_path>/backend/app/<sub>/*.py``.
        """
        tmp = Path(tempfile.mkdtemp(prefix="slowapi_pep563_test_"))
        product_path = tmp / slug
        target_dir = product_path / "backend" / "app" / sub
        target_dir.mkdir(parents=True)
        (target_dir / filename).write_text(py_content)
        return product_path

    # -----------------------------------------------------------------
    # True-positive: both patterns present → flag.
    # -----------------------------------------------------------------

    def test_flags_file_with_both_patterns(self):
        content = (
            "from __future__ import annotations\n"
            "\n"
            "from fastapi import APIRouter, Request\n"
            "from pydantic import BaseModel\n"
            "from app.rate_limit import limiter\n"
            "\n"
            "router = APIRouter()\n"
            "\n"
            "class RunRequest(BaseModel):\n"
            "    text: str\n"
            "\n"
            "@router.post('/run')\n"
            "@limiter.limit('10/minute')\n"
            "async def run(request: Request, body: RunRequest):\n"
            "    return {'ok': True}\n"
        )
        product = self._mk_product_with_router(content)
        issues = check_slowapi_with_pep563(product)
        assert len(issues) == 1, f"expected 1 issue, got {issues}"
        assert issues[0]["severity"] == "high"
        assert "from __future__ import annotations" in issues[0]["issue"]
        assert "@limiter.limit" in issues[0]["issue"]
        assert "PydanticUndefinedAnnotation" in issues[0]["issue"]

    def test_flags_file_under_app_api_directory(self):
        """The dev-team product uses `backend/app/api/` instead of
        `backend/app/routers/` — the DT-FORWARD-REF incident landed
        there. Detector must walk both directories."""
        content = (
            "from __future__ import annotations\n"
            "from fastapi import APIRouter, Request\n"
            "from app.rate_limit import limiter\n"
            "\n"
            "router = APIRouter()\n"
            "\n"
            "@router.post('/x')\n"
            "@limiter.limit('5/minute')\n"
            "async def x(request: Request):\n"
            "    return {}\n"
        )
        product = self._mk_product_with_router(content, sub="api", filename="run.py")
        issues = check_slowapi_with_pep563(product)
        assert len(issues) == 1
        assert "run.py" in issues[0]["file"]

    def test_flags_async_function_with_decorator(self):
        """Async route definitions are the common shape — make sure the
        AST walker traverses `AsyncFunctionDef` nodes, not just `FunctionDef`."""
        content = (
            "from __future__ import annotations\n"
            "from app.rate_limit import limiter\n"
            "\n"
            "@limiter.limit('1/second')\n"
            "async def handler(): pass\n"
        )
        product = self._mk_product_with_router(content)
        issues = check_slowapi_with_pep563(product)
        assert len(issues) == 1

    # -----------------------------------------------------------------
    # False-positives: each pattern in isolation → clean.
    # -----------------------------------------------------------------

    def test_does_not_flag_limiter_only(self):
        """`@limiter.limit` without PEP 563 is safe — slowapi works fine
        when annotations are real Python objects at decoration time."""
        content = (
            "from fastapi import APIRouter, Request\n"
            "from pydantic import BaseModel\n"
            "from app.rate_limit import limiter\n"
            "\n"
            "router = APIRouter()\n"
            "\n"
            "class RunRequest(BaseModel):\n"
            "    text: str\n"
            "\n"
            "@router.post('/run')\n"
            "@limiter.limit('10/minute')\n"
            "async def run(request: Request, body: RunRequest):\n"
            "    return {'ok': True}\n"
        )
        product = self._mk_product_with_router(content)
        issues = check_slowapi_with_pep563(product)
        assert issues == []

    def test_does_not_flag_future_import_only(self):
        """PEP 563 without slowapi is the platform default for many files —
        it's only the combination that breaks. Standalone is fine."""
        content = (
            "from __future__ import annotations\n"
            "\n"
            "from fastapi import APIRouter\n"
            "from pydantic import BaseModel\n"
            "\n"
            "router = APIRouter()\n"
            "\n"
            "class Payload(BaseModel):\n"
            "    text: str\n"
            "\n"
            "@router.post('/x')\n"
            "async def x(body: Payload):\n"
            "    return {}\n"
        )
        product = self._mk_product_with_router(content)
        issues = check_slowapi_with_pep563(product)
        assert issues == []

    def test_does_not_flag_neither_pattern(self):
        """A vanilla router file with neither pattern — explicit zero-result
        baseline so a future refactor accidentally inverting the boolean
        would surface immediately."""
        content = (
            "from fastapi import APIRouter\n"
            "router = APIRouter()\n"
            "\n"
            "@router.get('/health')\n"
            "async def health():\n"
            "    return {'ok': True}\n"
        )
        product = self._mk_product_with_router(content)
        issues = check_slowapi_with_pep563(product)
        assert issues == []

    def test_does_not_flag_other_limiter_attribute(self):
        """`@some_other.limit(...)` — same attribute name, different
        receiver. Must NOT trip on look-alikes; the slowapi shape is
        specifically `limiter.limit(...)`."""
        content = (
            "from __future__ import annotations\n"
            "\n"
            "class some_other:\n"
            "    @staticmethod\n"
            "    def limit(x): return lambda f: f\n"
            "\n"
            "@some_other.limit('10/minute')\n"
            "async def x(): return {}\n"
        )
        product = self._mk_product_with_router(content)
        issues = check_slowapi_with_pep563(product)
        assert issues == []

    def test_does_not_flag_future_other_feature(self):
        """`from __future__ import division` (or any non-`annotations`
        future) is not PEP 563 — must not trip the detector."""
        content = (
            "from __future__ import division\n"
            "from app.rate_limit import limiter\n"
            "\n"
            "@limiter.limit('5/minute')\n"
            "async def x(): return {}\n"
        )
        product = self._mk_product_with_router(content)
        issues = check_slowapi_with_pep563(product)
        assert issues == []

    # -----------------------------------------------------------------
    # Output shape pin
    # -----------------------------------------------------------------

    def test_issue_has_required_keys(self):
        content = (
            "from __future__ import annotations\n"
            "from app.rate_limit import limiter\n"
            "@limiter.limit('5/minute')\n"
            "async def x(): return {}\n"
        )
        product = self._mk_product_with_router(content)
        issues = check_slowapi_with_pep563(product)
        assert len(issues) == 1
        issue = issues[0]
        for key in ("product", "file", "issue", "severity"):
            assert key in issue, f"missing key {key} in {issue}"
        assert issue["product"] == "p1"
        assert issue["severity"] == "high"

    def test_real_repo_baseline_known_cases(self):
        """Baseline: zero. The original 4 baseline cases dropped
        ``from __future__ import annotations`` on 2026-05-11 via the
        slowapi-baseline-cleanup project:

          1. ``products/adconnect/backend/app/routers/financial.py``
          2. the retired ``imobi-scheduling`` product's
             ``routers/webhook_router.py`` (consolidated into
             ``social-wiring`` 2026-05-16)
          3. the retired ``media-scheduling`` product's
             ``routers/webhooks.py`` (consolidated into ``social-wiring``
             2026-05-16)
          4. ``products/seed/backend/app/routers/webhook_router.py``
          5. ``templates/product-seed/backend/app/routers/webhook_router.py``
             (template mirror — same body as seed)

        Any NEW occurrence (a rate-limited route in a file that also has
        ``from __future__ import annotations``) trips this assertion
        loudly. The fix shape is: drop the future-import from the file,
        OR move the rate-limited endpoint(s) to a sibling module.
        """
        products_dir = REPO_ROOT / "products"
        all_issues: list[dict] = []
        for product_dir in sorted(products_dir.iterdir()):
            if not product_dir.is_dir() or product_dir.name.startswith("."):
                continue
            all_issues.extend(check_slowapi_with_pep563(product_dir))
        known_baseline: set[str] = set()
        seen = {i["file"] for i in all_issues}
        new_cases = seen - known_baseline
        assert not new_cases, (
            f"slowapi + PEP 563 gotcha re-introduced beyond known baseline: "
            f"{sorted(new_cases)}. Fix the new file(s) — do NOT extend the "
            f"baseline silently. Either (a) drop `from __future__ import "
            f"annotations` from the file, or (b) move the rate-limited "
            f"endpoint(s) to a sibling module."
        )
        # Inverse pin: if known_baseline is non-empty, a fixed case here
        # forces an explicit shrink (no silent drift).
        missing = known_baseline - seen
        assert not missing, (
            f"Known-baseline case(s) appear to be fixed: {sorted(missing)}. "
            f"Shrink the `known_baseline` set in this test."
        )
# ---------------------------------------------------------------------------
# `check_derives_from_dev_only_artifact` -- dev-only-artifact derivation
# without an env fallback (the dev<->prod silent-fallback class). PROACTIVE
# keeper (N=1). `projects/seed-deploy-config-contract` slice B.
# ---------------------------------------------------------------------------

class TestCheckDerivesFromDevOnlyArtifact:
    def _mk_repo_with_seed(self, content: str, rel: str = "lib/backend/noctusai_lib/config/x.py") -> Path:
        """Write a seed `.py` at `seed/<rel>` under a temp repo root."""
        tmp = Path(tempfile.mkdtemp(prefix="dev_artifact_test_"))
        target = tmp / "seed" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return tmp

    def test_flags_registry_derivation_without_env_fallback(self):
        # Derives from `parse_products_registry` with NO env read -> the
        # silent-dev-value-in-prod shape. Exactly 1 finding.
        content = (
            "from noctusai_lib.config.cors_registry import parse_products_registry\n\n"
            "def build_ports():\n"
            "    entries = parse_products_registry()\n"
            "    return {e['slug']: e['backend_port'] for e in entries}\n"
        )
        repo = self._mk_repo_with_seed(content)
        issues = check_derives_from_dev_only_artifact(repo)
        assert len(issues) == 1, f"expected 1 finding, got: {issues}"
        assert issues[0]["severity"] == "warning"
        assert "build_ports" in issues[0]["issue"]

    def test_does_not_flag_when_env_fallback_present(self):
        # The `derive_cors_origins` shape: derives from the registry AND reads
        # `os.environ` (the prod-safe seam). MUST NOT flag -- the key signal.
        content = (
            "import os\n"
            "from noctusai_lib.config.cors_registry import parse_products_registry\n\n"
            "def derive_origins():\n"
            "    entries = parse_products_registry()\n"
            "    out = [f\"http://localhost:{e['frontend_port']}\" for e in entries]\n"
            "    for k, v in os.environ.items():\n"
            "        if k.startswith('PRODUCT_URL_') and v:\n"
            "            out.append(v)\n"
            "    return out\n"
        )
        repo = self._mk_repo_with_seed(content)
        issues = check_derives_from_dev_only_artifact(repo)
        assert issues == [], f"env-fallback derivation should pass, got: {issues}"

    def test_escape_hatch_comment_waives(self):
        # A `dev-artifact-derivation-ok` comment in the preceding window waives.
        content = (
            "from noctusai_lib.config.cors_registry import parse_products_registry\n\n"
            "# dev-artifact-derivation-ok: dev-only helper, never on the prod path\n"
            "def build_ports():\n"
            "    entries = parse_products_registry()\n"
            "    return {e['slug']: e['backend_port'] for e in entries}\n"
        )
        repo = self._mk_repo_with_seed(content)
        issues = check_derives_from_dev_only_artifact(repo)
        assert issues == [], f"escape-hatch comment should suppress, got: {issues}"

    def test_real_cors_registry_is_not_flagged(self):
        # CRITICAL ACCEPTANCE: the live `derive_cors_origins` reads `os.environ`
        # -> the real seed module must pass against the real repo root.
        from tools.noctus.dev.compliance import REPO_ROOT as _ROOT
        issues = check_derives_from_dev_only_artifact(_ROOT)
        cors_hits = [
            i for i in issues
            if i.get("file", "").endswith("config/cors_registry.py")
        ]
        assert cors_hits == [], (
            "derive_cors_origins HAS the os.environ fallback and MUST NOT be "
            f"flagged; got: {cors_hits}"
        )

    def test_seed_test_files_are_excluded(self):
        # Seed test code legitimately calls `parse_products_registry` to
        # exercise the parser -- it is not prod-path derivation, so the
        # `seed/.../tests/` tree is out of scope (live baseline stays clean).
        content = (
            "from noctusai_lib.config.cors_registry import parse_products_registry\\n\\n"
            "def test_parses():\\n"
            "    assert parse_products_registry() is not None\\n"
        )
        repo = self._mk_repo_with_seed(
            content, rel="lib/backend/tests/config/test_x.py"
        )
        issues = check_derives_from_dev_only_artifact(repo)
        assert issues == [], f"seed test files should be excluded, got: {issues}"

    def test_no_derivation_means_no_finding(self):
        # A plain pure function touching neither the registry nor a dev artifact.
        content = (
            "def add(a, b):\n"
            "    return a + b\n"
        )
        repo = self._mk_repo_with_seed(content)
        issues = check_derives_from_dev_only_artifact(repo)
        assert issues == [], f"non-derivation should pass, got: {issues}"


class TestCheckPlaywrightSupabaseEnv:
    """Boundary-contract-tests B6 — the E2E-harness VITE_SUPABASE_* keeper."""

    def _mk(self, slug: str, config_text: str | None) -> Path:
        """Temp repo with one product; ``config_text=None`` ⇒ no playwright
        config at all (backend-only / out-of-scope)."""
        tmp = Path(tempfile.mkdtemp(prefix="playwright_env_test_"))
        frontend = tmp / "products" / slug / "frontend"
        frontend.mkdir(parents=True, exist_ok=True)
        if config_text is not None:
            (frontend / "playwright.config.ts").write_text(config_text)
        return tmp

    _BOTH = (
        "export default defineConfig({\n"
        "  webServer: {\n"
        "    command: 'npm run dev',\n"
        "    env: {\n"
        "      VITE_SUPABASE_URL: 'http://localhost:54321',\n"
        "      VITE_SUPABASE_PUBLISHABLE_KEY: 'test-key',\n"
        "    },\n"
        "  },\n"
        "});\n"
    )

    # ── No-flag: both vars injected ────────────────────────────────────
    def test_both_vars_present_passes(self):
        repo = self._mk("good", self._BOTH)
        assert check_playwright_supabase_env(repo) == []

    # ── Flag: one var missing → single error ───────────────────────────
    def test_missing_one_var_flags_error(self):
        cfg = self._BOTH.replace(
            "      VITE_SUPABASE_PUBLISHABLE_KEY: 'test-key',\n", ""
        )
        issues = check_playwright_supabase_env(self._mk("erp", cfg))
        assert len(issues) == 1
        assert issues[0]["product"] == "erp"
        assert issues[0]["severity"] == "error"
        assert "VITE_SUPABASE_PUBLISHABLE_KEY" in issues[0]["issue"]

    # ── Flag: both missing → two errors ────────────────────────────────
    def test_missing_both_vars_flags_two(self):
        cfg = (
            "export default defineConfig({\n"
            "  webServer: { command: 'npm run dev', env: {} },\n"
            "});\n"
        )
        issues = check_playwright_supabase_env(self._mk("core", cfg))
        assert len(issues) == 2
        assert all(i["severity"] == "error" for i in issues)

    # ── Flag: var named only in a COMMENT does not false-pass ──────────
    def test_var_only_in_comment_still_flags(self):
        cfg = (
            "export default defineConfig({\n"
            "  webServer: {\n"
            "    command: 'npm run dev',\n"
            "    // VITE_SUPABASE_URL + VITE_SUPABASE_PUBLISHABLE_KEY needed\n"
            "    env: {},\n"
            "  },\n"
            "});\n"
        )
        issues = check_playwright_supabase_env(self._mk("commented", cfg))
        assert len(issues) == 2, f"comment mention must not pass: {issues}"

    # ── No-flag: backend-only product (no playwright config) ───────────
    def test_no_config_is_out_of_scope(self):
        assert check_playwright_supabase_env(self._mk("ke", None)) == []

    # ── No-flag: a config with no webServer never loads supabase ───────
    def test_no_webserver_is_out_of_scope(self):
        cfg = "export default defineConfig({ testDir: './e2e' });\n"
        assert check_playwright_supabase_env(self._mk("nows", cfg)) == []


class TestCheckMigrationNumberCollision:
    """Two migrations claiming one number — apply-order is undefined.

    Origin 2026-08-03: three concurrent sessions each picked a number from
    `ls migrations/` + `git log origin/dev`, both blind to a sibling branch
    that had not pushed. Two branches claimed 040; a third shipped a duplicate
    041 to dev.
    """

    def _mk(self, product: str, names: list[str]) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="migration_collision_test_"))
        mig = tmp / "products" / product / "backend" / "migrations"
        mig.mkdir(parents=True, exist_ok=True)
        for n in names:
            (mig / n).write_text("-- migration\nSELECT 1;\n")
        return tmp

    def _mk_with_mirror(self, product: str, canonical: list[str], mirror: list[str]) -> Path:
        """A product carrying a dialect-mirror subdirectory (igig's shape)."""
        tmp = self._mk(product, canonical)
        sub = tmp / "products" / product / "backend" / "migrations" / "sqlite"
        sub.mkdir(parents=True, exist_ok=True)
        for n in mirror:
            (sub / n).write_text("-- mirror\nSELECT 1;\n")
        return tmp

    # ── Directory scoping (regression, 2026-08-09) ─────────────────────
    def test_a_dialect_mirror_sharing_numbers_is_not_a_collision(self):
        """`migrations/sqlite/006_x.sql` beside `migrations/006_y.sql` is a
        deliberate PAIRING, not a race.

        Apply-order is only undefined between files the same runner applies,
        and each migrations directory is its own sequence. Leg B used to key
        on (product, number) and reported every mirrored pair as a collision;
        it now keys on the directory. Leg A was always directory-scoped (a
        non-recursive glob), so it never had the bug.
        """
        repo = self._mk_with_mirror(
            "igig",
            ["006_igig_dominio.sql", "007_igig_aprovacao.sql"],
            ["006_dominio.sql", "007_aprovacao.sql"],
        )
        assert check_migration_number_collision(repo) == []

    def test_a_real_duplicate_inside_the_mirror_dir_still_flags(self):
        """Loosening the key must not blind the detector INSIDE a directory."""
        repo = self._mk_with_mirror(
            "igig", ["006_igig_dominio.sql"], ["006_a.sql", "006_b.sql"]
        )
        issues = check_migration_number_collision(repo)
        assert any("006" in i["issue"] for i in issues), issues

    # ── Leg A: duplicates on disk ──────────────────────────────────────
    def test_distinct_numbers_pass(self):
        repo = self._mk("core", ["001_a.sql", "002_b.sql", "003_c.sql"])
        assert check_migration_number_collision(repo) == []

    def test_duplicate_number_flags_high(self):
        repo = self._mk("core", ["040_leads.sql", "040_imoveis.sql"])
        issues = [
            i for i in check_migration_number_collision(repo)
            if i["severity"] == "high"
        ]
        assert len(issues) == 1, issues
        assert issues[0]["product"] == "core"
        assert "040" in issues[0]["issue"]
        # The message must name BOTH files — the fix is "renumber all but the
        # earliest-merged", which you cannot do without knowing which they are.
        assert "040_leads.sql" in issues[0]["issue"]
        assert "040_imoveis.sql" in issues[0]["issue"]

    def test_three_way_duplicate_is_one_finding_naming_all_three(self):
        repo = self._mk("core", ["040_a.sql", "040_b.sql", "040_c.sql"])
        highs = [
            i for i in check_migration_number_collision(repo)
            if i["severity"] == "high"
        ]
        assert len(highs) == 1, highs
        assert "3 files" in highs[0]["issue"]

    def test_four_digit_prefix_supported(self):
        repo = self._mk("core", ["0040_a.sql", "0040_b.sql"])
        assert any(
            i["severity"] == "high"
            for i in check_migration_number_collision(repo)
        )

    def test_same_number_in_DIFFERENT_products_is_not_a_collision(self):
        """Numbering is per-product — every product has its own 001."""
        repo = self._mk("core", ["001_a.sql"])
        other = repo / "products" / "erp-imobiliario" / "backend" / "migrations"
        other.mkdir(parents=True)
        (other / "001_b.sql").write_text("SELECT 1;")
        assert check_migration_number_collision(repo) == []

    def test_unnumbered_file_is_ignored(self):
        repo = self._mk("core", ["001_a.sql", "README.md", "rollback.sql"])
        assert check_migration_number_collision(repo) == []

    def test_ratified_historical_duplicate_is_accepted(self):
        """`_ACCEPTED_MIGRATION_DUPLICATES` — renumbering an APPLIED migration
        is worse than the duplicate (the runner would re-run the renamed
        file). The allowlist keeps the detector meaningful for NEW collisions
        instead of muting it wholesale."""
        repo = self._mk(
            "social-wiring",
            ["005_integration_accounts.sql", "005_whatsapp_connection_webhook_token.sql"],
        )
        highs = [
            i for i in check_migration_number_collision(repo)
            if i["severity"] == "high"
        ]
        assert highs == [], f"ratified pair must not flag: {highs}"

    def test_accepted_entry_does_not_mute_other_numbers_in_that_product(self):
        """The allowlist is keyed on (product, NUMBER) — accepting 005 must
        not turn social-wiring into a free-for-all."""
        repo = self._mk(
            "social-wiring",
            [
                "005_integration_accounts.sql",
                "005_whatsapp_connection_webhook_token.sql",
                "046_x.sql",
                "046_y.sql",
            ],
        )
        highs = [
            i for i in check_migration_number_collision(repo)
            if i["severity"] == "high"
        ]
        assert len(highs) == 1, highs
        assert "046" in highs[0]["issue"]

    def test_missing_products_dir_is_not_a_crash(self):
        tmp = Path(tempfile.mkdtemp(prefix="migration_collision_empty_"))
        assert check_migration_number_collision(tmp) == []

    def test_nonexistent_root_returns_empty(self):
        assert check_migration_number_collision(Path("/no/such/root")) == []

    # ── Leg B: the same number claimed by DIFFERENT branches ───────────
    def _git_repo(self) -> Path | None:
        """A real repo with `origin/dev` + two feature branches. Returns None
        if git is unusable, so the suite degrades rather than false-fails."""
        import subprocess

        tmp = Path(tempfile.mkdtemp(prefix="migration_collision_git_"))

        def git(*a: str, cwd: Path = tmp) -> bool:
            r = subprocess.run(
                ["git", *a], cwd=cwd, capture_output=True, text=True, timeout=30
            )
            return r.returncode == 0

        def write(name: str) -> None:
            mig = tmp / "products" / "core" / "backend" / "migrations"
            mig.mkdir(parents=True, exist_ok=True)
            (mig / name).write_text("SELECT 1;\n")

        ok = (
            git("init", "-q", "-b", "dev")
            and git("config", "user.email", "t@test.local")
            and git("config", "user.name", "t")
        )
        if not ok:
            return None
        write("001_base.sql")
        if not (git("add", "-A") and git("commit", "-qm", "base")):
            return None
        # `origin/dev` without a real remote: a local ref under refs/remotes.
        if not git("update-ref", "refs/remotes/origin/dev", "HEAD"):
            return None
        for branch, fname in (("feat/a", "040_leads.sql"), ("feat/b", "040_imoveis.sql")):
            if not git("checkout", "-q", "-b", branch, "dev"):
                return None
            write(fname)
            if not (git("add", "-A") and git("commit", "-qm", branch)):
                return None
        # Land back on dev so the working tree carries neither 040 file —
        # isolating Leg B from Leg A.
        if not git("checkout", "-q", "dev"):
            return None
        return tmp

    def test_two_branches_claiming_one_number_flags_warning(self):
        repo = self._git_repo()
        if repo is None:
            import pytest as _pytest
            _pytest.skip("git unavailable in this environment")
        issues = check_migration_number_collision(repo)
        warnings = [i for i in issues if i["severity"] == "warning"]
        assert len(warnings) == 1, f"expected one latent-collision warning: {issues}"
        msg = warnings[0]["issue"]
        assert "040" in msg
        # Must name the branches — the fix belongs to whoever merges second,
        # who needs to know who the other claimant is.
        assert "feat/a" in msg and "feat/b" in msg
        assert "040_leads.sql" in msg and "040_imoveis.sql" in msg

    def test_leg_b_is_warning_not_high(self):
        """Latent, not broken: nothing is wrong until the second merge. Rating
        it `high` would block the FIRST branch, which did nothing wrong."""
        repo = self._git_repo()
        if repo is None:
            import pytest as _pytest
            _pytest.skip("git unavailable in this environment")
        assert all(
            i["severity"] == "warning" for i in check_migration_number_collision(repo)
        )

    def test_same_FILE_on_sibling_branches_is_not_a_collision(self):
        """A stack of sibling branches off one initiative all carry the same
        migration file. Comparing filenames (not just numbers) is what keeps
        that from false-flagging."""
        import subprocess

        repo = self._git_repo()
        if repo is None:
            import pytest as _pytest
            _pytest.skip("git unavailable in this environment")

        def git(*a: str) -> None:
            subprocess.run(["git", *a], cwd=repo, capture_output=True, timeout=30)

        # Wipe the divergent pair, then give two branches the SAME 041 file.
        git("branch", "-D", "feat/a")
        git("branch", "-D", "feat/b")
        mig = repo / "products" / "core" / "backend" / "migrations"
        for branch in ("feat/c", "feat/d"):
            git("checkout", "-q", "-b", branch, "dev")
            (mig / "041_shared.sql").write_text("SELECT 1;\n")
            git("add", "-A")
            git("commit", "-qm", branch)
            git("checkout", "-q", "dev")
        assert check_migration_number_collision(repo) == []

    def test_no_git_still_returns_leg_a_findings(self):
        """Leg B needs git; Leg A does not. An unavailable branch list must
        not swallow an on-disk duplicate that is already broken."""
        repo = self._mk("core", ["040_a.sql", "040_b.sql"])  # not a git repo
        issues = check_migration_number_collision(repo)
        assert any(i["severity"] == "high" for i in issues), issues


class TestCheckPrimaryCheckoutCommit:
    """Refuse a WORK commit on a shared branch in the PRIMARY checkout.

    Every input is injectable precisely because the forbidden state (a real
    primary checkout sitting on `dev` with work staged) is the thing the gate
    exists to prevent and so cannot be created in a test.
    """

    _ROOT = Path("/tmp")  # unused when every probe is injected

    def _run(self, **kw):
        base = dict(
            repo_root=self._ROOT,
            is_primary=True,
            branch="dev",
            allow_override=False,
            staged=["seed/lib/backend/noctusai_lib/x.py"],
        )
        base.update(kw)
        return check_primary_checkout_commit(**base)

    # ── Flag: work on each shared branch ───────────────────────────────
    def test_work_on_dev_in_primary_flags_high(self):
        issues = self._run()
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "high"
        assert "dev" in issues[0]["issue"]
        # The message must hand over the exact recovery command.
        assert "task_branch action=start" in issues[0]["issue"]

    def test_work_on_main_flags(self):
        assert len(self._run(branch="main")) == 1

    def test_work_on_prod_flags(self):
        assert len(self._run(branch="prod")) == 1

    # ── No-flag: not a shared branch ───────────────────────────────────
    def test_feature_branch_passes(self):
        assert self._run(branch="feat/some-slice") == []

    # ── No-flag: linked worktree (the sanctioned place to work) ────────
    def test_worktree_passes_even_on_dev(self):
        assert self._run(is_primary=False) == []

    # ── The ledger exemption ───────────────────────────────────────────
    def test_ledger_only_commit_passes(self):
        """`branch_pointer` / salvage / cost logs commit straight to dev from
        the primary by design — bookkeeping, not work."""
        assert self._run(staged=[
            "project-history/branch-tree.ndjson",
            "project-history/vector-costs.ndjson",
        ]) == []

    def test_one_source_file_mixed_into_a_ledger_commit_still_blocks(self):
        """The laundering path: hide work behind ledger files. Must block."""
        issues = self._run(staged=[
            "project-history/branch-tree.ndjson",
            "seed/lib/backend/noctusai_lib/domain/invitations.py",
        ])
        assert len(issues) == 1, issues
        assert "invitations.py" in issues[0]["file"]
        # ...and the ledger file must NOT be listed as the offender.
        assert "branch-tree" not in issues[0]["file"]

    def test_empty_staged_set_passes(self):
        assert self._run(staged=[]) == []

    # ── Escape hatch ───────────────────────────────────────────────────
    def test_env_override_suppresses(self):
        assert self._run(allow_override=True) == []

    def test_override_reads_the_env_var_when_not_injected(self, monkeypatch):
        """`NOCTUS_ALLOW_PRIMARY_COMMIT=1` is the documented hatch. Patching
        the ENVIRONMENT is an external boundary, not our own code."""
        monkeypatch.setenv("NOCTUS_ALLOW_PRIMARY_COMMIT", "1")
        assert check_primary_checkout_commit(
            repo_root=self._ROOT, is_primary=True, branch="dev",
            staged=["seed/x.py"],
        ) == []

    def test_env_var_set_to_something_else_does_not_suppress(self):
        """Only the literal "1" opens the hatch — a stray truthy value must
        not silently disable the gate."""
        import os
        prev = os.environ.get("NOCTUS_ALLOW_PRIMARY_COMMIT")
        os.environ["NOCTUS_ALLOW_PRIMARY_COMMIT"] = "0"
        try:
            assert len(check_primary_checkout_commit(
                repo_root=self._ROOT, is_primary=True, branch="dev",
                staged=["seed/x.py"],
            )) == 1
        finally:
            if prev is None:
                os.environ.pop("NOCTUS_ALLOW_PRIMARY_COMMIT", None)
            else:
                os.environ["NOCTUS_ALLOW_PRIMARY_COMMIT"] = prev

    # ── Message quality: the sample is truncated, and says so ──────────
    def test_many_files_are_summarised_with_a_remainder_count(self):
        issues = self._run(staged=[f"seed/f{i}.py" for i in range(9)])
        assert len(issues) == 1
        assert "+5 more" in issues[0]["file"], issues[0]["file"]
        assert "9 non-ledger file(s)" in issues[0]["issue"]


class TestCheckConflictMarkers:
    """A tracked file that still carries unresolved merge-conflict markers.

    Origin 2026-08-04: `042_whatsapp_inbox_realtime_schema.sql` reached
    `origin/dev` with a conflict header committed verbatim, produced by a
    rename-conflict during the 040→042 renumber. It sat in the header COMMENT
    block, so every semantic gate read past it and the already-applied live
    schema gave no runtime signal — a latent DR/provisioning failure.

    Markers are built by repetition here for the same reason the detector
    builds them that way: a literal would make this file self-flag under
    `test_real_repo_is_clean`.
    """

    OPEN = "<" * 7
    DIV = "=" * 7
    CLOSE = ">" * 7

    def _mk(self, rel: str, body: str) -> tuple[Path, str]:
        tmp = Path(tempfile.mkdtemp(prefix="conflict_markers_test_"))
        target = tmp / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
        return tmp, rel

    def _conflicted(self, *, opener: str | None = None) -> str:
        return (
            f"{opener or self.OPEN} HEAD\n"
            "SELECT 1;\n"
            f"{self.DIV}\n"
            "SELECT 2;\n"
            f"{self.CLOSE} feat/other\n"
        )

    # ── Flag: a real conflict ──────────────────────────────────────────
    def test_conflicted_file_flags_high(self):
        repo, rel = self._mk("products/core/backend/migrations/042_x.sql",
                             self._conflicted())
        issues = check_conflict_markers(repo, paths=[rel])
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "high"
        assert issues[0]["file"] == rel
        assert issues[0]["product"] == "core"

    def test_eight_char_rename_variant_flags(self):
        """git emits an EIGHT-character opener with a `path:` suffix when the
        conflict is in a RENAMED file — the exact shape that shipped, and the
        one nobody visually scans for."""
        repo, rel = self._mk(
            "products/core/backend/migrations/042_x.sql",
            self._conflicted(opener=("<" * 8) + " HEAD:migrations/040_x.sql"),
        )
        assert len(check_conflict_markers(repo, paths=[rel])) == 1

    def test_message_names_the_line_numbers(self):
        repo, rel = self._mk("a.sql", "-- head\n" + self._conflicted())
        issues = check_conflict_markers(repo, paths=[rel])
        assert "line(s) 2" in issues[0]["issue"], issues[0]["issue"]

    # ── No-flag: opener/closer must BOTH be present ────────────────────
    def test_lone_divider_is_a_markdown_heading_not_a_conflict(self):
        """`=======` underlines a Markdown heading and divides Python
        sections. Matching it alone would be almost all false positives."""
        repo, rel = self._mk("doc.md", f"Title\n{self.DIV}\n\nbody\n")
        assert check_conflict_markers(repo, paths=[rel]) == []

    def test_opener_without_closer_does_not_flag(self):
        repo, rel = self._mk("a.py", f"{self.OPEN} HEAD\nx = 1\n")
        assert check_conflict_markers(repo, paths=[rel]) == []

    def test_closer_without_opener_does_not_flag(self):
        repo, rel = self._mk("a.py", f"{self.CLOSE} feat/x\nx = 1\n")
        assert check_conflict_markers(repo, paths=[rel]) == []

    def test_clean_file_passes(self):
        repo, rel = self._mk("a.sql", "-- fine\nSELECT 1;\n")
        assert check_conflict_markers(repo, paths=[rel]) == []

    # ── The Markdown fence exemption ───────────────────────────────────
    def test_markers_inside_a_markdown_fence_are_exempt(self):
        """`branching-and-merging.md` teaches conflict resolution and must
        print all three markers. Docs do not execute."""
        repo, rel = self._mk(
            "KNOWLEDGE-BASE/x.md",
            "How to resolve:\n\n```\n" + self._conflicted() + "```\n",
        )
        assert check_conflict_markers(repo, paths=[rel]) == []

    def test_markers_OUTSIDE_a_fence_in_markdown_still_flag(self):
        """The exemption is the fence, not the file extension."""
        repo, rel = self._mk("KNOWLEDGE-BASE/x.md", self._conflicted())
        assert len(check_conflict_markers(repo, paths=[rel])) == 1

    def test_fence_exemption_does_NOT_apply_to_code(self):
        """A ``` line in a .py file is not a fence — it is nothing. A real
        conflict there must still flag."""
        repo, rel = self._mk("a.py", "```\n" + self._conflicted() + "```\n")
        assert len(check_conflict_markers(repo, paths=[rel])) == 1

    # ── Robustness ─────────────────────────────────────────────────────
    def test_binary_file_is_skipped_not_crashed(self):
        tmp = Path(tempfile.mkdtemp(prefix="conflict_markers_bin_"))
        (tmp / "b.bin").write_bytes(b"\xff\xfe\x00\x01" + b"\x80" * 32)
        assert check_conflict_markers(tmp, paths=["b.bin"]) == []

    def test_missing_path_is_skipped(self):
        tmp = Path(tempfile.mkdtemp(prefix="conflict_markers_missing_"))
        assert check_conflict_markers(tmp, paths=["nope.sql"]) == []

    def test_nonexistent_root_returns_empty(self):
        assert check_conflict_markers(Path("/no/such/root"), paths=["a.sql"]) == []

    def test_product_field_is_dash_outside_products(self):
        repo, rel = self._mk("seed/lib/backend/x.py", self._conflicted())
        assert check_conflict_markers(repo, paths=[rel])[0]["product"] == "-"

    # ── The real repo must be clean (this is how the class was caught) ──
    def test_real_repo_is_clean(self):
        from tools.noctus.dev.compliance import REPO_ROOT as _ROOT
        issues = check_conflict_markers(_ROOT)
        assert issues == [], (
            f"tracked file(s) carry unresolved conflict markers: "
            f"{[i['file'] for i in issues]}"
        )


class TestCheckPostgrestSchemaQualifiedTable:
    """PostgREST table names are schema-RELATIVE — a qualified name 500s.

    Live incident 2026-08-06: `f"{deps._db.schema}.invitations"` in the seed
    team router made PostgREST answer
    `Could not find the table 'social_wiring.social_wiring.invitations'` on
    every team invite, across all 9 products mounting that router. Green in CI
    for ~3 months because the test fixtures qualified the name too.
    """

    def _mk(self, body: str, *, where: str = "seed/framework/backend/x.py") -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="postgrest_qualified_test_"))
        target = tmp / where
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
        return tmp

    # ── Flag: the interpolated shape, at a `.table()` call site ────────
    def test_interpolated_at_table_call_flags(self):
        repo = self._mk('x = db.table(f"{deps._db.schema}.invitations")\n')
        issues = check_postgrest_schema_qualified_table(repo)
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "high"
        assert "interpolated" in issues[0]["issue"]

    # ── Flag: the interpolated shape at a DOMAIN-HELPER boundary ───────
    def test_interpolated_at_helper_call_flags(self):
        """The actual live shape. The qualified string was composed as a
        helper argument and only reached `.table()` two frames later, inside
        the lib — a call-site-anchored detector would have missed it."""
        repo = self._mk(
            'r = validate_invitation(admin, f"{deps._db.schema}.invitations", tok)\n'
        )
        issues = check_postgrest_schema_qualified_table(repo)
        assert len(issues) == 1, issues
        assert "interpolated" in issues[0]["issue"]

    # ── Flag: the hardcoded literal shape ──────────────────────────────
    def test_literal_dotted_name_flags(self):
        repo = self._mk('x = db.table("social_wiring.invitations").select("*")\n')
        issues = check_postgrest_schema_qualified_table(repo)
        assert len(issues) == 1, issues
        assert "literal" in issues[0]["issue"]
        assert "social_wiring.invitations" in issues[0]["issue"]

    def test_literal_at_invitation_helper_flags(self):
        repo = self._mk('cancel_invitation(db, "erp.invitations", iid, org)\n')
        issues = check_postgrest_schema_qualified_table(repo)
        assert len(issues) == 1, issues

    # ── Flag: `.from_()` is the same PostgREST builder ─────────────────
    def test_from_alias_flags(self):
        repo = self._mk('x = db.from_("therapy.invitations")\n')
        issues = check_postgrest_schema_qualified_table(repo)
        assert len(issues) == 1, issues

    # ── No-flag: the correct bare form ─────────────────────────────────
    def test_bare_table_name_passes(self):
        repo = self._mk('x = db.table("invitations").select("*")\n')
        assert check_postgrest_schema_qualified_table(repo) == []

    # ── No-flag: an f-string with no dot after the interpolation ───────
    def test_interpolated_without_dot_passes(self):
        repo = self._mk('x = db.table(f"{schema_prefix}_events")\n')
        assert check_postgrest_schema_qualified_table(repo) == []

    # ── No-flag: a dotted f-string that interpolates something else ────
    def test_dotted_fstring_without_schema_passes(self):
        repo = self._mk('p = f"{basename}.json"\nx = db.table("leads")\n')
        assert check_postgrest_schema_qualified_table(repo) == []

    # ── No-flag: a dotted literal NOT in a table-name position ─────────
    def test_dotted_literal_elsewhere_passes(self):
        """Module paths, filenames and version strings are dotted too — the
        literal shape is anchored to table-name arguments for exactly this
        reason."""
        repo = self._mk(
            'mod = importlib.import_module("app.services")\n'
            'x = db.table("invitations")\n'
        )
        assert check_postgrest_schema_qualified_table(repo) == []

    # ── No-flag: PROSE describing the bug (why this is AST-based) ──────
    def test_docstring_mentioning_the_bug_does_not_self_flag(self):
        """A regex over source text cannot tell an f-string in CODE from the
        same characters quoted inside a docstring — which would make the
        pattern doc, the fix's own comments, and these tests self-flag."""
        repo = self._mk(
            '"""Never write db.table(f"{deps._db.schema}.invitations") —\n'
            'PostgREST resolves it as social_wiring.social_wiring.invitations.\n'
            '"""\n'
            '# also not: db.table("social_wiring.invitations")\n'
            'x = db.table("invitations")\n'
        )
        assert check_postgrest_schema_qualified_table(repo) == []

    # ── No-flag: escape hatch ──────────────────────────────────────────
    def test_escape_hatch_suppresses(self):
        repo = self._mk(
            "# postgrest-qualified-ok — this table's NAME contains a dot\n"
            'x = db.table("weird.name")\n'
        )
        assert check_postgrest_schema_qualified_table(repo) == []

    # ── Scope: products/<slug>/backend is scanned; frontend is not ─────
    def test_product_backend_is_in_scope(self):
        repo = self._mk(
            'x = db.table("erp.invitations")\n',
            where="products/erp-imobiliario/backend/app/r.py",
        )
        assert len(check_postgrest_schema_qualified_table(repo)) == 1

    def test_unparseable_file_is_skipped_not_crashed(self):
        repo = self._mk('x = db.table("a.b"\n')  # syntax error
        assert check_postgrest_schema_qualified_table(repo) == []

    # ── The real repo must be clean ────────────────────────────────────
    def test_real_repo_is_clean(self):
        from tools.noctus.dev.compliance import REPO_ROOT as _ROOT
        issues = check_postgrest_schema_qualified_table(_ROOT)
        assert issues == [], (
            "Schema-qualified PostgREST table name(s) present — each is a "
            f"guaranteed runtime 500: {[i['file'] for i in issues]}"
        )


class TestCheckRootRequirementsSuperset:
    """root requirements.txt must be a superset of every product backend's deps
    (CI + predeploy install the root file). Regression for the 2026-05-31
    python-docx deploy blocker."""

    def _mk(self, root_reqs: str, product_reqs: dict[str, str]) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="req_superset_test_"))
        (tmp / "requirements.txt").write_text(root_reqs)
        for slug, reqs in product_reqs.items():
            be = tmp / "products" / slug / "backend"
            be.mkdir(parents=True, exist_ok=True)
            (be / "requirements.txt").write_text(reqs)
        return tmp

    def test_complete_superset_passes(self):
        repo = self._mk(
            "fastapi>=0.1\npython-docx>=1.1.0\nanthropic>=0.40.0\n",
            {"ke": "fastapi>=0.1\npython-docx>=1.1.0  # docx_export\n",
             "therapy": "anthropic>=0.40.0\n"},
        )
        assert check_root_requirements_superset(repo) == []

    def test_missing_product_dep_flags_high(self):
        repo = self._mk(
            "fastapi>=0.1\n",  # missing python-docx
            {"ke": "fastapi>=0.1\npython-docx>=1.1.0\n"},
        )
        issues = check_root_requirements_superset(repo)
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"
        assert issues[0]["product"] == "ke"
        assert "python-docx" in issues[0]["issue"]
        assert issues[0]["symbol"] == "root-requirements-superset-incomplete"

    def test_comment_lines_ignored_editables_matched(self):
        # comments ignored; an editable in the product that IS in root (modulo the
        # `../../` prefix) does not flag.
        repo = self._mk(
            "-e seed/lib/backend\nfastapi>=0.1\n",
            {"p": "-e ../../seed/lib/backend\n# a comment\nfastapi>=0.1\n"},
        )
        assert check_root_requirements_superset(repo) == []

    def test_missing_editable_flags_high(self):
        # product editable-installs the seed FRAMEWORK but root only has the lib —
        # the noctusai_seed gap (2026-05-31).
        repo = self._mk(
            "-e seed/lib/backend\nfastapi>=0.1\n",  # missing -e seed/framework/backend
            {"p": "-e ../../seed/lib/backend\n-e ../../seed/framework/backend\nfastapi>=0.1\n"},
        )
        issues = check_root_requirements_superset(repo)
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"
        assert issues[0]["symbol"] == "root-requirements-superset-incomplete-editable"
        assert "seed/framework/backend" in issues[0]["issue"]

    def test_name_normalization_underscore_dash(self):
        # product uses `python_docx`, root uses `python-docx` — pip-equivalent.
        repo = self._mk("python-docx>=1.1.0\n", {"p": "python_docx>=1.1.0\n"})
        assert check_root_requirements_superset(repo) == []

    def test_real_repo_superset_is_complete(self):
        # The live repo must satisfy the invariant (guards against re-drift).
        assert check_root_requirements_superset() == []


class TestCheckRlsPolicySelfReference:
    """An RLS policy whose USING/WITH CHECK subqueries its own table (42P17)."""

    def _mk(self, slug: str, files: dict[str, str]) -> Path:
        """Temp repo with one product; `files` maps migration filename -> SQL."""
        tmp = Path(tempfile.mkdtemp(prefix="rls_selfref_test_"))
        mig = tmp / "products" / slug / "backend" / "migrations"
        mig.mkdir(parents=True, exist_ok=True)
        for fname, sql in files.items():
            (mig / fname).write_text(sql)
        return tmp / "products" / slug

    _SELF_REF = (
        'CREATE POLICY "members_read" ON public.team_members FOR SELECT '
        'TO authenticated USING (\n'
        '  org_id IN (SELECT org_id FROM team_members WHERE id = auth.uid())\n'
        ');\n'
    )
    _SAFE = (
        'CREATE POLICY "members_read" ON public.team_members FOR SELECT '
        'TO authenticated USING (\n'
        '  org_id = public.current_user_org_id()\n'
        ');\n'
    )

    # ── Flag: a self-referencing policy ────────────────────────────────
    def test_self_reference_flags(self):
        issues = check_rls_policy_self_reference(self._mk("p", {"001.sql": self._SELF_REF}))
        assert len(issues) == 1
        assert issues[0]["severity"] == "error"
        assert "team_members" in issues[0]["issue"]

    # ── No-flag: a helper-based policy (no FROM self) ──────────────────
    def test_helper_based_policy_passes(self):
        assert check_rls_policy_self_reference(self._mk("p", {"001.sql": self._SAFE})) == []

    # ── No-flag: supersession — 001 self-ref DROP+recreated safe in 035 ─
    def test_later_drop_recreate_supersedes(self):
        fixed = (
            'DROP POLICY IF EXISTS "members_read" ON public.team_members;\n'
            + self._SAFE
        )
        repo = self._mk("p", {"001_init.sql": self._SELF_REF, "035_fix.sql": fixed})
        assert check_rls_policy_self_reference(repo) == [], "last create wins"

    # ── Flag: JOIN-form self-reference ─────────────────────────────────
    def test_join_self_reference_flags(self):
        sql = (
            'CREATE POLICY "p" ON public.team_members FOR SELECT TO authenticated '
            'USING (EXISTS (SELECT 1 FROM team_members t WHERE t.id = auth.uid()));\n'
        )
        assert len(check_rls_policy_self_reference(self._mk("p", {"001.sql": sql}))) == 1

    # ── No-flag: no migrations dir ─────────────────────────────────────
    def test_no_migrations_dir(self):
        tmp = Path(tempfile.mkdtemp(prefix="rls_none_"))
        (tmp / "products" / "p").mkdir(parents=True)
        assert check_rls_policy_self_reference(tmp / "products" / "p") == []


class TestCheckAuthSessionMutationOnSharedClient:
    """Session-establishing supabase-py auth on the shared service-role client."""

    def _mk(self, slug: str, py: str, *, rel: str = "backend/app/routers/auth.py") -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="auth_poison_test_"))
        f = tmp / "products" / slug / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(py)
        return tmp / "products" / slug

    # ── Flag: verify_otp on the supabase_admin singleton ───────────────
    def test_verify_otp_on_singleton_flags(self):
        py = (
            "def gen():\n"
            "    return supabase_admin.auth.verify_otp({'email': e})\n"
        )
        issues = check_auth_session_mutation_on_shared_client(self._mk("p", py))
        assert len(issues) == 1
        assert issues[0]["severity"] == "error"
        assert "verify_otp" in issues[0]["issue"]

    # ── Flag: sign_in on a get_admin_client() binding ──────────────────
    def test_sign_in_on_admin_binding_flags(self):
        py = (
            "def login():\n"
            "    sb = get_admin_client()\n"
            "    return sb.auth.sign_in_with_password({'email': e})\n"
        )
        assert len(check_auth_session_mutation_on_shared_client(self._mk("p", py))) == 1

    # ── No-flag: session call on a throwaway create_client ─────────────
    def test_throwaway_client_passes(self):
        py = (
            "def login():\n"
            "    client = create_client(url, anon_key)\n"
            "    return client.auth.sign_in_with_password({'email': e})\n"
        )
        assert check_auth_session_mutation_on_shared_client(self._mk("p", py)) == []

    # ── No-flag: a NON-session admin call (generate_link, reads) ───────
    def test_non_session_admin_call_passes(self):
        py = (
            "def gen():\n"
            "    supabase_admin.auth.admin.generate_link({'email': e})\n"
            "    return get_admin_client().table('noctus_users').select('*')\n"
        )
        assert check_auth_session_mutation_on_shared_client(self._mk("p", py)) == []

    # ── No-flag: tests/ are out of scope ───────────────────────────────
    def test_tests_dir_excluded(self):
        py = "def t():\n    supabase_admin.auth.verify_otp({'email': e})\n"
        repo = self._mk("p", py, rel="backend/tests/test_auth.py")
        assert check_auth_session_mutation_on_shared_client(repo) == []


class TestCheckProductServiceWorker:
    """Undeclared precaching service worker (PWA) → stale-bundle class."""

    def _mk(self, vite_config: str, *, name: str = "vite.config.ts") -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="sw_test_"))
        f = tmp / "products" / "p" / "frontend" / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(vite_config)
        return tmp / "products" / "p"

    # ── Flag: VitePWA without selfDestroying / declaration ─────────────
    def test_precaching_pwa_flags(self):
        cfg = (
            "import { VitePWA } from 'vite-plugin-pwa';\n"
            "export default { plugins: [VitePWA({ registerType: 'autoUpdate' })] };\n"
        )
        issues = check_product_service_worker(self._mk(cfg))
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"
        assert "service worker" in issues[0]["issue"].lower()

    # ── No-flag: self-destroying retirement worker ─────────────────────
    def test_self_destroying_passes(self):
        cfg = (
            "import { VitePWA } from 'vite-plugin-pwa';\n"
            "export default { plugins: [VitePWA({ selfDestroying: true })] };\n"
        )
        assert check_product_service_worker(self._mk(cfg)) == []

    # ── No-flag: explicit conscious declaration ────────────────────────
    def test_declared_service_worker_passes(self):
        cfg = (
            "import { VitePWA } from 'vite-plugin-pwa';\n"
            "// noc-allow: service-worker — offline field-app requirement\n"
            "export default { plugins: [VitePWA({ registerType: 'autoUpdate' })] };\n"
        )
        assert check_product_service_worker(self._mk(cfg)) == []

    # ── No-flag: no service worker at all ──────────────────────────────
    def test_no_pwa_passes(self):
        cfg = "export default { plugins: [] };\n"
        assert check_product_service_worker(self._mk(cfg)) == []

    # ── No-flag: no vite config ────────────────────────────────────────
    def test_no_config_passes(self):
        tmp = Path(tempfile.mkdtemp(prefix="sw_none_"))
        (tmp / "products" / "p" / "frontend").mkdir(parents=True)
        assert check_product_service_worker(tmp / "products" / "p") == []


# ---------------------------------------------------------------------------
# TestMethodologyDocRefs — check_methodology_doc_refs (2026-05-25)
#
# Verifies the compliance keeper that surfaces broken KB-doc refs across
# CLAUDE.md / CLAUDE/**/*.md / .claude/agents/*.md / KNOWLEDGE-BASE/**/*.md.
# Spec:
#   - returns `high`-severity dicts (mirrors check_archive_staleness shape)
#   - delegates to methodology_reference_gaps (NO logic duplication)
#   - zero issues on the real repo tree (no false positives)
# ---------------------------------------------------------------------------


class TestMethodologyDocRefs:
    """Regression suite for check_methodology_doc_refs (Stage-4, 2026-05-25)."""

    def _mk_simple_tree(self, root: Path) -> Path:
        """Scaffold a minimal valid repo tree under root."""
        kb = root / "KNOWLEDGE-BASE" / "CONTEXT" / "PATTERNS"
        kb.mkdir(parents=True, exist_ok=True)
        (kb / "existing.md").write_text("# Existing doc\n")
        (root / "CLAUDE.md").write_text("# CLAUDE\n")
        agents = root / ".claude" / "agents"
        agents.mkdir(parents=True, exist_ok=True)
        return root

    def test_returns_high_severity_for_broken_ref(self, tmp_path):
        """A dangling KB ref → one `high`-severity dict per gap."""
        from tools.noctus.dev.compliance import check_methodology_doc_refs

        self._mk_simple_tree(tmp_path)
        agent = tmp_path / ".claude" / "agents" / "eng.md"
        agent.write_text("`KB § PATTERNS/ghost.md` — a broken ref.\n")

        issues = check_methodology_doc_refs(repo_root=tmp_path)
        assert len(issues) >= 1, f"Expected ≥1 issue, got: {issues}"
        for issue in issues:
            assert issue["severity"] == "high", f"Expected high severity: {issue}"
            assert "ghost.md" in issue["issue"], f"Expected ghost.md in message: {issue}"

    def test_calls_shared_predicate_not_duplicated(self, tmp_path):
        """Compliance keeper reuses methodology_reference_gaps — no duplication.

        Proof: monkeypatching kb_sync.methodology_reference_gaps to return a
        known gap shows that check_methodology_doc_refs surfaces it.
        """
        import unittest.mock as _mock
        from tools.noctus.dev import compliance as _comp

        self._mk_simple_tree(tmp_path)

        fake_gaps = [".claude/agents/eng.md: `KB § PATTERNS/fake.md`"]
        with _mock.patch(
            "tools.kb_sync.methodology_reference_gaps",
            return_value=fake_gaps,
        ):
            issues = _comp.check_methodology_doc_refs(repo_root=tmp_path)

        assert len(issues) == 1, f"Expected 1 issue via shared predicate, got: {issues}"
        assert issues[0]["severity"] == "high"
        assert "fake.md" in issues[0]["issue"]

    def test_placeholder_refs_not_surfaced(self, tmp_path):
        """Placeholder refs do NOT produce issues."""
        from tools.noctus.dev.compliance import check_methodology_doc_refs

        self._mk_simple_tree(tmp_path)
        (tmp_path / "CLAUDE.md").write_text(
            "See `KB § INTEGRATIONS/<x>.md` or `KB § PATTERNS/X.md`.\n"
        )
        issues = check_methodology_doc_refs(repo_root=tmp_path)
        assert issues == [], f"Expected no issues for placeholders but got: {issues}"

    def test_zero_issues_on_real_repo(self):
        """No false positives on the live tree."""
        from tools.noctus.dev.compliance import check_methodology_doc_refs

        issues = check_methodology_doc_refs(repo_root=REPO_ROOT)
        assert issues == [], (
            f"check_methodology_doc_refs found {len(issues)} issue(s) on the "
            f"real repo — must fix before committing:\n"
            + "\n".join(f"  {i['file']}: {i['issue'][:120]}" for i in issues)
        )


# ---------------------------------------------------------------------------
# TestOpenDriftHasResolutionHandle — check_open_drift_has_resolution_handle
#
# Stage-4 keeper (2026-06-01): every OPEN auto-improvement entry past s1
# must carry a `resolve_when` handle so it can self-close / auto-promote.
# Pins true-positive (missing handle) and false-positive shapes.
# ---------------------------------------------------------------------------


class TestOpenDriftHasResolutionHandle:
    """Regression suite for check_open_drift_has_resolution_handle.

    Per KB § PATTERNS/compliance/testing.md § Regression-test-the-detector.
    """

    def _mk_ledger(self, tmp: Path, lines: list[str]) -> Path:
        """Write a minimal auto-improvement.ndjson under tmp."""
        ph = tmp / "project-history"
        ph.mkdir(parents=True, exist_ok=True)
        ledger = ph / "auto-improvement.ndjson"
        ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return tmp

    def test_no_ledger_returns_no_issues(self, tmp_path):
        """When the ledger does not exist (fresh repo), no issues reported."""
        from tools.noctus.dev.compliance import check_open_drift_has_resolution_handle
        issues = check_open_drift_has_resolution_handle(repo_root=tmp_path)
        assert issues == []

    def test_s1_emergent_exempt(self, tmp_path):
        """s1-emergent entries are exempt — too freshly surfaced."""
        import json
        from tools.noctus.dev.compliance import check_open_drift_has_resolution_handle
        row = json.dumps({
            "ts": "2026-06-01T00:00:00", "status": "s1-emergent",
            "target": "some drift", "description": "fresh",
        })
        self._mk_ledger(tmp_path, [row])
        assert check_open_drift_has_resolution_handle(repo_root=tmp_path) == []

    def test_terminal_statuses_exempt(self, tmp_path):
        """closed and s4-keeper are terminal — no resolution handle needed."""
        import json
        from tools.noctus.dev.compliance import check_open_drift_has_resolution_handle
        rows = [
            json.dumps({"ts": "2026-06-01", "status": "closed", "target": "t1",
                        "description": "done"}),
            json.dumps({"ts": "2026-06-01", "status": "s4-keeper", "target": "t2",
                        "description": "promoted"}),
        ]
        self._mk_ledger(tmp_path, rows)
        assert check_open_drift_has_resolution_handle(repo_root=tmp_path) == []

    def test_s2_without_resolve_when_flagged(self, tmp_path):
        """s2-memory entry with no resolve_when → issue with severity medium."""
        import json
        from tools.noctus.dev.compliance import check_open_drift_has_resolution_handle
        row = json.dumps({
            "ts": "2026-06-01T00:00:00", "status": "s2-memory",
            "target": "some unresolved drift", "description": "needs handle",
        })
        self._mk_ledger(tmp_path, [row])
        issues = check_open_drift_has_resolution_handle(repo_root=tmp_path)
        assert len(issues) == 1
        assert issues[0]["severity"] == "medium"
        assert "resolve_when" in issues[0]["issue"]
        assert "s2-memory" in issues[0]["issue"]

    def test_s3_codified_without_resolve_when_flagged(self, tmp_path):
        """s3-codified entry with no resolve_when → issue."""
        import json
        from tools.noctus.dev.compliance import check_open_drift_has_resolution_handle
        row = json.dumps({
            "ts": "2026-06-01T00:00:00", "status": "s3-codified",
            "target": "pending KB doc", "description": "no handle",
        })
        self._mk_ledger(tmp_path, [row])
        issues = check_open_drift_has_resolution_handle(repo_root=tmp_path)
        assert len(issues) == 1
        assert issues[0]["severity"] == "medium"

    def test_s2_with_resolve_when_passes(self, tmp_path):
        """s2-memory entry WITH a resolve_when handle → no issue."""
        import json
        from tools.noctus.dev.compliance import check_open_drift_has_resolution_handle
        row = json.dumps({
            "ts": "2026-06-01T00:00:00", "status": "s2-memory",
            "target": "drift with handle", "description": "handled",
            "resolve_when": "keeper:check_some_detector",
        })
        self._mk_ledger(tmp_path, [row])
        assert check_open_drift_has_resolution_handle(repo_root=tmp_path) == []

    def test_mixed_ledger_only_flags_missing(self, tmp_path):
        """Only the handleless OPEN entries are flagged; clean entries pass."""
        import json
        from tools.noctus.dev.compliance import check_open_drift_has_resolution_handle
        rows = [
            json.dumps({"ts": "2026-06-01", "status": "s2-memory",
                        "target": "a", "description": "no handle"}),
            json.dumps({"ts": "2026-06-01", "status": "s2-memory",
                        "target": "b", "description": "has handle",
                        "resolve_when": "grep_max:0:someterm@some/path"}),
            json.dumps({"ts": "2026-06-01", "status": "s1-emergent",
                        "target": "c", "description": "exempt"}),
            json.dumps({"ts": "2026-06-01", "status": "closed",
                        "target": "d", "description": "terminal"}),
        ]
        self._mk_ledger(tmp_path, rows)
        issues = check_open_drift_has_resolution_handle(repo_root=tmp_path)
        assert len(issues) == 1
        assert "a" in issues[0]["issue"]

    def test_malformed_lines_skipped_gracefully(self, tmp_path):
        """Malformed JSON lines are skipped without raising."""
        import json
        from tools.noctus.dev.compliance import check_open_drift_has_resolution_handle
        ph = tmp_path / "project-history"
        ph.mkdir(parents=True)
        ledger = ph / "auto-improvement.ndjson"
        ledger.write_text(
            '{"status": "s2-memory", "target": "x"}\n'  # missing resolve_when
            'NOT_JSON\n'
            '\n',
            encoding="utf-8",
        )
        issues = check_open_drift_has_resolution_handle(repo_root=tmp_path)
        # Only the valid s2 entry without resolve_when is flagged.
        assert len(issues) == 1


# ---------------------------------------------------------------------------
# TestBranchTreeMirror — check_branch_tree_mirror
#
# Pre-push keeper: ledger + mirror must be byte-identical, every active
# branch pointer must be present with valid git refs and metadata.
# Pins true-positive (drifted mirror, bad status, missing fields) and
# false-positive shapes (absent ledger, terminal branches skip).
# ---------------------------------------------------------------------------


class TestBranchTreeMirror:
    """Regression suite for check_branch_tree_mirror.

    Per KB § PATTERNS/compliance/testing.md § Regression-test-the-detector.
    """

    def _mk_repo(self, tmp: Path) -> Path:
        """Init a minimal bare git repo under tmp so git calls succeed."""
        import subprocess
        subprocess.run(["git", "init", "-b", "main", str(tmp)],
                       capture_output=True, check=True)
        subprocess.run(["git", "-C", str(tmp), "config", "user.email", "t@t.com"],
                       capture_output=True, check=True)
        subprocess.run(["git", "-C", str(tmp), "config", "user.name", "T"],
                       capture_output=True, check=True)
        # Commit an empty file so HEAD exists.
        (tmp / "README.md").write_text("init", encoding="utf-8")
        subprocess.run(["git", "-C", str(tmp), "add", "README.md"],
                       capture_output=True, check=True)
        subprocess.run(["git", "-C", str(tmp), "commit", "-m", "init"],
                       capture_output=True, check=True)
        (tmp / "project-history").mkdir(parents=True, exist_ok=True)
        return tmp

    def _head_sha(self, repo: Path) -> str:
        import subprocess
        r = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                           capture_output=True, text=True, check=True)
        return r.stdout.strip()

    def _write_ledger(self, repo: Path, lines: list[str]) -> None:
        """Write identical ledger + mirror."""
        content = "\n".join(lines) + "\n" if lines else ""
        (repo / "project-history" / "branch-tree.ndjson").write_text(
            content, encoding="utf-8"
        )
        (repo / "project-history" / "branch-tree.mirror.ndjson").write_text(
            content, encoding="utf-8"
        )

    def test_no_ledger_no_branch_returns_no_issues(self, tmp_path):
        """No ledger and no specific branch → nothing to audit, no issues."""
        from tools.noctus.dev.compliance import check_branch_tree_mirror
        self._mk_repo(tmp_path)
        issues = check_branch_tree_mirror(repo_root=tmp_path)
        assert issues == []

    def test_no_ledger_with_specific_branch_flags(self, tmp_path):
        """No ledger but a specific branch is requested → flags missing pointer."""
        from tools.noctus.dev.compliance import check_branch_tree_mirror
        self._mk_repo(tmp_path)
        issues = check_branch_tree_mirror(branch="feat/xyz", repo_root=tmp_path)
        assert len(issues) == 1
        assert "missing" in issues[0]["issue"].lower() or "No pointer" in issues[0]["issue"]

    def test_mirror_drift_flagged(self, tmp_path):
        """Ledger and mirror with different content → issue about drift."""
        from tools.noctus.dev.compliance import check_branch_tree_mirror
        repo = self._mk_repo(tmp_path)
        ph = repo / "project-history"
        ph.mkdir(parents=True, exist_ok=True)
        ledger_content = '{"branch":"feat/x","status":"on_going"}\n'
        mirror_content = '{"branch":"feat/x","status":"shipped"}\n'
        (ph / "branch-tree.ndjson").write_text(ledger_content, encoding="utf-8")
        (ph / "branch-tree.mirror.ndjson").write_text(mirror_content, encoding="utf-8")
        issues = check_branch_tree_mirror(repo_root=tmp_path)
        # At least one issue about the mirror drift.
        drift_issues = [i for i in issues if "DRIFTED" in i["issue"] or "mirror" in i["issue"].lower()]
        assert drift_issues, f"Expected mirror drift issue, got: {issues}"
        assert drift_issues[0]["severity"] == "high"

    def test_null_session_flagged(self, tmp_path):
        """A pointer with a null/empty session → high-severity session gate fires.

        The session field is the claude-tree's owning-session coordinate and must
        never be null (branch_pointer auto-fills it from CLAUDE_CODE_SESSION_ID);
        a null is drift the keeper hard-blocks. Scans ALL rows, incl. terminal.
        """
        from tools.noctus.dev.compliance import check_branch_tree_mirror
        repo = self._mk_repo(tmp_path)
        self._write_ledger(repo, [
            '{"branch":"feat/a","base":"origin/dev","commit":"abc","role":"orchestrator",'
            '"agent":"tech-lead","parent":"origin/dev","session":null,"status":"shipped"}',
            '{"branch":"feat/b","base":"origin/dev","commit":"def","role":"engineer",'
            '"agent":"x","parent":"tech-lead","session":"","status":"on_going"}',
        ])
        issues = check_branch_tree_mirror(repo_root=tmp_path)
        sess = [i for i in issues if "session" in i["issue"]]
        assert sess, f"Expected null-session gate to fire, got: {issues}"
        assert sess[0]["severity"] == "high"
        assert "2 branch-tree pointer" in sess[0]["issue"]

    def test_populated_session_passes(self, tmp_path):
        """All rows carry a non-empty session → no session gate issue."""
        from tools.noctus.dev.compliance import check_branch_tree_mirror
        repo = self._mk_repo(tmp_path)
        self._write_ledger(repo, [
            '{"branch":"feat/a","base":"origin/dev","commit":"abc","role":"orchestrator",'
            '"agent":"tech-lead","parent":"origin/dev",'
            '"session":"fe29a1ad-88aa-414e-8f9f-36385c40f1bd","status":"shipped"}',
        ])
        issues = check_branch_tree_mirror(repo_root=tmp_path)
        sess = [i for i in issues if "session" in i["issue"]]
        assert not sess, f"Expected no session issue, got: {sess}"

    def test_invalid_status_flagged(self, tmp_path):
        """A pointer with an invalid status value → issue."""
        import json
        from tools.noctus.dev.compliance import check_branch_tree_mirror
        repo = self._mk_repo(tmp_path)
        sha = self._head_sha(repo)
        row = json.dumps({
            "branch": "feat/test-invalid",
            "base": "origin/dev",
            "commit": sha,
            "ts": "2026-06-01T00:00:00+00:00",
            "status": "invalid_status_xyz",
            "role": "engineer",
            "agent": "backend-engineer",
            "parent": "feat/parent",
        })
        self._write_ledger(repo, [row])
        issues = check_branch_tree_mirror(branch="feat/test-invalid", repo_root=repo)
        status_issues = [i for i in issues if "invalid_status_xyz" in i["issue"]]
        assert status_issues, f"Expected invalid-status issue, got: {issues}"
        assert status_issues[0]["severity"] == "high"

    def test_terminal_branch_skipped_in_audit_mode(self, tmp_path):
        """In audit mode (branch=None), terminal (shipped/canceled) branches
        are not checked — only non-terminal ones are audited."""
        import json
        from tools.noctus.dev.compliance import check_branch_tree_mirror
        repo = self._mk_repo(tmp_path)
        sha = self._head_sha(repo)
        # Write a shipped branch — terminal, should not appear in audit.
        row = json.dumps({
            "branch": "feat/old-work",
            "base": "origin/dev",
            "commit": sha,
            "ts": "2026-01-01T00:00:00+00:00",
            "status": "shipped",
            "role": "engineer",
            "agent": "backend-engineer",
            "parent": "feat/orchestrator",
            "session": "2026-01-01-old-work",  # session-populated invariant
        })
        self._write_ledger(repo, [row])
        # Audit mode should find no non-terminal branches.
        issues = check_branch_tree_mirror(repo_root=repo)
        # No issues about shipped branch (even though commit may be in history).
        non_parity = [i for i in issues if "DRIFTED" not in i.get("issue", "")]
        assert non_parity == [], f"Shipped branch should be skipped in audit, got: {non_parity}"

    def test_missing_role_agent_parent_flagged(self, tmp_path):
        """Claude-tree fields (role/agent/parent) missing → issues for each."""
        import json
        from tools.noctus.dev.compliance import check_branch_tree_mirror
        repo = self._mk_repo(tmp_path)
        sha = self._head_sha(repo)
        row = json.dumps({
            "branch": "feat/incomplete",
            "base": "origin/dev",
            "commit": sha,
            "ts": "2026-06-01T00:00:00+00:00",
            "status": "on_going",
            "role": "",
            "agent": "",
            "parent": "",
        })
        self._write_ledger(repo, [row])
        issues = check_branch_tree_mirror(branch="feat/incomplete", repo_root=repo)
        field_issues = [i for i in issues if "missing claude-tree field" in i["issue"]]
        # role, agent, parent all missing → 3 field issues.
        assert len(field_issues) == 3, f"Expected 3 missing-field issues, got: {field_issues}"
