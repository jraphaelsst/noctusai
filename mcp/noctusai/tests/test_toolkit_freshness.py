"""Colocated tests for ``noctus.dev.toolkit_freshness`` — the stale-MCP-server
guard (2026-09-18 incident: ~30 hours of two-day-old ``task_branch.py`` code
silently answered every ``noctus.dev.*`` call because a long-lived Python
process never re-reads a module's file after import).

Design of the fixtures below: `stale_toolkit` / `fresh_toolkit` seed
``toolkit_freshness``'s module-level baseline with a REAL, disposable tmp
file (via `monkeypatch.setattr`, auto-reverted after each test — no
cross-test leakage), then genuinely change (or not) that file's bytes on
disk. `check()` / `warn_gate()` / `refuse_gate()` are never mocked — every
test below exercises their REAL stat-comparison logic against a controlled
tmp file, never the actual `mcp/noctusai` tree (no repo file is ever
touched). This is dependency-injection of the STATE those functions read
(the same seam this codebase already uses everywhere — `products_dir=
tmp_path`, `git_runner=FakeGitRunner(...)`), not a monkeypatch of the guard's
decision logic — the guard itself always runs for real.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import deploy_image as DI  # noqa: E402
from tools.noctus.dev import deploy_verify as DV  # noqa: E402
from tools.noctus.dev import migrate_product as MP  # noqa: E402
from tools.noctus.dev import predeploy_check as PC  # noqa: E402
from tools.noctus.dev import release as REL  # noqa: E402
from tools.noctus.dev import spa_smoke as SS  # noqa: E402
from tools.noctus.dev import task_branch as T  # noqa: E402
from tools.noctus.dev import toolkit_freshness as TF  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures — seed the module's baseline with a disposable tmp file
# ---------------------------------------------------------------------------


def _seed_baseline(tmp_path: Path, monkeypatch, name: str) -> Path:
    f = tmp_path / name
    f.write_text("# v1 — the bytes this process 'loaded'\n")
    st = f.stat()
    monkeypatch.setattr(TF, "_baseline", {str(f): (st.st_mtime, st.st_size)})
    monkeypatch.setattr(TF, "_loaded_at", time.time())
    monkeypatch.setattr(TF, "_cached_verdict", None)
    monkeypatch.setattr(TF, "_cached_at", 0.0)
    return f


@pytest.fixture
def stale_toolkit(tmp_path, monkeypatch):
    """Seeds a baseline, then REALLY changes the file on disk afterwards —
    every consumer of `check()` should see genuine drift."""
    f = _seed_baseline(tmp_path, monkeypatch, "loaded_module.py")
    f.write_text("# v2 — genuinely changed on disk AFTER the baseline\n")
    return f


@pytest.fixture
def fresh_toolkit(tmp_path, monkeypatch):
    """Seeds a baseline that matches the current on-disk state exactly —
    the positive control: nothing should report stale."""
    return _seed_baseline(tmp_path, monkeypatch, "loaded_module_fresh.py")


def _minimal_fake_git():
    """Answers every git subcommand task_branch's `status` action needs with
    a trivially-empty, zero-worktree tree — zero real git processes."""
    def run(cmd, cwd=None):
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "worktree":
            return (0, "", "")  # empty porcelain → no active self-branch worktrees
        return (0, "", "")
    return run


def _fake_git_with_refs(refs: dict[str, str]):
    """A slightly richer fake for `action='start'` dry-run: resolves the
    given ref names (e.g. `origin/dev`) via `rev-parse`, everything else
    answers empty/ok — zero real git processes."""
    calls: list[tuple] = []

    def run(cmd, cwd=None):
        calls.append((cmd, cwd))
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "rev-parse":
            sha = refs.get(cmd[-1])
            return (0, sha + "\n", "") if sha else (1, "", "bad ref")
        if sub == "worktree":
            return (0, "", "")
        return (0, "", "")

    run.calls = calls
    return run


SHELL = '<html><body><div id="root"></div><script src="/assets/index-abc.js"></script></body></html>'
BUNDLE = ("// app\n" + "x" * 20_000).encode()


def _spa_responder():
    mapping = {
        "/assets/index-abc.js": (200, BUNDLE, "application/javascript"),
        "/login": (200, b"<html></html>", "text/html"),
        "/": (200, SHELL.encode(), "text/html"),
    }

    def _fetch(url, timeout=25):
        for suffix, resp in mapping.items():
            if url.endswith(suffix):
                return resp
        return 404, b"", ""
    return _fetch


# ---------------------------------------------------------------------------
# Core mechanism
# ---------------------------------------------------------------------------


def test_fresh_when_baseline_matches_disk(fresh_toolkit):
    v = TF.check(bypass_cache=True)
    assert v["status"] == "fresh"
    assert v["changed_files"] == []
    assert v["deleted_files"] == []


def test_changed_file_is_detected(stale_toolkit):
    v = TF.check(bypass_cache=True)
    assert v["status"] == "stale"
    assert len(v["changed_files"]) == 1
    assert v["changed_files"][0]["path"] == str(stale_toolkit)
    assert v["deleted_files"] == []


def test_deleted_file_is_detected(fresh_toolkit):
    fresh_toolkit.unlink()
    v = TF.check(bypass_cache=True)
    assert v["status"] == "stale"
    assert v["deleted_files"] == [str(fresh_toolkit)]
    assert v["changed_files"] == []


def test_ttl_cache_does_not_mask_a_change_forever(tmp_path, monkeypatch):
    f = _seed_baseline(tmp_path, monkeypatch, "ttl_module.py")

    v0 = TF.check(ttl_seconds=0.2)
    assert v0["status"] == "fresh" and v0["from_cache"] is False

    # Genuinely change the file, but stay INSIDE the TTL window.
    f.write_text("# v2 — changed inside the TTL window\n")
    v1 = TF.check(ttl_seconds=0.2)
    assert v1["status"] == "fresh" and v1["from_cache"] is True, (
        "expected the TTL-cached (stale-in-the-good-sense) verdict to still "
        "mask the change inside the window"
    )

    # Cross the TTL boundary — a real stat pass must now see the change.
    time.sleep(0.25)
    v2 = TF.check(ttl_seconds=0.2)
    assert v2["status"] == "stale" and v2["from_cache"] is False, (
        "a change must be seen after the TTL elapses — the cache must not "
        "mask it indefinitely"
    )


def test_check_is_cheap_under_a_burst_of_calls():
    """The cheapness claim, measured: once the verdict is cached, a burst of
    calls (the '185 tools might all call this' scenario) costs microseconds
    each, not one stat pass each."""
    TF.capture_baseline(force=False)  # idempotent; real baseline either way
    first = TF.check(bypass_cache=True)
    assert "check_duration_ms" in first and first["check_duration_ms"] >= 0

    t0 = time.perf_counter()
    for _ in range(1000):
        TF.check(ttl_seconds=5.0)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 50, (
        f"1000 cached checks took {elapsed_ms:.2f}ms total — caching is not "
        "doing its job"
    )


# ---------------------------------------------------------------------------
# WARN posture: predeploy_check, deploy_verify, spa_smoke,
# task_branch action='status' / any confirm=False plan call
# ---------------------------------------------------------------------------


def test_predeploy_check_warns_and_still_answers_when_stale(stale_toolkit):
    r = PC.predeploy_check("")  # the empty-product fast, zero-IO error path
    assert r["status"] == "error"  # never refused — WARN posture still answers
    assert r["toolkit_stale"] is True
    assert any("toolkit_stale" in w for w in r["warnings"])


def test_deploy_verify_warns_and_still_answers_when_stale(stale_toolkit):
    r = DV.deploy_verify(run_local=lambda cmd: (1, "", "no real git in tests"))
    assert r["status"] == "error"  # can't resolve expected sha — zero real IO
    assert r["toolkit_stale"] is True
    assert any("toolkit_stale" in w for w in r["warnings"])


def test_spa_smoke_warns_and_still_answers_when_stale(stale_toolkit, monkeypatch):
    monkeypatch.setattr(SS, "_fetch", _spa_responder())
    r = SS.spa_smoke(products=["core"])
    assert r["toolkit_stale"] is True
    assert any("toolkit_stale" in w for w in r["warnings"])


def test_task_branch_status_action_warns_and_still_answers_when_stale(stale_toolkit):
    r = T.task_branch(action="status", run=_minimal_fake_git())
    assert r["status"] == "status"  # never refused — WARN posture still answers
    assert r["toolkit_stale"] is True
    assert any("toolkit_stale" in w for w in r["warnings"])


def test_task_branch_status_action_never_refused_even_with_confirm_true(stale_toolkit):
    """`action='status'` never inspects `confirm` — it must stay WARN-only
    regardless of what a caller passes for it."""
    r = T.task_branch(action="status", confirm=True, run=_minimal_fake_git())
    assert r["status"] != "refused_stale_toolkit"
    assert r["toolkit_stale"] is True


def test_task_branch_start_dry_run_is_only_warned_not_refused_when_stale(stale_toolkit):
    """confirm=False never provisions anything — WARN, never REFUSE."""
    fake = _fake_git_with_refs({"origin/dev": "d0"})
    r = T.task_branch(action="start", slug="feat-x", confirm=False, run=fake)
    assert r["status"] != "refused_stale_toolkit"
    assert r["toolkit_stale"] is True


def test_warn_posture_fresh_call_carries_no_warning(fresh_toolkit):
    """The verdict rides on every return, but a fresh toolkit never gets a
    manufactured warning — no silent-swallow in either direction."""
    r = PC.predeploy_check("")
    assert r["toolkit_stale"] is False
    assert "warnings" not in r


# ---------------------------------------------------------------------------
# REFUSE posture: migrate_product, release, deploy_image (confirm=True only),
# and task_branch's MUTATING actions (start/integrate/cleanup, confirm=True)
# ---------------------------------------------------------------------------


def test_migrate_product_refuses_the_write_when_stale(stale_toolkit):
    r = MP.migrate_product("definitely-not-a-real-product-xyz", confirm=True)
    assert r["status"] == "refused_stale_toolkit"
    assert r["exit_code"] == 1
    assert r["toolkit_stale"] is True
    assert any("toolkit_stale" in w for w in r["warnings"])
    assert "restart" in r["error"].lower() or "/mcp" in r["error"]


def test_migrate_product_dry_run_is_only_warned_not_refused_when_stale(stale_toolkit):
    """confirm=False never touches the database — WARN, never REFUSE."""
    r = MP.migrate_product(
        "definitely-not-a-real-product-xyz", confirm=False,
        live_products_fn=lambda: ["definitely-not-a-real-product-xyz"],
    )
    assert r["status"] != "refused_stale_toolkit"
    assert r["toolkit_stale"] is True


def test_migrate_product_allow_stale_toolkit_reaches_the_real_function(
    stale_toolkit, tmp_path,
):
    """The escape hatch must actually bypass the refusal (proceed into the
    real function body), not just relabel the refusal."""
    products_dir = tmp_path / "products"
    mig_dir = products_dir / "widgets" / "backend" / "migrations"
    mig_dir.mkdir(parents=True)
    (mig_dir / "001_seed.sql").write_text("CREATE SCHEMA IF NOT EXISTS widgets;")
    fake_executor = MP.FakeSqlExecutor()
    fake_git = MP.FakeGitRunner(
        responses={
            ("rev-parse", "--abbrev-ref", "HEAD"): "dev",
            ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/dev",
            ("rev-list", "--count", "HEAD..origin/dev"): "0",
            ("status", "--porcelain"): "",
        }
    )
    r = MP.migrate_product(
        "widgets", confirm=True, allow_stale_toolkit=True,
        executor=fake_executor, products_dir=products_dir,
        git_runner=fake_git, live_products_fn=lambda: ["widgets"],
    )
    assert r["status"] != "refused_stale_toolkit"
    # The real function ran for real: it actually applied the migration via
    # the injected fake executor (proof the wrapper truly proceeded).
    assert r["applied"] == ["001_seed.sql"]
    assert r["toolkit_stale"] is True
    assert r["allow_stale_toolkit"] is True


def test_release_refuses_the_write_when_stale(stale_toolkit):
    r = REL.release(stage="promote", confirm=True)
    assert r["status"] == "refused_stale_toolkit"
    assert r["exit_code"] == 1
    assert r["toolkit_stale"] is True
    assert any("toolkit_stale" in w for w in r["warnings"])


def test_deploy_image_refuses_the_write_when_stale(stale_toolkit):
    r = DI.deploy_image("erp-imobiliario", confirm=True)
    assert r["status"] == "refused_stale_toolkit"
    assert r["exit_code"] == 1
    assert r["toolkit_stale"] is True
    assert any("toolkit_stale" in w for w in r["warnings"])


# task_branch is the INCIDENT tool: "mutates prod" was never the real line —
# "can a stale version silently produce a plausible-looking wrong result?"
# is. A stale `action=start confirm=True` once returned status='started',
# exit 0, and a worktree that looked fine, while silently skipping the
# .env/node_modules provisioning. Zero fakes needed below — the refusal
# short-circuits before task_branch's body (and therefore any real git
# call) ever runs.
def test_task_branch_refuses_start_when_stale_and_confirmed(stale_toolkit):
    r = T.task_branch(action="start", slug="feat-x", confirm=True)
    assert r["status"] == "refused_stale_toolkit"
    assert r["exit_code"] == 1
    assert r["toolkit_stale"] is True
    assert any("toolkit_stale" in w for w in r["warnings"])


def test_task_branch_refuses_integrate_when_stale_and_confirmed(stale_toolkit):
    r = T.task_branch(action="integrate", slug="feat-x", confirm=True)
    assert r["status"] == "refused_stale_toolkit"
    assert r["exit_code"] == 1
    assert r["toolkit_stale"] is True


def test_task_branch_refuses_cleanup_when_stale_and_confirmed(stale_toolkit):
    r = T.task_branch(action="cleanup", slug="feat-x", confirm=True)
    assert r["status"] == "refused_stale_toolkit"
    assert r["exit_code"] == 1
    assert r["toolkit_stale"] is True


def test_task_branch_allow_stale_toolkit_reaches_the_real_function(stale_toolkit):
    """The escape hatch must actually bypass the refusal — proven here by
    the REAL function's own `requires slug` validation firing (it can only
    fire if task_branch's body actually ran)."""
    r = T.task_branch(action="start", confirm=True, allow_stale_toolkit=True,
                       run=_minimal_fake_git())
    assert r["status"] != "refused_stale_toolkit"
    assert r["status"] == "error" and "requires slug" in r["error"]


def test_refuse_posture_fresh_write_is_never_refused(fresh_toolkit):
    """Positive control: a fresh toolkit never manufactures a refusal."""
    r = REL.release(stage="promote", confirm=True)
    assert r["status"] != "refused_stale_toolkit"
    assert T.task_branch(action="start", slug="feat-x", confirm=True,
                          run=_fake_git_with_refs({"origin/dev": "d0"}))["status"] != "refused_stale_toolkit"
