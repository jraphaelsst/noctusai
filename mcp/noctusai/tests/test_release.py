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

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import release as R  # noqa: E402


_GREEN = [{"status": "completed", "conclusion": "success", "url": "https://ci/green"}]
_RED = [{"status": "completed", "conclusion": "failure", "url": "https://ci/red"}]


class FakeGit:
    """Scripts git IO. `refs` maps a ref string → sha; a push updates the dst
    ref (simulating the fast-forward). `anc` is an ancestor predicate over
    shas. `rev_list` maps `"a..b"` → an explicit newest-first sha list for
    `git rev-list a..b` (R1's bless walk); when a range is absent, defaults
    to `[refs["origin/<dev_branch>"]]` — i.e. "dev is exactly one commit
    ahead of main", which keeps every pre-R1 single-commit bless test
    working unchanged. `ci_by_sha` maps an exact sha → its own `gh run list`
    payload (falls back to the shared `ci`/`ci_rc` when absent) — needed for
    the multi-commit qualifying-green-walk tests where different candidates
    carry different verdicts. Records every (cmd, env_extra) for invariant
    assertions."""

    def __init__(self, refs, anc, logs=None, diffs=None, ci=_GREEN, ci_rc=0,
                rev_list=None, ci_by_sha=None, jobs_by_run_id=None,
                assume_since_fix=True):
        self.refs = dict(refs)
        self._anc = anc
        self.logs = logs or {}
        self.diffs = diffs or {}
        # `gh run list --json` payload for the bless CI precondition. Default
        # green so the pre-existing bless cases keep testing what they test.
        self.ci = ci
        self.ci_rc = ci_rc
        self.rev_list = rev_list or {}
        self.ci_by_sha = ci_by_sha or {}
        self.jobs_by_run_id = jobs_by_run_id or {}
        self.assume_since_fix = assume_since_fix
        self.calls: list[tuple[list[str], dict | None]] = []

    def anc(self, a, b):
        # R1 test default: every candidate is treated as descending from the
        # verified-base-fix landmark (the realistic 2026-09-24-onward case),
        # so the qualifying-green walk needs no extra `gh run view` call
        # unless a test sets `assume_since_fix=False` to exercise the OTHER
        # two qualifying legs (workflow_dispatch / heavy-job-check) deliberately.
        if self.assume_since_fix and a == R._VERIFIED_BASE_FIX_SHA:
            return True
        return self._anc(a, b)

    def __call__(self, cmd, env_extra=None):
        self.calls.append((cmd, env_extra))
        if cmd[0] == "gh":
            if self.ci_rc != 0:
                return (self.ci_rc, "", "gh: not authenticated")
            if cmd[1:3] == ["run", "view"]:
                run_id = cmd[3]
                return (0, json.dumps({"jobs": self.jobs_by_run_id.get(run_id, [])}), "")
            if "--commit" in cmd:
                sha = cmd[cmd.index("--commit") + 1]
                return (0, json.dumps(self.ci_by_sha.get(sha, self.ci)), "")
            return (0, json.dumps(self.ci), "")
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "fetch":
            return (0, "", "")
        if sub == "rev-parse":
            sha = self.refs.get(cmd[2])
            return (0, sha + "\n", "") if sha else (1, "", "bad ref")
        if sub == "merge-base":  # git merge-base --is-ancestor a b
            a, b = cmd[3], cmd[4]
            return (0 if self.anc(a, b) else 1, "", "")
        # `rev-list <a>..<b>` (exactly 2 args, R1's bless walk) is modeled
        # precisely; any OTHER rev-list shape (e.g. `--no-merges <a>..<b>`
        # from the rider manifest's `reachable_no_merges`) deliberately falls
        # through to the generic empty-success catch-all below, unaffected —
        # same as every subcommand this fake doesn't otherwise recognize.
        if sub == "rev-list" and len(cmd) == 3 and ".." in cmd[2]:
            key = cmd[2]
            if key in self.rev_list:
                return (0, "\n".join(self.rev_list[key]), "")
            a, b = key.split("..")
            dev_sha = self.refs.get("origin/dev")
            return (0, dev_sha if dev_sha and b in ("d", dev_sha) else "", "")
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


def test_bless_refuses_sha_loudly_instead_of_silently_ignoring_it():
    # PROD-PIN defect 2: stage='bless' used to silently plan/push the dev tip
    # even when sha= was passed, misleading the caller into believing their
    # pin took effect. It must now REFUSE — never a silent no-op.
    fake = FakeGit(
        refs={"origin/dev": "d", "origin/main": "m", "origin/prod": "p",
              "origin/prod-backup": "p"},
        anc=_anc_pairs([("m", "d")]),
        logs={"m..d": "a1 x\na2 y"},
    )
    res = R.release(stage="bless", confirm=True, sha="2f35bb74", run=fake)
    assert res["status"] == "error" and res["exit_code"] == 1
    assert "sha=" in res["error"] and "bless" in res["error"]
    assert fake.pushes() == []  # nothing moved — no silent partial-bless


def test_bless_refuses_sha_even_on_dry_run():
    # The refusal fires before the confirm-gate too — dry-run must not report
    # a misleading "planned" pin either.
    fake = FakeGit(
        refs={"origin/dev": "d", "origin/main": "m", "origin/prod": "p",
              "origin/prod-backup": "p"},
        anc=_anc_pairs([("m", "d")]),
        logs={"m..d": "a1 x"},
    )
    res = R.release(stage="bless", confirm=False, sha="2f35bb74", run=fake)
    assert res["status"] == "error" and res["exit_code"] == 1
    assert fake.pushes() == []


def test_bless_without_sha_still_works_unaffected():
    # Regression guard: the common no-sha bless path is untouched by the fix.
    fake = FakeGit(
        refs={"origin/dev": "d", "origin/main": "m", "origin/prod": "p",
              "origin/prod-backup": "p"},
        anc=_anc_pairs([("m", "d")]),
        logs={"m..d": "a1 x"},
    )
    res = R.release(stage="bless", confirm=True, sha=None, run=fake)
    assert res["status"] == "blessed"


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


# ── the CI-green bless precondition (2026-08-22) ──
# Doctrine said "CI green is MANDATORY before bless" and nothing checked it, so
# `1c83232f` reached BOTH main and prod carrying a red `Tests & Build`. These
# pin the mechanism, not the sentence.
def _ci_case(ci=_GREEN, ci_rc=0, diffs=None):
    return FakeGit(
        refs={"origin/dev": "d", "origin/main": "m", "origin/prod": "p",
              "origin/prod-backup": "p"},
        anc=_anc_pairs([("m", "d"), ("p", "m")]),
        logs={"m..d": "a1 x"},
        diffs=diffs or {"m..d": "products/x/backend/app/main.py"},
        ci=ci, ci_rc=ci_rc,
    )


def test_bless_is_blocked_when_ci_is_red_on_the_dev_tip():
    fake = _ci_case(ci=_RED)
    out = R.release(stage="bless", confirm=True, run=fake)
    assert out["status"] == "blocked"
    assert out["ci"]["verdict"] == "red"
    assert fake.pushes() == [], "a red CI must never reach the push"


def test_bless_is_blocked_when_ci_is_still_running():
    out = R.release(stage="bless", confirm=True,
                    run=_ci_case(ci=[{"status": "in_progress", "conclusion": None}]))
    assert out["status"] == "blocked" and out["ci"]["verdict"] == "pending"


def test_bless_is_blocked_when_no_run_exists_for_the_sha():
    out = R.release(stage="bless", confirm=True, run=_ci_case(ci=[]))
    assert out["status"] == "blocked" and out["ci"]["verdict"] == "missing"


def test_a_cancelled_run_carries_no_verdict_and_does_not_pass():
    out = R.release(stage="bless", confirm=True,
                    run=_ci_case(ci=[{"status": "completed", "conclusion": "cancelled"}]))
    assert out["status"] == "blocked" and out["ci"]["verdict"] == "missing"


def test_unreachable_ci_refuses_rather_than_defaulting_to_pass():
    """REFUSE-NOT-NULL: "I could not find out" is not "it passed"."""
    out = R.release(stage="bless", confirm=True, run=_ci_case(ci_rc=1))
    assert out["status"] == "blocked" and out["ci"]["verdict"] == "unavailable"


def test_a_docs_only_diff_is_the_one_sanctioned_exception():
    fake = _ci_case(ci=_RED, diffs={"m..d": "KNOWLEDGE-BASE/x.md\nproject-history/y.ndjson"})
    out = R.release(stage="bless", confirm=True, run=fake)
    assert out["status"] == "blessed", out
    assert "docs-only" in out["ci_exception"]


def test_one_executable_path_revokes_the_docs_only_exception():
    fake = _ci_case(ci=_RED, diffs={"m..d": "KNOWLEDGE-BASE/x.md\nmcp/noctusai/cli.py"})
    assert R.release(stage="bless", confirm=True, run=fake)["status"] == "blocked"


def test_green_ci_blesses_and_records_the_evidence():
    fake = _ci_case()
    out = R.release(stage="bless", confirm=True, run=fake)
    assert out["status"] == "blessed"
    assert out["ci"] == {"qualifies": True, "verdict": "green", "workflow": R._CI_WORKFLOW,
                         "conclusion": "success", "url": "https://ci/green",
                         "qualifying_reason": "since_verified_base_fix"}
    assert out["blessed_sha"] == "d" and out["dev_tip"] == "d"
    assert out["skipped_tail"] == {"count": 0, "commits": [], "projects": [], "migrations": []}


def test_status_surfaces_the_same_ci_verdict_read_only():
    fake = _ci_case(ci=_RED)
    out = R.release(stage="status", run=fake)
    assert out["bless"]["ci"]["verdict"] == "red"
    assert out["bless"]["qualifying_found"] is False
    assert fake.pushes() == []


def test_status_surfaces_the_qualifying_target_not_just_the_exact_tip_verdict():
    """F7 (compliance review, 2026-09-24): the tip's OWN verdict can be red
    while bless would still succeed against an older qualifying-green
    ancestor — `status` must show the REAL target, never just the
    exact-tip verdict a caller could mistake for the whole answer."""
    fake = _walk_case(["d2", "d1", "d0"], ci_by_sha={"d0": _GREEN})
    out = R.release(stage="status", run=fake)
    assert out["bless"]["ff"] is True
    assert out["bless"]["qualifying_found"] is True
    assert out["bless"]["qualifying_target"] == "d0"
    assert out["bless"]["qualifying_checked"] == 2  # d2, d1 walked past


def test_the_ci_probe_is_read_only_and_pinned_to_the_exact_sha():
    fake = _ci_case()
    R.release(stage="bless", confirm=True, run=fake)
    gh = [c for c, _e in fake.calls if c[0] == "gh"]
    assert len(gh) == 1, gh
    assert gh[0][:3] == ["gh", "run", "list"], "read-only subcommand only"
    assert "--commit" in gh[0] and gh[0][gh[0].index("--commit") + 1] == "d"


def test_read_ledger_dual_reads_origin_ledgers_and_dev():
    """2026-09-24: consent + pointer rows live on origin/ledgers; dev's legacy
    copy still counts (stale-code peers), exact duplicates collapse."""
    from tools.noctus.dev import release as R
    a, b = '{"project":"p","n":1}', '{"project":"p","n":2}'
    shows = {"origin/dev:project-history/ship-consent.ndjson": a + "\n",
             "origin/ledgers:ship-consent.ndjson": a + "\n" + b + "\n"}

    def git(*args):
        if args[0] == "show" and args[1] in shows:
            return 0, shows[args[1]], ""
        return 128, "", "fatal: not found"

    rows = R._read_ledger(git, "origin", "dev", "project-history/ship-consent.ndjson")
    assert [r["n"] for r in rows] == [1, 2]
    del shows["origin/dev:project-history/ship-consent.ndjson"]
    assert [r["n"] for r in R._read_ledger(git, "origin", "dev",
                                            "project-history/ship-consent.ndjson")] == [1, 2]
    shows.clear()
    assert R._read_ledger(git, "origin", "dev", "project-history/ship-consent.ndjson") == []


# ── R1 (2026-09-24): bless the newest QUALIFYING green descendant ──────────
# The dev-freeze fix. A rapid bookkeeping train (branch-pointer/salvage/
# ledger commits) sat at the dev tip with no CI run at all; the OLD bless
# froze on that (exact-tip-only). New bless walks back to the newest commit
# that actually IS verified and ships that, leaving the tail on dev.

def _walk_case(rev_list_shas, ci_by_sha, logs=None, jobs_by_run_id=None, main_anc_all=True):
    """`rev_list_shas`: newest-first main..dev candidates. Every candidate is
    treated as a descendant of main (`main_anc_all`) unless the test overrides
    `anc` itself afterwards."""
    anc = _anc_pairs([("m", s) for s in rev_list_shas]) if main_anc_all else _anc_pairs([])
    return FakeGit(
        refs={"origin/dev": rev_list_shas[0], "origin/main": "m", "origin/prod": "p",
              "origin/prod-backup": "p"},
        anc=anc,
        rev_list={f"m..{rev_list_shas[0]}": rev_list_shas},
        ci_by_sha=ci_by_sha,
        ci=[],  # default: no run at all for any sha not in ci_by_sha
        logs=logs or {},
        jobs_by_run_id=jobs_by_run_id or {},
    )


def test_bless_walks_past_a_ledger_only_tail_with_no_ci_run_to_the_last_qualifying_green():
    fake = _walk_case(["d2", "d1", "d0"], ci_by_sha={"d0": _GREEN},
                      logs={"m..d0": "c0 real work"})
    out = R.release(stage="bless", confirm=True, run=fake)
    assert out["status"] == "blessed", out
    assert out["blessed_sha"] == "d0"
    assert out["dev_tip"] == "d2"
    assert out["skipped_tail"]["count"] == 2
    assert out["skipped_tail"]["commits"] == ["d2", "d1"]
    assert out["skipped_tail"]["migrations"] == []
    # main → d0 (NOT the dev tip d2) is what actually got pushed.
    push_cmd, push_env = fake.pushes()[0]
    assert push_cmd == ["git", "push", "origin", "d0:refs/heads/main"]
    assert push_env == {"NOCTUS_ALLOW_MAIN_PUSH": "1"}


# ── F4/F6 (compliance review, 2026-09-24) ───────────────────────────────────
def test_bless_skipped_tail_lists_migrations_left_unverified_and_names_the_sha_hint():
    """F4: migration files touched in the SKIPPED range (blessed_sha..dev)
    surface in `skipped_tail.migrations`, and the bless message points the
    caller at `migrate_product sha=<blessed_sha>` (R3) to apply exactly what
    got blessed — never a bare migrate_product against the working tree,
    which would also pick up these unverified migrations."""
    fake = _walk_case(["d2", "d1", "d0"], ci_by_sha={"d0": _GREEN},
                      logs={"m..d0": "c0 real work"})
    fake.diffs["d0..d2"] = (
        "products/social-wiring/backend/migrations/099_x.sql\n"
        "products/core/frontend/src/App.tsx\n"
    )
    out = R.release(stage="bless", confirm=True, run=fake)
    assert out["status"] == "blessed", out
    assert out["skipped_tail"]["migrations"] == [
        "products/social-wiring/backend/migrations/099_x.sql",
    ]
    assert "migrate_product sha='d0'" in out["message"]
    assert "unverified migration" in out["message"]


def test_bless_docs_only_path_has_empty_skipped_tail_even_after_a_failed_walk():
    """F6: the docs-only exception blesses the dev TIP directly — nothing is
    actually left behind, so `skipped_tail` must be fully empty (never the
    non-qualifying candidates the FAILED qualifying-green walk collected on
    its way to concluding 'nothing qualifies, but the diff is docs-only')."""
    fake = _walk_case(["d2", "d1"], ci_by_sha={}, logs={"m..d2": "a1 x\na2 y"})
    fake.diffs["m..d2"] = "KNOWLEDGE-BASE/x.md\nproject-history/y.ndjson"
    out = R.release(stage="bless", confirm=True, run=fake)
    assert out["status"] == "blessed", out
    assert out["blessed_sha"] == "d2" == out["dev_tip"]
    assert out["skipped_tail"] == {"count": 0, "commits": [], "projects": [], "migrations": []}


def test_bless_walks_past_a_pending_code_tail_to_the_last_qualifying_green():
    """The tail commit isn't a bookkeeping ledger entry — it's real code
    whose CI simply hasn't reported yet. The walk is agnostic to WHY a
    candidate isn't qualifying; it just keeps looking."""
    fake = _walk_case(
        ["d2", "d1", "d0"],
        ci_by_sha={"d2": [{"status": "in_progress", "conclusion": None}], "d0": _GREEN},
        logs={"m..d0": "c0 real work"},
    )
    out = R.release(stage="bless", confirm=True, run=fake)
    assert out["status"] == "blessed"
    assert out["blessed_sha"] == "d0"
    assert out["skipped_tail"]["count"] == 2


def test_bless_refuses_when_no_descendant_of_main_has_a_qualifying_green():
    fake = _walk_case(["d2", "d1"], ci_by_sha={}, logs={})  # nothing green anywhere
    out = R.release(stage="bless", confirm=True, run=fake)
    assert out["status"] == "blocked" and out["exit_code"] == 1
    assert out["checked"] == 2
    assert len(out["skipped_tail"]) == 2
    assert fake.pushes() == []


def test_bless_never_ffs_a_green_run_that_is_not_a_descendant_of_main():
    """`d0` carries a green run but sits on the far side of a merge — it is
    IN `main..dev` (rev-list) yet NOT itself a descendant of main, so an FF
    straight to it would not actually work. `d1` (the dev tip, and a genuine
    descendant of main — satisfying the top-level `ff` gate) has no run of
    its own. Neither qualifies: the walk must never silently pick `d0`."""
    fake = FakeGit(
        refs={"origin/dev": "d1", "origin/main": "m", "origin/prod": "p",
              "origin/prod-backup": "p"},
        anc=_anc_pairs([("m", "d1")]),  # d1 IS a descendant of main; d0 is NOT
        rev_list={"m..d1": ["d1", "d0"]},
        ci_by_sha={"d0": _GREEN},  # d1 has no run at all (default ci=[])
        ci=[],
        logs={},
    )
    out = R.release(stage="bless", confirm=True, run=fake)
    assert out["status"] == "blocked" and out["exit_code"] == 1
    by_sha = {e["sha"]: e for e in out["skipped_tail"]}
    assert by_sha["d0"]["verdict"] == "not_a_descendant_of_main"
    assert by_sha["d1"]["verdict"] == "missing"
    assert fake.pushes() == []


def test_bless_qualifies_a_workflow_dispatch_run_even_before_the_verified_base_fix():
    """A run whose `event` is `workflow_dispatch` qualifies on its own —
    `test.yml` always forces `run_heavy=true` for those — even for a
    candidate that predates `_VERIFIED_BASE_FIX_SHA` (simulated here via
    `main_anc_all=False`, which also blocks the since-fix shortcut since
    `_is_ancestor(FIX_SHA, sha)` uses the SAME `anc` callable)."""
    old_sha = "d0"
    fake = FakeGit(
        refs={"origin/dev": old_sha, "origin/main": "m", "origin/prod": "p",
              "origin/prod-backup": "p"},
        anc=_anc_pairs([("m", old_sha)]),  # descendant of main, but NOT of the fix sha
        rev_list={f"m..{old_sha}": [old_sha]},
        ci_by_sha={old_sha: [{"status": "completed", "conclusion": "success",
                              "url": "https://ci/dispatch", "event": "workflow_dispatch",
                              "databaseId": 999}]},
        logs={f"m..{old_sha}": "c0 x"},
        assume_since_fix=False,
    )
    out = R.release(stage="bless", confirm=True, run=fake)
    assert out["status"] == "blessed"
    assert out["ci"]["qualifying_reason"] == "workflow_dispatch"
    gh = [c for c, _e in fake.calls if c[0] == "gh"]
    assert len(gh) == 1, "workflow_dispatch must short-circuit — no extra `gh run view` call"


def test_bless_falls_back_to_the_heavy_job_check_for_a_pre_fix_non_dispatch_green():
    """Neither since-fix nor workflow_dispatch — the third leg (an actual
    `Product Backend Tests *` job succeeded on this run) decides it."""
    old_sha = "d0"
    fake = FakeGit(
        refs={"origin/dev": old_sha, "origin/main": "m", "origin/prod": "p",
              "origin/prod-backup": "p"},
        anc=_anc_pairs([("m", old_sha)]),
        rev_list={f"m..{old_sha}": [old_sha]},
        ci_by_sha={old_sha: [{"status": "completed", "conclusion": "success",
                              "url": "https://ci/x", "event": "push", "databaseId": 42}]},
        jobs_by_run_id={"42": [{"name": "Product Backend Tests (pytest)", "conclusion": "success"}]},
        logs={f"m..{old_sha}": "c0 x"},
        assume_since_fix=False,
    )
    out = R.release(stage="bless", confirm=True, run=fake)
    assert out["status"] == "blessed"
    assert out["ci"]["qualifying_reason"] == "product_backend_tests_succeeded"
    gh = [c for c, _e in fake.calls if c[0] == "gh"]
    assert len(gh) == 2, "the third leg costs exactly one extra `gh run view` call"


def test_bless_rejects_a_green_run_whose_heavy_jobs_all_skipped():
    """The exact false-green this whole mechanism exists to catch: overall
    conclusion is 'success', but every downstream job merely skipped."""
    old_sha = "d0"
    fake = FakeGit(
        refs={"origin/dev": old_sha, "origin/main": "m", "origin/prod": "p",
              "origin/prod-backup": "p"},
        anc=_anc_pairs([("m", old_sha)]),
        rev_list={f"m..{old_sha}": [old_sha]},
        ci_by_sha={old_sha: [{"status": "completed", "conclusion": "success",
                              "url": "https://ci/x", "event": "push", "databaseId": 7}]},
        jobs_by_run_id={"7": [{"name": "Product Backend Tests (pytest)", "conclusion": "skipped"}]},
        logs={},
        assume_since_fix=False,
    )
    out = R.release(stage="bless", confirm=True, run=fake)
    assert out["status"] == "blocked"
    assert out["skipped_tail"][0]["qualifying_reason"] == "green_but_not_demonstrably_heavy"
    assert fake.pushes() == []
