"""Canonical phone-number format for the whole platform.

WHY THIS EXISTS
---------------
Before this module the platform had FOUR hand-rolled phone helpers that
disagreed with each other:

- ``erp-imobiliario/backend/app/services/whatsapp_service.py::_normalize_phone``
  → bare digits, no ``+``, blindly prepends ``55`` to anything ≤11 digits.
- ``erp-imobiliario/frontend/src/lib/utils.ts::formatPhoneNumber``
  → ``(11) 99457-3387``, truncates at 11 digits, drops the country code.
- ``erp-imobiliario/frontend/src/components/modals/NovoUsuarioModal.tsx``
  → a second, byte-similar copy of the same function.
- ``social-wiring/backend/app/modules/leads/importer/parsers.py::parse_contato``
  → bare digits, no country code at all.

So the same person's phone was stored as ``5511994573387``, displayed as
``(11) 99457-3387``, imported as ``11994573387`` and arrived from Meta as
``+5511994573387`` — four representations of one fact, none of which
compare equal. Dedup, search and "is this the WhatsApp contact we already
have?" were all quietly broken.

THE CANONICAL FORM
------------------
**E.164**: a leading ``+``, then country code, then the national number,
digits only — ``+5511994573387``.

That is not an arbitrary pick. It is exactly the shape Meta Lead-Ads
delivers campaign phones in (864 of 958 rows in social-wiring on
2026-07-30), and it is one ``lstrip('+')`` away from the WhatsApp/WAHA
chat id (``5511994573387@c.us``) — which is where these numbers are
ultimately headed. Choosing the format the data ALREADY arrives in means
the intake path for campaigns is a no-op rather than a translation.

ONE KNOB
--------
``format_phone`` is the single display seam for the entire platform. It
returns E.164 today. If the display target ever changes (pretty pt-BR,
WhatsApp JID, …), change ``format_phone`` here and every product follows —
that is the whole point of this module existing.

WHAT THIS MODULE REFUSES TO DO
------------------------------
It never invents digits. Brazil's 2012 nine-digit mobile migration means
some legacy rows hold 8-digit mobiles that "should" have a 9 prefixed;
guessing which ones would silently corrupt real contacts. An unparseable
or ambiguous number returns ``None`` so the caller can flag it, never a
plausible-looking fabrication.
"""
from __future__ import annotations

import re

# E.164 caps the total digit count (country code included) at 15; the ITU
# sets no formal minimum, but nothing shorter than 8 is a dialable
# subscriber number in practice, and treating 6-digit junk as valid is how
# malformed rows survive an import.
_E164_MIN_DIGITS = 8
_E164_MAX_DIGITS = 15

DEFAULT_COUNTRY_CODE = "55"
"""Brazil. The country every product on this platform currently serves."""

_NON_DIGITS = re.compile(r"\D")

# Excel reads a phone column as a NUMBER and stringifies it back with a
# fractional part: "11995735128" becomes "11995735128.0". 547 rows in
# social-wiring landed that way. The trailing ".0" is a spreadsheet artifact,
# not a digit, and removing it is not a guess — it is only ever accepted when
# what remains is a valid number, the same rule the country-code
# disambiguation uses.
_EXCEL_FLOAT_SUFFIX = re.compile(r"\.0+\s*$")

# Brazil: 2-digit area code (DDD) 11–99, then an 8-digit landline or a
# 9-digit mobile that MUST start with 9 (ANATEL reserves the leading 9 for
# mobile). Anything else claiming +55 is malformed.
_BR_NATIONAL = re.compile(r"^(?P<ddd>[1-9][0-9])(?P<subscriber>9[0-9]{8}|[2-5][0-9]{7})$")


def phone_digits(raw: str | None) -> str | None:
    """Digits of a canonical number, no ``+``.

    This is the WhatsApp/WAHA form: ``f"{phone_digits(x)}@c.us"``. Returns
    ``None`` for anything ``normalize_phone`` rejects, so a caller cannot
    accidentally build a chat id out of junk.
    """
    canonical = normalize_phone(raw)
    return canonical[1:] if canonical else None


def normalize_phone(
    raw: str | None,
    *,
    default_country_code: str = DEFAULT_COUNTRY_CODE,
) -> str | None:
    """Canonicalize any phone spelling to E.164, or ``None`` if it isn't one.

    Accepts every shape the platform has been observed to hold::

        "+5511994573387"   -> "+5511994573387"   (Meta Lead-Ads — already canonical)
        "11 99457.3387"    -> "+5511994573387"   (workbook import)
        "(11) 99457-3387"  -> "+5511994573387"   (ERP form input)
        "011994573387"     -> "+5511994573387"   (trunk-prefixed)
        "5511994573387"    -> "+5511994573387"   (WAHA chat id, sans suffix)
        "1132165498"       -> "+551132165498"    (8-digit landline)

    And refuses what it cannot resolve without guessing::

        "+55115072510"     -> None   (7-digit subscriber — malformed)
        "1199457"          -> None   (too short)
        "não informado"    -> None
        None / ""          -> None

    ``default_country_code`` only applies to numbers written in NATIONAL
    form. A value that already carries an explicit ``+`` is trusted as
    international and passed through untouched — normalizing a ``+1``
    number by prepending ``55`` would be worse than leaving it alone.
    """
    if raw is None:
        return None

    text = str(raw).strip()
    if not text:
        return None

    result = _normalize_text(text, default_country_code)
    if result is not None:
        return result

    # Second reading: strip a spreadsheet float suffix and try once more.
    # Accepted ONLY when it yields a valid number, so a genuinely broken value
    # cannot be rescued into a plausible-looking wrong one.
    stripped = _EXCEL_FLOAT_SUFFIX.sub("", text)
    if stripped != text:
        return _normalize_text(stripped, default_country_code)
    return None


def _normalize_text(text: str, default_country_code: str) -> str | None:
    # An explicit "+" is an assertion by the source that what follows is a
    # full international number. Believe it — but still validate the shape
    # if it claims to be Brazilian, because that is the claim we can check.
    explicit_international = text.startswith("+")
    digits = _NON_DIGITS.sub("", text)
    if not digits:
        return None

    if explicit_international:
        return _validate_international(digits, default_country_code)

    # National form. A leading 0 is the Brazilian long-distance trunk
    # prefix ("0 11 9...", "021..."), never part of the number itself.
    digits = digits.lstrip("0")
    if not digits:
        return None

    # Already carries the country code (a bare WAHA chat id, or a DB row
    # normalized by an earlier pass). Detect it by SHAPE rather than by a
    # length threshold: "5511994573387" is CC+DDD+mobile, while a bare
    # "11994573387" is DDD+mobile and must NOT lose its "11" to a prefix
    # test. Only the country-code reading that leaves a valid national
    # number behind is accepted.
    if digits.startswith(default_country_code):
        remainder = digits[len(default_country_code):]
        if _BR_NATIONAL.match(remainder):
            return f"+{digits}"

    if _BR_NATIONAL.match(digits):
        return f"+{default_country_code}{digits}"

    return None


def _validate_international(digits: str, default_country_code: str) -> str | None:
    """Shape-check a number the source already marked international."""
    if digits.startswith(default_country_code):
        # It claims Brazil, so hold it to Brazil's rules — this is what
        # rejects "+55115072510" (a 7-digit subscriber) instead of storing
        # a number that can never be dialed or matched.
        return f"+{digits}" if _BR_NATIONAL.match(digits[len(default_country_code):]) else None

    # Foreign number: we have no per-country plan, so the only honest check
    # is the E.164 envelope itself.
    if _E164_MIN_DIGITS <= len(digits) <= _E164_MAX_DIGITS:
        return f"+{digits}"
    return None


def phone_search_digits(raw: str | None) -> str | None:
    """The digit-run to COMPARE when searching for a phone.

    Canonicalizing a stored number changes what the UI shows but not what a
    substring search matches, and that gap is a real bug: the Funil card and
    the detail modal render ``+5511981912534`` while the row still stores
    ``11 98191.2534``, so a user who copies the number they can SEE and pastes
    it into the search box gets zero results.

    Comparing digit-runs closes it in both directions::

        phone_search_digits("+5511981912534")  -> "5511981912534"
        phone_search_digits("11 98191.2534")   -> "5511981912534"   (canonical)
        phone_search_digits("981912534")       -> "981912534"       (raw fallback)

    A parseable value yields its CANONICAL digits, so every spelling of one
    number produces one key. An unparseable one falls back to its raw digits
    rather than ``None`` — a partial fragment the user typed is not a valid
    phone and must still be matchable.
    """
    if raw is None:
        return None
    canonical = normalize_phone(raw)
    if canonical:
        return canonical[1:]
    digits = _NON_DIGITS.sub("", str(raw))
    return digits or None


def is_valid_phone(raw: str | None) -> bool:
    """``True`` when ``raw`` canonicalizes. Use to flag rows, not to reject
    them silently."""
    return normalize_phone(raw) is not None


def format_phone(raw: str | None, *, fallback: str | None = None) -> str | None:
    """THE display seam. Every phone rendered anywhere goes through here.

    Returns canonical E.164. When ``raw`` cannot be canonicalized the
    original string is returned (or ``fallback`` when given) rather than
    ``None`` — a malformed number the user can SEE and fix beats a blank
    field that hides that we hold bad data.
    """
    canonical = normalize_phone(raw)
    if canonical:
        return canonical
    if fallback is not None:
        return fallback
    return str(raw).strip() if raw is not None and str(raw).strip() else None


__all__ = [
    "DEFAULT_COUNTRY_CODE",
    "format_phone",
    "is_valid_phone",
    "normalize_phone",
    "phone_digits",
    "phone_search_digits",
]
