"""Pins the ASLEEP-product CI gate in `.github/workflows/test.yml`
(2026-09-22).

WHY. The user decided a subset of products (`deploy/fleet/active-scope.txt`,
GENERATED from the catalog: `academia-de-reciclagem`, `agents`, `community`,
`core`, `igig`, `orbity`, `p-studio`, `seed`, `social-wiring`) are AWAKE;
everything else (`adconnect`, `daily-life`, `dev-team`, `erp-imobiliario`,
`knowledge-extractor`, `personal-finance`, `therapy-platform`) is ASLEEP and
must be out of the CI process until reactivated. The workflow now derives
that scope from `active-scope.txt` at run time instead of hand-listing which
products are awake or asleep — the exact drift class
`check_hardcoded_product_slug_set` exists to stop elsewhere in the repo
(hand-maintained slug sets silently stop tracking the catalog).

This test does NOT re-implement a CI run. It pins two structural invariants
cheaply, from disk:

1. The `changes` job actually reads `deploy/fleet/active-scope.txt` (the
   single source of truth) rather than assuming/hardcoding the split.
2. No hand-maintained awake/asleep SLUG SET literal creeps back into the
   workflow — the two `strategy: matrix: product:` lists in
   `product-backend-tests` / `product-frontend-tests` are the one legitimate
   place a full product enumeration lives (required by
   `check_ci_test_matrix_coverage`, and mixed awake+asleep by construction —
   reactivating a product must cost zero workflow edits), so those are
   excluded before scanning for a NEW hardcoded group.

→ KB § PATTERNS/devops/product-lockfile-and-slug-drift.md
→ KB § PATTERNS/architect/product-working-scope.md
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = REPO / ".github" / "workflows" / "test.yml"

# The 2026-09-22 split, used only as SCAN INPUT (never re-encoded as a
# workflow literal by this test's assertions) — the same slugs the task that
# built this gate named explicitly.
_ASLEEP = [
    "adconnect", "daily-life", "dev-team", "erp-imobiliario",
    "knowledge-extractor", "personal-finance", "therapy-platform",
]
_AWAKE = [
    "academia-de-reciclagem", "agents", "community", "core", "igig",
    "orbity", "p-studio", "seed", "social-wiring",
]

_REQUIRED_MATRIX_JOBS = ("product-backend-tests", "product-frontend-tests")

# A plain YAML list item that is EXACTLY one product slug and nothing else —
# the shape a hand-maintained `product:` / `dormant:` / `awake:` array takes.
_SLUG_LIST_ITEM_RE = re.compile(r"^\s*-\s*([a-z][a-z0-9\-]*)\s*$")


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _workflow_doc() -> dict:
    return yaml.safe_load(_workflow_text())


def _text_minus_required_matrices(text: str) -> str:
    """Strip the two REQUIRED `matrix.product` lists (product-backend-tests,
    product-frontend-tests) — the one place a full, mixed awake+asleep
    product enumeration is supposed to live verbatim. Everything else is
    fair game for the hardcoded-slug-set scan below."""
    doc = yaml.safe_load(text)
    jobs = doc["jobs"]
    out = text
    for job_name in _REQUIRED_MATRIX_JOBS:
        products = jobs[job_name]["strategy"]["matrix"]["product"]
        for slug in products:
            out = out.replace(f"          - {slug}\n", "", 1)
    return out


class TestWorkflowParses:
    def test_workflow_file_exists_and_parses_as_yaml(self):
        assert WORKFLOW_PATH.exists()
        doc = _workflow_doc()
        assert "changes" in doc["jobs"]


class TestActiveScopeIsTheSourceOfTruth:
    def test_changes_job_reads_active_scope_txt(self):
        """The `changes` job must actually reference
        `deploy/fleet/active-scope.txt` — not assume/hardcode the split."""
        doc = _workflow_doc()
        changes_job = doc["jobs"]["changes"]
        step_bodies = "\n".join(s.get("run", "") for s in changes_job["steps"])
        assert "deploy/fleet/active-scope.txt" in step_bodies

    def test_changes_job_declares_active_products_output(self):
        doc = _workflow_doc()
        outputs = doc["jobs"]["changes"]["outputs"]
        assert "active_products" in outputs
        # must route through the classify step's own output, not a literal
        assert "steps.classify.outputs.active_products" in outputs["active_products"]

    def test_active_scope_file_is_a_shared_root_trigger(self):
        """Waking a product (editing/regenerating active-scope.txt) must
        re-test it immediately — the file itself joins the shared-root diff
        classification, not just the up-front active-set computation."""
        doc = _workflow_doc()
        classify_run = doc["jobs"]["changes"]["steps"][-1]["run"]
        # once for the up-front active-set read, once more in the
        # shared-root regex branch
        assert classify_run.count("active-scope") >= 2

    def test_missing_scope_file_fails_toward_coverage_not_silence(self):
        """A missing active-scope.txt must run everything + warn — never
        silently narrow the gates (product_scope.filter_active's own
        contract, mirrored here at the workflow level)."""
        doc = _workflow_doc()
        classify_run = doc["jobs"]["changes"]["steps"][-1]["run"]
        assert "::warning::" in classify_run
        assert "active_products=ALL" in classify_run


class TestScopeGateCoversEveryEventType:
    """The per-matrix-entry 'Scope gate' step must skip an asleep product
    unconditionally — before it ever looks at what changed in this diff (a
    diff-scoped check would only apply on push/PR, not workflow_dispatch or
    the always-full-suite branches)."""

    def _gate_run(self, job_name: str) -> str:
        doc = _workflow_doc()
        for step in doc["jobs"][job_name]["steps"]:
            if step.get("id") == "gate":
                return step["run"]
        raise AssertionError(f"no 'gate' step found in {job_name}")

    def test_backend_gate_checks_active_scope_before_the_diff(self):
        run = self._gate_run("product-backend-tests")
        assert "active-scope.txt" in run
        asleep_pos = run.find("active_products")
        diff_pos = run.find("shared_changed")
        assert 0 <= asleep_pos < diff_pos, "active-scope check must precede the diff-based check"

    def test_frontend_gate_checks_active_scope_before_the_diff(self):
        run = self._gate_run("product-frontend-tests")
        assert "active-scope.txt" in run
        asleep_pos = run.find("active_products")
        diff_pos = run.find("shared_changed")
        assert 0 <= asleep_pos < diff_pos, "active-scope check must precede the diff-based check"

    def test_gate_notice_message_matches_the_specified_shape(self):
        for job_name in _REQUIRED_MATRIX_JOBS:
            run = self._gate_run(job_name)
            assert "asleep (not in deploy/fleet/active-scope.txt)" in run


class TestSingleProductJobsAreGatedAtJobLevel:
    """erp-frontend-build / pf-frontend-build / erp-e2e-tests are not
    matrixed, so they cannot use a per-entry 'Scope gate' step — they must
    gate on `needs.changes.outputs.active_products` in their job-level
    `if:` instead."""

    def test_erp_frontend_build_gated_on_active_products(self):
        doc = _workflow_doc()
        cond = doc["jobs"]["erp-frontend-build"]["if"]
        assert "active_products" in cond
        assert "erp-imobiliario" in cond

    def test_pf_frontend_build_gated_on_active_products(self):
        doc = _workflow_doc()
        cond = doc["jobs"]["pf-frontend-build"]["if"]
        assert "active_products" in cond
        assert "personal-finance" in cond

    def test_erp_e2e_tests_gated_on_active_products(self):
        doc = _workflow_doc()
        cond = doc["jobs"]["erp-e2e-tests"]["if"]
        assert "active_products" in cond
        assert "erp-imobiliario" in cond

    def test_gates_fail_toward_coverage_on_a_missing_scope_file(self):
        for job_name, slug in (
            ("erp-frontend-build", "erp-imobiliario"),
            ("pf-frontend-build", "personal-finance"),
            ("erp-e2e-tests", "erp-imobiliario"),
        ):
            doc = _workflow_doc()
            cond = doc["jobs"][job_name]["if"]
            assert "== 'ALL'" in cond, f"{job_name} must fail-open on a missing scope file"


class TestDockerComposeValidateSkipsAsleepProducts:
    def test_per_product_loop_checks_active_scope(self):
        doc = _workflow_doc()
        steps = doc["jobs"]["docker-compose-validate"]["steps"]
        loop_step = next(s for s in steps if "standalone" in s.get("name", "").lower())
        assert "active-scope.txt" in loop_step["run"] or "active_products" in loop_step["run"]


class TestTrivyAndBanditDeriveDormantSetAtRuntime:
    def test_trivy_skip_dirs_computed_from_a_step_not_hardcoded(self):
        doc = _workflow_doc()
        steps = doc["jobs"]["trivy-fs-scan"]["steps"]
        scan_step = next(s for s in steps if s.get("uses", "").startswith("aquasecurity/trivy-action"))
        skip_dirs = scan_step["with"]["skip-dirs"]
        # must be an expression referencing a computed step output, never a
        # literal comma list of the dormant product dirs
        assert "steps." in str(skip_dirs) and "outputs" in str(skip_dirs)
        for slug in _ASLEEP:
            assert f"products/{slug}" not in str(skip_dirs)

    def test_bandit_dirs_computed_from_a_step_not_hardcoded(self):
        doc = _workflow_doc()
        steps = doc["jobs"]["bandit-scan"]["steps"]
        run_steps = [s for s in steps if "bandit -r" in s.get("run", "")]
        assert len(run_steps) == 2  # SARIF report + baseline gate
        for s in run_steps:
            assert "products/*/backend/app/" not in s["run"]
            env = s.get("env", {})
            assert "BANDIT_DIRS" in env
            assert "steps.scope.outputs.dirs" in env["BANDIT_DIRS"]


class TestNoHardcodedAwakeOrAsleepSlugSet:
    """The drift class this whole gate exists to avoid: a hand-maintained
    list of which products are awake/asleep, silently going stale the next
    time a product is reactivated (`check_hardcoded_product_slug_set`'s
    domain, applied here to the workflow itself)."""

    def test_no_line_names_three_or_more_asleep_slugs_at_once(self):
        # Prose comments (rationale history: "core / adconnect / dev-team
        # had FE test infra but ZERO test files") legitimately name several
        # products in a sentence — that is not a data literal a job branches
        # on, so comment-only lines are out of scope for this scan.
        text = _text_minus_required_matrices(_workflow_text())
        for line in text.splitlines():
            if line.strip().startswith("#"):
                continue
            hits = sum(1 for slug in _ASLEEP if slug in line)
            assert hits < 3, f"line looks like a hardcoded asleep-slug set: {line!r}"

    def test_no_line_names_three_or_more_awake_slugs_at_once(self):
        text = _text_minus_required_matrices(_workflow_text())
        for line in text.splitlines():
            if line.strip().startswith("#"):
                continue
            hits = sum(1 for slug in _AWAKE if slug in line)
            assert hits < 3, f"line looks like a hardcoded awake-slug set: {line!r}"

    def test_no_consecutive_yaml_list_run_of_three_or_more_same_class(self):
        """Catches a NEW hand-written YAML array (one slug per `- slug`
        line) that is entirely asleep-only or awake-only, anywhere outside
        the two required (and legitimately mixed) matrices."""
        text = _text_minus_required_matrices(_workflow_text())
        run: list[str] = []

        def _check_and_reset():
            if len(run) >= 3:
                all_asleep = all(s in _ASLEEP for s in run)
                all_awake = all(s in _AWAKE for s in run)
                assert not all_asleep, f"consecutive asleep-only slug list: {run}"
                assert not all_awake, f"consecutive awake-only slug list: {run}"
            run.clear()

        for line in text.splitlines():
            m = _SLUG_LIST_ITEM_RE.match(line)
            if m and (m.group(1) in _ASLEEP or m.group(1) in _AWAKE):
                run.append(m.group(1))
            else:
                _check_and_reset()
        _check_and_reset()
