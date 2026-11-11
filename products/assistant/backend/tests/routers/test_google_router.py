"""The Google connection (D50): admin-only routes (strict 401 / 403), the signed single-use callback, tokens never
leaving the backend, disconnect that revokes, and the proof endpoint over the seed Fakes (no live Google calls)."""
from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest

from noctusai_lib.integrations.google_calendar import EventInput, FakeCalendarAdapter
from noctusai_lib.integrations.google_drive.fake_reader import FakeDriveReader
from noctusai_lib.security.oauth import FakeOAuthProvider, FakeOAuthStateStore, TokenSet
from noctusai_lib.security.token_store import FakeCredentialStore

from app.routers import google_router as gr
from app.services import google_connection as gc

ORG = "00000000-0000-0000-0000-0000000000a1"
HOST = "https://assistant.example.test"
ADMIN_ROUTES = [
    ("get", "/api/google/status"),
    ("post", "/api/google/connect/start"),
    ("post", "/api/google/disconnect"),
    ("get", "/api/google/prova"),
]
ACCESS, REFRESH = "ya29.SECRET-ACCESS", "1//SECRET-REFRESH"


def _id_token(email: str) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).rstrip(b"=").decode()
    return f"h.{body}.s"


def _tokens(scopes=None, refresh=REFRESH) -> TokenSet:
    return TokenSet(
        access_token=ACCESS, refresh_token=refresh, expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scope=list(scopes if scopes is not None else gc.ASSISTANT_GOOGLE_SCOPES),
        raw={"id_token": _id_token("dono@example.com")},
    )


class _RevokeFails(FakeOAuthProvider):
    async def revoke(self, token: str) -> None:
        raise RuntimeError("network down")


class _FailingPut(FakeCredentialStore):
    def put(self, *a, **k):
        raise RuntimeError("db down")


class _Clients:
    def __init__(self, calendar, drive) -> None:
        self._calendar, self._drive = calendar, drive

    def calendar(self, org_id):
        if isinstance(self._calendar, Exception):
            raise self._calendar
        return self._calendar

    def drive(self, org_id):
        if isinstance(self._drive, Exception):
            raise self._drive
        return self._drive


class RefreshError(Exception):  # same class name google.auth raises for a dead refresh token
    pass


@pytest.fixture(autouse=True)
def _product_url(monkeypatch):
    monkeypatch.setenv("PRODUCT_URL_ASSISTANT", HOST)
    monkeypatch.delenv("GOOGLE_OAUTH_REDIRECT_URI", raising=False)


@pytest.fixture
def world(client):
    """Seed Fakes behind the router's seams; the caller is an org admin."""
    from app.main import app

    w = type("W", (), {})()
    w.provider = FakeOAuthProvider(name="google", use_pkce=True, predetermined_tokens=_tokens())
    w.states, w.store = FakeOAuthStateStore(), FakeCredentialStore()
    w.is_admin, w.nonce, w.removed = True, None, []

    def _remove(org, actor):
        w.removed.append((org, actor))
        w.store.delete(org, gc.STORE_PROVIDER)

    cal = FakeCalendarAdapter()
    base = datetime.now(timezone.utc) + timedelta(days=1)
    for i in range(7):  # 7 events: the proof must cut at 5
        cal.create_event("primary", EventInput(summary=f"Reunião {i}", start_at=base + timedelta(hours=i),
                                               end_at=base + timedelta(hours=i, minutes=30), timezone="UTC"))
    drive = FakeDriveReader()
    for i in range(7):
        drive.add_file(f"f{i}", f"Planilha {i}", b"conteudo-privado", modified_time=f"2026-11-0{i + 1}T10:00:00Z")
    w.clients = _Clients(cal, drive)
    w.app, w.client = app, client
    app.dependency_overrides.update({
        gr.require_org_admin: lambda: (type("U", (), {"id": "user-1"})(), "t", ORG),
        gr.get_provider: lambda: w.provider,
        gr.get_state_store: lambda: w.states,
        gr.get_credential_store: lambda: w.store,
        gr.get_google_clients: lambda: w.clients,
        gr.get_membership_checker: lambda: (lambda user_id, org_id: w.is_admin),
        gr.get_grant_remover: lambda: _remove,
    })
    yield w
    for dep in (gr.require_org_admin, gr.get_provider, gr.get_state_store, gr.get_credential_store, gr.get_google_clients,
                gr.get_membership_checker, gr.get_grant_remover):
        app.dependency_overrides.pop(dep, None)


COOKIE = "__Host-ast_goauth"


def _start(w) -> str:
    resp = w.client.post("/api/google/connect/start")
    assert resp.status_code == 200
    w.nonce = resp.cookies.get(COOKIE) or resp.headers["set-cookie"].split(";")[0].split("=", 1)[1]
    return parse_qs(urlsplit(resp.json()["url"]).query)["state"][0]


def _callback(w, cookie="browser", **params):
    """`cookie`: 'browser' = the cookie connect/start set; None = no cookie; any other string = that cookie value."""
    value = w.nonce if cookie == "browser" else cookie
    headers = {"Cookie": f"{COOKIE}={value}"} if value else {}
    return w.client.raw().get("/api/google/oauth/callback", params=params, headers=headers, follow_redirects=False)


def _connect(w, scopes=None, refresh=REFRESH) -> None:
    w.provider = FakeOAuthProvider(name="google", use_pkce=True, predetermined_tokens=_tokens(scopes, refresh))
    assert _callback(w, state=_start(w), code="c1").headers["location"].endswith("google=conectado")


# ----- access -----
@pytest.mark.parametrize("metodo,rota", ADMIN_ROUTES)
def test_unauthenticated_is_strictly_401(client, metodo, rota):
    assert getattr(client.raw(), metodo)(rota).status_code == 401


@pytest.mark.parametrize("metodo,rota", ADMIN_ROUTES)
def test_a_member_who_is_not_an_org_admin_is_403(client, metodo, rota):
    assert getattr(client, metodo)(rota).status_code == 403


def test_the_callback_is_not_session_gated_but_refuses_an_unknown_state(world):
    # reachable without a session (Google redirects the bare browser) -- and useless without an issued state
    raw = world.client.raw()
    assert raw.get("/api/google/oauth/callback", params={"state": "forged", "code": "x"}).status_code == 400
    assert raw.get("/api/google/oauth/callback").status_code == 422


# ----- scopes: least privilege -----
def test_scopes_are_exactly_the_least_privilege_set_and_never_gmail_or_full_drive():
    s = gc.ASSISTANT_GOOGLE_SCOPES
    assert gc.SCOPE_CALENDAR in s and gc.SCOPE_DRIVE_READ in s and gc.SCOPE_DRIVE_FILE in s
    assert not any("gmail" in x for x in s)
    for broad in ("https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/drive"):
        assert broad not in s


def test_connect_start_asks_google_with_pkce_state_and_exactly_those_scopes(world):
    url = world.client.post("/api/google/connect/start").json()["url"]
    q = parse_qs(urlsplit(url).query)
    assert q["scope"][0].split() == gc.ASSISTANT_GOOGLE_SCOPES
    assert q["redirect_uri"] == [f"{HOST}/api/google/oauth/callback"]
    assert q["code_challenge_method"] == ["S256"] and q["state"][0] != "pending" and len(q["state"][0]) >= 40


# ----- callback: state / CSRF / redirect -----
def test_state_mismatch_is_refused_and_stores_nothing(world):
    assert _callback(world, state="not-issued", code="c1").status_code == 400
    assert world.store.get(ORG, gc.STORE_PROVIDER) is None


def test_a_state_works_once_only(world):
    state = _start(world)
    assert _callback(world, state=state, code="c1").status_code == 303
    assert _callback(world, state=state, code="c1").status_code == 400


def test_a_state_issued_for_another_provider_is_refused(world):
    state = world.states.issue(provider="meta", org_id=ORG, user_id="u", redirect_uri="x", code_verifier="v")
    assert _callback(world, state=state, code="c1").status_code == 400


def test_a_redirect_uri_that_changed_since_start_is_not_trusted(world, monkeypatch):
    state = _start(world)
    monkeypatch.setenv("PRODUCT_URL_ASSISTANT", "https://evil.example.test")
    assert _callback(world, state=state, code="c1").headers["location"].endswith("google=erro")
    assert world.store.get(ORG, gc.STORE_PROVIDER) is None


def test_a_successful_callback_stores_per_org_and_redirects_to_the_settings_tab(world):
    resp = _callback(world, state=_start(world), code="c1")
    assert resp.status_code == 303 and resp.headers["location"] == f"{HOST}/configuracoes/google?google=conectado"
    stored = world.store.get(ORG, gc.STORE_PROVIDER)
    assert stored.tokens["refresh_token"] == REFRESH and stored.metadata["account_email"] == "dono@example.com"
    assert world.store.list_providers("another-org") == []


def test_consent_denied_stores_nothing(world):
    resp = _callback(world, state=_start(world), error="access_denied")
    assert resp.headers["location"].endswith("google=negado") and world.store.get(ORG, gc.STORE_PROVIDER) is None


def test_a_grant_without_a_refresh_token_is_refused(world):
    world.provider = FakeOAuthProvider(name="google", use_pkce=True, predetermined_tokens=_tokens(refresh=None))
    resp = _callback(world, state=_start(world), code="c1")
    assert resp.headers["location"].endswith("google=sem_refresh_token") and world.store.get(ORG, gc.STORE_PROVIDER) is None


# ----- tokens never reach the browser -----
def test_no_response_ever_carries_a_token(world):
    bodies = [world.client.post("/api/google/connect/start").text]
    resp = _callback(world, state=_start(world), code="c1")
    bodies += [resp.text, resp.headers["location"], world.client.get("/api/google/status").text, world.client.get("/api/google/prova").text]
    bodies.append(world.client.post("/api/google/disconnect").text)
    for body in bodies:
        assert ACCESS not in body and REFRESH not in body and "SECRET" not in body


def test_status_reports_account_scopes_and_missing_scopes_only(world):
    assert world.client.get("/api/google/status").json()["connected"] is False
    _connect(world, scopes=["openid", gc.SCOPE_CALENDAR])  # the user unticked Drive on the consent screen
    st = world.client.get("/api/google/status").json()
    assert st["connected"] is True and st["account_email"] == "dono@example.com"
    assert st["missing_scopes"] == [gc.SCOPE_DRIVE_READ] and gc.SCOPE_CALENDAR in st["scopes"]
    assert set(st) == {"connected", "account_email", "scopes", "missing_scopes", "connected_at", "needs_reconnection", "app_scopes"}


# ----- disconnect -----
def test_disconnect_revokes_at_google_then_deletes(world):
    _connect(world)
    out = world.client.post("/api/google/disconnect").json()
    assert out == {"connected": False, "revoked": True}
    assert world.provider.revoked_tokens == [REFRESH] and world.store.get(ORG, gc.STORE_PROVIDER) is None
    assert world.client.post("/api/google/disconnect").json() == {"connected": False, "revoked": None}


def test_disconnect_deletes_even_when_google_is_unreachable_and_says_so(world):
    _connect(world)
    world.provider = _RevokeFails(name="google")
    assert world.client.post("/api/google/disconnect").json() == {"connected": False, "revoked": False}
    assert world.store.get(ORG, gc.STORE_PROVIDER) is None


# ----- proof -----
def test_proof_needs_a_connection(world):
    assert world.client.get("/api/google/prova").status_code == 409


def test_proof_lists_five_events_and_five_files_names_only(world):
    _connect(world)
    body = world.client.get("/api/google/prova").json()
    assert body["calendario"]["status"] == "ok" and len(body["calendario"]["itens"]) == 5
    assert [i["titulo"] for i in body["calendario"]["itens"]][:2] == ["Reunião 0", "Reunião 1"]
    assert body["drive"]["status"] == "ok" and len(body["drive"]["itens"]) == 5
    assert {k for i in body["drive"]["itens"] for k in i} == {"nome", "tipo", "modificado_em"}
    assert "conteudo-privado" not in json.dumps(body) and body["needs_reconnection"] is False


def test_a_missing_scope_hides_only_its_half(world):
    _connect(world, scopes=["openid", gc.SCOPE_CALENDAR])
    body = world.client.get("/api/google/prova").json()
    assert body["calendario"]["status"] == "ok" and body["drive"] == {"status": "sem_permissao", "itens": []}


def test_a_dead_token_is_a_state_not_a_500(world):
    _connect(world)
    world.clients = _Clients(RefreshError("invalid_grant"), FakeDriveReader())
    world.app.dependency_overrides[gr.get_google_clients] = lambda: world.clients
    body = world.client.get("/api/google/prova").json()
    assert body["calendario"]["status"] == "reconectar" and body["needs_reconnection"] is True
    assert world.client.get("/api/google/status").json()["needs_reconnection"] is True


def test_one_failing_half_does_not_hide_the_other(world):
    _connect(world)
    world.app.dependency_overrides[gr.get_google_clients] = lambda: _Clients(RuntimeError("boom"), world.clients._drive)
    body = world.client.get("/api/google/prova").json()
    assert body["calendario"]["status"] == "erro" and body["drive"]["status"] == "ok" and len(body["drive"]["itens"]) == 5


# ----- deploy gaps are 503, never a silent Fake -----
def test_missing_google_client_or_encryption_key_is_a_503(client):
    from app.main import app

    app.dependency_overrides[gr.require_org_admin] = lambda: (type("U", (), {"id": "u"})(), "t", ORG)
    try:
        assert client.post("/api/google/connect/start").status_code == 503  # no GOOGLE_OAUTH_CLIENT_ID in the test env
        assert client.get("/api/google/status").status_code == 503  # no valid ENCRYPTION_KEY
    finally:
        app.dependency_overrides.pop(gr.require_org_admin, None)


# ----- G-1: the flow is bound to the browser that started it -----
def test_connect_start_sets_a_host_only_httponly_cookie(world):
    cookie = world.client.post("/api/google/connect/start").headers["set-cookie"]
    low = cookie.lower()
    assert cookie.startswith(f"{COOKIE}=") and "secure" in low and "httponly" in low and "samesite=lax" in low
    assert "max-age=600" in low and "path=/" in low and "domain" not in low


def test_a_valid_state_without_the_browser_cookie_is_refused_and_stores_nothing(world):
    state = _start(world)
    resp = _callback(world, cookie=None, state=state, code="c1")  # e.g. the victim a link was sent to
    assert resp.status_code == 400 and world.store.get(ORG, gc.STORE_PROVIDER) is None


def test_a_valid_state_with_another_cookie_is_refused_and_burns_the_state(world):
    state = _start(world)
    assert _callback(world, cookie="attacker-made-cookie", state=state, code="c1").status_code == 400
    assert world.store.get(ORG, gc.STORE_PROVIDER) is None
    assert _callback(world, state=state, code="c1").status_code == 400  # burned: the real browser cannot reuse it


def test_the_cookie_is_cleared_on_every_exit_of_the_callback(world):
    def cleared(resp):
        sc = resp.headers.get("set-cookie", "").lower()
        return sc.startswith(COOKIE.lower() + "=") and ("max-age=0" in sc or "expires=" in sc)

    ok = _callback(world, state=_start(world), code="c1")
    denied = _callback(world, state=_start(world), error="access_denied")
    bad_state = _callback(world, state="forged", code="c1")
    no_cookie = _callback(world, cookie=None, state=_start(world), code="c1")
    assert all(cleared(r) for r in (ok, denied, bad_state, no_cookie))


# ----- G-2: tier declaration -----
def test_the_callback_router_declares_the_oauth_callback_category():
    assert gr.callback_router.access_tier == "service" and gr.callback_router.access_tier_category == "oauth-callback"


# ----- G-4: rate limit + one flow in flight -----
def test_connect_start_is_rate_limited_to_10_per_minute(world):
    codes = [world.client.post("/api/google/connect/start").status_code for _ in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429


def test_a_new_start_supersedes_the_previous_one_for_the_same_user(world):
    first = _start(world)
    first_nonce = world.nonce
    second = _start(world)
    assert _callback(world, cookie=first_nonce, state=first, code="c1").status_code == 400
    assert _callback(world, state=second, code="c1").status_code == 303


# ----- G-5: the starter must still be an admin when Google calls back -----
def test_a_user_demoted_between_start_and_callback_cannot_store_a_grant(world):
    state = _start(world)
    world.is_admin = False
    assert _callback(world, state=state, code="c1").headers["location"].endswith("google=erro")
    assert world.store.get(ORG, gc.STORE_PROVIDER) is None


def test_a_membership_check_that_fails_refuses_too(world):
    def boom(user_id, org_id):
        raise RuntimeError("core db down")

    world.app.dependency_overrides[gr.get_membership_checker] = lambda: boom
    assert _callback(world, state=_start(world), code="c1").headers["location"].endswith("google=erro")
    assert world.store.get(ORG, gc.STORE_PROVIDER) is None


# ----- G-6: no orphan grants -----
def test_reconnect_revokes_the_previous_refresh_token_first(world):
    _connect(world)
    world.provider = FakeOAuthProvider(name="google", use_pkce=True, predetermined_tokens=_tokens(refresh="1//NEW-REFRESH"))
    assert _callback(world, state=_start(world), code="c2").headers["location"].endswith("google=conectado")
    assert world.provider.revoked_tokens == [REFRESH]
    assert world.store.get(ORG, gc.STORE_PROVIDER).tokens["refresh_token"] == "1//NEW-REFRESH"


def test_reconnect_with_the_same_refresh_token_does_not_revoke_it(world):
    _connect(world)
    assert _callback(world, state=_start(world), code="c2").headers["location"].endswith("google=conectado")
    assert world.provider.revoked_tokens == []


def test_disconnect_with_no_token_never_calls_revoke(world):
    world.store.put(ORG, gc.STORE_PROVIDER, {"scope": []}, metadata={})
    assert world.client.post("/api/google/disconnect").json() == {"connected": False, "revoked": None}
    assert world.provider.revoked_tokens == [] and world.store.get(ORG, gc.STORE_PROVIDER) is None


def test_a_persist_failure_revokes_the_grant_that_was_just_issued(world):
    world.store = _FailingPut()
    resp = _callback(world, state=_start(world), code="c1")
    assert resp.headers["location"].endswith("google=erro")
    assert world.provider.revoked_tokens == [REFRESH]


def test_disconnect_goes_through_the_remover_with_the_actor(world):
    _connect(world)
    world.client.post("/api/google/disconnect")
    assert world.removed == [(ORG, "user-1")]
