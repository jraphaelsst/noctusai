"""The pre-push hook recognises the guardian's PURE PUSH as the merge-queue path.

`git push origin <sha>:refs/heads/mq/<slug>--<sha7>` from the PRIMARY checkout (HEAD=dev) was refused
under the generic "main is sacred" banner: a bare sha is the local ref, so the branch-tree mirror
keeper was asked about a branch named after the sha and found no pointer (2026-11-10). These tests
install the REAL hook script in a temp repo (real git, real push); only the toolkit CLI the hook
shells out to is a stub that answers the mirror keeper the way the real one does for an unknown
name (exit 1) and everything else green.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(os.environ.get("NOC_PRE_PUSH_HOOK_UNDER_TEST") or Path(__file__).resolve().parents[3] / "scripts" / "hooks" / "pre-push")  # env: red/green proof against the pre-fix hook
_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t", "NOCTUS_HOOK_QUIET": "1"}
for _k in ("NOCTUS_ALLOW_MAIN_PUSH", "NOCTUS_SKIP_EMBED_REFRESH", "NOCTUS_SKIP_DOC_STALENESS"):
    _ENV.pop(_k, None)
_STUB_CLI = """\
import pathlib, sys
if sys.argv[1] == "--check-branch-tree-mirror":
    known = pathlib.Path(__file__).resolve().parent.joinpath("pointers.txt").read_text().split()
    if sys.argv[2] in known:
        print("ok"); sys.exit(0)
    print("[high] No branch-pointer found for %r" % sys.argv[2]); sys.exit(1)
sys.exit(0)
"""


def git(cwd, *a, check=True, env=None):
    r = subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, env={**_ENV, **(env or {})})
    if check and r.returncode:
        raise AssertionError(r.stderr)
    return r


@pytest.fixture()
def repo(tmp_path):
    origin, repo = tmp_path / "origin.git", tmp_path / "repo"
    git(tmp_path, "init", "--bare", "-b", "dev", str(origin))
    git(tmp_path, "clone", str(origin), str(repo))
    git(repo, "checkout", "-b", "dev")
    tool = repo / "mcp" / "noctusai"
    (tool / ".venv" / "bin").mkdir(parents=True)
    (tool / ".venv" / "bin" / "python").symlink_to(sys.executable)
    (tool / "cli.py").write_text(_STUB_CLI)
    (tool / "pointers.txt").write_text("feat/x\n")
    (repo / "a.txt").write_text("a\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "init")
    git(repo, "push", "--no-verify", "origin", "dev")  # seeding the fixture only, before the hook exists
    git(repo, "checkout", "-b", "feat/x")
    (repo / "b.txt").write_text("b\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "feat: b")
    git(repo, "checkout", "dev")  # the guardian's checkout: HEAD=dev, the delivery branch is NOT checked out here
    hook = repo / ".git" / "hooks" / "pre-push"
    shutil.copy(HOOK, hook)
    hook.chmod(0o755)
    return repo


def attest(repo, s, *, ok=True, age_s=0, sha=None, ref=None):
    """What `task_branch enqueue` writes right before its push: <git-common-dir>/noc-enqueue/<full sha>.json."""
    import json
    import time
    d = repo / ".git" / "noc-enqueue"
    d.mkdir(exist_ok=True)
    (d / f"{s}.json").write_text(json.dumps({"sha": sha or s, "ok": ok, "verdict": "deliverable" if ok else "needs_resync",
                                              "ref": ref or f"refs/heads/mq/x--{s[:7]}", "ts": time.time() - age_s}))


def sha(repo, ref="feat/x"):
    return git(repo, "rev-parse", ref).stdout.strip()


def remote_refs(repo):
    return sorted(ln.split("\t")[1] for ln in git(repo, "ls-remote", "origin").stdout.splitlines())


def test_the_exact_sha_mq_push_from_head_dev_is_allowed(repo):
    s = sha(repo)
    attest(repo, s)
    r = git(repo, "push", "origin", f"{s}:refs/heads/mq/x--{s[:7]}", check=False)
    assert r.returncode == 0, r.stderr
    assert f"refs/heads/mq/x--{s[:7]}" in remote_refs(repo)
    assert "queue path" in r.stdout + r.stderr


def test_an_mq_push_whose_sha7_does_not_match_is_refused(repo):
    s = sha(repo)
    r = git(repo, "push", "origin", f"{s}:refs/heads/mq/x--abcdef0", check=False)
    assert r.returncode != 0 and "must be mq/<slug>--<sha7>" in r.stderr
    assert not any("mq/" in ref for ref in remote_refs(repo))


def test_an_mq_ref_without_a_sha7_suffix_is_refused(repo):
    s = sha(repo)
    r = git(repo, "push", "origin", f"{s}:refs/heads/mq/x", check=False)
    assert r.returncode != 0 and "must be mq/<slug>--<sha7>" in r.stderr


@pytest.mark.parametrize("other", ["main", "dev", "prod"])
def test_an_mq_push_combined_with_another_ref_is_refused(repo, other):
    s = sha(repo)
    r = git(repo, "push", "origin", f"{s}:refs/heads/mq/x--{s[:7]}", f"{s}:refs/heads/{other}", check=False)
    assert r.returncode != 0 and "rides ALONE" in r.stderr
    assert not any(ref.startswith("refs/heads/mq/") for ref in remote_refs(repo))
    assert not any(ref == f"refs/heads/{other}" and other != "dev" for ref in remote_refs(repo))


def test_a_plain_push_to_main_is_still_refused(repo):
    s = sha(repo)
    r = git(repo, "push", "origin", f"{s}:refs/heads/main", check=False)
    assert r.returncode != 0 and "BLOCKED" in r.stderr and "production" in r.stderr
    assert "refs/heads/main" not in remote_refs(repo)


def test_a_bare_sha_push_to_an_ordinary_branch_still_meets_the_mirror_keeper(repo):
    """The carve-out is the queue ref ONLY: a bare sha pushed to any other branch name is still judged
    by the branch-tree mirror keeper (the pointer-less name is refused)."""
    s = sha(repo)
    r = git(repo, "push", "origin", f"{s}:refs/heads/feat/other", check=False)
    assert r.returncode != 0 and "branch-tree mirror keeper BLOCKED" in r.stderr


def test_the_head_form_is_refused_the_local_side_must_be_a_bare_sha(repo):
    """N-5: `HEAD:refs/heads/mq/...` / `feat/x:refs/heads/mq/...` name a REF, not the attested sha."""
    git(repo, "checkout", "feat/x")
    s = sha(repo)
    attest(repo, s)
    for src in ("HEAD", "feat/x", "refs/heads/feat/x"):
        r = git(repo, "push", "origin", f"{src}:refs/heads/mq/x--{s[:7]}", check=False)
        assert r.returncode != 0 and "by sha" in r.stderr, (src, r.stderr)
    assert not any("mq/" in ref for ref in remote_refs(repo))


# -- P1-2 (adversarial review): the queue path is for `task_branch enqueue`, not for anyone who types the refspec --

def test_a_raw_exact_sha_mq_push_without_an_enqueue_attestation_is_refused(repo):
    s = sha(repo)
    r = git(repo, "push", "origin", f"{s}:refs/heads/mq/x--{s[:7]}", check=False)
    assert r.returncode != 0
    assert "no enqueue attestation" in r.stderr and "task_branch action=enqueue" in r.stderr
    assert not any("mq/" in ref for ref in remote_refs(repo))


@pytest.mark.parametrize("kw,why", [
    ({"ok": False}, "not ok"),
    ({"age_s": 11 * 60}, "older than"),
    ({"sha": "f" * 40}, "another sha"),
])
def test_a_stale_not_ok_or_mismatched_attestation_is_refused(repo, kw, why):
    s = sha(repo)
    attest(repo, s, **kw)
    r = git(repo, "push", "origin", f"{s}:refs/heads/mq/x--{s[:7]}", check=False)
    assert r.returncode != 0, why
    assert "task_branch action=enqueue" in r.stderr
    assert not any("mq/" in ref for ref in remote_refs(repo))


def test_an_attestation_for_one_sha_does_not_cover_another(repo):
    a = sha(repo)
    git(repo, "checkout", "-q", "feat/x")
    (repo / "c.txt").write_text("c\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "feat: c")
    git(repo, "checkout", "-q", "dev")
    b = sha(repo)
    attest(repo, a)
    r = git(repo, "push", "origin", f"{b}:refs/heads/mq/x--{b[:7]}", check=False)
    assert r.returncode != 0 and "no enqueue attestation" in r.stderr


# -- N-5 (adversarial review, round 2): the attestation is scoped to the ref, one mq ref per push --------------

def test_an_attestation_for_one_queue_ref_does_not_authorise_another(repo):
    s = sha(repo)
    attest(repo, s, ref=f"refs/heads/mq/other--{s[:7]}")
    r = git(repo, "push", "origin", f"{s}:refs/heads/mq/x--{s[:7]}", check=False)
    assert r.returncode != 0 and "no enqueue attestation" in r.stderr
    assert not any("mq/" in ref for ref in remote_refs(repo))


def test_two_mq_refs_in_one_push_are_refused(repo):
    s = sha(repo)
    attest(repo, s)
    r = git(repo, "push", "origin", f"{s}:refs/heads/mq/x--{s[:7]}", f"{s}:refs/heads/mq/y--{s[:7]}", check=False)
    assert r.returncode != 0 and "exactly ONE merge-queue ref" in r.stderr
    assert not any("mq/" in ref for ref in remote_refs(repo))


# ─── withdrawal: deleting a queue ref (2026-11-10) ───────────────────────────────────────────────
# The guardian withdraws a queued culprit by deleting its mq ref, so the drain drops it instead of
# bisecting it. A delete has local side "(delete)" and an all-zero oid; the guard refused it as a
# ref-named push. Who may delete is the steward PreToolUse gate's call, asserted below.

def _queue(repo):
    s = sha(repo)
    attest(repo, s)
    ref = f"refs/heads/mq/x--{s[:7]}"
    git(repo, "push", "origin", f"{s}:{ref}")
    assert ref in remote_refs(repo)
    return s, ref


@pytest.mark.parametrize("form", ["--delete", "colon"])
def test_deleting_a_queue_ref_withdraws_it(repo, form):
    _s, ref = _queue(repo)
    args = ["--delete", ref.removeprefix("refs/heads/")] if form == "--delete" else [f":{ref}"]
    r = git(repo, "push", "origin", *args, check=False)
    assert r.returncode == 0, r.stderr
    assert ref not in remote_refs(repo)
    assert "withdrawal" in r.stdout + r.stderr


def test_a_queue_ref_delete_still_rides_alone(repo):
    s, ref = _queue(repo)
    r = git(repo, "push", "origin", f":{ref}", f"{s}:refs/heads/feat/x", check=False)
    assert r.returncode != 0 and "rides ALONE" in r.stderr
    assert ref in remote_refs(repo)


def test_deleting_a_protected_branch_is_still_refused(repo):
    r = git(repo, "push", "origin", "--delete", "dev", check=False)
    assert r.returncode != 0
    assert "refs/heads/dev" in remote_refs(repo)


@pytest.mark.parametrize("cmd", ["git push origin --delete mq/x--abcdef0",
                                 "git push origin :refs/heads/mq/x--abcdef0",
                                 "git push -d origin mq/x--abcdef0"])
def test_who_may_delete_a_queue_ref_is_the_steward_gate(cmd):
    import importlib.util
    path = Path(__file__).resolve().parents[1] / "tools" / "noctus" / "dev" / "release_steward.py"
    spec = importlib.util.spec_from_file_location("rs_mq_delete_ut", path)
    rs = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = rs
    spec.loader.exec_module(rs)
    hit = rs.classify_bash(cmd)
    assert hit is not None and "mq/x--abcdef0" in hit.kind, cmd
