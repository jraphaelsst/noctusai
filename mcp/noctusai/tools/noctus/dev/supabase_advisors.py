"""`noctus.dev.supabase_advisors` — filter-proxy over Supabase MCP `get_advisors`.

**Why this tool exists.** The Supabase MCP `get_advisors(project_id, type)`
returns *every* advisor at the project scope — for an active project, this
balloons to 100KB-500KB (Engineer Z's imobi P3 close hit 138KB security +
393KB performance). That overflows Anthropic's tool-result cap, so the
caller can't even see the lints they asked for.

**The cut.** We do *not* recursively call the Supabase MCP from inside the
noc MCP (no MCP-to-MCP infrastructure exists in noc, and chaining MCP
clients through stdio would add a runtime dependency for one tool). Instead
this proxy is a **client-side filter** that accepts the raw advisor dump
two ways:

  1. ``advisors_jsonl_path=`` — path to a file the caller saved beforehand
     (one JSON object per line, OR a single JSON object/array). The caller
     pipes Supabase MCP output through ``echo / jq / tee`` to disk first,
     dodging the cap because the dump goes through the filesystem rather
     than through Claude's tool-result channel.
  2. ``advisors_raw=`` — a Python list[dict] for direct programmatic use
     (smoke tests, fixtures, future MCP-from-MCP wiring).

Either way, filters fire **server-side BEFORE returning**, so what comes
back is small enough to fit (~≤10KB for typical product schemas).

**Filters.**
  - ``schema=`` — keep only rows whose ``metadata.schema`` matches.
  - ``severity=`` — list[Literal["ERROR", "WARN", "INFO"]] (Supabase calls
    this ``level``; we normalize to uppercase).
  - ``type=`` — ``security`` / ``performance`` / ``all``. The Supabase MCP
    splits by ``type``; if the caller dumped both into one file we filter
    here. Default ``all``.
  - ``drop_unused_index_for_new_schemas=True`` — drop ``unused_index`` lints
    for schemas the caller flags as fresh (no traffic baseline). Currently
    a hard pass-through: drop when ``name == "unused_index"`` AND the
    caller passed any non-None ``schema=`` (fresh-schema audits are the
    primary trigger). Future iterations can take a ``new_schemas=list``
    parameter for finer control.

**Return shape.** ``list[dict]`` (Pydantic-validated ``AdvisorResult``
serialized via ``model_dump``). Matches PROJECT.md §5.

**Worktree-aware.** Accepts ``worktree_path`` per
``feedback_mcp_write_tools_resolve_caller_root.md`` even though this is a
read-only tool — sets the precedent and keeps relative ``advisors_jsonl_path``
inputs anchored to the caller's worktree, not the MCP server's startup root.

Full convention: KB § PATTERNS/mcp-tool-conventions.md.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from workspace import resolve_caller_root

logger = logging.getLogger(__name__)


# ── Pydantic shapes ────────────────────────────────────────────────────


class AdvisorResult(BaseModel):
    """Filtered Supabase advisor row.

    Shape matches Supabase's underlying lints API, normalized for
    consumption by audit / drift / security tooling.

    Note: the ``schema`` field shadows ``BaseModel.schema()`` (a deprecated
    Pydantic v1 method) — Pydantic emits a UserWarning at class-creation
    time, but model behavior is correct (instance access + ``model_dump``
    both work as expected). Renaming is not warranted; PROJECT.md §5
    locks the field name to ``schema``.
    """

    severity: Literal["ERROR", "WARN", "INFO"] = Field(
        description="Severity level (Supabase ``level`` normalized uppercase)."
    )
    category: str = Field(
        description=(
            "Advisor category — first entry of Supabase's ``categories`` "
            "list, or empty string if absent."
        )
    )
    schema: Optional[str] = Field(
        default=None, description="Affected schema name, if scoped."
    )
    table: Optional[str] = Field(
        default=None, description="Affected table name, if scoped."
    )
    name: str = Field(
        description="Advisor lint name (e.g. ``unindexed_foreign_keys``)."
    )
    message: str = Field(
        description=(
            "Short human-readable description. We use Supabase's "
            "``title`` field when present, falling back to ``description``."
        )
    )
    suggested_action: Optional[str] = Field(
        default=None,
        description=(
            "Remediation hint — Supabase's ``remediation`` (URL or text) "
            "or ``detail`` if remediation is absent. ``None`` when neither."
        ),
    )


# ── Normalization (Supabase raw → AdvisorResult) ───────────────────────


def _normalize_row(raw: dict[str, Any]) -> Optional[AdvisorResult]:
    """Convert one Supabase advisor row into an ``AdvisorResult``.

    Returns ``None`` if the row is malformed (missing required fields).
    We log at WARNING — never raise — so a single bad row doesn't kill
    the whole batch.
    """
    try:
        level = str(raw.get("level", "")).upper()
        if level not in {"ERROR", "WARN", "INFO"}:
            # Supabase sometimes emits "WARNING" — normalize.
            if level == "WARNING":
                level = "WARN"
            else:
                logger.warning(
                    "supabase_advisors: unknown level %r in row %r — skipping",
                    level,
                    raw.get("name"),
                )
                return None

        name = raw.get("name")
        if not name:
            logger.warning("supabase_advisors: row missing ``name`` — skipping")
            return None

        categories = raw.get("categories") or []
        category = categories[0] if categories else ""

        metadata = raw.get("metadata") or {}
        schema = metadata.get("schema") if isinstance(metadata, dict) else None
        table = metadata.get("table") if isinstance(metadata, dict) else None

        message = raw.get("title") or raw.get("description") or ""

        suggested_action = raw.get("remediation") or raw.get("detail")
        if not suggested_action:
            suggested_action = None

        return AdvisorResult(
            severity=level,  # type: ignore[arg-type]
            category=category,
            schema=schema,
            table=table,
            name=str(name),
            message=str(message),
            suggested_action=str(suggested_action) if suggested_action else None,
        )
    except Exception as exc:  # noqa: BLE001 — explicit log, then skip
        logger.warning(
            "supabase_advisors: failed to normalize row %r: %s",
            raw.get("name", "<unknown>"),
            exc,
        )
        return None


# ── JSONL loader ───────────────────────────────────────────────────────


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read advisor rows from a JSONL or JSON file.

    Accepts three shapes:
      - One JSON object per line (true JSONL).
      - A single JSON array of objects.
      - A single JSON object with ``lints`` / ``advisors`` / ``result`` key
        holding the array (Supabase MCP wraps responses this way).

    Raises ``FileNotFoundError`` if the path doesn't exist. Raises
    ``ValueError`` on parse failure (caller decides how to surface).
    """
    if not path.exists():
        raise FileNotFoundError(f"advisors JSONL path not found: {path}")

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    # Try JSONL first (each line is a complete JSON object).
    if "\n" in text and text.lstrip().startswith("{"):
        try:
            rows: list[dict[str, Any]] = []
            for lineno, line in enumerate(text.splitlines(), start=1):
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
                else:
                    logger.warning(
                        "supabase_advisors: JSONL line %d is not an object — skipping",
                        lineno,
                    )
            if rows:
                return rows
        except json.JSONDecodeError:
            pass  # fall through to single-document parse

    # Single JSON document.
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"advisors file is not valid JSON or JSONL: {exc}") from exc

    if isinstance(doc, list):
        return [row for row in doc if isinstance(row, dict)]

    if isinstance(doc, dict):
        # Common Supabase MCP wrappers.
        for key in ("lints", "advisors", "result", "data"):
            inner = doc.get(key)
            if isinstance(inner, list):
                return [row for row in inner if isinstance(row, dict)]
        # Single advisor row.
        return [doc]

    raise ValueError(
        f"advisors file root must be array/object/JSONL, got {type(doc).__name__}"
    )


# ── Filter logic ───────────────────────────────────────────────────────


def _filter_rows(
    rows: list[AdvisorResult],
    *,
    schema: Optional[str],
    severity: Optional[list[str]],
    type_: str,
    drop_unused_index_for_new_schemas: bool,
) -> list[AdvisorResult]:
    """Apply the four filters in a deterministic order.

    Order: schema → severity → type → unused_index drop. Each filter is
    a pure predicate; order doesn't change the result set but does change
    debuggability when an audit asks "why did this row survive?".
    """
    out = rows

    if schema is not None:
        out = [r for r in out if r.schema == schema]

    if severity:
        sev_set = {s.upper() for s in severity}
        out = [r for r in out if r.severity in sev_set]

    # ``type`` filter — we keep ``all`` as a no-op since the underlying
    # Supabase MCP call already scopes by type. If the caller dumped both
    # security + performance into one file, they pass ``type="security"``
    # to slice. Heuristic: ``unused_index`` + perf categories on the
    # ``performance`` side; everything else maps to ``security`` (most
    # lints).
    _PERFORMANCE_LINTS: set[str] = {
        "unused_index",
        "unindexed_foreign_keys",
        "duplicate_index",
        "no_primary_key",
        "multiple_permissive_policies",
    }
    if type_ == "security":
        out = [r for r in out if r.name not in _PERFORMANCE_LINTS]
    elif type_ == "performance":
        out = [r for r in out if r.name in _PERFORMANCE_LINTS]
    # type_ == "all" → no filter

    if drop_unused_index_for_new_schemas and schema is not None:
        # Caller passed a specific schema → treat as fresh-audit context.
        out = [r for r in out if r.name != "unused_index"]

    return out


# ── Public entrypoint ──────────────────────────────────────────────────


def supabase_advisors(
    *,
    advisors_jsonl_path: Optional[str] = None,
    advisors_raw: Optional[list[dict[str, Any]]] = None,
    schema: Optional[str] = None,
    severity: Optional[list[str]] = None,
    type: str = "all",
    drop_unused_index_for_new_schemas: bool = True,
    worktree_path: Optional[str] = None,
) -> dict[str, Any]:
    """Filter a Supabase advisor dump server-side.

    Exactly one of ``advisors_jsonl_path`` or ``advisors_raw`` must be set.

    Returns a dict::

        {
            "advisors": [AdvisorResult.model_dump(), …],
            "total": <int — count after filtering>,
            "input_total": <int — count before filtering>,
            "source": "jsonl" | "raw",
            "filters_applied": {schema, severity, type, drop_unused_index_for_new_schemas},
        }

    No silent errors: missing/conflicting inputs → ``ValueError``. Bad rows
    inside the dump are logged + skipped (per-row tolerance).
    """
    if (advisors_jsonl_path is None) == (advisors_raw is None):
        raise ValueError(
            "supabase_advisors: pass exactly one of "
            "``advisors_jsonl_path`` or ``advisors_raw`` (got "
            f"{'both' if advisors_jsonl_path is not None else 'neither'})"
        )

    if type not in {"security", "performance", "all"}:
        raise ValueError(
            f"supabase_advisors: invalid type={type!r}; "
            "valid: 'security' / 'performance' / 'all'"
        )

    # Load raw rows
    raw_rows: list[dict[str, Any]]
    source: str
    if advisors_jsonl_path is not None:
        caller_root = resolve_caller_root(worktree_path)
        path = Path(advisors_jsonl_path)
        if not path.is_absolute():
            path = caller_root / path
        raw_rows = _load_jsonl(path)
        source = "jsonl"
    else:
        assert advisors_raw is not None  # mypy
        raw_rows = list(advisors_raw)
        source = "raw"

    # Normalize → AdvisorResult
    normalized: list[AdvisorResult] = []
    for row in raw_rows:
        ar = _normalize_row(row)
        if ar is not None:
            normalized.append(ar)

    input_total = len(normalized)

    # Filter
    filtered = _filter_rows(
        normalized,
        schema=schema,
        severity=severity,
        type_=type,
        drop_unused_index_for_new_schemas=drop_unused_index_for_new_schemas,
    )

    return {
        "advisors": [r.model_dump() for r in filtered],
        "total": len(filtered),
        "input_total": input_total,
        "source": source,
        "filters_applied": {
            "schema": schema,
            "severity": severity,
            "type": type,
            "drop_unused_index_for_new_schemas": drop_unused_index_for_new_schemas,
        },
    }


# ── MCP registration ───────────────────────────────────────────────────


def register(server) -> None:
    @server.tool(
        name="noctus.dev.supabase_advisors",
        description=(
            "Filter-proxy over Supabase MCP `get_advisors` to dodge Anthropic's "
            "tool-result cap. Accepts EITHER `advisors_jsonl_path=` (file the "
            "caller saved beforehand via `mcp__claude_ai_Supabase__get_advisors "
            "| jq … > file`) OR `advisors_raw=` (inline list of dicts). Filters "
            "server-side by `schema=` / `severity=` / `type=` "
            "(security|performance|all). Set `drop_unused_index_for_new_schemas` "
            "False to keep `unused_index` lints on schemas without traffic. Pass "
            "`worktree_path` so relative paths anchor to the caller's worktree."
        ),
    )
    def _supabase_advisors(
        advisors_jsonl_path: str | None = None,
        advisors_raw: list[dict[str, Any]] | None = None,
        schema: str | None = None,
        severity: list[str] | None = None,
        type: str = "all",
        drop_unused_index_for_new_schemas: bool = True,
        worktree_path: str | None = None,
    ) -> dict[str, Any]:
        return supabase_advisors(
            advisors_jsonl_path=advisors_jsonl_path,
            advisors_raw=advisors_raw,
            schema=schema,
            severity=severity,
            type=type,
            drop_unused_index_for_new_schemas=drop_unused_index_for_new_schemas,
            worktree_path=worktree_path,
        )
