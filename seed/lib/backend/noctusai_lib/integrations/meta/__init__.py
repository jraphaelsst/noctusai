"""Meta (Facebook + Instagram) Graph API adapter — canonical
Protocol + Fake + Real(OAuth, dual-auth) + factory + introspection seam.

Lifted into seed 2026-05-16 by `projects/social-wiring-absorption/`
Wave 1.E4 from the live-validated `noctusai-youtube-crawler`
`feat/meta-integrations` + `integration/oauth-discovery` branches
(end-to-end validated against a real One Consultoria FB Page + IG
account). Sibling to `google_calendar/`, `google_maps/`,
`google_drive/`, `vista/`. First Meta-side surface in noc.

**What ships:**
- Value objects: `FacebookPage`, `InstagramAccount`, `FacebookPost`,
  `InstagramMedia`, `PostInsights`, `MetaConnectionStatus`,
  `PublishedPost`, `PublishedMedia`, `MediaProcessingStatus`,
  `AdCampaign`, `AdInsights`.
- Contract: `MetaAdapter` (Protocol) — read surface + write/ads
  surface (publish FB post / IG media / IG carousel / IG Reel /
  FB video+Reel / list ad campaigns / ad insights). Video / Reel
  publish uses the asynchronous resumable-upload + processing-status
  poll contract (`poll_media_status`), distinct from the synchronous
  image flow but with the same typed error model.
- `FakeMetaAdapter` — deterministic in-memory; dev/test default.
- `MetaOAuthAdapter` — live Graph, **dual auth**: System User Token
  (production; required for Business-Portfolio-owned assets) →
  OAuth credential-store fallback (end-user path). `auth_mode`
  discriminator surfaced on `status()`.
- `MetaCredentialResolver` Protocol + `OAuthMetaCredentials` —
  product-injected per-tenant OAuth token lookup (mirrors
  `CalendarCredentialResolver`).
- Pure mappers + `parse_graph_datetime` (handles `+0000` offset).
- `MetaGraphError` (`is_auth_error` / `is_rate_limited`).
- Scope auto-discovery: `META_KITCHEN_SINK_SCOPES`,
  `resolve_oauth_scopes`, `discover_app_permissions`.
- `make_meta_router(...)` — `/api/meta/{status,scopes}` seam.

**Default factory** (`get_meta_adapter`): selection priority
`system_user` → `user_oauth` → `Fake`:
- `system_user_token` set → `MetaOAuthAdapter` (`auth_mode="system_user"`).
  No `org_id` / resolver needed (token is workspace-global).
- resolver present AND `resolver.get_credentials(org_id)` non-None →
  `MetaOAuthAdapter` (`auth_mode="user_oauth"`).
- neither → `FakeMetaAdapter` (safe dev/test fallback).

Posting (FB Page post, IG publish) and ads (campaign listing + ad
insights) **SHIP** — added additively to the Protocol + Real + Fake;
pre-existing read-only callers are unaffected. **Production needs the
write scopes (`pages_manage_posts`, `instagram_content_publish`) and
ads scopes (`ads_read`) approved through Meta App Review**: when the
active token lacks a gated scope the live adapter raises
`MetaGraphError` with `requires_app_review` true — never a silent or
faked success. The App Review is a deployment-activation gate, not a
reason to defer the code (mirrors `youtube.upload_video` shipping
real code behind a credential gate). Full ads *management* (campaign
create / update) is a separate follow-up. TikTok + webhook
subscriptions are separate future modules (`integrations/tiktok/`,
`integrations/meta/webhooks/`).

OAuth start/callback is the generic `noctusai_lib.security.oauth`
router's job (consumed as-is — this package does not duplicate the
dance; it ships only the read-only introspection seam).
"""

from noctusai_lib.integrations.meta._meta_api import (
    META_KITCHEN_SINK_SCOPES,
    MetaGraphError,
    discover_app_permissions,
    exchange_code_for_token,
    exchange_for_long_lived,
    poll_media_status, resolve_oauth_scopes,
)
from noctusai_lib.integrations.meta.credentials import (
    MetaCredentialResolver,
    OAuthMetaCredentials,
)
from noctusai_lib.integrations.meta.fake_adapter import FakeMetaAdapter
from noctusai_lib.integrations.meta.mappers import (
    ig_account_from_body,
    ig_media_from_body,
    insights_from_body,
    page_from_body,
    parse_graph_datetime,
    post_from_body,
)
from noctusai_lib.integrations.meta.router import make_meta_router
from noctusai_lib.integrations.meta.types import (
    AdCampaign,
    AdInsights,
    FacebookPage,
    FacebookPost,
    InstagramAccount,
    InstagramMedia,
    MediaProcessingStatus, MetaAdapter,
    MetaConnectionStatus,
    PostInsights,
    PublishedMedia,
    PublishedPost,
)


def get_meta_adapter(
    *,
    system_user_token: str | None = None,
    resolver: MetaCredentialResolver | None = None,
    credential_store=None,
    org_id: str | None = None,
    graph_version: str | None = None,
) -> MetaAdapter:
    """Return a Meta adapter wired per the auth-resolution priority.

    Priority: System User Token (production; workspace-global) →
    OAuth credential store (end-user) → `FakeMetaAdapter` (dev/test).

    `system_user_token` — when set, the adapter runs in `system_user`
    mode and needs no `org_id`/`resolver` (the token is workspace
    global, one System User serves every consumer).

    `resolver` + `org_id` — the user-OAuth fallback; the adapter
    resolves the stored long-lived token per tenant. The adapter is
    still constructed (so `status()` can report a useful error) but
    falls back to `FakeMetaAdapter` only when there is NEITHER a
    System User Token NOR a resolver.

    `credential_store` + `org_id` — the convenience path: pass a
    `noctusai_lib.security.token_store.CredentialStore` directly and
    the factory builds a `CredentialStoreMetaResolver` internally (no
    per-product resolver bridge). Ignored when `resolver` is given.
    """

    from noctusai_lib.integrations.meta._meta_api import DEFAULT_GRAPH_VERSION, poll_media_status
    from noctusai_lib.integrations.meta.oauth_adapter import MetaOAuthAdapter

    version = graph_version or DEFAULT_GRAPH_VERSION

    if resolver is None and credential_store is not None:
        from noctusai_lib.integrations.credential_resolvers import (
            CredentialStoreMetaResolver,
        )

        resolver = CredentialStoreMetaResolver(credential_store)

    if system_user_token:
        return MetaOAuthAdapter(
            system_user_token=system_user_token, graph_version=version
        )
    if resolver is not None:
        return MetaOAuthAdapter(
            resolver=resolver, org_id=org_id, graph_version=version
        )
    return FakeMetaAdapter()


__all__ = [
    "AdCampaign",
    "AdInsights",
    "FacebookPage",
    "FacebookPost",
    "FakeMetaAdapter",
    "InstagramAccount",
    "InstagramMedia",
    "META_KITCHEN_SINK_SCOPES",
    "MediaProcessingStatus", "MetaAdapter",
    "MetaConnectionStatus",
    "MetaCredentialResolver",
    "MetaGraphError",
    "OAuthMetaCredentials",
    "PostInsights",
    "PublishedMedia",
    "PublishedPost",
    "discover_app_permissions",
    "exchange_code_for_token",
    "exchange_for_long_lived",
    "get_meta_adapter",
    "ig_account_from_body",
    "ig_media_from_body",
    "insights_from_body",
    "make_meta_router",
    "page_from_body",
    "parse_graph_datetime",
    "post_from_body",
    "poll_media_status", "resolve_oauth_scopes",
]
