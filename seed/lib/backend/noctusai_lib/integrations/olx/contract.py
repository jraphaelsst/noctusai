"""The Grupo OLX lead-webhook contract — the SINGLE source of truth.

Both consumers import from here and neither restates it:

* `mcp/olx` serves it to an agent (`olx.webhook.describe_contract`) and
  diffs captured live bodies against it (`olx.contract.diff_observed`).
* the product receiver validates real deliveries with
  `validate_olx_lead_payload` before persisting.

If these were two copies they would disagree within a release, and the
disagreement would surface as leads silently rejected in production.

**Everything here is transcribed from developers.grupozap.com as of
2026-08-17 and is UNVERIFIED against live traffic.** Each row carries its
own `verified` flag; `Gate 1` in the project doc is the pass that flips
them. Do not treat a `verified=False` row as fact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .types import (
    OLX_LEAD_ORIGIN_MCMV,
    OLX_LEAD_ORIGIN_STANDARD,
    OLX_LEAD_TYPES,
    OLX_TEMPERATURES,
    OLX_TRANSACTION_TYPES,
)


@dataclass(frozen=True)
class OlxFieldSpec:
    """One documented field of the lead payload."""

    name: str
    type: str
    required: bool
    notes: str
    #: True once a real delivery has been observed carrying this field.
    #: Flipped by Gate 1, never by reading the vendor's HTML again.
    verified: bool = False


#: Wire-name → spec. Order is the vendor's documentation order.
OLX_LEAD_FIELDS: tuple[OlxFieldSpec, ...] = (
    OlxFieldSpec("leadOrigin", "string", True,
                 f"{OLX_LEAD_ORIGIN_STANDARD!r} or {OLX_LEAD_ORIGIN_MCMV!r}. Does NOT "
                 "name the portal (ZAP vs VivaReal vs ImovelWeb) — confirming "
                 "whether it ever can is Gate 1 item 5."),
    OlxFieldSpec("timestamp", "string", True, "ISO-8601 creation time."),
    OlxFieldSpec("originLeadId", "string", True,
                 "Vendor lead id. THE dedup key — retries and the 14-day "
                 "store-and-forward make duplicate delivery normal."),
    OlxFieldSpec("originListingId", "string", False,
                 "Vendor listing id. Absent on MCMV leads."),
    OlxFieldSpec("clientListingId", "string", False,
                 "OUR listing id, as published in the feed. Required for "
                 "listing leads, absent on MCMV. The vendor asks for a 4xx "
                 "when it is missing on a listing lead so the lead is requeued."),
    OlxFieldSpec("name", "string", True, "Consumer name."),
    OlxFieldSpec("email", "string", True, "Consumer email."),
    OlxFieldSpec("ddd", "string", True, "Area code, e.g. '11'."),
    OlxFieldSpec("phone", "string", True, "Phone without the area code."),
    OlxFieldSpec("phoneNumber", "string", False,
                 "Full phone. Marked deprecated by the vendor but still sent."),
    OlxFieldSpec("message", "string", True, "Consumer message."),
    OlxFieldSpec("temperature", "string", True, f"One of {OLX_TEMPERATURES}."),
    OlxFieldSpec("transactionType", "string", True, f"One of {OLX_TRANSACTION_TYPES}."),
    OlxFieldSpec("extraData", "object", True,
                 "Container: leadCerto, izi, feedback, leadType, mcmv."),
)

#: Enum-ish fields we know the documented value set for. A value outside
#: the set is reported as a WARNING, never an error — see
#: `validate_olx_lead_payload`.
OLX_ENUMS: dict[str, tuple[str, ...]] = {
    "temperature": OLX_TEMPERATURES,
    "transactionType": OLX_TRANSACTION_TYPES,
    "leadOrigin": (OLX_LEAD_ORIGIN_STANDARD, OLX_LEAD_ORIGIN_MCMV),
}

#: `extraData.leadType` gets the same treatment one level down.
OLX_EXTRA_DATA_ENUMS: dict[str, tuple[str, ...]] = {"leadType": OLX_LEAD_TYPES}

#: How the vendor reads our reply. Body is IGNORED — only the status code
#: is read — so a 200 with an error body means "delivered, done".
OLX_RESPONSE_SEMANTICS: dict[str, str] = {
    "2xx": "Delivered. The lead will not be sent again.",
    "3xx": "Treated as failure — retried.",
    "4xx": "Treated as failure — retried. Use for a missing clientListingId "
           "on a listing lead, which is the vendor's documented requeue path.",
    "5xx": "Treated as failure — retried.",
}

OLX_RETRY_POLICY: dict[str, Any] = {
    "max_attempts": 3,
    "store_days": 14,
    "duplicates_expected": True,
    "note": "After 14 days an undelivered lead is discarded permanently. "
            "There is no replay API — a lead lost to a receiver bug is gone.",
}

#: The vendor's own documentation sample, verbatim. Used as the default
#: body by `olx.webhook.simulate` and as a fixture across the tests.
OLX_SAMPLE_LEAD: dict[str, Any] = {
    "leadOrigin": OLX_LEAD_ORIGIN_STANDARD,
    "timestamp": "2017-10-23T15:50:30.619Z",
    "originLeadId": "59ee0fc6e4b043e1b2a6d863",
    "originListingId": "87027856",
    "clientListingId": "a40171",
    "name": "Nome Consumidor",
    "email": "nome.consumidor@email.com",
    "ddd": "11",
    "phone": "999999999",
    "phoneNumber": "11999999999",
    "message": "Olá, tenho interesse neste imóvel...",
    "temperature": "Alta",
    "transactionType": "SELL",
    "extraData": {
        "leadCerto": True,
        "izi": "Visualize o histórico...",
        "feedback": "Sua opinião é muito importante...",
        "leadType": "CONTACT_CHAT",
        "mcmv": {},
    },
}


def olx_lead_json_schema() -> dict[str, Any]:
    """JSON Schema derived from `OLX_LEAD_FIELDS` — derived, not restated,
    so the schema cannot drift from the field table above it."""
    type_map = {"string": "string", "object": "object", "boolean": "boolean"}
    properties: dict[str, Any] = {}
    for spec in OLX_LEAD_FIELDS:
        prop: dict[str, Any] = {
            "type": [type_map[spec.type], "null"],
            "description": spec.notes,
        }
        if spec.name in OLX_ENUMS:
            prop["examples"] = list(OLX_ENUMS[spec.name])
        properties[spec.name] = prop
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Grupo OLX lead webhook payload",
        "type": "object",
        "properties": properties,
        "required": [s.name for s in OLX_LEAD_FIELDS if s.required],
        "additionalProperties": True,
    }


@dataclass(frozen=True)
class ContractViolation:
    """One way a payload departs from the documented contract.

    `severity` matters more than it looks. `error` means we cannot build a
    lead from this body. `warning` means the body is usable but the
    document is stale — an unknown enum value, an undocumented field. A
    warning must NEVER become a 4xx: the vendor would requeue a perfectly
    good lead for three attempts and then drop it, and we would have
    thrown away a real customer over a doc we wrote ourselves.
    """

    field: str
    severity: str  # "error" | "warning"
    message: str


def validate_olx_lead_payload(payload: Any) -> list[ContractViolation]:
    """Check a delivery body against the documented contract.

    Returns violations, most severe concerns first; an empty list means
    the body matches the contract exactly. Never raises — a malformed
    body is data, not a crash.
    """
    if not isinstance(payload, dict):
        return [ContractViolation("<root>", "error",
                                  f"expected a JSON object, got {type(payload).__name__}")]

    violations: list[ContractViolation] = []
    lead_origin = payload.get("leadOrigin")
    is_mcmv = lead_origin == OLX_LEAD_ORIGIN_MCMV

    for spec in OLX_LEAD_FIELDS:
        present = spec.name in payload and payload[spec.name] not in (None, "")
        if spec.required and not present:
            violations.append(ContractViolation(
                spec.name, "error", f"required field {spec.name!r} is missing or empty"))
            continue
        if not present:
            continue
        value = payload[spec.name]
        if spec.type == "object" and not isinstance(value, dict):
            violations.append(ContractViolation(
                spec.name, "error",
                f"{spec.name!r} should be an object, got {type(value).__name__}"))
        elif spec.type == "string" and not isinstance(value, str):
            violations.append(ContractViolation(
                spec.name, "error",
                f"{spec.name!r} should be a string, got {type(value).__name__}"))

    # `clientListingId` is conditionally required — the one rule that
    # actually changes our HTTP status, so it is checked explicitly.
    if not is_mcmv and not payload.get("clientListingId"):
        violations.append(ContractViolation(
            "clientListingId", "error",
            "listing leads must carry clientListingId (the vendor documents a "
            "4xx here so the lead is requeued); absent only on MCMV leads"))

    for name, allowed in OLX_ENUMS.items():
        value = payload.get(name)
        if isinstance(value, str) and value and value not in allowed:
            violations.append(ContractViolation(
                name, "warning",
                f"{value!r} is outside the documented set {allowed} — usable, but "
                "the contract is stale; record it and update this table"))

    extra = payload.get("extraData")
    if isinstance(extra, dict):
        for name, allowed in OLX_EXTRA_DATA_ENUMS.items():
            value = extra.get(name)
            if isinstance(value, str) and value and value not in allowed:
                violations.append(ContractViolation(
                    f"extraData.{name}", "warning",
                    f"{value!r} is outside the documented set {allowed}"))

    known = {s.name for s in OLX_LEAD_FIELDS}
    for name in payload:
        if name not in known:
            violations.append(ContractViolation(
                name, "warning",
                "field is not in the documented contract — the vendor added it, "
                "or our transcription missed it"))

    violations.sort(key=lambda v: 0 if v.severity == "error" else 1)
    return violations


def has_blocking_violation(violations: list[ContractViolation]) -> bool:
    """True when at least one violation is an `error`."""
    return any(v.severity == "error" for v in violations)


def missing_client_listing_id(violations: list[ContractViolation]) -> bool:
    """True when the ONLY documented reason to answer 4xx applies."""
    return any(v.field == "clientListingId" and v.severity == "error"
               for v in violations)


def contract_summary() -> dict[str, Any]:
    """Everything an agent needs to understand the contract in one call."""
    return {
        "source": "https://developers.grupozap.com/webhooks/integration_leads.html",
        "transcribed_at": "2026-08-17",
        "verified_against_live_traffic": any(s.verified for s in OLX_LEAD_FIELDS),
        "auth": {
            "scheme": "http_basic",
            "header": "Authorization",
            "decoded_form": "vivareal:<SECRET_KEY>",
            "scope": "one key per CRM, not per advertiser",
            "body_binding": False,
            "caveat": "No signature and no timestamp: the header is identical on "
                      "every request, so it is replayable. TLS + idempotency on "
                      "originLeadId are mandatory at the receiver.",
        },
        "delivery": {"method": "POST", "content_type": "application/json",
                     "batching": "one lead per request"},
        "fields": [
            {"name": s.name, "type": s.type, "required": s.required,
             "notes": s.notes, "verified": s.verified}
            for s in OLX_LEAD_FIELDS
        ],
        "enums": {**{k: list(v) for k, v in OLX_ENUMS.items()},
                  "extraData.leadType": list(OLX_LEAD_TYPES)},
        "response_semantics": OLX_RESPONSE_SEMANTICS,
        "retry_policy": OLX_RETRY_POLICY,
        "json_schema": olx_lead_json_schema(),
        "sample": OLX_SAMPLE_LEAD,
    }


def diff_observed(bodies: list[dict[str, Any]]) -> dict[str, Any]:
    """Diff a corpus of REAL delivery bodies against this contract.

    The doc-vs-reality loop: `mcp/olx` records live bodies, this reports
    where the vendor's documentation (and therefore our transcription of
    it) is wrong. Its output is what gets written into the KB change log
    — and what flips the `verified` flags above.

    Returns undocumented fields, documented-but-never-seen fields,
    required-but-null fields, unseen enum values, and per-body violations.
    """
    documented = {s.name for s in OLX_LEAD_FIELDS}
    seen: set[str] = set()
    seen_non_null: set[str] = set()
    undocumented: dict[str, int] = {}
    novel_enum_values: dict[str, set[str]] = {}
    per_body: list[dict[str, Any]] = []

    for index, body in enumerate(bodies):
        if not isinstance(body, dict):
            per_body.append({"index": index, "error": "not a JSON object"})
            continue
        seen.update(body.keys())
        seen_non_null.update(k for k, v in body.items() if v not in (None, ""))
        for name in body:
            if name not in documented:
                undocumented[name] = undocumented.get(name, 0) + 1
        for name, allowed in OLX_ENUMS.items():
            value = body.get(name)
            if isinstance(value, str) and value and value not in allowed:
                novel_enum_values.setdefault(name, set()).add(value)
        extra = body.get("extraData")
        if isinstance(extra, dict):
            for name, allowed in OLX_EXTRA_DATA_ENUMS.items():
                value = extra.get(name)
                if isinstance(value, str) and value and value not in allowed:
                    novel_enum_values.setdefault(f"extraData.{name}", set()).add(value)
        violations = validate_olx_lead_payload(body)
        if violations:
            per_body.append({
                "index": index,
                "origin_lead_id": body.get("originLeadId"),
                "violations": [
                    {"field": v.field, "severity": v.severity, "message": v.message}
                    for v in violations
                ],
            })

    required_but_null = sorted(
        s.name for s in OLX_LEAD_FIELDS
        if s.required and s.name in seen and s.name not in seen_non_null
    )
    return {
        "bodies_examined": len(bodies),
        "undocumented_fields": dict(sorted(undocumented.items())),
        "documented_never_seen": sorted(documented - seen),
        "required_but_arrived_null": required_but_null,
        "novel_enum_values": {k: sorted(v) for k, v in sorted(novel_enum_values.items())},
        "bodies_with_violations": per_body,
        "clean": (
            not undocumented and not novel_enum_values
            and not required_but_null and not per_body
        ),
    }


__all__ = [
    "ContractViolation",
    "OLX_ENUMS",
    "OLX_EXTRA_DATA_ENUMS",
    "OLX_LEAD_FIELDS",
    "OLX_RESPONSE_SEMANTICS",
    "OLX_RETRY_POLICY",
    "OLX_SAMPLE_LEAD",
    "OlxFieldSpec",
    "contract_summary",
    "diff_observed",
    "has_blocking_violation",
    "missing_client_listing_id",
    "olx_lead_json_schema",
    "validate_olx_lead_payload",
]
