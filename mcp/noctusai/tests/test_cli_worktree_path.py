"""Regression tests for the CLI `--worktree-path` / `--root` override.

Surfaced by Engineers AAA + BBB + ZZ during keeper-trio Wave 1: running
`python mcp/noctusai/cli.py --review --product <slug>` from inside a
`git worktree add` workspace would scan migrations from the canonical noc
clone instead of the worktree's products/ tree. Engineers worked around
via direct in-process `run_review(products_dir=...)` calls or symlinks.

`--worktree-path` first-classes the seam: the CLI rebinds module-level
`settings.REPO_ROOT` + `settings.PRODUCTS_DIR` BEFORE lazily importing any
`tools.*` module. Every downstream tool that does
`from settings import REPO_ROOT, PRODUCTS_DIR` picks up the override at
import time.

Per KB § PATTERNS/testing.md § Regression-test-the-detector + KB §
PATTERNS/project-execution.md § The methodology evolves rule.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


CLI_PATH = Path(__file__).resolve().parents[1] / "cli.py"
SEED_LIB_BACKEND = Path(__file__).resolve().parents[3] / "seed" / "lib" / "backend"


def _make_fake_worktree(tmp: Path) -> Path:
    """Build a minimal fake worktree at `tmp/wt`:

      tmp/wt/
        .noctusai-workspace        (marker — defensive, not required)
        products/
          fake_product/
            backend/migrations/001_init.sql  (a CREATE FUNCTION with no
                                              SET search_path — a flag the
                                              detector should report).
    """
    wt = tmp / "wt"
    (wt / "products" / "fake_product" / "backend" / "migrations").mkdir(parents=True)
    (wt / ".noctusai-workspace").write_text(
        "workspace_kind=primary\nworkspace_name=test-worktree\n",
    )
    (wt / "products" / "fake_product" / "backend" / "migrations" / "001_init.sql").write_text(
        "CREATE FUNCTION fake.f() RETURNS int LANGUAGE sql\n"
        "AS $$ SELECT 1; $$;\n"
    )
    return wt


def _run_cli(*args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    """Run `cli.py <args>` in a fresh subprocess so settings module state
    resets between cases."""
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(Path.home()),
        # PYTHONPATH so `noctusai_lib` resolves (seed/lib/backend) PLUS the
        # MCP package dir so `from settings import ...` works.
        "PYTHONPATH": f"{SEED_LIB_BACKEND}:{CLI_PATH.parent}",
    }
    if env_extra:
        env.update(env_extra)
    # Use the parent venv's python so noctusai_lib is on path.
    venv_py = Path(__file__).resolve().parents[4] / "venv" / "bin" / "python"
    interpreter = str(venv_py) if venv_py.exists() else sys.executable
    return subprocess.run(
        [interpreter, str(CLI_PATH), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_arg_help_advertises_worktree_path():
    """`--help` documents the new arg so engineers can discover it."""
    proc = _run_cli("--help")
    assert proc.returncode == 0, proc.stderr
    # Both the long form and the alias appear.
    assert "--worktree-path" in proc.stdout
    assert "--root" in proc.stdout


def test_nonexistent_worktree_path_exits_with_error():
    """A bad `--worktree-path` exits non-zero with a clear message."""
    proc = _run_cli("--worktree-path", "/nonexistent/path/xyz", "--validate")
    assert proc.returncode != 0
    assert "not a directory" in proc.stdout or "not a directory" in proc.stderr


def test_worktree_path_overrides_review_products_dir():
    """`--review --product fake_product --worktree-path <wt>` scopes the
    detector to the fake worktree's migrations.

    Without the override, the run would scan noc's actual products/ and
    NOT find `fake_product` (so reviewed_products would be empty AND no
    issues would surface for fake_product's migration). With the override,
    `fake_product` should appear in reviewed_products and the CREATE
    FUNCTION block should be flagged.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        wt = _make_fake_worktree(Path(tmpdir))
        proc = _run_cli(
            "--review",
            "--product", "fake_product",
            "--worktree-path", str(wt),
            "--json",
        )
        # The review subcommand prints a banner then JSON; we just need to
        # confirm the override fired (the "worktree override:" line) and
        # the fake_product was actually reviewed.
        combined = proc.stdout + proc.stderr
        assert "worktree override:" in combined, combined
        # The fake_product is reported as reviewed in the JSON dump.
        assert "fake_product" in combined, combined


def test_root_alias_is_accepted():
    """`--root` is a parser alias for `--worktree-path`."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wt = _make_fake_worktree(Path(tmpdir))
        proc = _run_cli(
            "--root", str(wt),
            "--review",
            "--product", "fake_product",
            "--json",
        )
        combined = proc.stdout + proc.stderr
        assert "worktree override:" in combined, combined


def test_default_behavior_unchanged_when_arg_absent():
    """Running `--help` without `--worktree-path` does NOT emit the
    worktree-override banner — the override is strictly opt-in.
    """
    proc = _run_cli("--help")
    assert "worktree override:" not in proc.stdout


# ---------------------------------------------------------------------------
# `--scan-wiring <product>` — the MCP-first tool+flag+test convention.
# The `noctus.dev.scan_wiring` MCP tool existed + was registered but had no
# `cli.py` flag (an engineer had to call the pure fn in a long session because
# the tool wasn't reachable). This wires the flag so it mirrors `--scan-*`.
# ---------------------------------------------------------------------------

def _make_wiring_worktree(tmp: Path) -> Path:
    """Build a fake worktree at `tmp/wt` with a product whose FE hits a route
    with NO backend match (the 404 / missing-route class — Leg A)."""
    wt = tmp / "wt"
    be = wt / "products" / "fake_product" / "backend" / "app"
    fe = wt / "products" / "fake_product" / "frontend" / "src" / "pages"
    be.mkdir(parents=True)
    fe.mkdir(parents=True)
    (be / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n"
    )
    (fe / "Page.tsx").write_text(
        "const x = await api.get('/api/does-not-exist');\n"
    )
    return wt


def test_arg_help_advertises_scan_wiring():
    """`--help` documents `--scan-wiring` so engineers can discover it."""
    proc = _run_cli("--help")
    assert proc.returncode == 0, proc.stderr
    assert "--scan-wiring" in proc.stdout


def test_scan_wiring_json_runs_against_worktree():
    """`--scan-wiring fake_product --worktree-path <wt> --json` scans the
    worktree's product tree and emits valid JSON for that product."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wt = _make_wiring_worktree(Path(tmpdir))
        proc = _run_cli(
            "--scan-wiring", "fake_product",
            "--worktree-path", str(wt),
            "--json",
        )
        combined = proc.stdout + proc.stderr
        assert "worktree override:" in combined, combined
        # The JSON dump is the last `{...}` block in stdout (after the banner).
        start = proc.stdout.index("{", proc.stdout.index('"ok"') - 200)
        payload = json.loads(proc.stdout[start:])
        assert payload["ok"] is True, payload
        assert payload["product"] == "fake_product"
        # The bogus FE call surfaces as a missing-route finding (Leg A).
        assert payload["totals"]["missing_routes"] >= 1, payload
        # Findings present ⇒ exit code 1 (clean would be 0).
        assert proc.returncode == 1, (proc.returncode, combined)


def test_scan_wiring_unknown_product_typed_error():
    """An unknown product slug returns the honest typed error (exit 2)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wt = _make_wiring_worktree(Path(tmpdir))
        proc = _run_cli(
            "--scan-wiring", "nope_not_here",
            "--worktree-path", str(wt),
            "--json",
        )
        payload = json.loads(proc.stdout[proc.stdout.index("{", proc.stdout.index('"ok"') - 200):])
        assert payload["ok"] is False
        assert "does not exist" in payload["error"]
        assert proc.returncode == 2, proc.returncode
