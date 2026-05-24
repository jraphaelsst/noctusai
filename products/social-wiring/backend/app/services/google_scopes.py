"""Google OAuth scope catalog + resolver + post-consent introspection.

Why this module exists:

Three packages (``calendar/``, ``drive_api/``, plus future Gmail / Sheets /
Docs adapters) share a single Google OAuth credential bundle stored under
provider ``google_calendar``. The scopes requested at consent time
determine what every downstream adapter can do. Without a shared module,
each adapter would have to either:

1. Hardcode its own scope list (fragmented + duplicated), or
2. Read a flat env var (operator must maintain it manually).

This module is the source of truth: a kitchen-sink scope list covering
Calendar + Drive (the two we ship today), a resolver that respects the
``GOOGLE_OAUTH_SCOPES=auto`` convention, and a ``tokeninfo`` probe for
post-consent introspection. Same shape as
``noctusai_lib.integrations.meta.resolve_oauth_scopes`` (the seed Meta
module the product Meta consumer now wraps).

Important Google-vs-Meta nuance: Google does NOT expose a "list my app's
configured scopes" endpoint. Scopes must be added to the OAuth Consent
Screen in GCP Console before they can be requested at consent — otherwise
Google blocks the consent with an "unverified app" warning per scope.
The kitchen-sink list here is the realistic "we use these in this product"
set; expanding it requires operator action in GCP Console.

For introspection, ``https://www.googleapis.com/oauth2/v3/tokeninfo``
returns the granted scope string from an access token — accurate proof
of what the user actually consented to (vs. what we asked for).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


GOOGLE_TOKENINFO_URL = "https://www.googleapis.com/oauth2/v3/tokeninfo"


# Kitchen-sink set covering this product's current + near-future Google
# integrations. Identity scopes always safe (no review needed); Calendar
# + Drive sets are what the chatbot tools call. YouTube has its own OAuth
# client (``settings_router.oauth_router``) with separate scopes — not
# included here because that consent flow is unrelated.
#
# Adding a scope here is necessary but NOT sufficient — the operator must
# also add the matching entry to the OAuth Consent Screen at
# https://console.cloud.google.com/apis/credentials/consent before Google
# allows it at consent time.
GOOGLE_KITCHEN_SINK_SCOPES = [
    # Identity (Standard-Access; no review needed for any user)
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    # Calendar (Sensitive scope — needs the test user to be on the
    # Consent Screen's test-users list while the app is in Testing mode)
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    # Drive (Restricted scope — needs Google verification for production;
    # works fine in Testing mode with the test-users list)
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]


def resolve_google_scopes(*, configured: str) -> list[str]:
    """Decide what scope list to send to Google's consent dialog.

    - If ``configured`` is empty or ``"auto"`` (case-insensitive) →
      return :data:`GOOGLE_KITCHEN_SINK_SCOPES`.
    - Else split by **comma** OR **whitespace** (Google scope strings
      historically use whitespace; comma is accepted for parity with the
      Meta sibling).

    Returns the list deduplicated, preserving first-occurrence order.
    """
    raw = (configured or "").strip()
    if raw and raw.lower() != "auto":
        # Accept both comma-separated and whitespace-separated forms.
        if "," in raw:
            candidates = [s.strip() for s in raw.split(",") if s.strip()]
        else:
            candidates = [s.strip() for s in raw.split() if s.strip()]
    else:
        candidates = list(GOOGLE_KITCHEN_SINK_SCOPES)

    seen: set[str] = set()
    out: list[str] = []
    for s in candidates:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def format_scopes_for_authorize(scopes: list[str]) -> str:
    """Google's ``authorize`` endpoint accepts SPACE-SEPARATED scopes
    in the ``scope`` query param (not comma-separated like Meta).
    """
    return " ".join(scopes)


def discover_granted_scopes(
    *,
    access_token: str,
    timeout: float = 15.0,
) -> list[str]:
    """Probe Google's tokeninfo endpoint to see what scopes the access
    token actually has.

    Returns the granted scope list (best signal of what the user
    consented to). Returns ``[]`` if the call fails — the caller should
    treat that as "unknown" rather than "no scopes".

    Docs: https://developers.google.com/identity/protocols/oauth2/openid-connect#validatinganidtoken
    (the same endpoint works for access-token introspection).
    """
    try:
        response = httpx.get(
            GOOGLE_TOKENINFO_URL,
            params={"access_token": access_token},
            timeout=timeout,
        )
        if response.status_code != 200:
            logger.warning(
                "Google tokeninfo returned %s: %s",
                response.status_code, response.text[:200],
            )
            return []
        body = response.json()
    except Exception as exc:
        logger.warning("Google tokeninfo probe failed: %s", exc)
        return []

    scope_str = body.get("scope", "") or ""
    return [s for s in scope_str.split() if s]


def diagnose_consent_screen_gaps(
    *,
    requested: list[str],
    granted: list[str],
) -> dict[str, Any]:
    """Compare what we asked for vs. what the user got.

    Returns a dict with:
    - ``missing``: scopes requested but not granted (likely declined or
      not in Consent Screen config)
    - ``extra``: scopes granted but not requested (granted via
      ``include_granted_scopes=true``, harmless)
    - ``coverage_pct``: granted ∩ requested as a percentage

    Helps the operator answer "did Google actually give me everything I
    asked for?" without manually diffing two lists.
    """
    req_set = set(requested)
    grant_set = set(granted)
    missing = sorted(req_set - grant_set)
    extra = sorted(grant_set - req_set)
    overlap = req_set & grant_set
    coverage = (
        round(100 * len(overlap) / len(req_set), 1) if req_set else 0.0
    )
    return {
        "missing": missing,
        "extra": extra,
        "coverage_pct": coverage,
    }
