"""``noctus.dev.organ_knowledge_append`` / ``_query`` — the build-learn-cache loop for organs.

Purpose (PROJECT.md seed-organs-cache §3a + W5)
------------------------------------------------
Every registered organ carries an 8-field knowledge bundle in its
``<Name>.organ.yaml`` sidecar (the journey, not just the artifact):

    known_facts · errors_encountered · drifts_surfaced · alternatives_considered
    manual_validation_log · integration_test_status · e2e_test · bugs_fixed_during_dev

These tools let any builder APPEND to that journey during dev AND beyond
(refactor / bug-fix / integration touch-up / deploy) and QUERY it back so a
future builder sees "what did we learn building X" without reading commit logs.

The re-embed contract (§3b W5 — LOAD-BEARING)
----------------------------------------------
``organ_knowledge_append`` runs the embedding refresh INLINE (synchronous) by
calling ``register_organ(name, force=True)``: an agent querying
``find_reusable_component`` right after a ``manual_validation_log`` entry MUST
see the new content. The cache reflects the journey AS IT HAPPENS, not at
project close. The organ chunk's ``source_sha`` already hashes the knowledge
bundle (find_reusable_component._build_organ_chunk), so the re-embed is
idempotent + correct by construction.

KB § PATTERNS/common/build-learn-cache-mindset.md
KB § PATTERNS/architect/seed-organ-canonical-set.md
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import yaml  # PyYAML — available in the venv (used by sibling organ tools)

from settings import REPO_ROOT

# Reuse the W4 sidecar locators + the re-embed entry point (DRY — one source of
# truth for "where does an organ.yaml live" and "how does an organ re-embed").
from .find_reusable_component import (
    _find_organ_yaml,
    _load_organ_yaml,
    register_organ,
)

logger = logging.getLogger(__name__)


# ── Knowledge-field taxonomy (the 8 fields, by mutation shape) ─────────────────

# List fields: an append pushes the entry onto the list.
LIST_FIELDS = {
    "known_facts",
    "errors_encountered",
    "drifts_surfaced",
    "alternatives_considered",
    "manual_validation_log",
    "bugs_fixed_during_dev",
}
# Scalar fields: an "append" SETS the value (latest-wins).
SCALAR_FIELDS = {"integration_test_status"}
# Object fields: an "append" MERGES the dict entry into the existing object.
OBJECT_FIELDS = {"e2e_test"}

KNOWLEDGE_FIELDS = LIST_FIELDS | SCALAR_FIELDS | OBJECT_FIELDS

# The non-knowledge metadata fields a sidecar carries (echoed back by query).
META_FIELDS = ("name", "path", "phase", "registered_at", "validation_status")


# ── Sidecar IO ─────────────────────────────────────────────────────────────────


def _write_organ_yaml(sidecar_path: Path, data: dict) -> None:
    """Persist the full sidecar dict, preserving field order (sort_keys=False)."""
    text = yaml.safe_dump(
        data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    sidecar_path.write_text(text, encoding="utf-8")


# ── Public write path: organ_knowledge_append ─────────────────────────────────


def organ_knowledge_append(
    name: str,
    field: str,
    entry: Any,
    *,
    re_embed: bool = True,
    repo_root: Path | None = None,
) -> dict:
    """Append/set a knowledge entry on an organ's sidecar, then re-embed inline.

    Parameters
    ----------
    name:
        Organ name (e.g. ``"LoginForm"``).
    field:
        One of the 8 knowledge fields (see ``KNOWLEDGE_FIELDS``).
    entry:
        The value to append/set. For LIST fields it is pushed onto the list
        (str or dict — e.g. a ``manual_validation_log`` entry is a dict). For
        SCALAR fields it sets the value. For OBJECT fields it must be a dict
        and is merged into the existing object.
    re_embed:
        When True (default), re-embed the organ chunk synchronously via
        ``register_organ(force=True)`` so the search index reflects the new
        knowledge immediately (the §3b W5 contract). Set False to batch.
    repo_root:
        Override repo root (mainly for testing).

    Returns ``{ok, name, field, action, re_embedded, source_sha, status}``.
    """
    root = repo_root or REPO_ROOT

    if field not in KNOWLEDGE_FIELDS:
        return {
            "ok": False,
            "status": f"unknown-field: {field!r} not in {sorted(KNOWLEDGE_FIELDS)}",
            "name": name,
            "field": field,
        }

    sidecar = _find_organ_yaml(name, root)
    if sidecar is None:
        return {
            "ok": False,
            "status": "organ-not-found",
            "name": name,
            "field": field,
        }

    data = _load_organ_yaml(name, root)
    if not data:
        return {
            "ok": False,
            "status": "organ-yaml-empty-or-unparseable",
            "name": name,
            "field": field,
        }

    # Mutate per field shape.
    if field in LIST_FIELDS:
        existing = data.get(field)
        if existing is None:
            existing = []
        if not isinstance(existing, list):
            return {
                "ok": False,
                "status": f"field-shape-mismatch: {field!r} is not a list in the sidecar",
                "name": name,
                "field": field,
            }
        existing.append(entry)
        data[field] = existing
        action = "appended"
    elif field in SCALAR_FIELDS:
        data[field] = entry
        action = "set"
    else:  # OBJECT_FIELDS
        if not isinstance(entry, dict):
            return {
                "ok": False,
                "status": f"object-field-needs-dict: {field!r} requires a dict entry",
                "name": name,
                "field": field,
            }
        existing = data.get(field)
        if not isinstance(existing, dict):
            existing = {}
        existing.update(entry)
        data[field] = existing
        action = "merged"

    _write_organ_yaml(sidecar, data)

    # Inline re-embed — the build-learn-cache feedback closure (§3b W5).
    re_embedded = False
    source_sha = ""
    embed_status = "skipped"
    if re_embed:
        try:
            result = register_organ(name, force=True, repo_root=root)
            re_embedded = bool(result.get("ok"))
            source_sha = result.get("source_sha", "")
            embed_status = result.get("status", "unknown")
        except Exception as exc:  # surface, do not swallow — the write already landed
            logger.warning("organ_knowledge_append: re-embed failed for %r: %s", name, exc)
            embed_status = f"embed-error: {exc}"

    return {
        "ok": True,
        "status": "ok",
        "name": name,
        "field": field,
        "action": action,
        "re_embedded": re_embedded,
        "embed_status": embed_status,
        "source_sha": source_sha,
    }


# ── Public read path: organ_knowledge_query ───────────────────────────────────


def organ_knowledge_query(
    name: str,
    *,
    repo_root: Path | None = None,
) -> dict:
    """Return an organ's accumulated journey — the 8 knowledge fields + metadata.

    Returns ``{ok, name, path, validation_status, registered_at, phase,
    known_facts, errors_encountered, drifts_surfaced, alternatives_considered,
    manual_validation_log, integration_test_status, e2e_test,
    bugs_fixed_during_dev}`` — or ``{ok: False, status: 'organ-not-found'}``.
    """
    root = repo_root or REPO_ROOT

    sidecar = _find_organ_yaml(name, root)
    if sidecar is None:
        return {"ok": False, "status": "organ-not-found", "name": name}

    data = _load_organ_yaml(name, root)
    if not data:
        return {"ok": False, "status": "organ-yaml-empty-or-unparseable", "name": name}

    out: dict[str, Any] = {"ok": True, "status": "ok", "name": name}
    for key in META_FIELDS:
        if key in data:
            out[key] = data[key]
    # Knowledge fields — emit all 8 with defaults so the shape is stable.
    for key in LIST_FIELDS:
        out[key] = data.get(key) or []
    for key in SCALAR_FIELDS:
        out[key] = data.get(key, "unknown")
    for key in OBJECT_FIELDS:
        out[key] = data.get(key) or {}
    return out


# ── MCP registration ──────────────────────────────────────────────────────────


def register(server) -> None:
    @server.tool(
        name="noctus.dev.organ_knowledge_append",
        description=(
            "Append a knowledge entry to a registered seed organ's journey and "
            "re-embed it inline. ``field`` is one of: known_facts, "
            "errors_encountered, drifts_surfaced, alternatives_considered, "
            "manual_validation_log, integration_test_status, e2e_test, "
            "bugs_fixed_during_dev. List fields append; integration_test_status "
            "sets; e2e_test merges (pass entry_json). For plain entries pass "
            "``entry`` (a string); for structured entries (manual_validation_log "
            "dict, e2e_test object) set ``entry_json=true`` and pass JSON in "
            "``entry``. Re-embeds via register_organ(force=True) so "
            "find_reusable_component sees the new knowledge immediately "
            "(set re_embed=false to batch). "
            "Returns {ok, name, field, action, re_embedded, source_sha}. "
            "KB § PATTERNS/common/build-learn-cache-mindset.md"
        ),
    )
    def _organ_knowledge_append(
        name: str,
        field: str,
        entry: str,
        entry_json: bool = False,
        re_embed: bool = True,
    ) -> dict:
        import json as _json
        value: Any = entry
        if entry_json:
            try:
                value = _json.loads(entry)
            except (ValueError, TypeError) as exc:
                return {
                    "ok": False,
                    "status": f"entry-json-parse-error: {exc}",
                    "name": name,
                    "field": field,
                }
        return organ_knowledge_append(name, field, value, re_embed=re_embed)

    @server.tool(
        name="noctus.dev.organ_knowledge_query",
        description=(
            "Return a seed organ's accumulated build-learn-cache journey — the "
            "8 knowledge fields (known_facts, errors_encountered, "
            "drifts_surfaced, alternatives_considered, manual_validation_log, "
            "integration_test_status, e2e_test, bugs_fixed_during_dev) plus "
            "metadata (path, validation_status, registered_at, phase). "
            "Answers 'what did we learn building X' without reading commit logs. "
            "Returns {ok, ...} or {ok: false, status: 'organ-not-found'}."
        ),
    )
    def _organ_knowledge_query(name: str) -> dict:
        return organ_knowledge_query(name)


__all__ = [
    "LIST_FIELDS",
    "SCALAR_FIELDS",
    "OBJECT_FIELDS",
    "KNOWLEDGE_FIELDS",
    "META_FIELDS",
    "organ_knowledge_append",
    "organ_knowledge_query",
    "register",
]
