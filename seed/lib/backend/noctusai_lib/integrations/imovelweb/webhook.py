"""Parse one ImovelWeb callback delivery. Pure — zero IO, no FastAPI.

The receiver imports this; so does the MCP connector's validator. Keeping
it free of framework and transport means the same function that runs in
production is the one an agent can call against a captured fixture.

**This parser is deliberately permissive.** It returns `None` in exactly
one case — no event id, which makes the body impossible to deduplicate
and therefore impossible to store safely. Everything else is carried
through: unknown event types, unknown contact-type ids, unknown
`leadOrigin` values, undocumented fields, even an unrecognised language.
The reason is the vendor's retry policy: a 4xx starts a 72-hour retry
loop, and a body we refused for an unexpected enum will arrive identical
every time until it expires. Rejecting the unfamiliar throws real
customers away.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .contract import LANGUAGE_FIELD_ALIASES
from .types import ImovelWebLead

logger = logging.getLogger(__name__)

#: Fields whose canonical form is an integer on the wire but which we
#: keep as strings, because ids are identifiers and not arithmetic.
_ID_AS_STRING = ("event_id", "origin_lead_id", "codigo_imobiliaria",
                 "client_listing_id", "origin_listing_id", "internal_reference",
                 "development_code", "identification_id", "user_id_navplat")

_INT_FIELDS = ("contact_type_id", "message_id", "id_navplat_development")


def detect_callback_language(payload: Any) -> Optional[str]:
    """Guess which `lenguajeCallbackBody` a body was rendered in.

    Scores each language by how many of the body's keys it recognises,
    normalised by how distinctive the match is. Returns `None` when
    nothing matches, which the parser treats as "try the configured
    language anyway" rather than as a failure.

    This exists because the language is a *registration* setting: someone
    can change it at the vendor without telling us, and the first symptom
    would otherwise be every field arriving as `None`.
    """
    if not isinstance(payload, dict) or not payload:
        return None

    keys = set(payload)
    best: Optional[str] = None
    best_score = 0.0

    for language, aliases in LANGUAGE_FIELD_ALIASES.items():
        matched = keys & set(aliases)
        if not matched:
            continue
        # Coverage of the body beats coverage of the spec: a short body
        # fully explained by one language is a better signal than a long
        # spec partially touched.
        score = len(matched) / len(keys)
        # Tie-break toward the language that explains more of itself,
        # so EN2 does not win over PT purely by sharing `email`.
        score += (len(matched) / len(aliases)) * 0.25
        if score > best_score:
            best_score, best = score, language

    return best


def _coerce(canonical: str, value: Any) -> Any:
    """Normalize a wire value without losing or inventing information."""
    if value is None:
        return None
    if canonical in _INT_FIELDS:
        try:
            return int(value)
        except (TypeError, ValueError):
            # Keep the raw value visible rather than dropping it: an
            # unparseable id is evidence, and `raw` still has the truth.
            logger.warning(
                "imovelweb: %s=%r is not an integer — carried through as-is",
                canonical, value,
            )
            return None
    if canonical in _ID_AS_STRING:
        text = str(value).strip()
        return text or None
    if isinstance(value, str):
        return value.strip() or None
    return value


def parse_imovelweb_callback(
    payload: Any, *, language: Optional[str] = None
) -> Optional[ImovelWebLead]:
    """Parse a delivery into an `ImovelWebLead`, or `None` if unstorable.

    `language` pins the field-name mapping when the caller knows the
    registered value; otherwise it is detected. Never raises — the
    receiver must be able to answer within 1.5 seconds whatever arrives.
    """
    if not isinstance(payload, dict):
        logger.warning(
            "imovelweb: payload is %s, expected object — dropping",
            type(payload).__name__,
        )
        return None

    detected = detect_callback_language(payload)
    chosen = language or detected or "EN2"
    aliases = LANGUAGE_FIELD_ALIASES.get(chosen)
    if aliases is None:
        logger.warning(
            "imovelweb: unknown language %r — falling back to EN2", chosen
        )
        chosen, aliases = "EN2", LANGUAGE_FIELD_ALIASES["EN2"]

    if language and detected and detected != language:
        # Loud, because it means the vendor-side registration and our
        # config have diverged, and every subsequent body will too.
        logger.warning(
            "imovelweb: body looks like %r but %r is configured — parsing as "
            "%r. Check GET /v1/configuracao/callbacks.",
            detected, language, chosen,
        )

    fields: dict[str, Any] = {}
    for wire_name, value in payload.items():
        canonical = aliases.get(wire_name)
        if canonical is None:
            continue
        coerced = _coerce(canonical, value)
        # EN2 documents `reference` and `clientListingId` as the same
        # value; first non-empty wins rather than last, so a null alias
        # cannot blank a populated one.
        if fields.get(canonical) is None:
            fields[canonical] = coerced

    event_id = fields.get("event_id")
    if not event_id:
        logger.warning(
            "imovelweb: delivery carries no event id (parsed as %s) — cannot "
            "deduplicate, dropping. Body keys: %s",
            chosen, sorted(payload)[:20],
        )
        return None

    return ImovelWebLead(
        event_id=str(event_id),
        event_type=fields.get("event_type") or "",
        lead_origin=fields.get("lead_origin"),
        codigo_imobiliaria=fields.get("codigo_imobiliaria"),
        contact_type_id=fields.get("contact_type_id"),
        origin_lead_id=fields.get("origin_lead_id"),
        message_id=fields.get("message_id"),
        timestamp=fields.get("timestamp"),
        name=fields.get("name"),
        email=fields.get("email"),
        ddd=fields.get("ddd"),
        phone=fields.get("phone"),
        phone_number=fields.get("phone_number"),
        message=fields.get("message"),
        client_listing_id=fields.get("client_listing_id"),
        origin_listing_id=fields.get("origin_listing_id"),
        internal_reference=fields.get("internal_reference"),
        id_navplat_development=fields.get("id_navplat_development"),
        development_code=fields.get("development_code"),
        user_id_navplat=fields.get("user_id_navplat"),
        identification_id=fields.get("identification_id"),
        callback_language=chosen,
        raw=dict(payload),
    )


__all__ = ["detect_callback_language", "parse_imovelweb_callback"]
