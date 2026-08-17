"""`olx.webhook.*` — the map of the INBOUND lead contract, and the loop
that corrects it against reality.

Four tools, one job between them: make the contract in
`noctusai_lib.integrations.olx.contract` something an agent can read,
test against, exercise, and — crucially — *correct*.

`describe_contract` and `validate_payload` are zero-IO and need no
credentials at all, so they work the moment the connector is installed.
`simulate` and `record_delivery` are writes and carry the confirm gate.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import time
import urllib.error
import urllib.request
from typing import Any, Optional

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error
from noctusai_lib.integrations.olx import (
    OLX_SAMPLE_LEAD,
    contract_summary,
    diff_observed,
    has_blocking_violation,
    missing_client_listing_id,
    parse_olx_lead_webhook,
    validate_olx_lead_payload,
)
from noctusai_lib.integrations.olx.types import OLX_LEAD_ORIGIN_MCMV
from noctusai_lib.security import GRUPO_OLX_BASIC_USERNAME

from .. import api
from ..client import corpus_dir
from ..settings import get_settings
from ..types import (
    DescribeContractInput,
    DescribeContractOutput,
    DiffObservedInput,
    DiffObservedOutput,
    RecordDeliveryInput,
    RecordDeliveryOutput,
    SimulateInput,
    SimulateOutput,
    ValidatePayloadInput,
    ValidatePayloadOutput,
)

logger = logging.getLogger(__name__)

_SAFE_ID = re.compile(r"[^A-Za-z0-9_.-]")


def _violation_dicts(violations) -> list[dict[str, Any]]:
    return [
        {"field": v.field, "severity": v.severity, "message": v.message}
        for v in violations
    ]


async def describe_contract(args: dict) -> dict:
    DescribeContractInput(**args)
    summary = contract_summary()
    return DescribeContractOutput(
        contract=summary,
        verified_against_live_traffic=summary["verified_against_live_traffic"],
    ).model_dump()


async def validate_payload(args: dict) -> dict:
    parsed_args = ValidatePayloadInput(**args)
    violations = validate_olx_lead_payload(parsed_args.payload)
    lead = parse_olx_lead_webhook(parsed_args.payload)
    return ValidatePayloadOutput(
        valid=not has_blocking_violation(violations),
        would_return_4xx=missing_client_listing_id(violations),
        violations=_violation_dicts(violations),
        parsed=(
            {
                "origin_lead_id": lead.origin_lead_id,
                "client_listing_id": lead.client_listing_id,
                "name": lead.name,
                "full_phone": lead.full_phone,
                "lead_type": lead.lead_type,
                "is_mcmv": lead.is_mcmv,
            }
            if lead is not None
            else None
        ),
    ).model_dump()


async def record_delivery(args: dict) -> dict:
    parsed_args = RecordDeliveryInput(**args)
    try:
        if not parsed_args.confirm:
            raise api.ConfirmationRequiredError(
                "olx.webhook.record_delivery",
                "writes a delivery body into the observed corpus",
            )
        payload = parsed_args.payload
        lead = parse_olx_lead_webhook(payload)
        # An unparseable body is still evidence — arguably the MOST
        # valuable kind, since it is the shape our receiver would drop.
        # Key it by hash so it is recorded rather than refused.
        origin_lead_id = lead.origin_lead_id if lead else None
        stem = origin_lead_id or f"unparseable-{abs(hash(json.dumps(payload, sort_keys=True, default=str))):x}"
        directory = corpus_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{_SAFE_ID.sub('_', stem)}.json"
        record = {
            "label": parsed_args.label,
            "recorded_by": "olx.webhook.record_delivery",
            "body": payload,
        }
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return RecordDeliveryOutput(
            recorded=True,
            path=str(path),
            origin_lead_id=origin_lead_id,
            corpus_size=len(list(directory.glob("*.json"))),
            violations=_violation_dicts(validate_olx_lead_payload(payload)),
        ).model_dump()
    except (api.OlxApiError, OSError) as exc:
        return RecordDeliveryOutput(
            recorded=False, error=typed_error(api.map_seed_error(exc))
        ).model_dump()


def _load_corpus() -> list[dict[str, Any]]:
    directory = corpus_dir()
    if not directory.exists():
        return []
    bodies: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # A corrupt fixture is a corpus problem, not a contract
            # problem — skipping it would silently shrink the evidence,
            # so it is surfaced as an entry the diff reports on.
            bodies.append({"__corpus_error__": str(path)})
            continue
        bodies.append(record.get("body", record))
    return bodies


async def contract_diff_observed(args: dict) -> dict:
    DiffObservedInput(**args)
    bodies = _load_corpus()
    report = diff_observed(bodies)
    if not bodies:
        next_step = (
            "The corpus is empty, so this proves nothing. Capture a real "
            "delivery first — point the vendor's endpoint validator "
            "(developers.grupozap.com/webhooks/endpoint_validator/) at the "
            "receiver, then record the body with olx.webhook.record_delivery."
        )
    elif report["clean"]:
        next_step = (
            "No divergence across the corpus. Flip the `verified` flags in "
            "noctusai_lib/integrations/olx/contract.py and stamp the date in "
            "KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/olx.md's change log."
        )
    else:
        next_step = (
            "Divergence found. Fix contract.py FIRST (it is what the product "
            "receiver validates with), then record the observation and the "
            "date in the KB change log."
        )
    return DiffObservedOutput(
        report=report,
        corpus_size=len(bodies),
        clean=bool(bodies) and report["clean"],
        next_step=next_step,
    ).model_dump()


def _build_simulated_body(parsed_args: SimulateInput) -> dict[str, Any]:
    body = json.loads(json.dumps(OLX_SAMPLE_LEAD))  # deep copy
    if parsed_args.origin_lead_id:
        body["originLeadId"] = parsed_args.origin_lead_id
    if parsed_args.lead_type:
        body["extraData"]["leadType"] = parsed_args.lead_type
    if parsed_args.temperature:
        body["temperature"] = parsed_args.temperature
    if parsed_args.transaction_type:
        body["transactionType"] = parsed_args.transaction_type
    if parsed_args.mcmv:
        body["leadOrigin"] = OLX_LEAD_ORIGIN_MCMV
        body.pop("originListingId", None)
        body.pop("clientListingId", None)
    elif "client_listing_id" in parsed_args.model_fields_set:
        # Explicit null is the point — it rehearses the documented 4xx.
        if parsed_args.client_listing_id is None:
            body.pop("clientListingId", None)
        else:
            body["clientListingId"] = parsed_args.client_listing_id
    return body


def _interpret(status: int) -> str:
    if 200 <= status < 300:
        return ("2xx — OLX marks the lead delivered and never sends it again. "
                "The response body is ignored entirely.")
    return (f"{status} — OLX treats this as a FAILURE. It retries up to 3 times, "
            "stores the lead for 14 days, then discards it permanently. There is "
            "no replay API.")


async def simulate(args: dict) -> dict:
    parsed_args = SimulateInput(**args)
    try:
        if not parsed_args.confirm:
            raise api.ConfirmationRequiredError(
                "olx.webhook.simulate",
                "POSTs a synthetic lead at the configured receiver",
            )
        settings = get_settings()
        api.require_receiver_configured(settings)

        body = _build_simulated_body(parsed_args)
        secret = settings.webhook_secret or ""
        if parsed_args.wrong_secret:
            secret = f"{secret}-deliberately-wrong"
        credential = base64.b64encode(
            f"{GRUPO_OLX_BASIC_USERNAME}:{secret}".encode()
        ).decode("ascii")

        encoded = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(  # noqa: S310 — operator-supplied receiver URL
            settings.receiver_url,
            data=encoded,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Basic {credential}",
                "User-Agent": "noctusai-olx-simulator",
            },
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=settings.timeout_seconds) as response:  # noqa: S310
                status = int(response.status)
        except urllib.error.HTTPError as exc:
            # A non-2xx is a RESULT here, not an error — rehearsing the
            # reject path is half the point of this tool.
            status = int(exc.code)
        latency_ms = round((time.monotonic() - started) * 1000, 1)

        return SimulateOutput(
            sent=True,
            receiver_url=settings.receiver_url,
            http_status=status,
            latency_ms=latency_ms,
            interpretation=_interpret(status),
            payload=body,
        ).model_dump()
    except (api.OlxApiError, urllib.error.URLError, OSError, ValueError) as exc:
        return SimulateOutput(
            sent=False, error=typed_error(api.map_seed_error(exc))
        ).model_dump()


HANDLERS = {
    "olx.webhook.describe_contract": describe_contract,
    "olx.webhook.validate_payload": validate_payload,
    "olx.webhook.record_delivery": record_delivery,
    "olx.webhook.simulate": simulate,
    "olx.contract.diff_observed": contract_diff_observed,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="olx.webhook.describe_contract",
            description=(
                "The Grupo OLX lead-webhook contract: auth, delivery model, "
                "every field with type/required/notes, enums, response "
                "semantics, retry policy, JSON Schema and the vendor's sample. "
                "READ-ONLY, zero IO, no credentials needed. Served from the "
                "same seed module the product receiver validates with, so the "
                "map and the runtime cannot drift apart."
            ),
            inputSchema=DescribeContractInput.model_json_schema(),
        ),
        Tool(
            name="olx.webhook.validate_payload",
            description=(
                "Check one delivery body against the documented contract. "
                "Returns typed violations plus `would_return_4xx` — the ONE "
                "case (a listing lead with no clientListingId) where a non-2xx "
                "is correct. READ-ONLY, zero IO."
            ),
            inputSchema=ValidatePayloadInput.model_json_schema(),
        ),
        Tool(
            name="olx.webhook.record_delivery",
            description=(
                "Persist a REAL inbound body into the observed corpus that "
                "olx.contract.diff_observed reads. WRITE — requires confirm=true. "
                "Unparseable bodies are recorded too; they are the shapes the "
                "receiver would drop."
            ),
            inputSchema=RecordDeliveryInput.model_json_schema(),
        ),
        Tool(
            name="olx.webhook.simulate",
            description=(
                "POST a synthetic lead at OUR configured receiver with a real "
                "Basic header — the stand-in for the sandbox OLX does not "
                "provide. Can rehearse the reject paths too (wrong_secret=true "
                "expects 401; client_listing_id=null expects 4xx). WRITE — "
                "requires confirm=true."
            ),
            inputSchema=SimulateInput.model_json_schema(),
        ),
        Tool(
            name="olx.contract.diff_observed",
            description=(
                "Diff every recorded real delivery against the documented "
                "contract: undocumented fields, documented-but-never-seen "
                "fields, required fields that arrived null, novel enum values. "
                "This is the tool that closes the doc-vs-reality loop; its "
                "output is what gets written into the KB change log. READ-ONLY."
            ),
            inputSchema=DiffObservedInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
