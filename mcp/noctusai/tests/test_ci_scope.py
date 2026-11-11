"""ci_scope: the ONE path classifier CI's `changes` job and deliverable item 5 share (2026-11-10).

The cases are the behaviours the workflow's inline bash had (ledger-only skips, harness mods, shared roots run
every product, otherwise the touched slugs), plus a pin that the workflow calls this module and no longer carries
its own copy of the rules.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import ci_scope as cs  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
MODULE = REPO / "mcp/noctusai/tools/noctus/dev/ci_scope.py"


@pytest.mark.parametrize("paths,heavy,harness,shared,products", [
    (["project-history/branch-tree.ndjson"], False, False, False, ()),
    ([], False, False, False, ()),
    (["products/core/backend/migrations/119_x.sql", "project-history/x.ndjson"], True, False, False, ("core",)),
    (["products/social-wiring/frontend/a.tsx", "products/agents/backend/b.py"], True, False, False,
     ("agents", "social-wiring")),
    (["seed/framework/x.py", "products/core/a.py"], True, False, True, ()),
    (["requirements-dev.txt"], True, False, True, ()),
    ([".github/workflows/test.yml"], True, False, True, ()),
    (["deploy/fleet/active-scope.txt"], True, False, True, ()),
    ([".claude/mods/panel/x.js"], True, True, False, ()),
    ([".claude/settings.json", "products/igig/a.py"], True, True, False, ("igig",)),
    (["mcp/noctusai/cli.py"], True, False, False, ()),  # toolkit-only: heavy (toolkit/seed suites), no product
])
def test_classify(paths, heavy, harness, shared, products):
    s = cs.classify(paths)
    assert (s.run_heavy, s.harness_changed, s.shared_changed, s.changed_products) == (heavy, harness, shared, products)


def test_product_selection_follows_the_scope():
    assert cs.classify(["products/core/a.py"]).product_selected("core")
    assert not cs.classify(["products/core/a.py"]).product_selected("agents")
    assert cs.classify(["requirements.txt"]).product_selected("agents")
    assert not cs.classify(["project-history/a.ndjson"]).product_selected("core")
    assert cs.FULL.product_selected("anything")


def test_the_cli_prints_the_github_output_lines_the_workflow_appends():
    r = subprocess.run([sys.executable, str(MODULE)], input="products/core/a.py\nproducts/agents/b.py\n",
                       capture_output=True, text=True, timeout=30, check=True)
    assert r.stdout.splitlines() == ["run_heavy=true", "harness_changed=false", "shared_changed=false",
                                     "changed_products=,agents,core,"]
    assert "changed products: agents,core" in r.stderr


def test_the_module_is_stdlib_only_so_a_bare_python3_runs_it():
    import ast
    tree = ast.parse(MODULE.read_text())
    mods = {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} \
        | {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert mods <= set(sys.stdlib_module_names) | {"__future__"}, mods


def test_the_workflow_classifies_through_this_module_and_keeps_no_copy_of_the_rules():
    wf = (REPO / ".github/workflows/test.yml").read_text()
    changes = wf[wf.index("\n  changes:\n"):wf.index("\n  product-backend-tests:\n")]
    assert "mcp/noctusai/tools/noctus/dev/ci_scope.py" in changes
    for rule in ("project-history/.*\\.ndjson", "\\.claude/mods/", "scripts/ci/", "s#^products/"):
        assert rule not in changes, f"the changes job carries its own copy of a ci_scope rule: {rule}"
