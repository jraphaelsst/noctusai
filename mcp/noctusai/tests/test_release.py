"""Colocated tests for noctus.dev.release.

Zero real git — `run` is injected (a FakeGit that scripts rev-parse / merge-base
/ log / diff / push and simulates the FF on push). Covers status / bless
(planned / up_to_date / blocked / blessed) / promote (planned / blocked / sha-
not-in-main / promoted), and the two load-bearing safety invariants:
  • the safe-git allowlist guard rejects an off-list subcommand;
  • across a CONFIRMED bless AND a CONFIRMED promote the tool emits no banned
    token, AND sets NOCTUS_ALLOW_MAIN_PUSH ONLY on the main/prod pushes — never
    on the prod-backup snapshot push.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import release as R  # noqa: E402


class FakeGit:
    """Scripts git IO. `refs` maps a ref string → sha; a push updates the dst
    ref (simulating the fast-forward). `anc` is an ancestor predicate over shas.
    Records every (cmd, env_extra) for invariant assertions."""

    def __init__(self, refs, anc, logs=None, diffs=None):
        self.refs = dict(refs)
        self.anc = anc
        self.logs = logs or {}
        self.diffs = diffs or {}
        self.calls: list[tuple[list[str], dict | None]] = []

    def __call__(self, cmd, env_extra=None):
        self.calls.append((cmd, env_extra))
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "fetch":
            return (0, "", "")
        if sub == "rev-parse":
            sha = self.refs.get(cmd[2])
            return (0, sha + "\n", "") if sha else (1, "", "bad ref")
        if sub == "merge-base":  # git merge-base --is-ancestor a b
            a, b = cmd[3], cmd[4]
            return (0 if self.anc(a, b) else 1, "", "")
        if sub == "log":         # git log --oneline a..b
            return (0, self.logs.get(cmd[3], ""), "")
        if sub == "diff":        # git diff --name-only a..b
            return (0, self.diffs.get(cmd[3], ""), "")
        if sub == "push":        # git push origin <sha>:refs/heads/<dst>
            src, dst = cmd[3].split(":refs/heads/")
            self.refs["origin/" + dst] = src
            return (0, "", "")
        return (0, "", "")

    def pushes(self):
        return [(c, e) for (c, e) in self.calls if len(c) > 1 and c[1] == "push"]

    def flat(self):
        return " ".join(" ".join(c) for c, _e in self.calls)


def _anc_pairs(pairs):
    s = set(pairs)
    return lambda a, b: a == b or (a, b) in s


# ── status ──
def test_status_is_read_only_and_reports_chain():
    fake = FakeGit(
        refs={"origin/dev": "d", "origin/main": "m", "origin/prod": "p",
              "origin/prod-backup": "p"},
        anc=_anc_pairs([("m", "d"), ("p", "m")]),
        logs={"m..d": "a1 x\na2 y", "p..m": "b1 z"},
    )
    res = R.release(stage="status", run=fake)
    assert res["status"] == "status" and res["exit_code"] == 0
    assert res["bless"]["ff"] is True and res["bless"]["ahead"] == 2
    assert res["promote"]["ff"] is True and res["promote"]["ahead"] == 1
    assert res["prod_backup_trails_prod"] is True
    assert fake.pushes() == []  # never writes


# ── bless ──
def test_bless_dry_run_plans_without_push():
    fake = FakeGit(
        refs={"origin/dev": "d", "origin/main": "m", "origin/prod": "p",
              "origin/prod-backup": "p"},
        anc=_anc_pairs([("m", "d")]),
        logs={"m..d": "a1 x\na2 y"},
    )
    res = R.release(stage="bless", confirm=False, run=fake)
    assert res["status"] == "planned" and res["exit_code"] == 0
    assert res["incoming_commits"] == ["a1 x", "a2 y"]
    assert fake.pushes() == []


def test_bless_up_to_date():
    fake = FakeGit(
        refs={"origin/dev": "d", "origin/main": "d", "origin/prod": "p",
              "origin/prod-backup": "p"},
        anc=_anc_pairs([]),
    )
    res = R.release(stage="bless", confirm=True, run=fake)
    assert res["status"] == "up_to_date"
    assert fake.pushes() == []


def test_bless_blocked_when_main_not_ancestor_of_dev():
    fake = FakeGit(
        refs={"origin/dev": "d", "origin/main": "m", "origin/prod": "p",
              "origin/prod-backup": "p"},
        anc=_anc_pairs([]),  # m NOT ancestor of d → non-FF
    )
    res = R.release(stage="bless", confirm=True, run=fake)
    assert res["status"] == "blocked" and res["exit_code"] == 1
    assert fake.pushes() == []


def test_bless_confirm_pushes_main_with_override_and_verifies():
    fake = FakeGit(
        refs={"origin/dev": "d", "origin/main": "m", "origin/prod": "p",
              "origin/prod-backup": "p"},
        anc=_anc_pairs([("m", "d")]),
        logs={"m..d": "a1 x"},
    )
    res = R.release(stage="bless", confirm=True, run=fake)
    assert res["status"] == "blessed" and res["verified"] is True
    pushes = fake.pushes()
    assert len(pushes) == 1
    cmd, env = pushes[0]
    assert cmd == ["git", "push", "origin", "d:refs/heads/main"]
    assert env == {"NOCTUS_ALLOW_MAIN_PUSH": "1"}


# ── promote ──
def test_promote_dry_run_plans_snapshot_and_promote():
    fake = FakeGit(
        refs={"origin/dev": "d", "origin/main": "m", "origin/prod": "p",
              "origin/prod-backup": "p"},
        anc=_anc_pairs([("p", "m"), ("p", "p")]),
        logs={"p..m": "c1 a\nc2 b"},
        diffs={"p..m": "products/core/backend/svc.py"},
    )
    res = R.release(stage="promote", confirm=False, run=fake)
    assert res["status"] == "planned" and res["exit_code"] == 0
    assert res["target_sha"] == "m"
    assert res["rebuild"]["needed"] is True and "core" in res["rebuild"]["products"]
    assert fake.pushes() == []


def test_promote_blocked_when_prod_not_ancestor_of_target():
    fake = FakeGit(
        refs={"origin/dev": "d", "origin/main": "m", "origin/prod": "p",
              "origin/prod-backup": "p"},
        anc=_anc_pairs([]),  # p NOT ancestor of m
    )
    res = R.release(stage="promote", confirm=True, run=fake)
    assert res["status"] == "blocked" and res["exit_code"] == 1
    assert fake.pushes() == []


def test_promote_rejects_sha_not_contained_in_main():
    fake = FakeGit(
        refs={"origin/dev": "d", "origin/main": "m", "origin/prod": "p",
              "origin/prod-backup": "p", "x": "x"},
        anc=_anc_pairs([("p", "m")]),  # x NOT ancestor of m
    )
    res = R.release(stage="promote", confirm=True, sha="x", run=fake)
    assert res["status"] == "blocked" and "not contained in main" in res["reason"]
    assert fake.pushes() == []


def test_promote_confirm_snapshots_then_promotes_with_correct_env():
    fake = FakeGit(
        refs={"origin/dev": "d", "origin/main": "m", "origin/prod": "p",
              "origin/prod-backup": "p"},
        anc=_anc_pairs([("p", "m"), ("p", "p")]),
        logs={"p..m": "c1 a"},
        diffs={"p..m": "docs/x.md"},  # non-runtime → no rebuild
    )
    res = R.release(stage="promote", confirm=True, run=fake)
    assert res["status"] == "promoted" and res["verified"] is True
    pushes = fake.pushes()
    assert len(pushes) == 2
    # 1) snapshot prod -> prod-backup, NO override env
    assert pushes[0][0] == ["git", "push", "origin", "p:refs/heads/prod-backup"]
    assert pushes[0][1] is None
    # 2) promote main sha -> prod, WITH override env
    assert pushes[1][0] == ["git", "push", "origin", "m:refs/heads/prod"]
    assert pushes[1][1] == {"NOCTUS_ALLOW_MAIN_PUSH": "1"}


# ── safety invariants ──
def test_allowlist_guard_rejects_off_list_subcommand():
    import pytest

    with pytest.raises(ValueError):
        R._git(lambda *a, **k: (0, "", ""), "reset", "--hard")
    with pytest.raises(ValueError):
        R._git(lambda *a, **k: (0, "", ""), "status")  # not on the allowlist


def test_no_banned_token_and_override_only_on_protected_pushes():
    # Run a confirmed bless then a confirmed promote; inspect every call.
    fake = FakeGit(
        refs={"origin/dev": "d", "origin/main": "m", "origin/prod": "p",
              "origin/prod-backup": "p"},
        anc=_anc_pairs([("m", "d"), ("p", "m"), ("p", "d"), ("p", "p")]),
        logs={"m..d": "a1 x", "p..d": "c1 a", "p..m": "c1 a"},
        diffs={"p..d": "docs/x.md", "p..m": "docs/x.md"},
    )
    R.release(stage="bless", confirm=True, run=fake)
    R.release(stage="promote", confirm=True, run=fake)
    for cmd, env in fake.calls:
        for tok in cmd:
            assert tok not in R._BANNED_TOKENS, f"banned token {tok!r} in {cmd}"
        if len(cmd) > 1 and cmd[1] == "push":
            dst = cmd[3].split(":refs/heads/")[1]
            if dst in {"main", "prod"}:
                assert env == {"NOCTUS_ALLOW_MAIN_PUSH": "1"}, f"missing override on {cmd}"
            else:  # prod-backup snapshot
                assert env is None, f"override leaked onto non-protected push {cmd}"
