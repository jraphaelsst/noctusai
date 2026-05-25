"""Tests for noctus.dev.scan_remediation_markers (KB § PATTERNS/remediation-markers.md).

Real git repos + real `git grep` (no monkey-patch of our own code) so the
parse/classify/group predicates exercise the actual plumbing.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.scan_remediation_markers import scan_remediation_markers


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True,
                   capture_output=True, text=True)


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    r = tmp_path / "noc"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@t.t")
    _git(r, "config", "user.name", "t")
    for rel, content in files.items():
        p = r / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "seed")
    return r


class TestScan:
    def test_wellformed_grouped_and_clean_exit(self, tmp_path):
        r = _repo(tmp_path, {
            "a.py": "# NOC-REMEDIATE[perf]: tighten the loop — 2026-05-01\nx = 1\n",
            "b.py": "# NOC-REMEDIATE[perf]: cache the call — 2026-05-02\n",
        })
        res = scan_remediation_markers(repo_root=r)
        assert res["total"] == 2
        assert res["by_class"] == {"perf": 2}
        assert res["promote_candidates"] == []        # perf at N=2 (< 3)
        assert res["malformed"] == []
        assert res["on_except"] == []
        assert res["exit_code"] == 0
        assert res["status"] == "markers"

    def test_recurrence_promote_candidate_at_n3(self, tmp_path):
        lines = "".join(
            f"# NOC-REMEDIATE[dry]: extract helper {i} — 2026-05-1{i}\n" for i in range(3)
        )
        r = _repo(tmp_path, {"c.py": lines})
        res = scan_remediation_markers(repo_root=r)
        assert res["by_class"]["dry"] == 3
        assert "dry" in res["promote_candidates"]      # N≥3 ⇒ promote

    def test_malformed_missing_date_flagged(self, tmp_path):
        r = _repo(tmp_path, {
            "d.py": "# NOC-REMEDIATE[bug]: no date here\n",  # real class, missing date
        })
        res = scan_remediation_markers(repo_root=r)
        assert res["total"] == 1
        assert len(res["malformed"]) == 1
        assert res["exit_code"] == 1                   # defect ⇒ nonzero

    def test_prose_mentions_not_flagged(self, tmp_path):
        """The scanner must NOT trip on docs/code that merely MENTION the token
        (placeholder `[<class>]` or no bracket) — the false-positive fix."""
        r = _repo(tmp_path, {
            "doc.md": "The `NOC-REMEDIATE[<class>]: <what> — <YYYY-MM-DD>` token is "
                      "the sanctioned channel; NOC-REMEDIATE markers are swept.\n",
            "help.py": 'HELP = "batch-sweep the NOC-REMEDIATE deferral markers"\n',
        })
        res = scan_remediation_markers(repo_root=r)
        assert res["total"] == 0, f"prose mentions must not count: {res}"
        assert res["exit_code"] == 0
        assert res["status"] == "clean"

    def test_on_except_is_forbidden(self, tmp_path):
        r = _repo(tmp_path, {
            "e.py": "try:\n    pass\n"
                    "except Exception:  # NOC-REMEDIATE[err]: handle it — 2026-05-13\n"
                    "    pass\n",
        })
        res = scan_remediation_markers(repo_root=r)
        assert len(res["on_except"]) == 1
        assert res["on_except"][0]["class"] == "err"
        assert res["exit_code"] == 1                   # marker-on-except is a defect

    def test_no_markers_is_clean(self, tmp_path):
        r = _repo(tmp_path, {"f.py": "x = 1\n"})
        res = scan_remediation_markers(repo_root=r)
        assert res["total"] == 0
        assert res["status"] == "clean"
        assert res["exit_code"] == 0
