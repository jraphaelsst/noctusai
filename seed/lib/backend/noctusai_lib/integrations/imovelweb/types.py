"""Value objects for the ImovelWeb / OpenNavent callback feed.

One inbound delivery = one event. `ImovelWebLead` is the parsed shape;
`raw` carries the vendor body verbatim so nothing the parser did not
model is lost (the product persists `raw` in its ledger table).

**Two ids, and confusing them is a duplication bug.** `event_id` is the
*delivery* — the vendor's own advice is to dedup on it, and it is the
primary key of both product tables. `origin_lead_id` is the *contact* in
Navent, and one contact legitimately fans out to several events (a phone
reveal, then a message, on the same listing). Keying on the contact would
silently collapse distinct leads; keying on the event would not.

Vendor: Navent / Grupo QuintoAndar. Not Grupo OLX — see
`KB § INTEGRATIONS/imovelweb.md`.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Optional

#: Every event the callback system can deliver.
IMOVELWEB_EVENT_TYPES: tuple[str, ...] = (
    "CONTACTO",
    "CONTACTO_MENSAJE",
    "AVISO_ACTIVIDAD",
    "AVISO_ESTADO_PUBLICACION",
    "AVISO_CALIDAD",
    "CREDITO",
)

#: The two we subscribe to. A **ReadOnly** integration receives only
#: these; the `AVISO_*` and `CREDITO` events require a Read-and-Write
#: integration, which also grants publish/unpublish on the client's
#: listings — a credential-request decision, not an engineering one.
IMOVELWEB_LEAD_EVENT_TYPES: tuple[str, ...] = ("CONTACTO", "CONTACTO_MENSAJE")

#: `lenguajeCallbackBody` — the registered value decides the FIELD NAMES
#: of every body they push, not just its prose. See `contract.py`.
IMOVELWEB_CALLBACK_LANGUAGES: tuple[str, ...] = ("EN", "EN2", "EN_SF", "ES", "PT")

#: `contactTypeId` → label. Transcribed from the vendor docs;
#: `GET /v1/contatos/acoes` is the authoritative catalog and replaces
#: this at Gate 1.11. An unknown id is carried through, never rejected.
IMOVELWEB_CONTACT_TYPES: dict[int, str] = {
    1: "CONSULTA",
    2: "QUE_ME_LLAMEN",
    3: "AGENDAR_VISITA",
    6: "DATOS_ANUNCIANTE",
    10: "DATOS_ANUNCIANTE_WHATSAPP",
    12: "TASACION",
    15: "AGENDAR_VISITA_CRONUT",
}

#: `leadOrigin` values documented for BR. Unlike the Grupo OLX payload,
#: this field DOES name the portal — which is what makes honest
#: per-portal attribution possible. Only carried by the EN2 body.
IMOVELWEB_LEAD_ORIGINS: tuple[str, ...] = ("Imovelweb", "Wimoveis", "CasaMineira")


@dataclass(frozen=True)
class ImovelWebLead:
    """One lead event as delivered by the ImovelWeb callback.

    `event_id` is the dedup key. Retries continue for 72 hours and the
    reconciliation job re-reads the same window, so the same event
    legitimately arrives more than once, by two different paths.

    `client_listing_id` is OUR listing code (the one we associated),
    `origin_listing_id` is theirs, and `internal_reference` is the code
    the imobiliária uses in the vendor's own panel. All three are
    routinely absent, and none of them is a reason to refuse the lead.
    """

    event_id: str
    event_type: str
    #: Present only on the EN2 body. `None` elsewhere — see `contract.py`
    #: for why no single language variant carries everything we want.
    lead_origin: Optional[str] = None
    #: The agency code **in OUR system** — we choose it at onboarding, so
    #: it is the reliable tenant key when the body carries it.
    codigo_imobiliaria: Optional[str] = None
    contact_type_id: Optional[int] = None
    origin_lead_id: Optional[str] = None
    message_id: Optional[int] = None
    timestamp: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    ddd: Optional[str] = None
    phone: Optional[str] = None
    phone_number: Optional[str] = None
    message: Optional[str] = None
    client_listing_id: Optional[str] = None
    origin_listing_id: Optional[str] = None
    internal_reference: Optional[str] = None
    id_navplat_development: Optional[int] = None
    development_code: Optional[str] = None
    user_id_navplat: Optional[str] = None
    #: CPF. Parsed so the contract stays honest about what arrives, and
    #: then deliberately DROPPED by the normalizer — never projected,
    #: never stored in a typed column, never logged. It survives only
    #: inside `raw`, which makes that column personal data.
    #: → `KB § PATTERNS/security/lgpd.md`
    identification_id: Optional[str] = None
    #: Which language variant the parser read this body as. The only
    #: forensic record if someone changes the registered language at the
    #: vendor and bodies quietly start arriving in another shape.
    callback_language: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_message_lead(self) -> bool:
        """`CONTACTO_MENSAJE` carries a consumer message; `CONTACTO` is a
        phone reveal and carries none. Both are real leads."""
        return self.event_type == "CONTACTO_MENSAJE"

    @property
    def contact_type(self) -> Optional[str]:
        """Label for `contact_type_id`, or `None` when the vendor sends
        an id we have not catalogued. Deliberately not a raise: a new
        contact type is a product update, not a delivery failure."""
        if self.contact_type_id is None:
            return None
        return IMOVELWEB_CONTACT_TYPES.get(self.contact_type_id)

    @property
    def full_phone(self) -> Optional[str]:
        """The most complete phone number available, without inventing one.

        ⚠️ **The vendor's own documentation is self-contradictory here**, so
        this is defensive rather than literal. It says `phone` is "in
        international format, with a leading `+`", AND that `phoneNumber`
        is "the concatenation of phone and DDD". Both cannot hold: an
        international `+5531999998888` already contains the area code, so
        prefixing `ddd` yields `31+5531999998888` — a number that dials
        nowhere. Which of the two statements is true on the wire is a Gate 1
        question.

        Order, therefore:

        1. `phoneNumber` when sent — the vendor's own combined field.
        2. `phone` alone, when it already looks international (leading `+`)
           or already starts with the area code. Prefixing would corrupt it.
        3. `ddd` + `phone` only when `phone` looks like a bare local number.

        Digits are never reformatted; E.164 canonicalization is the
        consumer's step. Any of the three fields may be empty — the vendor
        documents that an invalid number, or one already carrying its area
        code, yields an empty `ddd`.
        """
        if self.phone_number and self.phone_number.strip():
            return self.phone_number.strip()

        phone = (self.phone or "").strip()
        ddd = (self.ddd or "").strip()

        if not phone:
            return ddd or None
        if not ddd:
            return phone
        # Already international, or already carrying the area code —
        # concatenating would corrupt a working number.
        if phone.startswith("+") or phone.startswith(ddd):
            return phone
        return f"{ddd}{phone}"


@dataclass(frozen=True)
class CallbackConfig:
    """The callback registration — `ConfiguracionCallback` on the wire.

    We choose the URL, the header name AND the header value: there is no
    signature scheme, so this object *is* the entire inbound security
    boundary.

    ⚠️ `PUT /v1/configuracao/callbacks` takes no agency code, so this
    configuration is **integrator-wide**. One bad write redirects every
    agency's leads at once. Every caller confirms, then reads back and
    diffs.
    """

    url: str
    authorization_header_value: str
    authorization_header_key: str = "Authorization"
    language: str = "EN2"
    subscriptions: tuple[str, ...] = IMOVELWEB_LEAD_EVENT_TYPES

    def validate(self) -> tuple[str, ...]:
        """Return blocking problems; empty tuple means the config is
        sendable. Pure — the caller decides what to do about them."""
        problems: list[str] = []

        if not self.url or not self.url.startswith(("http://", "https://")):
            problems.append(
                "url must start with http:// or https:// — the vendor rejects "
                f"anything else (got {self.url!r})"
            )
        if not self.authorization_header_value:
            problems.append(
                "authorization_header_value is empty — an unauthenticated "
                "receiver would accept anything that reached it"
            )
        elif self.authorization_header_value.lstrip().lower().startswith("basic") \
                and not self.authorization_header_value.startswith("Basic "):
            problems.append(
                "a Basic credential must be sent as the literal 'Basic <token>' "
                "including the word and the space — the vendor forwards this "
                "string verbatim, so a malformed one fails at our own verifier"
            )
        if not self.authorization_header_key:
            problems.append("authorization_header_key is empty")
        if self.language not in IMOVELWEB_CALLBACK_LANGUAGES:
            problems.append(
                f"language {self.language!r} is not one of "
                f"{', '.join(IMOVELWEB_CALLBACK_LANGUAGES)}"
            )
        if not self.subscriptions:
            # Legal to the vendor, useless to us, and invisible: a
            # perfectly-configured URL with no subscriptions delivers
            # nothing and reports no error anywhere.
            problems.append(
                "subscriptions is empty — the vendor accepts this and then "
                "delivers nothing, silently. Subscribe to at least one event."
            )
        else:
            unknown = [e for e in self.subscriptions if e not in IMOVELWEB_EVENT_TYPES]
            if unknown:
                problems.append(
                    f"unknown event(s) {', '.join(unknown)} — known: "
                    f"{', '.join(IMOVELWEB_EVENT_TYPES)}"
                )
        return tuple(problems)

    def to_wire(self) -> dict[str, Any]:
        """The vendor's `ConfiguracionCallback` shape."""
        return {
            "url": self.url,
            "authorizationHeaderKey": self.authorization_header_key,
            "authorizationHeaderValue": self.authorization_header_value,
            "lenguajeCallbackBody": self.language,
            "subscriptions": list(self.subscriptions),
        }

    @classmethod
    def from_wire(cls, payload: dict[str, Any]) -> "CallbackConfig":
        """Parse what `GET /v1/configuracao/callbacks` returns.

        Tolerant by design: this is the read-back half of the
        register-then-diff loop, and a config we cannot parse is exactly
        the drift the diff exists to surface.
        """
        subs = payload.get("subscriptions") or ()
        return cls(
            url=payload.get("url") or "",
            authorization_header_value=payload.get("authorizationHeaderValue") or "",
            authorization_header_key=payload.get("authorizationHeaderKey") or "Authorization",
            language=payload.get("lenguajeCallbackBody") or "EN2",
            subscriptions=tuple(subs),
        )

# ---------------------------------------------------------------------------
# The inbound credential.
#
# There is no signature scheme: the vendor forwards, verbatim, whatever
# header value we registered. So this pair of helpers IS the inbound
# security boundary, and it lives in the seed rather than in the connector
# or the receiver because all three have to agree on it byte-for-byte. A
# local copy in any one of them is a fork that fails as a 401 nobody can
# explain.
# ---------------------------------------------------------------------------

#: The username half of the Basic credential we register with the vendor.
#: Deliberately NOT Grupo OLX's `vivareal` default — a different vendor on a
#: different pipe, and reusing that value would make the two receivers
#: interchangeable, which they are not.
IMOVELWEB_BASIC_USERNAME = "noctusai-imovelweb"


def basic_credential(secret: str, *, username: str = IMOVELWEB_BASIC_USERNAME) -> str:
    """Build the `authorizationHeaderValue` we register with the vendor.

    Includes the literal `"Basic "` prefix, because the vendor forwards the
    string as-is and our own verifier requires it — a malformed credential
    fails at OUR end and reads like a vendor problem.
    """
    token = base64.b64encode(f"{username}:{secret}".encode()).decode("ascii")
    return f"Basic {token}"


# ---------------------------------------------------------------------------
# Receiver-URL sanity.
#
# The registered URL is environment-specific and the registration is
# integrator-wide, so a config pointing at a dev tunnel blackholes
# PRODUCTION leads with no error surfacing anywhere: the vendor believes it
# delivered, we never saw it, and the only symptom is leads that stop
# arriving. Pure, so the connector's write tool and the product's register
# service share one answer instead of two drifting ones.
# ---------------------------------------------------------------------------

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"})

#: Hosts that exist only for as long as somebody's laptop is open.
_EPHEMERAL_TUNNEL_SUFFIXES = (
    ".ngrok.io", ".ngrok-free.app", ".ngrok.app",
    ".trycloudflare.com", ".loca.lt", ".serveo.net",
    ".tunnelmole.net", ".devtunnels.ms", ".lhr.life", ".localhost.run",
)


def receiver_url_problems(url: Optional[str]) -> tuple[str, ...]:
    """Reasons this URL must not be registered with the live vendor.

    Empty tuple means it looks like a real public endpoint. This does not
    prove reachability — only the vendor's first delivery does that — it
    rules out the three shapes that are certainly wrong.
    """
    problems: list[str] = []
    if not url:
        return ("no receiver url",)

    if not url.startswith(("http://", "https://")):
        problems.append(
            f"url must start with http:// or https:// (got {url!r})"
        )

    # Host = between the scheme and the first '/', '?' or '#'.
    remainder = url.split("://", 1)[-1]
    for separator in ("/", "?", "#"):
        remainder = remainder.split(separator, 1)[0]
    host = remainder.split("@")[-1]
    if host.startswith("["):  # bracketed IPv6
        host = host.split("]", 1)[0] + "]"
    else:
        host = host.split(":", 1)[0]
    host = host.lower()

    if host in _LOCAL_HOSTS or host.endswith(".local") or host.endswith(".localhost"):
        problems.append(
            f"{host!r} is local — the vendor cannot reach it, and registering "
            "it silently blackholes every agency's leads"
        )
    elif _is_private_ipv4(host):
        problems.append(
            f"{host!r} is a private address — unreachable from the vendor's "
            "network, and the failure is invisible on our side"
        )
    elif any(host.endswith(suffix) for suffix in _EPHEMERAL_TUNNEL_SUFFIXES):
        problems.append(
            f"{host!r} is an ephemeral tunnel — it stops existing when the "
            "tunnel closes, and the callback config is INTEGRATOR-WIDE, so "
            "the whole fleet's leads go with it"
        )

    if url.startswith("http://") and host not in _LOCAL_HOSTS:
        problems.append(
            "plaintext http:// — the credential is a static header with no "
            "signature, so TLS is the only thing protecting it in transit"
        )

    return tuple(problems)


def _is_private_ipv4(host: str) -> bool:
    parts = host.split(".")
    if len(parts) != 4 or not all(p.isdigit() for p in parts):
        return False
    first, second = int(parts[0]), int(parts[1])
    return (
        first == 10
        or (first == 192 and second == 168)
        or (first == 172 and 16 <= second <= 31)
        or first == 169 and second == 254
    )


__all__ = [
    "IMOVELWEB_BASIC_USERNAME",
    "IMOVELWEB_CALLBACK_LANGUAGES",
    "IMOVELWEB_CONTACT_TYPES",
    "IMOVELWEB_EVENT_TYPES",
    "IMOVELWEB_LEAD_EVENT_TYPES",
    "IMOVELWEB_LEAD_ORIGINS",
    "CallbackConfig",
    "ImovelWebLead",
    "basic_credential",
    "receiver_url_problems",
]
