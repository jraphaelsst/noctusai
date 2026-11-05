"""Deny an UNGATED heavy test/build run from an agent's Bash call, BEFORE it runs.

WHY THIS EXISTS
===============
The machine-wide hardware gate (`hw_admission.py run --job <kind:target> -- <cmd>`)
admits one heavy run at a time on MEASURED capacity. The rule "wrap heavy shell
runs" was written only for devops-engineer and the KB, i.e. discipline-only. On
2026-11-04 several sessions ran suites ungated (1,253 + 273 + 568 tests) and the
8 GB machine swapped. Gate<->methodology sync: a rule ships with its by-
construction mechanism. This is that mechanism (PreToolUse hook on `Bash`).

WHAT IS MATCHED (per command segment; compound commands are split by shlex)
===========================================================================
`pytest` / `py.test` / `python -m pytest`, `vitest`, `playwright test`,
`vite build`, `npm|pnpm|yarn [run] test|build[:x]` (incl. via `npx`/`pnpm exec`
/ `npm exec`), and the same nested in `bash|sh|zsh -c "<script>"`.

WHAT IS ALLOWED
===============
* a segment that runs `hw_admission.py` (the wrapped command is its argument);
* `--collect-only` / `--co` / `--version` / `--help` / `-h` (nothing heavy runs);
* a segment whose command word is something else (`grep pytest f`, `echo "pytest"`);
* the escape `NOC_HW_UNGATED_OK=<non-empty reason>` as an inline env assignment
  (or in the hook's environment); the reason is echoed to stderr. Empty => deny.

SELF-GATING TOOLS ARE NOT AFFECTED (verified assumption)
========================================================
`task_branch integrate`, `gate_sweep`, `predeploy_check` take the slot inside the
MCP server process and spawn their gates with subprocess there. A PreToolUse hook
fires only on the AGENT's own tool calls (Bash/Edit/...), never on subprocesses
of an MCP server, so they cannot be blocked by this guard (and must not be
wrapped; see the KB). The agent's own `pytest` inside a Bash call IS seen.

HEREDOCS AND NEWLINES (2026-11-05)
==================================
A heredoc body is data (`cat > run.sh <<'EOF' … EOF` runs nothing) and is not
scanned, unless the heredoc feeds bash/sh/zsh. Newlines outside quotes split
commands. The escape is read BEFORE parsing, so an unparseable command that
carries a valid escape is no longer refused.

DELIBERATE LIMITS
=================
Token scanning, not a shell interpreter: `$(...)`, backticks, `xargs pytest`,
aliases and scripts that call pytest internally (`./run-tests.sh`) are not
resolved. The hardware gate itself and CI remain the backstops.
KB § PATTERNS/devops/hardware-admission-budget.md
"""
from __future__ import annotations

import os
import re
import shlex
import sys
from typing import Any

ESCAPE_ENV = "NOC_HW_UNGATED_OK"
KB_POINTER = "KB § PATTERNS/devops/hardware-admission-budget.md"
GATE = "python mcp/noctusai/tools/noctus/dev/hw_admission.py run"

_OPS = {"&&", "||", ";", "|", "&", "(", ")", "|&", ";;", "\n"}
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_WRAPPERS = {"env", "sudo", "time", "nohup", "command", "exec", "nice", "caffeinate", "builtin"}
_RUNNERS = {"npx", "pnpx", "bunx"}
_PKG = {"npm", "pnpm", "yarn", "bun"}
_SHELLS = {"bash", "sh", "zsh"}
_BENIGN = {"--collect-only", "--co", "--version", "--help", "-h"}
_SCRIPT_TARGETS = {"test", "t", "tst", "build"}


_HEREDOC = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
_ESCAPE_INLINE = re.compile(
    rf"(?:^|[\s;&|(]){ESCAPE_ENV}=('[^']*'|\"[^\"]*\"|[^\s;&|)]*)"
)


def _split_heredocs(command: str) -> tuple[str, list[tuple[str, str]]]:
    """Separate heredoc BODIES from the command text (2026-11-05).

    A heredoc body is DATA — `cat > run.sh <<'EOF' … pytest … EOF` writes a
    file, it runs nothing. The token scanner used to read the body as more
    command words, so writing a test script was refused as an ungated run, and
    an apostrophe in a body made the whole command "unparseable" (refused too).
    Returns (command text with bodies removed, [(introducing line, body)]).
    The caller re-scans a body only when the line feeds it to a shell
    (`bash <<EOF`), because then the body DOES run.
    """
    lines = command.split("\n")
    kept: list[str] = []
    bodies: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        kept.append(line)
        i += 1
        for strip_tabs, _q, delim in _HEREDOC.findall(line):
            body: list[str] = []
            while i < len(lines):
                cur = lines[i].lstrip("\t") if strip_tabs else lines[i]
                i += 1
                if cur == delim:
                    break
                body.append(lines[i - 1])
            bodies.append((line, "\n".join(body)))
    return "\n".join(kept), bodies


def _chunks(text: str) -> list[str]:
    """Split on newlines that are command separators (not inside quotes).

    shlex treats a newline as plain whitespace, so `cd x\\npytest` used to read
    as one segment whose command word is `cd`. Lines are accumulated until they
    parse; each parseable run is one chunk. A trailing unbalanced run is
    returned as-is so the caller's unparseable branch still judges it.
    """
    out: list[str] = []
    buf: list[str] = []
    for line in text.split("\n"):
        buf.append(line)
        joined = "\n".join(buf)
        if joined.rstrip().endswith("\\"):
            continue
        try:
            shlex.split(joined)
        except ValueError:
            continue
        out.append(joined)
        buf = []
    if buf:
        out.append("\n".join(buf))
    return out


def _feeds_a_shell(line: str) -> bool:
    """True when the heredoc on `line` is the stdin of bash/sh/zsh (so it runs)."""
    for seg in _segments(line):
        words, _env = _strip_prefix(seg)
        if words and os.path.basename(words[0]) in _SHELLS and "-c" not in words and "<<" in "".join(words):
            return True
    return False


def _escape_reason(command: str) -> str:
    """The escape is honoured FIRST, before any parsing can refuse (2026-11-05).

    It used to be read only after a successful scan, so a command the scanner
    could not parse was refused even when it carried a valid escape — the
    documented way out was unreachable exactly when it was needed.
    """
    for m in _ESCAPE_INLINE.finditer(command):
        val = m.group(1).strip("'\"").strip()
        if val:
            return val
    return os.environ.get(ESCAPE_ENV, "").strip()


def _segments(command: str) -> list[list[str]]:
    lex = shlex.shlex(command, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""
    segs: list[list[str]] = [[]]
    for tok in lex:
        if tok in _OPS:
            segs.append([])
        else:
            segs[-1].append(tok)
    return [s for s in segs if s]


def _strip_prefix(seg: list[str]) -> tuple[list[str], dict[str, str]]:
    """Drop leading VAR=val / wrapper words (and `timeout N`); return (rest, env)."""
    env: dict[str, str] = {}
    i = 0
    while i < len(seg):
        t = seg[i]
        if _ASSIGN.match(t):
            k, _, v = t.partition("=")
            env[k] = v
            i += 1
        elif os.path.basename(t) in _WRAPPERS:
            i += 1
        elif os.path.basename(t) == "timeout":
            i += 2 if i + 1 < len(seg) else 1
        else:
            break
    return seg[i:], env


def _is_pkg_script(args: list[str]) -> bool:
    """`npm test` / `npm run build` / `pnpm exec vitest` handled by caller; script names here."""
    words = [a for a in args if not a.startswith("-")]
    if not words:
        return False
    if words[0] in _SCRIPT_TARGETS or words[0].split(":")[0] in {"test", "build"}:
        return True
    if words[0] in {"run", "run-script"} and len(words) > 1:
        return words[1] in _SCRIPT_TARGETS or words[1].split(":")[0] in {"test", "build"}
    return False


def _heavy_kind(words: list[str]) -> str | None:
    """Return 'pytest'|'vitest'|'playwright'|'build' when `words` (prefix stripped) runs one."""
    if not words:
        return None
    cmd = os.path.basename(words[0])
    args = words[1:]
    if cmd in {"pytest", "py.test"}:
        return "pytest"
    if re.fullmatch(r"python[\d.]*", cmd):
        for a, b in zip(args, args[1:]):
            if a == "-m" and b in {"pytest", "py.test"}:
                return "pytest"
        return None
    if cmd == "vitest":
        return "vitest"
    if cmd == "playwright":
        return "playwright" if "test" in args else None
    if cmd == "vite":
        return "build" if "build" in args else None
    if cmd in _RUNNERS or (cmd in _PKG and args[:1] in (["exec"], ["dlx"], ["x"])):
        inner = args[1:] if cmd in _PKG else args
        inner = [a for a in inner if not a.startswith("-")] if inner[:1] and inner[0].startswith("-") else inner
        return _heavy_kind(inner)
    if cmd in _PKG and _is_pkg_script(args):
        return "build" if any(w.split(":")[0] == "build" for w in args) else "vitest"
    return None


def _scan(command: str, found: list[tuple[str, list[str], dict[str, str]]], depth: int = 0) -> None:
    for seg in _segments(command):
        words, env = _strip_prefix(seg)
        if not words:
            continue
        cmd = os.path.basename(words[0])
        if cmd in _SHELLS and depth < 3 and "-c" in words:
            idx = words.index("-c")
            if idx + 1 < len(words):
                _scan(words[idx + 1], found, depth + 1)
            continue
        if any(os.path.basename(w) == "hw_admission.py" for w in words[:3]):
            continue
        kind = _heavy_kind(words)
        if kind is None or any(a in _BENIGN for a in words[1:]):
            continue
        found.append((kind, words, env))


def _suggest_job(kind: str, words: list[str], command: str) -> str:
    m = re.search(r"products/([A-Za-z0-9_-]+)", command)
    if kind in {"vitest", "playwright", "build"}:
        return f"{'build' if kind == 'build' else kind}:{m.group(1) if m else '<product>'}"
    for a in words[1:]:
        if not a.startswith("-") and ("/" in a or a.endswith(".py")):
            target = a.split("::")[0].rstrip("/")
            return f"pytest:{os.path.basename(os.path.dirname(target) or target) or target}"
    return f"pytest:{m.group(1) if m else '<target>'}"


def decide(payload: dict[str, Any]) -> dict[str, Any] | None:
    """None to allow; `{"reason": ...}` to deny. Only `Bash` is judged."""
    if (payload.get("tool_name") or "") != "Bash":
        return None
    command = ((payload.get("tool_input") or {}).get("command")) or ""
    if not command.strip():
        return None
    found: list[tuple[str, list[str], dict[str, str]]] = []
    text, bodies = _split_heredocs(command)
    try:
        for chunk in _chunks(text):
            _scan(chunk, found)
        for feeder, body in bodies:
            # A body fed to a shell runs; a body fed to `cat >`/`tee`/python
            # stdin is data (python stdin is a script, but it cannot spawn a
            # suite through a word this scanner could see anyway).
            if _feeds_a_shell(feeder):
                for chunk in _chunks(body):
                    _scan(chunk, found)
    except ValueError:
        # Unparseable shell (unbalanced quotes): cannot judge; heavy words present => refuse.
        if re.search(r"\b(pytest|vitest|playwright test|vite build)\b", text):
            found.append(("pytest", ["pytest"], {"__unparseable__": "1"}))
    if not found:
        return None
    reason = _escape_reason(command)
    if reason:
        sys.stderr.write(f"[noc-guard:heavy-run] ungated heavy run accepted: {ESCAPE_ENV}={reason!r}\n")
        return None
    kind, words, env = found[0]
    why = "unparseable command" if "__unparseable__" in env else None
    return {"reason": _msg(kind, words, command, why)}


def _msg(kind: str, words: list[str], command: str, why: str | None) -> str:
    job = _suggest_job(kind, words, command)
    wrapped = f"{GATE} --job {job} -- {shlex.join(words)}"
    return (
        "heavy test/build run outside the machine-wide hardware gate"
        + (f" ({why})" if why else "")
        + f". Run it through the gate instead:\n  {wrapped}\n"
        "Self-gating tools (task_branch integrate, gate_sweep, predeploy_check) need no wrapper. "
        f"Genuinely cannot gate? Prefix `{ESCAPE_ENV}=<non-empty reason>` (recorded). "
        f"Why: ungated parallel suites swapped the 8 GB machine (2026-11-04). {KB_POINTER}"
    )
