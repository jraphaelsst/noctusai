"""The platform grant that wires an org to `agents` (KB § PATTERNS/backend/platform-grants.md): the receiver sink, the strict
auth boundary of the grant route, and the live reply reading the STORED grant (token + agent key) instead of env.
Fakes only: the seed Fake credential store, FakeAgentsClient, FakeWahaClient. The delivery token is a planted `AuthContext`."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.api.auth.session import GRANT_RECEIVE_SCOPE, AuthContext
from noctusai_lib.integrations.agents_channel import FakeAgentsClient, HttpAgentsClient
from noctusai_lib.security import FakeCredentialStore
from noctusai_lib.testing.migrations import migration_sql

from app.auth_context import get_auth_context
from app.live import registro as r
from app.live.wiring import agents_for
from app.services import agents_grant
from tests.live.test_resposta import NUMERO, Ctl, Reg, _build, _msg

ROOT = Path(__file__).resolve().parents[1]
ORG = uuid4()
OTHER_ORG = uuid4()
URL = "/api/platform/grants/agents"
SECRET = "noc_" + "ab12cd34" * 8
BODY = {
    "credential": SECRET, "agent_id": str(uuid4()),
    "metadata": {"grant_id": str(uuid4()), "agent_key": "assistente-pessoal", "token_prefix": SECRET[:12],
                 "scopes": ["agents:channel-turn"], "expires_at": None},
}


def _delivery(**kw) -> AuthContext:
    base = dict(org_id=ORG, caller_kind="product", user_id=None, scopes=[GRANT_RECEIVE_SCOPE], raw_token="noc_deliver",
                api_token_id=uuid4(), issuer="agents")
    base.update(kw)
    return AuthContext(**base)


@pytest.fixture
def store():
    s = FakeCredentialStore()
    agents_grant.configure_grant_store(lambda: s)
    yield s
    agents_grant.configure_grant_store(None)


@pytest.fixture
def http(store):
    from app.main import app

    yield TestClient(app), app
    app.dependency_overrides.pop(get_auth_context, None)


def _as(app, ctx):
    app.dependency_overrides[get_auth_context] = lambda: ctx


# ── the receiver: strict 401 without a valid delivery token, 403 for the wrong caller ─────────────────────────────
class TestBoundary:
    @pytest.mark.parametrize("method", ["put", "delete"])
    def test_no_credential_is_strict_401(self, http, store, method):
        client, _ = http
        kwargs = {"json": BODY} if method == "put" else {}
        assert getattr(client, method)(URL, **kwargs).status_code == 401
        assert store.list_providers(str(ORG)) == []

    @pytest.mark.parametrize("bearer", ["not-a-token", "eyJhbGciOiJIUzI1NiJ9.e30.sig", "noc_" + "0" * 64])
    def test_an_unknown_or_jwt_bearer_is_strict_401(self, http, store, bearer, monkeypatch):
        client, _ = http
        # an unknown `noc_` token reaches the resolver: make it answer "no such token" (no DB in unit tests)
        from app import auth_context

        class _Nobody:
            async def resolve(self, _secret):
                return None

        monkeypatch.setattr(auth_context, "_resolver", _Nobody())
        assert client.put(URL, json=BODY, headers={"Authorization": f"Bearer {bearer}"}).status_code == 401
        assert store.list_providers(str(ORG)) == []

    @pytest.mark.parametrize("ctx,code", [
        (_delivery(scopes=["agents:channel-turn"]), "scope_missing"),
        (_delivery(issuer="social-wiring"), "issuer_not_allowed"),
        (_delivery(caller_kind="user", user_id=uuid4()), "product_required"),
    ])
    def test_wrong_token_is_403_and_stores_nothing(self, http, store, ctx, code):
        client, app = http
        _as(app, ctx)
        for resp in (client.put(URL, json=BODY), client.delete(URL)):
            assert resp.status_code == 403 and code in resp.text
        assert store.list_providers(str(ORG)) == []

    def test_another_issuer_in_the_path_is_403(self, http, store):
        client, app = http
        _as(app, _delivery())
        assert client.put("/api/platform/grants/social-wiring", json=BODY).status_code == 403

    def test_a_body_org_id_is_422_the_org_comes_from_the_token(self, http, store):
        client, app = http
        _as(app, _delivery())
        resp = client.put(URL, json={**BODY, "org_id": str(OTHER_ORG)})
        assert resp.status_code == 422 and SECRET not in resp.text
        assert store.list_providers(str(OTHER_ORG)) == [] and store.list_providers(str(ORG)) == []


# ── the sink: accept, replace, revoke ──────────────────────────────────────────────────────────────────────────
class TestSink:
    def test_put_stores_the_credential_for_the_token_org_with_its_metadata(self, http, store, caplog):
        client, app = http
        _as(app, _delivery())
        caplog.set_level(logging.DEBUG)
        resp = client.put(URL, json=BODY)
        assert resp.status_code == 204 and resp.content == b""
        row = store.get(str(ORG), "agents")
        assert row.tokens == {"value": SECRET}
        assert row.metadata["agent_key"] == "assistente-pessoal" and row.metadata["token_prefix"] == SECRET[:12]
        assert row.metadata["agent_id"] == BODY["agent_id"] and row.metadata["grant_id"] == BODY["metadata"]["grant_id"]
        assert SECRET not in json.dumps(row.metadata)  # the secret never rides in the plaintext metadata
        assert store.list_providers(str(OTHER_ORG)) == []
        assert SECRET not in caplog.text and SECRET not in resp.text

    def test_a_regrant_replaces_the_credential(self, http, store):
        client, app = http
        _as(app, _delivery())
        client.put(URL, json=BODY)
        new = "noc_" + "ef56" * 16
        assert client.put(URL, json={**BODY, "credential": new}).status_code == 204
        assert store.get(str(ORG), "agents").tokens == {"value": new}

    def test_delete_drops_it_and_is_idempotent(self, http, store):
        client, app = http
        _as(app, _delivery())
        client.put(URL, json=BODY)
        assert client.delete(URL).status_code == 204
        assert store.get(str(ORG), "agents") is None
        assert client.delete(URL).status_code == 204

    def test_a_store_failure_is_a_500_that_leaks_nothing(self, http, caplog):
        client, app = http

        class _Boom:
            def put(self, *a, **k):
                raise RuntimeError(f"db down {SECRET}")

        agents_grant.configure_grant_store(lambda: _Boom())
        try:
            _as(app, _delivery())
            resp = client.put(URL, json=BODY)
        finally:
            agents_grant.configure_grant_store(None)
        assert resp.status_code == 500 and SECRET not in resp.text

    def test_the_real_store_is_the_fernet_credential_store_on_agent_grants(self, monkeypatch):
        from cryptography.fernet import Fernet
        from noctusai_lib.security.token_store.supabase_store import SupabaseCredentialStore

        monkeypatch.setattr(agents_grant.settings, "encryption_key", Fernet.generate_key().decode())
        monkeypatch.setattr("app.dependencies.get_admin_client", lambda: object())
        real = agents_grant._store()
        assert isinstance(real, SupabaseCredentialStore) and real._table == "agent_grants"

    def test_without_an_encryption_key_nothing_is_stored_in_plaintext(self, monkeypatch):
        from noctusai_lib.security.api_keys import EncryptionNotConfigured

        monkeypatch.setattr(agents_grant.settings, "encryption_key", "")
        with pytest.raises(EncryptionNotConfigured):
            agents_grant._store()


# ── what the live reply resolves from the grant ───────────────────────────────────────────────────────────────────
def _put(store, org=ORG, *, token=SECRET, agent_key="assistente-pessoal", expires_at=None):
    store.put(str(org), "agents", {"value": token}, metadata={"agent_key": agent_key, "expires_at": expires_at})


class TestAcesso:
    @pytest.fixture(autouse=True)
    def _url(self, monkeypatch):
        monkeypatch.setenv("PRODUCT_URL_AGENTS", "https://agents.internal/")

    def test_a_live_grant_gives_a_real_client_with_the_stored_token_and_the_granted_agent(self, store):
        _put(store)
        acesso = agents_grant.acesso_do_org(ORG)
        assert acesso.agent_key == "assistente-pessoal" and isinstance(acesso.client, HttpAgentsClient)
        assert acesso.client._token == SECRET and str(acesso.client._base_url).rstrip("/") == "https://agents.internal"

    def test_one_orgs_grant_never_answers_for_another(self, store):
        _put(store)
        assert agents_grant.acesso_do_org(OTHER_ORG) is None

    @pytest.mark.parametrize("kw", [{"token": ""}, {"agent_key": ""}, {"expires_at": "2020-01-01T00:00:00+00:00"},
                                    {"expires_at": "not-a-date"}])
    def test_an_unusable_grant_is_no_access(self, store, kw):
        _put(store, **kw)
        assert agents_grant.acesso_do_org(ORG) is None

    def test_no_agents_url_is_no_access_never_a_fake(self, store, monkeypatch):
        monkeypatch.delenv("PRODUCT_URL_AGENTS")
        monkeypatch.delenv("PRODUCT_URL_PATTERN", raising=False)
        _put(store)
        assert agents_grant.acesso_do_org(ORG) is None

    def test_an_unreadable_store_raises_it_is_not_no_grant(self):
        class _Boom:
            def get(self, *a):
                raise RuntimeError("decrypt")

        with pytest.raises(RuntimeError):
            agents_grant.acesso_do_org(ORG, store=_Boom())


# ── the live reply uses the STORED grant ──────────────────────────────────────────────────────────────────────────
class TestLiveReplyUsesTheGrant:
    @pytest.fixture(autouse=True)
    def _url(self, monkeypatch):
        monkeypatch.setenv("PRODUCT_URL_AGENTS", "https://agents.internal")

    def _run(self, rep, msg):
        return asyncio.run(rep.responder(ORG, uuid4(), msg))

    def test_the_turn_carries_the_granted_agent_key_and_is_sent_with_the_granted_token(self, store, monkeypatch, caplog):
        _put(store, agent_key="agente-da-grant")
        made = []
        fake = Ctl(lista=[])

        def _make(*, token, base_url, allow_fake):
            made.append((token, base_url, allow_fake))
            return fake

        monkeypatch.setattr(agents_grant, "make_agents_client", _make)
        caplog.set_level(logging.DEBUG)
        rep, waha, reg = _build(None, agents_for=agents_for)
        assert self._run(rep, _msg()) == r.ENVIADA
        assert made == [(SECRET, "https://agents.internal", False)]  # allow_fake=False: never a scripted fake
        assert [t.agent_key for t in fake.turns] == ["agente-da-grant"]
        assert fake.ctl_calls == 1 and len(waha.sent_messages) == 1
        assert SECRET not in caplog.text and SECRET not in json.dumps(reg.eventos, default=str)

    def test_an_org_without_a_grant_is_answered_by_nobody_one_declared_event(self, store, caplog):
        caplog.set_level(logging.DEBUG)
        rep, waha, reg = _build(None, agents_for=agents_for)
        assert self._run(rep, _msg()) == r.ERRO_TURNO
        assert waha.sent_messages == []
        assert [(e["desfecho"], e["motivo"]) for e in reg.eventos] == [(r.ERRO_TURNO, "sem_grant_agents")]

    def test_a_revoked_grant_stops_the_reply_at_once(self, store, monkeypatch):
        _put(store)
        monkeypatch.setattr(agents_grant, "make_agents_client", lambda **_: Ctl(lista=[]))
        rep, waha, reg = _build(None, agents_for=agents_for)
        assert self._run(rep, _msg()) == r.ENVIADA
        agents_grant.on_revoke(SimpleNamespace(org_id=ORG, issuer="agents"))
        assert self._run(rep, _msg()) == r.ERRO_TURNO and len(waha.sent_messages) == 1
        assert reg.eventos[-1]["motivo"] == "sem_grant_agents"

    def test_an_unreadable_grant_is_an_error_event_not_a_silent_skip(self, monkeypatch):
        class _Boom:
            def get(self, *a):
                raise RuntimeError(f"decrypt {SECRET}")

        agents_grant.configure_grant_store(lambda: _Boom())
        try:
            rep, waha, reg = _build(None, agents_for=agents_for)
            assert self._run(rep, _msg()) == r.ERRO_TURNO
        finally:
            agents_grant.configure_grant_store(None)
        assert waha.sent_messages == [] and reg.eventos[-1]["motivo"].startswith("grant_ilegivel")
        assert SECRET not in json.dumps(reg.eventos, default=str)

    def test_the_owner_message_forwarder_needs_a_live_grant(self, store, monkeypatch, caplog):
        from app.services.humano_para_agente import build_human_forwarder

        class _Spy(FakeAgentsClient):
            called = False

            async def buscar_thread(self, **kw):
                _Spy.called = True
                return None

        monkeypatch.setattr(agents_grant, "make_agents_client", lambda **_: _Spy())
        fwd = build_human_forwarder(agents_for=agents_for, owner_user_id=lambda *_: "u1", identity_key=lambda: "k", enabled=lambda: True)
        msg = _msg(from_me=True)
        asyncio.run(fwd(ORG, uuid4(), SimpleNamespace(), msg))
        assert _Spy.called is False  # no grant: nothing is sent to agents
        _put(store)
        asyncio.run(fwd(ORG, uuid4(), SimpleNamespace(), msg))
        assert _Spy.called is True


# ── the migration ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_migration_023_is_service_role_only_encrypted_and_has_append_only_events():
    sql = migration_sql(ROOT, "agents_grant")
    for table in ("api_tokens", "agent_grants", "agent_grants_eventos"):
        assert f"COMMENT ON TABLE assistant.{table} IS 'tier:service';" in sql
        assert f"ALTER TABLE assistant.{table} ENABLE ROW LEVEL SECURITY;" in sql
        assert f"REVOKE ALL ON assistant.{table} FROM PUBLIC, anon, authenticated;" in sql
    assert "TO authenticated" not in sql
    assert "encrypted_tokens text NOT NULL" in sql and "provider = 'agents'" in sql
    assert "'concedido', 'rotacionado', 'revogado'" in sql
    assert "guard_agent_grants_eventos_append_only" in sql and "AFTER INSERT OR UPDATE OR DELETE ON assistant.agent_grants" in sql
    assert "expires_at          timestamptz," in sql  # a grant token may have no expiry


def test_the_agents_credential_is_not_env_config():
    from app.config import SeedSettings

    for gone in ("assistant_agents_token", "assistant_agent_key", "assistant_agents_base_url"):
        assert gone not in SeedSettings.model_fields
