"""Tests for the entry-aware LGPD-WARNINGS.md merge: the pure `merge_warnings`,
the CLI mode, and the REAL git driver (scripts/hooks/merge-lgpd-warnings.sh)
in throwaway repos where two branches each run `lgpd.flag(...)`.

Why it exists: `flag()` inserts every entry at the SAME anchor, so parallel flags
always conflicted, and the 2026-10-10 hand-resolution silently dropped one.

→ KB § PATTERNS/common/auto-generated-merge-drivers.md · lgpd-entry-keeper.md
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import lgpd  # noqa: E402
from tools.noctus.dev.lgpd import entry_identity, merge_warnings, parse_warnings  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
DRIVER = REPO / "scripts" / "hooks" / "merge-lgpd-warnings.sh"
REAL_CLI = REPO / "mcp" / "noctusai" / "cli.py"
FIX = Path(__file__).resolve().parent / "fixtures" / "lgpd"

HEADER = lgpd._FILE_HEADER


def _entry(concern: str, path: str, *, checked: bool = False, mit: str = "m", day: str = "2026-10-10") -> str:
    return lgpd._format_entry(concern=concern, code_path=path, reason="r", mitigation=mit,
                              first_flagged=day, last_seen=day, checked=checked)


def _doc(*entries: str, header: str = HEADER) -> str:
    return header + "\n".join(e.rstrip() for e in entries) + ("\n" if entries else "")


def _idents(text: str) -> list[tuple[str, str]]:
    return [entry_identity(b) for b in parse_warnings(text)[1]]


A, B, C = _entry("alpha", "a.py"), _entry("beta", "b.py"), _entry("gamma", "c.py")


class TestMergeWarnings:
    def test_identical_sides_are_a_noop(self):
        base = _doc(A, B)
        assert merge_warnings(base, base, base) == (base, False)

    def test_parallel_adds_keep_both_and_are_direction_independent(self):
        base = _doc(A)
        ours, theirs = _doc(B, A), _doc(C, A)
        out, conflicted = merge_warnings(base, ours, theirs)
        assert not conflicted
        assert sorted(_idents(out)) == sorted([("alpha", "a.py"), ("beta", "b.py"), ("gamma", "c.py")])
        assert out == merge_warnings(base, theirs, ours)[0]  # deterministic regardless of direction
        assert _idents(out)[-1] == ("alpha", "a.py")  # existing entry stays below the new ones

    def test_new_entries_sort_newest_first(self):
        base = _doc(A)
        old = _entry("older", "o.py", day="2026-10-01")
        new = _entry("newer", "n.py", day="2026-10-09")
        out, _ = merge_warnings(base, _doc(old, A), _doc(new, A))
        assert [i[0] for i in _idents(out)] == ["newer", "older", "alpha"]

    def test_same_entry_added_identically_on_both_sides_is_kept_once(self):
        base = _doc(A)
        side = _doc(B, A)
        out, conflicted = merge_warnings(base, side, side)
        assert not conflicted and _idents(out).count(("beta", "b.py")) == 1

    def test_one_sided_change_takes_that_side(self):
        base = _doc(A, B)
        edited = _doc(_entry("alpha", "a.py", mit="NEW"), B)
        assert merge_warnings(base, edited, base) == (edited, False)
        assert merge_warnings(base, base, edited) == (edited, False)

    def test_tick_on_one_side_and_add_on_the_other(self):
        base = _doc(A)
        ticked = _doc(_entry("alpha", "a.py", checked=True))
        out, conflicted = merge_warnings(base, ticked, _doc(B, A))
        assert not conflicted
        assert "- [x] **alpha**" in out and "- [ ] **beta**" in out

    def test_delete_on_one_side_unchanged_on_other_is_deleted(self):
        base = _doc(A, B)
        out, conflicted = merge_warnings(base, _doc(A), base)
        assert not conflicted and _idents(out) == [("alpha", "a.py")]
        # (the keeper, not the driver, polices deletes at commit time)

    def test_both_change_differently_conflicts_only_that_block(self):
        base = _doc(A, B)
        ours = _doc(_entry("alpha", "a.py", mit="ours"), B)
        theirs = _doc(_entry("alpha", "a.py", mit="theirs"), B)
        out, conflicted = merge_warnings(base, ours, theirs)
        assert conflicted
        assert out.count("<<<<<<< ours") == 1 and out.count(">>>>>>> theirs") == 1
        before, rest = out.split("<<<<<<< ours\n")
        inside, after = rest.split(">>>>>>> theirs\n")
        assert before == HEADER and "**beta**" not in inside  # only the one block is wrapped
        assert "Mitigation*: ours" in inside and "Mitigation*: theirs" in inside
        assert after.startswith("- [ ] **beta**")

    def test_modify_vs_delete_conflicts(self):
        base = _doc(A, B)
        out, conflicted = merge_warnings(base, _doc(B), _doc(_entry("alpha", "a.py", mit="x"), B))
        assert conflicted and "<<<<<<< ours" in out

    def test_header_edit_on_one_side_only_is_kept(self):
        base = _doc(A)
        new_header = HEADER.replace("Do not delete items", "Do NOT delete items")
        out, conflicted = merge_warnings(base, _doc(A), _doc(A, header=new_header))
        assert not conflicted and out.startswith(new_header)

    def test_ticked_and_reflagged_duplicate_identity_keep_their_own_edits(self):
        ticked = _entry("alpha", "a.py", checked=True)
        base = _doc(ticked)
        ours = _doc(_entry("alpha", "a.py"), ticked)  # re-flagged on top of the ticked one
        theirs = _doc(_entry("alpha", "a.py", checked=True, mit="theirs-edit"))
        out, conflicted = merge_warnings(base, ours, theirs)
        assert not conflicted
        assert "- [ ] **alpha**" in out and "theirs-edit" in out

    def test_real_incident_parallel_add_keeps_BOTH_entries(self):
        """6698da2e5 (adds the core transcription entry) vs the biblioteca flag that
        7c2667c83 made on a branch that did not have it. Base = 6698da2e5's parent."""
        base = (FIX / "base-5af13374b.md").read_text(encoding="utf-8")
        ours = (FIX / "pre-7c2667c83.md").read_text(encoding="utf-8")        # 6698da2e5's result
        post = (FIX / "post-7c2667c83.md").read_text(encoding="utf-8")
        biblioteca = next(b for b in parse_warnings(post)[1] if "Biblioteca de virais" in b)
        header, blocks = parse_warnings(base)
        theirs = header + "\n".join(b.rstrip() for b in [biblioteca, *blocks]) + "\n"
        out, conflicted = merge_warnings(base, ours, theirs)
        assert not conflicted
        concerns = " ".join(c for c, _ in _idents(out))
        assert "Platform transcription API (core)" in concerns and "Biblioteca de virais" in concerns
        assert len(_idents(out)) == len(_idents(ours)) + 1
        assert out == merge_warnings(base, theirs, ours)[0]


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "PYTHON": sys.executable}
    return subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=cwd, check=check,
                          capture_output=True, text=True, env=env)


def _make_repo(tmp_path: Path) -> Path:
    """A throwaway noc-shaped repo wired to the REAL driver and the REAL cli
    (through a shim, since the driver resolves `$REPO_ROOT/mcp/noctusai/cli.py`)."""
    root = tmp_path / "repo"
    (root / "scripts" / "hooks").mkdir(parents=True)
    (root / "mcp" / "noctusai").mkdir(parents=True)
    shutil.copy(DRIVER, root / "scripts" / "hooks" / "merge-lgpd-warnings.sh")
    (root / "mcp" / "noctusai" / "cli.py").write_text(
        "import runpy, sys\n"
        f"REAL = {str(REAL_CLI)!r}\n"
        "sys.argv[0] = REAL\n"
        "runpy.run_path(REAL, run_name='__main__')\n"
    )
    (root / ".gitattributes").write_text("LGPD-WARNINGS.md merge=lgpd-warnings\n")
    (root / ".noctusai-workspace").write_text("")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "merge.lgpd-warnings.driver",
         f"{root}/scripts/hooks/merge-lgpd-warnings.sh %O %A %B %P")
    lgpd.flag(code_path="seed.py", concern="seed-concern", reason="r", worktree_path=root)
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    return root


def _flag_commit(root: Path, concern: str, path: str) -> None:
    lgpd.flag(code_path=path, concern=concern, reason="r", worktree_path=root)
    _git(root, "add", "LGPD-WARNINGS.md")
    _git(root, "commit", "-qm", f"flag {concern}")


class TestLgpdMergeDriverRealGit:
    def test_two_branches_each_flagging_merge_cleanly_with_both_entries(self, tmp_path):
        root = _make_repo(tmp_path)
        _git(root, "checkout", "-qb", "feat-a")
        _flag_commit(root, "concern-a", "a.py")
        _git(root, "checkout", "-q", "main")
        _git(root, "checkout", "-qb", "feat-b")
        _flag_commit(root, "concern-b", "b.py")
        merged = _git(root, "merge", "--no-edit", "feat-a", check=False)
        assert merged.returncode == 0, merged.stdout + merged.stderr
        text = (root / "LGPD-WARNINGS.md").read_text()
        assert "<<<<<<<" not in text
        assert {c for c, _ in _idents(text)} == {"concern-a", "concern-b", "seed-concern"}
        assert _git(root, "status", "--porcelain").stdout.strip() == ""  # driver wrote %A only

    def test_rebase_of_parallel_flag_is_clean(self, tmp_path):
        """`task_branch integrate` rebases onto dev: the driver must survive it."""
        root = _make_repo(tmp_path)
        _git(root, "checkout", "-qb", "feat-b")
        _flag_commit(root, "concern-b", "b.py")
        _git(root, "checkout", "-q", "main")
        _flag_commit(root, "concern-a", "a.py")
        _git(root, "checkout", "-q", "feat-b")
        rb = _git(root, "rebase", "main", check=False)
        assert rb.returncode == 0, rb.stdout + rb.stderr
        text = (root / "LGPD-WARNINGS.md").read_text()
        assert {c for c, _ in _idents(text)} == {"concern-a", "concern-b", "seed-concern"}

    def test_genuine_conflict_surfaces_markers_and_exit_1(self, tmp_path):
        root = _make_repo(tmp_path)
        _git(root, "checkout", "-qb", "feat-a")
        lgpd.flag(code_path="seed.py", concern="seed-concern", reason="A-side reason", worktree_path=root)
        _git(root, "commit", "-qam", "edit a")
        _git(root, "checkout", "-q", "main")
        lgpd.flag(code_path="seed.py", concern="seed-concern", reason="main-side reason", worktree_path=root)
        _git(root, "commit", "-qam", "edit main")
        merged = _git(root, "merge", "--no-edit", "feat-a", check=False)
        assert merged.returncode != 0
        text = (root / "LGPD-WARNINGS.md").read_text()
        assert text.count("<<<<<<< ours") == 1 and "A-side reason" in text and "main-side reason" in text

    def test_driver_leaves_no_scratch_files(self, tmp_path):
        root = _make_repo(tmp_path)
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        base = tmp_path / "o.md"
        cur = tmp_path / "a.md"
        other = tmp_path / "b.md"
        base.write_text(_doc(A)); cur.write_text(_doc(B, A)); other.write_text(_doc(C, A))
        env = {**os.environ, "PYTHON": sys.executable, "TMPDIR": str(scratch)}
        proc = subprocess.run(
            ["bash", str(root / "scripts/hooks/merge-lgpd-warnings.sh"), str(base), str(cur), str(other), "LGPD-WARNINGS.md"],
            cwd=root, env=env, capture_output=True, text=True)
        assert proc.returncode == 0
        assert list(scratch.iterdir()) == []
        assert {c for c, _ in _idents(cur.read_text())} == {"alpha", "beta", "gamma"}

    def test_missing_cli_degrades_to_conflict_with_a_untouched(self, tmp_path):
        root = _make_repo(tmp_path)
        (root / "mcp" / "noctusai" / "cli.py").unlink()
        cur = tmp_path / "a.md"
        cur.write_text("keep me\n")
        (tmp_path / "o.md").write_text("o\n"); (tmp_path / "b.md").write_text("b\n")
        proc = subprocess.run(
            ["bash", str(root / "scripts/hooks/merge-lgpd-warnings.sh"),
             str(tmp_path / "o.md"), str(cur), str(tmp_path / "b.md"), "LGPD-WARNINGS.md"],
            cwd=root, env={**os.environ, "PYTHON": sys.executable}, capture_output=True, text=True)
        assert proc.returncode == 1 and cur.read_text() == "keep me\n"
