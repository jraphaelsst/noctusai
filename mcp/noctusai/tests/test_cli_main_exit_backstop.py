"""Regression tests for the `cli.py` `if __name__ == "__main__":` backstop.

Context (2026-08-31): a `--auto-improvement-query` invocation under a bare
(non-venv) interpreter was observed ONCE to print a traceback and still exit
0. The root cause was investigated and NOT reproduced — see the comment
directly above the wrapper in `cli.py`. This is now load-bearing for
`_refresh_via_cli_subprocess` (`tools/noctus/dev/noc_graph_cache.py`), which
raises on `proc.returncode != 0`; a CLI that can return 0 on a crash would
silently defeat that check.

IMPORTANT — mutation-testing honesty note: for a genuinely UNCAUGHT
exception, CPython's own default top-level exception handling already
prints a traceback to stderr and exits with code 1 (verified empirically
against the pre-fix `cli.py`, i.e. the file BEFORE this backstop was added —
same rc=1, same stderr traceback). So a bare "raise inside main(), assert
rc != 0" test does NOT discriminate pre-fix from post-fix for that fault
class; it would pass either way. The wrapper's actual, testable contract is
narrower and is what these tests exercise:

1. A genuinely escaping (non-`SystemExit`) exception still yields a loud,
   non-zero exit — proven against the REAL `cli.py` (regression coverage).
2. The test methodology is NOT a fake that always passes: a plausible wrong
   implementation (broad `except: pass` with no re-raise / no `sys.exit`)
   is built as a mutant and shown to silently exit 0 with NO traceback —
   proving assertion (1) is falsifiable, not vacuous.
3. `SystemExit` passes through UNCHANGED — a mutant missing the
   `except SystemExit: raise` line is shown to CORRUPT an existing
   `sys.exit(2)` down to `sys.exit(1)`; the real wrapper preserves it.

KB § PATTERNS/common/methodology-execution-discipline.md (verify by exit
code, not by assuming "prints a traceback" implies anything about rc).
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


CLI_PATH = Path(__file__).resolve().parents[1] / "cli.py"
MCP_ROOT = CLI_PATH.parent
VENV_PYTHON = Path(__file__).resolve().parents[3] / "venv" / "bin" / "python3"
PYTHON = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable


def _extract_main_wrapper_block() -> str:
    """Pull the literal `if __name__ == "__main__": ...` block out of the
    REAL `cli.py` so the SystemExit-passthrough mutant test tracks the
    actual shipped source instead of a hand-copied (and driftable) string.
    """
    lines = CLI_PATH.read_text().splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith('if __name__ == "__main__":'):
            return "".join(lines[i:])
    raise AssertionError('cli.py has no `if __name__ == "__main__":` block')


def _run_stub_injected_cli(tmp_path: Path, cli_path: Path, fault: str) -> subprocess.CompletedProcess:
    """Run `cli_path` (a real or copied cli.py) with `--auto-improvement-query`,
    after replacing `tools.noctus.dev.auto_improvement` in `sys.modules` with
    a stub whose `query()` executes `fault` (arbitrary Python source, e.g.
    `raise RuntimeError(...)`). Runs via `runpy.run_path` so the file's own
    `if __name__ == "__main__":` block executes exactly as it would for a
    real `python cli.py ...` invocation.
    """
    harness = tmp_path / "run_harness.py"
    harness.write_text(
        textwrap.dedent(f"""
        import runpy, sys, types
        sys.path.insert(0, {str(MCP_ROOT)!r})
        fake = types.ModuleType("tools.noctus.dev.auto_improvement")
        def query(*a, **kw):
            {fault}
        fake.query = query
        sys.modules["tools.noctus.dev.auto_improvement"] = fake
        sys.argv = [{str(cli_path)!r}, "--auto-improvement-query", "anything"]
        runpy.run_path({str(cli_path)!r}, run_name="__main__")
        """)
    )
    return subprocess.run(
        [PYTHON, str(harness)],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_real_cli_uncaught_exception_exits_nonzero_with_traceback(tmp_path: Path) -> None:
    """The shipped `cli.py`: a genuinely escaping exception (not SystemExit)
    from a flag handler still yields rc != 0 with the traceback on stderr.
    """
    result = _run_stub_injected_cli(
        tmp_path, CLI_PATH, 'raise RuntimeError("MUTATION-TEST-INJECTED-FAILURE")'
    )
    assert result.returncode != 0, (
        f"expected non-zero exit, got {result.returncode}\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "Traceback (most recent call last):" in result.stderr
    assert "MUTATION-TEST-INJECTED-FAILURE" in result.stderr


def test_naive_swallow_mutant_would_have_exited_zero_silently(tmp_path: Path) -> None:
    """Mutation-kill proof for the test above: a plausible WRONG
    implementation (`except BaseException: pass`, no re-raise, no
    `sys.exit`) silently swallows the crash and the script falls through to
    completion — exit 0, nothing on stderr. This is the exact "traceback
    printed... no wait, NOT even printed, and exit 0" shape the real
    backstop is designed to prevent. Proves the assertions in
    `test_real_cli_uncaught_exception_exits_nonzero_with_traceback` are
    falsifiable (a broken implementation of the SAME contract fails them),
    not a fake that always passes.
    """
    mutant = tmp_path / "cli_swallow_mutant.py"
    mutant.write_text(
        textwrap.dedent('''
        import argparse

        def main():
            parser = argparse.ArgumentParser()
            parser.add_argument("--auto-improvement-query")
            args = parser.parse_args()
            if args.auto_improvement_query:
                from tools.noctus.dev import auto_improvement as ai
                ai.query(target=args.auto_improvement_query)

        if __name__ == "__main__":
            try:
                main()
            except BaseException:
                pass  # BUG: swallowed, no re-raise, no sys.exit — falls through to exit 0
        ''')
    )
    result = _run_stub_injected_cli(
        tmp_path, mutant, 'raise RuntimeError("MUTATION-TEST-INJECTED-FAILURE")'
    )
    assert result.returncode == 0, (
        "sanity check: the swallow-mutant must exit 0 for this to be a "
        f"real mutation-kill demonstration; got rc={result.returncode} "
        f"stderr={result.stderr}"
    )
    assert "MUTATION-TEST-INJECTED-FAILURE" not in result.stderr
    assert "Traceback" not in result.stderr


def test_systemexit_passthrough_preserves_real_exit_codes(tmp_path: Path) -> None:
    """The real wrapper's `except SystemExit: raise` means an existing
    `sys.exit(N)` call site inside `main()` keeps ITS code untouched — the
    wrapper must not remap a legitimate `sys.exit(2)` (or any other code)
    down to a generic `sys.exit(1)`.
    """
    harness_src = textwrap.dedent("""
        import sys

        def main():
            sys.exit(2)

    """) + _extract_main_wrapper_block()
    harness = tmp_path / "cli_systemexit_real.py"
    harness.write_text(harness_src)

    result = subprocess.run([PYTHON, str(harness)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 2, (
        f"expected the real wrapper to preserve sys.exit(2), got "
        f"rc={result.returncode} stdout={result.stdout} stderr={result.stderr}"
    )


def test_missing_systemexit_passthrough_would_corrupt_exit_code(tmp_path: Path) -> None:
    """Mutation-kill proof for the test above: take the REAL wrapper block
    (extracted from `cli.py`, not hand-copied) and remove ONLY the
    `except SystemExit: raise` lines. That mutant now catches the
    `SystemExit(2)` in the broad `except BaseException:` clause and
    remaps it to `sys.exit(1)` — corrupting a real, meaningful exit code
    into a generic failure code. Proves the SystemExit-passthrough
    assertion above is falsifiable, not a coincidence of how few flags were
    tried.
    """
    real_block = _extract_main_wrapper_block()
    mutant_block = real_block.replace(
        "    except SystemExit:\n        raise\n", ""
    )
    assert mutant_block != real_block, "extraction/replace did not find the SystemExit clause to strip"

    harness_src = textwrap.dedent("""
        import sys

        def main():
            sys.exit(2)

    """) + mutant_block
    harness = tmp_path / "cli_systemexit_mutant.py"
    harness.write_text(harness_src)

    result = subprocess.run([PYTHON, str(harness)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 1, (
        "sanity check: the missing-passthrough mutant must corrupt "
        f"sys.exit(2) into rc=1 for this to be a real mutation-kill "
        f"demonstration; got rc={result.returncode}"
    )
