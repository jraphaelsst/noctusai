"""Unified cross-provider OAuth scope resolution — Protocol + Fake + Real + factory.

WHY this module
---------------
`integrations.google_scopes` (`resolve_google_scopes`,
`discover_granted_scopes`, `diagnose_consent_screen_gaps`) and
`integrations.meta._meta_api` (`resolve_oauth_scopes`,
`discover_app_permissions`) each ship a per-provider scope surface with
*differently-named module functions*. A consumer wiring N providers had
to learn N call shapes. This module introduces ONE `ScopeResolver`
Protocol both providers satisfy.

It **reconciles, it does not re-implement** — the Google + Meta Real
impls delegate to the already-shipped per-provider functions; the scope
catalog stays single-sourced in `integrations/`.

Provider-shaped, not generic
----------------------------
Scope auto-discovery differs structurally: Meta exposes
`GET /{app-id}/permissions` (an app-side scope-list endpoint), Google
does NOT. The Protocol encodes this with
`list_app_scopes() -> list[str] | None` — Google's Real impl returns
`None` ("no discovery endpoint, defaults are authoritative"), Meta's
returns the Graph permission list (or `None` in pure dev mode).

Layer placement
---------------
`noctusai_lib.security.oauth` already owns the cross-provider OAuth
surface (`OAuthProvider` Protocol + `GoogleProvider` + `oauth_router` +
`make_oauth_provider`). Scope resolution is an auth-layer concern, not a
vendor adapter, so the unifying Protocol sits beside the dance here
rather than in a new `integrations/oauth/` package. `security` importing
`integrations` introduces no cycle (`integrations/` does not import
`security/`); it mirrors how `GoogleProvider` was itself lifted from a
vendor adapter into this auth package.

Seed-fake-real shape
--------------------
`discover_granted` (Google `oauth2/v3/tokeninfo`) and `list_app_scopes`
(Meta `/{app-id}/permissions`) touch provider HTTP — this IS an IO seam,
so it ships Protocol + Fake + Real + factory per
`KB § PATTERNS/seed-fake-real-adapter.md`. `FakeScopeResolver` is
deterministic + network-free for tests / FakeMode.

Filed in `projects/oauth-integrations-seed-lift/` (residual gap 1 of 3).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from noctusai_lib.integrations.google_scopes import (
    GOOGLE_KITCHEN_SINK_SCOPES,
    diagnose_consent_screen_gaps,
    discover_granted_scopes,
    resolve_google_scopes,
)
from noctusai_lib.integrations.meta._meta_api import (
    META_KITCHEN_SINK_SCOPES,
    discover_app_permissions,
    resolve_oauth_scopes,
)


@runtime_checkable
class ScopeResolver(Protocol):
    """One scope-resolution contract every OAuth provider satisfies.

    Four methods, uniform across providers; provider-shaped differences
    (Google has no app-scope endpoint) are encoded in the *return type*
    of `list_app_scopes`, not in differently-named functions.
    """

    @property
    def provider(self) -> str:
        """Stable provider identifier (e.g. `"google"`, `"meta"`)."""
        ...

    def resolve(self, configured: str | None) -> list[str]:
        """Resolve a configured scope env value to a concrete list.

        `"auto"`/empty → kitchen-sink (or discovered, for Meta);
        explicit → parsed verbatim. Order-stable, deduped.
        """
        ...

    def list_app_scopes(self) -> list[str] | None:
        """The scopes the *app itself* is configured/approved for, when
        the provider exposes an app-side scope catalog.

        Meta → `GET /{app-id}/permissions` (list, or `None` in pure dev
        mode). Google → always `None`: Google exposes NO app-scope
        endpoint, so the in-code kitchen-sink is authoritative. `None`
        means "no discovery, defaults are the source of truth".
        """
        ...

    def discover_granted(self, access_token: str) -> list[str]:
        """The scopes the user *actually granted* post-consent — the
        ground truth from the provider's token-introspection endpoint.
        Returns `[]` when unknown (never raises into the caller).
        """
        ...

    def diagnose(
        self, requested: list[str], granted: list[str]
    ) -> dict:
        """Set-diff requested vs granted → operator coverage report
        (`coverage_pct`, `missing`, `extra`). Provider-agnostic math.
        """
        ...


# ─── Real impls — delegate to the already-shipped per-provider fns ────────


class GoogleScopeResolver:
    """Google `ScopeResolver` — delegates to `integrations.google_scopes`.

    `list_app_scopes()` returns `None`: Google exposes no app-side
    scope-list endpoint (the in-code kitchen-sink is authoritative).
    `discover_granted` probes `oauth2/v3/tokeninfo`.
    """

    def __init__(self, *, kitchen_sink: list[str] | None = None) -> None:
        self._kitchen_sink = kitchen_sink

    @property
    def provider(self) -> str:
        return "google"

    def resolve(self, configured: str | None) -> list[str]:
        return resolve_google_scopes(
            configured, kitchen_sink=self._kitchen_sink
        )

    def list_app_scopes(self) -> list[str] | None:
        # Google has NO app-scope endpoint — defaults are authoritative.
        return None

    def discover_granted(self, access_token: str) -> list[str]:
        return discover_granted_scopes(access_token)

    def diagnose(
        self, requested: list[str], granted: list[str]
    ) -> dict:
        return diagnose_consent_screen_gaps(requested, granted)


class MetaScopeResolver:
    """Meta `ScopeResolver` — delegates to `integrations.meta._meta_api`.

    `list_app_scopes()` queries `GET /{app-id}/permissions` with the App
    Access Token (`{app_id}|{app_secret}`); returns `None` in pure dev
    mode (nothing submitted for review) or on Graph failure.
    `discover_granted` reuses the same coverage math as Google for the
    operator-facing report.
    """

    def __init__(
        self,
        *,
        app_id: str | None = None,
        app_secret: str | None = None,
    ) -> None:
        self._app_id = app_id
        self._app_secret = app_secret

    @property
    def provider(self) -> str:
        return "meta"

    def resolve(self, configured: str | None) -> list[str]:
        return resolve_oauth_scopes(
            configured=configured,
            app_id=self._app_id,
            app_secret=self._app_secret,
        )

    def list_app_scopes(self) -> list[str] | None:
        if not (self._app_id and self._app_secret):
            return None
        return discover_app_permissions(
            app_id=self._app_id, app_secret=self._app_secret
        )

    def discover_granted(self, access_token: str) -> list[str]:
        # Meta's granted-scope probe is `GET /me/permissions`, surfaced
        # by `make_meta_router` `/api/meta/scopes`. The resolver does
        # not own that HTTP call (the introspection router does); from
        # the resolver's seat the post-consent ground truth arrives via
        # the caller. Returning [] = "unknown from here" (no raise).
        return []

    def diagnose(
        self, requested: list[str], granted: list[str]
    ) -> dict:
        # Coverage math is provider-agnostic — reuse the Google impl
        # (single source of truth for the set-diff report shape).
        return diagnose_consent_screen_gaps(requested, granted)


# ─── Fake — deterministic, network-free (tests / FakeMode) ────────────────


class FakeScopeResolver:
    """Deterministic `ScopeResolver` for tests + FakeMode.

    No network. `resolve` honours the `"auto"`/explicit contract against
    an injected scope list; `list_app_scopes` returns whatever was
    seeded (default `None`, the Google-shaped case); `discover_granted`
    returns the seeded granted list; `diagnose` reuses the real
    provider-agnostic coverage math (so the Fake exercises the same
    report shape the Real does).
    """

    def __init__(
        self,
        *,
        provider: str = "fake",
        kitchen_sink: list[str] | None = None,
        app_scopes: list[str] | None = None,
        granted: list[str] | None = None,
    ) -> None:
        self._provider = provider
        self._kitchen_sink = kitchen_sink or ["scope.a", "scope.b"]
        self._app_scopes = app_scopes
        self._granted = granted or []

    @property
    def provider(self) -> str:
        return self._provider

    def resolve(self, configured: str | None) -> list[str]:
        raw = (configured or "").strip()
        if not raw or raw.lower() == "auto":
            return list(self._kitchen_sink)
        parts: list[str] = []
        for chunk in raw.split(","):
            parts.extend(chunk.split())
        seen: set[str] = set()
        out: list[str] = []
        for p in parts:
            if p and p not in seen:
                seen.add(p)
                out.append(p)
        return out

    def list_app_scopes(self) -> list[str] | None:
        return self._app_scopes

    def discover_granted(self, access_token: str) -> list[str]:
        return list(self._granted)

    def diagnose(
        self, requested: list[str], granted: list[str]
    ) -> dict:
        return diagnose_consent_screen_gaps(requested, granted)


# ─── Factory — single seam for provider selection ─────────────────────────


def make_scope_resolver(
    provider: str,
    *,
    use_fake: bool = False,
    kitchen_sink: list[str] | None = None,
    app_id: str | None = None,
    app_secret: str | None = None,
) -> ScopeResolver:
    """Resolve a provider name to a concrete `ScopeResolver`.

    Args:
        provider: `"google"` or `"meta"`. Unknown → `ValueError`
            (unless `use_fake=True`).
        use_fake: short-circuit to `FakeScopeResolver` regardless of
            provider (tests / FakeMode); works for any name by design.
        kitchen_sink: Google scope-list override (per-product extension
            point — a product also needing Gmail passes its own list).
        app_id / app_secret: Meta App credentials for `list_app_scopes`
            discovery (`GET /{app-id}/permissions`).

    Returns:
        A `ScopeResolver`.

    Raises:
        ValueError: unknown provider when `use_fake=False`.
    """
    if use_fake:
        return FakeScopeResolver(provider=provider, kitchen_sink=kitchen_sink)
    if provider == "google":
        return GoogleScopeResolver(kitchen_sink=kitchen_sink)
    if provider == "meta":
        return MetaScopeResolver(app_id=app_id, app_secret=app_secret)
    raise ValueError(f"unknown scope-resolver provider: {provider}")


__all__ = [
    "FakeScopeResolver",
    "GOOGLE_KITCHEN_SINK_SCOPES",
    "GoogleScopeResolver",
    "META_KITCHEN_SINK_SCOPES",
    "MetaScopeResolver",
    "ScopeResolver",
    "make_scope_resolver",
]
