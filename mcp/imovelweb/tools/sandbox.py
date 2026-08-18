"""`imovelweb.sandbox.*` — ask the vendor to push a real delivery at us.

This is the tool the Grupo OLX connector could not have, and the reason
this project's gate order differs from that one's. OLX offered no sandbox,
so its Gate 1 could not close without production traffic — a real customer
enquiry was the first test. Here the vendor runs an event simulator, so the
end-to-end contract is provable before a single real lead exists.

Two refusals guard it, and both are refusals rather than warnings:

- **Non-sandbox host.** Enforced in the seed
  (`ImovelWebClient.emit_event`), not re-implemented here — a second,
  weaker copy of a safety check is how the weaker one ends up being the
  one that runs. It fabricates lead events; pointed at production those
  would be indistinguishable from real customers inside a client's CRM.
- **An incomplete payload.** `CONTACTO_MENSAJE` needs name, phone, email
  and message; `CONTACTO` needs only an email. Sending a partial one
  produces a delivery that exercises the wrong branch of our parser and
  proves something we did not mean to prove.

The sandbox is up roughly 07:00-21:00 UTC-3. Outside that window the call
times out, so the window is surfaced in the result rather than left as a
mystery.
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error
from noctusai_lib.integrations.imovelweb import (
    IMOVELWEB_EVENT_TYPES,
    IMOVELWEB_SANDBOX_WINDOW,
    ImovelWebError,
)

from .. import api
from ..client import get_client
from ..settings import get_settings
from ..types import SandboxEmitEventInput, SandboxEmitEventOutput

logger = logging.getLogger(__name__)

#: What the vendor requires per event type, in canonical argument names.
_REQUIRED_FIELDS = {
    "CONTACTO_MENSAJE": ("contact_name", "contact_phone", "contact_email", "contact_message"),
    "CONTACTO": ("contact_email",),
}


def _build_payload(parsed_args: SandboxEmitEventInput) -> dict:
    """The vendor's `CallbackEventoDTO`.

    `configuracionCallback` is deliberately omitted: leaving it out makes
    the simulator use the REGISTERED configuration, which is the thing we
    are actually trying to test. Supplying an inline one would prove that
    the simulator works, not that our registration does.
    """
    payload = {
        "tipoDeEvento": parsed_args.event_type,
        "codigoInmobiliaria": parsed_args.codigo_imobiliaria,
    }
    optional = {
        "codigoAviso": parsed_args.codigo_aviso,
        "contactName": parsed_args.contact_name,
        "contactEmail": parsed_args.contact_email,
        "contactPhone": parsed_args.contact_phone,
        "contactMessage": parsed_args.contact_message,
        "referer": parsed_args.referer,
    }
    payload.update({k: v for k, v in optional.items() if v})
    return payload


async def emit_event(args: dict) -> dict:
    parsed_args = SandboxEmitEventInput(**args)
    settings = get_settings()
    try:
        if not parsed_args.confirm:
            raise api.ConfirmationRequiredError(
                "imovelweb.sandbox.emit_event",
                "asks the vendor to push a REAL delivery at whatever receiver "
                "is currently registered",
            )
        if parsed_args.event_type not in IMOVELWEB_EVENT_TYPES:
            raise api.ImovelWebApiError(
                f"unknown event type {parsed_args.event_type!r} — known: "
                f"{', '.join(IMOVELWEB_EVENT_TYPES)}",
                status=422,
            )
        required = _REQUIRED_FIELDS.get(parsed_args.event_type, ())
        missing = [f for f in required if not getattr(parsed_args, f, None)]
        if missing:
            raise api.ImovelWebApiError(
                f"{parsed_args.event_type} requires {', '.join(required)}; "
                f"missing {', '.join(missing)}. A partial event exercises the "
                "wrong branch of our parser and proves the wrong thing.",
                status=422,
            )

        payload = _build_payload(parsed_args)
        client = get_client()
        response = await client.emit_event(payload)
        return SandboxEmitEventOutput(
            emitted=True,
            base_url=settings.base_url,
            sandbox_window=IMOVELWEB_SANDBOX_WINDOW,
            payload=payload,
            response=api.redact(response, settings, client),
            next_step=(
                "The vendor now delivers to the REGISTERED receiver — check "
                "imovelweb.callbacks.get_config if nothing arrives — then "
                "capture the body with imovelweb.webhook.record_delivery and "
                "close the loop with imovelweb.contract.diff_observed."
            ),
        ).model_dump()
    except (api.ImovelWebApiError, ImovelWebError) as exc:
        mapped = api.map_seed_error(exc)
        error = typed_error(mapped)
        if mapped.status in (502, None):
            # A timeout here is usually the sandbox being closed, not broken.
            error["hint"] = (
                f"the sandbox is available roughly {IMOVELWEB_SANDBOX_WINDOW}; "
                "outside that window this call times out rather than refusing"
            )
        return SandboxEmitEventOutput(
            emitted=False,
            base_url=settings.base_url,
            sandbox_window=IMOVELWEB_SANDBOX_WINDOW,
            error=error,
        ).model_dump()


HANDLERS = {"imovelweb.sandbox.emit_event": emit_event}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="imovelweb.sandbox.emit_event",
            description=(
                "Ask the SANDBOX to push a synthetic lead event at our "
                "registered receiver — the instrument that proves the "
                "end-to-end contract before any real lead exists. HARD-REFUSES "
                "a non-sandbox host: it fabricates leads, and against "
                "production those are indistinguishable from real customers in "
                "a client's CRM. Agency and listing codes must be REAL in the "
                "sandbox. The sandbox runs roughly 07:00-21:00 UTC-3; outside "
                "that it times out. WRITE — requires confirm=true."
            ),
            inputSchema=SandboxEmitEventInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
