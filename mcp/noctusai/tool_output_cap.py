"""ONE cap for every toolkit tool's result: over the limit it becomes a compact summary + the path of the full JSON.

A tool result over the client's cap is dropped or rejected whole, and the caller cannot tell "empty" from "too
big" (`noctus.dev.session_end_sweep` returned ~150k chars on 2026-11-14/15). The fix is by construction, not
per tool: `install_output_cap(server)` wraps the tool manager's `call_tool` (after `register_all`, beside
`install_strict_tool_arguments`), so a tool added tomorrow is capped too. A tool that can shrink its own result
meaningfully (the sweep) still does so itself; this is the net behind it.

Nothing is lost and nothing is silent: the FULL value is written to `~/.noctus/tool-output/<tool>-<utc>-<pid>.json`
(0600; newest 50 kept) and the result names that path. When the file cannot be written the summary says so.

Stdlib only. KB § PATTERNS/architect/mcp-tool-conventions.md (output cap).
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: A client's tool-result window is ~25k tokens (~100k chars); half of that leaves room for the envelope.
DEFAULT_CAP_CHARS = 50_000
CAP_ENV = "NOCTUS_TOOL_OUTPUT_CAP_CHARS"
OUT_DIR_ENV = "NOCTUS_TOOL_OUTPUT_DIR"
KEEP_DEFAULT = 50
_PREVIEW_CHARS = 1_500

__all__ = ["CAP_ENV", "DEFAULT_CAP_CHARS", "OUT_DIR_ENV", "cap_limit", "cap_value", "default_out_dir", "install_output_cap",
           "write_full_output"]


def cap_limit() -> int:
    raw = os.environ.get(CAP_ENV, "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else DEFAULT_CAP_CHARS


def default_out_dir() -> Path:
    override = os.environ.get(OUT_DIR_ENV, "").strip()
    return Path(override) if override else Path.home() / ".noctus" / "tool-output"


def _dumps(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)


def write_full_output(tool: str, value: Any, out_dir: Path | None = None, *, keep: int = KEEP_DEFAULT) -> tuple[Path | None, str]:
    """Write `value` as JSON under `out_dir`. Returns `(path, "")` or `(None, why)`; prunes to the newest `keep`."""
    d = Path(out_dir) if out_dir is not None else default_out_dir()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", tool).strip("_") or "tool"
    try:
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{stem}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}-{os.getpid()}.json"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(value, default=str, ensure_ascii=False, indent=1))
        files = sorted(d.glob("*.json"), key=lambda p: (p.stat().st_mtime, p.name))
        for old in files[:-keep] if keep > 0 else []:
            try:
                old.unlink()
            except OSError:
                pass
        return path, ""
    except OSError as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _shape(v: Any) -> str:
    if isinstance(v, list):
        return f"list[{len(v)}]"
    if isinstance(v, dict):
        return f"dict[{len(v)}]"
    if isinstance(v, str):
        return f"str[{len(v)}]"
    return type(v).__name__


def cap_value(tool: str, value: Any, *, limit: int | None = None, out_dir: Path | None = None, keep: int = KEEP_DEFAULT) -> Any:
    """`value` itself when its JSON fits `limit`; else a compact summary naming the file that holds all of it."""
    cap = cap_limit() if limit is None else limit
    text = _dumps(value)
    if len(text) <= cap:
        return value
    path, why = write_full_output(tool, value, out_dir, keep=keep)
    summary: dict[str, Any] = {
        "ok": value.get("ok", True) if isinstance(value, dict) else True,
        "truncated": True,
        "tool": tool,
        "chars": len(text),
        "cap_chars": cap,
        "full_output_path": str(path) if path else None,
        "how_to_read": (f"the FULL result is the JSON file at full_output_path; read it with `jq` or Read (offset/limit), "
                        f"e.g. `jq 'keys' <path>`" if path else "the full result could not be saved"),
    }
    if isinstance(value, dict):
        summary["top_level"] = {k: _shape(v) for k, v in list(value.items())[:60]}
        scalars = {k: v for k, v in value.items() if isinstance(v, (bool, int, float)) or (isinstance(v, str) and len(v) <= 160)}
        if scalars:
            summary["scalars"] = dict(list(scalars.items())[:30])
    elif isinstance(value, list):
        summary["top_level"] = {"items": _shape(value)}
    summary["preview"] = text[:_PREVIEW_CHARS]
    if not path:
        summary["error"] = f"the full output could not be saved ({why}); only the preview above is available - re-run with narrower arguments"
    return summary


def _blocks_text(result: Any) -> tuple[str, list[Any]] | None:
    """`(joined text, blocks)` when `result` is a sequence of MCP text content blocks (the wire shape), else None."""
    blocks = result[0] if isinstance(result, tuple) and result and isinstance(result[0], (list, tuple)) else result
    if isinstance(blocks, (list, tuple)) and blocks and all(hasattr(b, "text") and hasattr(b, "type") for b in blocks):
        return "".join(b.text for b in blocks), list(blocks)
    return None


def install_output_cap(server: Any, *, limit: int | None = None) -> None:
    """Wrap the server's tool manager so no tool result exceeds the cap. Call AFTER `register_all`."""
    manager = server._tool_manager
    inner = manager.call_tool

    async def _capped_call_tool(name, arguments, *args, **kwargs):
        result = await inner(name, arguments, *args, **kwargs)
        cap = cap_limit() if limit is None else limit
        wire = _blocks_text(result)
        if wire is not None:
            text, blocks = wire
            if len(text) <= cap:
                return result
            try:
                parsed: Any = json.loads(text)
            except ValueError:
                parsed = text
            from mcp.types import TextContent  # noqa: PLC0415 - only the wire path needs the SDK type

            return [TextContent(type="text", text=_dumps(cap_value(name, parsed, limit=cap)))]
        if isinstance(result, (dict, list)):
            return cap_value(name, result, limit=cap)
        return result

    _capped_call_tool._noc_output_cap = True  # type: ignore[attr-defined]
    manager.call_tool = _capped_call_tool  # type: ignore[method-assign]
