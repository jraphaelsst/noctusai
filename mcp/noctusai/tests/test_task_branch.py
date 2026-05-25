"""Colocated tests for noctus.dev.task_branch.

Zero real git — `run` is injected (a FakeGit that scripts rev-parse / merge-base
/ log / worktree list|add|remove|prune / rebase / push / branch -d, and
simulates the FF push + the concurrent-push race + a rebase conflict). Covers
status / start / integrate (planned / up_to_date / integrated / retry-on-race /
conflict) / cleanup (planned / cleaned / blocked-unmerged + the salvage-before-
delete recovery-pointer leg recorded BEFORE the destructive remove), and the
load-bearing safety invariants:
  • the safe-git allowlist guard rejects an off-list subcommand;
  • the DEV-ONLY push boundary refuses a push whose dst is main/prod;
  • across a full start→integrate→cleanup the tool emits no banned token.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from tools.noctus.dev import task_branch as T  # noqa: E402


class FakeGit:
    """Scripts git IO. `refs` maps ref→sha. A push (when its scripted rc is 0)
    advances the dst ref to `head_sha` (the worktree HEAD), simulating the FF.
    `rebase_rcs` / `push_rcs` are consumed left-to-right (default → 0). `anc` is
    an ancestor predicate over shas. Records every (cmd, cwd)."""

    def __init__(self, refs, anc, logs=None, porcelain="", head_sha=None,
                 rebase_rcs=None, push_rcs=None, conflicts=None):
        self.refs = dict(refs)
        self.anc = anc
        self.logs = logs or {}
        self.porcelain = porcelain
        self.head_sha = head_sha
        self.rebase_rcs = list(rebase_rcs or [])
        self.push_rcs = list(push_rcs or [])
        self.conflicts = conflicts or []
        self.calls: list[tuple[list[str], str | None]] = []

    def __call__(self, cmd, cwd=None):
        self.calls.append((cmd, cwd))
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "fetch":
            return (0, "", "")
        if sub == "rev-parse":
            sha = self.refs.get(cmd[2])
            return (0, sha + "\n", "") if sha else (1, "", "bad ref")
        if sub == "merge-base":  # merge-base --is-ancestor a b
            return (0 if self.anc(cmd[3], cmd[4]) else 1, "", "")
        if sub == "log":         # log --oneline a..b
            return (0, self.logs.get(cmd[3], ""), "")
        if sub == "diff":        # diff --name-only [--diff-filter=U] a..b
            if "--diff-filter=U" in cmd:
                return (0, "\n".join(self.conflicts), "")
            return (0, "", "")
        if sub == "worktree":
            if cmd[2] == "list":
                return (0, self.porcelain, "")
            return (0, "", "")  # add / remove / prune
        if sub == "rebase":
            if "--abort" in cmd:
                return (0, "", "")
            rc = self.rebase_rcs.pop(0) if self.rebase_rcs else 0
            return (rc, "", "conflict" if rc else "")
        if sub == "push":
            rc = self.push_rcs.pop(0) if self.push_rcs else 0
            if rc == 0:
                dst = cmd[3].split(":refs/heads/")[1]
                self.refs["origin/" + dst] = self.head_sha or self.refs.get("origin/" + dst)
            return (rc, "", "non-fast-forward" if rc else "")
        if sub == "branch":      # branch -d <name>
            return (0, "", "")
        return (0, "", "")

    def subcmds(self):
        return [(c[1] if len(c) > 1 else "", c) for c, _cwd in self.calls]

    def pushes(self):
        return [c for c, _cwd in self.calls if len(c) > 1 and c[1] == "push"]

    def ran(self, *needles):
        flat = " ".join(" ".join(c) for c, _cwd in self.calls)
        return all(n in flat for n in needles)


def _anc_pairs(pairs):
    s = set(pairs)
    return lambda a, b: a == b or (a, b) in s


def _capture_recorder():
    """A fake salvage_recorder: captures (root, removed) and returns a ledger
    path WITHOUT real IO — so cleanup tests exercise the recovery-pointer leg
    deterministically (no settings import, no file write)."""
    captured: list[tuple] = []

    def rec(root, removed):
        captured.append((root, removed))
        return Path(root) / "project-history/worktree-salvage.ndjson"

    rec.captured = captured
    return rec


_PORCELAIN = (
    "worktree /repo\nHEAD m0\nbranch refs/heads/dev\n\n"
    "worktree /repo/.claude/worktrees/foo\nHEAD f0\nbranch refs/heads/feat/foo\n\n"
    "worktree /repo/.claude/worktrees/agent-xyz\nHEAD a0\nbranch refs/heads/worktree-agent-xyz\n"
)


# ── status ──
def test_status_lists_self_branch_worktrees_read_only():
    fake = FakeGit(
        refs={"origin/dev": "d0"},
        anc=_anc_pairs([]),
        logs={"d0..f0": "c1 x\nc2 y", "f0..d0": "z1 q"},
        porcelain=_PORCELAIN,
    )
    res = T.task_branch(action="status", run=fake)
    assert res["status"] == "status" and res["exit_code"] == 0
    # only the feat/* worktree under .claude/worktrees — NOT dev, NOT agent-* worktree
    assert len(res["active"]) == 1
    only = res["active"][0]
    assert only["slug"] == "foo" and only["branch"] == "feat/foo"
    assert only["ahead"] == 2 and only["behind"] == 1
    assert fake.pushes() == []  # never writes


# ── start ──
def test_start_dry_run_plans_without_creating():
    fake = FakeGit(refs={"origin/dev": "d0"}, anc=_anc_pairs([]))
    res = T.task_branch(action="start", slug="feat-x", confirm=False, run=fake)
    assert res["status"] == "planned" and res["exit_code"] == 0
    assert res["base_sha"] == "d0"
    assert not any(c[2] == "add" for c, _ in fake.calls if c[1] == "worktree" and len(c) > 2)


def test_start_confirm_forks_off_origin_dev():
    fake = FakeGit(refs={"origin/dev": "d0"}, anc=_anc_pairs([]))
    res = T.task_branch(action="start", slug="feat-x", confirm=True, run=fake)
    assert res["status"] == "started" and res["exit_code"] == 0
    assert fake.ran("worktree add .claude/worktrees/feat-x -b feat/feat-x origin/dev")


def test_start_requires_slug():
    fake = FakeGit(refs={"origin/dev": "d0"}, anc=_anc_pairs([]))
    res = T.task_branch(action="start", confirm=True, run=fake)
    assert res["status"] == "error" and "requires slug" in res["error"]


# ── integrate ──
def test_integrate_dry_run_plans_rebase_and_push():
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x\nc2 y", "b0..d0": "e1 z"},
    )
    res = T.task_branch(action="integrate", slug="x", confirm=False, run=fake)
    assert res["status"] == "planned" and res["exit_code"] == 0
    assert res["ahead"] == 2 and res["behind"] == 1
    assert fake.pushes() == []


def test_integrate_up_to_date():
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "d0"},
        anc=_anc_pairs([("d0", "d0")]),
        logs={"d0..d0": ""},
    )
    res = T.task_branch(action="integrate", slug="x", confirm=True, run=fake)
    assert res["status"] == "up_to_date"
    assert fake.pushes() == []


def test_integrate_confirm_pushes_to_dev_and_verifies():
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x", "b0..d0": ""},
        head_sha="b0",
    )
    res = T.task_branch(action="integrate", slug="x", confirm=True, run=fake)
    assert res["status"] == "integrated" and res["exit_code"] == 0
    assert res["attempts"] == 1 and res["verified"] is True
    pushes = fake.pushes()
    assert len(pushes) == 1
    assert pushes[0] == ["git", "push", "origin", "HEAD:refs/heads/dev"]


def test_integrate_retries_on_concurrent_push_race():
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x", "b0..d0": ""},
        head_sha="b0",
        push_rcs=[1, 0],  # first push rejected (peer beat us), second FFs
    )
    res = T.task_branch(action="integrate", slug="x", confirm=True, run=fake)
    assert res["status"] == "integrated" and res["attempts"] == 2
    assert len(fake.pushes()) == 2


def test_integrate_conflict_aborts_and_surfaces():
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x", "b0..d0": "e1 z"},
        head_sha="b0",
        rebase_rcs=[1],                       # rebase conflicts
        conflicts=["seed/lib/backend/x.py"],
    )
    res = T.task_branch(action="integrate", slug="x", confirm=True, run=fake)
    assert res["status"] == "conflict" and res["exit_code"] == 1
    assert res["conflicted_files"] == ["seed/lib/backend/x.py"]
    assert fake.pushes() == []               # never pushes a conflicted state
    assert fake.ran("rebase --abort")        # worktree restored clean


# ── cleanup ──
def test_cleanup_dry_run_plans():
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([("b0", "d0")]),       # branch merged into dev
    )
    res = T.task_branch(action="cleanup", slug="x", confirm=False, run=fake)
    assert res["status"] == "planned" and res["branch_merged"] is True
    # the salvage ritual is SURFACED in the plan (learn-before-delete) — dry-run
    # records nothing yet.
    assert set(res["cleanup_ritual"]) == {
        "1_extract_learnings", "2_record_recovery_pointer",
        "3_mole_sweep_before_delete", "4_remove"}
    assert "KB/memory" in res["learnings_checkpoint"]


def test_cleanup_confirm_removes_worktree_and_deletes_branch():
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([("b0", "d0")]),
    )
    rec = _capture_recorder()
    res = T.task_branch(action="cleanup", slug="x", confirm=True, run=fake,
                        primary_root="/repo", salvage_recorder=rec)
    assert res["status"] == "cleaned" and res["exit_code"] == 0
    assert fake.ran("worktree remove .claude/worktrees/x")
    assert fake.ran("worktree prune")
    assert fake.ran("branch -d feat/x")
    # MECHANICAL recovery-pointer leg fired (branch+SHA recorded to the ledger).
    assert res["salvage_ledger"].endswith("worktree-salvage.ndjson")
    assert len(rec.captured) == 1
    _root, removed = rec.captured[0]
    assert removed[0]["branch"] == "feat/x" and removed[0]["sha"] == "b0"


def test_cleanup_records_recovery_pointer_before_removing_the_worktree():
    """Leg 2 is recorded BEFORE the destructive `worktree remove` — so a
    remove failure can't lose the recovery pointer."""
    order: list[str] = []

    def rec(root, removed):
        order.append("salvage")
        return Path(root) / "project-history/worktree-salvage.ndjson"

    fake = FakeGit(refs={"origin/dev": "d0", "feat/x": "b0"},
                   anc=_anc_pairs([("b0", "d0")]))
    _orig = fake.__call__

    def spy(cmd, cwd=None):
        if len(cmd) > 1 and cmd[1] == "worktree" and cmd[2] == "remove":
            order.append("remove")
        return _orig(cmd, cwd)

    res = T.task_branch(action="cleanup", slug="x", confirm=True, run=spy,
                        primary_root="/repo", salvage_recorder=rec)
    assert res["status"] == "cleaned"
    assert order == ["salvage", "remove"]   # recovery pointer recorded first


def test_cleanup_resolves_actual_branch_for_reused_worktree_dir():
    """A reused/renamed worktree whose dir (`sw-waha-youtube`) ≠ feat/<slug>
    (`feat/salvage-before-delete`): cleanup must resolve the ACTUAL branch from the
    worktree list (keyed by dir) so the recovery-pointer leg records the real
    branch — not silently no-op on a nonexistent feat/<slug>, leaving the real
    branch dangling. The 2026-05-25 dogfood regression."""
    porcelain = (
        "worktree /repo\nHEAD m0\nbranch refs/heads/dev\n\n"
        "worktree /repo/.claude/worktrees/sw-waha-youtube\n"
        "HEAD b0\nbranch refs/heads/feat/salvage-before-delete\n"
    )
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/salvage-before-delete": "b0"},
        anc=_anc_pairs([("b0", "d0")]),
        porcelain=porcelain,
    )
    rec = _capture_recorder()
    res = T.task_branch(action="cleanup", slug="sw-waha-youtube", confirm=True,
                        run=fake, primary_root="/repo", salvage_recorder=rec)
    assert res["status"] == "cleaned"
    # the ACTUAL branch (not feat/sw-waha-youtube) was resolved, recorded + deleted
    assert res["branch"] == "feat/salvage-before-delete"
    assert fake.ran("branch -d feat/salvage-before-delete")
    _root, removed = rec.captured[0]
    assert removed[0]["branch"] == "feat/salvage-before-delete"
    assert removed[0]["sha"] == "b0"
    # the worktree dir (the stable key) is still removed by its path
    assert fake.ran("worktree remove .claude/worktrees/sw-waha-youtube")


def test_branch_for_path_keys_on_dir_not_slug():
    """Unit: _branch_for_path matches by dir path/basename, returns the real
    branch; None for a detached or absent worktree."""
    porcelain = (
        "worktree /repo/.claude/worktrees/sw-waha-youtube\n"
        "HEAD b0\nbranch refs/heads/feat/salvage-before-delete\n"
    )
    assert T._branch_for_path(porcelain, ".claude/worktrees/sw-waha-youtube") == \
        "feat/salvage-before-delete"
    assert T._branch_for_path(porcelain, ".claude/worktrees/absent") is None
    # detached HEAD (no branch line) → None
    assert T._branch_for_path("worktree /repo/.claude/worktrees/x\nHEAD b0\n",
                              ".claude/worktrees/x") is None


def test_cleanup_blocked_when_branch_unmerged():
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),                   # b0 NOT ancestor of d0 → unmerged
    )
    res = T.task_branch(action="cleanup", slug="x", confirm=True, run=fake)
    assert res["status"] == "blocked" and res["exit_code"] == 1
    assert "integrate first" in res["reason"]
    assert not fake.ran("worktree remove")


# ── safety invariants ──
def test_allowlist_guard_rejects_off_list_subcommand():
    with pytest.raises(ValueError):
        T._git(lambda *a, **k: (0, "", ""), "reset", "--hard")
    with pytest.raises(ValueError):
        T._git(lambda *a, **k: (0, "", ""), "stash")  # not on the allowlist


def test_banned_token_rejected():
    with pytest.raises(ValueError):
        T._git(lambda *a, **k: (0, "", ""), "push", "origin", "HEAD:refs/heads/dev", "--force")


def test_dev_only_push_boundary_refuses_main_and_prod():
    for bad in ("main", "prod"):
        with pytest.raises(ValueError):
            T._assert_push_targets_dev(("push", "origin", f"HEAD:refs/heads/{bad}"), "dev")
    # dev is allowed
    T._assert_push_targets_dev(("push", "origin", "HEAD:refs/heads/dev"), "dev")
    # and through _git
    with pytest.raises(ValueError):
        T._git(lambda *a, **k: (0, "", ""), "push", "origin", "HEAD:refs/heads/main")


def test_unknown_action_is_an_error_not_a_raise():
    res = T.task_branch(action="frobnicate", run=FakeGit(refs={}, anc=_anc_pairs([])))
    assert res["status"] == "error" and res["exit_code"] == 1


def test_full_lifecycle_emits_no_banned_token_and_only_dev_pushes():
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([("b0", "d0")]),
        logs={"d0..b0": "c1 x", "b0..d0": ""},
        head_sha="b0",
    )
    T.task_branch(action="start", slug="x", confirm=True, run=fake)
    T.task_branch(action="integrate", slug="x", confirm=True, run=fake)
    T.task_branch(action="cleanup", slug="x", confirm=True, run=fake,
                  primary_root="/repo", salvage_recorder=_capture_recorder())
    for cmd, _cwd in fake.calls:
        for tok in cmd:
            assert tok not in T._BANNED_TOKENS, f"banned token {tok!r} in {cmd}"
        if len(cmd) > 1 and cmd[1] == "push":
            dst = cmd[3].split(":refs/heads/")[1]
            assert dst == "dev", f"push to non-dev ref {dst!r}: {cmd}"


# ── env auto-wire (the §5a verification-env recipe) ──
def _seed_primary(primary, *, slugs=("alpha",), with_product_nm=True,
                  with_seed_nm=True):
    """Build a fixture PRIMARY tree under `primary` (a tmp Path): seed-frontend
    packages (+ their node_modules) and products/<slug>/frontend (+ node_modules).
    Returns nothing — just lays out dirs for FsOps (real os) to read."""
    for rel in ("seed/lib/frontend", "seed/framework/frontend"):
        (primary / rel).mkdir(parents=True, exist_ok=True)
        if with_seed_nm:
            (primary / rel / "node_modules").mkdir(exist_ok=True)
    for slug in slugs:
        fe = primary / "products" / slug / "frontend"
        fe.mkdir(parents=True, exist_ok=True)
        if with_product_nm:
            (fe / "node_modules").mkdir(exist_ok=True)


def _seed_worktree_tree(wt_root):
    """A fresh worktree mirrors the tracked tree (the seed pkgs exist) but has NO
    node_modules anywhere (gitignored ⇒ absent) — exactly the state wire_env fixes."""
    for rel in ("seed/lib/frontend", "seed/framework/frontend"):
        (wt_root / rel).mkdir(parents=True, exist_ok=True)


def test_plan_env_wiring_lists_expected_symlink_targets(tmp_path):
    primary = tmp_path / "primary"
    wt_root = primary / ".claude" / "worktrees" / "alpha"
    _seed_primary(primary, slugs=("alpha",))
    _seed_worktree_tree(wt_root)

    wire, skipped = T._plan_env_wiring(str(primary), str(wt_root), T.FsOps())
    links = {w["link"]: w for w in wire}

    # seed node_modules mirrored in (target = PRIMARY's node_modules)
    for rel in ("seed/lib/frontend", "seed/framework/frontend"):
        link = str(wt_root / rel / "node_modules")
        assert link in links and links[link]["kind"] == "node_modules"
        assert links[link]["target"] == str(primary / rel / "node_modules")

    # the product frontend node_modules + the two @noctusai re-points (to WORKTREE seed)
    pnm = wt_root / "products" / "alpha" / "frontend" / "node_modules"
    assert str(pnm) in links and links[str(pnm)]["kind"] == "node_modules"
    lib_link = str(pnm / "@noctusai" / "lib")
    seed_link = str(pnm / "@noctusai" / "seed")
    assert links[lib_link]["kind"] == "@noctusai"
    assert links[lib_link]["target"] == str(wt_root / "seed/lib/frontend")
    assert links[seed_link]["target"] == str(wt_root / "seed/framework/frontend")
    assert skipped == []


def test_plan_env_wiring_reports_missing_primary_node_modules(tmp_path):
    # primary seed dirs exist but their node_modules are ABSENT → reported, not crashed
    primary = tmp_path / "primary"
    wt_root = primary / ".claude" / "worktrees" / "beta"
    _seed_primary(primary, slugs=("beta",), with_seed_nm=False, with_product_nm=False)
    _seed_worktree_tree(wt_root)

    wire, skipped = T._plan_env_wiring(str(primary), str(wt_root), T.FsOps())
    # nothing to mirror (no primary node_modules anywhere) → all node_modules skipped;
    # the @noctusai re-points target the WORKTREE seed (which exists) so they still plan
    nm_skips = [s for s in skipped if "primary node_modules absent" in s["reason"]]
    assert len(nm_skips) == 3  # 2 seed pkgs + 1 product frontend
    assert all(w["kind"] == "@noctusai" for w in wire)


def test_start_wire_env_dry_run_reports_plan_without_creating(tmp_path):
    primary = tmp_path / "primary"
    wt_root = primary / ".claude" / "worktrees" / "feat-x"
    _seed_primary(primary, slugs=("alpha",))
    _seed_worktree_tree(wt_root)
    fake = FakeGit(refs={"origin/dev": "d0"}, anc=_anc_pairs([]))

    res = T.task_branch(action="start", slug="feat-x", confirm=False,
                        wire_env=True, primary_root=str(primary), run=fake)
    assert res["status"] == "planned" and res["wire_env"] is True
    would_links = {w["link"] for w in res["would_wire"]}
    assert str(wt_root / "seed/lib/frontend/node_modules") in would_links
    assert str(wt_root / "products/alpha/frontend/node_modules") in would_links
    # dry-run created NOTHING on disk
    assert not (wt_root / "seed/lib/frontend/node_modules").exists()
    assert not (wt_root / "products/alpha/frontend/node_modules").exists()


def test_start_wire_env_confirm_creates_symlinks(tmp_path):
    primary = tmp_path / "primary"
    wt_root = primary / ".claude" / "worktrees" / "feat-y"
    _seed_primary(primary, slugs=("alpha",))
    _seed_worktree_tree(wt_root)
    fake = FakeGit(refs={"origin/dev": "d0"}, anc=_anc_pairs([]))

    res = T.task_branch(action="start", slug="feat-y", confirm=True,
                        wire_env=True, primary_root=str(primary), run=fake)
    assert res["status"] == "started" and res["wire_env"] is True
    # symlinks now exist + point where the recipe says
    seed_nm = wt_root / "seed/lib/frontend/node_modules"
    assert seed_nm.is_symlink()
    assert os.path.realpath(seed_nm) == os.path.realpath(primary / "seed/lib/frontend/node_modules")
    lib_repoint = wt_root / "products/alpha/frontend/node_modules/@noctusai/lib"
    assert lib_repoint.is_symlink()
    # the @noctusai/lib re-point resolves to the WORKTREE seed (crux), not PRIMARY
    assert os.path.realpath(lib_repoint) == os.path.realpath(wt_root / "seed/lib/frontend")
    assert len(res["wired"]) >= 4


def test_start_wire_env_skips_real_node_modules_never_clobbers(tmp_path):
    # a REAL node_modules already present in the worktree must NOT be replaced/nested
    primary = tmp_path / "primary"
    wt_root = primary / ".claude" / "worktrees" / "feat-z"
    _seed_primary(primary, slugs=("alpha",))
    _seed_worktree_tree(wt_root)
    real_nm = wt_root / "seed/lib/frontend/node_modules"
    real_nm.mkdir(parents=True)
    sentinel = real_nm / "KEEP"
    sentinel.write_text("real")
    fake = FakeGit(refs={"origin/dev": "d0"}, anc=_anc_pairs([]))

    res = T.task_branch(action="start", slug="feat-z", confirm=True,
                        wire_env=True, primary_root=str(primary), run=fake)
    # untouched: still a real dir, sentinel intact, NOT a symlink
    assert real_nm.is_dir() and not real_nm.is_symlink()
    assert sentinel.read_text() == "real"
    reasons = " ".join(s["reason"] for s in res["skipped"])
    assert "real node_modules already present" in reasons


def test_start_without_wire_env_is_unchanged(tmp_path):
    # the default path stays exactly as before — no wire_env key, no plan
    fake = FakeGit(refs={"origin/dev": "d0"}, anc=_anc_pairs([]))
    res = T.task_branch(action="start", slug="feat-x", confirm=False, run=fake)
    assert res["status"] == "planned"
    assert "wire_env" not in res and "would_wire" not in res
