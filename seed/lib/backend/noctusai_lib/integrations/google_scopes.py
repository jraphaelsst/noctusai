"""Google OAuth scope resolution + post-consent introspection.

Reconciled 2026-05-16 by `projects/social-wiring-absorption/` Wave 1.E3
from the live-validated workspace module
`youtube-crawler/app/services/google_scopes.py`
(promotion manifest `reference/.promotions/google-scope-discovery.md`,
session note `SESSION-NOTES_google-scope-discovery-2026-05-13.md`).

WHY this module
---------------
Per-workspace `GOOGLE_OAUTH_SCOPES` env vars drift as scope lists
evolve — operators hand-edit one workspace, forget another, prod
diverges from dev. Google (unlike Meta) exposes NO "list my app's
configured scopes" endpoint, so full auto-discovery is impossible.
What we CAN do:

1. Move the canonical scope list into code
   (`GOOGLE_KITCHEN_SINK_SCOPES`) and let `GOOGLE_OAUTH_SCOPES=auto`
   invoke it — the env var stops being a maintenance surface.
2. Probe Google's `oauth2/v3/tokeninfo` endpoint post-consent to read
   the *actually-granted* scope list — the ground truth the operator
   needs to confirm "did GCP Console accept every scope I asked for?".
3. Set-diff requested vs granted (`diagnose_consent_screen_gaps`) so
   the operator gets a "covered 100% / 60% / 0%" answer + the exact
   missing-scope list, without manual comparison.

Layer placement
---------------
This is a provider-wide *shared helper* (every Google adapter on the
consent path touches it), so it sits at the top level of
`noctusai_lib.integrations.` alongside the `google_calendar` /
`google_maps` / `google_drive` adapter packages — matching noc's
flat `google_*` layout (the manifest's `google/scopes/` assumed a
`google/` parent package which noc does not use).

Pure-logic + httpx — exempt from Protocol+Fake+Real per
`KB § PATTERNS/seed-fake-real-adapter.md`: the resolver/diagnosis
functions are pure; only `discover_granted_scopes` touches the
network and is tested with a mocked httpx transport (a Fake here
would exercise no different code than the Real).

Kitchen-sink split (per manifest §3)
------------------------------------
`GOOGLE_KITCHEN_SINK_BASE` = identity scopes every Google product
needs. `GOOGLE_KITCHEN_SINK_SCOPES` = base + Calendar + Drive (what
the social-wiring CMS ships today). A consuming product extends by
passing its own list to `resolve_google_scopes(..., kitchen_sink=)`.

Operator note (NOT an LLM count): every scope in the kitchen-sink
list MUST be added in GCP Console → APIs & Services → OAuth Consent
Screen → Scopes BEFORE the consent flow can request it. Google
*blocks* unconfigured scopes (unlike Meta, which silently filters).
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

# Stable since 2017. If Google ever deprecates v3, bump here only.
GOOGLE_TOKENINFO_URL = "https://www.googleapis.com/oauth2/v3/tokeninfo"

# Identity scopes every Google-OAuth product needs.
GOOGLE_KITCHEN_SINK_BASE: list[str] = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

# Base + the Calendar + Drive scopes the social-wiring CMS ships today.
# A product needing more (Gmail, Sheets, Docs) passes its own list to
# `resolve_google_scopes(..., kitchen_sink=...)` — it does NOT edit this
# constant (that would couple the seed to one product's needs).
GOOGLE_KITCHEN_SINK_SCOPES: list[str] = GOOGLE_KITCHEN_SINK_BASE + [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]

_DEFAULT_TIMEOUT = 15.0


def _dedupe_preserving_order(scopes: list[str]) -> list[str]:
    """Drop duplicates, keep first-occurrence order (stable consent URL)."""
    seen: set[str] = set()
    out: list[str] = []
    for s in scopes:
        s = s.strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def resolve_google_scopes(
    configured: str | None,
    *,
    kitchen_sink: list[str] | None = None,
) -> list[str]:
    """Resolve the configured scope env value to a concrete scope list.

    - `"auto"` (case-insensitive) OR empty / whitespace → the
      `kitchen_sink` list (defaults to `GOOGLE_KITCHEN_SINK_SCOPES`).
    - Anything else → parsed as an explicit list, split on commas OR
      whitespace (operators write both), deduped preserving order.

    The kitchen-sink list is the per-product extension point — a
    product that also needs Gmail passes
    `kitchen_sink=GOOGLE_KITCHEN_SINK_BASE + [...gmail..., ...calendar...]`.
    """
    sink = kitchen_sink if kitchen_sink is not None else GOOGLE_KITCHEN_SINK_SCOPES
    raw = (configured or "").strip()
    if not raw or raw.lower() == "auto":
        return _dedupe_preserving_order(list(sink))
    # Explicit: accept comma- and/or whitespace-separated.
    parts: list[str] = []
    for chunk in raw.split(","):
        parts.extend(chunk.split())
    return _dedupe_preserving_order(parts)


def format_scopes_for_authorize(scopes: list[str]) -> str:
    """Join scopes with single spaces — Google's authorize-endpoint
    format (Google uses spaces, NOT commas, in the `scope` query param)."""
    return " ".join(scopes)


def discover_granted_scopes(
    access_token: str,
    *,
    http_client: httpx.Client | None = None,
) -> list[str]:
    """Probe Google's `oauth2/v3/tokeninfo` for the *actually-granted*
    scope list — the post-consent ground truth.

    Returns `[]` on ANY failure (network error, non-2xx, missing
    `scope` field) — an empty list means "unknown", never raises into
    the caller. Failures are logged at WARN (no-silent-errors rule).
    """
    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=_DEFAULT_TIMEOUT)
    try:
        response = client.get(
            GOOGLE_TOKENINFO_URL, params={"access_token": access_token}
        )
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        logger.warning("google_scopes.tokeninfo_failed error=%s", exc)
        return []
    except ValueError as exc:  # non-JSON body
        logger.warning("google_scopes.tokeninfo_bad_body error=%s", exc)
        return []
    finally:
        if owns_client:
            client.close()
    scope_raw = data.get("scope", "")
    if not isinstance(scope_raw, str) or not scope_raw.strip():
        logger.warning(
            "google_scopes.tokeninfo_no_scope_field keys=%s", sorted(data)
        )
        return []
    return scope_raw.split()


def diagnose_consent_screen_gaps(
    requested: list[str],
    granted: list[str],
) -> dict:
    """Set-diff requested vs granted → operator-facing coverage report.

    Answers "did Google honor every scope I asked for?" without manual
    list comparison. Coverage is `granted∩requested / requested`. A
    `<100%` coverage is the signal a scope is missing from the GCP
    Console Consent Screen config (Google blocks unconfigured scopes).

    Returns:
        {
          "requested": [...],            # deduped, order-stable
          "granted": [...],              # deduped, order-stable
          "missing": [...],              # requested - granted
          "extra": [...],                # granted - requested (rare)
          "coverage_pct": 0.0..100.0,    # 100.0 when requested is empty
        }
    """
    req = _dedupe_preserving_order(requested)
    grn = _dedupe_preserving_order(granted)
    req_set, grn_set = set(req), set(grn)
    missing = [s for s in req if s not in grn_set]
    extra = [s for s in grn if s not in req_set]
    if not req:
        coverage = 100.0
    else:
        coverage = round(100.0 * (len(req_set) - len(missing)) / len(req_set), 1)
    return {
        "requested": req,
        "granted": grn,
        "missing": missing,
        "extra": extra,
        "coverage_pct": coverage,
    }


__all__ = [
    "GOOGLE_KITCHEN_SINK_BASE",
    "GOOGLE_KITCHEN_SINK_SCOPES",
    "GOOGLE_TOKENINFO_URL",
    "diagnose_consent_screen_gaps",
    "discover_granted_scopes",
    "format_scopes_for_authorize",
    "resolve_google_scopes",
]
