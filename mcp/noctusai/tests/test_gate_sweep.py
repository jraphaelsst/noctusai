"""Colocated tests for noctus.dev.gate_sweep.

Fully hermetic — `git_runner` (FakeGitRunner, imported from
`migrate_product` — the exact same shape, per the module docstring's
"match it exactly" posture) and `run_gate` are both injected. No real
subprocess, no real git, no real filesystem beyond `tmp_path` fixtures used
to make `_build_gate_specs`' existence checks (backend/tests,
frontend/package.json) resolve realistically.

Covers: scope derivation for each of the four buckets (product / seed-fleet
/ mcp / doc-only) + the unmapped-diff fallback, gate-spec construction per
bucket, the verdict function (green / red / incomplete, red-over-incomplete
priority), full `gate_sweep()` orchestration (green / red / incomplete /
stale-tree refusal / allow_stale_tree bypass), and the porcelain-path
parser (plain + rename shapes).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import gate_sweep as GS  # noqa: E402
from tools.noctus.dev.migrate_product import (  # noqa: E402
    FakeGitRunner,
    SubprocessGitRunner,
)


# ── scope derivation ──────────────────────────────────────────────


def test_scope_product_diff():
    scope = GS._derive_scope([
        "products/erp-imobiliario/backend/app/routers/leads.py",
        "products/erp-imobiliario/frontend/src/App.tsx",
    ])
    assert scope["products"] == ["erp-imobiliario"]
    assert scope["seed_fleet_wide"] is False
    assert scope["mcp"] is False
    assert scope["doc_only"] is False
    assert scope["unmapped_files"] == []


def test_scope_two_products():
    scope = GS._derive_scope([
        "products/core/backend/app/main.py",
        "products/igig/frontend/src/pages/Home.tsx",
    ])
    assert scope["products"] == ["core", "igig"]


def test_scope_seed_diff_is_fleet_wide():
    scope = GS._derive_scope(["seed/lib/backend/noctusai_lib/domain/x.py"])
    assert scope["seed_fleet_wide"] is True
    assert scope["products"] == []


def test_scope_products_seed_is_a_product_not_fleet_wide():
    """`products/seed/...` is the dogfood reference PRODUCT (slug 'seed') —
    a different thing from the top-level `seed/` framework+lib tree, even
    though both are named "seed". Must NOT trip fleet-wide."""
    scope = GS._derive_scope(["products/seed/backend/app/main.py"])
    assert scope["products"] == ["seed"]
    assert scope["seed_fleet_wide"] is False


def test_scope_mcp_diff():
    scope = GS._derive_scope(["mcp/noctusai/tools/noctus/dev/gate_sweep.py"])
    assert scope["mcp"] is True
    assert scope["products"] == []
    assert scope["seed_fleet_wide"] is False


def test_scope_doc_only_diff():
    scope = GS._derive_scope([
        "KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/methodology-execution-discipline.md",
    ])
    assert scope["doc_only"] is True
    assert scope["claude_md_touched"] is False


def test_scope_claude_md_touched_flag():
    scope = GS._derive_scope(["CLAUDE.md"])
    assert scope["doc_only"] is True
    assert scope["claude_md_touched"] is True


def test_scope_mixed_doc_and_code_is_not_doc_only():
    """A doc file alongside a code file is NOT doc-only — the doc gates
    only fire when the ENTIRE diff is doc/KB, per the brief's literal
    mapping ('KB/doc-only ⇒ the doc gates')."""
    scope = GS._derive_scope([
        "CLAUDE.md",
        "products/core/backend/app/main.py",
    ])
    assert scope["doc_only"] is False
    assert scope["products"] == ["core"]


def test_scope_unmapped_file_surfaced_not_dropped():
    scope = GS._derive_scope(["deploy/fleet/docker-compose.prod.yml"])
    assert scope["unmapped_files"] == ["deploy/fleet/docker-compose.prod.yml"]
    assert scope["products"] == []
    assert scope["doc_only"] is False


def test_scope_empty_diff():
    scope = GS._derive_scope([])
    assert scope["products"] == []
    assert scope["seed_fleet_wide"] is False
    assert scope["doc_only"] is False
    assert scope["unmapped_files"] == []


# ── gate-spec construction ────────────────────────────────────────


def _make_product(
    root: Path, slug: str, *, backend=True, frontend=True, wired=True, e2e=False
) -> None:
    """`wired=True` gives the frontend a `node_modules/` — i.e. a VALID
    harness. It is the default because almost every test here is about
    verdict logic, and an unwired fixture would make those gates
    `harness_invalid` (correctly: you cannot build without deps) and mask
    what they mean to assert. `wired=False` is how the harness-validity
    tests below get an INVALID one on purpose."""
    if backend:
        (root / "products" / slug / "backend" / "tests").mkdir(parents=True)
    if frontend:
        fe = root / "products" / slug / "frontend"
        fe.mkdir(parents=True)
        (fe / "package.json").write_text("{}")
        if wired:
            (fe / "node_modules").mkdir()
        if e2e:
            (fe / "playwright.config.ts").write_text("export default {}")
            (fe / "e2e").mkdir()
            if wired:
                (fe / "node_modules" / "@playwright" / "test").mkdir(parents=True)


def test_build_gate_specs_product_scope(tmp_path):
    _make_product(tmp_path, "erp-imobiliario")
    scope = GS._derive_scope(["products/erp-imobiliario/backend/app/main.py"])
    specs = GS._build_gate_specs(tmp_path, scope)
    names = sorted(s.gate for s in specs)
    assert names == ["pytest:erp-imobiliario", "vite_build:erp-imobiliario"]


def test_build_gate_specs_product_backend_only_no_frontend_gate(tmp_path):
    _make_product(tmp_path, "core", frontend=False)
    scope = GS._derive_scope(["products/core/backend/app/main.py"])
    specs = GS._build_gate_specs(tmp_path, scope)
    names = [s.gate for s in specs]
    assert names == ["pytest:core"]  # no frontend -> no vite_build gate at all,
    # never a listed-but-structurally-impossible entry


def test_build_gate_specs_mcp_scope(tmp_path):
    scope = GS._derive_scope(["mcp/noctusai/tools/noctus/dev/gate_sweep.py"])
    specs = GS._build_gate_specs(tmp_path, scope)
    assert [s.gate for s in specs] == ["mcp_toolkit_tests"]
    assert specs[0].cwd == tmp_path


def test_build_gate_specs_doc_only_scope_without_claude_md(tmp_path):
    scope = GS._derive_scope(["KNOWLEDGE-BASE/CONTEXT/PATTERNS/x.md"])
    specs = GS._build_gate_specs(tmp_path, scope)
    assert [s.gate for s in specs] == ["kb_sync_verify"]


def test_build_gate_specs_doc_only_scope_with_claude_md():
    scope = GS._derive_scope(["CLAUDE.md"])
    specs = GS._build_gate_specs(Path("/tmp/does-not-matter"), scope)
    assert [s.gate for s in specs] == ["kb_sync_verify", "claude_md_router"]


def test_build_gate_specs_seed_fleet_wide_includes_seed_roots_and_every_product(tmp_path):
    (tmp_path / "seed" / "lib" / "backend" / "tests").mkdir(parents=True)
    (tmp_path / "seed" / "framework" / "backend" / "tests").mkdir(parents=True)
    fe1 = tmp_path / "seed" / "lib" / "frontend"
    fe1.mkdir(parents=True)
    (fe1 / "package.json").write_text("{}")
    # framework/frontend deliberately absent — must not be listed (no package.json)
    _make_product(tmp_path, "a-product")
    _make_product(tmp_path, "b-product", frontend=False)

    scope = GS._derive_scope(["seed/lib/backend/noctusai_lib/x.py"])
    specs = GS._build_gate_specs(tmp_path, scope)
    names = {s.gate for s in specs}
    assert "pytest:seed/lib/backend" in names
    assert "pytest:seed/framework/backend" in names
    assert "vitest:seed/lib/frontend" in names
    assert "vitest:seed/framework/frontend" not in names  # no package.json -> not listed
    assert "pytest:a-product" in names and "vite_build:a-product" in names
    assert "pytest:b-product" in names and "vite_build:b-product" not in names


# ── verdict ────────────────────────────────────────────────────────


def test_verdict_all_green():
    gates = [
        {"gate": "a", "ran": True, "exit_code": 0},
        {"gate": "b", "ran": True, "exit_code": 0},
    ]
    assert GS._verdict(gates) == "green"


def test_verdict_empty_is_green():
    assert GS._verdict([]) == "green"


def test_verdict_a_failure_is_red():
    gates = [
        {"gate": "a", "ran": True, "exit_code": 0},
        {"gate": "b", "ran": True, "exit_code": 1},
    ]
    assert GS._verdict(gates) == "red"


def test_verdict_unrun_gate_is_incomplete_never_green():
    gates = [
        {"gate": "a", "ran": True, "exit_code": 0},
        {"gate": "b", "ran": False, "exit_code": None},
    ]
    assert GS._verdict(gates) == "incomplete"


def test_verdict_red_takes_priority_over_incomplete():
    gates = [
        {"gate": "a", "ran": True, "exit_code": 1},
        {"gate": "b", "ran": False, "exit_code": None},
    ]
    assert GS._verdict(gates) == "red"


# ── porcelain parser ─────────────────────────────────────────────


def test_porcelain_paths_plain():
    out = " M products/core/backend/app/main.py\n?? new_file.py\n"
    assert GS._porcelain_paths(out) == [
        "products/core/backend/app/main.py",
        "new_file.py",
    ]


def test_porcelain_paths_rename_shape_keeps_new_path():
    out = "R  old/path.py -> new/path.py\n"
    assert GS._porcelain_paths(out) == ["new/path.py"]


# ── full orchestration (fake git + fake gate runner) ──────────────


def _clean_git_runner(diff_files: str = "", status: str = "") -> FakeGitRunner:
    return FakeGitRunner(
        responses={
            ("rev-parse", "--abbrev-ref", "HEAD"): "feat/x",
            ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/feat/x",
            ("rev-list", "--count", "HEAD..origin/feat/x"): "0",
            ("status", "--porcelain"): status,
            ("diff", "--name-only", "origin/dev...HEAD"): diff_files,
        }
    )


def test_gate_sweep_all_green(tmp_path):
    _make_product(tmp_path, "core")
    git_runner = _clean_git_runner(diff_files="products/core/backend/app/main.py\n")

    def fake_run(spec):
        return 0, "ok", 1.23

    result = GS.gate_sweep(
        repo_root=str(tmp_path), git_runner=git_runner, run_gate=fake_run,
    )
    assert result["ok"] is True
    assert result["status"] == "green"
    assert result["exit_code"] == 0
    assert {g["gate"] for g in result["gates"]} == {"pytest:core", "vite_build:core"}
    assert all(g["ran"] and g["exit_code"] == 0 for g in result["gates"])


def test_gate_sweep_one_gate_fails_is_red(tmp_path):
    _make_product(tmp_path, "core")
    git_runner = _clean_git_runner(diff_files="products/core/backend/app/main.py\n")

    def fake_run(spec):
        if spec.gate == "pytest:core":
            return 1, "3 failed", 2.0
        return 0, "built", 0.5

    result = GS.gate_sweep(
        repo_root=str(tmp_path), git_runner=git_runner, run_gate=fake_run,
    )
    assert result["status"] == "red"
    assert result["exit_code"] == 1


def test_gate_sweep_unrun_gate_is_incomplete_not_green(tmp_path):
    """The exact shape of incident #1: a gate that never ran must NEVER be
    reported as green, even when every gate that DID run passed."""
    _make_product(tmp_path, "core")
    git_runner = _clean_git_runner(diff_files="products/core/backend/app/main.py\n")

    def fake_run(spec):
        if spec.gate == "pytest:core":
            return None, "timeout after 300s", 300.0
        return 0, "built", 0.5

    result = GS.gate_sweep(
        repo_root=str(tmp_path), git_runner=git_runner, run_gate=fake_run,
    )
    assert result["status"] == "incomplete"
    assert result["status"] != "green"
    pytest_entry = next(g for g in result["gates"] if g["gate"] == "pytest:core")
    assert pytest_entry["ran"] is False
    assert pytest_entry["exit_code"] is None


def test_gate_sweep_unmapped_diff_blocks_green(tmp_path):
    git_runner = _clean_git_runner(diff_files="deploy/fleet/docker-compose.prod.yml\n")
    result = GS.gate_sweep(
        repo_root=str(tmp_path), git_runner=git_runner, run_gate=lambda spec: (0, "ok", 0.1),
    )
    assert result["status"] == "incomplete"
    unmapped = next(g for g in result["gates"] if g["gate"] == "unmapped_diff")
    assert unmapped["ran"] is False
    assert "docker-compose.prod.yml" in unmapped["summary"]


def test_gate_sweep_empty_diff_is_vacuously_green(tmp_path):
    git_runner = _clean_git_runner()
    result = GS.gate_sweep(
        repo_root=str(tmp_path), git_runner=git_runner, run_gate=lambda spec: (0, "ok", 0.1),
    )
    assert result["status"] == "green"
    assert result["gates"] == []


def test_gate_sweep_refuses_stale_tree(tmp_path):
    stale_runner = FakeGitRunner(
        responses={
            ("rev-parse", "--abbrev-ref", "HEAD"): "feat/x",
            ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/feat/x",
            ("rev-list", "--count", "HEAD..origin/feat/x"): "5",
        }
    )
    result = GS.gate_sweep(
        repo_root=str(tmp_path), git_runner=stale_runner, run_gate=lambda spec: (0, "ok", 0.1),
    )
    assert result["status"] == "refused_stale_tree"
    assert result["exit_code"] == 1
    assert result["gates"] == []
    assert result["stale_tree"]["stale"] is True


def test_gate_sweep_allow_stale_tree_bypasses(tmp_path):
    stale_runner = FakeGitRunner(
        responses={
            ("rev-parse", "--abbrev-ref", "HEAD"): "feat/x",
            ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/feat/x",
            ("rev-list", "--count", "HEAD..origin/feat/x"): "5",
            ("status", "--porcelain"): "",
            ("diff", "--name-only", "origin/dev...HEAD"): "",
        }
    )
    result = GS.gate_sweep(
        repo_root=str(tmp_path), git_runner=stale_runner,
        run_gate=lambda spec: (0, "ok", 0.1), allow_stale_tree=True,
    )
    assert result["status"] == "green"
    assert result["allow_stale_tree"] is True
    assert result["stale_tree"]["stale"] is True  # visible even though bypassed — never silent


# ── SubprocessGitRunner real-git regression (found building this tool) ─

def _run(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, check=True, timeout=15,
    ).stdout


class TestSubprocessGitRunnerPorcelainIntegrity:
    """`SubprocessGitRunner.run()` used to `.strip()` the WHOLE multi-line
    stdout blob — which trims the leading space off `git status
    --porcelain`'s FIRST line when that line's own status code starts with
    a space (` M path`, the common "modified, not staged" code), silently
    eating the first character of that one path
    (`KNOWLEDGE-BASE/...` -> `NOWLEDGE-BASE/...`). `FakeGitRunner`-based
    tests can never exercise this (the Fake returns exact canned strings);
    a real subprocess is required. Deliberately NOT hermetic — mirrors
    `TestBranchOrphan`'s real-tmp-repo pattern in
    `test_compliance_hygiene.py`."""

    def test_leading_space_status_line_not_corrupted(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, timeout=10)
        _run(repo, "config", "user.email", "test@example.com")
        _run(repo, "config", "user.name", "Test")
        # A path that alphabetically sorts FIRST in porcelain output, so its
        # ` M ` (leading-space) status code lands on the very first line of
        # the blob `SubprocessGitRunner.run()` returns.
        (repo / "AAA_file.txt").write_text("v1\n")
        _run(repo, "add", "AAA_file.txt")
        _run(repo, "commit", "-q", "-m", "initial")
        (repo / "AAA_file.txt").write_text("v2\n")  # modified, NOT staged -> " M "

        runner = SubprocessGitRunner()
        out = runner.run(repo, ["status", "--porcelain"])
        assert out.startswith(" M "), f"leading status-code space must survive, got: {out!r}"
        paths = GS._porcelain_paths(out)
        assert paths == ["AAA_file.txt"], f"path's first char must not be eaten, got: {paths}"


def test_gate_sweep_diff_query_failure_is_a_warning_not_a_crash(tmp_path):
    runner = FakeGitRunner(
        responses={
            ("rev-parse", "--abbrev-ref", "HEAD"): "feat/x",
            ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/feat/x",
            ("rev-list", "--count", "HEAD..origin/feat/x"): "0",
            ("status", "--porcelain"): "",
        },
        fail_on={("diff", "--name-only", "origin/dev...HEAD")},
    )
    result = GS.gate_sweep(
        repo_root=str(tmp_path), git_runner=runner, run_gate=lambda spec: (0, "ok", 0.1),
    )
    assert result["ok"] is True
    assert result["warnings"], "diff-query failure must surface as a warning, not be swallowed"


# ── harness validity ──────────────────────────────────────────────────────
#
# The 2026-09-20 class: a red that is about the HARNESS, not the code. Every
# `output` below is VERBATIM from a real run in that session.


_PLAYWRIGHT_NO_BROWSER = (
    "Error: browserType.launch: Executable doesn't exist at "
    "/Users/x/Library/Caches/ms-playwright/chromium-1201/chrome-mac/Chromium.app\n"
    "Please run the following command to download new browsers:\n"
    "    npx playwright install\n"
)
_WEBSERVER_DEAD = (
    "[WebServer] error when starting dev server:\n"
    "Error: Process from config.webServer was not able to start. Exit code: 1\n"
)
_UNWIRED_SEED = (
    '[vite]: Rollup failed to resolve import "@noctusai/lib/design-system" '
    'from "src/App.tsx"\n'
)
_VENVLESS = "ModuleNotFoundError: No module named 'noctusai_lib'\n"
# Verbatim from running the real sweep over products/agents, 2026-09-20.
_PYTEST_COLLECTION = (
    "E   ModuleNotFoundError: No module named 'claude_agent_sdk'\n"
    "!!!!!!!! Interrupted: 5 errors during collection !!!!!!!!\n"
)


def test_signature_matches_every_real_2026_09_20_harness_fault():
    """Prove the detector can FIRE — on the actual output each fault
    produced, not a paraphrase of it."""
    assert GS._harness_suspect(_PLAYWRIGHT_NO_BROWSER)["signature"] == "playwright_browser_missing"
    assert GS._harness_suspect(_WEBSERVER_DEAD)["signature"] == "webserver_never_started"
    assert GS._harness_suspect(_UNWIRED_SEED)["signature"] == "node_deps_missing"
    assert GS._harness_suspect(_VENVLESS)["signature"] == "python_env_missing"
    assert GS._harness_suspect(_PYTEST_COLLECTION)["signature"] == "pytest_collection_error"


def test_signature_does_not_fire_on_genuine_failures():
    """Prove it can STAY SILENT. A signature that swallowed a real red
    would be the same harm pointed the other way — it would hide the bug
    instead of inventing one."""
    for genuine in (
        "Error: expect(locator).toHaveAttribute(expected) failed",
        "AssertionError: assert 3 == 4",
        'Failed to resolve import "./components/Missing" from "src/App.tsx"',
        "ModuleNotFoundError: No module named 'app.services.nope'",
        "src/App.tsx(12,3): error TS2304: Cannot find name 'foo'.",
        "  2 failed\n  49 passed (1.7m)",
        "1 failed, 42 passed in 0.28s",
        "FAILED tests/test_x.py::test_y - AssertionError",
    ):
        assert GS._harness_suspect(genuine) is None, genuine


def test_signature_carries_its_evidence_line():
    """A reclassification you cannot audit is just a different guess."""
    hit = GS._harness_suspect(_PLAYWRIGHT_NO_BROWSER)
    assert "Executable doesn't exist" in hit["matched_line"]
    assert "playwright install" in hit["remedy"]


def test_unwired_frontend_gate_is_not_run_at_all(tmp_path):
    """The precondition leg: no node_modules => the gate never runs, so
    there is no exit code to mistake for a verdict about the code."""
    _make_product(tmp_path, "core", backend=False, wired=False)
    git_runner = _clean_git_runner(diff_files="products/core/frontend/src/App.tsx\n")
    ran: list[str] = []

    def fake_run(spec):
        ran.append(spec.gate)
        return 1, "boom", 0.1, "boom"

    result = GS.gate_sweep(repo_root=str(tmp_path), git_runner=git_runner, run_gate=fake_run)
    assert "vite_build:core" not in ran, "an invalid harness must not be RUN"
    entry = next(g for g in result["gates"] if g["gate"] == "vite_build:core")
    assert entry["ran"] is False
    assert entry["exit_code"] is None
    assert entry["harness_invalid"][0]["precondition"] == "node_modules"
    assert "npm ci" in entry["harness_invalid"][0]["remedy"]
    assert result["status"] == "inconclusive"
    assert result["exit_code"] == 1, "not-measured is never a pass"
    assert result["harness"]["invalid"][0]["gate"] == "vite_build:core"


def test_missing_file_linked_seed_dep_is_a_precondition(tmp_path):
    """Fault #5: `npm ci` does NOT install a `file:`-linked @noctusai dep,
    so node_modules can exist while the app still cannot build."""
    _make_product(tmp_path, "core")
    fe = tmp_path / "products" / "core" / "frontend"
    fe.joinpath("package.json").write_text('{"dependencies": {"@noctusai/lib": "file:../../../seed/lib/frontend"}}')
    pres = GS._node_preconditions(fe)
    assert [p.name for p in pres] == ["node_modules", "@noctusai/lib"]
    assert not pres[1].path.exists()
    (fe / "node_modules" / "@noctusai" / "lib").mkdir(parents=True)
    assert all(p.path.exists() for p in GS._node_preconditions(fe))


def test_all_failures_suspect_is_inconclusive_never_red(tmp_path):
    """The signature leg, and the whole point: when every red carries a
    harness signature, there is no trustworthy red to report."""
    _make_product(tmp_path, "core")
    git_runner = _clean_git_runner(diff_files="products/core/frontend/src/App.tsx\n")

    def fake_run(spec):
        return 1, "failed", 0.1, _PLAYWRIGHT_NO_BROWSER

    result = GS.gate_sweep(repo_root=str(tmp_path), git_runner=git_runner, run_gate=fake_run)
    assert result["status"] == "inconclusive"
    entry = next(g for g in result["gates"] if g["gate"] == "vite_build:core")
    assert entry["harness_suspect"]["signature"] == "playwright_browser_missing"
    assert {s["gate"] for s in result["harness"]["suspects"]} == {"pytest:core", "vite_build:core"}


def test_a_genuine_red_still_wins_over_a_suspect(tmp_path):
    """A known real failure stays the headline — downgrading it would hide
    a real bug behind a setup complaint."""
    _make_product(tmp_path, "core")
    git_runner = _clean_git_runner(diff_files="products/core/backend/app/main.py\n")

    def fake_run(spec):
        if spec.gate == "pytest:core":
            return 1, "3 failed", 2.0, "AssertionError: assert 3 == 4"
        return 1, "failed", 0.1, _PLAYWRIGHT_NO_BROWSER

    result = GS.gate_sweep(repo_root=str(tmp_path), git_runner=git_runner, run_gate=fake_run)
    assert result["status"] == "red"
    assert len(result["harness"]["suspects"]) == 1


def test_e2e_gate_is_derived_for_products_with_playwright(tmp_path):
    """The suite CI enforces was missing from the local sweep entirely —
    which is how a Playwright investigation ended up in raw shell."""
    _make_product(tmp_path, "erp-imobiliario", e2e=True)
    scope = GS._derive_scope(["products/erp-imobiliario/frontend/e2e/tests/metas.spec.ts"])
    specs = GS._build_gate_specs(tmp_path, scope)
    assert "e2e:erp-imobiliario" in {s.gate for s in specs}
    e2e_spec = next(s for s in specs if s.gate == "e2e:erp-imobiliario")
    assert e2e_spec.argv == ["npx", "playwright", "test"]
    assert "@playwright/test" in {p.name for p in e2e_spec.preconditions}


def test_e2e_gate_absent_without_playwright_config(tmp_path):
    _make_product(tmp_path, "core", e2e=False)
    scope = GS._derive_scope(["products/core/frontend/src/App.tsx"])
    specs = GS._build_gate_specs(tmp_path, scope)
    assert not any(s.gate.startswith("e2e:") for s in specs)


def test_three_tuple_runner_still_supported(tmp_path):
    """Back-compat for every pre-existing injected seam."""
    _make_product(tmp_path, "core")
    git_runner = _clean_git_runner(diff_files="products/core/backend/app/main.py\n")
    result = GS.gate_sweep(
        repo_root=str(tmp_path), git_runner=git_runner, run_gate=lambda spec: (0, "ok", 0.1),
    )
    assert result["status"] == "green"


def test_verdict_precedence_table():
    def g(name, ran, code, **extra):
        return {"gate": name, "ran": ran, "exit_code": code, **extra}

    assert GS._verdict([g("a", True, 0)]) == "green"
    assert GS._verdict([g("a", True, 1)]) == "red"
    assert GS._verdict([g("a", False, None)]) == "incomplete"
    assert GS._verdict([g("a", False, None, harness_invalid=[{"precondition": "node_modules"}])]) == "inconclusive"
    assert GS._verdict([g("a", True, 1, harness_suspect={"signature": "x"})]) == "inconclusive"
    # a real red outranks a suspect one
    assert GS._verdict([
        g("a", True, 1, harness_suspect={"signature": "x"}),
        g("b", True, 1),
    ]) == "red"
    # nothing measurable at all is still not green
    assert GS._verdict([
        g("a", False, None, harness_invalid=[{"precondition": "node_modules"}]),
        g("b", True, 0),
    ]) == "inconclusive"
