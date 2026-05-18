"""Colocated tests for the codegen scaffolders. Quality gate: the
EMITTED code must compile (a codegen tool that emits broken code is
worse than none)."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import scaffold_keeper as sk  # noqa: E402
from tools.noctus.dev import scaffold_mcp_tool as smt  # noqa: E402
from tools.noctus.dev import scaffold_memory as sm  # noqa: E402
from tools.noctus.dev import scaffold_seed_adapter as ssa  # noqa: E402


class TestScaffoldMemory:
    def test_writes_entry_and_index_line(self, tmp_path):
        (tmp_path / "MEMORY.md").write_text(
            "# Mem\n\n## Feedback Rules\n\n### Foundational principles\n"
        )
        out = sm.scaffold_memory(
            "feedback_demo", "demo desc", "the body **Why:** x",
            mem_dir=str(tmp_path),
        )
        assert out["ok"] is True
        entry = (tmp_path / "feedback_demo.md").read_text()
        assert "name: feedback_demo" in entry and "type: feedback" in entry
        assert "feedback_demo.md)" in (tmp_path / "MEMORY.md").read_text()

    def test_refuses_clobber(self, tmp_path):
        (tmp_path / "x.md").write_text("exists")
        out = sm.scaffold_memory("x", "d", "b", mem_dir=str(tmp_path))
        assert out["ok"] is False and "already exists" in out["error"]

    def test_bad_type_rejected(self, tmp_path):
        out = sm.scaffold_memory("y", "d", "b", mtype="bogus", mem_dir=str(tmp_path))
        assert out["ok"] is False

    def test_registered(self):
        assert _rn(sm) == "noctus.dev.scaffold_memory"


class TestScaffoldMcpTool:
    def test_emitted_leaf_and_test_compile(self):
        out = smt.scaffold_mcp_tool("meta", "ads", "pause_campaign", kind="write")
        assert out["tool_name"] == "meta.ads.pause_campaign"
        ast.parse(out["leaf_code"])  # must be valid Python
        ast.parse(out["test_code"])
        assert "confirm" in out["leaf_code"]  # write ⇒ gate present

    def test_read_kind_has_no_confirm_gate(self):
        out = smt.scaffold_mcp_tool("google", "gmail", "list_labels", kind="read")
        ast.parse(out["leaf_code"])
        assert "WRITE GATE" not in out["leaf_code"]

    def test_registered(self):
        assert _rn(smt) == "noctus.dev.scaffold_mcp_tool"


class TestScaffoldKeeper:
    def test_emitted_detector_and_test_compile(self):
        out = sk.scaffold_keeper("files_xyz", "xyz")
        ast.parse(out["detector_code"])
        ast.parse(out["test_code"])
        assert "check_files_xyz" in out["detector_code"]
        assert "--check-xyz" in out["cli_argparse_line"]

    def test_registered(self):
        assert _rn(sk) == "noctus.dev.scaffold_keeper"


class TestScaffoldSeedAdapter:
    def test_six_files_all_compile(self):
        out = ssa.scaffold_seed_adapter("acme", methods=["fetch", "push"])
        files = out["files"]
        assert set(files) == {
            "types.py", "protocol.py", "fake.py", "real.py",
            "factory.py", "__init__.py",
        }
        for code in files.values():
            ast.parse(code)
        ast.parse(out["test_code"])
        assert "make_acme_client" in files["factory.py"]

    def test_registered(self):
        assert _rn(ssa) == "noctus.dev.scaffold_seed_adapter"


def _rn(mod):
    cap = {}

    class _S:
        def tool(self, *, name, description):
            cap["n"] = name
            return lambda fn: fn

    mod.register(_S())
    return cap["n"]
