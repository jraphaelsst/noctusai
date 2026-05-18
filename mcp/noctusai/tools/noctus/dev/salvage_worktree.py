"""noctus.dev.salvage_worktree — operationalize the R6 engineer-salvage
ritual (verify true disk → scoped authorship commit → cherry-pick onto
the integration branch → confirm landed / refuse loudly on divergence).

Replaces the ~10x/session manual git ritual that caused the
stash-entanglement bug + the two lost-work incidents. The harness
overlay⊥worktree divergence (see KB § PATTERNS/ast.md neighbours +
memory feedback_harness_overlay_worktree_divergence) means "engineer
reported done" is NOT evidence — on-disk grep is. This tool runs the
verification from the SERVER's own context (true disk), never trusts a
report.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def _git(cwd: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", cwd, *args], capture_output=True, text=True, timeout=120
    )


def salvage_worktree(
    agent_worktree: str,
    message: str,
    expect_markers: list[list[str]] | None = None,
    onto_worktree: str | None = None,
    author_name: str = "jraphaelsst",
    author_email: str = "joaoraphaelsst@gmail.com",
) -> dict:
    """Verify + commit an engineer worktree's staged work, optionally
    cherry-pick it onto the integration branch.

    `expect_markers`: list of `[relpath, substring]` — each is grep'd on
    the ACTUAL on-disk file; any miss ⇒ divergence refusal (do NOT
    loop-redispatch; re-author in the worktree via Bash). `onto_worktree`:
    path of the worktree where the integration branch is checked out; if
    given, the commit is cherry-picked there + verified present.
    """
    wt = Path(agent_worktree)
    if not (wt / ".git").exists():
        return {"ok": False, "error": f"not a git worktree: {wt}"}

    staged = [
        l for l in _git(str(wt), "diff", "--cached", "--name-only").stdout.splitlines()
        if l.strip()
    ]
    if not staged:
        return {
            "ok": False,
            "divergence_suspected": True,
            "error": (
                "nothing staged — likely harness overlay⊥worktree "
                "divergence (R6): the engineer's overlay reported success "
                "but true disk is clean. Do NOT loop-redispatch; "
                "re-author the change in this worktree via Bash, or apply "
                "architect-inline from a reliable context."
            ),
        }

    miss = []
    for marker in expect_markers or []:
        rel, needle = marker[0], marker[1]
        fp = wt / rel
        if not fp.exists() or needle not in fp.read_text(errors="ignore"):
            miss.append({"path": rel, "needle": needle})
    if miss:
        return {
            "ok": False,
            "divergence_suspected": True,
            "missing_on_disk": miss,
            "error": "expected change text absent on true disk — R6 divergence; re-author via Bash.",
        }

    commit = _git(
        str(wt),
        "-c", f"user.name={author_name}",
        "-c", f"user.email={author_email}",
        "commit", "-q", "-m", message,
    )
    if commit.returncode != 0:
        return {"ok": False, "error": f"commit failed: {commit.stderr.strip()}"}
    sha = _git(str(wt), "rev-parse", "HEAD").stdout.strip()
    result: dict = {"ok": True, "committed_sha": sha, "staged_files": staged}

    if onto_worktree:
        cp = _git(onto_worktree, "cherry-pick", sha)
        if cp.returncode != 0:
            _git(onto_worktree, "cherry-pick", "--abort")
            result["cherry_pick"] = {
                "ok": False,
                "error": f"cherry-pick failed (aborted): {cp.stderr.strip()}",
            }
            return result
        onto_sha = _git(onto_worktree, "rev-parse", "HEAD").stdout.strip()
        landed = all(
            _git(onto_worktree, "cat-file", "-e", f"HEAD:{f}").returncode == 0
            for f in staged
        )
        result["cherry_pick"] = {
            "ok": landed,
            "onto_sha": onto_sha,
            "files_present_on_branch": landed,
        }
    else:
        result["next"] = f"git -C <integration-worktree> cherry-pick {sha}"
    return result


def register(server) -> None:
    @server.tool(
        name="noctus.dev.salvage_worktree",
        description=(
            "Operationalizes the R6 engineer-salvage ritual: verify the "
            "agent worktree's staged work is on TRUE DISK (refuses loudly "
            "on overlay⊥worktree divergence — do NOT loop-redispatch), "
            "scoped authorship commit, optional cherry-pick onto the "
            "integration worktree + landed-verify. Pass expect_markers "
            "[[relpath, substring], ...] to assert the change physically "
            "landed. Replaces the ~10x/session manual git ritual."
        ),
    )
    def _salvage(
        agent_worktree: str,
        message: str,
        expect_markers: list[list[str]] | None = None,
        onto_worktree: str | None = None,
    ) -> dict:
        return salvage_worktree(
            agent_worktree, message,
            expect_markers=expect_markers, onto_worktree=onto_worktree,
        )


__all__ = ["salvage_worktree", "register"]
