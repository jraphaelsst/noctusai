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

Per KB § PATTERNS/compliance/testing.md § Regression-test-the-detector + KB §
PATTERNS/architect/project-execution.md § The methodology evolves rule.
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
        # This env is built from scratch (conftest's pin does not reach it), and
        # the ledger store's default is the REAL store — git plumbing that
        # pushes to origin/ledgers. A test subprocess must never publish.
        "NOCTUS_LEDGER_STORE": "fake",
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
        # F2 + also-item (compliance review, 2026-09-24): cli.py now logs,
        # banners, AND the "worktree override:" line to stderr exclusively
        # — stdout carries ONLY the JSON dump, so the first `{` IS the
        # JSON's start (in practice, position 0), no banner/log-skipping
        # offset needed anymore.
        start = proc.stdout.index("{")
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
        # See F2 note above test_scan_wiring_json_runs_against_worktree —
        # stdout is log/banner-free now, so the first `{` is the JSON start.
        payload = json.loads(proc.stdout[proc.stdout.index("{"):])
        assert payload["ok"] is False
        assert "does not exist" in payload["error"]
        assert proc.returncode == 2, proc.returncode


# ---------------------------------------------------------------------------
# `--refresh-auto-improvement-cache --worktree-path <wt>` (2026-09-18): a
# SECOND instance of item 1's defect class. `auto_improvement.py`'s
# `LEDGER_PATH` is pinned to `settings.LEDGER_ROOT` (deliberately unwraps
# the worktree boundary back to the primary — ledger durability), which is
# NOT rebound by the CLI's generic `--worktree-path` -> `settings.REPO_ROOT`
# override (unlike `agent_context_cache`'s `AGENTS_DIR`). The CLI's own
# `--refresh-auto-improvement-cache` handler also dropped the parsed
# `args.worktree_path` on the floor instead of threading it into
# `ai.refresh(worktree_path=...)` — so the refresh ALWAYS cached the
# PRIMARY's ndjson sha regardless of `--worktree-path`, while
# `check_auto_improvement_cache_freshness(repo_root=<worktree>)` (correctly
# worktree-scoped) compared against the WORKTREE's own ndjson — a
# structurally unsatisfiable "STALE" verdict no matter how many times the
# suggested remedy re-ran. KB § PATTERNS/common/scoped-auto-improvement.md
# § cross-tree refresh/check parity.
# ---------------------------------------------------------------------------

def _make_auto_improvement_worktree(tmp: Path, ndjson_lines: list[str]) -> Path:
    """A fake worktree carrying its OWN `project-history/auto-improvement.ndjson`
    — deliberately DIFFERENT content than whatever the real primary checkout's
    copy holds, so a refresh that silently reads the primary instead of this
    worktree is caught by a content mismatch, not just a path check.

    `.git` is a real (if uninitialized) DIRECTORY here, not a worktree-stub
    `gitdir:` FILE — `cache_backend._git_common_dir` falls back to
    `<root>/.git` for a non-repo, and that fallback must be able to `mkdir`
    a `noctusai/cache/` subdirectory under it.
    """
    wt = tmp / "wt"
    (wt / ".git").mkdir(parents=True)
    (wt / ".noctusai-workspace").write_text(
        "workspace_kind=primary\nworkspace_name=test-worktree\n",
    )
    ph = wt / "project-history"
    ph.mkdir(parents=True)
    (ph / "auto-improvement.ndjson").write_text(
        "".join(line + "\n" for line in ndjson_lines), encoding="utf-8",
    )
    return wt


_ONE_LINE = '{"ts": "2026-09-18T00:00:00+00:00", "agent": "t", "scope": "scoped", "kind": "improvement", "target": "*", "description": "d1", "status": "s1-emergent", "source_ref": null}'
_TWO_LINES = [_ONE_LINE, _ONE_LINE.replace("d1", "d2")]


def test_refresh_auto_improvement_cache_reads_the_worktree_not_the_primary():
    """The core regression: refresh with `--worktree-path <wt>` must hash +
    cache THAT worktree's ndjson — not silently fall back to whatever
    `LEDGER_ROOT` resolves to (the primary checkout, real content unrelated
    to this test's fixture)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wt = _make_auto_improvement_worktree(Path(tmpdir), [_ONE_LINE])
        proc = _run_cli(
            "--refresh-auto-improvement-cache",
            "--worktree-path", str(wt),
        )
        combined = proc.stdout + proc.stderr
        assert proc.returncode == 0, combined
        assert "worktree override:" in combined, combined
        # Since 2026-09-24 a refresh is the DUAL-READ (this tree's dev copy ∪
        # the ledger store), so the absolute count also carries the store's
        # rows. What proves THIS worktree's file was read is the DELTA: one
        # more distinct row in the worktree ⇒ exactly one more cached row.
        n1 = _rebuilt_rows(combined)
        wt2 = _make_auto_improvement_worktree(Path(tmpdir) / "second", _TWO_LINES)
        proc2 = _run_cli("--refresh-auto-improvement-cache", "--worktree-path", str(wt2))
        n2 = _rebuilt_rows(proc2.stdout + proc2.stderr)
        assert n1 >= 1 and n2 == n1 + 1, (n1, n2, combined)


def _rebuilt_rows(out: str) -> int:
    import re
    m = re.search(r"rebuilt — (\d+) rows?", out)
    assert m, out
    return int(m.group(1))


def test_refresh_then_check_agree_on_the_same_worktree():
    """THE bug, end-to-end: refresh via the CLI's suggested remedy, then
    the freshness check against the SAME worktree must report fresh — not
    a structurally unsatisfiable STALE that no amount of re-running the
    remedy could ever clear."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wt = _make_auto_improvement_worktree(Path(tmpdir), _TWO_LINES)
        refresh_proc = _run_cli(
            "--refresh-auto-improvement-cache",
            "--worktree-path", str(wt),
        )
        assert refresh_proc.returncode == 0, refresh_proc.stdout + refresh_proc.stderr

        check_proc = _run_cli(
            "--check-auto-improvement-cache-freshness",
            "--worktree-path", str(wt),
        )
        combined = check_proc.stdout + check_proc.stderr
        assert check_proc.returncode == 0, (
            "freshness check reported STALE right after a scoped refresh of "
            f"the SAME worktree — the exact 'remedy doesn't work' bug: {combined}"
        )
        assert "fresh" in combined.lower(), combined

        # Repeating the refresh must not matter either way — regression
        # against a flake, not just a single lucky pass.
        for _ in range(2):
            _run_cli("--refresh-auto-improvement-cache", "--worktree-path", str(wt))
        check_proc2 = _run_cli(
            "--check-auto-improvement-cache-freshness", "--worktree-path", str(wt),
        )
        assert check_proc2.returncode == 0, check_proc2.stdout + check_proc2.stderr
