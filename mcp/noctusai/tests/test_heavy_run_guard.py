"""heavy_run_guard: REWRITE ungated heavy runs through the gate; allow wrapped / benign / escaped ones;
still refuse local whisper and unparseable commands."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import shlex
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TOOL = REPO / "mcp/noctusai/tools/noctus/dev/heavy_run_guard.py"
HOOK = REPO / "scripts/hooks/claude-guard-bash-rewrite.py"


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


def _rewrite(cmd: str) -> dict:
    """The REWRITE verdict for `cmd`; asserts it is a rewrite, not a refusal."""
    verdict = guard.decide(_bash(cmd))
    assert verdict and verdict.get("decision") == "allow", verdict
    assert "reason" not in verdict
    return verdict


@pytest.mark.parametrize("cmd", DENY)
def test_heavy_run_is_rewritten_not_denied(cmd):
    verdict = _rewrite(cmd)
    new = verdict["updated_input"]["command"]
    assert "hw_admission.py run --job" in new and "--wait-s 7200 -- bash -c " in new
    assert shlex.split(new)[-1] == cmd  # the original command is ONE intact bash -c argument
    assert "REWROTE" in verdict["context"] and "hardware-admission-budget.md" in verdict["context"]
    # the rewritten command is what the guard itself accepts (no second wrap)
    assert guard.decide(_bash(new)) is None


def test_rewrite_uses_absolute_python_and_gate_path():
    new = _rewrite("pytest -q x")["updated_input"]["command"]
    py, gate = shlex.split(new)[:2]
    assert os.path.isabs(py) and os.path.isabs(gate) and gate.endswith("hw_admission.py")


def test_rewrite_keeps_other_tool_input_fields():
    verdict = guard.decide({"tool_name": "Bash", "tool_input": {"command": "pytest", "timeout": 5000,
                                                                "run_in_background": True}})
    assert verdict["updated_input"]["timeout"] == 5000 and verdict["updated_input"]["run_in_background"] is True


def test_rewrite_quotes_awkward_commands_round_trip():
    cmd = "cd 'a b' && pytest -q -k \"x and 'y'\" $HOME `echo z`"
    assert shlex.split(_rewrite(cmd)["updated_input"]["command"])[-1] == cmd


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
    r = _rewrite("cd products/erp/frontend && npx vitest run")["updated_input"]["command"]
    assert "--job vitest:erp " in r
    r = _rewrite("pytest -q mcp/noctusai/tests/test_a.py")["updated_input"]["command"]
    assert "--job pytest:tests " in r


def test_unparseable_with_heavy_word_still_denies():
    verdict = guard.decide(_bash("pytest 'unterminated"))
    assert verdict and "reason" in verdict and "updated_input" not in verdict


def test_hook_wrapper_rewrites_and_allows(tmp_path, monkeypatch):
    hook = _load("hrg_hook_under_test", HOOK)
    out, log = io.StringIO(), tmp_path / "events.ndjson"
    monkeypatch.setenv("NOCTUS_GUARD_EVENT_LOG", str(log))  # the composed hook logs each member guard's event itself
    assert hook.run_guard("heavy-run", hook._judge, stdin=io.StringIO(json.dumps(_bash("pytest"))), stdout=out,
                          event_log=log) == 0
    body = json.loads(out.getvalue())["hookSpecificOutput"]
    assert body["permissionDecision"] == "allow" and "hw_admission.py run --job" in body["updatedInput"]["command"]
    assert json.loads(log.read_text().splitlines()[-1])["outcome"] == "rewrite"
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


# 2026-11-05 — heredoc bodies are data; newlines separate commands; the escape
# is honoured before any parse can refuse. Each case is a shape that was
# refused (or missed) in practice.
HEREDOC_ALLOW = [
    # writing a test-runner script is not running it
    "cat > /tmp/s/g1.sh <<'EOF'\ncd x && .venv/bin/python -m pytest -q tests/a.py\nEOF\n"
    "python mcp/noctusai/tools/noctus/dev/hw_admission.py run --job pytest:x -- bash /tmp/s/g1.sh",
    # an apostrophe in a body used to make the whole command "unparseable"
    "cat > notes.md <<EOF\nit's where pytest lives\nEOF",
    "git commit -F - <<'EOF'\nfix: don't run pytest ungated\nEOF",
    "cat > f <<-EOF\n\tpytest\n\tEOF",
]
HEREDOC_DENY = [
    "cd x\npytest -q",
    "bash <<'EOF'\ncd x && pytest -q\nEOF",
    "cat > f <<EOF\ndata\nEOF\npytest",
    # the compound: a heredoc writes the test, then the suite runs
    "cat > t_new.py <<'EOF'\ndef test_a():\n    assert 1\nEOF\npytest -q t_new.py",
]


@pytest.mark.parametrize("cmd", HEREDOC_ALLOW)
def test_heredoc_body_is_data(cmd):
    assert guard.decide(_bash(cmd)) is None


@pytest.mark.parametrize("cmd", HEREDOC_DENY)
def test_heredoc_and_newline_still_judged(cmd):
    new = _rewrite(cmd)["updated_input"]["command"]
    assert shlex.split(new)[-1] == cmd  # heredoc + run travel together inside the one gated job


def test_escape_honoured_even_when_unparseable():
    assert guard.decide(_bash("NOC_HW_UNGATED_OK=harness-trial pytest 'unterminated")) is None
    assert guard.decide(_bash("NOC_HW_UNGATED_OK= pytest 'unterminated"))  # empty escape: refused


# ── Local Whisper (owner rule 2026-11-07): server first, local only after a server failure ──
WHISPER_DENY = [
    "uv run -q --no-project --with faster-whisper python -I /tmp/s/whisper_one.py a.mp3 o.json",
    "python whisper_one.py a.mp3 out.json",
    "nice -n 10 backend/.venv/bin/python -I local_whisper_batch.py mp3 out",
    "python3 -m faster_whisper a.mp3",
    "whisper a.mp3 --model turbo",
    "cd v02 && whisperx a.mp3",
]
WHISPER_ALLOW = [
    'python -c "import faster_whisper"',
    "grep -rn whisper .",
    "python script.py whisper.mp3",
    "uv run python tools/report.py",
    "python mcp/noctusai/tools/noctus/dev/hw_admission.py run --job whisper:local -- python whisper_one.py a b",
]


@pytest.mark.parametrize("cmd", WHISPER_DENY)
def test_local_whisper_denied_with_server_first_message(cmd):
    out = guard.decide(_bash(cmd))
    assert out and "noctus.transcription.transcribe" in out["reason"]
    assert "--job whisper:local" in out["reason"]


@pytest.mark.parametrize("cmd", WHISPER_ALLOW)
def test_whisper_lookalikes_allowed(cmd):
    assert guard.decide(_bash(cmd)) is None


def test_whisper_escape_after_server_failure(capsys):
    assert guard.decide(_bash('NOC_HW_UNGATED_OK="transcriber 503 after retries" python whisper_one.py a b')) is None
    assert "transcriber 503" in capsys.readouterr().err


@pytest.mark.parametrize("cmd", ["nice -n 10 pytest tests", "nice -10 pytest", "env -i FOO=1 pytest",
                                 "uv run pytest -q", "uv run --with x pytest"])
def test_wrapper_and_uv_flags_do_not_hide_a_suite(cmd):
    _rewrite(cmd)


# ── 2026-11-16: a `timeout`-prefixed bare-venv pytest ran outside the hardware slot (3 concurrent runs, swap 8.7/9.2G) ──
_REAL_BYPASS = ("timeout 300 /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest "
                "tests/modules/media_creation -q")
WRAPPED_FORMS = [
    _REAL_BYPASS,
    f"cd products/p-studio/backend && {_REAL_BYPASS} 2>&1 | tail -20",
    "timeout -k 10 300 /a/venv/bin/python -m pytest tests -q",
    "timeout --signal=KILL 300 python -m pytest tests",
    "timeout --kill-after=5s --foreground 300 python -m pytest tests",
    "gtimeout 300 .venv/bin/python3.11 -m pytest tests",
    "PYTHONPATH=. timeout 300 venv/bin/pytest tests",
    "caffeinate -i timeout 300 venv/bin/python -m pytest tests",
    "nice -n 10 timeout 300 venv/bin/python -m pytest tests",
    "time timeout 300s venv/bin/python -m pytest tests",
    "ionice -c 3 stdbuf -oL venv/bin/py.test tests",
    "/a/venv/bin/python -m unittest discover",
]


@pytest.mark.parametrize("cmd", WRAPPED_FORMS)
def test_wrapped_and_bare_venv_pytest_is_rewritten_into_the_gate_keeping_the_wrapper_inside(cmd):
    verdict = guard.decide(_bash(cmd))
    assert verdict is not None and verdict["decision"] == "allow", cmd
    rewritten = verdict["updated_input"]["command"]
    assert "hw_admission.py" in rewritten and f" -- bash -c " in rewritten
    assert shlex.split(rewritten)[-1] == cmd  # the whole original (timeout included) runs INSIDE the admitted job


def test_the_exact_bypass_command_names_a_pytest_job():
    verdict = guard.decide(_bash(_REAL_BYPASS))
    assert "--job pytest:" in verdict["updated_input"]["command"]


@pytest.mark.parametrize("cmd", ["timeout 5 git status", "timeout 300 ls tests", "gtimeout -k 1 5 echo pytest",
                                 "nice -n 10 git log --oneline"])
def test_a_wrapped_command_that_is_not_heavy_is_allowed_untouched(cmd):
    assert guard.decide(_bash(cmd)) is None


def test_an_already_gated_timeout_pytest_is_not_wrapped_twice():
    gated = guard.gated_command(_REAL_BYPASS, "pytest:media_creation")
    assert guard.decide(_bash(gated)) is None
