"""WhatsApp contact-identity resolver.

Given any raw JID (phone ``@c.us`` / ``@s.whatsapp.net`` or ``@lid``),
produces a canonical ``ResolvedIdentity`` that unifies all JID forms for
the same human under a single phone-digits key.

Problem
-------
WAHA 2026.x delivers inbound from three JID forms for one human:
- ``5511974693365@c.us``
- ``5511974693365@s.whatsapp.net``
- ``33613018058989@lid``  (and sometimes a second LID for the same phone)

The canonical dedup key is the PHONE (digits only), NOT the LID.

Resolution algorithm
--------------------
1.  ``@lid`` input → ``get_lid_phone(lid)`` → phone digits; ``get_contact(lid)``
    for pushname.
2.  Phone-form input → strip suffix → digits; ``get_contact(<phone>@c.us)``
    for the paired LID and display name.
3.  Fail-soft throughout: any WAHA error returns a partial result (at
    minimum the raw digits / lid string) and logs at WARNING — never raises.

Usage
-----
    resolver = resolve_identity(client, raw_jid="33613018058989@lid")
    # ResolvedIdentity(phone="5511974693365", jid="5511974693365@c.us",
    #                  lids=["33613018058989@lid"], name="João Raphael")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from noctusai_lib.integrations.whatsapp.lid_auth import is_lid, normalize_phone

if TYPE_CHECKING:
    from noctusai_lib.integrations.whatsapp.types import WhatsAppClient

logger = logging.getLogger(__name__)

_PHONE_SUFFIXES = ("@c.us", "@s.whatsapp.net")


@dataclass
class ResolvedIdentity:
    """Canonical identity for one human across all WAHA JID forms."""

    phone: str | None = None          # digits only, e.g. "5511974693365"
    jid: str | None = None            # canonical send JID, e.g. "5511974693365@c.us"
    lids: list[str] = field(default_factory=list)  # all known @lid JIDs
    name: str | None = None           # best display name (WAHA name > pushname > None)


def _extract_name(contact_data: dict[str, Any]) -> str | None:
    """Best display name from a WAHA contact dict."""
    return contact_data.get("name") or contact_data.get("pushname") or None


async def resolve_identity(
    client: "WhatsAppClient",
    raw_jid: str,
) -> ResolvedIdentity:
    """Resolve *raw_jid* to a :class:`ResolvedIdentity`.

    Fail-soft: WAHA errors produce a partial result; they never raise.
    """
    result = ResolvedIdentity()

    try:
        if is_lid(raw_jid):
            # ── LID path ──────────────────────────────────────────────
            result.lids = [raw_jid]
            # Step 1: LID → phone JID
            try:
                pn = await client.get_lid_phone(raw_jid)
            except Exception:
                logger.warning("resolve_identity: get_lid_phone failed for lid=%s", raw_jid)
                pn = None

            if pn:
                digits = normalize_phone(pn)
                result.phone = digits
                result.jid = f"{digits}@c.us"

            # Step 2: get_contact on the LID for pushname
            try:
                cdata = await client.get_contact(raw_jid)
            except Exception:
                logger.warning("resolve_identity: get_contact failed for lid=%s", raw_jid)
                cdata = {}
            result.name = _extract_name(cdata)

            # Step 3: get_contact on the phone-JID for the full record + name
            if result.jid:
                try:
                    cdata_phone = await client.get_contact(result.jid)
                except Exception:
                    logger.warning(
                        "resolve_identity: get_contact failed for jid=%s", result.jid
                    )
                    cdata_phone = {}
                # Phone-form contact may give a richer name
                if not result.name:
                    result.name = _extract_name(cdata_phone)
                # Phone-form contact returns paired LID — add it if different
                paired_lid = cdata_phone.get("lid")
                if paired_lid and paired_lid not in result.lids:
                    result.lids.append(paired_lid)

        else:
            # ── Phone-JID path ────────────────────────────────────────
            digits = normalize_phone(raw_jid)
            result.phone = digits
            result.jid = f"{digits}@c.us"

            try:
                cdata = await client.get_contact(result.jid)
            except Exception:
                logger.warning(
                    "resolve_identity: get_contact failed for jid=%s", result.jid
                )
                cdata = {}

            result.name = _extract_name(cdata)
            # WAHA returns the paired LID on phone-form contacts
            paired_lid = cdata.get("lid")
            if paired_lid:
                result.lids = [paired_lid]

    except Exception:
        logger.warning(
            "resolve_identity: unexpected error for raw_jid=%s", raw_jid, exc_info=True
        )

    return result


def build_lids_map_from_list(lids_list: list[dict]) -> dict[str, str]:
    """Convert ``list_lids()`` output to a {lid_jid: phone_digits} lookup dict.

    Example input: [{"lid": "33613018058989@lid", "pn": "5511974693365@c.us"}, ...]
    Example output: {"33613018058989@lid": "5511974693365"}

    Used to build a ONE-SHOT LID→phone map for the chats dedup pass
    (avoids N WAHA calls per chat).
    """
    result: dict[str, str] = {}
    for entry in lids_list:
        lid = entry.get("lid") or ""
        pn = entry.get("pn") or ""
        if lid and pn:
            result[lid] = normalize_phone(pn)
    return result
