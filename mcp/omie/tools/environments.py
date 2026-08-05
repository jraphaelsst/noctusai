"""`omie.environments.*` — inspect and verify the configured companies.

An Omie "environment" is a company with its own `app_key`/`app_secret`.
Before an agent writes anything it should be able to answer "which
companies can I reach, which one am I about to hit, and is it the live
one?" — that is what these three tools are for.

`check` is the only one that spends a request, and it deliberately uses
`ListarEmpresas` (a cheap read) so verifying a credential can never
mutate anything.
"""
from __future__ import annotations

import asyncio

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from ..api import OmieClient
from ..errors import OmieApiError
from ..settings import get_settings
from ._common import guarded, schema


async def list_environments(args: dict) -> dict:
    """Every configured environment, redacted. Never returns a secret."""
    s = get_settings()
    try:
        default = s.get(None).name
    except OmieApiError:
        default = None  # unresolvable default is reported, not raised
    return {
        "ok": True,
        "environments": [e.redacted() for e in s.environments],
        "count": len(s.environments),
        "default_environment": default,
        "default_environment_setting": s.default_environment,
        "base_url": s.base_url,
        "configured": s.configured,
        "hint": (
            "Configure with OMIE_ENVIRONMENTS (JSON), OMIE_ENV__<NAME>__APP_KEY/"
            "__APP_SECRET, or OMIE_APP_KEY + OMIE_APP_SECRET."
            if not s.environments else
            "Pass `environment` on any tool to target a specific company."
        ),
    }


async def describe_environment(args: dict) -> dict:
    """Resolve one environment (or the default) without calling Omie."""
    async def run():
        env = get_settings().get(args.get("environment"))
        return {"environment": env.redacted(),
                "resolved_from": args.get("environment") or "default"}
    return await guarded(run)


async def check_environment(args: dict) -> dict:
    """Live credential check via `ListarEmpresas` — a read, never a write.

    With `all=true`, checks every configured environment concurrently and
    reports each verdict independently: one bad credential must not hide
    the health of the others.
    """
    s = get_settings()
    names = (
        s.names() if args.get("all")
        else [args.get("environment") or (s.get(None).name if s.environments else "")]
    )
    if not s.environments:
        return {"ok": False, "error": {
            "error_class": "OmieConfigError", "status": 424,
            "message": "No Omie environment is configured."}}

    async def probe(name: str) -> dict:
        try:
            env = s.get(name)
        except OmieApiError as e:
            return {"environment": name, "ok": False, "error": typed_error(e)}
        client = OmieClient(env)
        try:
            data = await client.call(
                "/geral/empresas/", "ListarEmpresas",
                {"pagina": 1, "registros_por_pagina": 5},
            )
        except OmieApiError as e:
            return {"environment": name, "ok": False,
                    "readonly": env.readonly, "error": typed_error(e)}
        companies = data.get("empresas_cadastro") if isinstance(data, dict) else None
        return {
            "environment": name,
            "ok": True,
            "readonly": env.readonly,
            "reachable": True,
            "companies_visible": data.get("total_de_registros") if isinstance(data, dict) else None,
            "sample": [
                {k: c.get(k) for k in ("codigo_empresa", "razao_social", "cnpj")
                 if k in c}
                for c in (companies or [])[:5]
            ],
        }

    results = await asyncio.gather(*(probe(n) for n in names))
    return {
        "ok": all(r.get("ok") for r in results),
        "checked": len(results),
        "results": list(results),
    }


HANDLERS = {
    "omie.environments.list": list_environments,
    "omie.environments.describe": describe_environment,
    "omie.environments.check": check_environment,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="omie.environments.list",
            description=(
                "List every configured Omie environment (company). An Omie "
                "'environment' is a company with its own app_key/app_secret — "
                "there is no shared sandbox. Credentials are redacted: only an "
                "app_key suffix is returned, never a secret. Start here to see "
                "what you can reach and which environment is the default."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="omie.environments.describe",
            description=(
                "Resolve one environment (or the configured default) and return "
                "its redacted profile, including whether it is pinned readonly. "
                "Makes no API call — use this to confirm which company a "
                "subsequent write would land on."
            ),
            inputSchema=schema({}),
        ),
        Tool(
            name="omie.environments.check",
            description=(
                "Verify credentials live by calling ListarEmpresas (a read — "
                "never mutates). Returns reachability plus the visible companies. "
                "Pass all=true to check every configured environment concurrently; "
                "each verdict is reported independently."
            ),
            inputSchema=schema({
                "all": {"type": "boolean", "default": False,
                        "description": "Check every configured environment."},
            }),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
