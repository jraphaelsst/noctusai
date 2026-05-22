"""Regression for settings.resolve_test_python() — the shared interpreter resolver.

Root of an N=2 bug (deploy-hardening, 2026-05-22): both
`noctus.dev.predeploy_check` (P5 gate, predeploy_check.py) and
`noctus.dev.pytest` (testing.py) shelled out to a bare ``"python"``, which on
a dev box resolves to a system interpreter WITHOUT pytest — a false *block*
in the P5 gate and a false *green* in the test runner. The resolver MUST hand
back an interpreter that can actually import pytest.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from settings import REPO_ROOT, resolve_test_python  # noqa: E402


def test_resolves_to_an_existing_interpreter():
    p = resolve_test_python()
    assert Path(p).exists(), f"resolve_test_python() returned a non-existent path: {p}"


def test_resolved_interpreter_can_import_pytest():
    """The behavioral contract: whatever we hand the test runners can run
    pytest. This is the exact regression — bare 'python' could not."""
    p = resolve_test_python()
    r = subprocess.run([p, "-c", "import pytest"], capture_output=True, text=True)
    assert r.returncode == 0, f"resolved interpreter lacks pytest: {p}\n{r.stderr}"


def test_prefers_repo_root_venv_else_current_interpreter():
    """Documents the resolution order: the repo-root venv (full noc stack)
    when present, else the running interpreter — never bare 'python'."""
    venv_py = REPO_ROOT / "venv" / "bin" / "python"
    expected = str(venv_py) if venv_py.exists() else sys.executable
    assert resolve_test_python() == expected
