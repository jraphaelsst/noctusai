"""Regression tests for the Stage-4 codification batch — `keeper-stage4-
codification-batch` Phase 1 (2026-05-11).

Covers six detectors promoting Stage-3 methodology rules to Stage-4
keeper detectors. Each detector gets a focused `Test<CamelCase>` class
with positive-fires + negative-doesn't-fire + at least one edge-case
test. Tests are file-system-scoped (`tmp_path` fixture) per the seed
test pattern; no monkey-patching of our own code.

Detectors covered:
  - `check_no_silent_ok_comment`
  - `check_auth_dep_anti_pattern`
  - `check_mcp_path_via_settings`
  - `check_mcp_write_tool_worktree_arg`
  - `check_pipefail_grep_q`
  - `check_doc_tool_reference_drift`

The seventh detector from the project doc (`check_no_self_monkeypatch`)
was already codified prior to this batch; its regression suite lives in
`test_compliance.py::TestCheckNoSelfMonkeypatch`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    check_auth_dep_anti_pattern,
    check_doc_tool_reference_drift,
    check_mcp_path_via_settings,
    check_mcp_write_tool_worktree_arg,
    check_no_silent_ok_comment,
    check_pipefail_grep_q,
)


# ---------------------------------------------------------------------------
# check_no_silent_ok_comment
# ---------------------------------------------------------------------------


class TestCheckNoSilentOkComment:
    """Literal `# silent-ok` in production code → warning."""

    def _mk_product_file(
        self, tmp_path: Path, py_content: str, *, filename: str = "service.py",
    ) -> Path:
        target = tmp_path / "products" / "p1" / "backend" / "app" / "services"
        target.mkdir(parents=True)
        (target / filename).write_text(py_content)
        return tmp_path

    def test_flags_silent_ok_in_production_py(self, tmp_path):
        content = (
            "import logging\n"
            "logger = logging.getLogger(__name__)\n\n"
            "def foo():\n"
            "    try:\n"
            "        do_thing()\n"
            "    except Exception:  # silent-ok: bootstrap\n"
            "        pass\n"
        )
        self._mk_product_file(tmp_path, content)
        issues = check_no_silent_ok_comment(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "warning"
        assert "silent-ok" in issues[0]["issue"]
        assert issues[0]["product"] == "p1"

    def test_does_not_flag_test_file_with_literal_in_docstring(self, tmp_path):
        """Tests directories MUST be excluded — they reference the literal
        in docstrings + assertion strings (this very file does)."""
        test_dir = tmp_path / "products" / "p1" / "backend" / "tests"
        test_dir.mkdir(parents=True)
        (test_dir / "test_x.py").write_text(
            '"""Pin the rule: no `# silent-ok` allowed."""\n'
            "def test_thing():\n"
            "    pass\n"
        )
        issues = check_no_silent_ok_comment(tmp_path)
        assert issues == [], f"tests/ must be excluded, got: {issues}"

    def test_flags_silent_ok_in_seed(self, tmp_path):
        """`seed/` is production code — must scan it too."""
        seed_dir = tmp_path / "seed" / "lib" / "backend"
        seed_dir.mkdir(parents=True)
        (seed_dir / "x.py").write_text(
            "try:\n    something()\nexcept Exception:  # silent-ok\n    pass\n"
        )
        issues = check_no_silent_ok_comment(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["product"] == "<root>"

    def test_flags_silent_ok_in_shell_script(self, tmp_path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "x.sh").write_text(
            "#!/usr/bin/env bash\n"
            "if ! command -v jq >/dev/null 2>&1; then\n"
            "  : # silent-ok: optional dep\n"
            "fi\n"
        )
        issues = check_no_silent_ok_comment(tmp_path)
        assert len(issues) == 1, issues
        assert "x.sh" in issues[0]["file"]

    def test_no_silent_ok_clean_repo_returns_empty(self, tmp_path):
        # No annotation anywhere — detector silent.
        self._mk_product_file(
            tmp_path,
            "def foo():\n    try:\n        do()\n    except Exception as exc:\n"
            "        import logging; logging.getLogger(__name__).warning('x: %s', exc)\n",
        )
        issues = check_no_silent_ok_comment(tmp_path)
        assert issues == [], issues

    def test_missing_scan_root_does_not_error(self, tmp_path):
        # Repo with no products/ / seed/ / mcp/ / scripts/ → silent.
        issues = check_no_silent_ok_comment(tmp_path)
        assert issues == []


# ---------------------------------------------------------------------------
# check_auth_dep_anti_pattern
# ---------------------------------------------------------------------------


class TestCheckAuthDepAntiPattern:
    """`Depends(ProductDependencies.get_org_id)` shape → warning."""

    def _mk_router_file(self, tmp_path: Path, py_content: str) -> Path:
        target = tmp_path / "products" / "p1" / "backend" / "app" / "routers"
        target.mkdir(parents=True)
        (target / "demo_router.py").write_text(py_content)
        return tmp_path

    def test_flags_depends_get_org_id(self, tmp_path):
        content = (
            "from fastapi import APIRouter, Depends\n"
            "from app.deps import ProductDependencies\n"
            "router = APIRouter()\n\n"
            "@router.get('/x')\n"
            "def x(org_id = Depends(ProductDependencies.get_org_id)):\n"
            "    return {}\n"
        )
        self._mk_router_file(tmp_path, content)
        issues = check_auth_dep_anti_pattern(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "warning"
        assert "get_org_id" in issues[0]["issue"]
        assert issues[0]["product"] == "p1"

    def test_flags_each_of_three_antipattern_attrs(self, tmp_path):
        content = (
            "from fastapi import APIRouter, Depends\n"
            "from app.deps import ProductDependencies\n"
            "router = APIRouter()\n\n"
            "@router.get('/a')\n"
            "def a(x = Depends(ProductDependencies.get_org_id)):\n"
            "    return {}\n"
            "@router.get('/b')\n"
            "def b(x = Depends(ProductDependencies.get_user_role)):\n"
            "    return {}\n"
            "@router.get('/c')\n"
            "def c(x = Depends(ProductDependencies.get_user_client)):\n"
            "    return {}\n"
        )
        self._mk_router_file(tmp_path, content)
        issues = check_auth_dep_anti_pattern(tmp_path)
        assert len(issues) == 3, issues
        attrs_flagged = {
            attr for issue in issues for attr in (
                "get_org_id", "get_user_role", "get_user_client",
            ) if attr in issue["issue"]
        }
        assert attrs_flagged == {"get_org_id", "get_user_role", "get_user_client"}

    def test_allows_canonical_depends_get_current_user_org(self, tmp_path):
        content = (
            "from fastapi import APIRouter, Depends\n"
            "from app.deps import get_current_user_org\n"
            "router = APIRouter()\n\n"
            "@router.get('/x')\n"
            "def x(user = Depends(get_current_user_org)):\n"
            "    return {}\n"
        )
        self._mk_router_file(tmp_path, content)
        issues = check_auth_dep_anti_pattern(tmp_path)
        assert issues == [], f"canonical wiring must not flag, got: {issues}"

    def test_allows_imperative_use_without_depends(self, tmp_path):
        # Calling `ProductDependencies.get_org_id(...)` directly (NOT inside
        # Depends) is permitted — only the Depends(...) wrapper is the trap.
        content = (
            "from app.deps import ProductDependencies\n"
            "def helper(user, token):\n"
            "    org = ProductDependencies.get_org_id(user, token)\n"
            "    return org\n"
        )
        self._mk_router_file(tmp_path, content)
        issues = check_auth_dep_anti_pattern(tmp_path)
        assert issues == [], f"imperative use must not flag, got: {issues}"

    def test_missing_router_dir_no_issues(self, tmp_path):
        # No products/ at all → silent.
        issues = check_auth_dep_anti_pattern(tmp_path)
        assert issues == []


# ---------------------------------------------------------------------------
# check_mcp_path_via_settings
# ---------------------------------------------------------------------------


class TestCheckMcpPathViaSettings:
    """`Path(__file__).parents[N]` in MCP tools → warning."""

    def _mk_mcp_tool(
        self, tmp_path: Path, py_content: str, *, filename: str = "x.py",
    ) -> Path:
        target = tmp_path / "mcp" / "noctusai" / "tools" / "noctus" / "dev"
        target.mkdir(parents=True)
        (target / filename).write_text(py_content)
        return tmp_path

    def test_flags_parents_subscript(self, tmp_path):
        content = (
            "from pathlib import Path\n\n"
            "REPO_ROOT = Path(__file__).parents[4]\n"
        )
        self._mk_mcp_tool(tmp_path, content)
        issues = check_mcp_path_via_settings(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "warning"
        assert "parents[N]" in issues[0]["issue"]
        assert issues[0]["product"] == "<mcp>"

    def test_flags_each_occurrence_separately(self, tmp_path):
        content = (
            "from pathlib import Path\n\n"
            "ROOT = Path(__file__).parents[4]\n"
            "PRODUCTS = Path(__file__).parents[4] / 'products'\n"
        )
        self._mk_mcp_tool(tmp_path, content)
        issues = check_mcp_path_via_settings(tmp_path)
        assert len(issues) == 2, issues

    def test_allows_settings_import(self, tmp_path):
        content = (
            "from settings import REPO_ROOT, PRODUCTS_DIR\n\n"
            "def tool():\n"
            "    return REPO_ROOT / 'x'\n"
        )
        self._mk_mcp_tool(tmp_path, content)
        issues = check_mcp_path_via_settings(tmp_path)
        assert issues == [], f"settings import must not flag, got: {issues}"

    def test_does_not_flag_path_parent_singular(self, tmp_path):
        # `Path(__file__).parent` (singular, no subscript) is not the
        # anti-pattern — `parents[N]` is. Singular form is common in
        # __file__-relative test setup and is fine.
        content = (
            "from pathlib import Path\n\n"
            "HERE = Path(__file__).parent\n"
        )
        self._mk_mcp_tool(tmp_path, content)
        issues = check_mcp_path_via_settings(tmp_path)
        assert issues == [], f"`.parent` must not flag, got: {issues}"

    def test_missing_mcp_tools_dir_no_issues(self, tmp_path):
        # No `mcp/noctusai/tools/` → silent.
        issues = check_mcp_path_via_settings(tmp_path)
        assert issues == []


# ---------------------------------------------------------------------------
# check_mcp_write_tool_worktree_arg
# ---------------------------------------------------------------------------


class TestCheckMcpWriteToolWorktreeArg:
    """MCP write-tool def missing `worktree_path: str` arg → warning."""

    def _mk_mcp_tool(
        self, tmp_path: Path, py_content: str, *, filename: str = "x.py",
    ) -> Path:
        target = tmp_path / "mcp" / "noctusai" / "tools" / "noctus" / "dev"
        target.mkdir(parents=True)
        (target / filename).write_text(py_content)
        return tmp_path

    def test_flags_archive_without_worktree_path(self, tmp_path):
        content = (
            "def archive(target_path: str) -> dict:\n"
            "    return {}\n"
        )
        self._mk_mcp_tool(tmp_path, content)
        issues = check_mcp_write_tool_worktree_arg(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "warning"
        assert "archive" in issues[0]["issue"]
        assert issues[0]["product"] == "<mcp>"

    def test_flags_scaffold_without_worktree_path(self, tmp_path):
        content = (
            "def scaffold_product(slug: str) -> dict:\n"
            "    return {}\n"
        )
        self._mk_mcp_tool(tmp_path, content)
        issues = check_mcp_write_tool_worktree_arg(tmp_path)
        assert len(issues) == 1, issues
        assert "scaffold_product" in issues[0]["issue"]

    def test_allows_write_tool_with_worktree_path(self, tmp_path):
        content = (
            "def archive(target_path: str, worktree_path: str | None = None) -> dict:\n"
            "    return {}\n"
        )
        self._mk_mcp_tool(tmp_path, content)
        issues = check_mcp_write_tool_worktree_arg(tmp_path)
        assert issues == [], f"with worktree_path must not flag, got: {issues}"

    def test_does_not_flag_read_tool(self, tmp_path):
        # `list_proposals` / `get_X` / `status` etc. are read-side; the verb
        # heuristic shouldn't catch them.
        content = (
            "def list_proposals() -> list:\n"
            "    return []\n"
            "def get_product(slug: str) -> dict:\n"
            "    return {}\n"
            "def status() -> dict:\n"
            "    return {}\n"
        )
        self._mk_mcp_tool(tmp_path, content)
        issues = check_mcp_write_tool_worktree_arg(tmp_path)
        assert issues == [], f"read tools must not flag, got: {issues}"

    def test_allows_async_write_tool_with_worktree_path(self, tmp_path):
        # `async def` write tools also covered.
        content = (
            "async def absorb_file(path: str, worktree_path: str | None = None) -> dict:\n"
            "    return {}\n"
        )
        self._mk_mcp_tool(tmp_path, content)
        issues = check_mcp_write_tool_worktree_arg(tmp_path)
        assert issues == [], f"async with worktree_path must not flag, got: {issues}"


# ---------------------------------------------------------------------------
# check_pipefail_grep_q
# ---------------------------------------------------------------------------


class TestCheckPipefailGrepQ:
    """`cmd | grep -q ...` under `set -o pipefail` → warning."""

    def _mk_script(self, tmp_path: Path, content: str, *, name: str = "x.sh") -> Path:
        scripts = tmp_path / "scripts"
        scripts.mkdir(exist_ok=True)
        (scripts / name).write_text(content)
        return tmp_path

    def test_flags_pipefail_with_grep_q(self, tmp_path):
        content = (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'if echo "hello" | grep -q "ell"; then\n'
            "  echo ok\n"
            "fi\n"
        )
        self._mk_script(tmp_path, content)
        issues = check_pipefail_grep_q(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "warning"
        assert "SIGPIPE" in issues[0]["issue"] or "141" in issues[0]["issue"]
        assert issues[0]["product"] == "<scripts>"

    def test_does_not_flag_without_pipefail(self, tmp_path):
        # No `set -o pipefail` → the footgun doesn't fire → no finding.
        content = (
            "#!/usr/bin/env bash\n"
            "set -eu\n"
            'echo "x" | grep -q "x" && echo found\n'
        )
        self._mk_script(tmp_path, content)
        issues = check_pipefail_grep_q(tmp_path)
        assert issues == [], f"no pipefail must not flag, got: {issues}"

    def test_does_not_flag_grep_q_in_comment(self, tmp_path):
        # An example inside a comment must NOT fire — the script doesn't
        # actually execute the antipattern.
        content = (
            "#!/usr/bin/env bash\n"
            "set -o pipefail\n"
            '# Antipattern example: echo "x" | grep -q "y"\n'
            'echo "x" | grep "y"  # safe (no -q)\n'
        )
        self._mk_script(tmp_path, content)
        issues = check_pipefail_grep_q(tmp_path)
        assert issues == [], f"comment-line example must not flag, got: {issues}"

    def test_flags_each_occurrence(self, tmp_path):
        # Same-file co-occurrence; each `| grep -q` line gets a finding.
        content = (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'echo "a" | grep -q "a"\n'
            'echo "b" | grep -q "b"\n'
        )
        self._mk_script(tmp_path, content)
        issues = check_pipefail_grep_q(tmp_path)
        assert len(issues) == 2, issues

    def test_missing_scripts_dir_no_issues(self, tmp_path):
        issues = check_pipefail_grep_q(tmp_path)
        assert issues == []


# ---------------------------------------------------------------------------
# check_doc_tool_reference_drift
# ---------------------------------------------------------------------------


class TestCheckDocToolReferenceDrift:
    """KB doc references `bash scripts/<name>.sh <mode>` that mismatch the
    script's recognized modes → warning."""

    def _mk_doc_and_script(
        self, tmp_path: Path, *, doc_body: str, scripts: dict[str, str],
    ) -> Path:
        # Build the doc surface in scope: methodology-codification-pipeline.md.
        doc_dir = tmp_path / "KNOWLEDGE-BASE" / "CONTEXT" / "PATTERNS"
        doc_dir.mkdir(parents=True)
        (doc_dir / "methodology-codification-pipeline.md").write_text(doc_body)
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        for name, body in scripts.items():
            (scripts_dir / name).write_text(body)
        return tmp_path

    def test_flags_doc_mode_missing_from_script(self, tmp_path):
        # Doc says `bash scripts/x.sh deprecated_mode` but script body only
        # mentions `scan` / `sweep`.
        self._mk_doc_and_script(
            tmp_path,
            doc_body=(
                "| symptom | tool | invocation |\n"
                "|---|---|---|\n"
                "| stale | x.sh | `bash scripts/x.sh deprecated_mode` |\n"
            ),
            scripts={
                "x.sh": "#!/usr/bin/env bash\ncase $1 in scan) ;; sweep) ;; esac\n",
            },
        )
        issues = check_doc_tool_reference_drift(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "warning"
        assert "deprecated_mode" in issues[0]["issue"]
        assert issues[0]["product"] == "<docs>"

    def test_allows_doc_mode_present_in_script(self, tmp_path):
        self._mk_doc_and_script(
            tmp_path,
            doc_body=(
                "Run `bash scripts/x.sh scan` to detect.\n"
            ),
            scripts={
                "x.sh": "#!/usr/bin/env bash\ncase $1 in scan) ;; sweep) ;; esac\n",
            },
        )
        issues = check_doc_tool_reference_drift(tmp_path)
        assert issues == [], f"valid mode must not flag, got: {issues}"

    def test_flags_doc_referencing_missing_script(self, tmp_path):
        # Doc says `bash scripts/gone.sh scan` but `gone.sh` doesn't exist.
        self._mk_doc_and_script(
            tmp_path,
            doc_body="Run `bash scripts/gone.sh scan` to detect.\n",
            scripts={},
        )
        issues = check_doc_tool_reference_drift(tmp_path)
        assert len(issues) == 1, issues
        assert "does not exist" in issues[0]["issue"]
        assert "gone.sh" in issues[0]["issue"]

    def test_word_boundary_match_does_not_partial(self, tmp_path):
        # Mode `scan` should NOT be satisfied by `scanner` in the script.
        # Script body mentions `scanner` only; doc references `scan` mode.
        self._mk_doc_and_script(
            tmp_path,
            doc_body="Run `bash scripts/x.sh scan` to detect.\n",
            scripts={
                "x.sh": "#!/usr/bin/env bash\n# uses a scanner internally\n",
            },
        )
        issues = check_doc_tool_reference_drift(tmp_path)
        assert len(issues) == 1, issues
        assert "scan" in issues[0]["issue"]

    def test_missing_doc_no_issues(self, tmp_path):
        # If the scoped doc doesn't exist, the detector is silent (no false
        # positives on fresh checkouts).
        issues = check_doc_tool_reference_drift(tmp_path)
        assert issues == []
