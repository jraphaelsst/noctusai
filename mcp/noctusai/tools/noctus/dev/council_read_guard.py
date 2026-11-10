"""Council blind-recorder READ guard (council must-fix J, 2026-11-09).

The council ledger's neutral-recorder design (tool-assigned anon labels, seats withheld until a verdict) only holds if
nobody can simply read `project-history/council/<YYYY-MM>/<session>.ndjson` while a session is open: the rows are plain
ndjson in the tree and carry every seat's claim + label. Until now that was a prompt instruction. This is the mechanism:
while a council session has NO `verdict` row, a direct read of its file is denied for EVERY caller (the tech-lead
included — the blindness is about the tech-lead too). Reading through the tool (`noctus.dev.council_ledger`,
`python mcp/noctusai/cli.py --council-ledger ...`, `blind_view`) is untouched: the guard judges file reads, not the tool.

Judged tools: `Read` (file_path), `Grep` (path, glob), `Glob` (path, pattern), `Bash` (a read verb — cat/head/tail/sed/
grep/rg/jq/python/git show... — whose command names `project-history/council`). A path naming one `<id>.ndjson` is
denied only if THAT session is open; a directory / glob / unknown target is denied while ANY session is open. Known
limit: a Grep whose path is a strict ANCESTOR of the council dir (repo root, `project-history`) with no council-naming
glob is not judged — blocking every repo-wide grep during a council would cost more than it protects.

A session file that cannot be parsed is treated as OPEN (cannot prove a verdict => stay blind). Pure function; the HOOK
decides shadow vs enforce (`MODE`) and carries telemetry. Stdlib-only (bare `python3`).
KB § PATTERNS/common/council.md · KB § PATTERNS/common/gate-methodology-sync.md.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

MODE = "shadow"  # house rule: a new gate runs warn-only >=7 days before blocking (gate_alignment triad). Flip to "enforce" (or env NOC_COUNCIL_READ_MODE=enforce) once `gate_alignment walls` shows no false positives; blindness is the aim, so flip promptly.
COUNCIL_REL = "project-history/council"
_READ_VERBS = re.compile(
    r"(?<![\w-])(cat|head|tail|less|more|sed|awk|grep|egrep|fgrep|rg|ag|jq|nl|strings|xxd|od|cut|sort|uniq|wc|bat|"
    r"python3?|node|perl|ruby|xargs|open)(?![\w-])|git\s+(show|diff|log|cat-file|grep|blame)\b")
_TOOL_OK = re.compile(r"council[_-]ledger")
_ID_FILE = re.compile(r"([0-9a-f-]{36})\.ndjson$")


def _open_sessions(root: Path) -> dict[str, Path]:
    """session_id (file stem) -> file, for every session file under `root` with no verdict row (unparseable => open)."""
    base = root / COUNCIL_REL
    out: dict[str, Path] = {}
    if not base.is_dir():
        return out
    for f in sorted(base.glob("*/*.ndjson")):
        has_verdict = False
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip() and json.loads(line).get("record") == "verdict":
                    has_verdict = True
                    break
        except (OSError, ValueError, AttributeError):
            has_verdict = False
        if not has_verdict:
            out[f.stem] = f
    return out


def _targets(tool_name: str, ti: dict[str, Any]) -> list[str]:
    if tool_name == "Read":
        return [str(ti.get("file_path") or "")]
    if tool_name == "Grep":
        return [str(ti.get("path") or ""), str(ti.get("glob") or "")]
    if tool_name == "Glob":
        return [str(ti.get("path") or ""), str(ti.get("pattern") or "")]
    return []


def _names_council(text: str) -> bool:
    t = text.replace("\\", "/")
    return COUNCIL_REL in t or bool(re.search(r"(^|/)council/", t) and "project-history" in t)


def decide(tool_name: str, tool_input: dict[str, Any] | None, roots: list[Path]) -> dict[str, Any] | None:
    """None to allow; `{"reason", "target", "session_ids"}` to deny a read of an open council session."""
    ti = tool_input or {}
    if tool_name == "Bash":
        cmd = str(ti.get("command") or "")
        if not _names_council(cmd) or _TOOL_OK.search(cmd) or not _READ_VERBS.search(cmd):
            return None
        texts = [cmd]
    elif tool_name in ("Read", "Grep", "Glob"):
        texts = [t for t in _targets(tool_name, ti) if t]
        if not any(_names_council(t) for t in texts):
            return None
    else:
        return None
    opened: dict[str, Path] = {}
    for r in roots:
        opened.update(_open_sessions(r))
    if not opened:
        return None
    joined = " ".join(texts)
    named = {m.group(1) for m in re.finditer(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", joined)}
    if named:  # the call points at specific session files: deny only if one of THEM is open
        hit = sorted(named & set(opened))
        if not hit:
            return None
    else:
        hit = sorted(opened)
    return {"reason": ("a council session is open (no verdict row yet) and its file is withheld: seats and labels stay "
                       "hidden until the chair decides (neutral recorder). Use the tool, not the file: "
                       "`blind_view` (chair view) or `status` via noctus.dev.council_ledger / "
                       "`python mcp/noctusai/cli.py --council-ledger`. Reads are allowed again once the verdict is "
                       f"recorded. Open: {', '.join(hit[:3])}{' ...' if len(hit) > 3 else ''}."),
            "target": joined[:200], "session_ids": hit}


__all__ = ["decide", "MODE", "COUNCIL_REL"]
