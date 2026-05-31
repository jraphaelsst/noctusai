"""Regression test for `check_commands_listed_in_router` (eight-way-sync §2).

Contract: every `.claude/commands/<name>.md` on disk MUST be referenced in
CLAUDE.md, AND every `/command` in the §2 'Slash commands' line MUST exist on
disk (both legs `high`). Silent when CLAUDE.md or .claude/commands/ is absent.

Provenance: surfaced as the ONE genuinely-untested detector (vs 9 tested-but-
unrecognized) by the MCP toolkit suite's first CI-gate pass, 2026-05-31 — the
gap that let a detector ship without a test for as long as the suite ran
ungated. KB § PATTERNS/common/eight-way-sync.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_commands_listed_in_router  # noqa: E402

_SECTION = "## 2\n**Slash commands** (`.claude/commands/`): {body}.\n"


def _mk(repo: Path, *, body: str, commands: list[str]) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "CLAUDE.md").write_text(_SECTION.format(body=body), encoding="utf-8")
    cmd_dir = repo / ".claude" / "commands"
    cmd_dir.mkdir(parents=True, exist_ok=True)
    for name in commands:
        (cmd_dir / f"{name}.md").write_text(f"# /{name}\n", encoding="utf-8")


class TestCheckCommandsListedInRouter:
    def test_clean_when_command_referenced(self, tmp_path):
        _mk(tmp_path, body="`/foo`", commands=["foo"])
        assert check_commands_listed_in_router(repo_root=tmp_path) == []

    def test_flags_command_on_disk_not_in_router(self, tmp_path):
        # `orphan.md` exists but the router never mentions it (leg a).
        _mk(tmp_path, body="`/foo`", commands=["foo", "orphan"])
        issues = check_commands_listed_in_router(repo_root=tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "high"
        assert "orphan" in issues[0]["file"]
        assert issues[0]["symbol"] == "command-orphan-on-disk"

    def test_flags_router_command_not_on_disk(self, tmp_path):
        # §2 references `/ghost` but no ghost.md on disk (leg b).
        _mk(tmp_path, body="`/foo` · `/ghost`", commands=["foo"])
        issues = check_commands_listed_in_router(repo_root=tmp_path)
        assert any(
            "ghost" in (i.get("file", "") + i.get("issue", "")) for i in issues
        ), issues
        assert all(i["severity"] == "high" for i in issues)

    def test_silent_without_claude_md(self, tmp_path):
        cmd_dir = tmp_path / ".claude" / "commands"
        cmd_dir.mkdir(parents=True)
        (cmd_dir / "foo.md").write_text("# /foo\n", encoding="utf-8")
        assert check_commands_listed_in_router(repo_root=tmp_path) == []

    def test_silent_without_commands_dir(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("no commands here\n", encoding="utf-8")
        assert check_commands_listed_in_router(repo_root=tmp_path) == []
