"""The bundled Omie API catalog — 134 endpoints · 461 methods · 1757 types.

Omie publishes no OpenAPI/Swagger document. What it *does* publish is an
HTML doc page per endpoint, served from the endpoint's own URL on GET
(`GET https://app.omie.com.br/api/v1/geral/clientes/` → the docs;
POST → the API). `scripts/harvest_catalog.py` parses all 134 of them into
`data/catalog.json.gz`, which this module reads.

Why bundle it rather than fetch live:

* **Discovery must not cost a request.** Omie meters per IP and blocks a
  method for 30 min after repeated failures — an agent browsing the API
  surface should never spend that budget.
* **It works offline and is deterministic**, so a tool result is
  reproducible and the catalog is reviewable in git like any other
  artifact.
* **It carries the live request examples** Omie ships per method (458 of
  461 have one), which is what actually lets an agent construct a valid
  `param` on the first try.

Regenerate with `python mcp/omie/scripts/harvest_catalog.py` (writes
`catalog.json`; re-gzip into `data/`). `harvested_at` records provenance —
a stale catalog is reported honestly by `omie.catalog.status`, never
silently trusted.
"""
from __future__ import annotations

import difflib
import gzip
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Optional

_DATA = Path(__file__).resolve().parent / "data" / "catalog.json.gz"


@lru_cache(maxsize=1)
def load() -> dict:
    """Load + cache the bundled catalog. Missing/corrupt ⇒ raises (never {})."""
    if not _DATA.exists():
        raise FileNotFoundError(
            f"Omie catalog missing at {_DATA}. Regenerate with "
            "`python mcp/omie/scripts/harvest_catalog.py`."
        )
    with gzip.open(_DATA, "rt", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _index() -> dict:
    """Build the lookup indexes once: methods by name, endpoints by path."""
    cat = load()
    by_method: dict[str, list[dict]] = {}
    by_path: dict[str, dict] = {}
    for ep in cat["endpoints"]:
        by_path[ep["path"]] = ep
        for m in ep["methods"]:
            by_method.setdefault(m["name"].lower(), []).append(
                {"endpoint": ep["path"], "family": ep["family"],
                 "resource": ep["resource"], "method": m}
            )
    return {"by_method": by_method, "by_path": by_path, "catalog": cat}


def status() -> dict:
    """Provenance + shape of the bundled catalog."""
    cat = load()
    eps = cat["endpoints"]
    return {
        "harvested_at": cat.get("harvested_at"),
        "source": cat.get("source"),
        "base_url": cat.get("base_url"),
        "endpoints": len(eps),
        "methods": sum(len(e["methods"]) for e in eps),
        "complex_types": sum(len(e["types"]) for e in eps),
        "families": sorted({e["family"] for e in eps}),
        "bundled_file": str(_DATA),
        "note": "Harvested from the official Omie developer portal; "
                "regenerate with scripts/harvest_catalog.py.",
    }


def list_endpoints(family: Optional[str] = None) -> list[dict]:
    """Endpoint inventory, optionally filtered to one family."""
    return [
        {
            "path": e["path"],
            "family": e["family"],
            "resource": e["resource"],
            "method_count": len(e["methods"]),
            "methods": [m["name"] for m in e["methods"]],
        }
        for e in load()["endpoints"]
        if not family or e["family"] == family
    ]


def _score(needle: str, hay: str) -> int:
    if not hay:
        return 0
    h = hay.lower()
    if needle == h:
        return 100
    if h.startswith(needle):
        return 60
    return 30 if needle in h else 0


def search(query: str, *, limit: int = 25, family: Optional[str] = None) -> list[dict]:
    """Keyword search across method names, descriptions, and resources.

    Deliberately a plain ranked substring search: the catalog is small,
    local, and the caller is an LLM that reformulates well. No embedding
    dependency, no network, no cost.
    """
    terms = [t for t in re.split(r"\W+", (query or "").lower()) if t]
    if not terms:
        return []
    hits: list[dict] = []
    for ep in load()["endpoints"]:
        if family and ep["family"] != family:
            continue
        for m in ep["methods"]:
            s = 0
            for t in terms:
                s += (
                    _score(t, m["name"]) * 3
                    + _score(t, m.get("description") or "")
                    + _score(t, ep["resource"]) * 2
                    + _score(t, ep["path"])
                )
            if s:
                hits.append({
                    "score": s,
                    "call": m["name"],
                    "endpoint": ep["path"],
                    "family": ep["family"],
                    "resource": ep["resource"],
                    "description": m.get("description") or "",
                    "mutating": not m["name"].startswith(
                        ("Listar", "Consultar", "Obter", "Pesquisar", "Verificar")
                    ),
                })
    hits.sort(key=lambda h: (-h["score"], h["call"]))
    return hits[:limit]


def _resolve_type(ep: dict, type_name: Optional[str], depth: int, seen: set) -> Any:
    """Expand a complex type into a nested field description.

    `depth` bounds the expansion (Omie types nest deeply — a full expansion
    of e.g. `pedido_venda_produto` is thousands of fields and would blow the
    caller's context). Truncation is always reported, never silent.
    """
    if not type_name:
        return None
    t = ep["types"].get(type_name)
    if t is None:
        return {"type": type_name, "unresolved": True}
    if type_name in seen:
        return {"type": type_name, "recursive_ref": True}
    if depth <= 0:
        return {
            "type": type_name,
            "truncated": True,
            "field_count": len(t.get("fields") or []),
            "hint": "Re-call with a higher `depth` to expand this type.",
        }
    seen = seen | {type_name}
    if t.get("array_of"):
        return {
            "type": type_name,
            "array_of": t["array_of"],
            "description": t.get("description") or "",
            "items": _resolve_type(ep, t["array_of"], depth - 1, seen),
        }
    fields = []
    for f in t.get("fields") or []:
        entry = {k: v for k, v in f.items() if v not in (None, "", False)}
        nested = ep["types"].get(f.get("type") or "")
        if nested is not None:
            entry["schema"] = _resolve_type(ep, f["type"], depth - 1, seen)
        fields.append(entry)
    return {
        "type": type_name,
        "description": t.get("description") or "",
        "fields": fields,
    }


def describe_method(call: str, *, endpoint: Optional[str] = None, depth: int = 2) -> dict:
    """Full schema for one method: params, resolved types, return, example.

    Raises `KeyError` with the near-miss candidates when the method is
    unknown — a wrong `call` should tell the agent what the right one is,
    not fail blankly.
    """
    idx = _index()
    matches = idx["by_method"].get((call or "").lower(), [])
    if endpoint:
        want = endpoint if endpoint.startswith("/") else f"/{endpoint.strip('/')}/"
        matches = [m for m in matches if m["endpoint"] == want] or matches
    if not matches:
        near = suggest(call or "", limit=8)
        raise KeyError(
            f"Unknown Omie method {call!r}."
            + (f" Did you mean: {near}?" if near else "")
        )
    hit = matches[0]
    ep = idx["by_path"][hit["endpoint"]]
    m = hit["method"]
    return {
        "call": m["name"],
        "endpoint": ep["path"],
        "url": f"{load()['base_url']}{ep['path']}",
        "family": ep["family"],
        "resource": ep["resource"],
        "description": m.get("description") or "",
        "mutating": not m["name"].startswith(
            ("Listar", "Consultar", "Obter", "Pesquisar", "Verificar")
        ),
        "example_param": m.get("example"),
        "params": [
            {
                "name": p.get("name"),
                "docs": p.get("docs"),
                "schema": _resolve_type(ep, p.get("type"), depth, set()),
            }
            for p in m.get("params") or []
        ],
        "returns": {
            "type": m.get("returns"),
            "docs": m.get("returns_doc") or "",
            "schema": _resolve_type(ep, m.get("returns"), depth, set()),
        },
        "also_available_on": [x["endpoint"] for x in matches[1:]],
        "docs_url": ep["url"],
    }


def find_method(call: str) -> Optional[dict]:
    """Locate a method without expanding schemas — used to validate `omie.call`."""
    hits = _index()["by_method"].get((call or "").lower(), [])
    return hits[0] if hits else None


@lru_cache(maxsize=1)
def all_method_names() -> tuple[str, ...]:
    """Every distinct method name in the catalog (for typo suggestions)."""
    return tuple(sorted({
        m["name"] for ep in load()["endpoints"] for m in ep["methods"]
    }))


def suggest(call: str, limit: int = 6) -> list[str]:
    """Near-miss method names for a wrong `call`.

    Keyword search alone misses the common case — a singular/plural or
    one-character typo (`ListarClienteZ`) shares no whole token with the
    real name — so close-match ranking runs first, with the keyword hits
    appended for genuinely different wording.
    """
    q = (call or "").strip()
    if not q:
        return []
    names = all_method_names()
    lower = {n.lower(): n for n in names}
    out = [lower[m] for m in difflib.get_close_matches(
        q.lower(), list(lower), n=limit, cutoff=0.6)]
    for h in search(q, limit=limit):
        if h["call"] not in out:
            out.append(h["call"])
    return out[:limit]


def endpoint_methods(path: str) -> list[dict]:
    """All methods on one endpoint, with their examples."""
    want = path if path.startswith("/") else f"/{path.strip('/')}/"
    ep = _index()["by_path"].get(want)
    if ep is None:
        raise KeyError(
            f"Unknown Omie endpoint {path!r}. "
            f"Use omie.catalog.list_endpoints to see the {len(load()['endpoints'])} available."
        )
    return [
        {
            "call": m["name"],
            "description": m.get("description") or "",
            "example_param": m.get("example"),
            "returns": m.get("returns"),
            "mutating": not m["name"].startswith(
                ("Listar", "Consultar", "Obter", "Pesquisar", "Verificar")
            ),
        }
        for m in ep["methods"]
    ]


__all__ = [
    "load", "status", "search", "describe_method", "list_endpoints",
    "endpoint_methods", "find_method", "suggest",
]
