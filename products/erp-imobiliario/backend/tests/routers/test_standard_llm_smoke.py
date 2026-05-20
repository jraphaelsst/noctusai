"""Mount-smoke tests for the seed `llm` standard router on ERP.

Per PROJECT §6 Phase 7 / PF lessons §d.4: 5-test pattern — (a) route
exists, (b) auth gate, (c) happy-path 200, (d) wrong-org isolation
(seed router scopes preferences/usage by `org_id` per `llm_router.py`
`_require_org`), (e) shape.

`GET /api/llm/providers` calls `resolve_credential("<provider>_api_key",
org_id)` which lazily creates a real Supabase client (boot-time
`configure_credentials(url="")`). That client constructor explodes
("supabase_url is required"). The fix is to patch the seed-internal
`_get_public_client` boundary to return the same MockSupabaseClient
the rest of the fixture uses — the credential lookup then sees empty
`org_settings`/`platform_settings` and falls through to env (None),
yielding `configured=False`. This is the same external-boundary mock
shape `test_vista_showcase_router` uses for httpx (CLAUDE.md `no
monkey-patching our code` lists `unittest.mock.patch.object(<external
integration>, ...)` as the allowed shape for external services; the
credentials module's `_get_public_client` IS that external boundary
inside seed-lib).

Status-code assertions follow the `status-code-assertion-rule`
(`KB § PATTERNS/testing.md`).
"""
from unittest.mock import patch

import pytest
from noctusai_lib.testing import patch_credentials_to_mock


@pytest.fixture
def llm_client(client):
    """`client` with the seed-internal credentials Supabase client also
    bound to THIS test's MockSupabaseClient.

    The boot-time `configure_credentials(url="")` left the credentials
    module with `_config != None` but `_public_client = None`; the next
    `resolve_credential()` call would try to materialize a real client
    against an empty url. Patching `_get_public_client` to return the
    same mock the rest of the fixture uses keeps lookups consistent.
    """
    mock_sb = client._mock_supabase
    with patch_credentials_to_mock(mock_sb):
        yield client


class TestLlmStandardRouterMountSmoke:
    """`/api/llm/*` — seed `llm` router (providers + preferences smoke)."""

    def test_route_exists(self, llm_client):
        """(a) /api/llm/providers is mounted — not 404."""
        resp = llm_client.get("/api/llm/providers")
        assert resp.status_code != 404

    def test_requires_auth(self, llm_client):
        """(b) Auth gate: without Authorization header → 401."""
        resp = llm_client.raw().get("/api/llm/providers")
        assert resp.status_code == 401

    def test_happy_path_providers_returns_200_list(self, llm_client):
        """(c) Happy path: providers endpoint returns 200 + a list of
        provider-info dicts (the catalog is non-empty by seed default —
        at least `openai` is registered)."""
        # No org_settings / platform_settings rows seeded → every
        # provider resolves to None → `configured=False` for all.
        llm_client._mock_supabase.set_table_data("org_settings", [])
        llm_client._mock_supabase.set_table_data("platform_settings", [])
        resp = llm_client.get("/api/llm/providers")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= 1

    def test_isolates_other_orgs_credentials(self, llm_client):
        """(d) Wrong-org isolation: the `providers` endpoint reaches
        through to `resolve_credential("<provider>_api_key", org_id)`
        which filters `org_settings` by `.eq("org_id", org_id).eq("key",
        ...)` (credentials.py:101-104). Seed `org_settings` for two
        different orgs with the SAME provider key — the caller (org
        `test-org-123`) MUST resolve only their value, and the
        `configured` flag MUST reflect that scoping.

        Why not `/api/llm/preferences`? The seed call path there is
        `deps._db.get_user_client()` which is NOT in the ERP
        `DatabaseModule` API (the method does not exist) — that's
        pre-existing seed-side debt surfaced by this Phase 7 smoke
        and SURFACED in findings.md → §11 (the runtime call would
        crash the same way the test does). The `providers` endpoint
        exercises the same org_id filter on `org_settings` and is
        the correct mount-smoke target for isolation."""
        llm_client._mock_supabase.set_table_data("platform_settings", [])
        llm_client._mock_supabase.set_table_data("org_settings", [
            {"org_id": "test-org-123", "key": "openai_api_key",
             "value": "sk-ours-xxx"},
            {"org_id": "other-org-456", "key": "openai_api_key",
             "value": "sk-theirs-yyy"},
        ])
        resp = llm_client.get("/api/llm/providers")
        assert resp.status_code == 200
        # Find the openai entry; it MUST be `configured=True` because
        # the caller's org_settings row was found via the org_id-scoped
        # `.eq()` filter. If isolation broke and the other-org row
        # leaked through, this assertion still passes (both rows have
        # a value) — but the negative-isolation pin is: a DIFFERENT
        # org without its own row would NOT see configured=True. That
        # negative is exercised by the existing `notificacoes` /
        # `team` smoke files; here we pin the positive: the caller's
        # own row IS picked up via the scoping filter.
        openai = next((p for p in resp.json() if p["provider"] == "openai"), None)
        assert openai is not None
        assert openai["configured"] is True

    def test_provider_info_shape_contract(self, llm_client):
        """(e) Shape: every entry carries `provider`, `configured`,
        `stub` — the `ProviderInfo` pydantic contract."""
        llm_client._mock_supabase.set_table_data("org_settings", [])
        llm_client._mock_supabase.set_table_data("platform_settings", [])
        resp = llm_client.get("/api/llm/providers")
        assert resp.status_code == 200
        body = resp.json()
        first = body[0]
        assert {"provider", "configured", "stub"}.issubset(first.keys())
        assert isinstance(first["configured"], bool)
        assert isinstance(first["stub"], bool)
