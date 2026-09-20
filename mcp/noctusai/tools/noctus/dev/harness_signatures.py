"""Harness-failure signature catalog — SHARED between `noctus.dev.gate_sweep`
(the orchestrated leg) and the `claude-guard-harness-signature` PostToolUse
Bash hook (the ad-hoc leg). One table, two consumers; see
`KB § PATTERNS/common/methodology-execution-discipline.md` § 6/7 for the
full "verdict-channel integrity" + "harness validity" write-up.

WHY THIS TABLE IS ITS OWN MODULE (2026-09-20)
----------------------------------------------
`_HARNESS_SIGNATURES` + `_harness_suspect` used to live PRIVATE inside
`gate_sweep.py`, so they only ever fired when `gate_sweep` itself orchestrated
a gate. The same session that motivated `gate_sweep`'s harness-validity leg
ALSO produced a case it structurally could not reach: a tech-lead ran
`cli.py --predeploy-check --product core` with the wrong argparse syntax,
got exit 2 before any real work happened, and reported "6 failing products"
— a plain interactive Bash call, never routed through `gate_sweep`. A
signature table that only `gate_sweep` can see cannot catch a mis-read
OUTSIDE `gate_sweep`. Extracting it here — stdlib-only, no `settings`/toolkit
import — lets a cheap PostToolUse hook load it BY PATH (the same
`importlib.util.spec_from_file_location` idiom `claude-guard-primary-write.py`
already uses) without paying for the toolkit's import graph on every Bash
call. `gate_sweep.py` imports this module normally (it is already inside the
same package) and re-exports the old private names so its own behavior, and
its own tests, are unchanged by the move.

WHY EACH SIGNATURE EXISTS
--------------------------
A verdict is evidence about the SUBJECT only if the harness that produced it
was VALID. A missing browser binary, an unwired `node_modules`, a venv-less
interpreter, a dev server that never booted, a wrong CLI invocation, a
process the shell couldn't even find, a timeout that killed the process
before it could answer, and a test suite that collected and ran nothing all
produce an authoritative, correctly-attributed, completely uninformative
exit code. None of those verdicts describes the code under test — each looks
exactly like one that does. Every entry below is CONSERVATIVE ON PURPOSE: a
pattern that also matches a genuine product failure would hide a real red,
which is the same class of harm pointed the other way. Every match carries
its evidence line so a wrong guess is visible and refutable, never an opaque
reclassification.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HarnessSignature:
    """One named, matchable harness-failure fingerprint.

    `pattern` is a regex checked against each line of captured output (the
    original table's only axis). `exit_codes`, when set, is ALSO checked
    against the gate/command's own process exit code. The two combine with
    no extra boolean flag needed, because the shape of each real fault
    dictates which combination is safe:

      pattern only         -> text match alone is sufficient (the original,
                               still-most-common shape: the tool's own
                               distinctive setup-failure message).
      exit_codes only       -> the exit code alone is sufficient (used only
                               where that exit code is not shared with
                               anything else worth distinguishing).
      BOTH set               -> BOTH must match (AND). Used exactly where an
                               exit code on its own is too generic to trust
                               (argparse's plain `exit 2` is shared by every
                               tool that validates its own CLI args) — only
                               pairing it with argparse's OWN usage-error
                               text makes the classification safe.
    """

    name: str
    pattern: str | None
    remedy: str
    exit_codes: tuple[int, ...] | None = None


# (signature, regex, remedy[, exit_codes]). See the dataclass docstring for
# how `pattern` and `exit_codes` combine. Order matters: a MORE SPECIFIC
# signature must precede a more GENERAL one that could also match the same
# line (see `python_env_missing` before `python_module_missing`).
HARNESS_SIGNATURES: tuple[HarnessSignature, ...] = (
    HarnessSignature(
        "playwright_browser_missing",
        r"Executable doesn't exist at"
        r"|Please run the following command to download new browsers"
        r"|browserType\.launch:.*Executable",
        "npx playwright install chromium — browser binaries are per-VERSION, "
        "and installing a different @playwright/test version PRUNES the "
        "revision the old one needs (measured 2026-09-20: a 1.63 install "
        "silently removed 1.62.1's chromium, and its suite then 'failed').",
    ),
    HarnessSignature(
        "webserver_never_started",
        r"Process from config\.webServer was not able to start"
        r"|error when starting dev server",
        "the dev server never booted, so the suite never loaded the app — "
        "read the [WebServer] lines for the real cause; the test names in "
        "the report are noise.",
    ),
    HarnessSignature(
        "node_deps_missing",
        r"Cannot find module '(?!\.)"
        r"|ERR_MODULE_NOT_FOUND"
        r"|Failed to resolve entry for package"
        r"|[Ff]ailed to resolve import \"(?!\.)",
        "a BARE (package) specifier did not resolve — `npm ci "
        "--legacy-peer-deps` in the package dir, or re-run "
        "noctus.dev.task_branch action='start' wire_env=True to link a "
        "worktree's node_modules + @noctusai/* seed deps.",
    ),
    HarnessSignature(
        # Found by running this very sweep against the real tree, 2026-09-20:
        # `pytest:agents` exited 2 on `ModuleNotFoundError: claude_agent_sdk`
        # and was about to be reported as a plain `red`.
        "pytest_collection_error",
        r"Interrupted: \d+ errors? during collection"
        r"|INTERNALERROR"
        r"|ERROR: file or directory not found",
        "pytest exited on a COLLECTION error — NO test ever ran, so this is "
        "not a verdict about behaviour. Usually a dependency missing from "
        "the environment (KB § PATTERNS/common/"
        "silent-test-failure-from-missing-dep.md); read the ImportError to "
        "tell that apart from a genuinely broken import in shipped code.",
    ),
    HarnessSignature(
        # Live in this repo as of 2026-09-20: OpenAI credits are exhausted,
        # so every embedding-touching call 429s. Found the same day by
        # running the toolkit suite NON-hermetically (it loads .env, CI does
        # not) — it blocked ~33min on backoff at 3% CPU. A test that fails
        # this way is reporting the billing account, not the code.
        "llm_quota_or_auth",
        r"You have no credits remaining"
        r"|Error code: 429"
        r"|insufficient_quota"
        r"|Error code: 401.*[Aa]pi.?[Kk]ey",
        "the LLM provider refused on quota/auth — this is the ENVIRONMENT, "
        "not the code. CI runs the toolkit suite hermetically (no live key) "
        "for exactly this reason; reproduce it that way rather than against "
        "a live account.",
    ),
    HarnessSignature(
        "python_env_missing",
        r"ModuleNotFoundError: No module named 'noctusai_lib'"
        r"|ModuleNotFoundError: No module named 'seed",
        "worktrees carry NO venv — run gates through the PRIMARY's: "
        "<primary>/venv/bin/python <wt>/mcp/noctusai/cli.py --<flag> "
        "--worktree-path <wt>.",
    ),
    HarnessSignature(
        # 2026-09-20, instance 3 of the same-session harness-validity class:
        # `cli.py --predeploy-check --product core` (the flag takes a
        # POSITIONAL slug) exited 2 before any real work ran, for all 6 live
        # products — reported as "6 failing products" and had to be
        # retracted. Deliberately AND-gated on the exit code: plain `exit 2`
        # alone is far too generic (many tools use it for real failures) to
        # trust without argparse's own usage-error phrasing alongside it.
        "argparse_usage_error",
        r"error: (argument|unrecognized arguments|the following arguments "
        r"are required)|expected one argument|invalid choice"
        r"|unrecognized arguments",
        "the command NEVER RAN — argparse rejected the invocation before "
        "any work happened. Re-read `--help` for the correct syntax; this "
        "is not a verdict about the subject the command was meant to check.",
        (2,),
    ),
    HarnessSignature(
        "command_not_found",
        None,
        "the shell could not find the executable at all — nothing about "
        "the subject was measured. Check the binary is installed/on PATH, "
        "or that the path used is correct for this tree (worktrees ≠ "
        "primary checkout).",
        (127,),
    ),
    HarnessSignature(
        "command_not_found",
        r"command not found|No such file or directory",
        "the shell could not find the executable/path referenced — nothing "
        "about the subject was measured. Check the binary is installed/on "
        "PATH, or that the path used is correct for this tree (worktrees ≠ "
        "primary checkout).",
    ),
    HarnessSignature(
        "timeout_killed",
        None,
        "the process was killed by a wrapper timeout (GNU `timeout` exits "
        "124) before it could finish — re-run with more time or investigate "
        "why it hung; a killed process proves nothing about correctness.",
        (124,),
    ),
    HarnessSignature(
        "timeout_killed",
        r"\bKilled\b|signal 9",
        "the process was killed (SIGKILL / OOM / a wrapper timeout) before "
        "it could finish — a killed process proves nothing about "
        "correctness; re-run with more time/memory and investigate why it "
        "was killed.",
    ),
    HarnessSignature(
        "no_tests_collected",
        r"collected 0 items|no tests ran",
        "the suite collected/ran ZERO tests — that is neither a pass nor a "
        "fail, it is an empty measurement. Check the test path/pattern "
        "actually matches files in this tree before trusting an exit code "
        "either way.",
    ),
    HarnessSignature(
        # Deliberately narrower than "any ModuleNotFoundError/ImportError":
        # a DOTTED module path (`app.services.nope`) is almost always an
        # internal import genuinely broken in shipped code, not a missing
        # environment dependency — and MUST keep classifying as a real red
        # (see `test_signature_does_not_fire_on_genuine_failures`, which
        # asserts exactly that case stays unmatched). An UNDOTTED top-level
        # name (`claude_agent_sdk`, `requests`, ...) is the common
        # "package never installed in this interpreter" shape `python_env_missing`
        # above already special-cases for noctusai_lib/seed; this is that
        # same shape generalized to any other top-level package, keeping the
        # module's conservative-on-purpose posture.
        "python_module_missing",
        r"ModuleNotFoundError: No module named '[A-Za-z_][A-Za-z0-9_]*'",
        "a top-level Python package is not importable in the interpreter "
        "that ran this — before treating it as a code defect, check which "
        "interpreter actually ran (worktrees carry NO venv; see "
        "`python_env_missing` above) and whether the package is declared "
        "in the right requirements/pyproject.",
    ),
)


def harness_suspect(output: str, exit_code: int | None = None) -> dict[str, Any] | None:
    """Does this failing gate/command's output (and, optionally, its own
    process exit code) carry a known HARNESS-failure signature? Returns the
    matched evidence line so the call is auditable (and refutable) rather
    than an opaque reclassification. `exit_code=None` preserves the
    original text-only call shape (every pre-2026-09-20 call site)."""
    lines = (output or "").splitlines()
    for sig in HARNESS_SIGNATURES:
        text_hit: str | None = None
        if sig.pattern is not None:
            rx = re.compile(sig.pattern)
            for line in lines:
                if rx.search(line):
                    text_hit = line.strip()[:300]
                    break
            if text_hit is None:
                continue  # pattern required and did not match this signature
        exit_hit = (
            sig.exit_codes is not None
            and exit_code is not None
            and exit_code in sig.exit_codes
        )
        if sig.pattern is not None and sig.exit_codes is not None:
            if not exit_hit:
                continue  # AND semantics: text matched but exit code did not
            matched_line = text_hit
        elif sig.pattern is not None:
            matched_line = text_hit
        elif sig.exit_codes is not None:
            if not exit_hit:
                continue
            matched_line = f"(exit code {exit_code}, no output text required)"
        else:
            continue  # malformed entry: neither axis set — never matches
        return {"signature": sig.name, "matched_line": matched_line, "remedy": sig.remedy}
    return None


# ---------------------------------------------------------------------------
# PostToolUse Bash-hook support — extraction helpers for the raw hook
# payload's `tool_response`. Deliberately defensive: the exact field names
# Claude Code's harness uses for a Bash tool's exit status are not pinned
# down anywhere in this repo (no PostToolUse hook existed before this one),
# so this tries every plausible spelling PLUS a textual "Exit code: N"
# fallback, and degrades to "stay silent" rather than guessing wrong.
# ---------------------------------------------------------------------------

_EXIT_CODE_KEYS = ("exit_code", "exitCode", "returncode", "return_code", "code")
_TEXT_KEYS = ("stdout", "stderr", "output", "content")
_EXIT_CODE_TEXT_RE = re.compile(r"[Ee]xit code:?\s*(-?\d+)")


def _extract_text(tool_response: Any) -> str:
    if isinstance(tool_response, str):
        return tool_response
    if not isinstance(tool_response, dict):
        return ""
    parts = [v for k in _TEXT_KEYS if isinstance((v := tool_response.get(k)), str)]
    return "\n".join(parts)


def _extract_exit_code(tool_response: Any) -> int | None:
    if isinstance(tool_response, dict):
        for key in _EXIT_CODE_KEYS:
            v = tool_response.get(key)
            if isinstance(v, int) and not isinstance(v, bool):
                return v
    m = _EXIT_CODE_TEXT_RE.search(_extract_text(tool_response))
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def _extract_is_error(tool_response: Any, exit_code: int | None) -> bool | None:
    """`True`/`False` when determinable, `None` when it cannot be told —
    callers MUST treat `None` as "stay silent", never as "assume failed"."""
    if isinstance(tool_response, dict) and isinstance(tool_response.get("is_error"), bool):
        return tool_response["is_error"]
    if exit_code is not None:
        return exit_code != 0
    return None


def bash_advisory(tool_response: Any) -> dict[str, Any] | None:
    """The PostToolUse Bash-hook decision function. Given a Bash tool's raw
    `tool_response`, returns an advisory dict (`signature`, `matched_line`,
    `remedy`, `exit_code`) when the call both (a) failed and (b) matches a
    known harness-failure fingerprint — else `None`, meaning STAY SILENT.

    Silent by construction on: a successful call (`is_error` False/exit 0),
    an undeterminable outcome (no `is_error` flag and no parseable exit
    code — never guessed as a failure), and any non-zero exit that matches
    no signature (a real, unclassified red — the hook has nothing useful to
    add, so it says nothing). Never raises: a malformed/partial
    `tool_response` degrades to `None`, matching the fail-open posture the
    PreToolUse guards already use."""
    exit_code = _extract_exit_code(tool_response)
    is_error = _extract_is_error(tool_response, exit_code)
    if not is_error:  # False or None (undeterminable) -> silent
        return None
    hit = harness_suspect(_extract_text(tool_response), exit_code)
    if hit is None:
        return None
    return {**hit, "exit_code": exit_code}


__all__ = [
    "HarnessSignature",
    "HARNESS_SIGNATURES",
    "harness_suspect",
    "bash_advisory",
]
