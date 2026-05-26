"""Colocated regression test for the `check_files_outlined` keeper
(KB § PATTERNS/common/ast.md § Always-outline-able platform). Every keeper
check_* ships a colocated Test<CamelCase> per the meta-detector."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_files_outlined  # noqa: E402


class TestCheckFilesOutlined:
    def test_clean_python_file_is_outlineable(self, tmp_path):
        good = tmp_path / "good.py"
        good.write_text("def f(x):\n    return x + 1\n")
        assert check_files_outlined(paths=[good], repo_root=tmp_path) == []

    def test_syntax_error_python_is_flagged_high(self, tmp_path):
        bad = tmp_path / "bad.py"
        bad.write_text("def broken(:\n    return\n")  # SyntaxError
        issues = check_files_outlined(paths=[bad], repo_root=tmp_path)
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"
        assert issues[0]["file"] == "bad.py"
        assert "outline-able" in issues[0]["issue"]

    def test_mixed_set_reports_only_the_broken_one(self, tmp_path):
        (tmp_path / "ok.py").write_text("CONST = 1\n")
        (tmp_path / "broken.py").write_text("class C(\n")  # SyntaxError
        issues = check_files_outlined(
            paths=[tmp_path / "ok.py", tmp_path / "broken.py"],
            repo_root=tmp_path,
        )
        assert [i["file"] for i in issues] == ["broken.py"]

    def test_non_source_extensions_skipped(self, tmp_path):
        (tmp_path / "data.json").write_text("{ not valid python")
        (tmp_path / "notes.md").write_text("# not code")
        assert check_files_outlined(
            paths=[tmp_path / "data.json", tmp_path / "notes.md"],
            repo_root=tmp_path,
        ) == []

    def test_vendored_dirs_skipped_even_if_broken(self, tmp_path):
        nm = tmp_path / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "x.js").write_text("function (")  # broken but vendored
        assert check_files_outlined(
            paths=[nm / "x.js"], repo_root=tmp_path
        ) == []

    def test_typescript_clean_file_is_outlineable(self, tmp_path):
        ts = tmp_path / "ok.ts"
        ts.write_text("export const add = (a: number, b: number) => a + b;\n")
        assert check_files_outlined(paths=[ts], repo_root=tmp_path) == []
