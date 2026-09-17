"""noctus.dev.mole — native-Python port parity + safe-gate.

Builds real temp filesystem / git trees and asserts the native
implementation's scan/dry-run/sweep classifications match the
`scripts/mole.sh` semantics it replaces. No subprocess-to-mole.sh; no
monkey-patching of our own logic.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import mole as mole_tool


# ───────────────────────── git temp-tree helper ────────────────────────
def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True
    ).stdout


def _init_repo(root: Path) -> None:
    # Engineer worktrees integrate to the `dev` integration branch, so the
    # classifier keys staleness off `origin/dev` (KB § branching-and-merging
    # § 0). Init on `dev` + provide a self-referential `origin/dev`.
    _git(root, "init", "-q", "-b", "dev")
    _git(root, "config", "user.email", "t@t.t")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")
    # Marker so resolve_caller_root accepts this as a valid caller root
    # (the same gate engineer worktrees satisfy in production).
    (root / ".noctusai-workspace").write_text("test\n")
    (root / "README.md").write_text("seed\n")
    # An EMPTY project-history/branch-tree.ndjson so `pointer_status_for_branch`'s
    # `git show origin/dev:project-history/branch-tree.ndjson` always succeeds
    # from this fake repo instead of falling back to the REAL production
    # ledger (`branch_pointer.LEDGER_PATH`, derived from the real
    # `settings.REPO_ROOT`) — a genuine test-isolation hazard.
    (root / "project-history").mkdir(parents=True)
    (root / "project-history" / "branch-tree.ndjson").write_text("")
    _git(root, "add", "README.md", "project-history/branch-tree.ndjson")
    _git(root, "commit", "-qm", "init")
    # A self-referential 'origin/dev' so merge-base checks resolve offline.
    _git(root, "remote", "add", "origin", str(root))
    _git(root, "fetch", "-q", "origin")


def _publish_pointer_row(root: Path, *, branch: str, status: str) -> None:
    """Append a branch-tree pointer row for `branch` and re-fetch the
    self-referential `origin` so `origin/dev` picks it up."""
    import json as _json

    ledger = root / "project-history" / "branch-tree.ndjson"
    row = _json.dumps({
        "branch": branch, "status": status,
        "ts": "2026-09-16T19:05:00+00:00",
    })
    with ledger.open("a") as fh:
        fh.write(row + "\n")
    _git(root, "add", "project-history/branch-tree.ndjson")
    _git(root, "commit", "-qm", f"pointer: {branch} {status}")
    _git(root, "fetch", "-q", "origin")


# ─────────────────────────── artifacts scope ───────────────────────────
def test_artifact_scope_matches_denylist_and_prune_rules(tmp_path):
    root = tmp_path
    _init_repo(root)
    # Matched: __pycache__ anywhere outside prune set.
    pc = root / "pkg" / "__pycache__"
    pc.mkdir(parents=True)
    (pc / "x.pyc").write_bytes(b"0" * 4096)
    # Matched: products/*/frontend/dist.
    dist = root / "products" / "p1" / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "bundle.js").write_bytes(b"0" * 4096)
    # PRUNED: .venv at depth-1, node_modules, .claude/worktrees pycache.
    venv_pc = root / "pkg" / ".venv" / "__pycache__"
    venv_pc.mkdir(parents=True)
    (venv_pc / "y.pyc").write_bytes(b"0" * 8192)
    nm_pc = root / "node_modules" / "__pycache__"
    nm_pc.mkdir(parents=True)
    (nm_pc / "z.pyc").write_bytes(b"0" * 8192)
    wt_pc = root / ".claude" / "worktrees" / "agent-x" / "__pycache__"
    wt_pc.mkdir(parents=True)
    (wt_pc / "w.pyc").write_bytes(b"0" * 8192)
    # NOT a frontend dir → dist outside products/*/frontend/ is NOT matched.
    stray_dist = root / "products" / "p1" / "backend" / "dist"
    stray_dist.mkdir(parents=True)
    (stray_dist / "s.js").write_bytes(b"0" * 4096)

    found = {p.relative_to(root) for p in mole_tool._iter_artifact_dirs(root)}
    assert Path("pkg/__pycache__") in found
    assert Path("products/p1/frontend/dist") in found
    assert Path("pkg/.venv/__pycache__") not in found
    assert Path("node_modules/__pycache__") not in found
    assert Path(".claude/worktrees/agent-x/__pycache__") not in found
    assert Path("products/p1/backend/dist") not in found


def test_scan_is_read_only_sweep_dry_run_deletes_nothing(tmp_path):
    root = tmp_path
    _init_repo(root)
    pc = root / "pkg" / "__pycache__"
    pc.mkdir(parents=True)
    (pc / "x.pyc").write_bytes(b"0" * 4096)

    out = mole_tool.run_mole(mode="scan", scope="artifacts", worktree_path=str(root))
    assert out["ok"] and out["mode"] == "scan"
    assert out["executed_destructive"] is False
    assert out["dry_run"] is False
    assert pc.exists(), "scan must never mutate the filesystem"

    out = mole_tool.run_mole(
        mode="sweep", scope="artifacts", force=False, worktree_path=str(root)
    )
    assert out["dry_run"] is True
    assert out["executed_destructive"] is False
    assert pc.exists(), "sweep without force must delete nothing"


def test_sweep_with_force_removes_artifacts(tmp_path):
    root = tmp_path
    _init_repo(root)
    pc = root / "pkg" / "__pycache__"
    pc.mkdir(parents=True)
    (pc / "x.pyc").write_bytes(b"0" * 4096)

    out = mole_tool.run_mole(
        mode="sweep", scope="artifacts", force=True, worktree_path=str(root)
    )
    assert out["executed_destructive"] is True
    assert out["dry_run"] is False
    assert not pc.exists(), "sweep --force removes regenerable artifacts"


# ───────────────────────── environments scope ──────────────────────────
def test_environments_is_advisory_and_never_swept(tmp_path):
    root = tmp_path
    _init_repo(root)
    venv = root / ".venv"
    venv.mkdir()
    (venv / "lib.bin").write_bytes(b"0" * 4096)

    out = mole_tool.run_mole(
        mode="sweep", scope="environments", force=True, worktree_path=str(root)
    )
    assert out["ok"]
    assert venv.exists(), "environments scope is NEVER swept even with force"
    assert "NEVER auto-swept" in out["stderr_tail"]


# ───────────────────── worktree classifier parity ──────────────────────
def test_worktree_classifier_categories(tmp_path):
    root = tmp_path
    _init_repo(root)
    wt_dir = root / ".claude" / "worktrees"
    wt_dir.mkdir(parents=True)

    # ORPHAN: on-disk agent-* dir, not git-registered.
    orphan = wt_dir / "agent-orphan"
    orphan.mkdir()
    (orphan / "f.txt").write_text("x")

    # STALE: registered worktree whose branch is merged to origin/dev
    # (created from dev, no new commits → ancestor of origin/dev). Publish a
    # terminal `shipped` pointer so it isn't incidentally POINTER_BLOCKED
    # (2026-09-17: unresolvable pointer now fails closed).
    stale = wt_dir / "agent-stale"
    _git(root, "worktree", "add", "-q", "-b", "merged-br", str(stale))
    _publish_pointer_row(root, branch="merged-br", status="shipped")

    # ACTIVE: registered worktree with an unmerged commit.
    active = wt_dir / "agent-active"
    _git(root, "worktree", "add", "-q", "-b", "wip-br", str(active))
    (active / "new.txt").write_text("wip")
    _git(active, "add", "new.txt")
    _git(active, "commit", "-qm", "wip")

    # STALE_DIRTY: merged branch but uncommitted file present.
    dirty = wt_dir / "agent-dirty"
    _git(root, "worktree", "add", "-q", "-b", "dirty-br", str(dirty))
    (dirty / "untracked.txt").write_text("dirty")

    # min_age_minutes=0 + recent_mtime_minutes=0: this test is about
    # CATEGORY parity, not the (separately tested) age/mtime guards — every
    # worktree here was just created in this test run.
    recs = mole_tool._classify_worktrees(
        root, min_age_minutes=0, recent_mtime_minutes=0,
    )
    by_path = {Path(p).name: cat for cat, p, _b, _r in recs}

    assert by_path.get("agent-orphan") == "ORPHAN"
    assert by_path.get("agent-stale") == "STALE"
    assert by_path.get("agent-active") == "ACTIVE"
    assert by_path.get("agent-dirty") == "STALE_DIRTY"


def test_scan_actionable_count_is_stale_orphan_phantom(tmp_path):
    root = tmp_path
    _init_repo(root)
    wt_dir = root / ".claude" / "worktrees"
    wt_dir.mkdir(parents=True)
    (wt_dir / "agent-orphan").mkdir()
    stale = wt_dir / "agent-stale"
    _git(root, "worktree", "add", "-q", "-b", "m-br", str(stale))
    _publish_pointer_row(root, branch="m-br", status="shipped")

    actionable, tally, _recs = mole_tool._scan_worktrees(
        root, min_age_minutes=0, recent_mtime_minutes=0,
    )
    assert tally["ORPHAN"] == 1 and tally["STALE"] == 1
    assert actionable == tally["STALE"] + tally["ORPHAN"] + tally["PHANTOM"]


def test_sweep_worktrees_force_removes_only_target_set(tmp_path):
    root = tmp_path
    _init_repo(root)
    wt_dir = root / ".claude" / "worktrees"
    wt_dir.mkdir(parents=True)

    orphan = wt_dir / "agent-orphan"
    orphan.mkdir()
    (orphan / "f.txt").write_text("x")
    stale = wt_dir / "agent-stale"
    _git(root, "worktree", "add", "-q", "-b", "m-br", str(stale))
    _publish_pointer_row(root, branch="m-br", status="shipped")
    dirty = wt_dir / "agent-dirty"
    _git(root, "worktree", "add", "-q", "-b", "d-br", str(dirty))
    (dirty / "u.txt").write_text("dirty")

    # Dry-run: nothing removed.
    out = mole_tool.run_mole(
        mode="sweep", scope="worktrees", force=False, worktree_path=str(root),
        recent_mtime_minutes=0,
    )
    assert out["dry_run"] is True
    assert orphan.exists() and stale.exists() and dirty.exists()

    # Force: STALE + ORPHAN gone, STALE_DIRTY preserved.
    # recent_mtime_minutes=0: isolates this test from the (separately
    # tested, never-force-bypassable) mtime guard — every worktree here
    # was just created in this test run.
    out = mole_tool.run_mole(
        mode="sweep", scope="worktrees", force=True, worktree_path=str(root),
        recent_mtime_minutes=0,
    )
    assert out["executed_destructive"] is True
    assert not orphan.exists(), "ORPHAN swept"
    assert not stale.exists(), "STALE swept"
    assert dirty.exists(), "STALE_DIRTY is NEVER auto-destroyed"


# ───────────────────── severity / next_action parity ───────────────────
def test_severity_grading_thresholds():
    assert mole_tool._grade_severity(0, 0) == "OK"
    assert mole_tool._grade_severity(2048, 0) == "WARNING"
    assert mole_tool._grade_severity(0, 15) == "WARNING"
    assert mole_tool._grade_severity(5120, 0) == "CRITICAL"
    assert mole_tool._grade_severity(0, 30) == "CRITICAL"


def test_next_action_priority_order():
    # next_action repointed to the canonical MCP surface (scripts/mole.sh
    # deleted — scripts-mcp-absorption 2026-05-18).
    assert "scope='worktrees', force=True" in mole_tool._next_action(0, 30, 0)
    assert "scope='artifacts', force=True" in mole_tool._next_action(5120, 0, 0)
    assert "scope='worktrees', force=True" in mole_tool._next_action(0, 15, 0)
    assert mole_tool._next_action(2048, 0, 0).endswith(
        "noctus.dev.mole(mode='sweep', scope='artifacts')"
    )
    assert "advisory" in mole_tool._next_action(0, 0, 3001)
    assert mole_tool._next_action(0, 0, 0) == "ok — nothing to do"


# ─────────────────────────── contract / shape ──────────────────────────
def test_result_shape_unchanged_keys(tmp_path):
    root = tmp_path
    _init_repo(root)
    out = mole_tool.run_mole(mode="scan", worktree_path=str(root))
    for key in (
        "ok", "mode", "scope", "executed_destructive", "dry_run",
        "exit_code", "severity", "artifacts_mb", "environments_mb",
        "worktrees_stale", "next_action", "safe_gate", "stderr_tail",
    ):
        assert key in out, f"result-shape key missing: {key}"
    assert "merged-to-dev" in out["safe_gate"]


def test_unresolvable_root_surfaces_error_never_silent(tmp_path):
    # Bare dir: no .noctusai-workspace marker / no .git → resolve_caller_root
    # rejects it. Must surface loudly (ok=False + error), never silently
    # fall back to noc main or proceed.
    out = mole_tool.run_mole(mode="scan", worktree_path=str(tmp_path))
    assert out["ok"] is False
    assert out["error"]
    assert out.get("executed") is False


def test_registers_under_dotted_name():
    captured = {}

    class _Srv:
        def tool(self, *, name, description):
            captured["name"] = name

            def deco(fn):
                return fn

            return deco

    mole_tool.register(_Srv())
    assert captured["name"] == "noctus.dev.mole"


# ═══════════ 2026-09-16 incident: shares the guards with cleanup_stale_worktrees ═══
# via _worktree_staleness — confirming BOTH callers actually got the fix, per
# the brief's explicit "fix it ONCE, confirm both callers get it" instruction.
def test_pointer_blocked_worktree_never_stale_even_with_force(tmp_path):
    root = tmp_path
    _init_repo(root)
    wt_dir = root / ".claude" / "worktrees"
    wt_dir.mkdir(parents=True)
    wt = wt_dir / "agent-live"
    _git(root, "worktree", "add", "-q", "-b", "feat/live", str(wt))
    _publish_pointer_row(root, branch="feat/live", status="on_going")

    recs = mole_tool._classify_worktrees(root, min_age_minutes=0)
    by_path = {Path(p).name: (cat, reason) for cat, p, _b, reason in recs}
    cat, reason = by_path["agent-live"]
    assert cat == "POINTER_BLOCKED"
    assert "on_going" in reason

    out = mole_tool.run_mole(
        mode="sweep", scope="worktrees", force=True, worktree_path=str(root),
        min_age_minutes=0,
    )
    assert wt.exists(), "force=True must NEVER sweep a live-pointer worktree"


def test_too_young_worktree_skipped_by_default_but_removable_with_force(tmp_path):
    root = tmp_path
    _init_repo(root)
    wt_dir = root / ".claude" / "worktrees"
    wt_dir.mkdir(parents=True)
    wt = wt_dir / "agent-fresh"
    _git(root, "worktree", "add", "-q", "-b", "feat/fresh", str(wt))
    _publish_pointer_row(root, branch="feat/fresh", status="shipped")

    # Default min_age_minutes, recent_mtime_minutes=0 to isolate the age
    # guard from the (separately tested) mtime guard — this worktree was
    # created microseconds ago.
    recs = mole_tool._classify_worktrees(root, recent_mtime_minutes=0)
    by_path = {Path(p).name: cat for cat, p, _b, _r in recs}
    assert by_path["agent-fresh"] == "TOO_YOUNG"

    out = mole_tool.run_mole(
        mode="sweep", scope="worktrees", force=True, worktree_path=str(root),
        recent_mtime_minutes=0,
    )
    assert not wt.exists(), "force=True MAY bypass the age guard"


def test_recently_active_worktree_skipped_even_with_force(tmp_path):
    root = tmp_path
    _init_repo(root)
    wt_dir = root / ".claude" / "worktrees"
    wt_dir.mkdir(parents=True)
    wt = wt_dir / "agent-recent"
    _git(root, "worktree", "add", "-q", "-b", "feat/recent", str(wt))
    _publish_pointer_row(root, branch="feat/recent", status="shipped")

    # Default recent_mtime_minutes — files just checked out are nowhere
    # near stale.
    recs = mole_tool._classify_worktrees(root, min_age_minutes=0)
    by_path = {Path(p).name: cat for cat, p, _b, _r in recs}
    assert by_path["agent-recent"] == "RECENTLY_ACTIVE"

    out = mole_tool.run_mole(
        mode="sweep", scope="worktrees", force=True, worktree_path=str(root),
        min_age_minutes=0,
    )
    assert wt.exists(), "force=True must NEVER sweep a recently-active worktree"


def test_unknown_pointer_blocks_removal_fail_closed(tmp_path):
    root = tmp_path
    _init_repo(root)
    wt_dir = root / ".claude" / "worktrees"
    wt_dir.mkdir(parents=True)
    wt = wt_dir / "agent-unknown"
    _git(root, "worktree", "add", "-q", "-b", "feat/unknown", str(wt))
    # No pointer published at all — the genuinely-unknown-liveness case.

    recs = mole_tool._classify_worktrees(
        root, min_age_minutes=0, recent_mtime_minutes=0,
    )
    by_path = {Path(p).name: (cat, reason) for cat, p, _b, reason in recs}
    cat, reason = by_path["agent-unknown"]
    assert cat == "POINTER_BLOCKED"
    assert "UNKNOWN" in reason or "unknown" in reason.lower()

    out = mole_tool.run_mole(
        mode="sweep", scope="worktrees", force=True, worktree_path=str(root),
        min_age_minutes=0, recent_mtime_minutes=0,
    )
    assert wt.exists(), (
        "force=True must NEVER sweep a worktree with unresolvable pointer "
        "liveness"
    )


def test_actual_incident_shape_terminal_pointer_plus_live_dir_plus_recent_mtime(
    tmp_path,
):
    """Reproduces the 2026-09-16→17 incident: a branch flipped to a TERMINAL
    pointer status while its worktree directory is still on disk and its
    files were touched moments ago — must be refused even with force=True."""
    root = tmp_path
    _init_repo(root)
    wt_dir = root / ".claude" / "worktrees"
    wt_dir.mkdir(parents=True)
    wt = wt_dir / "agent-incident"
    _git(root, "worktree", "add", "-q", "-b", "feat/incident", str(wt))
    _publish_pointer_row(root, branch="feat/incident", status="shipped")

    out = mole_tool.run_mole(
        mode="sweep", scope="worktrees", force=True, worktree_path=str(root),
    )
    assert wt.exists(), (
        "terminal pointer + live directory + recent mtime must be refused "
        "even with force=True — this is the exact incident shape"
    )


def test_scan_worktrees_tally_includes_the_new_categories(tmp_path):
    root = tmp_path
    _init_repo(root)
    wt_dir = root / ".claude" / "worktrees"
    wt_dir.mkdir(parents=True)
    live = wt_dir / "agent-live2"
    _git(root, "worktree", "add", "-q", "-b", "feat/live2", str(live))
    _publish_pointer_row(root, branch="feat/live2", status="deferred")
    fresh = wt_dir / "agent-fresh2"
    _git(root, "worktree", "add", "-q", "-b", "feat/fresh2", str(fresh))
    _publish_pointer_row(root, branch="feat/fresh2", status="shipped")

    # recent_mtime_minutes=0 isolates POINTER_BLOCKED/TOO_YOUNG tally
    # accounting from the (separately tested) mtime guard for "fresh2".
    _actionable, tally, _recs = mole_tool._scan_worktrees(
        root, recent_mtime_minutes=0,
    )
    assert tally["POINTER_BLOCKED"] == 1
    assert tally["TOO_YOUNG"] == 1

    # Default recent_mtime_minutes — the mtime guard runs BEFORE the age
    # guard, so a freshly-touched worktree tallies RECENTLY_ACTIVE (not
    # TOO_YOUNG) even though it would also qualify as too-young.
    recent = wt_dir / "agent-recent2"
    _git(root, "worktree", "add", "-q", "-b", "feat/recent2", str(recent))
    _publish_pointer_row(root, branch="feat/recent2", status="shipped")
    _actionable2, tally2, _recs2 = mole_tool._scan_worktrees(
        root, min_age_minutes=0,
    )
    assert tally2["RECENTLY_ACTIVE"] >= 1
