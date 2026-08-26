"""The ImovelWeb callback contract — the SINGLE source of truth.

Both consumers import from here and neither restates it:

* `mcp/imovelweb` serves it to an agent (`imovelweb.contract.describe`)
  and diffs captured live bodies against it
  (`imovelweb.contract.diff_observed`).
* the product receiver validates real deliveries with
  `validate_imovelweb_payload` before persisting.

Two copies would disagree within a release, and the disagreement would
surface as leads silently rejected in production.

**Why this module is language-parameterized, unlike every sibling.**
`lenguajeCallbackBody` is a registration setting, and it changes the
FIELD NAMES of every body the vendor pushes — five incompatible shapes
for the same event. Worse, Gate 0 established that the vendor's OpenAPI
spec models **zero** callback bodies: it documents only the API we call,
so the shapes below are transcribed from prose and cannot be confirmed
from any machine-readable source. Pinning one language would mean
rewriting this module the moment we learn which one is right. Keying it
by language costs one dict and survives the answer.

**Everything here is transcribed from open-classifieds.notion.site/bra
as of 2026-08-17 and is UNVERIFIED against live traffic.** Each row
carries its own `verified` flag; Gate 1 in the project doc is the pass
that flips them, from an observed body and never from re-reading the
vendor's HTML. Do not treat a `verified=False` row as fact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .types import (
    IMOVELWEB_CALLBACK_LANGUAGES,
    IMOVELWEB_CONTACT_TYPES,
    IMOVELWEB_EVENT_TYPES,
    IMOVELWEB_LEAD_ORIGINS,
)

#: What the vendor does with our response. Diverges from Grupo OLX in
#: three ways that each changed a design decision, so it is data rather
#: than prose in a docstring.
IMOVELWEB_RESPONSE_SEMANTICS: dict[str, Any] = {
    # 3xx counts too — the vendor is explicit. Never rely on it; do
    # record it, so nobody "fixes" a redirect into a failure.
    "success_status_ranges": ("2xx", "3xx"),
    "failure_status_ranges": ("4xx", "5xx"),
    "response_timeout_seconds": 1.5,
    "notes": (
        "A slower answer than 1.5s is scored a timeout, i.e. an error. That "
        "rules out tenant resolution, listing lookups and authoritative "
        "re-fetch inside the request — persist once, answer, then process."
    ),
}

#: Delivery retry policy. The 72h window is what makes reconciliation
#: (rather than the webhook) the durability guarantee for this vendor.
IMOVELWEB_RETRY_POLICY: dict[str, Any] = {
    "response_timeout_seconds": 1.5,
    "retry_until_hours": 72,
    "expired_status": "VENCIDO",
    "max_attempts": None,  # not a count — a deadline
    "duplicates_expected": True,
    "vendor_advice": "validate delivery by checking the event id",
}


@dataclass(frozen=True)
class FieldSpec:
    """One documented field of a callback body, for one language."""

    #: The name on the wire, in this language.
    name: str
    #: The name we normalize it to, shared across languages.
    canonical: str
    type: str
    required: bool
    notes: str = ""
    #: True once a real delivery has been observed carrying this field.
    #: Flipped by Gate 1, never by reading the vendor's docs again.
    verified: bool = False


def _spec(name: str, canonical: str, type_: str, required: bool, notes: str = "") -> FieldSpec:
    return FieldSpec(name=name, canonical=canonical, type=type_, required=required, notes=notes)


# --------------------------------------------------------------------------
# Per-language field tables.
#
# The canonical names are ours and are stable across languages; the wire
# names are the vendor's and are not. `LANGUAGE_FIELD_ALIASES` is derived
# from these rather than hand-maintained beside them, because two
# hand-synced tables drift.
# --------------------------------------------------------------------------

_EN2_FIELDS: tuple[FieldSpec, ...] = (
    _spec("eventId", "event_id", "string", True,
          "Per-DELIVERY id. THE dedup key, and the vendor's own advice. Not "
          "the same thing as originLeadId, which is the contact."),
    _spec("eventType", "event_type", "string", True,
          "CONTACTO (phone reveal) or CONTACTO_MENSAJE (message)."),
    _spec("contactTypeId", "contact_type_id", "integer", False,
          f"Known ids: {sorted(IMOVELWEB_CONTACT_TYPES)}. An unknown id is "
          "carried through — a new contact type is a product update, not a "
          "delivery failure."),
    _spec("timestamp", "timestamp", "string", True,
          "yyyy-MM-dd'T'HH:mm:ss.SSSZ where Java's Z is an RFC-822 NUMERIC "
          "offset (-0300), not the literal character."),
    _spec("name", "name", "string", False, "Omitted when null."),
    _spec("email", "email", "string", False, ""),
    _spec("ddd", "ddd", "string", False,
          "Area code. Empty when the phone is invalid or already carries it."),
    _spec("phone", "phone", "string", False,
          "International format with a leading +."),
    _spec("phoneNumber", "phone_number", "string", False,
          "ddd + phone concatenated. Any of the three may be empty."),
    _spec("messageId", "message_id", "long", False,
          "Navent message id — the re-fetch handle for GET /v1/mensagens/{id}."),
    _spec("message", "message", "string", False, "CONTACTO_MENSAJE only."),
    _spec("reference", "client_listing_id", "string", False,
          "In EN2 the vendor documents this as clientListingId. OUR listing "
          "code. Omitted when the listing was never associated — which is NOT "
          "a reason to refuse the lead (see IMOVELWEB_RESPONSE_SEMANTICS)."),
    _spec("clientListingId", "client_listing_id", "string", False,
          "EN2-only alias of `reference`. The docs use both names for the "
          "same value and contradict themselves about when it is null; Gate 1 "
          "settles which arrives."),
    _spec("originListingId", "origin_listing_id", "long", False,
          "Their listing id (idNavplat of the aviso)."),
    _spec("internalReference", "internal_reference", "string", False,
          "The code the imobiliária uses in the vendor's own panel — which "
          "may or may not be ours."),
    _spec("leadOrigin", "lead_origin", "string", False,
          f"Names the PORTAL: {', '.join(IMOVELWEB_LEAD_ORIGINS)}. EN2 is the "
          "only variant documented to carry it, which is why honest "
          "per-portal attribution is possible here and not on the OLX pipe."),
    _spec("originLeadId", "origin_lead_id", "integer", False,
          "Navent CONTACT id. One contact fans out to several events — do "
          "not use as a dedup key. Omitted when null."),
    _spec("idNavplatDevelopment", "id_navplat_development", "long", False,
          "Parent development; omitted when not a development or unit."),
    _spec("developmentCode", "development_code", "string", False, ""),
    _spec("userIdNavplat", "user_id_navplat", "string", False,
          "Masked seeker id, vendor-internal."),
    _spec("identificationId", "identification_id", "string", False,
          "CPF. Parsed for contract honesty, then DROPPED by the normalizer: "
          "never projected, never stored typed, never logged."),
)

_PT_FIELDS: tuple[FieldSpec, ...] = (
    _spec("idEvento", "event_id", "string", True, "Per-delivery id. The dedup key."),
    _spec("tipoEvento", "event_type", "string", True, ""),
    _spec("idTipoContacto", "contact_type_id", "integer", False, ""),
    _spec("codigoImobiliaria", "codigo_imobiliaria", "string", False,
          "The agency code IN OUR SYSTEM — we choose it at onboarding, so it "
          "is the reliable tenant key. PT/ES/EN carry it; the documented EN2 "
          "sample does not. That trade-off is Gate 1's language decision."),
    _spec("idMensagem", "message_id", "integer", False, ""),
    _spec("idContato", "origin_lead_id", "integer", False, "Navent contact id."),
    _spec("idnavplat", "origin_listing_id", "long", False, ""),
    _spec("idAnuncioPai", "id_navplat_development", "long", False, ""),
    _spec("codigoLancamento", "development_code", "string", False, ""),
    _spec("referencia", "client_listing_id", "string", False, "codigoAviso — our listing code."),
    _spec("dataRegistro", "timestamp", "string", False, ""),
    _spec("nome", "name", "string", False, ""),
    _spec("email", "email", "string", False, ""),
    _spec("telefone", "phone", "string", False, ""),
    _spec("mensagem", "message", "string", False, ""),
    _spec("planoDePublicacao", "publication_plan", "string", False, ""),
    _spec("codigoDoAnunciante", "internal_reference", "string", False, ""),
    _spec("userIdNavplat", "user_id_navplat", "string", False, ""),
    _spec("cpf", "identification_id", "string", False, "CPF — dropped by the normalizer."),
)

_ES_FIELDS: tuple[FieldSpec, ...] = (
    _spec("idEvento", "event_id", "string", True, ""),
    _spec("tipoEvento", "event_type", "string", True, ""),
    _spec("idTipoContacto", "contact_type_id", "integer", False, ""),
    _spec("codigoCliente", "codigo_imobiliaria", "string", False, "Agency code in our system."),
    _spec("idMensaje", "message_id", "integer", False, ""),
    _spec("idContacto", "origin_lead_id", "integer", False, ""),
    _spec("idNavplat", "origin_listing_id", "long", False, ""),
    _spec("idAvisoPadre", "id_navplat_development", "long", False, ""),
    _spec("codigoDesarrollo", "development_code", "string", False, ""),
    _spec("referencia", "client_listing_id", "string", False, ""),
    _spec("fechaRegistro", "timestamp", "string", False, ""),
    _spec("nombre", "name", "string", False, ""),
    _spec("email", "email", "string", False, ""),
    _spec("telefono", "phone", "string", False, ""),
    _spec("mensaje", "message", "string", False, ""),
    _spec("planDePublicacion", "publication_plan", "string", False, ""),
    _spec("claveInterna", "internal_reference", "string", False, ""),
    _spec("userIdNavplat", "user_id_navplat", "string", False, ""),
    _spec("dni", "identification_id", "string", False, "National id — dropped by the normalizer."),
)

_EN_FIELDS: tuple[FieldSpec, ...] = (
    _spec("eventId", "event_id", "string", True, ""),
    _spec("eventType", "event_type", "string", True, ""),
    _spec("contactTypeId", "contact_type_id", "integer", False, ""),
    _spec("clientCode", "codigo_imobiliaria", "string", False, "Agency code in our system."),
    _spec("contactId", "origin_lead_id", "integer", False, ""),
    _spec("idNavplat", "origin_listing_id", "long", False, ""),
    _spec("idNavplatDevelopment", "id_navplat_development", "long", False, ""),
    _spec("developmentCode", "development_code", "string", False, ""),
    _spec("reference", "client_listing_id", "string", False, ""),
    _spec("registerDate", "timestamp", "string", False, ""),
    _spec("name", "name", "string", False, ""),
    _spec("email", "email", "string", False, ""),
    _spec("phone", "phone", "string", False, ""),
    _spec("message", "message", "string", False, ""),
    _spec("publicationPlan", "publication_plan", "string", False, ""),
    _spec("internalReference", "internal_reference", "string", False, ""),
    _spec("userIdNavplat", "user_id_navplat", "string", False, ""),
    _spec("identificationId", "identification_id", "string", False, "CPF — dropped."),
)

#: Salesforce-flavoured flat body. Carries neither an agency code nor a
#: portal name, and its `token` field is the callback URL echoed back —
#: it is documented, and it is the wrong choice for a multi-tenant
#: receiver. Modelled so `detect_callback_language` can recognise one if
#: the registration is ever changed under us.
_EN_SF_FIELDS: tuple[FieldSpec, ...] = (
    _spec("id", "event_id", "long", True,
          "EN_SF has no separate event id — `id` is the CONTACT id doing "
          "double duty, which makes this variant unsafe for dedup."),
    _spec("token", "callback_token", "string", False, "The URL we gave them, echoed."),
    _spec("txtNome", "name", "string", False, ""),
    _spec("txtEmail", "email", "string", False, ""),
    _spec("txtDdd", "ddd", "string", False, ""),
    _spec("txtTelefone", "phone", "integer", False, ""),
    _spec("messageId", "message_id", "long", False, ""),
    _spec("txtMensagem", "message", "string", False, ""),
)

#: language → field table.
IMOVELWEB_FIELD_SPECS: dict[str, tuple[FieldSpec, ...]] = {
    "EN2": _EN2_FIELDS,
    "PT": _PT_FIELDS,
    "ES": _ES_FIELDS,
    "EN": _EN_FIELDS,
    "EN_SF": _EN_SF_FIELDS,
}

#: language → {wire name: canonical name}. Derived, never hand-kept.
LANGUAGE_FIELD_ALIASES: dict[str, dict[str, str]] = {
    lang: {spec.name: spec.canonical for spec in specs}
    for lang, specs in IMOVELWEB_FIELD_SPECS.items()
}

#: Sample bodies, transcribed from the vendor docs. Used by the Fake, by
#: `imovelweb.contract.describe`, and as the fixture baseline in tests.
IMOVELWEB_SAMPLE_BODIES: dict[str, dict[str, Any]] = {
    "EN2": {
        "eventId": "evt-0000000001",
        "eventType": "CONTACTO_MENSAJE",
        "contactTypeId": 1,
        "timestamp": "2026-08-17T15:50:30.619-0300",
        "name": "Fulano de Tal",
        "email": "fulano@example.com",
        "ddd": "31",
        "phone": "+5531999998888",
        "phoneNumber": "31999998888",
        "messageId": 987654321,
        "message": "Tenho interesse neste imóvel.",
        "reference": "AP-1024",
        "clientListingId": "AP-1024",
        "originListingId": 45491025,
        "internalReference": "IMOB-AP-1024",
        "leadOrigin": "Imovelweb",
        "originLeadId": 55512345,
        "userIdNavplat": "masked-user-id",
    },
    "PT": {
        "idEvento": "evt-0000000002",
        "tipoEvento": "CONTACTO",
        "idTipoContacto": 6,
        "codigoImobiliaria": "noc-org-demo",
        "idContato": 55512346,
        "referencia": "AP-1024",
        "dataRegistro": "2026-08-17T15:52:10.001-0300",
        "nome": "Beltrana",
        "email": "beltrana@example.com",
        "telefone": "+5531988887777",
        "planoDePublicacao": "SIMPLE",
        "codigoDoAnunciante": "IMOB-AP-1024",
        "userIdNavplat": "masked-user-id-2",
    },
}


def contract_summary(language: Optional[str] = None) -> dict[str, Any]:
    """What an agent should see before trusting anything here."""
    langs = (language,) if language else tuple(IMOVELWEB_FIELD_SPECS)
    return {
        "vendor": "ImovelWeb / OpenNavent (Navent · Grupo QuintoAndar)",
        "languages": list(IMOVELWEB_CALLBACK_LANGUAGES),
        "event_types": list(IMOVELWEB_EVENT_TYPES),
        "response_semantics": IMOVELWEB_RESPONSE_SEMANTICS,
        "retry_policy": IMOVELWEB_RETRY_POLICY,
        "verified_against_live_traffic": False,
        "fields": {
            lang: [
                {
                    "name": s.name,
                    "canonical": s.canonical,
                    "type": s.type,
                    "required": s.required,
                    "verified": s.verified,
                    "notes": s.notes,
                }
                for s in IMOVELWEB_FIELD_SPECS.get(lang, ())
            ]
            for lang in langs
            if lang in IMOVELWEB_FIELD_SPECS
        },
        "caveat": (
            "Transcribed from vendor prose. The vendor's OpenAPI spec models "
            "ZERO callback bodies, so none of this is confirmable from a "
            "machine-readable source — only from an observed delivery."
        ),
    }


def imovelweb_json_schema(language: str = "EN2") -> dict[str, Any]:
    """JSON Schema for one language's body."""
    specs = IMOVELWEB_FIELD_SPECS.get(language)
    if specs is None:
        raise ValueError(
            f"unknown language {language!r}; known: "
            f"{', '.join(IMOVELWEB_CALLBACK_LANGUAGES)}"
        )
    type_map = {"string": "string", "integer": "integer", "long": "integer"}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"ImovelWeb callback body ({language})",
        "type": "object",
        "properties": {
            s.name: {"type": [type_map.get(s.type, "string"), "null"], "description": s.notes}
            for s in specs
        },
        "required": [s.name for s in specs if s.required],
        # The vendor adds fields without notice, and refusing one would
        # 4xx a real lead into a 72-hour retry loop.
        "additionalProperties": True,
    }


def validate_imovelweb_payload(
    payload: Any, *, language: str = "EN2"
) -> dict[str, list[str]]:
    """Split complaints into blocking `error`s and non-blocking `warning`s.

    The split is the whole point. For this vendor the only genuinely
    blocking condition is a body we cannot dedup — everything else,
    including an unknown enum or a missing listing code, is a warning
    that still gets a 2xx. Refusing any of those requeues a real lead
    for 72 hours against a body that will never change.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(payload, dict):
        return {"error": [f"payload is {type(payload).__name__}, expected object"],
                "warning": []}

    specs = IMOVELWEB_FIELD_SPECS.get(language)
    if specs is None:
        return {"error": [f"unknown language {language!r}"], "warning": []}

    aliases = LANGUAGE_FIELD_ALIASES[language]
    canonical = {aliases[k]: v for k, v in payload.items() if k in aliases}

    if not canonical.get("event_id"):
        errors.append(
            "no event id — the body cannot be deduplicated, so it cannot be "
            "stored safely. This is the ONLY blocking condition."
        )

    event_type = canonical.get("event_type")
    if not event_type:
        warnings.append("no event type")
    elif event_type not in IMOVELWEB_EVENT_TYPES:
        warnings.append(f"unknown eventType {event_type!r} — carried through")

    contact_type_id = canonical.get("contact_type_id")
    if contact_type_id is not None and contact_type_id not in IMOVELWEB_CONTACT_TYPES:
        warnings.append(
            f"unknown contactTypeId {contact_type_id!r} — carried through; "
            "refresh the catalog from GET /v1/contatos/acoes"
        )

    lead_origin = canonical.get("lead_origin")
    if lead_origin and lead_origin not in IMOVELWEB_LEAD_ORIGINS:
        warnings.append(
            f"unknown leadOrigin {lead_origin!r} — attribution falls back to "
            "imovel-web and the raw value is preserved"
        )

    if not canonical.get("client_listing_id"):
        warnings.append(
            "no client listing code — expected when the listing was never "
            "associated. NOT a refusal: unlike Grupo OLX, this vendor "
            "documents no requeue path for it."
        )

    if not canonical.get("codigo_imobiliaria"):
        warnings.append(
            "no agency code in this body — tenant resolution must fall back "
            "to the listing code. Expected for EN2; a PT/ES/EN body missing "
            "it is a real anomaly."
        )

    unknown_fields = [k for k in payload if k not in aliases]
    if unknown_fields:
        warnings.append(
            f"undocumented field(s): {', '.join(sorted(unknown_fields))} — "
            "carried through in raw; record via imovelweb.webhook.record_delivery"
        )

    return {"error": errors, "warning": warnings}


def has_blocking_violation(result: dict[str, list[str]]) -> bool:
    return bool(result.get("error"))


def diff_observed(
    bodies: list[dict[str, Any]], *, language: str = "EN2"
) -> dict[str, Any]:
    """Compare captured live bodies against the transcribed contract.

    This closes the doc-vs-reality loop: it is the input to flipping the
    `verified` flags, and the only honest way to do so.
    """
    specs = IMOVELWEB_FIELD_SPECS.get(language)
    if specs is None:
        raise ValueError(f"unknown language {language!r}")

    documented = {s.name for s in specs}
    seen: set[str] = set()
    for body in bodies:
        if isinstance(body, dict):
            seen.update(body.keys())

    return {
        "language": language,
        "bodies_examined": len(bodies),
        "undocumented_fields": sorted(seen - documented),
        "never_observed_fields": sorted(documented - seen),
        "confirmed_fields": sorted(documented & seen),
        "verified_against_live_traffic": False,
        "next_step": (
            "Resolve every undocumented field in contract.py FIRST, then date "
            "the observation in KB § INTEGRATIONS/imovelweb.md §8, then flip "
            "the verified flags. Never flip them from a document."
        ),
    }


__all__ = [
    "IMOVELWEB_FIELD_SPECS",
    "IMOVELWEB_RESPONSE_SEMANTICS",
    "IMOVELWEB_RETRY_POLICY",
    "IMOVELWEB_SAMPLE_BODIES",
    "LANGUAGE_FIELD_ALIASES",
    "FieldSpec",
    "contract_summary",
    "diff_observed",
    "has_blocking_violation",
    "imovelweb_json_schema",
    "validate_imovelweb_payload",
]
