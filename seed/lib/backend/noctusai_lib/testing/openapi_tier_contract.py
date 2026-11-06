"""Schema-driven access-tier contract: "documented => protected" (owner, 2026-11-05).

`/docs` and `/openapi.json` stay PUBLIC in prod, so the schema must (1) leak nothing and (2) describe only routes whose declared
tier is ENFORCED. Three helpers every product's CI calls against its own app (backstop; the construction leg is `make_router`):

* :func:`schema_leaks` / :func:`assert_schema_clean` -- no secrets, internal hostnames, prompt/skill text or stack traces in
  descriptions, examples, defaults or error responses; no Platform-IP route in the public schema.
* :func:`assert_tier_contract` -- for every operation whose tier is not public / signed: an unauthenticated call is strictly
  ``== 401``; a wrong-tier call (a platform route with an org user) is strictly ``== 403``.

Stdlib-only (the tier map comes from `noctus.dev.access_tier_catalog`; the client is a Starlette/FastAPI TestClient).
KB § PATTERNS/security/access-tiers.md.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

_HTTP = ("get", "post", "put", "patch", "delete")
_PATTERNS: dict[str, re.Pattern[str]] = {
    "secret": re.compile(r"sk-[A-Za-z0-9_-]{16,}|eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}\.|AKIA[0-9A-Z]{12,}|"
                         r"(?i:(?:api[_-]?key|secret|password|passwd|token)\s*[:=]\s*[\"']?[A-Za-z0-9/+_-]{16,})"),
    "internal-host": re.compile(r"(?i)\b(?:localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|[\w-]+\.internal|[\w-]+\.local|"
                                r"[a-z0-9]{20}\.supabase\.co|host\.docker\.internal)\b"),
    "prompt-or-skill-text": re.compile(r"(?i)system prompt|<skill|você é |you are (?:julia|an? (?:ai )?assistant)|canary|compiled[_ ]prompt"),
    "stack-trace": re.compile(r"Traceback \(most recent call last\)|File \"/|\bat [\w.$]+\(.*\.(?:py|js|ts):\d+"),
}
_LONG_DESCRIPTION = 800


def _strings(node: Any, path: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, Mapping):
        for k, v in node.items():
            yield from _strings(v, f"{path}/{k}")
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            yield from _strings(v, f"{path}[{i}]")


def schema_leaks(schema: Mapping[str, Any], platform_paths: Iterable[tuple[str, str]] = ()) -> list[str]:
    """Findings for one OpenAPI schema. ``platform_paths`` = (METHOD, path) pairs whose tier is ``platform``: they must NOT be present."""
    out: list[str] = []
    for where, text in _strings(schema):
        for kind, pat in _PATTERNS.items():
            m = pat.search(text)
            if m:
                out.append(f"{kind} at {where}: ...{text[max(0, m.start() - 10):m.end() + 10][:80]!r}")
        if where.endswith(("/description", "/example", "/default")) and len(text) > _LONG_DESCRIPTION:
            out.append(f"over-long text ({len(text)} chars) at {where}: prompt/skill content does not belong in a public schema")
    paths = schema.get("paths", {})
    for method, path in platform_paths:
        if method.lower() in (paths.get(path) or {}):
            out.append(f"platform-tier route {method.upper()} {path} is in the PUBLIC schema (router must set include_in_schema=False)")
    return out


def assert_schema_clean(app: Any, platform_paths: Iterable[tuple[str, str]] = ()) -> None:
    leaks = schema_leaks(app.openapi(), platform_paths)
    assert not leaks, "OpenAPI schema leaks:\n  " + "\n  ".join(leaks)


def assert_tier_contract(client: Any, tiers: Mapping[tuple[str, str], str], *, org_headers: Mapping[str, str] | None = None,
                         skip: Iterable[tuple[str, str]] = ()) -> list[str]:
    """For every documented operation not public/service-signed: unauthenticated == 401; platform routes with an org user == 403.
    ``tiers`` = {(METHOD, path): tier}. Path params are filled with a dummy; a 404/422 is NOT accepted as protection (auth must fire
    first). Returns the failures (empty = proven); call ``assert not failures``."""
    skipped = {(m.upper(), p) for m, p in skip}
    schema_paths = client.app.openapi().get("paths", {})
    fails: list[str] = []
    for path, ops in schema_paths.items():
        for method in _HTTP:
            if method not in ops or (method.upper(), path) in skipped:
                continue
            tier = tiers.get((method.upper(), path))
            if tier is None:
                fails.append(f"{method.upper()} {path}: documented but has NO declared tier (default deny)")
                continue
            if tier in ("public", "service"):
                continue
            url = re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-000000000000", path)
            r = client.request(method.upper(), url)
            if r.status_code != 401:
                fails.append(f"{method.upper()} {path} (tier {tier}): unauthenticated call returned {r.status_code}, expected strictly 401")
            if tier == "platform" and org_headers:
                r = client.request(method.upper(), url, headers=dict(org_headers))
                if r.status_code != 403:
                    fails.append(f"{method.upper()} {path} (tier platform): org-user call returned {r.status_code}, expected strictly 403")
    return fails
