"""Adapter for Claude Code's local JSONL session transcripts.

Single concern: parse one session file into a stable, internal `Event`
list that detectors can walk without ever touching the raw JSONL keys.
This is the only module that depends on Anthropic's undocumented Claude
Code session-log schema. When fields rename, the fix lives here.

**Privacy:** the adapter NEVER carries user/assistant message text into
its return shape. Only `tool_use` and `tool_result` blocks are surfaced;
within those, only the structural fields detectors need (paths, tool
names, input dicts, content size, error flag). See
`projects/session-review-baseline/PROJECT.md § 3` principle 5.

**Phase 0 audit findings (2026-05-03):** tool_use ↔ tool_result pairing
across 5 real sessions had zero orphans (n=669 pairs). The Phase 0 audit
also catalogued non-`assistant`/`user` record types that we ignore:
`permission-mode`, `system`, `attachment`, `ai-title`, `last-prompt`,
`file-history-snapshot`, `queue-operation`. Anything we don't recognize
is silently skipped — that is the documented format-drift survival
strategy.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Union

logger = logging.getLogger(__name__)

DEFAULT_JSONL_DIR = (
    Path.home()
    / ".claude"
    / "projects"
    / "-Users-rapha-Documents-repository-NoctusAI-noctusai"
)


@dataclass(frozen=True)
class ToolUse:
    line_no: int           # 1-based JSONL line where the tool_use lives
    id: str                # `toolu_…` (the JSONL's tool_use id)
    name: str              # "Read", "Edit", "Bash", …
    input: dict            # the tool's input dict (paths, commands, …)


@dataclass(frozen=True)
class ToolResult:
    line_no: int
    tool_use_id: str       # pair-key back to ToolUse.id
    content_size: int      # len of the result content (size heuristic)
    is_error: bool


Event = Union[ToolUse, ToolResult]


def load_session(path: Path) -> list[Event]:
    """Parse a Claude Code JSONL session into an ordered Event list.

    Returns events in JSONL line order. Skips records that are not
    `assistant` or `user` (session metadata, attachments, etc.). Within
    each kept record, walks `message.content[]` and emits one Event per
    `tool_use` / `tool_result` block.

    Raises:
        FileNotFoundError: if `path` does not exist.
        ValueError: if the file is not valid JSONL (one record per line).
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Session JSONL not found: {p}")

    events: list[Event] = []
    with p.open("r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{p.name}:{line_no}: malformed JSONL: {exc.msg}"
                ) from exc
            events.extend(_extract_events(record, line_no))
    return events


def _extract_events(record: dict, line_no: int) -> Iterator[Event]:
    rtype = record.get("type")
    if rtype == "assistant":
        msg = record.get("message") or {}
        for block in msg.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                yield ToolUse(
                    line_no=line_no,
                    id=str(block.get("id", "")),
                    name=str(block.get("name", "")),
                    input=block.get("input") or {},
                )
    elif rtype == "user":
        msg = record.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, list):
            return
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                raw_content = block.get("content")
                yield ToolResult(
                    line_no=line_no,
                    tool_use_id=str(block.get("tool_use_id", "")),
                    content_size=_content_size(raw_content),
                    is_error=bool(block.get("is_error", False)),
                )


def _content_size(content) -> int:
    """Heuristic byte-ish size of a tool_result.content blob.

    Detectors only ever see the size, never the body. Strings → len; lists
    of blocks → sum of inner text lengths; anything else → 0. Kept simple
    on purpose — this is a tripwire signal, not a measurement.
    """
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        total = 0
        for block in content:
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    total += len(text)
        return total
    return 0


def latest_session_path(jsonl_dir: Path | None = None) -> Path:
    """Return the most-recently-modified `.jsonl` in `jsonl_dir`.

    Defaults to `DEFAULT_JSONL_DIR`. Raises `FileNotFoundError` when the
    directory is missing or empty (the explicit `--path` form is the
    safety net for non-macOS callers — see `PROJECT.md § 2 / § 7 Q1`).
    """
    d = jsonl_dir or DEFAULT_JSONL_DIR
    if not d.exists():
        raise FileNotFoundError(
            f"Default JSONL dir not found: {d}. "
            "Pass an explicit --path on non-macOS hosts."
        )
    candidates = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No .jsonl files in {d}")
    return candidates[0]
