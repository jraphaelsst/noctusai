"""`imovelweb.contract.*` — the map of the inbound callback contract, and
the loop that corrects it against reality.

Three tools, all **zero IO and no credentials**. That is not a convenience;
it is what makes this connector usable for diagnosis DURING an incident
rather than being one more thing that is down. They answer the moment the
connector is installed, with no vendor, no network and no model provider
in the path.

Two facts make them load-bearing here in a way they were not for Grupo OLX:

1. The vendor's callback body has **five language variants** and the
   registered `lenguajeCallbackBody` decides the field NAMES, not just the
   prose. A payload that "looks wrong" is usually a payload read as the
   wrong language — `validate_payload` auto-detects rather than assuming.
2. The vendor's OpenAPI spec models **zero** callback bodies. Every field
   here is transcribed from prose, so `diff_observed` against real captures
   is the only honest path to flipping a `verified` flag.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error
from noctusai_lib.integrations.imovelweb import (
    contract_summary,
    detect_callback_language,
    # Aliased: the tool handler below is also called `diff_observed`, and
    # a module that exports both under one name is a trap for the next
    # reader (and for a test that reaches for the handler by attribute).
    diff_observed as seed_diff_observed,
    has_blocking_violation,
    imovelweb_json_schema,
    parse_imovelweb_callback,
    validate_imovelweb_payload,
)

from .. import api
from ..client import corpus_dir
from ..types import (
    ContractDescribeInput,
    ContractDescribeOutput,
    ContractDiffObservedInput,
    ContractDiffObservedOutput,
    ContractValidatePayloadInput,
    ContractValidatePayloadOutput,
)

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "EN2"


async def describe(args: dict) -> dict:
    parsed_args = ContractDescribeInput(**args)
    summary = contract_summary(parsed_args.language)
    schema = None
    if parsed_args.language:
        try:
            schema = imovelweb_json_schema(parsed_args.language)
        except ValueError as exc:
            # An unknown language is the caller's typo, not a contract
            # fact — say so instead of returning an empty contract that
            # reads like "this language has no fields".
            return ContractDescribeOutput(
                contract={"error": str(exc)},
                verified_against_live_traffic=False,
            ).model_dump()
    return ContractDescribeOutput(
        contract=summary,
        verified_against_live_traffic=summary["verified_against_live_traffic"],
        json_schema=schema,
    ).model_dump()


async def validate_payload(args: dict) -> dict:
    parsed_args = ContractValidatePayloadInput(**args)
    detected = detect_callback_language(parsed_args.payload)
    language = parsed_args.language or detected or DEFAULT_LANGUAGE

    result = validate_imovelweb_payload(parsed_args.payload, language=language)
    lead = parse_imovelweb_callback(parsed_args.payload, language=language)
    return ContractValidatePayloadOutput(
        valid=not has_blocking_violation(result),
        detected_language=detected,
        language_used=language,
        errors=result.get("error", []),
        warnings=result.get("warning", []),
        parsed=(
            {
                "event_id": lead.event_id,
                "event_type": lead.event_type,
                "codigo_imobiliaria": lead.codigo_imobiliaria,
                "lead_origin": lead.lead_origin,
                "client_listing_id": lead.client_listing_id,
                "contact_type": lead.contact_type,
                "name": lead.name,
                "email": lead.email,
                "full_phone": lead.full_phone,
                "is_message_lead": lead.is_message_lead,
                # `identification_id` is a CPF and is deliberately absent
                # from this projection — see `api.strip_pii`.
                "carries_national_id": bool(lead.identification_id),
            }
            if lead is not None
            else None
        ),
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
            # problem — skipping it silently would shrink the evidence
            # without saying so, so it is carried through as an entry the
            # diff reports on.
            bodies.append({"__corpus_error__": str(path)})
            continue
        bodies.append(record.get("body", record))
    return bodies


async def diff_observed(args: dict) -> dict:
    parsed_args = ContractDiffObservedInput(**args)
    language = parsed_args.language or DEFAULT_LANGUAGE
    bodies = _load_corpus()
    try:
        report = seed_diff_observed(bodies, language=language)
    except ValueError as exc:
        return ContractDiffObservedOutput(
            report=typed_error(api.map_seed_error(exc)),
            corpus_size=len(bodies),
            clean=False,
            next_step=f"Unknown language {language!r} — pick one of EN, EN2, EN_SF, ES, PT.",
        ).model_dump()

    undocumented = report.get("undocumented_fields", [])
    clean = bool(bodies) and not undocumented

    if not bodies:
        next_step = (
            "The corpus is empty, so this proves nothing. Capture a delivery "
            "first: imovelweb.sandbox.emit_event asks the vendor to push a "
            "synthetic CONTACTO_MENSAJE at our receiver, then record the body "
            "with imovelweb.webhook.record_delivery. Unlike Grupo OLX this "
            "does NOT require production traffic."
        )
    elif clean:
        next_step = (
            "No undocumented field across the corpus. Flip the `verified` "
            "flags in noctusai_lib/integrations/imovelweb/contract.py and date "
            "the evidence in KB § INTEGRATIONS/imovelweb.md § 8. Never flip "
            "them from a document — the vendor's spec models zero callback "
            "bodies, so a document cannot confirm this."
        )
    else:
        next_step = (
            "Divergence found. Fix contract.py FIRST — it is what the product "
            "receiver validates with — then date the observation in the KB "
            "change log."
        )
    return ContractDiffObservedOutput(
        report=report, corpus_size=len(bodies), clean=clean, next_step=next_step
    ).model_dump()


HANDLERS = {
    "imovelweb.contract.describe": describe,
    "imovelweb.contract.validate_payload": validate_payload,
    "imovelweb.contract.diff_observed": diff_observed,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="imovelweb.contract.describe",
            description=(
                "The ImovelWeb / OpenNavent callback contract: response "
                "semantics (2xx AND 3xx succeed), the 1.5-second answer budget, "
                "the 72-hour retry window ending in VENCIDO, and every field "
                "per language variant with type/required/verified/notes. Pass "
                "`language` for one variant plus its JSON Schema. READ-ONLY, "
                "zero IO, NO credentials — works during an outage. Served from "
                "the same seed module the product receiver validates with, so "
                "the map and the runtime cannot drift apart."
            ),
            inputSchema=ContractDescribeInput.model_json_schema(),
        ),
        Tool(
            name="imovelweb.contract.validate_payload",
            description=(
                "Check one delivery body against the contract, auto-detecting "
                "which of the five language variants it is (the registered "
                "language decides the FIELD NAMES, so a body that looks wrong "
                "is usually one read as the wrong language). Returns blocking "
                "`errors` — only ever 'no event id', because a body we cannot "
                "deduplicate cannot be stored — separately from `warnings`, "
                "which still get a 2xx. READ-ONLY, zero IO."
            ),
            inputSchema=ContractValidatePayloadInput.model_json_schema(),
        ),
        Tool(
            name="imovelweb.contract.diff_observed",
            description=(
                "Diff every recorded real delivery against the transcribed "
                "contract: undocumented fields, documented-but-never-seen "
                "fields, confirmed fields. This is the tool that closes the "
                "doc-vs-reality loop, and its output is what gets written into "
                "the KB change log. An empty corpus is reported as NOT clean — "
                "it proves nothing. READ-ONLY."
            ),
            inputSchema=ContractDiffObservedInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
