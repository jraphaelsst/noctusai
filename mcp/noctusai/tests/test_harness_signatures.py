"""Colocated tests for `noctus.dev.harness_signatures` — the SHARED table
extracted from `gate_sweep.py` on 2026-09-20 (see that module's own
docstring for the incident). `test_gate_sweep.py` still exercises the
original five signatures end-to-end via `GS._harness_suspect` (unchanged,
re-exported names); this file owns the NEW signatures + the PostToolUse
Bash-hook decision function (`bash_advisory`), which `gate_sweep` never
touches.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import harness_signatures as HS  # noqa: E402

# ── new signatures: realistic captured output per signature ────────────────

# Verbatim shape of the 2026-09-20 instance-3 incident: `cli.py
# --predeploy-check --product core` — the flag takes a POSITIONAL slug, not
# `--product`. argparse exits 2 before any work runs.
_ARGPARSE_USAGE_ERROR = (
    "usage: cli.py [-h] [--predeploy-check PRODUCT] ...\n"
    "cli.py: error: unrecognized arguments: --product core\n"
)
_ARGPARSE_REQUIRED_ARG = (
    "usage: cli.py migrate [-h] product\n"
    "cli.py migrate: error: the following arguments are required: product\n"
)
_COMMAND_NOT_FOUND_TEXT = "/bin/sh: line 1: nonexistent-tool: command not found\n"
_COMMAND_NOT_FOUND_ENOENT = (
    "/usr/bin/env: 'nonexistent-interpreter': No such file or directory\n"
)
_TIMEOUT_KILLED_TEXT = "Killed\n"
_TIMEOUT_SIGNAL9 = "Command terminated by signal 9\n"
# Real `pytest -k nonexistent_marker` shape.
_NO_TESTS_COLLECTED = (
    "============================= test session starts ==============================\n"
    "collected 0 items\n"
    "\n"
    "============================== no tests ran in 0.00s ===============================\n"
)
_TOP_LEVEL_MODULE_MISSING = "ModuleNotFoundError: No module named 'requests'\n"
# The exact shape `test_signature_does_not_fire_on_genuine_failures` (in
# test_gate_sweep.py) already asserts must NOT be reclassified — an internal,
# dotted import path is almost always a genuinely broken import in shipped
# code, not a missing environment dependency.
_GENUINE_DOTTED_IMPORT_FAILURE = "ModuleNotFoundError: No module named 'app.services.nope'\n"


def test_argparse_usage_error_requires_both_exit_code_and_text():
    hit = HS.harness_suspect(_ARGPARSE_USAGE_ERROR, exit_code=2)
    assert hit is not None
    assert hit["signature"] == "argparse_usage_error"
    assert "unrecognized arguments" in hit["matched_line"]

    hit2 = HS.harness_suspect(_ARGPARSE_REQUIRED_ARG, exit_code=2)
    assert hit2["signature"] == "argparse_usage_error"


def test_argparse_usage_error_does_not_fire_without_the_matching_exit_code():
    """The exit code half of the AND is load-bearing: the same argparse-style
    text without the corroborating exit 2 must not be reclassified — this is
    exactly why the class needed `exit_code` threaded through at all."""
    assert HS.harness_suspect(_ARGPARSE_USAGE_ERROR, exit_code=None) is None
    assert HS.harness_suspect(_ARGPARSE_USAGE_ERROR, exit_code=1) is None


def test_argparse_usage_error_does_not_fire_on_bare_exit_2_alone():
    """A plain `exit 2` shared by countless tools must not, on its own, be
    read as an argparse usage error — only the corroborating text does."""
    assert HS.harness_suspect("AssertionError: assert 1 == 2\n", exit_code=2) is None


def test_command_not_found_fires_on_exit_code_alone():
    hit = HS.harness_suspect("", exit_code=127)
    assert hit is not None
    assert hit["signature"] == "command_not_found"


def test_command_not_found_fires_on_text_alone():
    hit = HS.harness_suspect(_COMMAND_NOT_FOUND_TEXT)
    assert hit["signature"] == "command_not_found"
    hit2 = HS.harness_suspect(_COMMAND_NOT_FOUND_ENOENT)
    assert hit2["signature"] == "command_not_found"


def test_timeout_killed_fires_on_exit_code_alone():
    hit = HS.harness_suspect("", exit_code=124)
    assert hit is not None
    assert hit["signature"] == "timeout_killed"


def test_timeout_killed_fires_on_text_alone():
    assert HS.harness_suspect(_TIMEOUT_KILLED_TEXT)["signature"] == "timeout_killed"
    assert HS.harness_suspect(_TIMEOUT_SIGNAL9)["signature"] == "timeout_killed"


def test_no_tests_collected_fires_on_real_pytest_output():
    hit = HS.harness_suspect(_NO_TESTS_COLLECTED)
    assert hit is not None
    assert hit["signature"] == "no_tests_collected"
    assert "collected 0 items" in hit["matched_line"]


def test_python_module_missing_fires_on_a_top_level_package():
    hit = HS.harness_suspect(_TOP_LEVEL_MODULE_MISSING)
    assert hit is not None
    assert hit["signature"] == "python_module_missing"


def test_python_module_missing_stays_silent_on_a_dotted_internal_import():
    """The deliberate narrowing vs. a blanket ModuleNotFoundError/ImportError
    match: a dotted internal import path is a genuine code bug, and must
    keep classifying as one. Mirrors
    test_gate_sweep.test_signature_does_not_fire_on_genuine_failures."""
    assert HS.harness_suspect(_GENUINE_DOTTED_IMPORT_FAILURE) is None


def test_python_env_missing_still_wins_over_the_generic_signature():
    """Ordering: the specific noctusai/seed signature must still be named
    specifically, not swallowed by the new generic one."""
    hit = HS.harness_suspect("ModuleNotFoundError: No module named 'noctusai_lib'\n")
    assert hit["signature"] == "python_env_missing"


def test_new_signatures_do_not_fire_on_existing_genuine_failures():
    """Same fixture set `test_gate_sweep.test_signature_does_not_fire_on_genuine_failures`
    uses — the new signatures must not regress that guarantee either."""
    for genuine in (
        "Error: expect(locator).toHaveAttribute(expected) failed",
        "AssertionError: assert 3 == 4",
        'Failed to resolve import "./components/Missing" from "src/App.tsx"',
        "ModuleNotFoundError: No module named 'app.services.nope'",
        "src/App.tsx(12,3): error TS2304: Cannot find name 'foo'.",
        "  2 failed\n  49 passed (1.7m)",
        "1 failed, 42 passed in 0.28s",
        "FAILED tests/test_x.py::test_y - AssertionError",
    ):
        assert HS.harness_suspect(genuine) is None, genuine
        assert HS.harness_suspect(genuine, exit_code=1) is None, genuine


# ── bash_advisory (the PostToolUse hook's decision function) ──────────────


def test_bash_advisory_silent_on_success():
    assert HS.bash_advisory({"stdout": "ok\n", "stderr": "", "exit_code": 0}) is None
    assert HS.bash_advisory({"stdout": "ok\n", "is_error": False}) is None


def test_bash_advisory_silent_on_unmatched_non_zero_exit():
    """A real, unclassified red: the hook has nothing useful to add, so it
    must say nothing rather than invent a guess."""
    result = HS.bash_advisory({
        "stdout": "",
        "stderr": "AssertionError: assert 3 == 4\n",
        "exit_code": 1,
    })
    assert result is None


def test_bash_advisory_silent_when_error_status_is_undeterminable():
    """No `is_error` flag and no parseable exit code anywhere -> must stay
    silent rather than assume failure."""
    assert HS.bash_advisory({"stdout": "some output with no exit info\n"}) is None
    assert HS.bash_advisory("plain string tool_response, no exit info") is None


def test_bash_advisory_fires_on_a_matched_failure_via_exit_code_field():
    result = HS.bash_advisory({
        "stdout": "",
        "stderr": _ARGPARSE_USAGE_ERROR,
        "exit_code": 2,
    })
    assert result is not None
    assert result["signature"] == "argparse_usage_error"
    assert result["exit_code"] == 2


def test_bash_advisory_fires_via_is_error_flag_and_exit_code_text_fallback():
    """Exercises the textual `Exit code: N` fallback extractor when no
    numeric field is present under any of the known key spellings."""
    result = HS.bash_advisory({
        "is_error": True,
        "stdout": "",
        "stderr": _ARGPARSE_USAGE_ERROR + "Exit code: 2\n",
    })
    assert result is not None
    assert result["signature"] == "argparse_usage_error"
    assert result["exit_code"] == 2


def test_bash_advisory_accepts_alternate_exit_code_key_spellings():
    for key in ("exit_code", "exitCode", "returncode", "return_code", "code"):
        result = HS.bash_advisory({"stdout": "", "stderr": "", key: 127})
        assert result is not None, key
        assert result["signature"] == "command_not_found"
