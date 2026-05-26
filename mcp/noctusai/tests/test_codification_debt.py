"""Tests for check_codification_debt + markers_of_class.

The keeper is the always-on compliance-gate form of the /codify command's
*detection* half (KB § PATTERNS/common/methodology-codification-pipeline.md). It reads
``NOC-REMEDIATE[codify]`` markers so a deferred codification can never go silent
in prose. Real git repos + real ``git grep`` (no monkey-patch of our own code) so
the parse/classify path exercises the actual plumbing.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_codification_debt
from tools.noctus.dev.scan_remediation_markers import markers_of_class


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


class TestCodificationDebt:
    def test_wellformed_codify_marker_is_warning(self, tmp_path):
        r = _repo(tmp_path, {
            "KNOWLEDGE-BASE/x.md":
                "<!-- NOC-REMEDIATE[codify]: build check_foo keeper (N=3) — 2026-05-01 -->\n",
        })
        out = check_codification_debt(repo_root=r)
        assert len(out) == 1
        assert out[0]["severity"] == "warning"
        assert out[0]["product"] == "<methodology>"
        assert "Deferred codification pending" in out[0]["issue"]

    def test_malformed_codify_marker_missing_date_is_high(self, tmp_path):
        r = _repo(tmp_path, {
            "a.py": "# NOC-REMEDIATE[codify]: build check_foo (no date)\n",
        })
        out = check_codification_debt(repo_root=r)
        assert len(out) == 1
        assert out[0]["severity"] == "high"
        assert "missing" in out[0]["issue"]

    def test_on_except_codify_marker_is_high(self, tmp_path):
        r = _repo(tmp_path, {
            "b.py": "try:\n    pass\n"
                    "except Exception:  # NOC-REMEDIATE[codify]: codify this — 2026-05-02\n"
                    "    pass\n",
        })
        out = check_codification_debt(repo_root=r)
        assert any(i["severity"] == "high" and "except" in i["issue"] for i in out)

    def test_backlog_at_three_adds_extra_warning(self, tmp_path):
        lines = "".join(
            f"<!-- NOC-REMEDIATE[codify]: keeper {i} — 2026-05-0{i} -->\n" for i in range(1, 4)
        )
        r = _repo(tmp_path, {"KNOWLEDGE-BASE/y.md": lines})
        out = check_codification_debt(repo_root=r)
        # 3 per-marker warnings + 1 backlog warning.
        assert len(out) == 4
        assert sum(1 for i in out if i["file"] == "<codify-backlog>") == 1
        assert all(i["severity"] == "warning" for i in out)

    def test_no_codify_markers_is_empty(self, tmp_path):
        r = _repo(tmp_path, {"f.py": "x = 1\n"})
        assert check_codification_debt(repo_root=r) == []

    def test_only_codify_class_counted(self, tmp_path):
        """A [perf] marker must not register as codify debt — class-scoped."""
        r = _repo(tmp_path, {
            "c.py": "# NOC-REMEDIATE[perf]: memoize this — 2026-05-03\n",
        })
        assert check_codification_debt(repo_root=r) == []

    def test_defining_doc_codify_example_not_flagged(self, tmp_path):
        """A concrete [codify] example inside the docs that DEFINE the convention
        (codify.md / remediation-markers.md / the pipeline meta-doc) is
        self-reference — never counted (the placeholder-exclusion lesson)."""
        marker = "leave a `NOC-REMEDIATE[codify]: <rule> — 2026-05-04` marker\n"
        r = _repo(tmp_path, {
            ".claude/commands/codify.md": marker,
            "KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/remediation-markers.md": marker,
            "KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/methodology-codification-pipeline.md": marker,
        })
        assert check_codification_debt(repo_root=r) == []


class TestMarkersOfClass:
    def test_filters_to_class(self, tmp_path):
        r = _repo(tmp_path, {
            "a.py": "# NOC-REMEDIATE[codify]: one — 2026-05-01\n"
                    "# NOC-REMEDIATE[codify]: two — 2026-05-02\n"
                    "# NOC-REMEDIATE[perf]: three — 2026-05-03\n",
        })
        assert len(markers_of_class(r, "codify")) == 2
        assert all(m["class"] == "codify" for m in markers_of_class(r, "codify"))

    def test_empty_class_returns_all(self, tmp_path):
        r = _repo(tmp_path, {
            "a.py": "# NOC-REMEDIATE[codify]: one — 2026-05-01\n"
                    "# NOC-REMEDIATE[perf]: two — 2026-05-02\n",
        })
        assert len(markers_of_class(r, "")) == 2
