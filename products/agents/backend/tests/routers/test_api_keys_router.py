"""``/api/settings/api-keys*`` — the org's LLM provider keys (Lais A1, B1).

Auth boundary: strict ``== 401`` (never ``in (401, 404|422)``). Writes are
admin-only through the trusted ``noctus_users`` role; the status screen reports
THIS org's key only (never the platform's tier-0 Anthropic override).
"""
from __future__ import annotations

import httpx
import pytest
from cryptography.fernet import Fernet

from noctusai_lib.config import credentials as seed_credentials

from app.config import settings
from app.credentials.api_key_testers import make_llm_key_testers
from noctusai_lib.testing.clients import TEST_USER_ID
from tests.routers.conftest import DEFAULT_ORG_ID


def seed_org_role(client, *, role: str) -> None:
    """The legacy `get_current_user_org` (what the seed api-keys router takes)
    looks the trusted `noctus_users` row up by the RAW user id — unlike
    `require_*`, which maps it through uuid5 — so seed that shape."""
    client.mock_supabase.set_table_data(
        "noctus_users",
        [{"id": TEST_USER_ID, "org_id": str(DEFAULT_ORG_ID), "org_role": role}],
    )

BASE = "/api/settings/api-keys"
ROUTES = [
    ("GET", BASE, None),
    ("PUT", f"{BASE}/openai_api_key", {"value": "sk-x"}),
    ("DELETE", f"{BASE}/openai_api_key", None),
    ("POST", f"{BASE}/openai_api_key/test", None),
]


def _call(client, method, path, body):
    return client.request(method, path, json=body) if body is not None else client.request(method, path)


@pytest.fixture
def encrypted(monkeypatch):
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())


class TestAuthBoundary:
    @pytest.mark.parametrize("method,path,body", ROUTES)
    def test_no_credential_is_401(self, agents_client, method, path, body):
        assert _call(agents_client.raw(), method, path, body).status_code == 401


class TestStatusAndWrites:
    def test_member_lists_both_provider_keys_unconfigured(self, agents_client):
        seed_org_role(agents_client, role="member")
        resp = agents_client.get(BASE)
        assert resp.status_code == 200, resp.text
        items = {i["key"]: i for i in resp.json()["items"]}
        assert set(items) == {"openai_api_key", "anthropic_api_key"}
        assert all(not i["configured"] for i in items.values())
        assert all(i["testable"] for i in items.values())

    def test_platform_tier0_anthropic_override_is_not_reported_as_the_orgs_key(self, agents_client):
        """`studio/wiring.py` registers a tier-0 override that answers
        `anthropic_api_key` platform-wide; the screen must still say this org
        has none (the runtime would fail closed, B1)."""
        seed_credentials.register_credential_override(
            lambda key, org: "sk-ant-PLATFORM" if key == "anthropic_api_key" else None
        )
        try:
            seed_org_role(agents_client, role="owner")
            items = {i["key"]: i for i in agents_client.get(BASE).json()["items"]}
            assert items["anthropic_api_key"]["configured"] is False
        finally:
            seed_credentials.register_credential_override(None)

    def test_member_cannot_write_403(self, agents_client, encrypted):
        seed_org_role(agents_client, role="member")
        resp = agents_client.put(f"{BASE}/openai_api_key", json={"value": "sk-x"})
        assert resp.status_code == 403
        assert resp.json()["code"] == "admin_obrigatorio"

    def test_admin_writes_the_org_key_and_the_status_shows_it_masked(self, agents_client, encrypted):
        seed_org_role(agents_client, role="owner")
        resp = agents_client.put(f"{BASE}/openai_api_key", json={"value": "sk-secret-1234"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["configured"] is True and body["source"] == "local"
        assert body["hint"] == "...1234" and "sk-secret" not in resp.text
        listed = {i["key"]: i for i in agents_client.get(BASE).json()["items"]}
        assert listed["openai_api_key"]["configured"] is True
        assert listed["anthropic_api_key"]["configured"] is False

    def test_unknown_key_404(self, agents_client, encrypted):
        seed_org_role(agents_client, role="owner")
        assert agents_client.put(f"{BASE}/not_a_key", json={"value": "x"}).status_code == 404

    def test_admin_write_without_an_encryption_key_is_503_never_plaintext(self, agents_client, monkeypatch):
        monkeypatch.setattr(settings, "encryption_key", "")
        seed_org_role(agents_client, role="owner")
        assert agents_client.put(f"{BASE}/openai_api_key", json={"value": "sk-x"}).status_code == 503

    def test_post_test_for_a_key_the_org_never_set_is_422(self, agents_client, encrypted):
        seed_org_role(agents_client, role="owner")
        resp = agents_client.post(f"{BASE}/openai_api_key/test")
        assert resp.status_code == 422


class TestKeyProbes:
    @staticmethod
    def _factory(status_code):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"], seen["headers"] = str(request.url), dict(request.headers)
            return httpx.Response(status_code, json={"data": []})

        return (lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))), seen

    @pytest.mark.asyncio
    async def test_openai_ok_uses_a_free_models_call_with_the_orgs_key(self):
        factory, seen = self._factory(200)
        result = await make_llm_key_testers(http_client_factory=factory)["openai_api_key"]("sk-org")
        assert result.success and seen["url"].startswith("https://api.openai.com/v1/models")
        assert seen["headers"]["authorization"] == "Bearer sk-org"

    @pytest.mark.asyncio
    async def test_anthropic_401_is_a_clear_failure(self):
        factory, seen = self._factory(401)
        result = await make_llm_key_testers(http_client_factory=factory)["anthropic_api_key"]("bad")
        assert not result.success and "inválida" in result.message
        assert seen["headers"]["x-api-key"] == "bad"
