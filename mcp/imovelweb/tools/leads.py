"""`imovelweb.leads.*` — the pull side: reconciliation reads and enrichment.

These four tools exist because this vendor, unlike Grupo OLX, has a pull
API. That single fact changes the durability story: a callback we missed is
recoverable as long as we re-read the window inside 72 hours, which is what
makes the vendor's 1.5-second answer budget survivable at all.

Every result is PII-filtered by default. `identificationId` is a CPF — a
direct national identifier, and the highest-value personal data in the
whole leads pipeline. LGPD minimization (Art. 6.III) says we do not surface
what no feature uses, and the argument is stronger here than in the
database: an MCP result goes straight into a model's context window, which
is a log we do not control. `include_pii=true` is available, deliberately
explicit, and reported back in the result.
"""
from __future__ import annotations

import logging
from typing import Any

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error
from noctusai_lib.integrations.imovelweb import (
    IMOVELWEB_CONTACT_TYPES,
    ImovelWebError,
)

from .. import api
from ..client import get_client
from ..settings import get_settings
from ..types import (
    LeadsGetMessageInput,
    LeadsGetMessageOutput,
    LeadsGetSmartleadInput,
    LeadsGetSmartleadOutput,
    LeadsListContactActionsInput,
    LeadsListContactActionsOutput,
    LeadsListMessagesInput,
    LeadsListMessagesOutput,
)

logger = logging.getLogger(__name__)

_RECONCILE_CAVEAT = (
    "A `Mensaje` from this endpoint carries no eventId — the callback's "
    "dedup key. Whether `id`/`idMensaje` share an id space with the "
    "callback's `eventId`/`messageId` is an open vendor question (Gate 0.6); "
    "get it wrong and reconciliation duplicates every lead."
)

_SMARTLEAD_LGPD_NOTE = (
    "Smartlead is behavioural profiling — price range, rooms, m², "
    "neighbourhoods contacted, days searching, listings viewed — about an "
    "identified person. Enrichment only. If a lead is ever scored or routed "
    "on it, LGPD Art. 20 (right to review of automated decisions) engages, "
    "and that is a decision to take before building the scorer, not after."
)


def _present(payload: Any, include_pii: bool, settings, client) -> tuple[Any, int]:
    """Redact secrets always; redact PII unless explicitly asked otherwise."""
    redacted = api.redact(payload, settings, client)
    if include_pii:
        return redacted, 0
    return api.strip_pii(redacted)


async def get_message(args: dict) -> dict:
    parsed_args = LeadsGetMessageInput(**args)
    settings = get_settings()
    try:
        client = get_client()
        payload = await client.get_message(parsed_args.id_mensaje)
        message, redacted = _present(payload, parsed_args.include_pii, settings, client)
        return LeadsGetMessageOutput(
            fetched=True, message=message, pii_redacted=redacted
        ).model_dump()
    except (api.ImovelWebApiError, ImovelWebError) as exc:
        return LeadsGetMessageOutput(
            fetched=False, error=typed_error(api.map_seed_error(exc))
        ).model_dump()


async def list_messages(args: dict) -> dict:
    parsed_args = LeadsListMessagesInput(**args)
    settings = get_settings()
    try:
        client = get_client()
        page = await client.list_agency_messages(
            parsed_args.codigo_imobiliaria,
            from_date=parsed_args.from_date,
            to_date=parsed_args.to_date,
            page=parsed_args.page,
            size=parsed_args.size,
        )
        content, redacted = _present(
            page.get("content") or [], parsed_args.include_pii, settings, client
        )
        return LeadsListMessagesOutput(
            fetched=True,
            messages=content,
            page=page.get("number", parsed_args.page),
            size=page.get("size", parsed_args.size),
            total=page.get("total"),
            pii_redacted=redacted,
            caveat=_RECONCILE_CAVEAT,
        ).model_dump()
    except (api.ImovelWebApiError, ImovelWebError) as exc:
        return LeadsListMessagesOutput(
            fetched=False, error=typed_error(api.map_seed_error(exc))
        ).model_dump()


async def get_smartlead(args: dict) -> dict:
    parsed_args = LeadsGetSmartleadInput(**args)
    settings = get_settings()
    try:
        client = get_client()
        payload = await client.get_smartlead(parsed_args.id_mensagem)
        smartlead, redacted = _present(
            payload, parsed_args.include_pii, settings, client
        )
        return LeadsGetSmartleadOutput(
            fetched=True,
            smartlead=smartlead,
            pii_redacted=redacted,
            lgpd_note=_SMARTLEAD_LGPD_NOTE,
        ).model_dump()
    except (api.ImovelWebApiError, ImovelWebError) as exc:
        return LeadsGetSmartleadOutput(
            fetched=False,
            lgpd_note=_SMARTLEAD_LGPD_NOTE,
            error=typed_error(api.map_seed_error(exc)),
        ).model_dump()


def _catalog_divergence(actions: list[dict[str, Any]]) -> list[str]:
    """Where the live catalog and our hand-transcribed copy disagree.

    Reported rather than auto-applied: the transcribed table is what the
    parser labels leads with, so changing it is a code edit with a diff, not
    a side effect of running a diagnostic.
    """
    live: dict[int, str] = {}
    for action in actions:
        identifier = action.get("id") or action.get("idContactoAccion") or action.get("codigo")
        label = action.get("nombre") or action.get("nome") or action.get("descripcion") or action.get("name")
        if identifier is None:
            continue
        try:
            live[int(identifier)] = str(label) if label is not None else ""
        except (TypeError, ValueError):
            continue

    out: list[str] = []
    for identifier, label in sorted(live.items()):
        ours = IMOVELWEB_CONTACT_TYPES.get(identifier)
        if ours is None:
            out.append(f"{identifier} = {label!r} is live and NOT in our catalog")
        elif label and ours != label:
            out.append(f"{identifier}: ours {ours!r}, live {label!r}")
    for identifier, ours in sorted(IMOVELWEB_CONTACT_TYPES.items()):
        if identifier not in live:
            out.append(f"{identifier} = {ours!r} is in our catalog and NOT live")
    return out


async def list_contact_actions(args: dict) -> dict:
    LeadsListContactActionsInput(**args)
    settings = get_settings()
    transcribed = {str(k): v for k, v in IMOVELWEB_CONTACT_TYPES.items()}
    try:
        client = get_client()
        actions = await client.list_contact_actions()
        actions = api.redact(actions, settings, client)
        return LeadsListContactActionsOutput(
            fetched=True,
            actions=actions,
            transcribed=transcribed,
            divergence=_catalog_divergence(actions),
        ).model_dump()
    except (api.ImovelWebApiError, ImovelWebError) as exc:
        return LeadsListContactActionsOutput(
            fetched=False,
            transcribed=transcribed,
            error=typed_error(api.map_seed_error(exc)),
        ).model_dump()


HANDLERS = {
    "imovelweb.leads.get_message": get_message,
    "imovelweb.leads.list_messages": list_messages,
    "imovelweb.leads.get_smartlead": get_smartlead,
    "imovelweb.leads.list_contact_actions": list_contact_actions,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="imovelweb.leads.get_message",
            description=(
                "Authoritative re-fetch of one message by id. The callback "
                "body is unsigned, so for anything that matters this is the "
                "truth and the delivery is a hint. Background use only — an "
                "upstream round-trip does not fit the vendor's 1.5-second "
                "response budget. CPF is redacted unless include_pii=true. "
                "READ-ONLY."
            ),
            inputSchema=LeadsGetMessageInput.model_json_schema(),
        ),
        Tool(
            name="imovelweb.leads.list_messages",
            description=(
                "Paged messages for one agency from a date — the read the "
                "reconciliation job is built on, and the reason a missed "
                "callback is recoverable here at all. `from_date` is yyyyMMdd. "
                "Note the caveat: these rows carry no eventId, so deduplicating "
                "them against callback deliveries is an unsettled question. CPF "
                "redacted unless include_pii=true. READ-ONLY."
            ),
            inputSchema=LeadsListMessagesInput.model_json_schema(),
        ),
        Tool(
            name="imovelweb.leads.get_smartlead",
            description=(
                "Buyer-intent enrichment for one message: price range, rooms, "
                "baths, m², neighbourhoods contacted, days searching, listings "
                "viewed. Enrichment only — it sits downstream of the durable "
                "write and its absence is a degradation, never a lost lead. "
                "Behavioural profiling of an identified person; see the "
                "lgpd_note in the result. READ-ONLY."
            ),
            inputSchema=LeadsGetSmartleadInput.model_json_schema(),
        ),
        Tool(
            name="imovelweb.leads.list_contact_actions",
            description=(
                "The vendor's authoritative contactTypeId catalog, diffed "
                "against the hand-transcribed copy in the seed. This is what "
                "closes Gate 1.11. Divergence is REPORTED, never auto-applied: "
                "the transcribed table is what labels leads, so changing it "
                "should be a code diff a human reads. READ-ONLY."
            ),
            inputSchema=LeadsListContactActionsInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
