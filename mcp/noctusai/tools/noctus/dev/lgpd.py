"""
lgpd tool — records unresolved LGPD concerns as checklist items in
`LGPD-WARNINGS.md` at the repo root.

Concept: whenever an agent writes code that touches personal data and
encounters an unresolved LGPD concern (retention unclear, 3rd-party egress,
cache of patient text, cross-product leak, unbounded log, etc.), it calls
this tool. The tool **does not block** — it:

  1. Appends a checklist item to `LGPD-WARNINGS.md` (creates the file if
     missing).
  2. Notifies the user with a ⚠️ message so they see the flag in real time.
  3. Returns a structured dict for the calling agent.

Items are checkboxes — resolved ones get ticked (`- [ ]` → `- [x]`) when
the underlying concern is addressed. The file is a rolling log, not a
one-shot report.

Deduplication: if the same (code_path, concern) pair is already flagged
and unresolved, the tool updates the existing entry's "last seen" timestamp
instead of appending a duplicate row.

Full conventions: `KNOWLEDGE-BASE/CONTEXT/PATTERNS/lgpd.md`.
"""
from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path
from typing import Optional

from settings import REPO_ROOT  # noqa: E402  (path constant)
from workspace import resolve_caller_root

WARNINGS_FILE = REPO_ROOT / "LGPD-WARNINGS.md"


def _resolve_warnings_file(worktree_path: str | Path | None) -> tuple[Path, Path]:
    """Resolve (warnings_file, repo_root) for the active call.

    When ``worktree_path`` is None, returns the module-level defaults
    (server-startup workspace). When set, returns the caller's worktree's
    ``LGPD-WARNINGS.md`` — caller-aware path resolution per
    ``projects/mcp-worktree-path-resolution/``.
    """
    if worktree_path is None:
        return WARNINGS_FILE, REPO_ROOT
    root = resolve_caller_root(worktree_path)
    return root / "LGPD-WARNINGS.md", root

# `concern` is LAZY up to the closing `** at `: a concern may itself contain a
# lone `*` (e.g. "pk_* tokens"). The old `[^*]+` silently failed to parse such an
# entry, so `flag()` dropped it on the next rewrite (the core transcription-API
# entry, 2026-10-10) and swallowed it into the "header".
_ENTRY_RE = re.compile(
    r"^- \[(?P<checked>[ x])\] \*\*(?P<concern>.+?)\*\* at `(?P<path>[^`]+)`",
    re.MULTILINE,
)
# Any entry START (parseable or not) — block boundaries never depend on the
# identity regex, so an entry of an unexpected shape is kept verbatim, not lost.
_ENTRY_START_RE = re.compile(r"^- \[[ x]\] ", re.MULTILINE)

_FILE_HEADER = """# LGPD Concerns — Rolling Log

> **Auto-generated** by `noctus.dev.lgpd_flag` (see
> `mcp/noctusai/tools/lgpd.py`). Each item is an unresolved concern
> discovered during development. They are **not blockers** — the code
> ships and this file tracks what must be reviewed before the feature
> can be called done.
>
> Mark an item `- [x]` when the concern is resolved (code changed or
> dismissed with rationale). Do not delete items — strike through or
> move to an "Archive" section at the bottom. A commit that removes an
> unresolved item is refused by keeper `check_lgpd_entry_removal`; a genuine
> duplicate or re-key needs the commit trailer
> `LGPD-Entry-Removed: <concern or path prefix> — <reason>`.
>
> Philosophy + the five questions: `KNOWLEDGE-BASE/CONTEXT/PATTERNS/security/lgpd.md`.

"""


def _now() -> str:
    from noctusai_lib.primitives.timeutil import current_day_ref
    return current_day_ref()


def _format_entry(
    *,
    concern: str,
    code_path: str,
    reason: str,
    mitigation: Optional[str],
    first_flagged: str,
    last_seen: str,
    checked: bool = False,
) -> str:
    check = "x" if checked else " "
    mitigation_text = mitigation or "TBD — review before resolving."
    if first_flagged == last_seen:
        ts_line = f"  - *Flagged*: {first_flagged}"
    else:
        ts_line = f"  - *First flagged*: {first_flagged} · *Last seen*: {last_seen}"
    return (
        f"- [{check}] **{concern}** at `{code_path}` — {reason}\n"
        f"  - *Mitigation*: {mitigation_text}\n"
        f"{ts_line}"
    )


def _split_entries(existing: str) -> list[str]:
    """Split the warnings file into individual entry blocks (header + trailing
    lines). Each block starts with a `- [ ]` / `- [x]` line and continues
    until the next such line or EOF.
    """
    if not existing:
        return []
    lines = existing.splitlines(keepends=True)
    entries: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if _ENTRY_START_RE.match(line):
            if current:
                entries.append(current)
            current = [line]
        else:
            if current:
                current.append(line)
    if current:
        entries.append(current)
    return ["".join(e).rstrip() + "\n" for e in entries]


# ---------------------------------------------------------------------------
# Entry-aware parsing + 3-way merge (the `merge=lgpd-warnings` git driver).
#
# `flag()` always inserts a new entry at index 0, so two parallel branches that
# each flag a concern insert at the SAME anchor and git's text merge conflicts
# every time (2026-10-10: the conflict was resolved by REPLACING one entry with
# the other, silently losing an unresolved concern). `merge=union` is not an
# option (it duplicates / mangles multi-line blocks), so the driver merges by
# ENTRY IDENTITY. Shell half: scripts/hooks/merge-lgpd-warnings.sh. The
# commit-time guard against a lost entry is keeper `check_lgpd_entry_removal`
# (compliance.py): the driver does NOT re-police deletes.
# KB § PATTERNS/common/auto-generated-merge-drivers.md
# ---------------------------------------------------------------------------

_FLAGGED_RE = re.compile(r"\*(?:First flagged|Flagged)\*:\s*(\d{4}-\d{2}-\d{2})")


def entry_identity(block: str) -> tuple[str, str] | None:
    """The (concern, code_path) identity of one entry block, or None."""
    m = _ENTRY_RE.match(block)
    if m:
        return m.group("concern"), m.group("path")
    # Unparseable shape: identify by its first line so it still cannot vanish.
    return ("", block.split("\n", 1)[0].strip()) if _ENTRY_START_RE.match(block) else None


def entry_is_resolved(block: str) -> bool:
    return bool(re.match(r"- \[x\] ", block))


def parse_warnings(text: str) -> tuple[str, list[str]]:
    """Split the file into (header, entry blocks) with the SAME regex/splitter
    `flag()` and `list_warnings()` use (no second parser)."""
    m = _ENTRY_START_RE.search(text or "")
    if not m:
        return text or "", []
    return text[: m.start()], _split_entries(text[m.start():])


def _keyed_blocks(blocks: list[str]) -> dict[tuple, str]:
    """Key each block by identity + ordinal counted from the BOTTOM.

    The same (concern, path) can appear twice (a ticked entry plus a re-flagged
    unresolved one). New entries are inserted at the top, so counting from the
    bottom keeps an old entry's key stable when entries are added above it.
    """
    seen: dict[tuple[str, str], int] = {}
    keyed: dict[tuple, str] = {}
    for block in reversed(blocks):
        ident = entry_identity(block) or ("", block.strip())
        n = seen.get(ident, 0)
        seen[ident] = n + 1
        keyed[(ident, n)] = block
    return keyed


def _norm(block: str | None) -> str | None:
    return None if block is None else block.rstrip()


def _conflict(ours: str | None, theirs: str | None) -> str:
    return (
        "<<<<<<< ours\n" + ((ours or "").rstrip() + "\n" if ours else "")
        + "=======\n" + ((theirs or "").rstrip() + "\n" if theirs else "")
        + ">>>>>>> theirs\n"
    )


def _flagged_on(block: str) -> str:
    m = _FLAGGED_RE.search(block)
    return m.group(1) if m else ""


def merge_warnings(base: str, ours: str, theirs: str) -> tuple[str, bool]:
    """Entry-aware 3-way merge of `LGPD-WARNINGS.md`. Returns (text, conflicted).

    * Header: 3-way (a header edit on one side only is kept; both sides editing
      it differently conflicts, in markers around the header only).
    * Entries are keyed by identity (see `_keyed_blocks`).
    * Added on one side, or on both under different keys: all kept. Entries new
      relative to base are placed at the top, newest first (flagged date desc,
      then identity), so the result does not depend on merge direction.
    * Changed on one side only: that side's version. Changed identically on
      both: kept once.
    * Changed differently on both sides (or modified vs deleted): standard
      conflict markers around just that block, `conflicted=True`.
    * Deleted on one side and unchanged on the other: deleted. The driver does
      NOT re-police deletes; keeper `check_lgpd_entry_removal` governs them at
      commit time.
    Entries present in base keep OURS' relative order.
    """
    h_base, b_blocks = parse_warnings(base)
    h_ours, o_blocks = parse_warnings(ours)
    h_theirs, t_blocks = parse_warnings(theirs)
    kb, ko, kt = _keyed_blocks(b_blocks), _keyed_blocks(o_blocks), _keyed_blocks(t_blocks)

    conflicted = False
    if h_ours == h_theirs or h_theirs == h_base:
        header = h_ours
    elif h_ours == h_base:
        header = h_theirs
    else:
        conflicted = True
        header = _conflict(h_ours, h_theirs)
    if header and not header.endswith("\n\n") and not conflicted:
        header = header.rstrip("\n") + "\n\n"

    def resolve(key: tuple) -> tuple[str | None, bool]:
        b, o, t = kb.get(key), ko.get(key), kt.get(key)
        nb, no, nt = _norm(b), _norm(o), _norm(t)
        if no == nt:
            return o, False
        if no == nb:
            return t, False
        if nt == nb:
            return o, False
        return _conflict(o, t), True

    resolved: dict[tuple, str | None] = {}
    for key in {*kb, *ko, *kt}:
        out, c = resolve(key)
        resolved[key] = out
        conflicted = conflicted or c

    new_keys = [k for k in resolved if k not in kb and resolved[k] is not None]
    new_keys.sort(key=lambda k: k[0])
    new_keys.sort(key=lambda k: _flagged_on(resolved[k] or ""), reverse=True)
    # `ko` is bottom-up (see _keyed_blocks): restore file order for ours.
    old_keys = [k for k in reversed(list(ko)) if k in kb and resolved.get(k) is not None] + [
        k for k in reversed(list(kt)) if k in kb and k not in ko and resolved.get(k) is not None
    ]

    body = [resolved[k].rstrip() for k in new_keys + old_keys if resolved[k] is not None]
    text = header + "\n".join(body) + ("\n" if body else "")
    return text, conflicted


def flag(
    *,
    code_path: str,
    concern: str,
    reason: str,
    mitigation: Optional[str] = None,
    worktree_path: str | Path | None = None,
) -> dict:
    """Record a new LGPD concern (or refresh an existing one's last_seen).

    Args:
        code_path: Where the concern lives — file:line or a short locator.
        concern: Short label — e.g. `"patient-text-in-llm-cache"`,
                 `"cross-product-embedding-leak"`, `"service-role-no-tenant-filter"`.
        reason: Brief explanation of HOW this breaks LGPD (the five-questions
                answer). One to three sentences.
        mitigation: Optional suggested fix. If omitted, the entry gets a
                    `TBD — review before resolving` placeholder that future
                    reviewers fill in.
        worktree_path: **Caller-aware path resolution.** When set, the
            ``LGPD-WARNINGS.md`` lands at the caller's worktree root, not
            the MCP server's startup workspace. Engineers in a git worktree
            pass their worktree root; architects on main noc omit. See
            ``resolve_caller_root``.

    Returns:
        A dict with the full entry, the warnings-file path, and a
        notification string the caller should surface to the user.
    """
    if not concern or not reason or not code_path:
        return {"error": "concern, reason, and code_path are required"}

    warnings_file, repo_root = _resolve_warnings_file(worktree_path)

    warnings_file.parent.mkdir(parents=True, exist_ok=True)
    existing = warnings_file.read_text(encoding="utf-8") if warnings_file.exists() else ""

    # Split existing content: header (up to and including the last blank line
    # before the first entry) + entry blocks.
    header, entries = parse_warnings(existing)
    if not entries:
        header = existing or _FILE_HEADER

    now = _now()
    deduped = False
    refreshed_entries: list[str] = []
    for block in entries:
        m = _ENTRY_RE.search(block)
        if m and m.group("checked") == " " and m.group("concern") == concern and m.group("path") == code_path:
            # Same unresolved concern/path — refresh "last seen"
            first_ts_match = re.search(r"\*First flagged\*:\s*([\d-]+)|\*Flagged\*:\s*([\d-]+)", block)
            first_ts = (
                (first_ts_match.group(1) or first_ts_match.group(2))
                if first_ts_match else now
            )
            refreshed_entries.append(_format_entry(
                concern=concern,
                code_path=code_path,
                reason=reason,
                mitigation=mitigation,
                first_flagged=first_ts,
                last_seen=now,
            ) + "\n")
            deduped = True
        else:
            refreshed_entries.append(block if block.endswith("\n") else block + "\n")

    if not deduped:
        new_entry = _format_entry(
            concern=concern,
            code_path=code_path,
            reason=reason,
            mitigation=mitigation,
            first_flagged=now,
            last_seen=now,
        ) + "\n"
        refreshed_entries.insert(0, new_entry)  # newest first

    if not header.startswith("# LGPD Concerns"):
        header = _FILE_HEADER
    # Ensure blank line between header and entries.
    if not header.endswith("\n\n"):
        header = header.rstrip("\n") + "\n\n"

    warnings_file.write_text(header + "\n".join(b.rstrip() for b in refreshed_entries) + "\n", encoding="utf-8")

    notification = (
        f"⚠️  LGPD concern flagged: **{concern}** at `{code_path}`. "
        f"Recorded in `{warnings_file.name}`. This does NOT block; "
        f"review the file before the feature is called done."
    )
    return {
        "notification": notification,
        "warnings_file": str(warnings_file.relative_to(repo_root)),
        "concern": concern,
        "code_path": code_path,
        "reason": reason,
        "mitigation": mitigation,
        "deduped": deduped,
        "count_total": len(refreshed_entries),
    }


def list_warnings(worktree_path: str | Path | None = None) -> dict:
    """Return the current state of `LGPD-WARNINGS.md` as structured data.

    Args:
        worktree_path: Caller-aware path resolution; see :func:`flag`.
    """
    warnings_file, repo_root = _resolve_warnings_file(worktree_path)
    if not warnings_file.exists():
        return {"file": str(warnings_file.relative_to(repo_root)), "entries": []}

    content = warnings_file.read_text(encoding="utf-8")
    entries: list[dict] = []
    for m in _ENTRY_RE.finditer(content):
        entries.append({
            "concern": m.group("concern"),
            "code_path": m.group("path"),
            "resolved": m.group("checked") == "x",
        })
    return {
        "file": str(warnings_file.relative_to(repo_root)),
        "entries": entries,
        "unresolved_count": sum(1 for e in entries if not e["resolved"]),
        "resolved_count": sum(1 for e in entries if e["resolved"]),
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.lgpd_flag",
        description=(
            "Record an unresolved LGPD concern in `LGPD-WARNINGS.md`. Call whenever "
            "data-touching code raises an LGPD question (retention unclear, 3rd-party "
            "egress, cache of patient text, cross-product leak, …). DOES NOT BLOCK — "
            "appends a checklist item and notifies the user. Returns a user-facing "
            "notification string the caller should surface. Pass `worktree_path` "
            "when calling from inside a git worktree so the LGPD log lands in the "
            "worktree, not the MCP server's startup workspace."
        ),
    )
    def _lgpd_flag(
        code_path: str,
        concern: str,
        reason: str,
        mitigation: str | None = None,
        worktree_path: str | None = None,
    ) -> dict:
        return flag(
            code_path=code_path,
            concern=concern,
            reason=reason,
            mitigation=mitigation,
            worktree_path=worktree_path,
        )

    @server.tool(
        name="noctus.dev.lgpd_list",
        description=(
            "List all LGPD concerns from `LGPD-WARNINGS.md` (unresolved + resolved). "
            "Pass `worktree_path` to read the caller's worktree log."
        ),
    )
    def _lgpd_list(worktree_path: str | None = None) -> dict:
        return list_warnings(worktree_path=worktree_path)
