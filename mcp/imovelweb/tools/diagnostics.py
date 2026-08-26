"""`imovelweb.diagnostics.*` — is this connector set up, and does the vendor
behave the way we wrote down?

`connection_status` makes **zero API calls**. An agent asking "am I set
up?" must not spend a request, and an unconfigured connector must not
produce an upstream error that reads like an outage.

`probe` is the one to read carefully, and its caveat is not boilerplate.
Gate 0 established that `/v1/**` answers **401 before routing** — Spring
Security's filter chain runs ahead of the dispatcher — so an unauthenticated
probe cannot tell a real path from a typo. Every `/v1/` row is therefore
marked non-discriminating, and `fetch_swagger` is the tool that actually
answers path existence.

`fetch_swagger` has no counterpart in the OLX connector, because this
vendor publishes a machine-readable spec on both hosts with **no auth**.
That closes the doc-vs-reality loop for the API surface without waiting
for credentials — which is exactly why Gate 0 was cheap here.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any, Optional

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error
from noctusai_lib.integrations.imovelweb import (
    IMOVELWEB_ENDPOINT_BASELINE,
    IMOVELWEB_LOGIN_BUTTON_URLS,
    IMOVELWEB_PATH_VARIANTS,
    IMOVELWEB_PROD_BR,
    IMOVELWEB_REFERENCE_URLS,
    IMOVELWEB_SANDBOX_BR,
    IMOVELWEB_SANDBOX_WINDOW,
    IMOVELWEB_SUPPORT_CONTACTS,
    IMOVELWEB_SWAGGER_PATH,
    contract_summary,
    receiver_url_problems,
)
from noctusai_lib.integrations.imovelweb.endpoints import ENDPOINT_INBOUND

from .. import api
from ..settings import get_settings
from ..types import (
    DiagnosticsConnectionStatusInput,
    DiagnosticsConnectionStatusOutput,
    DiagnosticsFetchSwaggerInput,
    DiagnosticsFetchSwaggerOutput,
    DiagnosticsListKnownEndpointsInput,
    DiagnosticsListKnownEndpointsOutput,
    DiagnosticsProbeInput,
    DiagnosticsProbeOutput,
)

logger = logging.getLogger(__name__)

_TOOL_BY_PATH = {
    "/v1/configuracao/callbacks": "imovelweb.callbacks.get_config / .put_config",
    "/v1/configuracao/callbacks/{evento}": "imovelweb.callbacks.subscribe / .unsubscribe",
    "/v1/callbacks/geracao/eventos": "imovelweb.sandbox.emit_event",
    "/v2/imobiliarias/{codigoImobiliaria}/mensagens": "imovelweb.leads.list_messages",
    "/v1/mensagens/{idMensaje}": "imovelweb.leads.get_message",
    "/v1/mensagen/{idMensagen}/smartLead": "imovelweb.leads.get_smartlead",
    "/v1/contatos/acoes": "imovelweb.leads.list_contact_actions",
    "/v1/imobiliarias": "imovelweb.agencies.list",
    IMOVELWEB_SWAGGER_PATH: "imovelweb.diagnostics.fetch_swagger",
    "<our receiver>": "imovelweb.webhook.simulate",
}

#: Sent on every outbound request this module makes.
#:
#: Not cosmetic. The vendor's edge 403s `Python-urllib/*` outright — the
#: default urllib header — while accepting curl, a browser, and this string.
#: Observed 2026-08-18: the public spec answered 200 to curl and 403 to
#: urllib from the same machine, seconds apart. Without this the connector
#: reports "network or DNS on our side" for a request the vendor's WAF is
#: rejecting by name, which sends an operator debugging the wrong layer.
#: Identifying ourselves honestly is also the right thing to send; there is
#: no need to impersonate a browser.
USER_AGENT = "noctusai-imovelweb-connector/1.0 (+https://noctusai.com.br)"

_PROBE_CAVEAT = (
    "Gate 0 proved that /v1/** answers 401 BEFORE routing — a bogus path "
    "returns the same 401 as a real one — so a 401 here confirms only that "
    "the filter chain is up, never that an endpoint exists. Use "
    "imovelweb.diagnostics.fetch_swagger for path existence; it reads the "
    "vendor's own generated spec, which needs no credentials."
)


def _next_step(settings) -> Optional[str]:
    missing = []
    if not settings.api_configured:
        missing.append(
            "vendor API: set IMOVELWEB_CLIENT_ID + IMOVELWEB_CLIENT_SECRET "
            "(request them at integracao@imovelweb.com.br — one email for "
            "sandbox, a second for production)"
        )
    if not settings.receiver_configured:
        missing.append(
            "inbound: set IMOVELWEB_RECEIVER_URL + IMOVELWEB_WEBHOOK_SECRET "
            "(we choose this secret; it must match what the product receiver "
            "validates, or a simulation proves nothing)"
        )
    return "; ".join(missing) if missing else None


async def connection_status(args: dict) -> dict:
    DiagnosticsConnectionStatusInput(**args)
    settings = get_settings()
    return DiagnosticsConnectionStatusOutput(
        ok=settings.configured,
        api_configured=settings.api_configured,
        receiver_configured=settings.receiver_configured,
        base_url=settings.base_url,
        region=settings.region,
        sandbox=settings.sandbox,
        sandbox_window=settings.sandbox_window,
        receiver_url=settings.receiver_url,
        receiver_url_problems=(
            list(receiver_url_problems(settings.receiver_url))
            if settings.receiver_url
            else []
        ),
        has_client_id=bool(settings.client_id),
        has_client_secret=bool(settings.client_secret),
        has_webhook_secret=bool(settings.webhook_secret),
        contract_verified=contract_summary()["verified_against_live_traffic"],
        next_step=_next_step(settings),
    ).model_dump()


def _probe_one(url: str, timeout: float) -> tuple[Optional[int], float, Optional[str]]:
    started = time.monotonic()
    try:
        request = urllib.request.Request(  # noqa: S310 — fixed baseline
            url, method="GET", headers={"User-Agent": USER_AGENT}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return int(response.status), round((time.monotonic() - started) * 1000, 1), None
    except urllib.error.HTTPError as exc:
        # A non-2xx is a MEASUREMENT, not a failure — most of these
        # endpoints answer a bare unauthenticated GET with 401 by design.
        return int(exc.code), round((time.monotonic() - started) * 1000, 1), None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return None, round((time.monotonic() - started) * 1000, 1), str(exc)


async def probe(args: dict) -> dict:
    DiagnosticsProbeInput(**args)
    settings = get_settings()
    base = settings.base_url
    if not base:
        return DiagnosticsProbeOutput(
            results=[],
            caveat=_PROBE_CAVEAT,
            probed=False,
        ).model_dump()

    results: list[dict[str, Any]] = []
    unexpected: list[dict[str, Any]] = []
    unverified: list[dict[str, Any]] = []

    for row in IMOVELWEB_ENDPOINT_BASELINE:
        path = row["path"]
        expected = row["expected_status"]
        out: dict[str, Any] = {
            "method": row["method"],
            "endpoint": path,
            "probe_status": row["status"],
            "expected_http_status": expected,
            "note": row["notes"],
            "tool": _TOOL_BY_PATH.get(path),
        }
        if row["status"] == ENDPOINT_INBOUND:
            out.update({
                "observed_http_status": None,
                "as_expected": None,
                "skipped": "inbound — THEY call US; use imovelweb.webhook.simulate",
            })
            results.append(out)
            continue

        url = f"{base.rstrip('/')}{path}"
        status, latency_ms, error = _probe_one(url, settings.timeout_seconds)
        # The swagger endpoint is public, so its result actually means
        # something. Everything under /v1/ 401s before routing.
        discriminating = path == IMOVELWEB_SWAGGER_PATH
        out.update({
            "url": url,
            "observed_http_status": status,
            "latency_ms": latency_ms,
            "transport_error": error,
            "discriminating": discriminating,
        })
        if not discriminating:
            out["interpretation"] = (
                "401 here is expected and proves nothing about this path — "
                "the security filter runs before routing."
            )
        if expected is None:
            out["as_expected"] = None
            out["action"] = (
                "No expectation recorded yet. If this status is stable AND the "
                "row is discriminating, write it into "
                "IMOVELWEB_ENDPOINT_BASELINE and date it in the KB change log."
            )
            unverified.append(out)
        else:
            out["as_expected"] = status == expected
            if not out["as_expected"]:
                unexpected.append(out)
        results.append(out)

    return DiagnosticsProbeOutput(
        results=results,
        unexpected=unexpected,
        unverified=unverified,
        caveat=_PROBE_CAVEAT,
        probed=True,
    ).model_dump()


async def list_known_endpoints(args: dict) -> dict:
    DiagnosticsListKnownEndpointsInput(**args)
    return DiagnosticsListKnownEndpointsOutput(
        endpoints=[
            {
                "method": row["method"],
                "path": row["path"],
                "expected_http_status": row["expected_status"],
                "probe_status": row["status"],
                "note": row["notes"],
                "tool": _TOOL_BY_PATH.get(row["path"]),
            }
            for row in IMOVELWEB_ENDPOINT_BASELINE
        ],
        path_variants={k: list(v) for k, v in IMOVELWEB_PATH_VARIANTS.items()},
        login_button_urls=dict(IMOVELWEB_LOGIN_BUTTON_URLS),
        reference_urls=dict(IMOVELWEB_REFERENCE_URLS),
        support_contacts=dict(IMOVELWEB_SUPPORT_CONTACTS),
        sandbox_window=IMOVELWEB_SANDBOX_WINDOW,
    ).model_dump()


def _normalize_path(path: str) -> str:
    """Compare paths without their parameter NAMES.

    The vendor spells the same parameter three ways across its own surfaces
    (`{codigoImobiliaria}`, `{codigoInmobiliaria}`, `{cod}`), and a diff
    that treated those as different endpoints would report drift on every
    single row and be ignored within a day.
    """
    base = path.split("?", 1)[0].rstrip("/")
    out: list[str] = []
    depth = 0
    for char in base:
        if char == "{":
            depth += 1
            if depth == 1:
                out.append("{}")
        elif char == "}":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(char)
    return "".join(out)


def _fetch_spec(url: str, timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    try:
        request = urllib.request.Request(  # noqa: S310 — fixed host
            url, method="GET", headers={"User-Agent": USER_AGENT}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read().decode("utf-8", errors="replace")
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        code = int(exc.code)
        if code in (401, 403):
            # This endpoint is public, so a 401/403 is the vendor's EDGE
            # refusing our client, not an authorization problem we can fix
            # with credentials. Saying "not served" would send an operator
            # hunting for a key that was never required.
            reason = (
                f"the vendor's edge refused this client ({code}) — the spec "
                "itself is public and needs no credentials, so this is a "
                "User-Agent / WAF rejection, not an authorization failure"
            )
        else:
            reason = "spec not served"
        return {"url": url, "http_status": code, "error": reason}
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"url": url, "http_status": None, "error": str(exc)}

    latency_ms = round((time.monotonic() - started) * 1000, 1)
    try:
        spec = json.loads(body)
    except ValueError as exc:
        # A 200 that is not JSON is worth reporting loudly: it usually
        # means a captive portal or a proxy answered instead of the vendor.
        return {
            "url": url,
            "http_status": status,
            "latency_ms": latency_ms,
            "error": f"body was not JSON: {exc}",
        }

    paths = sorted((spec.get("paths") or {}).keys())
    return {
        "url": url,
        "http_status": status,
        "latency_ms": latency_ms,
        "spec_version": (spec.get("info") or {}).get("version"),
        "title": (spec.get("info") or {}).get("title"),
        "path_count": len(paths),
        "paths": paths,
    }


async def fetch_swagger(args: dict) -> dict:
    parsed_args = DiagnosticsFetchSwaggerInput(**args)
    timeout = get_settings().timeout_seconds

    hosts = {
        "prod_br": _fetch_spec(f"{IMOVELWEB_PROD_BR}{IMOVELWEB_SWAGGER_PATH}", timeout),
        "sandbox_br": _fetch_spec(f"{IMOVELWEB_SANDBOX_BR}{IMOVELWEB_SWAGGER_PATH}", timeout),
    }

    spec_paths: dict[str, list[str]] = {
        name: data.get("paths", []) for name, data in hosts.items()
    }
    prod = {_normalize_path(p) for p in spec_paths.get("prod_br", [])}
    sandbox = {_normalize_path(p) for p in spec_paths.get("sandbox_br", [])}
    served = prod | sandbox

    # Rows that are not vendor REST endpoints cannot be in a spec.
    baseline = {
        _normalize_path(row["path"])
        for row in IMOVELWEB_ENDPOINT_BASELINE
        if row["status"] != ENDPOINT_INBOUND and not row["path"].startswith("/v2/api-docs")
    }

    reachable = any(data.get("path_count") for data in hosts.values())
    if not reachable:
        refused = [
            name for name, data in hosts.items()
            if data.get("http_status") in (401, 403)
        ]
        if refused:
            next_step = (
                f"The vendor's edge refused us on {', '.join(refused)}. The spec "
                "is public, so this is a client-level rejection — check the "
                "User-Agent this connector sends before assuming credentials or "
                "network are the problem."
            )
        else:
            next_step = (
                "Neither host served a spec. This endpoint is PUBLIC and needs "
                "no credentials, so a failure here is network or DNS on our "
                "side, not an authorization problem."
            )
    elif not (served - baseline) and not (baseline - served):
        next_step = (
            "The spec and IMOVELWEB_ENDPOINT_BASELINE agree. Record the spec "
            "versions and the date in KB § INTEGRATIONS/imovelweb.md § 8."
        )
    else:
        next_step = (
            "Reconcile endpoints.py with the spec, then date the observation in "
            "the KB change log. `in_baseline_not_in_spec` is usually a spelling "
            "the prose and the generated spec disagree on — see "
            "IMOVELWEB_PATH_VARIANTS — not a missing endpoint."
        )

    return DiagnosticsFetchSwaggerOutput(
        hosts={
            name: {k: v for k, v in data.items() if k != "paths"}
            for name, data in hosts.items()
        },
        in_spec_not_in_baseline=sorted(served - baseline),
        in_baseline_not_in_spec=sorted(baseline - served),
        confirmed=sorted(served & baseline),
        sandbox_only=sorted(sandbox - prod),
        prod_only=sorted(prod - sandbox),
        paths=spec_paths if parsed_args.include_paths else None,
        next_step=next_step,
    ).model_dump()


HANDLERS = {
    "imovelweb.diagnostics.connection_status": connection_status,
    "imovelweb.diagnostics.probe": probe,
    "imovelweb.diagnostics.list_known_endpoints": list_known_endpoints,
    "imovelweb.diagnostics.fetch_swagger": fetch_swagger,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="imovelweb.diagnostics.connection_status",
            description=(
                "Is the ImovelWeb connector configured — vendor credentials, "
                "inbound receiver + secret, resolved host, sandbox flag and "
                "window, whether the receiver URL is safe to register, and "
                "whether the payload contract has been verified against live "
                "traffic yet. Makes ZERO API calls. READ-ONLY, never faked."
            ),
            inputSchema=DiagnosticsConnectionStatusInput.model_json_schema(),
        ),
        Tool(
            name="imovelweb.diagnostics.probe",
            description=(
                "Probe each known endpoint and report what it actually "
                "answers. IMPORTANT: /v1/** returns 401 BEFORE routing, so "
                "those rows are marked non-discriminating — a 401 proves the "
                "filter chain is up, not that the path exists. For path "
                "existence use imovelweb.diagnostics.fetch_swagger. READ-ONLY."
            ),
            inputSchema=DiagnosticsProbeInput.model_json_schema(),
        ),
        Tool(
            name="imovelweb.diagnostics.list_known_endpoints",
            description=(
                "Static catalog of every known endpoint, the tool that wraps "
                "it, the unresolved path spellings (the generated spec and the "
                "hand-written docs disagree), the agency login-button URLs, the "
                "vendor documentation links and the support addresses to email "
                "for credentials. Derived from the same baseline `probe` "
                "measures, so the two cannot disagree. READ-ONLY, no API calls."
            ),
            inputSchema=DiagnosticsListKnownEndpointsInput.model_json_schema(),
        ),
        Tool(
            name="imovelweb.diagnostics.fetch_swagger",
            description=(
                "Download the vendor's generated OpenAPI spec from BOTH the "
                "production and sandbox hosts and diff it against our endpoint "
                "baseline. The spec is PUBLIC — no credentials — which is what "
                "lets the doc-vs-reality loop close before Gate 1. Reports "
                "endpoints we are missing, endpoints we believe in that the "
                "spec does not list, and which paths exist only on sandbox "
                "(the event simulator is one). READ-ONLY."
            ),
            inputSchema=DiagnosticsFetchSwaggerInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
