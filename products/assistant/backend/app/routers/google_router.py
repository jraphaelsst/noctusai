"""Google for the Assistant (D50): "Conectar Google" (Calendar + Drive) per org.

* `/api/google/*` -- tier `org`, org ADMIN only: `connect/start` (returns the Google consent URL), `status`,
  `disconnect` (revoke at Google, then delete), `prova` (next 5 calendar events + 5 most recent Drive files, names only).
  No route ever returns a token.
* `GET /api/google/oauth/callback` -- the redirect target registered in Google Cloud Console: tier `service`
  (signed: it acts only for a `state` THIS server issued, single-use, 10 minutes, bound to the org/user AND the browser
  (host-only cookie) that started it, carrying the PKCE verifier). It sends the browser back to `/configuracoes/google?google=<resultado>`.
"""
# NO `from __future__ import annotations`: with @limiter.limit (slowapi) a postponed annotation resolves against the
# WRAPPER's globals and FastAPI silently treats the parameter as a Query (see academia-de-reciclagem interessados_router).
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import anyio.to_thread
from fastapi import Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.api.integration_errors import integration_error
from noctusai_seed.organ_auth import make_organ_auth

from app.dependencies import _db, coerce_org_uuid, get_admin_client
from app.dependencies import get_current_user_org
from app.rate_limit import limiter
from app.services import google_connection as gc

logger = logging.getLogger(__name__)

_organ_auth = make_organ_auth(get_current_user_org, lambda: _db.get_core_client(), context="A conexão com o Google")


async def require_org_admin(a: Any = Depends(_organ_auth.admin)) -> Any:
    """403 unless the caller is an admin of the selected org (the seed organ-auth admin gate)."""
    return a


# ----- Seams (FastAPI dependencies; tests inject the seed Fakes, prod builds the Real ones) -----
def get_provider():
    try:
        return gc.build_provider()
    except gc.GoogleNotConfigured as exc:
        raise integration_error("not_configured", exc=exc, op="google_provider") from None


def get_state_store():
    try:
        return gc.build_state_store(get_admin_client())
    except gc.GoogleNotConfigured as exc:
        raise integration_error("not_configured", exc=exc, op="google_state_store") from None


def get_credential_store():
    try:
        return gc.build_credential_store(get_admin_client())
    except gc.GoogleNotConfigured as exc:
        raise integration_error("not_configured", exc=exc, op="google_credential_store") from None


def get_google_clients(store: Any = Depends(get_credential_store)) -> gc.GoogleClients:
    return gc.GoogleClients(store)


def get_membership_checker():
    """`(user_id, org_id) -> is that user an admin of that org now`. A seam so the callback's re-check is testable."""
    return gc.user_is_org_admin


def get_grant_remover():
    """`(org_id, actor_id) -> None`: deletes the grant and records who did it, in one transaction (migration 019)."""
    return lambda org_id, actor_id: gc.remove_grant(get_admin_client(), org_id, actor_id)


router = make_router(tier="org", guard=require_org_admin, prefix="/api/google", tags=["Google"])
callback_router = make_router(tier="service", category="oauth-callback", prefix="/api/google", tags=["Google"])


def _org(auth: Any) -> str:
    return str(coerce_org_uuid(auth[2]))


def _user(auth: Any) -> str:
    return str(getattr(auth[0], "id", "") or "")


@router.get("/status")
async def status(auth: Any = Depends(require_org_admin), store: Any = Depends(get_credential_store)) -> dict:
    return gc.read_status(store, _org(auth)).as_dict()


@router.post("/connect/start")
@limiter.limit("10/minute")
async def connect_start(
    request: Request,  # required positionally by @limiter.limit (slowapi)
    response: Response,
    auth: Any = Depends(require_org_admin),
    provider: Any = Depends(get_provider),
    states: Any = Depends(get_state_store),
) -> dict:
    """Issue a single-use state (+ PKCE verifier) bound to this org/user AND to this browser (cookie); return the
    Google consent URL. A newer start supersedes this user's older one."""
    try:
        redirect = gc.redirect_uri()
    except gc.GoogleNotConfigured as exc:
        raise integration_error("not_configured", exc=exc, op="google_redirect_uri") from None
    # The provider mints the verifier+challenge WITH the consent URL, and the store needs the verifier to mint the state,
    # so the URL is built once with a placeholder and the real state is set as that one query parameter.
    probe = await provider.authorization_url(state="pending", scopes=gc.ASSISTANT_GOOGLE_SCOPES, redirect_uri=redirect)
    issued = states.issue(
        provider=gc.OAUTH_PROVIDER, org_id=_org(auth), user_id=_user(auth), redirect_uri=redirect,
        code_verifier=probe.code_verifier or "",
    )
    response.set_cookie(
        gc.COOKIE_NAME, issued.browser_nonce, max_age=gc.COOKIE_MAX_AGE, path="/", secure=True, httponly=True, samesite="lax",
    )  # host-only: no `domain`
    parts = urlsplit(probe.url)
    query = [(k, issued.state if k == "state" else v) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    return {"url": urlunsplit(parts._replace(query=urlencode(query)))}


def consume_state(states: Any, state: str, *, binding: str | None):
    """Single-use: a state this server issued for the Google provider TO THIS BROWSER, or None."""
    return states.consume(state, provider=gc.OAUTH_PROVIDER, binding=binding)


def _clear_cookie(resp):
    resp.delete_cookie(gc.COOKIE_NAME, path="/", secure=True, httponly=True, samesite="lax")
    return resp


def _back(resultado: str) -> RedirectResponse:
    return _clear_cookie(RedirectResponse(gc.frontend_url(f"/configuracoes/google?google={resultado}"), status_code=303))


async def _revoke_quietly(provider: Any, token: str, why: str) -> None:
    try:
        await provider.revoke(token)
    except Exception as exc:  # noqa: BLE001 -- best effort by design; the class is logged, never the token
        logger.warning("google %s: revoke failed: %s", why, exc.__class__.__name__)


@callback_router.get("/oauth/callback")
async def oauth_callback(
    request: Request,
    state: str = Query(..., max_length=200),
    code: str | None = Query(default=None, max_length=2000),
    error: str | None = Query(default=None, max_length=200),
    provider: Any = Depends(get_provider),
    states: Any = Depends(get_state_store),
    store: Any = Depends(get_credential_store),
    is_admin_of: Any = Depends(get_membership_checker),
):
    record = consume_state(states, state, binding=request.cookies.get(gc.COOKIE_NAME))
    if record is None:
        # not a state we issued TO THIS BROWSER (forged, replayed, expired, other provider, another browser): 400 and
        # redirect nowhere -- never act for a state the caller cannot prove it started
        return _clear_cookie(JSONResponse({"detail": "invalid oauth state"}, status_code=400))
    if error or not code:
        return _back("negado" if error == "access_denied" else "erro")
    if record.redirect_uri != gc.redirect_uri():
        logger.warning("google callback: redirect uri changed since the flow started")
        return _back("erro")
    try:  # the starter must STILL be an admin of that org (demoted / removed between start and callback => refuse)
        still_admin = await anyio.to_thread.run_sync(lambda: is_admin_of(record.user_id, record.org_id))
    except Exception as exc:  # noqa: BLE001 -- fail closed
        logger.warning("google callback: membership check failed: %s", exc.__class__.__name__)
        still_admin = False
    if not still_admin:
        return _back("erro")
    try:
        tokens = await provider.exchange_code(code=code, state=state, redirect_uri=record.redirect_uri,
                                              code_verifier=record.code_verifier)
    except Exception as exc:  # noqa: BLE001 -- the browser must land somewhere; the class (never the body) is logged
        logger.warning("google callback: exchange failed: %s", exc.__class__.__name__)
        return _back("erro")
    if not tokens.refresh_token:
        await _revoke_quietly(provider, tokens.access_token, "no-refresh-token")  # the grant exists at Google: undo it
        return _back("sem_refresh_token")
    try:
        previous = await anyio.to_thread.run_sync(lambda: store.get(record.org_id, gc.STORE_PROVIDER))
    except Exception:  # noqa: BLE001 -- an undecryptable old row must not block a fresh consent
        previous = None
    previous_token = (previous.tokens.get("refresh_token") if previous is not None else None) or None
    if previous_token and previous_token != tokens.refresh_token:
        await _revoke_quietly(provider, previous_token, "reconnect")  # reconnecting must not orphan the old grant
    try:
        await anyio.to_thread.run_sync(lambda: gc.persist_tokens(store, org_id=record.org_id, user_id=record.user_id, tokens=tokens))
    except Exception as exc:  # noqa: BLE001
        logger.warning("google callback: persist failed: %s", exc.__class__.__name__)
        await _revoke_quietly(provider, tokens.refresh_token, "persist-failed")  # never leave a grant nobody holds
        return _back("erro")
    return _back("conectado")


@router.post("/disconnect")
async def disconnect(
    auth: Any = Depends(require_org_admin),
    provider: Any = Depends(get_provider),
    store: Any = Depends(get_credential_store),
    remove: Any = Depends(get_grant_remover),
) -> dict:
    """Revoke the grant at Google, THEN delete it. A revoke that fails (network) still deletes locally -- the
    Assistant must stop holding it -- and says so (`revoked: false`) so the owner can remove it in their Google account.
    A row with no token at all is deleted without calling Google (`revoked: null`)."""
    org = _org(auth)
    stored = await anyio.to_thread.run_sync(lambda: store.get(org, gc.STORE_PROVIDER))
    if stored is None:
        return {"connected": False, "revoked": None}
    token = stored.tokens.get("refresh_token") or stored.tokens.get("access_token") or ""
    revoked: bool | None = None
    if token:
        revoked = True
        try:
            await provider.revoke(token)
        except Exception as exc:  # noqa: BLE001
            revoked = False
            logger.warning("google disconnect: revoke failed: %s", exc.__class__.__name__)
    await anyio.to_thread.run_sync(lambda: remove(org, _user(auth)))
    return {"connected": False, "revoked": revoked}


def _calendar_items(adapter) -> list[dict]:
    now = datetime.now(timezone.utc)
    events = adapter.list_events("primary", now, now + timedelta(days=30))[:5]
    out = []
    for ev in events:
        start = (ev.raw.get("start") or {})
        out.append({"titulo": ev.raw.get("summary") or "(sem título)", "inicio": start.get("dateTime") or start.get("date")})
    return out


async def _drive_items(reader) -> list[dict]:
    res = await reader.list_recent(page_size=5)
    return [{"nome": h.name, "tipo": h.mime_type, "modificado_em": h.modified_time} for h in res.files[:5]]


def _is_dead_token(exc: Exception) -> bool:
    return exc.__class__.__name__ == "RefreshError"


@router.get("/prova")
async def prova(
    auth: Any = Depends(require_org_admin),
    clients: gc.GoogleClients = Depends(get_google_clients),
    store: Any = Depends(get_credential_store),
) -> dict:
    """Proof the connection works: the next 5 calendar events and the 5 most recent Drive files (names only). Each
    half fails on its own (`status`: ok | sem_permissao | reconectar | erro) so one broken scope hides nothing."""
    org = _org(auth)
    st = await anyio.to_thread.run_sync(lambda: gc.read_status(store, org))
    if not st.connected:
        raise HTTPException(status_code=409, detail="Google não conectado.")
    result: dict[str, Any] = {"calendario": {"status": "ok", "itens": []}, "drive": {"status": "ok", "itens": []}}
    reconnect = False

    async def _half(key: str, scope: str, run) -> None:
        nonlocal reconnect
        if scope not in st.scopes:
            result[key]["status"] = "sem_permissao"
            return
        try:
            result[key]["itens"] = await run()
        except Exception as exc:  # noqa: BLE001 -- per-half isolation; the class is logged, never the body
            if _is_dead_token(exc):
                reconnect = True
                result[key]["status"] = "reconectar"
            else:
                logger.warning("google prova (%s): %s", key, exc.__class__.__name__)
                result[key]["status"] = "erro"

    await _half("calendario", gc.SCOPE_CALENDAR, lambda: anyio.to_thread.run_sync(lambda: _calendar_items(clients.calendar(org))))

    async def _drive():
        return await _drive_items(clients.drive(org))

    await _half("drive", gc.SCOPE_DRIVE_READ, _drive)
    if reconnect:
        await anyio.to_thread.run_sync(lambda: gc.mark_needs_reconnection(store, org))
    result["needs_reconnection"] = reconnect
    return result
