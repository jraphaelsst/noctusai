"""Tests for the social-wiring Meta seam (post seed-consume migration).

The hand-rolled Meta fork was retired by
`social-wiring-meta-seed-consume` — the product now consumes the
canonical `noctusai_lib.integrations.meta` (Protocol + Fake + Real +
factory + mappers + OAuth helpers). The seed owns the deep contract
(mapper field maps, Graph error classification, OAuth token exchange,
scope discovery, system-user/user-OAuth auth resolution, Fake adapter)
and exercises it in
`seed/lib/backend/tests/integrations/meta/test_meta_integration.py`.
Duplicating those here would violate DRY.

These tests cover the **product-side seam** only:

1. `app.services.meta.get_meta_adapter` — the product-convention
   factory wrapper that adapts (`org_id`, `credential_store`,
   product `settings`) onto the seed factory and resolves the
   three-tier auth priority (system_user → user_oauth → Fake).
2. `META_PROVIDER` re-export (the credential-vault storage key).
3. The shim re-export surface the app imports rely on.
4. The two consumer projection helpers in `whatsapp_intake_service`
   that recover `attachments_summary` / insight `period` from the seed
   value objects (NEW product logic introduced by the migration).
"""
from __future__ import annotations

from uuid import uuid4

from app.services.meta import (
    META_PROVIDER,
    FacebookPage,
    FacebookPost,
    FakeMetaAdapter,
    InstagramAccount,
    InstagramMedia,
    MetaAdapter,
    MetaConnectionStatus,
    MetaGraphError,
    MetaOAuthAdapter,
    PostInsights,
    get_meta_adapter,
)


# ─── Product factory wrapper — auth resolution via the local call shape ──
class _Settings:
    """Minimal product-settings stand-in for the factory wrapper."""

    def __init__(
        self,
        *,
        system_user_token: str = "",
        app_id: str = "",
        app_secret: str = "",
        graph_version: str = "v21.0",
    ) -> None:
        self.meta_system_user_token = system_user_token
        self.meta_app_id = app_id
        self.meta_app_secret = app_secret
        self.meta_graph_api_version = graph_version


class _Stored:
    def __init__(self, access_token: str | None = "USER-OAUTH-TOKEN") -> None:
        self.tokens = {"access_token": access_token} if access_token else {}
        self.metadata: dict = {}


class _Store:
    """A `CredentialStore`-shaped fake — only `.get` is exercised."""

    def __init__(self, stored=None) -> None:
        self._stored = stored

    def get(self, org_id, provider):  # noqa: ARG002
        return self._stored


class TestProductFactoryWrapper:
    def test_no_credentials_falls_back_to_fake(self):
        adapter = get_meta_adapter(settings=_Settings())
        assert isinstance(adapter, FakeMetaAdapter)

    def test_no_credential_row_falls_back_to_fake(self):
        adapter = get_meta_adapter(
            org_id=uuid4(),
            credential_store=_Store(stored=None),
            settings=_Settings(app_id="x", app_secret="y"),
        )
        assert isinstance(adapter, FakeMetaAdapter)

    def test_system_user_token_selects_oauth_adapter(self):
        adapter = get_meta_adapter(
            settings=_Settings(system_user_token="SYS-TOKEN-123")
        )
        assert isinstance(adapter, MetaOAuthAdapter)
        assert adapter.auth_mode == "system_user"

    def test_system_user_token_wins_over_credential_store(self):
        adapter = get_meta_adapter(
            org_id=uuid4(),
            credential_store=_Store(stored=_Stored()),
            settings=_Settings(
                system_user_token="SYS-TOKEN", app_id="x", app_secret="y"
            ),
        )
        assert isinstance(adapter, MetaOAuthAdapter)
        assert adapter.auth_mode == "system_user"

    def test_user_oauth_credential_selects_oauth_adapter(self):
        adapter = get_meta_adapter(
            org_id=uuid4(),
            credential_store=_Store(stored=_Stored("USER-OAUTH-TOKEN")),
            settings=_Settings(app_id="x", app_secret="y"),
        )
        assert isinstance(adapter, MetaOAuthAdapter)
        assert adapter.auth_mode == "user_oauth"

    def test_uuid_org_id_is_stringified_for_the_resolver(self):
        captured: dict = {}

        class _CapturingStore:
            def get(self, org_id, provider):  # noqa: ARG002
                captured["org_id"] = org_id
                return _Stored("USER-OAUTH-TOKEN")

        org = uuid4()
        get_meta_adapter(
            org_id=org,
            credential_store=_CapturingStore(),
            settings=_Settings(app_id="x", app_secret="y"),
        )._user_token()
        # The seed resolver does `store.get(org_id, provider)`; the
        # product wrapper must pass the UUID as a string (the vault keys
        # on str) — never the bare UUID object.
        assert captured["org_id"] == str(org)
        assert isinstance(captured["org_id"], str)


# ─── Re-export surface the app imports rely on ───────────────────────────
class TestShimSurface:
    def test_meta_provider_is_the_vault_key(self):
        assert META_PROVIDER == "meta"

    def test_value_objects_and_adapters_reexported(self):
        # These must remain importable from `app.services.meta` so the
        # existing consumers (meta_router, whatsapp_intake) keep working.
        assert FacebookPage is not None
        assert FacebookPost is not None
        assert InstagramAccount is not None
        assert InstagramMedia is not None
        assert PostInsights is not None
        assert MetaConnectionStatus is not None
        assert MetaGraphError is not None
        assert issubclass(MetaOAuthAdapter, object)

    def test_metaadapter_protocol_is_seed_protocol(self):
        from noctusai_lib.integrations.meta import MetaAdapter as SeedMetaAdapter

        assert MetaAdapter is SeedMetaAdapter


# ─── Consumer projection helpers (new product logic from the migration) ──
class TestConsumerProjectionHelpers:
    def test_attachments_summary_prefers_title_then_description_then_type(self):
        from app.services.whatsapp_intake_service import _meta_attachments_summary

        attachments = [
            {"title": "Vista da varanda", "type": "photo"},
            {"description": "Sem titulo", "type": "video"},
            {"type": "video_inline"},
            {},  # all-empty → dropped
        ]
        assert _meta_attachments_summary(attachments) == [
            "Vista da varanda",
            "Sem titulo",
            "video_inline",
        ]

    def test_attachments_summary_empty_and_none(self):
        from app.services.whatsapp_intake_service import _meta_attachments_summary

        assert _meta_attachments_summary(None) == []
        assert _meta_attachments_summary([]) == []
        assert _meta_attachments_summary(["not-a-dict"]) == []

    def test_insights_period_reads_first_raw_row(self):
        from app.services.whatsapp_intake_service import _meta_insights_period

        insights = PostInsights(
            object_id="111_222",
            metrics={"post_impressions": 1234},
            raw=[{"name": "post_impressions", "period": "day"}],
        )
        assert _meta_insights_period(insights) == "day"

    def test_insights_period_defaults_to_lifetime(self):
        from app.services.whatsapp_intake_service import _meta_insights_period

        # No raw rows / no period key → the documented default.
        assert _meta_insights_period(PostInsights(object_id="x")) == "lifetime"
        assert (
            _meta_insights_period(
                PostInsights(object_id="x", raw=[{"name": "m"}])
            )
            == "lifetime"
        )


# ─── Fake adapter sanity through the product seam ────────────────────────
class TestFakeAdapterThroughSeam:
    def test_seeded_pages_and_posts_roundtrip(self):
        adapter = FakeMetaAdapter()
        adapter.seed(
            pages=[
                FacebookPage(
                    id="111",
                    name="Imobiliaria One",
                    category="Real Estate",
                    access_token="P",
                ),
            ],
            posts_by_page={
                "111": [
                    FacebookPost(id="111_222", message="Novo imovel", likes=12),
                ]
            },
        )
        pages = adapter.list_facebook_pages()
        assert pages[0].id == "111"
        posts = adapter.list_facebook_posts("111", limit=10)
        assert posts[0].likes == 12
        assert adapter.list_facebook_posts("999") == []
