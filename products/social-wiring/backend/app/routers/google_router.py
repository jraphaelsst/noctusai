"""Google-wide introspection endpoints.

Lives separately from ``calendar_router`` because Google scopes cover
multiple integrations (Calendar + Drive today, Gmail / Sheets / Docs
tomorrow) — the consent flow is owned by ``calendar_router`` for
historical reasons (single OAuth bundle shared across adapters), but
the introspection surface is Google-wide.

Current surface:

* ``GET /api/google/scopes`` — four-layer view of scope state:
  configured / kitchen-sink-default / granted-by-user /
  declined-by-user. Lets the operator answer "did Google honor my
  Consent Screen config?" without leaving the terminal.

Future additions could include token introspection (expiry, refresh
health), GCP project metadata, etc. — all under the ``/api/google``
prefix to signal "applies to every Google integration on this product".
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.config import settings
from app.dependencies import get_admin_client
from app.services.credential_vault import (
    CredentialStore, EncryptionNotConfigured, build_credential_store)
from app.services.google_scopes import (
    GOOGLE_KITCHEN_SINK_SCOPES,
    diagnose_consent_screen_gaps,
    discover_granted_scopes,
    resolve_google_scopes,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/google", tags=["google"])


# ─── Response shape ────────────────────────────────────────────────────
class GoogleScopesResponse(BaseModel):
    configured: list[str]             # what oauth_start would request
    kitchen_sink_default: list[str]   # the hardcoded full list
    granted_to_user: list[str] | None     # from tokeninfo after consent
    declined_by_user: list[str] | None    # configured ∩ ¬granted (best-effort)
    coverage_pct: float | None        # % of requested that came back granted
    note: str


# ─── Helpers ───────────────────────────────────────────────────────────
def _build_store() -> CredentialStore | None:
    """Try to build a CredentialStore. Returns None if encryption isn't
    configured (no fatal error — the scopes endpoint is informational)."""
    try:
        return build_credential_store(get_admin_client())
    except EncryptionNotConfigured:
        return None


def _resolve_org_id(raw: str | None) -> UUID:
    if raw:
        try:
            return UUID(raw)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid org_id",
            ) from exc
    return UUID(settings.local_dev_org_id)


# ─── Scope introspection ───────────────────────────────────────────────
@router.get("/scopes", response_model=GoogleScopesResponse)
def google_scopes(org_id: str | None = Query(default=None)) -> GoogleScopesResponse:
    """Show what scopes Google was asked for, the kitchen-sink default,
    and (after consent) what the user actually granted.

    Probes Google's ``tokeninfo`` endpoint with the stored access token
    to get the granted-scope ground truth. If no credential exists yet
    (consent never completed), ``granted_to_user`` is null.
    """
    configured = resolve_google_scopes(configured=settings.google_oauth_scopes)

    granted: list[str] | None = None
    declined: list[str] | None = None
    coverage_pct: float | None = None
    note_parts: list[str] = []

    store = _build_store()
    if store is None:
        note_parts.append(
            "ENCRYPTION_KEY not configured — can't read stored credentials, "
            "so granted/declined fields will stay null."
        )
    else:
        try:
            resolved_org = _resolve_org_id(org_id)
        except HTTPException:
            resolved_org = None

        # Import lazily so this module doesn't pull calendar deps at
        # import time (keeps the router lightweight).
        from app.services.calendar import CALENDAR_PROVIDER

        stored = None
        if resolved_org is not None:
            try:
                stored = store.get(str(resolved_org), CALENDAR_PROVIDER)
            except Exception as exc:
                logger.warning("Google credential lookup failed: %s", exc)

        if stored and stored.tokens.get("access_token"):
            granted = discover_granted_scopes(
                access_token=stored.tokens["access_token"],
            )
            if granted:
                diff = diagnose_consent_screen_gaps(
                    requested=configured,
                    granted=granted,
                )
                declined = diff["missing"]
                coverage_pct = diff["coverage_pct"]
        else:
            note_parts.append(
                "No Google credential stored for this org — visit "
                "/api/calendar/oauth/start to consent."
            )

    note_parts.append(
        f"Will request {len(configured)} scope(s) at next consent. "
        "Set GOOGLE_OAUTH_SCOPES=auto in .env (or leave empty) for "
        "kitchen-sink mode; set a comma/space-separated list to pin."
    )
    if configured == list(GOOGLE_KITCHEN_SINK_SCOPES):
        note_parts.append(
            "Reminder: every scope in the kitchen-sink must also be "
            "added to GCP Console → OAuth Consent Screen → Scopes "
            "before Google allows it at consent."
        )

    return GoogleScopesResponse(
        configured=configured,
        kitchen_sink_default=list(GOOGLE_KITCHEN_SINK_SCOPES),
        granted_to_user=granted,
        declined_by_user=declined,
        coverage_pct=coverage_pct,
        note=" ".join(note_parts),
    )


__all__ = ["router"]
