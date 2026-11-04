"""heavy_run_guard: deny ungated heavy runs; allow wrapped / benign / escaped ones."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TOOL = REPO / "mcp/noctusai/tools/noctus/dev/heavy_run_guard.py"
HOOK = REPO / "scripts/hooks/claude-guard-heavy-run.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


guard = _load("hrg_under_test", TOOL)


def _bash(cmd: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


@pytest.fixture(autouse=True)
def _no_ambient_escape(monkeypatch):
    monkeypatch.delenv(guard.ESCAPE_ENV, raising=False)


DENY = [
    "pytest",
    "pytest -q mcp/noctusai/tests/test_x.py",
    "venv/bin/python -m pytest -q products/erp/backend/tests",
    "python3 -m pytest",
    "cd products/erp/backend && pytest -q",
    "cd x; pytest",
    "make && (pytest -q)",
    "echo hi | pytest",
    "npx vitest run src/a.test.ts",
    "vitest",
    "cd products/erp/frontend && npm test",
    "npm run test",
    "npm run build",
    "pnpm run build:prod",
    "npx playwright test",
    "playwright test e2e/a.spec.ts",
    "npx vite build",
    "vite build",
    "bash -c 'cd x && pytest -q'",
    "NOC_HW_UNGATED_OK= pytest",
    "FOO=1 pytest",
    "time pytest",
]

ALLOW = [
    "python mcp/noctusai/tools/noctus/dev/hw_admission.py run --job pytest:x -- venv/bin/python -m pytest -q x",
    "cd x && python mcp/noctusai/tools/noctus/dev/hw_admission.py run --job vitest:erp -- npx vitest run",
    "pytest --collect-only -q",
    "pytest --version",
    "npx vitest --help",
    "npm run build --help",
    "grep pytest file.txt",
    'echo "pytest"',
    "cat pytest.ini",
    "git commit -m 'run pytest and vite build'",
    "ls products",
    "NOC_HW_UNGATED_OK='trial harness itself' pytest -q",
    "",
]


@pytest.mark.parametrize("cmd", DENY)
def test_denies(cmd):
    verdict = guard.decide(_bash(cmd))
    assert verdict and "hw_admission.py run --job" in verdict["reason"]
    assert "hardware-admission-budget.md" in verdict["reason"]


@pytest.mark.parametrize("cmd", ALLOW)
def test_allows(cmd):
    assert guard.decide(_bash(cmd)) is None


def test_non_bash_tool_ignored():
    assert guard.decide({"tool_name": "Edit", "tool_input": {"command": "pytest"}}) is None


def test_escape_is_recorded(capsys):
    assert guard.decide(_bash("NOC_HW_UNGATED_OK=because pytest -q")) is None
    assert "because" in capsys.readouterr().err


def test_hook_env_escape(monkeypatch):
    monkeypatch.setenv(guard.ESCAPE_ENV, "ci box")
    assert guard.decide(_bash("pytest")) is None


def test_suggested_job_and_wrapped_command():
    r = guard.decide(_bash("cd products/erp/frontend && npx vitest run"))["reason"]
    assert "--job vitest:erp -- npx vitest run" in r
    r = guard.decide(_bash("pytest -q mcp/noctusai/tests/test_a.py"))["reason"]
    assert "--job pytest:tests -- pytest -q mcp/noctusai/tests/test_a.py" in r


def test_unparseable_with_heavy_word_denies():
    assert guard.decide(_bash("pytest 'unterminated"))


def test_hook_wrapper_denies_and_allows():
    hook = _load("hrg_hook_under_test", HOOK)
    out = io.StringIO()
    assert hook.run_guard("heavy-run", hook._judge, stdin=io.StringIO(json.dumps(_bash("pytest"))), stdout=out) == 0
    assert "[noc-guard:heavy-run]" in out.getvalue() and "deny" in out.getvalue()
    out = io.StringIO()
    hook.run_guard("heavy-run", hook._judge, stdin=io.StringIO(json.dumps(_bash("ls"))), stdout=out)
    assert out.getvalue() == ""


def test_hook_wrapper_fails_closed_on_bad_stdin_and_crash(monkeypatch):
    hook = _load("hrg_hook_failclosed", HOOK)
    out = io.StringIO()
    hook.run_guard("heavy-run", hook._judge, stdin=io.StringIO("not json"), stdout=out)
    assert "deny" in out.getvalue()

    def boom(_payload):
        raise RuntimeError("x")

    out = io.StringIO()
    hook.run_guard("heavy-run", boom, stdin=io.StringIO(json.dumps(_bash("ls"))), stdout=out)
    assert "deny" in out.getvalue() and "[noc-guard:heavy-run]" in out.getvalue()
