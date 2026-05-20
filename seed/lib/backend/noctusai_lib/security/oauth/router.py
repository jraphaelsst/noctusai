"""`oauth_router(*providers, on_callback=)` — generic OAuth callback router.

Mounts FOUR endpoints per registered provider, all under
`/api/oauth/<provider>/...`:

  GET  /api/oauth/{provider}/authorize?scopes=…&state=…&redirect_uri=…
       → returns `{"url": "...", "state": "..."}` (the consent URL).
       Consumer redirects the user there.

  GET  /api/oauth/{provider}/callback?code=…&state=…
       → exchanges `code` for tokens, calls `on_callback(result)`,
         returns `{"provider": "...", "state": "...", "ok": true|false}`.
       The `redirect_uri` consumed here is read from the query string
       too (forwarded so it matches the authorize call).

  POST /api/oauth/{provider}/refresh
       Body: `{"refresh_token": "..."}`
       → returns the new TokenSet shape as JSON.

  POST /api/oauth/{provider}/revoke
       Body: `{"token": "..."}`
       → 204 on success.

Persistence is the consumer's concern
-------------------------------------
This router does NOT save tokens. The `on_callback` async hook is the
only seam for "what to do with a successful exchange" — products plug
their persistence (encrypted-at-rest via
`noctusai_lib.security.encrypted_tokens.encrypt(...)`) here. If
`on_callback` is None, the callback still works (exchange + result
echo back to the browser); the consumer is then responsible for
fetching the tokens via some other path. The router stays unopinionated
about storage.

Error handling — never raise into the response body
---------------------------------------------------
Every exchange/refresh failure maps to either a JSON error response
(refresh / revoke) or `OAuthCallbackResult(error=...)` (callback). The
router never lets a network error / token-endpoint 4xx escape as a 500
into a browser-facing response — consumers depend on the callback path
landing _somehow_ so their state-machine doesn't strand.

Unknown-provider semantics
--------------------------
Requests for `/api/oauth/<not-registered>/...` return 404 with a
`{"detail": "unknown provider: <name>"}` body. The router knows the
provider set at construction time; it doesn't accept dynamic
registration after mounting.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response

from noctusai_lib.security.oauth.protocol import OAuthProvider
from noctusai_lib.security.oauth.types import OAuthCallbackResult

logger = logging.getLogger(__name__)


CallbackHook = Callable[[OAuthCallbackResult], Awaitable[None]]
def oauth_router(
    *providers: OAuthProvider,
    on_callback: CallbackHook | None = None,
    prefix: str = "/api/oauth",
    callback_paths: dict[str, str] | None = None,
) -> APIRouter:
    """Build an APIRouter exposing the OAuth dance for `providers`.

    Args:
        *providers: one or more `OAuthProvider` instances. Each provider's
            `name` is the path segment (`<prefix>/<name>/...`). Names
            must be unique within the router; duplicates raise `ValueError`
            at construction.
        on_callback: optional async hook invoked on every callback round-trip
            (success OR failure — `result.error` is set on failure). The
            hook is where consumers persist tokens, typically encrypting
            via `noctusai_lib.security.encrypted_tokens.encrypt(...)` first.
            When None, the callback handler simply returns the result
            shape; the consumer is then responsible for retrieving tokens
            via a parallel mechanism.
        prefix: URL prefix every endpoint is mounted under. Defaults to
            `"/api/oauth"` — the historical hardcoded value, so existing
            consumers are unaffected. Override when a product must serve
            the OAuth dance under a different base path.
        callback_paths: optional per-provider absolute callback-path map
            (`{provider_name: "/api/youtube/oauth/callback", ...}`). A
            provider listed here gets its `GET callback` endpoint mounted
            at the given **absolute** path (independent of `prefix`),
            instead of the default `<prefix>/<name>/callback`. This is the
            "absorbed product carries pre-registered Google-Cloud-Console
            redirect URIs that MUST NOT move" seam — the legacy path is
            preserved verbatim, every other endpoint
            (authorize/refresh/revoke) still lives under `prefix`. When
            None (the default), every provider's callback is the default
            `<prefix>/<name>/callback` — zero existing-consumer impact.

    Returns:
        A FastAPI `APIRouter` ready to be mounted via
        `create_product_app(..., extra_routers=[oauth_router(...)])`
        (or any equivalent `app.include_router(...)`).

    Raises:
        ValueError: if `providers` is empty, has duplicate `name`s, or
            `callback_paths` references an unregistered provider name.
    """
    if not providers:
        raise ValueError("oauth_router requires at least one OAuthProvider")

    registry: dict[str, OAuthProvider] = {}
    for provider in providers:
        if provider.name in registry:
            raise ValueError(
                f"oauth_router duplicate provider name: {provider.name!r}"
            )
        registry[provider.name] = provider

    overrides: dict[str, str] = dict(callback_paths or {})
    for _name in overrides:
        if _name not in registry:
            raise ValueError(
                f"oauth_router callback_paths references unknown provider: "
                f"{_name!r} (registered: {sorted(registry)})"
            )

    # Prefix-less router: every route carries its FULL path explicitly so
    # `callback_paths` overrides can sit at an arbitrary absolute path
    # while the default endpoints stay under `prefix`. (A FastAPI
    # `APIRouter(prefix=...)` would prepend `prefix` to *every* route,
    # making absolute-path overrides impossible — hence prefix-less here
    # with `prefix` baked into the default route strings.)
    base = prefix.rstrip("/")
    router = APIRouter(tags=["OAuth"])

    def _resolve(name: str) -> OAuthProvider:
        if name not in registry:
            raise HTTPException(status_code=404, detail=f"unknown provider: {name}")
        return registry[name]

    async def _run_callback(
        provider: str,
        state: str,
        code: str | None,
        error: str | None,
        redirect_uri: str,
    ) -> dict:
        """Shared callback body — used by both the default
        `<prefix>/{provider}/callback` route and any `callback_paths`
        override."""
        impl = _resolve(provider)

        if error:
            result = OAuthCallbackResult(
                provider=provider, state=state, tokens=None, error=error
            )
        elif not code:
            result = OAuthCallbackResult(
                provider=provider,
                state=state,
                tokens=None,
                error="missing authorization code",
            )
        else:
            try:
                tokens = await impl.exchange_code(
                    code=code, state=state, redirect_uri=redirect_uri
                )
                result = OAuthCallbackResult(
                    provider=provider, state=state, tokens=tokens, error=None
                )
            except Exception as exc:  # noqa: BLE001 — collapse all to result.error
                logger.warning(
                    "oauth_router: exchange_code failed for provider=%s: %s",
                    provider,
                    exc,
                )
                result = OAuthCallbackResult(
                    provider=provider,
                    state=state,
                    tokens=None,
                    error=f"exchange failed: {exc.__class__.__name__}",
                )

        if on_callback is not None:
            try:
                await on_callback(result)
            except Exception as exc:  # noqa: BLE001 — hook errors are not response errors
                logger.exception(
                    "oauth_router: on_callback hook raised for provider=%s; "
                    "treating as non-fatal so the response still echoes",
                    provider,
                )
                # Carry the hook failure into the response so consumers see it.
                if result.error is None:
                    result = OAuthCallbackResult(
                        provider=result.provider,
                        state=result.state,
                        tokens=result.tokens,
                        error=f"on_callback hook failed: {exc.__class__.__name__}",
                    )

        return {
            "provider": result.provider,
            "state": result.state,
            "ok": result.error is None,
            "error": result.error,
        }

    # ─── GET authorize ────────────────────────────────────────────────────

    @router.get(f"{base}/{{provider}}/authorize")
    async def authorize(
        provider: str,
        state: str = Query(...),
        redirect_uri: str = Query(...),
        scopes: list[str] = Query(default_factory=list),
    ) -> dict:
        """Build the provider consent URL and hand it back to the consumer.

        `scopes` accepts repeated `?scopes=...&scopes=...` query params
        (FastAPI's standard list-from-query convention). `state` and
        `redirect_uri` are required.
        """
        impl = _resolve(provider)
        auth_url = await impl.authorization_url(
            state=state, scopes=scopes, redirect_uri=redirect_uri
        )
        return {"url": auth_url.url, "state": auth_url.state}

    # ─── GET callback (default — `<prefix>/{provider}/callback`) ───────────

    @router.get(f"{base}/{{provider}}/callback")
    async def callback(
        provider: str,
        request: Request,
        state: str = Query(...),
        code: str | None = Query(default=None),
        error: str | None = Query(default=None),
        redirect_uri: str = Query(...),
    ) -> dict:
        """Exchange the auth code, fire `on_callback`, return a result echo.

        The `error` query param is set by some providers (Google
        included) when the user denies consent. We surface that as
        `OAuthCallbackResult(error=...)` directly without attempting
        an exchange.

        Providers listed in `callback_paths` are served by a dedicated
        absolute-path route (registered below) instead of this default —
        they 404 here so the legacy registered redirect URI is the only
        callback surface for them.
        """
        if provider in overrides:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"provider {provider!r} uses a fixed callback path "
                    f"({overrides[provider]!r}); the default callback route "
                    f"is not mounted for it"
                ),
            )
        return await _run_callback(
            provider=provider,
            state=state,
            code=code,
            error=error,
            redirect_uri=redirect_uri,
        )

    # ─── GET callback (per-provider absolute-path overrides) ───────────────
    # One route per `callback_paths` entry, at the exact absolute path so
    # the legacy Google-Cloud-Console redirect URI is preserved verbatim
    # (e.g. /api/youtube/oauth/callback) independent of `prefix`.

    def _make_override_callback(provider_name: str):
        async def _override_callback(
            request: Request,
            state: str = Query(...),
            code: str | None = Query(default=None),
            error: str | None = Query(default=None),
            redirect_uri: str = Query(...),
        ) -> dict:
            return await _run_callback(
                provider=provider_name,
                state=state,
                code=code,
                error=error,
                redirect_uri=redirect_uri,
            )

        return _override_callback

    for _provider_name, _abs_path in overrides.items():
        router.add_api_route(
            _abs_path,
            _make_override_callback(_provider_name),
            methods=["GET"],
            name=f"oauth_callback_{_provider_name}",
            tags=["OAuth"],
        )

    # ─── POST refresh ─────────────────────────────────────────────────────

    @router.post(f"{base}/{{provider}}/refresh")
    async def refresh(provider: str, body: dict) -> JSONResponse:
        """Refresh an access token. Body: `{"refresh_token": "..."}`.

        Returns a JSON shape mirroring `TokenSet`. On failure, returns
        a 502 with `{"error": "..."}` — refresh failures are
        consumer-actionable (re-prompt for consent), not silent.
        """
        impl = _resolve(provider)
        refresh_token = body.get("refresh_token")
        if not refresh_token or not isinstance(refresh_token, str):
            raise HTTPException(
                status_code=400, detail="missing or invalid refresh_token"
            )
        try:
            new_tokens = await impl.refresh(refresh_token)
        except Exception as exc:  # noqa: BLE001 — network/4xx → 502 with reason
            logger.warning(
                "oauth_router: refresh failed for provider=%s: %s", provider, exc
            )
            return JSONResponse(
                status_code=502,
                content={"error": f"refresh failed: {exc.__class__.__name__}"},
            )
        return JSONResponse(
            status_code=200,
            content={
                "access_token": new_tokens.access_token,
                "refresh_token": new_tokens.refresh_token,
                "expires_at": new_tokens.expires_at.isoformat(),
                "scope": new_tokens.scope,
            },
        )

    # ─── POST revoke ──────────────────────────────────────────────────────

    @router.post(f"{base}/{{provider}}/revoke")
    async def revoke(provider: str, body: dict) -> Response:
        """Revoke a token at the provider. Body: `{"token": "..."}`. 204 on success."""
        impl = _resolve(provider)
        token = body.get("token")
        if not token or not isinstance(token, str):
            raise HTTPException(status_code=400, detail="missing or invalid token")
        try:
            await impl.revoke(token)
        except Exception as exc:  # noqa: BLE001 — surface as 502, never 500
            logger.warning(
                "oauth_router: revoke failed for provider=%s: %s", provider, exc
            )
            return JSONResponse(
                status_code=502,
                content={"error": f"revoke failed: {exc.__class__.__name__}"},
            )
        return Response(status_code=204)

    return router


__all__ = ["oauth_router", "CallbackHook"]
