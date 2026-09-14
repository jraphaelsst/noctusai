"""Tests for `tools/noctus/dev/knowledge_bundle_export.py`.

Every git repo used here is a throwaway created under `tmp_path` — never
the real sibling repo, per the A2 brief's hard rule against real sibling
content in fixtures.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.knowledge_bundle_export import export_knowledge_bundle


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _write(repo: Path, rel_path: str, content: str) -> None:
    p = repo / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _init_repo(tmp_path: Path, name: str = "fake-sibling") -> Path:
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    return repo


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


class TestMultiCommitHistory:
    def test_exports_one_line_per_commit_touching_a_matching_path(self, tmp_path):
        repo = _init_repo(tmp_path)
        _write(repo, "KNOWLEDGE-BASE/GERAL/a.md", "# A\n\nversao 1")
        _commit(repo, "add a.md")
        _write(repo, "KNOWLEDGE-BASE/GERAL/a.md", "# A\n\nversao 2")
        _commit(repo, "update a.md")
        _write(
            repo,
            "projects/state/tasks.json",
            json.dumps([{"codigo": "T-001", "titulo": "X"}]),
        )
        _commit(repo, "add tasks.json")

        out_dir = tmp_path / "out"
        result = export_knowledge_bundle(str(repo), str(out_dir))

        assert result.ok is True
        assert result.lines == 3  # 2 revisions of a.md + 1 of tasks.json
        assert result.commits == 3
        assert set(result.paths) == {"KNOWLEDGE-BASE/GERAL/a.md", "projects/state/tasks.json"}

        bundle_path = Path(result.path)
        assert bundle_path.exists()
        rows = [json.loads(line) for line in bundle_path.read_text().splitlines()]
        assert len(rows) == 3
        a_rows = [r for r in rows if r["path"] == "KNOWLEDGE-BASE/GERAL/a.md"]
        assert [r["content"] for r in a_rows] == ["# A\n\nversao 1", "# A\n\nversao 2"]
        for row in rows:
            assert {"path", "git_sha", "git_author_raw", "git_committed_at", "git_message", "content"} <= row.keys()

    def test_report_shape_has_no_refused_paths_on_a_clean_export(self, tmp_path):
        repo = _init_repo(tmp_path)
        _write(repo, "docs/SPEC.md", "# Spec\n\nnada suspeito aqui")
        _commit(repo, "add spec")

        result = export_knowledge_bundle(str(repo), str(tmp_path / "out"))
        d = result.to_dict()
        assert d["ok"] is True
        assert d["refused_paths"] == []
        assert d["error"] is None


class TestOutDirRefusal:
    def test_refuses_out_dir_inside_repo_path(self, tmp_path):
        repo = _init_repo(tmp_path)
        _write(repo, "docs/SPEC.md", "# Spec\n\nconteudo")
        _commit(repo, "add spec")

        result = export_knowledge_bundle(str(repo), str(repo / "scratch"))

        assert result.ok is False
        assert result.error is not None
        assert result.path is None
        assert not (repo / "scratch").exists()

    def test_refuses_out_dir_equal_to_repo_path(self, tmp_path):
        repo = _init_repo(tmp_path)
        _write(repo, "docs/SPEC.md", "# Spec\n\nconteudo")
        _commit(repo, "add spec")

        result = export_knowledge_bundle(str(repo), str(repo))

        assert result.ok is False
        assert result.error is not None


class TestSecretRefusal:
    def test_refuses_and_reports_paths_on_a_planted_fake_secret(self, tmp_path):
        repo = _init_repo(tmp_path)
        _write(repo, "docs/SPEC.md", "# Spec\n\nconteudo normal")
        _commit(repo, "add spec")
        _write(
            repo,
            "KNOWLEDGE-BASE/GERAL/leak.md",
            "# Leak\n\ntoken: ghp_1234567890abcdefghijklmnopqrstuvwx",
        )
        _commit(repo, "oops committed a token")

        out_dir = tmp_path / "out"
        result = export_knowledge_bundle(str(repo), str(out_dir))

        assert result.ok is False
        assert "KNOWLEDGE-BASE/GERAL/leak.md" in result.refused_paths
        assert not out_dir.exists() or not (out_dir / "knowledge-bundle.jsonl").exists()

    def test_clean_paths_are_not_written_either_when_any_line_is_refused(self, tmp_path):
        repo = _init_repo(tmp_path)
        _write(repo, "docs/SPEC.md", "# Spec\n\nconteudo limpo")
        _commit(repo, "add clean spec")
        _write(
            repo,
            "KNOWLEDGE-BASE/GERAL/leak.md",
            "-----BEGIN RSA PRIVATE KEY-----\nMIIB...\n",
        )
        _commit(repo, "add a pem-shaped secret")

        out_dir = tmp_path / "out"
        result = export_knowledge_bundle(str(repo), str(out_dir))

        assert result.ok is False
        assert not (out_dir / "knowledge-bundle.jsonl").exists()


class TestGlobFiltering:
    def test_paths_outside_include_globs_are_excluded(self, tmp_path):
        repo = _init_repo(tmp_path)
        _write(repo, "KNOWLEDGE-BASE/GERAL/a.md", "# A\n\nconteudo")
        _write(repo, "notes/random.txt", "isto nao deveria entrar no bundle")
        _commit(repo, "add both files")

        result = export_knowledge_bundle(str(repo), str(tmp_path / "out"))

        assert result.ok is True
        assert result.paths == ["KNOWLEDGE-BASE/GERAL/a.md"]

    def test_custom_include_globs_narrow_the_export(self, tmp_path):
        repo = _init_repo(tmp_path)
        _write(repo, "KNOWLEDGE-BASE/GERAL/a.md", "# A\n\nconteudo")
        _write(repo, "docs/SPEC.md", "# Spec\n\nconteudo")
        _commit(repo, "add both files")

        result = export_knowledge_bundle(
            str(repo), str(tmp_path / "out"), include_globs=("docs/SPEC.md",)
        )

        assert result.ok is True
        assert result.paths == ["docs/SPEC.md"]
