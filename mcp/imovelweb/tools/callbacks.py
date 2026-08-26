"""`imovelweb.callbacks.*` — the registration that decides where every
agency's leads go.

This is the most dangerous surface in the connector and the reason it was
worth building before the receiver. `PUT /v1/configuracao/callbacks` takes
**no agency code**: the configuration is integrator-wide, so one bad write
redirects the leads of every agency authorized to our integration, at once,
with no error anywhere.

Three habits follow from that, and they are enforced here rather than
remembered:

1. **Confirm before effect.** The gate is evaluated before settings are
   even read, so "gated" means "nothing happened", not "it failed after".
2. **Read back and diff.** A PUT that silently drops `subscriptions` is
   invisible — and a config with no subscriptions delivers nothing, ever,
   while reporting perfect health. The likeliest production incident on
   this integration is a URL that is right and a subscription list that is
   empty.
3. **Keep the previous config.** After a bad write the vendor cannot tell
   you what you had. We can.

The `authorizationHeaderValue` is redacted out of every result. There is no
signature scheme here — that header IS the entire inbound security
boundary, and an MCP result goes straight into a model's context window.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error
from noctusai_lib.integrations.imovelweb import (
    IMOVELWEB_EVENT_TYPES,
    IMOVELWEB_LEAD_EVENT_TYPES,
    CallbackConfig,
    ImovelWebError,
    basic_credential,
    receiver_url_problems,
)

from .. import api
from ..client import get_client
from ..settings import get_settings
from ..types import (
    CallbacksGetConfigInput,
    CallbacksGetConfigOutput,
    CallbacksPutConfigInput,
    CallbacksPutConfigOutput,
    CallbacksSubscribeInput,
    CallbacksSubscribeOutput,
    CallbacksUnsubscribeInput,
    CallbacksUnsubscribeOutput,
)

logger = logging.getLogger(__name__)

#: Events a ReadOnly integration never receives. Subscribing to one from a
#: ReadOnly integration succeeds and then delivers nothing — a silence that
#: looks exactly like a broken receiver.
_WRITE_SCOPE_EVENTS = tuple(
    e for e in IMOVELWEB_EVENT_TYPES if e not in IMOVELWEB_LEAD_EVENT_TYPES
)

_REDACTED_HEADER = "***REDACTED***"


def _public_config(config: Optional[CallbackConfig]) -> Optional[dict[str, Any]]:
    """The wire shape, minus the credential."""
    if config is None:
        return None
    wire = config.to_wire()
    if wire.get("authorizationHeaderValue"):
        wire["authorizationHeaderValue"] = _REDACTED_HEADER
    return wire


def _drift(requested: CallbackConfig, applied: CallbackConfig) -> list[str]:
    """What the vendor did differently from what we asked for.

    Compared field by field rather than by equality so the report names the
    field. `subscriptions` is compared as a SET: the vendor is free to
    reorder, and a reordering reported as drift would train the reader to
    ignore this list.
    """
    out: list[str] = []
    if requested.url != applied.url:
        out.append(f"url: requested {requested.url!r}, vendor has {applied.url!r}")
    if requested.language != applied.language:
        out.append(
            f"lenguajeCallbackBody: requested {requested.language!r}, vendor has "
            f"{applied.language!r} — this changes the FIELD NAMES of every body"
        )
    if requested.authorization_header_key != applied.authorization_header_key:
        out.append(
            f"authorizationHeaderKey: requested "
            f"{requested.authorization_header_key!r}, vendor has "
            f"{applied.authorization_header_key!r}"
        )
    if requested.authorization_header_value != applied.authorization_header_value:
        # Never echo either value.
        out.append(
            "authorizationHeaderValue: the vendor stored something different "
            "from what we sent — every delivery will fail our verifier with 401"
        )
    if set(requested.subscriptions) != set(applied.subscriptions):
        dropped = sorted(set(requested.subscriptions) - set(applied.subscriptions))
        added = sorted(set(applied.subscriptions) - set(requested.subscriptions))
        out.append(
            f"subscriptions: dropped={dropped or None} added={added or None} — "
            "a dropped subscription delivers nothing and reports no error"
        )
    return out


async def get_config(args: dict) -> dict:
    CallbacksGetConfigInput(**args)
    settings = get_settings()
    try:
        client = get_client()
        config = await client.get_callback_config()
        registered_url = (config.url or "").rstrip("/")
        our_url = (settings.receiver_url or "").rstrip("/")
        return CallbacksGetConfigOutput(
            fetched=True,
            config=api.redact(_public_config(config), settings, client),
            subscriptions=list(config.subscriptions),
            delivers_nothing=not config.subscriptions,
            receiver_url_matches=(
                (registered_url == our_url) if our_url else None
            ),
            problems=list(config.validate()),
        ).model_dump()
    except (api.ImovelWebApiError, ImovelWebError) as exc:
        return CallbacksGetConfigOutput(
            fetched=False, error=typed_error(api.map_seed_error(exc))
        ).model_dump()


async def put_config(args: dict) -> dict:
    parsed_args = CallbacksPutConfigInput(**args)
    try:
        # First, before settings are even read: gated means nothing happened.
        if not parsed_args.confirm:
            raise api.ConfirmationRequiredError(
                "imovelweb.callbacks.put_config",
                "rewrites the INTEGRATOR-WIDE callback registration — there is "
                "no agency code in this call, so it redirects EVERY agency's "
                "leads at once",
            )
        settings = get_settings()

        url = parsed_args.url or settings.receiver_url
        if not url:
            raise api.ImovelWebApiError(
                "no receiver url — pass `url` or set IMOVELWEB_RECEIVER_URL.",
                status=424,
            )
        if not settings.webhook_secret:
            raise api.ImovelWebApiError(
                "IMOVELWEB_WEBHOOK_SECRET is not set. We choose this secret "
                "ourselves and it becomes the whole inbound security boundary "
                "— registering without one would accept any request that "
                "reached the receiver.",
                status=424,
            )

        warnings: list[str] = []
        url_problems = receiver_url_problems(url)
        if url_problems and not parsed_args.allow_local_url:
            raise api.ImovelWebApiError(
                "refusing to register this receiver url: "
                + "; ".join(url_problems)
                + ". The registration is integrator-wide, so an unreachable "
                "url blackholes every agency's leads and reports no error "
                "anywhere. Pass allow_local_url=true only for a rehearsal.",
                status=422,
            )
        if url_problems:
            warnings.append(
                "registered anyway (allow_local_url=true): "
                + "; ".join(url_problems)
            )

        requested = CallbackConfig(
            url=url,
            authorization_header_value=basic_credential(settings.webhook_secret),
            authorization_header_key=parsed_args.authorization_header_key or "Authorization",
            language=parsed_args.language or "EN2",
            subscriptions=tuple(parsed_args.subscriptions)
            if parsed_args.subscriptions is not None
            else IMOVELWEB_LEAD_EVENT_TYPES,
        )
        problems = requested.validate()
        if problems:
            raise api.ImovelWebApiError(
                "refusing to register an invalid config: " + "; ".join(problems),
                status=422,
            )
        subscribed_write_scope = [
            e for e in requested.subscriptions if e in _WRITE_SCOPE_EVENTS
        ]
        if subscribed_write_scope:
            warnings.append(
                f"{', '.join(subscribed_write_scope)} are delivered only to a "
                "Read-and-Write integration. On a ReadOnly one this subscribes "
                "successfully and then delivers nothing — a silence that looks "
                "like a broken receiver."
            )

        client = get_client()

        previous = None
        try:
            previous = await client.get_callback_config()
        except (api.ImovelWebApiError, ImovelWebError) as exc:
            # Not fatal — first-time registration has nothing to read. But
            # say what was lost: after a bad PUT the vendor cannot tell you
            # what you had, and this was the only copy.
            warnings.append(
                "could not read the previous configuration "
                f"({type(exc).__name__}) — if this write is wrong there is "
                "nothing to roll back to."
            )

        applied = await client.put_callback_config(requested)
        drift = _drift(requested, applied)
        if not applied.subscriptions:
            warnings.append(
                "the vendor reports NO subscriptions after this write — it "
                "will deliver nothing, silently. Fix before relying on it."
            )

        return CallbacksPutConfigOutput(
            registered=True,
            requested=api.redact(_public_config(requested), settings, client),
            previous=api.redact(_public_config(previous), settings, client),
            applied=api.redact(_public_config(applied), settings, client),
            drift=drift,
            warnings=warnings,
        ).model_dump()
    except (api.ImovelWebApiError, ImovelWebError, ValueError) as exc:
        return CallbacksPutConfigOutput(
            registered=False, error=typed_error(api.map_seed_error(exc))
        ).model_dump()


def _check_event(event: str) -> list[str]:
    """Unknown events are refused, not passed through.

    The inverse of the receiver's rule — there, an unknown event is carried
    so a real lead is never dropped. Here it is a typo in an argument, and
    passing it through registers a subscription that can never fire.
    """
    if event not in IMOVELWEB_EVENT_TYPES:
        raise api.ImovelWebApiError(
            f"unknown event {event!r} — known: {', '.join(IMOVELWEB_EVENT_TYPES)}. "
            "A subscription to an unknown event succeeds and then never fires.",
            status=422,
        )
    if event in _WRITE_SCOPE_EVENTS:
        return [
            f"{event} is delivered only to a Read-and-Write integration. On a "
            "ReadOnly one this subscribes and then delivers nothing."
        ]
    return []


async def _read_subscriptions(client) -> list[str]:
    """The read-back half. A subscribe that reports success and changes
    nothing is the failure mode this catches."""
    config = await client.get_callback_config()
    return list(config.subscriptions)


async def subscribe(args: dict) -> dict:
    parsed_args = CallbacksSubscribeInput(**args)
    try:
        if not parsed_args.confirm:
            raise api.ConfirmationRequiredError(
                "imovelweb.callbacks.subscribe",
                "changes the INTEGRATOR-WIDE subscription list — it affects "
                "every agency's deliveries",
            )
        warnings = _check_event(parsed_args.event)
        client = get_client()
        await client.subscribe_event(parsed_args.event)
        subscriptions = await _read_subscriptions(client)
        if parsed_args.event not in subscriptions:
            warnings.append(
                f"{parsed_args.event} is NOT in the configuration after the "
                "call — the vendor accepted it and did not store it."
            )
        return CallbacksSubscribeOutput(
            subscribed=True,
            event=parsed_args.event,
            subscriptions=subscriptions,
            warnings=warnings,
        ).model_dump()
    except (api.ImovelWebApiError, ImovelWebError) as exc:
        return CallbacksSubscribeOutput(
            subscribed=False, error=typed_error(api.map_seed_error(exc))
        ).model_dump()


async def unsubscribe(args: dict) -> dict:
    parsed_args = CallbacksUnsubscribeInput(**args)
    try:
        if not parsed_args.confirm:
            raise api.ConfirmationRequiredError(
                "imovelweb.callbacks.unsubscribe",
                "STOPS delivery of this event for every agency — the leads "
                "are not queued, they are simply never sent",
            )
        _check_event(parsed_args.event)
        client = get_client()
        await client.unsubscribe_event(parsed_args.event)
        subscriptions = await _read_subscriptions(client)
        warnings: list[str] = []
        if not subscriptions:
            warnings.append(
                "no subscriptions remain — the integration now delivers "
                "nothing at all, silently."
            )
        return CallbacksUnsubscribeOutput(
            unsubscribed=True,
            event=parsed_args.event,
            subscriptions=subscriptions,
            warnings=warnings,
        ).model_dump()
    except (api.ImovelWebApiError, ImovelWebError) as exc:
        return CallbacksUnsubscribeOutput(
            unsubscribed=False, error=typed_error(api.map_seed_error(exc))
        ).model_dump()


HANDLERS = {
    "imovelweb.callbacks.get_config": get_config,
    "imovelweb.callbacks.put_config": put_config,
    "imovelweb.callbacks.subscribe": subscribe,
    "imovelweb.callbacks.unsubscribe": unsubscribe,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="imovelweb.callbacks.get_config",
            description=(
                "Read the registered callback configuration back from the "
                "vendor: URL, header key, language, and subscriptions. Flags "
                "`delivers_nothing` when no events are subscribed — the vendor "
                "accepts that and then delivers nothing, silently, which is the "
                "likeliest production failure here — and whether the registered "
                "URL still matches ours. The credential is redacted. READ-ONLY."
            ),
            inputSchema=CallbacksGetConfigInput.model_json_schema(),
        ),
        Tool(
            name="imovelweb.callbacks.put_config",
            description=(
                "Register our receiver with the vendor. ⚠️ INTEGRATOR-WIDE: "
                "there is no agency code in this call, so it redirects EVERY "
                "agency's leads at once. Refuses a localhost / private / "
                "ephemeral-tunnel URL, because an unreachable registration "
                "blackholes leads with no error anywhere. Reads the previous "
                "config first (the vendor cannot tell you afterwards what you "
                "had) and diffs what was applied against what was asked. "
                "WRITE — requires confirm=true."
            ),
            inputSchema=CallbacksPutConfigInput.model_json_schema(),
        ),
        Tool(
            name="imovelweb.callbacks.subscribe",
            description=(
                "Subscribe one event type, then read the configuration back to "
                "prove it stuck. Unknown event names are refused rather than "
                "passed through: a subscription to a name the vendor does not "
                "know succeeds and then never fires. AVISO_* and CREDITO reach "
                "only Read-and-Write integrations. WRITE — requires confirm=true."
            ),
            inputSchema=CallbacksSubscribeInput.model_json_schema(),
        ),
        Tool(
            name="imovelweb.callbacks.unsubscribe",
            description=(
                "Stop delivery of one event type for every agency. The leads "
                "are not queued for later — they are simply never sent. Warns "
                "when the last subscription is removed. WRITE — requires "
                "confirm=true."
            ),
            inputSchema=CallbacksUnsubscribeInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
