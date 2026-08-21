"""`/api/portals/receiver-tokens/*` — operator management of the
per-advertiser webhook URLs.

Portal-generic on purpose: the token table carries a `provider`, and the
next portal (direct ImovelWeb) manages its URLs through these same three
routes rather than growing a parallel set.

The whole point of this router is to produce **one copyable URL** for a
human to paste into a vendor's CRM-integration field. So the mint
response is the only place a plaintext token is ever returned, and it is
returned assembled into the full URL — an operator who has to concatenate
a base and a token by hand eventually pastes a wrong one, and a wrong URL
in Canal Pro fails silently as "no leads are arriving".
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import settings
from app.dependencies import coerce_org_uuid, get_current_user_org_unified
from app.modules.leads.deps import get_leads_client
from app.modules.portal_leads.services.receiver_token_service import (
    RECEIVER_TOKEN_PROVIDERS,
    UnknownReceiverProvider,
    list_receiver_tokens,
    mint_receiver_token,
    revoke_receiver_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/portals/receiver-tokens", tags=["portal-leads"])

#: Where each provider's receiver lives, relative to the public base.
#: Explicit rather than f-string-derived: `imovelweb` is listed so the
#: table's CHECK and this map cannot silently disagree, and a provider
#: whose route does not exist yet must fail loudly at mint time rather
#: than hand an operator a URL that 404s.
_RECEIVER_PATHS: dict[str, str] = {
    "olx": "/api/portals/olx/leads",
}


class MintReceiverTokenIn(BaseModel):
    provider: str = Field(..., description="Portal this URL receives for.")
    label: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Human note — which advertiser account this URL is for.",
    )


class MintReceiverTokenOut(BaseModel):
    id: str
    provider: str
    label: str
    token_prefix: str
    url: str = Field(
        ...,
        description=(
            "The full receiver URL, containing the plaintext token. Shown "
            "ONCE — it is not stored and cannot be retrieved again."
        ),
    )


class ReceiverTokenOut(BaseModel):
    id: str
    provider: str
    label: str
    token_prefix: str
    created_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    revoked_at: Optional[str] = None


#: Injected public-origin provider. `None` ⇒ resolve from settings for
#: real. Module-level rather than a FastAPI dependency because
#: `_receiver_url` is called from two places that are not both deps.
#:
#: This seam exists because the alternative is a test doing
#: `monkeypatch.setattr(settings, "tunnel_hostname", ...)`, which is
#: monkeypatching our own code — forbidden here in tests as well as in
#: production (`KB § PATTERNS/backend/di-test-seam.md`), and flagged
#: high-severity by `check_all_products`. It earned exactly that finding
#: on 2026-08-21 before this seam existed.
_base_url_provider: Optional[Callable[[], str]] = None


def configure_receiver_urls(
    *, base_url_provider: Optional[Callable[[], str]] = None
) -> None:
    """Install (or with `None`, clear) the public-origin provider.

    Always pair it with `reset_receiver_urls()` — a leaked provider
    silently re-configures every later test in the session.
    """
    global _base_url_provider
    _base_url_provider = base_url_provider


def reset_receiver_urls() -> None:
    """Drop any injected provider. Fixture teardown calls this."""
    configure_receiver_urls(base_url_provider=None)


def _public_base_url() -> str:
    """The externally reachable origin for this backend.

    Resolution order is deliberate: the value an operator pastes into a
    vendor's form must be the one the vendor can actually reach, so the
    tunnel hostname (which is what is publicly routed) outranks anything
    inferred. Empty means we do not know, and the caller is told so
    instead of being handed a relative path that looks like a URL.

    Read fresh on every call, never captured at import, so an operator
    changing the deployment's origin does not need a restart.
    """
    if _base_url_provider is not None:
        return (_base_url_provider() or "").rstrip("/")
    for candidate in (settings.tunnel_hostname, settings.oauth_redirect_base_url):
        if candidate:
            return candidate.rstrip("/")
    return ""


def _receiver_url(provider: str, token: str) -> str:
    path = _RECEIVER_PATHS.get(provider)
    if path is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"provider {provider!r} has no receiver route yet — minting a "
                "token for it would produce a URL that 404s"
            ),
        )
    base = _public_base_url()
    if not base:
        raise HTTPException(
            status_code=503,
            detail=(
                "the public base URL is not configured (TUNNEL_HOSTNAME / "
                "OAUTH_REDIRECT_BASE_URL), so a receiver URL cannot be built. "
                "Refusing rather than returning a relative path that would be "
                "pasted into a vendor form and silently never receive anything."
            ),
        )
    return f"{base}{path}/{token}"


@router.post("", response_model=MintReceiverTokenOut, status_code=201)
def mint_token(
    body: MintReceiverTokenIn,
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> MintReceiverTokenOut:
    """Issue a new receiver URL for this org.

    Existing tokens are left active. Rotation is issue-new → paste-new →
    confirm traffic moved → revoke-old, because the vendor field is
    changed by a human and any revoke-first order drops every lead in the
    gap.
    """
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    # Build-then-mint: a URL we cannot assemble must not leave a live
    # token in the table that nobody can use and nobody will revoke.
    _receiver_url(body.provider, "probe")

    try:
        minted = mint_receiver_token(
            client, org_id=org_id, provider=body.provider, label=body.label
        )
    except UnknownReceiverProvider as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    logger.info(
        "receiver-token: minted provider=%s org=%s prefix=%s",
        body.provider,
        org_id,
        minted.token_prefix,
    )
    return MintReceiverTokenOut(
        id=str(minted.id),
        provider=minted.provider,
        label=minted.label,
        token_prefix=minted.token_prefix,
        url=_receiver_url(body.provider, minted.plaintext),
    )


@router.get("", response_model=list[ReceiverTokenOut])
def list_tokens(
    provider: Optional[str] = Query(None),
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> list[ReceiverTokenOut]:
    """This org's receiver tokens. Never includes a plaintext.

    `last_seen_at` is the column worth reading: a token that has never
    been seen is the signature of a URL that was pasted wrong, which is
    otherwise indistinguishable from "no leads today".
    """
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    if provider is not None and provider not in RECEIVER_TOKEN_PROVIDERS:
        raise HTTPException(status_code=422, detail=f"unknown provider {provider!r}")

    rows = list_receiver_tokens(client, org_id=org_id, provider=provider)
    return [
        ReceiverTokenOut(
            id=str(r.get("id")),
            provider=str(r.get("provider")),
            label=str(r.get("label") or ""),
            token_prefix=str(r.get("token_prefix") or ""),
            created_at=r.get("created_at"),
            last_seen_at=r.get("last_seen_at"),
            revoked_at=r.get("revoked_at"),
        )
        for r in rows
    ]


@router.delete("/{token_id}", status_code=200)
def revoke_token(
    token_id: str,
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    """Revoke one token.

    A revoked token stops resolving, and deliveries still addressed to it
    park as `unresolved` behind a 200 — they are not lost, but they are
    not attributed either. Revoke only after `last_seen_at` shows traffic
    has moved to the replacement.
    """
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    try:
        parsed_id = UUID(token_id)
    except (ValueError, AttributeError, TypeError) as exc:
        # Not `coerce_org_uuid` — that helper carries org-resolution
        # semantics and reusing it for a row id would make a malformed id
        # read as an org problem in the logs.
        raise HTTPException(status_code=422, detail="token id is not a UUID") from exc

    revoked = revoke_receiver_token(client, org_id=org_id, token_id=parsed_id)
    if not revoked:
        # 404, not 403: saying "that token exists but is not yours" would
        # confirm the id to a caller from another org.
        raise HTTPException(status_code=404, detail="token not found or already revoked")
    return {"status": "revoked", "id": token_id}


__all__ = ["configure_receiver_urls", "reset_receiver_urls", "router"]
