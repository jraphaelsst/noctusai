"""Platform grants (Julia-line CONTRACT D1-D4): ``/api/studio/plataforma/grants``.

The seed Fakes carry the IO (``FakeGrantDelivery``, ``FakeProductTokenAdmin`` with the grant's STRICT scope
allow-list, ``FakeCredentialStore``); the side effects are asserted on their WRITES (token rows in both schemas,
the stored tools secret, the delivery calls) -- never on a status code alone."""
from __future__ import annotations

import logging
from uuid import UUID, uuid4

import pytest

from app.channels.token_audit import FakeTokenAudit
from app.dependencies import (
    get_auth_context,
    get_grant_delivery_dep,
    get_grant_store_dep,
    get_grant_token_admin_dep,
    get_grant_tools_store_factory_dep,
    get_org_directory_dep,
    get_token_audit_dep,
)
from app.grants.orgs import FakeOrgDirectory, OrgRef
from app.grants.registry import GRANT_CHANNEL_SCOPES, GRANT_TOKEN_SCOPES
from app.grants.store import FakeGrantStore
from app.routers.studio_agents_router import get_studio_definition_store_dep
from app.stores.studio_definitions import FakeStudioDefinitionStore
from noctusai_lib.api.auth.grants import FakeGrantDelivery
from noctusai_lib.api.auth.session import (
    GRANT_RECEIVE_SCOPE,
    AuthContext,
    FakeProductTokenAdmin,
    UnknownTokenScopeError,
)
from noctusai_lib.security import FakeCredentialStore
from noctusai_lib.security.api_keys import read_local_api_key
from noctusai_lib.testing import handler_status
from tests.routers.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID

URL = "/api/studio/plataforma/grants"
TARGET_ORG = uuid4()
OTHER_ORG = uuid4()
TOOLS_NAME = "social_wiring_lais_tools_token"


class Kit:
    """The Fakes one test shares, plus read helpers over what they recorded."""

    def __init__(self) -> None:
        self.grants = FakeGrantStore()
        self.admin = FakeProductTokenAdmin(GRANT_TOKEN_SCOPES)
        self.delivery = FakeGrantDelivery()
        self.tools = FakeCredentialStore()
        self.audit = FakeTokenAudit()
        self.orgs = FakeOrgDirectory([
            OrgRef(TARGET_ORG, "Imobiliária Alfa", "alfa"), OrgRef(OTHER_ORG, "Beta Imóveis", "beta"),
        ])
        self.studio = FakeStudioDefinitionStore()

    def live(self, schema: str) -> list[dict]:
        return [r for r in self.admin.rows.get(schema, []) if not r.get("revoked_at")]

    def all(self, schema: str) -> list[dict]:
        return self.admin.rows.get(schema, [])

    def tools_secret(self, org: UUID) -> str | None:
        stored = read_local_api_key(self.tools, str(org), TOOLS_NAME)
        return (stored.tokens or {}).get("value") if stored else None


@pytest.fixture
def kit(agents_client):
    from app.main import app

    k = Kit()
    for org in (TARGET_ORG, OTHER_ORG):
        k.studio.create_studio_agent(org, "julia", "Julia", None, runtime="llm", owner_product="social-wiring")
    overrides = {
        get_grant_store_dep: lambda: k.grants,
        get_grant_token_admin_dep: lambda: k.admin,
        get_grant_delivery_dep: lambda: k.delivery,
        get_grant_tools_store_factory_dep: lambda: (lambda: k.tools),
        get_org_directory_dep: lambda: k.orgs,
        get_token_audit_dep: lambda: k.audit,
        get_studio_definition_store_dep: lambda: k.studio,
    }
    app.dependency_overrides.update(overrides)
    agents_client.kit = k
    try:
        yield agents_client
    finally:
        for dep in overrides:
            app.dependency_overrides.pop(dep, None)


def _platform_admin(client) -> None:
    client.mock_supabase.set_table_data("noctus_users", [{
        "id": str(DEFAULT_USER_ID), "org_id": str(DEFAULT_ORG_ID), "role": "admin", "org_role": "owner"}])


def _body(**kw):
    return {"agent_key": "julia", "product": "social-wiring", "org_id": str(TARGET_ORG), **kw}


def _create(client, **kw):
    return client.post(URL, json=_body(**kw))


def _all_values(obj) -> str:
    return " ".join(str(v) for v in obj.values())


def assert_no_secret_in(k: Kit, *haystacks: str) -> None:
    """Planted-secret check: every real secret the Fakes saw (delivered credentials, delivery tokens, the stored
    tools secrets) is absent from the given response text and from every field value of it."""
    secrets = {c.payload.credential for c in k.delivery.calls if c.method == "PUT"}
    secrets |= {c.delivery_token for c in k.delivery.calls}
    secrets |= {sec for org in (TARGET_ORG, OTHER_ORG) if (sec := k.tools_secret(org))}
    assert secrets, "no secret was planted: the assertion would be vacuous"
    for secret in secrets:
        for hay in haystacks:
            assert secret not in hay


class TestBoundary:
    ROUTES = [
        ("get", URL, None), ("get", f"{URL}/opcoes", None), ("post", URL, _body()),
        ("post", f"{URL}/{uuid4()}/rotate", None), ("delete", f"{URL}/{uuid4()}", None),
    ]

    @pytest.mark.parametrize("method,path,body", ROUTES)
    def test_no_credential_is_401(self, kit, method, path, body):
        kwargs = {"json": body} if body is not None else {}
        assert getattr(kit.raw(), method)(path, **kwargs).status_code == 401

    @pytest.mark.parametrize("method,path,body", ROUTES)
    def test_org_owner_is_not_a_platform_admin_403(self, kit, method, path, body):
        kit.mock_supabase.set_table_data("noctus_users", [{
            "id": str(DEFAULT_USER_ID), "org_id": str(DEFAULT_ORG_ID), "role": "user", "org_role": "owner"}])
        kwargs = {"json": body} if body is not None else {}
        resp = getattr(kit, method)(path, **kwargs)
        assert resp.status_code == 403
        assert resp.json()["code"] == "platform_admin_required"
        assert kit.kit.all("agents") == [] and kit.kit.delivery.calls == []

    @pytest.mark.parametrize("method,path,body", ROUTES)
    def test_product_token_caller_403(self, kit, method, path, body):
        from app.main import app

        app.dependency_overrides[get_auth_context] = lambda: AuthContext(
            org_id=DEFAULT_ORG_ID, caller_kind="product", user_id=None, scopes=["*"],
            raw_token="x", api_token_id=UUID(int=1),
        )
        try:
            kwargs = {"json": body} if body is not None else {}
            resp = getattr(kit.raw(), method)(path, **kwargs)
        finally:
            app.dependency_overrides.pop(get_auth_context, None)
        assert resp.status_code == 403
        assert kit.kit.all("agents") == []


class TestCreate:
    def test_happy_path_mints_both_tokens_delivers_and_spends_the_delivery_token(self, kit, caplog):
        _platform_admin(kit)
        caplog.set_level(logging.DEBUG)
        resp = _create(kit)
        assert resp.status_code == 201, resp.text
        out = resp.json()
        assert out["status"] == "ativo" and out["agent_key"] == "julia" and out["product"] == "social-wiring"
        assert out["org_id"] == str(TARGET_ORG) and out["org_nome"] == "Imobiliária Alfa"
        assert out["expires_at"] is None and out["last_error"] is None and out["last_delivered_at"]
        k = kit.kit
        agent = k.studio.get_agent(TARGET_ORG, "julia")
        # 1. channel token: target org, transport issuer, the grant's scopes, bound to the org's instance, no expiry
        (channel,) = k.live("agents")
        assert channel["org_id"] == str(TARGET_ORG) and channel["issuer"] == "social-wiring"
        assert set(channel["scopes"]) == set(GRANT_CHANNEL_SCOPES) == {
            "agents:channel-turn", "agents:channel-status", "agents:channel-specs"}
        assert channel["principal_agent_id"] == str(agent.id) and channel["expires_at"] is None
        assert channel["id"] == out["channel_token_id"]
        # 2. tools token in the PRODUCT schema; its secret is kept in agents' per-org store
        (tools,) = k.live("social_wiring")
        assert tools["issuer"] == "agents" and tools["scopes"] == ["social-wiring:lais-tools"]
        assert tools["id"] == out["product_token_id"] and tools["org_id"] == str(TARGET_ORG)
        secret = k.tools_secret(TARGET_ORG)
        assert secret and secret.startswith("noc_") and k.admin.find_by_secret("social_wiring", secret).id == UUID(tools["id"])
        assert k.tools_secret(OTHER_ORG) is None
        # 3-5. one PUT to the product with the channel credential; the 5-minute delivery token was minted AND revoked
        (call,) = k.delivery.calls
        assert (call.method, call.product_slug, call.issuer) == ("PUT", "social-wiring", "agents")
        assert call.payload.agent_id == str(agent.id) and call.payload.credential.startswith("noc_")
        assert k.admin.find_by_secret("agents", call.payload.credential).id == UUID(channel["id"])
        delivery_row = k.admin.find_by_secret("social_wiring", call.delivery_token)
        assert list(delivery_row.scopes) == [GRANT_RECEIVE_SCOPE] and delivery_row.revoked_at is not None
        assert 0 < (delivery_row.expires_at - delivery_row.created_at).total_seconds() <= 300
        assert call.payload.metadata["grant_id"] == out["id"] and call.payload.metadata["agent_key"] == "julia"
        # audit: the channel mint is on the trail, with the acting platform admin
        assert [(r.method, r.api_token_id) for r in k.audit.rows][:1] == [("MINT", UUID(channel["id"]))]
        # a secret is never in a response body or a log line
        for s in (secret, call.payload.credential, call.delivery_token):
            assert s not in resp.text and s not in caplog.text
        # the response carries the stored prefix (what the UI shows), a strict prefix of the real credential
        assert out["token_prefix"] == channel["token_prefix"]
        assert call.payload.credential.startswith(out["token_prefix"]) and out["token_prefix"] != call.payload.credential
        assert_no_secret_in(k, resp.text, _all_values(out))

    def test_optional_expiry_applies_to_the_tokens(self, kit):
        _platform_admin(kit)
        resp = _create(kit, expira_em_dias=30)
        assert resp.status_code == 201, resp.text
        assert resp.json()["expires_at"]
        (channel,) = kit.kit.live("agents")
        assert channel["expires_at"]

    def test_a_second_live_grant_for_the_triple_is_409_and_mints_nothing(self, kit):
        _platform_admin(kit)
        assert _create(kit).status_code == 201
        before = (len(kit.kit.all("agents")), len(kit.kit.all("social_wiring")), len(kit.kit.delivery.calls))
        resp = _create(kit)
        assert resp.status_code == 409 and resp.json()["code"] == "grant_exists"
        assert (len(kit.kit.all("agents")), len(kit.kit.all("social_wiring")), len(kit.kit.delivery.calls)) == before
        # a different org is a different triple
        assert _create(kit, org_id=str(OTHER_ORG)).status_code == 201

    def test_delivery_failure_revokes_everything_and_marks_the_grant_falhou(self, kit, caplog):
        _platform_admin(kit)
        caplog.set_level(logging.DEBUG)
        kit.kit.delivery.fail_deliver = True
        resp = _create(kit)
        assert handler_status(resp) == 502 and resp.json()["code"] == "delivery_failed"
        k = kit.kit
        assert k.live("agents") == [] and k.live("social_wiring") == []
        assert len(k.all("agents")) == 1 and len(k.all("social_wiring")) == 2  # minted, then all revoked
        assert k.tools_secret(TARGET_ORG) is None  # the stored tools secret is gone with its token
        (grant,) = k.grants.list()
        assert grant.status == "falhou" and grant.last_error.startswith("deliver: GrantDeliveryError")
        assert "noc_" not in grant.last_error
        for row in k.all("agents") + k.all("social_wiring"):
            assert row["token_prefix"] not in grant.last_error
        # the failed grant does not block a retry
        k.delivery.fail_deliver = False
        assert _create(kit).status_code == 201

    def test_a_failure_restores_the_previously_stored_tools_secret(self, kit):
        from noctusai_lib.security.api_keys import put_api_key

        _platform_admin(kit)
        put_api_key(kit.kit.tools, str(TARGET_ORG), TOOLS_NAME, "noc_previous")
        kit.kit.delivery.fail_deliver = True
        assert handler_status(_create(kit)) == 502
        assert kit.kit.tools_secret(TARGET_ORG) == "noc_previous"

    @pytest.mark.parametrize("nth,stage_code", [(1, "mint_failed"), (2, "mint_failed"), (3, "mint_failed")])
    def test_a_mint_failure_midway_revokes_what_was_minted(self, kit, nth, stage_code):
        """The channel token (1st), the tools token (2nd) or the delivery token (3rd) fails to mint."""
        _platform_admin(kit)
        k = kit.kit
        real_mint, calls = k.admin.mint, []

        class _Flaky(FakeProductTokenAdmin):
            pass

        flaky = _Flaky(GRANT_TOKEN_SCOPES)
        flaky.rows = k.admin.rows

        def mint(*a, **kw):
            calls.append(1)
            if len(calls) == nth:
                raise RuntimeError("boom")
            return FakeProductTokenAdmin.mint(flaky, *a, **kw)

        flaky.mint = mint  # the DI seam's own double, not product code
        from app.main import app

        app.dependency_overrides[get_grant_token_admin_dep] = lambda: flaky
        resp = _create(kit)
        assert handler_status(resp) == 502 and resp.json()["code"] == stage_code
        assert k.live("agents") == [] and k.live("social_wiring") == []
        assert k.delivery.calls == []
        (grant,) = k.grants.list()
        assert grant.status == "falhou" and "RuntimeError" in grant.last_error
        assert k.tools_secret(TARGET_ORG) is None

    def test_the_scope_allow_list_is_strict(self):
        admin = FakeProductTokenAdmin(GRANT_TOKEN_SCOPES)
        with pytest.raises(UnknownTokenScopeError):
            admin.mint("agents", org_id=TARGET_ORG, label="x", scopes=["agents:everything"], expires_at=None)

    @pytest.mark.parametrize("body,status_,code", [
        ({"product": "nope"}, 422, "product_unknown"),
        ({"agent_key": "bia"}, 422, "agent_not_grantable"),
        ({"org_id": str(uuid4())}, 404, "org_not_found"),
    ])
    def test_unknown_product_agent_or_org_mints_nothing(self, kit, body, status_, code):
        _platform_admin(kit)
        resp = _create(kit, **body)
        assert resp.status_code == status_ and resp.json()["code"] == code
        assert kit.kit.all("agents") == [] and kit.kit.grants.list() == []

    def test_unknown_fields_and_bad_shape_are_422(self, kit):
        _platform_admin(kit)
        assert kit.post(URL, json={**_body(), "scopes": ["x"]}).status_code == 422
        assert kit.post(URL, json={**_body(), "org_id": "not-a-uuid"}).status_code == 422
        assert kit.post(URL, json={"product": "social-wiring"}).status_code == 422


class TestRotate:
    def test_rotation_overlaps_new_pair_delivered_before_the_old_is_revoked(self, kit):
        _platform_admin(kit)
        grant = _create(kit).json()
        k = kit.kit
        old_secret = k.tools_secret(TARGET_ORG)
        resp = kit.post(f"{URL}/{grant['id']}/rotate")
        assert resp.status_code == 200, resp.text
        out = resp.json()
        assert out["status"] == "ativo" and out["id"] == grant["id"]
        assert out["channel_token_id"] != grant["channel_token_id"] and out["product_token_id"] != grant["product_token_id"]
        # exactly one live pair afterwards, and it is the NEW one; the old one is revoked
        (channel,) = k.live("agents")
        (tools,) = k.live("social_wiring")
        assert channel["id"] == out["channel_token_id"] and tools["id"] == out["product_token_id"]
        old = next(r for r in k.all("agents") if r["id"] == grant["channel_token_id"])
        assert old["revoked_at"]
        # two PUTs were delivered: the second carries the NEW channel credential (the product now holds it)
        puts = [c for c in k.delivery.calls if c.method == "PUT"]
        assert len(puts) == 2 and puts[0].payload.credential != puts[1].payload.credential
        assert k.admin.find_by_secret("agents", puts[1].payload.credential).id == UUID(out["channel_token_id"])
        assert k.admin.find_by_secret("agents", puts[0].payload.credential).revoked_at is not None
        assert out["token_prefix"] == channel["token_prefix"] and puts[1].payload.credential.startswith(out["token_prefix"])
        assert_no_secret_in(k, resp.text, _all_values(out))
        new_secret = k.tools_secret(TARGET_ORG)
        assert new_secret != old_secret and k.admin.find_by_secret("social_wiring", new_secret).id == UUID(out["product_token_id"])

    def test_a_failed_rotation_keeps_the_old_pair_live_and_revokes_the_new(self, kit):
        _platform_admin(kit)
        grant = _create(kit).json()
        k = kit.kit
        old_secret = k.tools_secret(TARGET_ORG)
        k.delivery.fail_deliver = True
        resp = kit.post(f"{URL}/{grant['id']}/rotate")
        assert handler_status(resp) == 502 and resp.json()["code"] == "delivery_failed"
        assert [r["id"] for r in k.live("agents")] == [grant["channel_token_id"]]
        assert [r["id"] for r in k.live("social_wiring")] == [grant["product_token_id"]]
        assert k.tools_secret(TARGET_ORG) == old_secret
        stored = k.grants.get(UUID(grant["id"]))
        assert stored.status == "ativo" and stored.last_error.startswith("deliver:")
        assert stored.channel_token_id == UUID(grant["channel_token_id"])

    def test_only_an_active_grant_rotates(self, kit):
        _platform_admin(kit)
        grant = _create(kit).json()
        assert kit.delete(f"{URL}/{grant['id']}").status_code == 204
        resp = kit.post(f"{URL}/{grant['id']}/rotate")
        assert resp.status_code == 409 and resp.json()["code"] == "grant_not_active"
        assert kit.post(f"{URL}/{uuid4()}/rotate").status_code == 404


class TestRevoke:
    def test_revoke_kills_both_tokens_the_stored_secret_and_tells_the_product(self, kit):
        _platform_admin(kit)
        grant = _create(kit).json()
        k = kit.kit
        resp = kit.delete(f"{URL}/{grant['id']}")
        assert resp.status_code == 204 and resp.content == b""
        assert k.live("agents") == [] and k.live("social_wiring") == []
        assert k.tools_secret(TARGET_ORG) is None
        stored = k.grants.get(UUID(grant["id"]))
        assert stored.status == "revogado" and stored.revoked_at and stored.revoked_by == DEFAULT_USER_ID
        (delete,) = [c for c in k.delivery.calls if c.method == "DELETE"]
        assert (delete.product_slug, delete.issuer) == ("social-wiring", "agents")
        assert k.admin.find_by_secret("social_wiring", delete.delivery_token).revoked_at is not None  # also spent
        assert [r.method for r in k.audit.rows] == ["MINT", "REVOKE"]
        # idempotent, and the triple is free again
        assert kit.delete(f"{URL}/{grant['id']}").status_code == 204
        assert _create(kit).status_code == 201

    def test_the_product_being_down_does_not_fail_the_revoke(self, kit):
        _platform_admin(kit)
        grant = _create(kit).json()
        kit.kit.delivery.fail_revoke = True
        assert kit.delete(f"{URL}/{grant['id']}").status_code == 204
        assert kit.kit.live("agents") == [] and kit.kit.live("social_wiring") == []

    def test_a_token_that_cannot_be_revoked_is_a_502_and_the_grant_stays_active(self, kit):
        _platform_admin(kit)
        grant = _create(kit).json()
        kit.kit.admin.fail_revoke = True
        resp = kit.delete(f"{URL}/{grant['id']}")
        assert handler_status(resp) == 502 and resp.json()["code"] == "revoke_failed"
        stored = kit.kit.grants.get(UUID(grant["id"]))
        assert stored.status == "ativo" and "revogação incompleta" in stored.last_error

    def test_unknown_grant_is_404(self, kit):
        _platform_admin(kit)
        assert kit.delete(f"{URL}/{uuid4()}").status_code == 404


class TestListAndOptions:
    def test_list_newest_first_with_org_names_and_no_secret(self, kit):
        _platform_admin(kit)
        first = _create(kit).json()
        second = _create(kit, org_id=str(OTHER_ORG)).json()
        resp = kit.get(URL)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2 and [i["id"] for i in body["items"]] == [second["id"], first["id"]]
        assert {i["org_nome"] for i in body["items"]} == {"Imobiliária Alfa", "Beta Imóveis"}
        assert "secret" not in resp.text and "token_hash" not in resp.text
        # the prefix (stored, non-secret) is carried for every grant; no field holds a full secret
        by_id = {i["id"]: i for i in body["items"]}
        for g in (first, second):
            row = next(r for r in kit.kit.all("agents") if r["id"] == g["channel_token_id"])
            assert by_id[g["id"]]["token_prefix"] == row["token_prefix"] and row["token_prefix"].startswith("noc_")
        assert_no_secret_in(kit.kit, resp.text, *[_all_values(i) for i in body["items"]])

    def test_options_list_the_server_registry_and_search_orgs(self, kit):
        _platform_admin(kit)
        body = kit.get(f"{URL}/opcoes").json()
        assert body["produtos"] == [
            {"slug": "assistant", "label": "Assistant", "agent_keys": ["assistente-pessoal"]},
            {"slug": "social-wiring", "label": "Social Wiring", "agent_keys": ["julia"]},
        ]
        assert {o["nome"] for o in body["orgs"]} == {"Imobiliária Alfa", "Beta Imóveis"}
        found = kit.get(f"{URL}/opcoes", params={"q": "beta"}).json()["orgs"]
        assert [o["id"] for o in found] == [str(OTHER_ORG)]
        assert kit.get(f"{URL}/opcoes", params={"limit": 1000}).status_code == 422


class TestAssistantGrant:
    """`assistente-pessoal` -> `assistant`: the product only RECEIVES the channel token, so no tools token is minted, stored
    or revoked -- and the channel token carries the `assistant` issuer the channel gate allows."""

    @pytest.fixture
    def assistant(self, kit):
        _platform_admin(kit)
        kit.kit.studio.create_studio_agent(
            TARGET_ORG, "assistente-pessoal", "Assistente", None, runtime="llm", owner_product="assistant")
        return kit

    def _grant(self, client, **kw):
        return client.post(URL, json={"agent_key": "assistente-pessoal", "product": "assistant", "org_id": str(TARGET_ORG), **kw})

    def test_create_mints_only_the_channel_token_and_delivers_it(self, assistant):
        resp = self._grant(assistant)
        assert resp.status_code == 201, resp.text
        out = resp.json()
        k = assistant.kit
        assert out["status"] == "ativo" and out["product_token_id"] is None
        (channel,) = k.live("agents")
        assert channel["issuer"] == "assistant" and channel["id"] == out["channel_token_id"]
        assert channel["principal_agent_id"] == str(k.studio.get_agent(TARGET_ORG, "assistente-pessoal").id)
        assert k.tools_secret(TARGET_ORG) is None
        # only the (spent) delivery token lives in the product schema: no standing credential is left there
        assert [r for r in k.live("assistant")] == []
        (call,) = k.delivery.calls
        assert (call.method, call.product_slug, call.issuer) == ("PUT", "assistant", "agents")
        assert call.payload.metadata["agent_key"] == "assistente-pessoal" and call.payload.credential.startswith("noc_")
        assert k.admin.find_by_secret("agents", call.payload.credential).id == UUID(channel["id"])
        assert call.payload.credential not in resp.text

    def test_rotate_and_revoke_work_without_a_tools_token(self, assistant):
        grant = self._grant(assistant).json()
        k = assistant.kit
        rotated = assistant.post(f"{URL}/{grant['id']}/rotate")
        assert rotated.status_code == 200, rotated.text
        out = rotated.json()
        assert out["channel_token_id"] != grant["channel_token_id"] and out["product_token_id"] is None
        (channel,) = k.live("agents")
        assert channel["id"] == out["channel_token_id"]
        assert assistant.delete(f"{URL}/{grant['id']}").status_code == 204
        assert k.live("agents") == [] and k.grants.get(UUID(grant["id"])).status == "revogado"
        assert [c.method for c in k.delivery.calls] == ["PUT", "PUT", "DELETE"]
        assert k.delivery.calls[-1].product_slug == "assistant"

    def test_a_second_agent_cannot_be_granted_to_the_assistant(self, assistant):
        resp = assistant.post(URL, json={"agent_key": "julia", "product": "assistant", "org_id": str(TARGET_ORG)})
        assert resp.status_code == 422 and resp.json()["code"] == "agent_not_grantable"
        assert assistant.kit.all("agents") == []
