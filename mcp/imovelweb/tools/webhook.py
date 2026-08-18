"""`imovelweb.webhook.*` — our own receiver: record what arrives, rehearse
what should.

`record_delivery` builds the corpus that `imovelweb.contract.diff_observed`
reads. Unparseable bodies are recorded too, keyed by a hash — they are the
shapes our receiver would drop, which makes them the most valuable evidence
in the corpus, not the least.

`simulate` POSTs a synthetic body at our own receiver with a real
credential. It is not a substitute for `imovelweb.sandbox.emit_event`
(which asks the VENDOR to deliver, and therefore also tests the
registration): it tests the receiver in isolation, works with no vendor
credentials at all, and — the reason it earns its place — **measures the
response latency against the vendor's 1.5-second budget**. That budget is
the single most design-forcing fact in this integration, and a receiver
that answers in 1.8 seconds is not slow, it is losing leads: the vendor
scores the timeout an error and starts a 72-hour retry loop.
"""
from __future__ import annotations

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
from noctusai_lib.integrations.imovelweb import (
    IMOVELWEB_SAMPLE_BODIES,
    LANGUAGE_FIELD_ALIASES,
    basic_credential,
    detect_callback_language,
    parse_imovelweb_callback,
    validate_imovelweb_payload,
)

from .. import api
from ..client import corpus_dir
from ..settings import get_settings
from ..types import (
    WebhookRecordDeliveryInput,
    WebhookRecordDeliveryOutput,
    WebhookSimulateInput,
    WebhookSimulateOutput,
)

logger = logging.getLogger(__name__)

_SAFE_ID = re.compile(r"[^A-Za-z0-9_.-]")

#: The vendor's hard limit. Not a target — a slower answer is scored an
#: error and starts the 72-hour retry loop.
RESPONSE_BUDGET_MS = 1500.0

DEFAULT_LANGUAGE = "EN2"


def _wire_name(language: str, canonical: str) -> Optional[str]:
    """The field name this language uses for a canonical field.

    Derived from the contract's alias table rather than hardcoded, because
    the whole point of the five-language problem is that the names are
    configuration, not constants.
    """
    for name, target in LANGUAGE_FIELD_ALIASES.get(language, {}).items():
        if target == canonical:
            return name
    return None


async def record_delivery(args: dict) -> dict:
    parsed_args = WebhookRecordDeliveryInput(**args)
    try:
        if not parsed_args.confirm:
            raise api.ConfirmationRequiredError(
                "imovelweb.webhook.record_delivery",
                "writes a delivery body into the observed corpus",
            )
        payload = parsed_args.payload
        detected = detect_callback_language(payload)
        language = parsed_args.language or detected or DEFAULT_LANGUAGE
        lead = parse_imovelweb_callback(payload, language=language)
        result = validate_imovelweb_payload(payload, language=language)

        event_id = lead.event_id if lead else None
        # An unparseable body is still evidence — arguably the most
        # valuable kind, since it is the shape our receiver would drop. Key
        # it by hash so it is recorded rather than refused.
        stem = event_id or (
            "unparseable-"
            f"{abs(hash(json.dumps(payload, sort_keys=True, default=str))):x}"
        )
        directory = corpus_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{_SAFE_ID.sub('_', stem)}.json"
        path.write_text(
            json.dumps(
                {
                    "label": parsed_args.label,
                    "recorded_by": "imovelweb.webhook.record_delivery",
                    "detected_language": detected,
                    "body": payload,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return WebhookRecordDeliveryOutput(
            recorded=True,
            path=str(path),
            event_id=event_id,
            detected_language=detected,
            corpus_size=len(list(directory.glob("*.json"))),
            errors=result.get("error", []),
            warnings=result.get("warning", []),
        ).model_dump()
    except (api.ImovelWebApiError, OSError) as exc:
        return WebhookRecordDeliveryOutput(
            recorded=False, error=typed_error(api.map_seed_error(exc))
        ).model_dump()


def _build_body(parsed_args: WebhookSimulateInput, language: str) -> dict[str, Any]:
    sample = IMOVELWEB_SAMPLE_BODIES.get(language)
    if sample is None:
        raise api.ImovelWebApiError(
            f"no sample body transcribed for language {language!r} — available: "
            f"{', '.join(sorted(IMOVELWEB_SAMPLE_BODIES))}. Record a real one "
            "with imovelweb.webhook.record_delivery and add it to contract.py "
            "rather than inventing one here.",
            status=422,
        )
    body = json.loads(json.dumps(sample))  # deep copy
    if parsed_args.event_id:
        key = _wire_name(language, "event_id")
        if key:
            body[key] = parsed_args.event_id
    if parsed_args.event_type:
        key = _wire_name(language, "event_type")
        if key:
            body[key] = parsed_args.event_type
    return body


def _interpret(status: int) -> str:
    # This vendor counts 3xx as success too — unusual, documented, and
    # never something to rely on.
    if 200 <= status < 400:
        return (
            f"{status} — delivered. ImovelWeb counts any 2xx OR 3xx as success "
            "and never sends this event again."
        )
    return (
        f"{status} — FAILURE. ImovelWeb retries until 72 hours have passed, "
        "then marks the callback VENCIDO and stops. The lead is recoverable "
        "in the meantime through imovelweb.leads.list_messages, which is the "
        "only reason a miss here is survivable."
    )


async def simulate(args: dict) -> dict:
    parsed_args = WebhookSimulateInput(**args)
    settings = get_settings()
    try:
        if not parsed_args.confirm:
            raise api.ConfirmationRequiredError(
                "imovelweb.webhook.simulate",
                "POSTs a synthetic lead at the configured receiver",
            )
        api.require_receiver_configured(settings)

        language = parsed_args.language or DEFAULT_LANGUAGE
        body = _build_body(parsed_args, language)

        secret = settings.webhook_secret or ""
        if parsed_args.wrong_secret:
            secret = f"{secret}-deliberately-wrong"

        request = urllib.request.Request(  # noqa: S310 — operator-supplied receiver
            settings.receiver_url,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": basic_credential(secret),
                "User-Agent": "noctusai-imovelweb-simulator",
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

        interpretation = _interpret(status)
        within_budget = latency_ms <= RESPONSE_BUDGET_MS
        if not within_budget:
            interpretation += (
                f" ⚠️ The receiver took {latency_ms}ms, over the vendor's "
                f"{RESPONSE_BUDGET_MS}ms limit — in production that is scored "
                "a timeout regardless of the status code, and the handler "
                "shape needs revisiting before go-live."
            )

        return WebhookSimulateOutput(
            sent=True,
            receiver_url=settings.receiver_url,
            http_status=status,
            latency_ms=latency_ms,
            response_budget_ms=RESPONSE_BUDGET_MS,
            within_response_budget=within_budget,
            interpretation=interpretation,
            payload=body,
        ).model_dump()
    except (api.ImovelWebApiError, urllib.error.URLError, OSError, ValueError) as exc:
        return WebhookSimulateOutput(
            sent=False, error=typed_error(api.map_seed_error(exc))
        ).model_dump()


HANDLERS = {
    "imovelweb.webhook.record_delivery": record_delivery,
    "imovelweb.webhook.simulate": simulate,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="imovelweb.webhook.record_delivery",
            description=(
                "Persist a REAL inbound body into the observed corpus that "
                "imovelweb.contract.diff_observed reads, detecting which of "
                "the five language variants it is. Unparseable bodies are "
                "recorded too — they are the shapes the receiver would drop, "
                "which makes them the most valuable evidence, not the least. "
                "WRITE — requires confirm=true."
            ),
            inputSchema=WebhookRecordDeliveryInput.model_json_schema(),
        ),
        Tool(
            name="imovelweb.webhook.simulate",
            description=(
                "POST a synthetic lead at OUR receiver with a real credential "
                "and MEASURE the response against the vendor's 1.5-second "
                "budget — a receiver that answers slower is not slow, it is "
                "losing leads to a 72-hour retry loop. Needs no vendor "
                "credentials. Can rehearse the reject path (wrong_secret=true "
                "expects 401). For an end-to-end test that also proves the "
                "registration, use imovelweb.sandbox.emit_event instead. "
                "WRITE — requires confirm=true."
            ),
            inputSchema=WebhookSimulateInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
