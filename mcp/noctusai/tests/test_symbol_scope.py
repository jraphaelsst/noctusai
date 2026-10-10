"""symbol_scope — narrowing the toolkit gate from "every importer" to "the
tests naming what changed", and every guard that falls back instead.

Fully hermetic except `TestGateSweepEndToEnd`, which builds a throwaway git
repo under `tmp_path` (real `git`, no network)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.noctus.dev import gate_sweep as GS  # noqa: E402
from tools.noctus.dev import symbol_scope as SS  # noqa: E402

MOD = "tools.noctus.dev.big"

BIG = '''\
"""Module docstring naming check_beta, which is not a reference."""
import os

LIMIT = 3


def _helper(x):
    return x + LIMIT


def check_alpha():
    return _helper(1)


def check_beta():
    """Mentions check_alpha in prose only."""
    return 2


def check_gamma():
    return 3


def check_delta():
    return 4


def check_epsilon():
    return 5


def check_all():
    return [check_alpha(), check_beta(), check_gamma(), check_delta(), check_epsilon()]


@decorated
def check_decorated():
    return 6
'''


def _diff(old: str, new: str) -> str:
    """A real `git diff -U0` between two strings."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        a, b = Path(d) / "a.py", Path(d) / "b.py"
        a.write_text(old)
        b.write_text(new)
        r = subprocess.run(["git", "diff", "--no-index", "-U0", str(a), str(b)],
                           capture_output=True, text=True)
        return r.stdout


def _edit(old: str, before: str, after: str) -> tuple[str, str]:
    assert old.count(before) == 1
    new = old.replace(before, after)
    return new, _diff(old, new)


class TestChangedSymbols:
    def test_body_edit_names_its_def(self):
        new, diff = _edit(BIG, "    return 3\n", "    return 33\n")

        assert SS.changed_symbols(BIG, new, diff) == {"check_gamma"}

    def test_comment_and_blank_lines_change_nothing(self):
        new, diff = _edit(BIG, "LIMIT = 3\n", "LIMIT = 3\n# a note\n\n")

        assert SS.changed_symbols(BIG, new, diff) == set()

    def test_named_assignment_is_a_symbol(self):
        new, diff = _edit(BIG, "LIMIT = 3\n", "LIMIT = 4\n")

        assert SS.changed_symbols(BIG, new, diff) == {"LIMIT"}

    def test_import_edit_is_unattributable(self):
        new, diff = _edit(BIG, "import os\n", "import os\nimport re\n")

        assert SS.changed_symbols(BIG, new, diff) is None

    def test_decorator_edit_is_unattributable(self):
        new, diff = _edit(BIG, "@decorated\n", "@decorated(strict=True)\n")

        assert SS.changed_symbols(BIG, new, diff) is None

    def test_deleted_def_is_named_from_the_old_side(self):
        new, diff = _edit(BIG, "def check_delta():\n    return 4\n\n\n", "")

        assert SS.changed_symbols(BIG, new, diff) == {"check_delta"}

    def test_unparseable_side_is_unattributable(self):
        new, diff = _edit(BIG, "    return 3\n", "    return (\n")

        assert SS.changed_symbols(BIG, new, diff) is None


class TestModuleGraph:
    def test_closure_pulls_in_transitive_users(self):
        syms = SS._symbols(BIG)

        assert SS.closure({"LIMIT"}, syms) == {"LIMIT", "_helper", "check_alpha", "check_all"}

    def test_docstrings_are_not_references(self):
        syms = SS._symbols(BIG)

        assert "check_alpha" not in syms.refs["check_beta"]

    def test_registry_is_derived_from_public_fanout(self):
        assert SS.registry(SS._symbols(BIG)) == {"check_all"}

    def test_registry_reach_is_one_hop_and_skips_ambiguous_names(self):
        sources = {
            "a.py": "def runner():\n    return check_all()\n\ndef main():\n    check_all()\n",
            "b.py": "def main():\n    pass\n\ndef outer():\n    return runner()\n",
        }

        assert SS.registry_reach(sources, {"check_all"}) == {"check_all", "runner"}


class TestSelectInTest:
    def test_selects_only_nodes_naming_a_target(self):
        src = (
            "from tools.noctus.dev.big import check_alpha, check_beta\n"
            "class TestAlpha:\n    def test_a(self):\n        assert check_alpha()\n"
            "class TestBeta:\n    def test_b(self):\n        assert check_beta()\n"
        )

        sel, named = SS.select_in_test("t.py", src, MOD, {"check_alpha"}, set())

        assert sel == ["t.py::TestAlpha"] and named == {"check_alpha"}

    def test_fixture_naming_a_target_selects_the_tests_requesting_it(self):
        src = (
            "import pytest\n"
            "@pytest.fixture\ndef snap():\n    return check_all()\n"
            "def test_uses(snap):\n    assert snap\n"
            "def test_other():\n    assert True\n"
        )

        sel, _ = SS.select_in_test("t.py", src, MOD, set(), {"check_all"})

        assert sel == ["t.py::test_uses"]

    def test_module_level_statement_takes_the_whole_file(self):
        src = "VALUES = [check_alpha]\ndef test_x():\n    assert VALUES\n"

        sel, _ = SS.select_in_test("t.py", src, MOD, {"check_alpha"}, set())

        assert sel == ["t.py"]

    def test_reflection_over_the_module_takes_the_whole_file(self):
        src = (
            "from tools.noctus.dev import big\n"
            "def test_every_detector():\n"
            "    for name in dir(big):\n        assert name\n"
        )

        sel, _ = SS.select_in_test("t.py", src, MOD, {"check_alpha"}, set())

        assert sel == ["t.py"]

    def test_cli_flag_names_the_snake_case_symbol(self):
        src = "def test_cli():\n    run(['cli.py', '--check-alpha'])\n"

        sel, _ = SS.select_in_test("t.py", src, MOD, {"check_alpha"}, set())

        assert sel == ["t.py::test_cli"]

    def test_prose_in_a_string_is_not_a_reference(self):
        src = "def test_msg():\n    assert True, 'the keeper said so'\n"

        sel, _ = SS.select_in_test("t.py", src, MOD, {"keeper"}, set())

        assert sel == []


def _tests(n_extra: int = 9) -> dict[str, str]:
    files = {
        "tests/test_gamma.py": (
            f"from {MOD} import check_gamma\n"
            "def test_gamma():\n    assert check_gamma() == 3\n"
        ),
        "tests/test_fleet.py": (
            f"from {MOD} import check_all\n"
            "def test_fleet():\n    assert check_all()\n"
        ),
    }
    for i in range(n_extra):
        files[f"tests/test_other_{i}.py"] = (
            f"from {MOD} import check_delta\n"
            f"def test_d{i}():\n    assert check_delta() == 4\n"
        )
    return files


def _scope(files: dict[str, str], new: str, diff: str, kit: dict[str, str] | None = None):
    return SS.scope_module(files.__getitem__, MOD, sorted(files), BIG, new, diff, kit)


class TestScopeModule:
    def test_narrows_to_the_namer_plus_the_registry_runner(self):
        new, diff = _edit(BIG, "    return 3\n", "    return 33\n")

        assert _scope(_tests(), new, diff) == ["tests/test_fleet.py::test_fleet", "tests/test_gamma.py::test_gamma"]

    def test_a_test_reaching_the_registry_through_a_helper_module_is_always_selected(self):
        files = _tests()
        files["tests/test_snapshot.py"] = (
            f"import {MOD}\nfrom snap import fingerprints\n"
            "def test_fleet_clean():\n    assert fingerprints() == []\n"
        )
        kit = {"snap.py": "def fingerprints():\n    return check_all()\n"}
        new, diff = _edit(BIG, "    return 3\n", "    return 33\n")

        assert "tests/test_snapshot.py::test_fleet_clean" in _scope(files, new, diff, kit)

    def test_changed_symbol_no_test_names_falls_back(self):
        new, diff = _edit(BIG, "    return 2\n", "    return 22\n")  # check_beta: unnamed

        assert _scope(_tests(), new, diff) is None

    def test_unattributable_edit_falls_back(self):
        new, diff = _edit(BIG, "import os\n", "import os\nimport re\n")

        assert _scope(_tests(), new, diff) is None

    def test_a_no_op_diff_falls_back_rather_than_selecting_zero(self):
        new, diff = _edit(BIG, "LIMIT = 3\n", "LIMIT = 3\n# note\n")

        assert _scope(_tests(), new, diff) is None

    def test_small_modules_keep_import_scoping(self):
        new, diff = _edit(BIG, "    return 3\n", "    return 33\n")
        few = dict(list(_tests().items())[:SS.MIN_IMPORTING_TESTS - 1])

        assert _scope(few, new, diff) is None


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout


class TestGateSweepEndToEnd:
    """The real wiring: `gate_sweep` diffs the module against the merge-base
    and the mcp gate's argv carries node ids, not all eleven importers."""

    def _repo(self, tmp_path: Path) -> Path:
        pkg = tmp_path / "mcp/noctusai"
        (pkg / "tools/noctus/dev").mkdir(parents=True)
        (pkg / "tools/noctus/dev/big.py").write_text(BIG)
        for rel, src in _tests().items():
            (pkg / rel).parent.mkdir(parents=True, exist_ok=True)
            (pkg / rel).write_text(src)
        _git(tmp_path, "init", "-q", "-b", "dev")
        _git(tmp_path, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
        _git(tmp_path, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base")
        _git(tmp_path, "branch", "base")
        return tmp_path

    def _mcp_argv(self, root: Path) -> list[str]:
        seen: list[list[str]] = []

        def run_gate(spec):
            seen.append(list(spec.argv))
            return 0, "ok", 0.0

        GS.gate_sweep(base_ref="base", repo_root=str(root), run_gate=run_gate, allow_stale_tree=True)
        return next(a for a in seen if "pytest" in a and any("tests/test_" in x for x in a))

    def test_body_edit_runs_only_the_named_nodes(self, tmp_path):
        root = self._repo(tmp_path)
        big = root / "mcp/noctusai/tools/noctus/dev/big.py"
        big.write_text(BIG.replace("    return 3\n", "    return 33\n"))

        argv = self._mcp_argv(root)

        assert [a for a in argv if "tests/" in a] == [
            "mcp/noctusai/tests/test_fleet.py::test_fleet",
            "mcp/noctusai/tests/test_gamma.py::test_gamma",
        ]

    def test_import_edit_keeps_every_importer(self, tmp_path):
        root = self._repo(tmp_path)
        big = root / "mcp/noctusai/tools/noctus/dev/big.py"
        big.write_text(BIG.replace("import os\n", "import os\nimport re\n"))

        argv = self._mcp_argv(root)

        assert len([a for a in argv if "tests/" in a]) == 11
