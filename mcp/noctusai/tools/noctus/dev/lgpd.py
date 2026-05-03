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

REPO_ROOT = Path(__file__).resolve().parents[5]
WARNINGS_FILE = REPO_ROOT / "LGPD-WARNINGS.md"

_ENTRY_RE = re.compile(
    r"^- \[(?P<checked>[ x])\] \*\*(?P<concern>[^*]+)\*\* at `(?P<path>[^`]+)`",
    re.MULTILINE,
)

_FILE_HEADER = """# LGPD Concerns — Rolling Log

> **Auto-generated** by `noctusai_lgpd_flag` (see
> `mcp/noctusai/tools/lgpd.py`). Each item is an unresolved concern
> discovered during development. They are **not blockers** — the code
> ships and this file tracks what must be reviewed before the feature
> can be called done.
>
> Mark an item `- [x]` when the concern is resolved (code changed or
> dismissed with rationale). Do not delete items — strike through or
> move to an "Archive" section at the bottom.
>
> Philosophy + the five questions: `KNOWLEDGE-BASE/CONTEXT/PATTERNS/lgpd.md`.

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
        if _ENTRY_RE.match(line.rstrip("\n")):
            if current:
                entries.append(current)
            current = [line]
        else:
            if current:
                current.append(line)
    if current:
        entries.append(current)
    return ["".join(e).rstrip() + "\n" for e in entries]


def flag(
    *,
    code_path: str,
    concern: str,
    reason: str,
    mitigation: Optional[str] = None,
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

    Returns:
        A dict with the full entry, the warnings-file path, and a
        notification string the caller should surface to the user.
    """
    if not concern or not reason or not code_path:
        return {"error": "concern, reason, and code_path are required"}

    WARNINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing = WARNINGS_FILE.read_text(encoding="utf-8") if WARNINGS_FILE.exists() else ""

    # Split existing content: header (up to and including the last blank line
    # before the first entry) + entry blocks.
    body_split = re.split(r"(?=^- \[)", existing, maxsplit=1, flags=re.MULTILINE)
    header = body_split[0] if len(body_split) > 1 else existing or _FILE_HEADER
    entries_text = body_split[1] if len(body_split) > 1 else ""
    entries = _split_entries(entries_text)

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

    WARNINGS_FILE.write_text(header + "\n".join(b.rstrip() for b in refreshed_entries) + "\n", encoding="utf-8")

    notification = (
        f"⚠️  LGPD concern flagged: **{concern}** at `{code_path}`. "
        f"Recorded in `{WARNINGS_FILE.name}`. This does NOT block; "
        f"review the file before the feature is called done."
    )
    return {
        "notification": notification,
        "warnings_file": str(WARNINGS_FILE.relative_to(REPO_ROOT)),
        "concern": concern,
        "code_path": code_path,
        "reason": reason,
        "mitigation": mitigation,
        "deduped": deduped,
        "count_total": len(refreshed_entries),
    }


def list_warnings() -> dict:
    """Return the current state of `LGPD-WARNINGS.md` as structured data."""
    if not WARNINGS_FILE.exists():
        return {"file": str(WARNINGS_FILE.relative_to(REPO_ROOT)), "entries": []}

    content = WARNINGS_FILE.read_text(encoding="utf-8")
    entries: list[dict] = []
    for m in _ENTRY_RE.finditer(content):
        entries.append({
            "concern": m.group("concern"),
            "code_path": m.group("path"),
            "resolved": m.group("checked") == "x",
        })
    return {
        "file": str(WARNINGS_FILE.relative_to(REPO_ROOT)),
        "entries": entries,
        "unresolved_count": sum(1 for e in entries if not e["resolved"]),
        "resolved_count": sum(1 for e in entries if e["resolved"]),
    }


def register(server) -> None:
    @server.tool(
        name="noctusai_lgpd_flag",
        description=(
            "Record an unresolved LGPD concern in `LGPD-WARNINGS.md`. Call whenever "
            "data-touching code raises an LGPD question (retention unclear, 3rd-party "
            "egress, cache of patient text, cross-product leak, …). DOES NOT BLOCK — "
            "appends a checklist item and notifies the user. Returns a user-facing "
            "notification string the caller should surface."
        ),
    )
    def _lgpd_flag(
        code_path: str,
        concern: str,
        reason: str,
        mitigation: str | None = None,
    ) -> dict:
        return flag(
            code_path=code_path,
            concern=concern,
            reason=reason,
            mitigation=mitigation,
        )

    @server.tool(
        name="noctusai_lgpd_list",
        description="List all LGPD concerns from `LGPD-WARNINGS.md` (unresolved + resolved).",
    )
    def _lgpd_list() -> dict:
        return list_warnings()
