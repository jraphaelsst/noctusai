"""Real-git tests for the ship-consent rider manifest, the release CUT and the
backmerge (`noctus.dev.release` stage=manifest|bless|backmerge).

Each test builds a throwaway bare `origin` + a working clone (the repo the
tool runs in) under tmp_path. Only `gh` is scripted (CI verdict). Consent and
pointer ledgers are injected via the DI seams (`consent_rows`/`pointer_rows`/
`verify_consent`) — no monkeypatching.
KB § PATTERNS/devops/ship-consent-riders.md.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import release as R  # noqa: E402
from tools.noctus.dev import _release_riders as RR  # noqa: E402

#: R1 (2026-09-24): a green run in these tests always qualifies via the
# `workflow_dispatch` leg (the object shas these throwaway repos mint can
# never be a real descendant of `_VERIFIED_BASE_FIX_SHA` — that commit does
# not exist in a tmp bare repo — so the since-fix leg is structurally
# unavailable here; a dedicated qualifying-green-walk test below exercises
# the OTHER two legs explicitly instead of relying on this default).
_GREEN = [{"status": "completed", "conclusion": "success", "url": "https://ci/green",
          "event": "workflow_dispatch", "databaseId": 1}]
_NOW = dt.datetime(2026, 9, 22, 14, 5, tzinfo=dt.timezone.utc)
_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_NOSYSTEM": "1"}


def _sh(cwd: Path, *args: str, stdin: str | None = None) -> str:
    env = {**os.environ, **_ENV}
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                       input=stdin, env=env)
    assert r.returncode == 0, (args, r.stderr)
    return r.stdout.strip()


class Repo:
    """bare origin + `work` clone (where release runs) + `dev_wt` clone (where
    'agents' author commits and push to origin/dev)."""

    def __init__(self, tmp: Path):
        self.origin = tmp / "origin.git"
        _sh(tmp, "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.author = tmp / "author"
        _sh(tmp, "clone", "-q", str(self.origin), str(self.author))
        (self.author / "README.md").write_text("root\n")
        (self.author / "shared.py").write_text("x = 0\n")
        _sh(self.author, "add", "-A")
        _sh(self.author, "commit", "-qm", "root")
        _sh(self.author, "push", "-q", "origin", "HEAD:main", "HEAD:dev", "HEAD:prod")
        _sh(self.author, "checkout", "-qb", "dev", "--track", "origin/dev")
        self.work = tmp / "work"
        _sh(tmp, "clone", "-q", str(self.origin), str(self.work))
        self.ci = _GREEN
        # R1: per-sha `gh run list` override + per-run-id `gh run view --json
        # jobs` payload — the qualifying-green-walk tests need different
        # commits to carry different CI verdicts.
        self.ci_by_sha: dict[str, list] = {}
        self.jobs_by_run_id: dict[str, list] = {}
        self.calls: list[tuple[list[str], dict | None]] = []

    def commit(self, path: str, content: str, subject: str, branch: str | None = None) -> str:
        f = self.author / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content)
        _sh(self.author, "add", "-A")
        msg = subject + (f"\n\nNoc-Branch: {branch}\n" if branch else "\n")
        _sh(self.author, "commit", "-q", "-F", "-", stdin=msg)
        _sh(self.author, "push", "-q", "origin", "HEAD:dev")
        return _sh(self.author, "rev-parse", "HEAD")

    def ref(self, name: str) -> str:
        return _sh(self.origin, "rev-parse", name)

    def run(self, cmd, env_extra=None, stdin=None):
        self.calls.append((cmd, env_extra))
        if cmd[0] == "gh":
            if cmd[1:3] == ["run", "view"]:
                return 0, json.dumps({"jobs": self.jobs_by_run_id.get(cmd[3], [])}), ""
            if "--commit" in cmd:
                sha = cmd[cmd.index("--commit") + 1]
                return 0, json.dumps(self.ci_by_sha.get(sha, self.ci)), ""
            return 0, json.dumps(self.ci), ""
        env = {**os.environ, **_ENV, **(env_extra or {})}
        r = subprocess.run(cmd, cwd=str(self.work), capture_output=True, text=True,
                           input=stdin, env=env)
        return r.returncode, r.stdout, r.stderr

    def release(self, **kw):
        kw.setdefault("run", self.run)
        kw.setdefault("now", _NOW)
        kw.setdefault("verify_consent", lambda row: (True, ""))
        kw.setdefault("pointer_rows", [])
        kw.setdefault("consent_rows", [])
        return R.release(**kw)


def _consent(project: str, dev_sha: str, ts: str = "2026-09-22T10:00:00+00:00") -> dict:
    return {"ts": ts, "action": "author", "project": project, "dev_sha": dev_sha,
            "session_id": "s"}


@pytest.fixture()
def repo(tmp_path):
    return Repo(tmp_path)


def _alpha_scene(repo: Repo):
    a1 = repo.commit("a.py", "a = 1\n", "feat(a): one", "feat/a")
    d = repo.commit("KNOWLEDGE-BASE/x.md", "doc\n", "docs: x")
    u = repo.commit("u.py", "u = 1\n", "feat(u): wip", "feat/u")
    a2 = repo.commit("a2.py", "a2 = 1\n", "feat(a): two", "feat/a-eng")
    pointers = [{"branch": "feat/a", "project": "alpha"},
                {"branch": "feat/a-eng", "project": "alpha"}]
    return a1, d, u, a2, pointers


def _files_at(repo: Repo, sha: str) -> set[str]:
    return set(_sh(repo.origin, "ls-tree", "-r", "--name-only", sha).splitlines())


# ── manifest ─────────────────────────────────────────────────────────────────
def test_manifest_groups_riders_by_project_and_consent(repo):
    a1, d, u, a2, pointers = _alpha_scene(repo)
    out = repo.release(stage="manifest", pointer_rows=pointers,
                       consent_rows=[_consent("alpha", a2)])
    assert out["status"] == "manifest", out
    states = {c["sha"]: (c["state"], c["project"], c["attribution"]) for c in out["commits"]}
    assert states[a1] == ("approved", "alpha", "trailer")
    assert states[a2] == ("approved", "alpha", "trailer")
    assert states[d][0] == "exempt"
    assert states[u] == ("unapproved", "feat/u", "trailer")  # unmapped ⇒ branch name
    projects = {p["project"]: p for p in out["projects"]}
    assert projects["alpha"]["consent"] == "approved"
    assert projects["feat/u"]["consent"] == "none"
    assert out["all_approved"] is False
    assert out["ship"] == [a1, d, a2]
    assert repo.ref("main") == repo.ref("prod")  # read-only


def test_consent_covers_only_commits_up_to_its_dev_sha(repo):
    a1 = repo.commit("a.py", "a = 1\n", "feat(a): one", "feat/a")
    a2 = repo.commit("a2.py", "a2 = 1\n", "feat(a): later", "feat/a")
    out = repo.release(stage="manifest", pointer_rows=[{"branch": "feat/a", "project": "alpha"}],
                       consent_rows=[_consent("alpha", a1)])
    states = {c["sha"]: c["state"] for c in out["commits"]}
    assert states == {a1: "approved", a2: "unapproved"}
    assert out["projects"][0]["consent"] == "partial"


def test_revoked_and_unverified_consents_approve_nothing(repo):
    a1 = repo.commit("a.py", "a = 1\n", "feat(a): one", "feat/a")
    rows = [_consent("feat/a", a1),
            {"ts": "2026-09-22T11:00:00+00:00", "action": "revoke", "project": "feat/a"}]
    assert repo.release(stage="manifest", consent_rows=rows)["commits"][0]["state"] == "unapproved"
    out = repo.release(stage="manifest", consent_rows=[_consent("feat/a", a1)],
                       verify_consent=lambda row: (False, "no transcript"))
    assert out["commits"][0]["state"] == "unapproved"
    assert out["projects"][0]["consent"] == "unverified"


def test_legacy_attribution_pointer_commit_subject_patch_id_else_unattributed(repo):
    by_sha = repo.commit("l1.py", "1\n", "chore: legacy one")
    by_subject = repo.commit("l2.py", "2\n", "chore: legacy two")
    # patch-id: the pointer recorded the PRE-rebase sha on feat/p; dev carries
    # the same patch under a different sha + subject.
    _sh(repo.author, "checkout", "-q", "-b", "feat/p", "origin/main")
    (repo.author / "p.py").write_text("p = 1\n")
    _sh(repo.author, "add", "p.py")
    _sh(repo.author, "commit", "-qm", "feat(p): pre-rebase")
    pre = _sh(repo.author, "rev-parse", "HEAD")
    _sh(repo.author, "push", "-q", "origin", "feat/p")
    _sh(repo.author, "checkout", "-q", "dev")
    by_pid = repo.commit("p.py", "p = 1\n", "feat(p): landed")
    orphan = repo.commit("o.py", "o\n", "chore: nobody's")
    _sh(repo.work, "fetch", "-q", "origin")
    pointers = [{"branch": "feat/l1", "commit": by_sha[:9]},
                {"branch": "feat/l2", "commit": "", "notes": "chore: legacy two"},
                {"branch": "feat/p", "commit": pre[:9]}]
    out = repo.release(stage="manifest", pointer_rows=pointers)
    got = {c["sha"]: (c["branch"], c["attribution"], c["state"]) for c in out["commits"]}
    assert got[by_sha] == ("feat/l1", "pointer-commit", "unapproved")
    assert got[by_subject] == ("feat/l2", "pointer-subject", "unapproved")
    assert got[by_pid] == ("feat/p", "patch-id", "unapproved")
    assert got[orphan] == (None, "none", "unattributed")
    assert any("unattributed" in r for r in out["unapproved_riders"])


# ── bless: default mode='ff' ships to the newest CI-qualifying-green commit
#    main..dev (owner decision 2026-09-24: the ask is the permission; R1,
#    2026-09-24: not necessarily the exact tip — see git-branch-model.md);
#    mode='cut'/'refuse' are explicit opt-ins ─────────────────────────────
def test_default_bless_fast_forwards_with_unapproved_riders(repo):
    """No ship-consent at all: the default bless still ships. `repo`'s default
    CI fixture (`_GREEN`, a `workflow_dispatch`-shaped run) qualifies the dev
    tip itself here, so blessed_sha == dev tip in THIS scenario — R1's walk
    is exercised separately in the qualifying-green-specific tests below."""
    a1, d, u, a2, pointers = _alpha_scene(repo)
    out = repo.release(stage="bless", confirm=True, pointer_rows=pointers, consent_rows=[])
    assert out["status"] == "blessed", out
    assert repo.ref("main") == repo.ref("dev")
    assert out["riders"]["all_approved"] is False and out["riders"]["unapproved"]


def test_default_bless_still_requires_ci_green(repo):
    repo.commit("a.py", "a = 1\n", "feat(a): one", "feat/a")
    main0 = repo.ref("main")
    repo.ci = []
    out = repo.release(stage="bless", confirm=True)
    assert out["status"] == "blocked" and out["ci"]["verdict"] == "missing", out
    assert repo.ref("main") == main0


# R1 (2026-09-24): bless the newest QUALIFYING green descendant, not
# necessarily the exact dev tip — the dev-freeze fix (a bookkeeping train at
# the tip no longer requires a fresh CI run before ANY bless can land).
def test_default_bless_walks_past_an_unverified_tail_to_a_qualifying_green_ancestor(repo):
    a1, d, u, a2, pointers = _alpha_scene(repo)
    # Only `d` (2nd-oldest — a docs commit) carries a qualifying green CI
    # run; everything newer (`u`, `a2`) has NO run at all yet.
    repo.ci = []  # nothing qualifies by default
    repo.ci_by_sha = {d: _GREEN}
    out = repo.release(stage="bless", confirm=True, pointer_rows=pointers, consent_rows=[])
    assert out["status"] == "blessed", out
    assert out["blessed_sha"] == d
    assert out["dev_tip"] == a2 and out["dev_tip"] != d
    assert out["skipped_tail"]["count"] == 2
    assert set(out["skipped_tail"]["commits"]) == {a2[:9], u[:9]}
    # project attribution on the skipped tail, reusing the SAME rider
    # manifest already built for the bless call (no second read):
    # a2 -> "alpha" (Noc-Branch: feat/a-eng, mapped via `pointers`), u ->
    # "feat/u" (unmapped Noc-Branch ⇒ branch name, per the manifest tests).
    assert out["skipped_tail"]["projects"] == ["alpha", "feat/u"]
    # main really did stop AT `d`, never reaching the dev tip.
    assert repo.ref("main") == d


def test_default_bless_refuses_a_diverged_main_until_backmerge(repo):
    a1, d, u, a2, pointers = _alpha_scene(repo)
    kw = dict(pointer_rows=pointers, consent_rows=[_consent("alpha", a2)])
    repo.release(stage="bless", mode="cut", confirm=True, **kw)
    repo.release(stage="bless", release_branch="release/20260922-1405", confirm=True, **kw)
    out = repo.release(stage="bless", confirm=True, **kw)
    assert out["status"] == "blocked" and "backmerge" in out["reason"], out
def test_bless_all_approved_keeps_the_fast_forward(repo):
    a1 = repo.commit("a.py", "a = 1\n", "feat(a): one", "feat/a")
    repo.commit("KNOWLEDGE-BASE/x.md", "doc\n", "docs: x")
    out = repo.release(stage="bless", confirm=True, consent_rows=[_consent("feat/a", a1)])
    assert out["status"] == "blessed", out
    assert repo.ref("main") == repo.ref("dev")


def test_bless_with_unapproved_rider_cuts_release_of_approved_only(repo):
    a1, d, u, a2, pointers = _alpha_scene(repo)
    main0 = repo.ref("main")
    kw = dict(pointer_rows=pointers, consent_rows=[_consent("alpha", a2)])

    plan = repo.release(stage="bless", mode="cut", **kw)
    assert plan["status"] == "planned_cut" and plan["release_branch"] == "release/20260922-1405"
    assert [p["from"] for p in plan["picked"]] == [a1, d, a2]
    assert repo.ref("main") == main0

    cut = repo.release(stage="bless", mode="cut", confirm=True, **kw)
    assert cut["status"] == "cut_pushed", cut
    rel = repo.ref("release/20260922-1405")
    files = _files_at(repo, rel)
    assert {"a.py", "a2.py", "KNOWLEDGE-BASE/x.md"} <= files and "u.py" not in files
    assert repo.ref("main") == main0, "a cut never moves main"
    body = _sh(repo.origin, "log", "-1", "--format=%B", rel)
    assert f"(cherry picked from commit {a2})" in body and "Noc-Branch: feat/a-eng" in body
    assert _sh(repo.origin, "log", "-1", "--format=%an", rel) == "t"

    blessed = repo.release(stage="bless", release_branch="release/20260922-1405",
                           confirm=True, **kw)
    assert blessed["status"] == "blessed" and blessed["verified"], blessed
    assert repo.ref("main") == rel
    main_pushes = [(c, e) for c, e in repo.calls
                   if c[:2] == ["git", "push"] and c[-1].endswith("refs/heads/main")]
    assert len(main_pushes) == 1 and main_pushes[0][1] == {"NOCTUS_ALLOW_MAIN_PUSH": "1"}
    other = [(c, e) for c, e in repo.calls
             if c[:2] == ["git", "push"] and not c[-1].endswith("refs/heads/main")]
    assert other and all(e is None for _c, e in other), "override only on the main push"


def test_bless_refuses_when_ci_not_green_on_release_sha(repo):
    a1, d, u, a2, pointers = _alpha_scene(repo)
    kw = dict(pointer_rows=pointers, consent_rows=[_consent("alpha", a2)])
    repo.release(stage="bless", mode="cut", confirm=True, **kw)
    repo.ci = []
    out = repo.release(stage="bless", release_branch="release/20260922-1405", confirm=True, **kw)
    assert out["status"] == "blocked" and out["ci"]["verdict"] == "missing"


def test_release_branch_with_foreign_commit_is_refused(repo):
    a1, d, u, a2, pointers = _alpha_scene(repo)
    kw = dict(pointer_rows=pointers, consent_rows=[_consent("alpha", a2)])
    repo.release(stage="bless", mode="cut", confirm=True, **kw)
    _sh(repo.author, "fetch", "-q", "origin")
    _sh(repo.author, "checkout", "-q", "-b", "sneak", "origin/release/20260922-1405")
    (repo.author / "evil.py").write_text("1\n")
    _sh(repo.author, "add", "evil.py")
    _sh(repo.author, "commit", "-qm", "hand-added")
    _sh(repo.author, "push", "-q", "origin", "HEAD:release/20260922-1405")
    out = repo.release(stage="bless", release_branch="release/20260922-1405", confirm=True, **kw)
    assert out["status"] == "blocked" and out["foreign_commits"]


def test_mode_refuse_blocks_without_writing(repo):
    a1, d, u, a2, pointers = _alpha_scene(repo)
    out = repo.release(stage="bless", confirm=True, mode="refuse", pointer_rows=pointers,
                       consent_rows=[_consent("alpha", a2)])
    assert out["status"] == "blocked" and out["unapproved_riders"]
    assert not [c for c, _e in repo.calls if c[:2] == ["git", "push"]]


def test_cut_refuses_approved_commit_that_depends_on_unapproved_rider(repo):
    u = repo.commit("shared.py", "x = 1\n", "feat(u): change shared", "feat/u")
    a = repo.commit("shared.py", "x = 2\n", "feat(a): builds on shared", "feat/a")
    out = repo.release(stage="bless", mode="cut", confirm=True, consent_rows=[_consent("feat/a", a)])
    assert out["status"] == "blocked"
    assert out["dependencies"][0]["commit"] == a and out["dependencies"][0]["depends_on"] == [u]
    assert "shared.py" in out["dependencies"][0]["files"]
    assert not [c for c, _e in repo.calls if c[:2] == ["git", "push"]]


def test_docs_commit_depending_on_rider_is_deferred_not_refused(repo):
    (repo.author / "KNOWLEDGE-BASE").mkdir(exist_ok=True)
    (repo.author / "KNOWLEDGE-BASE/u.md").write_text("u doc\n")
    repo.commit("u.py", "u\n", "feat(u): wip + its doc", "feat/u")  # u.py AND u.md
    repo.commit("KNOWLEDGE-BASE/u.md", "u doc v2\n", "docs: touch u doc")
    a = repo.commit("a.py", "a\n", "feat(a): one", "feat/a")
    out = repo.release(stage="bless", mode="cut", consent_rows=[_consent("feat/a", a)])
    assert out["status"] == "planned_cut", out
    assert len(out["deferred"]) == 1 and out["ship"][-1] == a


def test_nothing_approved_blocks(repo):
    repo.commit("u.py", "u\n", "feat(u): wip", "feat/u")
    out = repo.release(stage="bless", mode="cut", confirm=True)
    assert out["status"] == "blocked" and "nothing approved" in out["reason"]


# ── patch-id skip + backmerge ────────────────────────────────────────────────
def test_after_cut_shipped_work_is_on_main_then_backmerge_restores_ff(repo):
    a1, d, u, a2, pointers = _alpha_scene(repo)
    kw = dict(pointer_rows=pointers, consent_rows=[_consent("alpha", a2)])
    repo.release(stage="bless", mode="cut", confirm=True, **kw)
    repo.release(stage="bless", release_branch="release/20260922-1405", confirm=True, **kw)

    man = repo.release(stage="manifest", **kw)
    states = {c["sha"]: c["state"] for c in man["commits"]}
    assert states[a1] == states[a2] == states[d] == "on_main"
    assert states[u] == "unapproved" and man["ff"] is False
    again = repo.release(stage="bless", mode="cut", **kw)
    assert again["status"] == "blocked" and "nothing approved" in again["reason"]

    plan = repo.release(stage="backmerge")
    assert plan["status"] == "planned"
    done = repo.release(stage="backmerge", confirm=True)
    assert done["status"] == "backmerged" and done["verified"], done
    assert _sh(repo.origin, "merge-base", "--is-ancestor", "main", "dev") == ""
    assert repo.release(stage="backmerge")["status"] == "up_to_date"

    # dev ⊇ main again: the plain FF bless works (default mode='ff').
    new_dev = repo.ref("dev")
    ok = repo.release(stage="bless", confirm=True, pointer_rows=pointers,
                      consent_rows=[_consent("alpha", a2), _consent("feat/u", new_dev)])
    assert ok["status"] == "blessed", ok
    assert repo.ref("main") == new_dev


def test_unit_plan_ship_set_ignores_ledger_paths_for_dependencies():
    riders = [
        {"sha": "u", "subject": "", "project": "p", "state": "unapproved",
         "files": ["project-history/branch-tree.ndjson", "u.py"]},
        {"sha": "a", "subject": "", "project": "q", "state": "approved",
         "files": ["project-history/branch-tree.ndjson"]},
    ]
    plan = RR.plan_ship_set(riders)
    assert plan["ship"] == ["a"] and plan["dependencies"] == []


def test_default_runner_roundtrips_non_utf8_bytes(tmp_path, monkeypatch):
    """stage=manifest crashed on a non-UTF-8 byte in `git log -p` (2026-09-23)."""
    import subprocess as sp
    import settings
    from tools.noctus.dev import release as R
    repo = tmp_path / "r"
    repo.mkdir()
    sp.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "latin1.txt").write_bytes(b"caf\xe9 \x93quoted\x94\n")
    sp.run(["git", "-C", str(repo), "add", "."], check=True)
    sp.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
            "commit", "-qm", "x"], check=True)
    monkeypatch.setattr(settings, "REPO_ROOT", repo)
    rc, out, _e = R._default_run_local(["git", "log", "-p", "--format=commit %H", "-1"])
    assert rc == 0
    rc2, ids, _e2 = R._default_run_local(["git", "patch-id", "--stable"], stdin=out)
    assert rc2 == 0 and len(ids.split()) == 2
