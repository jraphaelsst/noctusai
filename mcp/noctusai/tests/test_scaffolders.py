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
        out = sk.scaffold_keeper("files_xyz", "xyz", mechanism="scaffold: noctus.dev.scaffold_x",
                                 owner="tooling-engineer", source="KB § PATTERNS/common/gate-methodology-sync.md")
        ast.parse(out["detector_code"])
        ast.parse(out["test_code"])
        assert "check_files_xyz" in out["detector_code"]
        assert "--check-xyz" in out["cli_argparse_line"]

    def test_refuses_without_construction_leg_owner_or_source(self):
        ok = dict(mechanism="scaffold: x", owner="o", source="s")
        for bad in ({**ok, "mechanism": ""}, {**ok, "mechanism": "we will remember"},
                    {**ok, "mechanism": "none (x)"}, {**ok, "owner": " "}, {**ok, "source": ""}):
            out = sk.scaffold_keeper("files_xyz", "xyz", **bad)
            assert out["ok"] is False and "required" in out["error"]

    def test_none_with_reason_is_accepted_and_emits_triad_declaration(self):
        out = sk.scaffold_keeper("files_xyz", "xyz", mechanism="none (an in-line choice, no construction possible)",
                                 owner="tooling-engineer", source="s")
        assert out["ok"] and out["gate_id"] == "keeper:check-xyz"
        assert "--gate-alignment declare" in out["declare_command"] and "--placement warn" in out["declare_command"]
        assert out["inventory_entry"]["new"] is True and "shadow" in out["precommit_block"]

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


class TestScaffoldNoctusDevTarget:
    """target='noctus.dev': libcst edits against COPIES of the real
    __init__.py / cli.py / toolkit_freshness.py in a temp tree."""

    @staticmethod
    def _tree(tmp_path):
        import shutil

        real = Path(__file__).resolve().parents[3]
        for rel in ("mcp/noctusai/tools/noctus/dev/__init__.py",
                    "mcp/noctusai/cli.py",
                    "mcp/noctusai/tools/noctus/dev/toolkit_freshness.py"):
            (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(real / rel, tmp_path / rel)
        return tmp_path

    def test_dry_run_is_default_and_writes_nothing(self, tmp_path):
        root = self._tree(tmp_path)
        before = (root / "mcp/noctusai/cli.py").read_text()
        out = smt.scaffold_mcp_tool(target="noctus.dev", name="demo_probe", kind="write",
                                    worktree_path=str(root))
        assert out["ok"] and out["status"] == "planned"
        ast.parse(out["module_code"]); ast.parse(out["test_code"])
        assert (root / "mcp/noctusai/cli.py").read_text() == before
        assert not (root / "mcp/noctusai/tools/noctus/dev/demo_probe.py").exists()

    def test_write_tool_wires_all_five_places(self, tmp_path):
        root = self._tree(tmp_path)
        out = smt.scaffold_mcp_tool(target="noctus.dev", name="demo_probe", kind="write",
                                    tree_dependent=True, worktree_path=str(root), confirm=True)
        assert out["ok"] and out["status"] == "scaffolded", out
        dev = root / "mcp/noctusai/tools/noctus/dev"
        mod = (dev / "demo_probe.py").read_text()
        assert "refuse_gate(\"demo_probe\")" in mod and "confirm: bool = False" in mod
        init = (dev / "__init__.py").read_text()
        assert "from . import demo_probe\n" in init and "demo_probe.register(server)" in init
        cli = (root / "mcp/noctusai/cli.py").read_text()
        for f in ("--demo-probe", "--demo-probe-confirm", "--demo-probe-allow-stale-toolkit"):
            assert f'"{f}"' in cli
        assert "elif args.demo_probe:" in cli
        fresh = (dev / "toolkit_freshness.py").read_text()
        assert '\n    "demo_probe": frozenset({"confirm", "worktree_path"}),\n}' in fresh
        assert 'tool_name == "demo_probe"' in fresh
        for f in (dev / "__init__.py", root / "mcp/noctusai/cli.py", dev / "toolkit_freshness.py",
                  dev / "demo_probe.py", root / "mcp/noctusai/tests/test_demo_probe.py"):
            ast.parse(f.read_text())

    def test_edits_are_pure_insertions(self, tmp_path):
        """libcst round-trips: the only diff vs the original is added lines."""
        root = self._tree(tmp_path)
        orig = (root / "mcp/noctusai/cli.py").read_text().splitlines()
        smt.scaffold_mcp_tool(target="noctus.dev", name="demo_probe", worktree_path=str(root), confirm=True)
        new = (root / "mcp/noctusai/cli.py").read_text().splitlines()
        import difflib

        removed = [l for l in difflib.unified_diff(orig, new, lineterm="", n=0)
                   if l.startswith("-") and not l.startswith("---")]
        assert removed == []

    def test_read_tool_skips_the_freshness_wiring(self, tmp_path):
        root = self._tree(tmp_path)
        fresh_before = (root / "mcp/noctusai/tools/noctus/dev/toolkit_freshness.py").read_text()
        out = smt.scaffold_mcp_tool(target="noctus.dev", name="demo_reader", kind="read",
                                    worktree_path=str(root), confirm=True)
        assert out["ok"], out
        assert (root / "mcp/noctusai/tools/noctus/dev/toolkit_freshness.py").read_text() == fresh_before
        assert "refuse_gate" not in (root / "mcp/noctusai/tools/noctus/dev/demo_reader.py").read_text()

    def test_rerun_refuses_and_duplicates_nothing(self, tmp_path):
        root = self._tree(tmp_path)
        kw = dict(target="noctus.dev", name="demo_probe", kind="write",
                  worktree_path=str(root), confirm=True)
        assert smt.scaffold_mcp_tool(**kw)["ok"]
        snap = {p: p.read_text() for p in root.rglob("*.py")}
        again = smt.scaffold_mcp_tool(**kw)
        assert again["ok"] is False and again["status"] == "refused_exists"
        assert {p: p.read_text() for p in root.rglob("*.py")} == snap

    def test_name_clash_in_cli_or_init_alone_is_refused_all_or_nothing(self, tmp_path):
        root = self._tree(tmp_path)
        out = smt.scaffold_mcp_tool(target="noctus.dev", name="verify_db_guards", worktree_path=str(root))
        assert out["ok"] is False
        # an already-registered name with no module file in this tree
        out = smt.scaffold_mcp_tool(target="noctus.dev", name="verify_db_guards",
                                    worktree_path=str(root), confirm=True)
        assert out["ok"] is False
        assert not (root / "mcp/noctusai/tools/noctus/dev/verify_db_guards.py").exists()

    def test_bad_inputs(self, tmp_path):
        assert smt.scaffold_mcp_tool(target="noctus.dev", name="Bad-Name")["ok"] is False
        assert smt.scaffold_mcp_tool(target="nope")["ok"] is False
        assert smt.scaffold_mcp_tool(target="connector")["ok"] is False  # needs vendor/service/action


def _rn(mod):
    cap = {}

    class _S:
        def tool(self, *, name, description):
            cap["n"] = name
            return lambda fn: fn

    mod.register(_S())
    return cap["n"]
