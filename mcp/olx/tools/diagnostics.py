"""`olx.diagnostics.*` — is this connector set up, and does the vendor
behave the way we wrote down?

`connection_status` makes zero API calls (an agent asking "am I set up?"
should not spend a request, and an unconfigured connector must not
produce an upstream error that reads like an outage).

`probe` is the one to read carefully. Every baseline row currently has
NO recorded expectation, so every result lands in `unverified` rather
than `unexpected`. That is deliberate: the alternative is to guess an
expected status, print `as_expected: true` for a number we invented, and
teach the operator that the report lies.
"""
from __future__ import annotations

import logging
import time
import urllib.error
import urllib.request
from typing import Any, Optional

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error
from noctusai_lib.integrations.olx import (
    OLX_ENDPOINT_BASELINE,
    OLX_REFERENCE_URLS,
    OLX_SUPPORT_CONTACTS,
    contract_summary,
)
from noctusai_lib.integrations.olx.endpoints import ENDPOINT_INBOUND

from .. import api
from ..settings import get_settings
from ..types import (
    ConnectionStatusInput,
    ConnectionStatusOutput,
    ListKnownEndpointsInput,
    ListKnownEndpointsOutput,
    ProbeInput,
    ProbeOutput,
)

logger = logging.getLogger(__name__)

_TOOL_BY_PATH = {
    "/v1/addLeads": "olx.leads.push",
    "<inbound>/webhooks/lead": "olx.webhook.simulate",
}


def _next_step(settings) -> Optional[str]:
    missing = []
    if not settings.lead_manager_configured:
        missing.append(
            "outbound: set OLX_API_KEY + OLX_AGENT_NAME (Gestor de Leads setup, "
            "integracaoleads@grupozap.com)"
        )
    if not settings.receiver_configured:
        missing.append(
            "inbound: set OLX_RECEIVER_URL + OLX_WEBHOOK_SECRET (the per-CRM key "
            "issued at homologation)"
        )
    return "; ".join(missing) if missing else None


async def connection_status(args: dict) -> dict:
    ConnectionStatusInput(**args)
    settings = get_settings()
    return ConnectionStatusOutput(
        ok=settings.configured,
        lead_manager_configured=settings.lead_manager_configured,
        receiver_configured=settings.receiver_configured,
        base_url=settings.base_url,
        receiver_url=settings.receiver_url,
        has_api_key=bool(settings.api_key),
        has_agent_name=bool(settings.agent_name),
        has_webhook_secret=bool(settings.webhook_secret),
        contract_verified=contract_summary()["verified_against_live_traffic"],
        next_step=_next_step(settings),
    ).model_dump()


def _probe_one(url: str, timeout: float) -> tuple[Optional[int], float, Optional[str]]:
    started = time.monotonic()
    try:
        request = urllib.request.Request(url, method="GET")  # noqa: S310 — fixed baseline
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return int(response.status), round((time.monotonic() - started) * 1000, 1), None
    except urllib.error.HTTPError as exc:
        # A non-2xx is a MEASUREMENT, not a failure — several endpoints
        # answer a bare GET with 401/405 by design.
        return int(exc.code), round((time.monotonic() - started) * 1000, 1), None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return None, round((time.monotonic() - started) * 1000, 1), str(exc)


async def probe(args: dict) -> dict:
    ProbeInput(**args)
    settings = get_settings()
    results: list[dict[str, Any]] = []
    unexpected: list[dict[str, Any]] = []
    unverified: list[dict[str, Any]] = []

    for path, expected, probe_status, note in OLX_ENDPOINT_BASELINE:
        row: dict[str, Any] = {
            "endpoint": path,
            "probe_status": probe_status,
            "expected_http_status": expected,
            "note": note,
            "tool": _TOOL_BY_PATH.get(path),
        }
        if probe_status == ENDPOINT_INBOUND:
            row.update({
                "observed_http_status": None,
                "as_expected": None,
                "skipped": "inbound — THEY call US; use olx.webhook.simulate",
            })
            results.append(row)
            continue

        url = f"{settings.base_url.rstrip('/')}{path}"
        status, latency_ms, error = _probe_one(url, settings.timeout_seconds)
        row.update({
            "url": url,
            "observed_http_status": status,
            "latency_ms": latency_ms,
            "transport_error": error,
        })
        if expected is None:
            row["as_expected"] = None
            row["action"] = (
                "No expectation recorded yet. If this status is stable, write it "
                "into OLX_ENDPOINT_BASELINE and stamp the date in the KB change log."
            )
            unverified.append(row)
        else:
            row["as_expected"] = status == expected
            if not row["as_expected"]:
                unexpected.append(row)
        results.append(row)

    return ProbeOutput(
        results=results, unexpected=unexpected, unverified=unverified, probed=True
    ).model_dump()


async def list_known_endpoints(args: dict) -> dict:
    ListKnownEndpointsInput(**args)
    return ListKnownEndpointsOutput(
        endpoints=[
            {
                "path": path,
                "expected_http_status": expected,
                "probe_status": probe_status,
                "note": note,
                "tool": _TOOL_BY_PATH.get(path),
            }
            for path, expected, probe_status, note in OLX_ENDPOINT_BASELINE
        ],
        reference_urls=dict(OLX_REFERENCE_URLS),
        support_contacts=dict(OLX_SUPPORT_CONTACTS),
    ).model_dump()


HANDLERS = {
    "olx.diagnostics.connection_status": connection_status,
    "olx.diagnostics.probe": probe,
    "olx.diagnostics.list_known_endpoints": list_known_endpoints,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="olx.diagnostics.connection_status",
            description=(
                "Is the OLX connector configured — outbound credentials, "
                "inbound receiver + secret, and whether the payload contract "
                "has been verified against live traffic yet. Makes ZERO API "
                "calls. READ-ONLY, never faked."
            ),
            inputSchema=ConnectionStatusInput.model_json_schema(),
        ),
        Tool(
            name="olx.diagnostics.probe",
            description=(
                "Probe each known OLX endpoint and report what it actually "
                "answers. Read `unexpected` (contradicts a recorded "
                "expectation) and `unverified` (no expectation recorded yet — "
                "every row until Gate 1). A row's observed status is what fills "
                "the baseline in. READ-ONLY."
            ),
            inputSchema=ProbeInput.model_json_schema(),
        ),
        Tool(
            name="olx.diagnostics.list_known_endpoints",
            description=(
                "Static catalog of every known OLX endpoint, the tool that "
                "wraps it, plus the vendor documentation URLs and the support "
                "addresses to email for a key or an ImovelWeb activation code. "
                "Derived from the same baseline `probe` measures, so the two "
                "cannot disagree. READ-ONLY, no API calls."
            ),
            inputSchema=ListKnownEndpointsInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
