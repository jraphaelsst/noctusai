"""Vendored-OpenAPI-spec reader — the zero-IO substrate for `trello.contract.*`.

Every `trello.contract.*` tool reads `contract/swagger.v3.json`
(`mcp/trello/contract/PROVENANCE.md` records its source + fetch date +
sha256) through this module. No network call, no credentials — the whole
point of the contract-tools surface is that it works **forever**, offline,
regardless of whether `TRELLO_API_KEY`/`TRELLO_TOKEN` are set.

Named `spec.py`, NOT `contract.py` — `contract/` is a data directory
(the vendored JSON + its provenance doc), not a Python package, and a
`contract.py` module living beside a `contract/` directory in the same
parent package is an avoidable ambiguity for no benefit.

Deliberately named `TrelloList` in Trello's own schema — `List` is too
generic a name to trust as a bare dict key lookup, so we use the same
convention here (`schema("TrelloList")`, not `schema("List")`).
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

SPEC_PATH = Path(__file__).resolve().parent / "contract" / "swagger.v3.json"

_ROOT_RESOURCE_RE = re.compile(r"^/([a-zA-Z]+)")
_HTTP_METHODS = ("get", "post", "put", "delete", "patch")


class SpecNotFoundError(Exception):
    """The vendored spec file is missing. Never silently returns an empty
    catalog — a missing contract file is a broken install, not "no
    endpoints exist"."""


@lru_cache(maxsize=1)
def load_spec() -> dict[str, Any]:
    """Parse and cache `contract/swagger.v3.json`. Process-lifetime cache
    (the file only changes via a deliberate vendoring refresh, never at
    runtime) — mirrors the `lru_cache(maxsize=1)` shape `_kit.settings`
    uses for `get_settings()`."""
    if not SPEC_PATH.exists():
        raise SpecNotFoundError(
            f"Vendored Trello spec not found at {SPEC_PATH} — see "
            "mcp/trello/contract/PROVENANCE.md § Refreshing this file."
        )
    import json

    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def resource_of(path: str) -> str:
    """The root path segment used for grouping/filtering (`/cards/{id}`
    → `cards`). Matches the classification the vendored PROVENANCE.md
    per-resource table was computed with."""
    m = _ROOT_RESOURCE_RE.match(path)
    return m.group(1) if m else path


def operations() -> list[dict[str, Any]]:
    """Every operation in the spec, flattened to one row each:
    `{method, path, resource, operation_id, summary, description}`.
    Order: spec path order, then HTTP-method order (get/post/put/delete/
    patch) — stable across calls (the spec's own dict order, which
    Python preserves)."""
    spec = load_spec()
    rows: list[dict[str, Any]] = []
    for path, methods in spec.get("paths", {}).items():
        for method in _HTTP_METHODS:
            op = methods.get(method)
            if op is None:
                continue
            rows.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "resource": resource_of(path),
                    "operation_id": op.get("operationId"),
                    "summary": op.get("summary", ""),
                    "description": op.get("description", ""),
                }
            )
    return rows


def find_operation(
    *,
    method: Optional[str] = None,
    path: Optional[str] = None,
    operation_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Resolve one operation by (method + path) OR by operation_id.
    Returns the RAW spec operation object (unflattened — parameters,
    requestBody, responses intact) plus `method`/`path`, or `None` when
    no operation matches (the caller decides how to report that)."""
    spec = load_spec()
    if operation_id:
        for p, methods in spec.get("paths", {}).items():
            for m, op in methods.items():
                if m in _HTTP_METHODS and op.get("operationId") == operation_id:
                    return {**op, "method": m.upper(), "path": p}
        return None
    if not method or not path:
        return None
    op = spec.get("paths", {}).get(path, {}).get(method.lower())
    if op is None:
        return None
    return {**op, "method": method.upper(), "path": path}


def schemas() -> dict[str, Any]:
    """`components.schemas` verbatim."""
    return load_spec().get("components", {}).get("schemas", {})


def schema(name: str) -> Optional[dict[str, Any]]:
    """One named schema (`Card`, `Checklist`, `TrelloList`, …), or `None`
    when the name does not exist in this spec (never a fabricated shape)."""
    return schemas().get(name)


def resolve_ref(ref: str) -> Optional[dict[str, Any]]:
    """`#/components/schemas/Foo` → the `Foo` schema object, or `None`."""
    if not ref.startswith("#/components/schemas/"):
        return None
    return schema(ref.rsplit("/", 1)[-1])


def flatten_properties(schema_obj: dict[str, Any]) -> dict[str, Any]:
    """One level of `describe_model`'s flattening: for every property that
    is itself an object (inline `properties`, or a `$ref` to another
    schema), attach that nested object's own `properties` under a
    `nested_properties` key — so `Card.badges.*` is visible without
    fully recursing the whole schema graph (which would pull in Board →
    Organization → … and never terminate usefully)."""
    props = schema_obj.get("properties", {})
    out: dict[str, Any] = {}
    for name, prop in props.items():
        entry: dict[str, Any] = {
            "type": prop.get("type"),
            "description": prop.get("description"),
        }
        ref = prop.get("$ref")
        nested_source = None
        if ref:
            entry["ref"] = ref.rsplit("/", 1)[-1]
            nested_source = resolve_ref(ref)
        elif prop.get("type") == "array" and isinstance(prop.get("items"), dict):
            items = prop["items"]
            if items.get("$ref"):
                entry["items_ref"] = items["$ref"].rsplit("/", 1)[-1]
                nested_source = resolve_ref(items["$ref"])
            else:
                entry["items_type"] = items.get("type")
        elif prop.get("type") == "object" and prop.get("properties"):
            nested_source = prop
        if nested_source is not None:
            entry["nested_properties"] = sorted(nested_source.get("properties", {}).keys())
        out[name] = entry
    return out


def response_schema_ref(op: dict[str, Any]) -> Optional[str]:
    """The `$ref` schema name of a `2xx` response body, if any."""
    for status, resp in op.get("responses", {}).items():
        if not status.startswith("2"):
            continue
        content = resp.get("content", {}).get("application/json", {})
        ref = content.get("schema", {}).get("$ref")
        if ref:
            return ref.rsplit("/", 1)[-1]
    return None


__all__ = [
    "SPEC_PATH",
    "SpecNotFoundError",
    "find_operation",
    "flatten_properties",
    "load_spec",
    "operations",
    "resolve_ref",
    "resource_of",
    "response_schema_ref",
    "schema",
    "schemas",
]
