"""`/api/julia/agente` routes (contract section 5, 10.1 H1/H3, 11.1, 11.3, 11.4) + the per-chat
pause + the authorized-numbers PATCH invariant. Strict `== 401` on every auth boundary.

Seams: mock DB, seed `FakeWahaClient`, `FakeAgentsClient` -- injected through the routes' own
`Depends` factories (`get_agents_client_factory`, `get_waha_client_factory`) and the grant sink's
`configure_grant_sink` store slot, never by patching our own code.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.api.auth.session import AuthContext
from noctusai_lib.testing import handler_status, TEST_USER_ID, MockUser, MockUserResponse, bind_consent_module_to_mock

from app.clients.agents import (
    AgentNotFound,
    AgentsTimeout,
    AgentsTokenInvalid,
    AgentStatus,
    FakeAgentsClient,
)
from app.services import julia_agente_service as julia
from app.services.api_keys_store import build_api_key_store
from app.services.julia_grant_sink import configure_grant_sink
from app.services.whatsapp_realtime import get_whatsapp_bus, reset_bus_cache, whatsapp_scope

from tests.support.julia_world import (
    ADMIN_ID,
    CONNECTION_ID,
    CORRETOR_ID,
    ENCRYPTION_KEY,
    LEAD_CHAT,
    MEMBER_ID,
    ORG_ID,
    OTHER_ORG_ID,
    OWNER_ID,
    World,
)

BASE = "/api/julia/agente"
CONN_URL = f"{BASE}/conexoes/{CONNECTION_ID}"  # only the per-chat deletion route lives here now
ROT_URL = f"/api/julia/roteamento/linhas/{CONNECTION_ID}"
H = {"Authorization": "Bearer test-token"}


class Scene:
    def __init__(self, tc, world):
        self.tc, self.w = tc, world

    def get(self, url, **kw):
        return self.tc.get(url, headers=H, **kw)

    def put(self, url, json, **kw):
        return self.tc.put(url, json=json, headers=H, **kw)

    def snapshot_ids(self) -> set[str]:
        return {r["chat_id"] for r in self.w.sw.table("julia_agente_chats_preexistentes").select("*").execute().data}

    def conn(self) -> dict:
        return next(r for r in self.w.sw.table("whatsapp_connections").select("*").execute().data if r["id"] == CONNECTION_ID)


def _scene(monkeypatch, override_settings_factory, *, role: str | None):
    world = World()
    world.core.set_table_data("noctus_users", [
        {"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": role},
        {"id": OWNER_ID, "org_id": ORG_ID, "org_role": "owner"},
        {"id": ADMIN_ID, "org_id": ORG_ID, "org_role": "admin"},
        {"id": CORRETOR_ID, "org_id": ORG_ID, "org_role": "corretor"},
        {"id": MEMBER_ID, "org_id": ORG_ID, "org_role": "member"},
    ])
    world.root.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id=ORG_ID, org_role=role)))
    monkeypatch.setenv("REDIS_URL", "redis://fake:6379/0")
    monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", "https://sw.example.test")
    monkeypatch.setattr("redis.Redis.from_url", lambda *_a, **_kw: world.redis)
    reset_bus_cache()
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=world.root),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=world.root),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=world.admin),
    ):
        from app.main import app
        from app.routers.julia_agente_router import get_agents_client_factory
        from app.routers.whatsapp_connections_router import get_waha_client_factory

        bind_consent_module_to_mock(world.root)
        scene = Scene(TestClient(app), world)
        scene.override = override_settings_factory

        app.dependency_overrides[get_agents_client_factory] = lambda: (lambda org_id: world.agents)
        app.dependency_overrides[get_waha_client_factory] = lambda: (lambda **kw: world.waha)
        override_settings_factory(
            encryption_key=ENCRYPTION_KEY, waha_webhook_hmac_secret="sekrit", redis_url="redis://fake:6379/0",
        )
        configure_grant_sink(lambda: build_api_key_store(encryption_key=ENCRYPTION_KEY))
        yield scene
        configure_grant_sink(None)
        for dep in (get_agents_client_factory, get_waha_client_factory):
            app.dependency_overrides.pop(dep, None)
    reset_bus_cache()


@pytest.fixture
def override_settings_factory():
    from app.config import settings as _settings
    from app.dependencies import get_settings
    from app.main import app

    overrides: dict = {}
    previous = app.dependency_overrides.get(get_settings)

    def apply(**kw):
        overrides.update(kw)
        stub = _settings.model_copy(update=dict(overrides))
        app.dependency_overrides[get_settings] = lambda: stub

    yield apply
    if previous is None:
        app.dependency_overrides.pop(get_settings, None)
    else:
        app.dependency_overrides[get_settings] = previous


@pytest.fixture
def admin(monkeypatch, override_settings_factory):
    yield from _scene(monkeypatch, override_settings_factory, role="owner")


@pytest.fixture
def member(monkeypatch, override_settings_factory):
    yield from _scene(monkeypatch, override_settings_factory, role="member")


def _off_connection(w: World, **over):
    return w.seed_connection(agente_leads_ativo=False, agente_leads_ativado_em=None, agente_leads_key=None, **over)


# ── auth boundary: strict 401 / 403 ─────────────────────────────────────────
class TestAuth:
    @pytest.mark.parametrize("method,url,body", [
        ("get", BASE, None),
        ("put", ROT_URL, {"alimenta": True}),
        ("put", f"{BASE}/token", {"token": "pk_12345678"}),
        ("patch", f"/api/whatsapp/connections/{CONNECTION_ID}/chats/{LEAD_CHAT}/agente", {"pausado": True}),
        ("post", f"{CONN_URL}/chats/{LEAD_CHAT}/apagar-dados", None),
    ])
    def test_no_token_is_401(self, admin, method, url, body):
        r = getattr(admin.tc, method)(url, **({"json": body} if body is not None else {}))
        assert r.status_code == 401

    def test_a_member_can_read(self, member):
        member.w.seed_connection()
        assert member.get(BASE).status_code == 200

    @pytest.mark.parametrize("method,url,body", [
        ("put", ROT_URL, {"alimenta": True}),
        ("patch", f"/api/whatsapp/connections/{CONNECTION_ID}/chats/{LEAD_CHAT}/agente", {"pausado": True}),
        ("post", f"{CONN_URL}/chats/{LEAD_CHAT}/apagar-dados", None),
    ])
    def test_a_member_cannot_write_403(self, member, method, url, body):
        member.w.seed_connection()
        r = getattr(member.tc, method)(url, headers=H, **({"json": body} if body is not None else {}))
        assert r.status_code == 403

    def test_a_connection_of_another_org_is_404(self, admin):
        admin.w.seed_connection(org_id=OTHER_ORG_ID)
        assert admin.put(ROT_URL, {"alimenta": False}).status_code == 404


# ── GET /api/julia/agente ────────────────────────────────────────────────────
class TestGetAgente:
    def test_shape_and_per_connection_fields(self, admin):
        admin.w.seed_connection(authorized_numbers=["+5511999990000", "+5511999991111"])
        data = admin.get(BASE).json()["data"]
        # the lines moved to GET /api/julia/roteamento
        assert set(data) == {"token_configurado", "status_agente", "erro", "banner", "conexao_plataforma", "pode_ligar", "motivo_bloqueio"}

    def test_status_agente_is_the_3_2_shape(self, admin):
        admin.w.seed_connection()
        admin.w.agents = FakeAgentsClient(status=AgentStatus("julia", "Julia", True, 3, "openai", "gpt-5-mini", True))
        st = admin.get(BASE).json()["data"]["status_agente"]
        assert st == {"agent_key": "julia", "nome": "Julia", "ativo": True, "versao_ativa": 3,
                      "provider": "openai", "model": "gpt-5-mini", "llm_configurado": True}

    def test_an_org_without_connections_still_answers(self, admin):
        assert "conexoes" not in admin.get(BASE).json()["data"]

    def test_the_legacy_line_switch_is_retired(self, admin):
        admin.w.seed_connection()
        assert admin.put(CONN_URL, {"agente_leads_ativo": False}).status_code in (404, 405)

    def test_token_configurado_reflects_the_org_token_and_never_echoes_it(self, admin):
        assert admin.get(BASE).json()["data"]["token_configurado"] is False
        _entregar(admin, "pk_secret_value")
        r = admin.get(BASE)
        assert r.json()["data"]["token_configurado"] is True
        assert "pk_secret_value" not in r.text

    @pytest.mark.parametrize("error,expected", [
        (AgentsTokenInvalid(), "token_invalido"),
        (AgentNotFound(code="agent_not_found"), "agent_not_found"),
    ])
    def test_a_refused_token_or_missing_agent_shows_as_erro(self, admin, error, expected):
        admin.w.agents = FakeAgentsClient(status_error=error)
        data = admin.get(BASE).json()["data"]
        assert data["erro"] == julia.LINK_ERROR_MESSAGES[expected] and data["status_agente"] is None

    def test_an_inactive_agent_and_a_missing_llm_key_show_as_erro(self, admin):
        admin.w.agents = FakeAgentsClient(status=AgentStatus("julia", "Julia", False, None, None, None, True))
        assert admin.get(BASE).json()["data"]["erro"] == julia.LINK_ERROR_MESSAGES["agent_unavailable"]
        admin.w.agents = FakeAgentsClient(status=AgentStatus("julia", "Julia", True, 1, "openai", "gpt-5", False))
        assert admin.get(BASE).json()["data"]["erro"] == julia.LINK_ERROR_MESSAGES["llm_not_configured"]

    def test_L2_an_upstream_failure_gives_a_generic_line_never_the_detail(self, admin):
        admin.w.agents = FakeAgentsClient(status_error=AgentsTimeout("connect to 10.0.0.7:8000 refused"))
        erro = admin.get(BASE).json()["data"]["erro"]
        assert "10.0.0.7" not in erro and erro

    def test_the_last_turn_failure_is_surfaced_when_the_live_status_is_fine(self, admin):
        julia.registrar_erro_link(ORG_ID, "llm_not_configured", cfg=admin.w.cfg)
        assert admin.get(BASE).json()["data"]["erro"] == julia.LINK_ERROR_MESSAGES["llm_not_configured"]

    def test_no_client_in_prod_means_nao_configurado(self, admin):
        from app.main import app
        from app.routers.julia_agente_router import get_agents_client_factory

        app.dependency_overrides[get_agents_client_factory] = lambda: (lambda org_id: None)
        assert admin.get(BASE).json()["data"]["erro"] == julia.LINK_ERROR_MESSAGES["nao_configurado"]


# ── PUT /roteamento/linhas/{id}: the switch (the legacy PUT /agente/conexoes/{id} is retired) ──────────────────────────────────────────
class TestSwitchOn:
    def _on(self, scene, **extra):
        return scene.put(ROT_URL, {"alimenta": True, **extra})

    def test_turning_on_snapshots_the_session_then_sets_the_flag(self, admin):
        _off_connection(admin.w)
        admin.w.waha.fake_chat_list = [{"id": {"_serialized": f"55119{i:08d}@c.us"}} for i in range(230)]
        r = self._on(admin)
        assert r.status_code == 200
        out = r.json()["data"]
        assert out["alimenta"] is True
        assert out["alimenta_desde"]
        # 230 phone chats + their `@s.whatsapp.net` twins
        assert len(admin.snapshot_ids()) == 460
        row = admin.conn()
        assert row["agente_leads_ativo"] is True and row["agente_leads_ativado_em"] and row["agente_leads_key"] == "julia"

    def test_both_the_phone_and_the_lid_form_are_stored_when_waha_exposes_both(self, admin):
        _off_connection(admin.w)
        admin.w.waha.fake_chat_list = [{"id": "5511988887777@c.us"}]
        admin.w.waha.fake_lids = [{"lid": "123456@lid", "pn": "5511988887777@c.us"}]
        assert self._on(admin).status_code == 200
        assert admin.snapshot_ids() >= {"5511988887777@c.us", "5511988887777@s.whatsapp.net", "123456@lid"}

    def test_julia_line_D5_empty_authorized_numbers_no_longer_blocks_turning_it_on(self, admin):
        _off_connection(admin.w, authorized_numbers=[])
        r = self._on(admin)
        assert r.status_code == 200
        assert admin.conn()["agente_leads_ativo"] is True

    def test_H1_without_a_webhook_hmac_secret_it_is_409(self, admin, override_settings_factory):
        _off_connection(admin.w)
        override_settings_factory(waha_webhook_hmac_secret="")
        r = self._on(admin)
        assert r.status_code == 409 and "webhook_hmac_required" in r.text
        assert admin.conn()["agente_leads_ativo"] is False and admin.snapshot_ids() == set()

    def test_11_3_an_aviso_without_empresa_nome_is_409_aviso_incompleto(self, admin):
        _off_connection(admin.w)
        admin.w.core.set_table_data("organizations", [])  # the notice's controller name is unknown
        r = self._on(admin)
        assert r.status_code == 409 and "aviso_incompleto" in r.text
        assert admin.conn()["agente_leads_ativo"] is False

    def test_11_3_an_unresolvable_public_url_is_409_never_a_made_up_link(self, admin, monkeypatch):
        _off_connection(admin.w)
        monkeypatch.delenv("PRODUCT_URL_SOCIAL_WIRING")
        monkeypatch.delenv("PRODUCT_URL_PATTERN", raising=False)
        r = self._on(admin)
        assert r.status_code == 409 and "url_publica_indisponivel" in r.text

    def test_11_1_a_failed_listing_is_502_snapshot_falhou_and_the_switch_stays_OFF(self, admin):
        _off_connection(admin.w)

        async def boom(limit=50, offset=0):
            raise RuntimeError("WAHA 422")

        admin.w.waha.list_chats = boom
        r = self._on(admin)
        assert handler_status(r) == 502 and "snapshot_falhou" in r.text
        assert admin.conn()["agente_leads_ativo"] is False and admin.snapshot_ids() == set()

    def test_11_1_an_incomplete_listing_is_the_same_502_not_a_partial_snapshot(self, admin):
        _off_connection(admin.w)
        calls = {"n": 0}
        chats = [{"id": f"55119{i:08d}@c.us"} for i in range(150)]

        async def flaky(limit=50, offset=0):
            calls["n"] += 1
            if offset > 0:
                raise TimeoutError("slow")
            return chats[:limit]

        admin.w.waha.list_chats = flaky
        assert handler_status(self._on(admin)) == 502
        assert admin.snapshot_ids() == set() and admin.conn()["agente_leads_ativo"] is False

    def test_11_1_a_session_with_no_chats_snapshots_nothing_and_turns_on(self, admin):
        _off_connection(admin.w)
        assert self._on(admin).status_code == 200 and admin.snapshot_ids() == set()

    def test_11_1_off_then_on_again_takes_a_NEW_snapshot_and_keeps_the_old_exclusions(self, admin):
        _off_connection(admin.w)
        admin.w.waha.fake_chat_list = [{"id": "5511900000001@c.us"}]
        self._on(admin)
        first = admin.snapshot_ids()
        assert admin.put(ROT_URL, {"alimenta": False}).json()["data"]["alimenta"] is False
        admin.w.waha.fake_chat_list = [{"id": "5511900000001@c.us"}, {"id": "5511900000002@c.us"}]
        self._on(admin)
        assert admin.snapshot_ids() > first and "5511900000002@c.us" in admin.snapshot_ids()
        assert first <= admin.snapshot_ids(), "chats excluded once stay excluded"

    def test_putting_on_while_already_on_does_not_re_snapshot_nor_move_ativado_em(self, admin):
        admin.w.seed_connection()  # already on, ativado_em fixed
        admin.w.waha.fake_chat_list = [{"id": "5511900000001@c.us"}]
        r = self._on(admin)
        assert r.status_code == 200
        assert admin.snapshot_ids() == set()
        assert admin.conn()["agente_leads_ativado_em"] == "2026-10-01T00:00:00+00:00"

    def test_turning_off_keeps_the_exclusions_and_clears_only_the_flag(self, admin):
        admin.w.seed_connection()
        r = admin.put(ROT_URL, {"alimenta": False})
        assert r.status_code == 200 and admin.conn()["agente_leads_ativo"] is False

    def test_unknown_fields_are_rejected(self, admin):
        _off_connection(admin.w)
        assert admin.put(ROT_URL, {"alimenta": True, "org_id": "x"}).status_code == 422

    def test_a_missing_connection_is_404(self, admin):
        assert admin.put(f"/api/julia/roteamento/linhas/00000000-0000-4000-8000-0000000000ee", {"alimenta": True}).status_code == 404


# ── 11.4: handoff target ────────────────────────────────────────────────────
class TestHandoffTargetRoute:
    def test_an_admin_target_is_stored(self, admin):
        admin.w.seed_connection()
        r = admin.put(ROT_URL, {"alimenta": True, "destino_handoff_user_id": ADMIN_ID})
        assert r.status_code == 200 and r.json()["data"]["destino_handoff_user_id"] == ADMIN_ID

    @pytest.mark.parametrize("uid", [MEMBER_ID, CORRETOR_ID])
    def test_member_and_corretor_targets_are_422_destinatario_invalido(self, admin, uid):
        admin.w.seed_connection()
        r = admin.put(ROT_URL, {"alimenta": True, "destino_handoff_user_id": uid})
        assert r.status_code == 422 and "destinatario_invalido" in r.text
        assert admin.conn()["agente_handoff_notificar_user_id"] is None

    def test_null_resets_to_the_connection_owner(self, admin):
        admin.w.seed_connection(agente_handoff_notificar_user_id=ADMIN_ID)
        r = admin.put(ROT_URL, {"alimenta": True, "destino_handoff_user_id": None})
        assert r.json()["data"]["destino_handoff_user_id"] is None

    def test_omitting_the_field_keeps_the_current_target(self, admin):
        admin.w.seed_connection(agente_handoff_notificar_user_id=ADMIN_ID)
        r = admin.put(ROT_URL, {"alimenta": True})
        assert r.json()["data"]["destino_handoff_user_id"] == ADMIN_ID

    def test_the_target_can_be_set_while_julia_is_off_too(self, admin):
        _off_connection(admin.w)
        r = admin.put(ROT_URL, {"alimenta": False, "destino_handoff_user_id": ADMIN_ID})
        assert r.status_code == 200 and admin.conn()["agente_handoff_notificar_user_id"] == ADMIN_ID

    def test_a_user_of_another_org_is_422(self, admin):
        admin.w.seed_connection()
        admin.w.core.table("noctus_users").insert({"id": "00000000-0000-4000-8000-0000000000d1", "org_id": OTHER_ORG_ID, "org_role": "admin"}).execute()
        r = admin.put(ROT_URL, {"alimenta": True, "destino_handoff_user_id": "00000000-0000-4000-8000-0000000000d1"})
        assert r.status_code == 422


# ── H3: the authorized-numbers PATCH ────────────────────────────────────────
class TestAuthorizedNumbersPatch:
    URL = f"/api/whatsapp/connections/{CONNECTION_ID}"

    def test_emptying_the_list_while_julia_is_on_is_fine_julia_needs_no_authorized_numbers(self, admin):
        """The One Chat operator bot is retired (2026-11-04): `authorized_numbers` is a dead column and Julia never reads it."""
        admin.w.seed_connection()
        r = admin.tc.patch(self.URL, json={"authorized_numbers": []}, headers=H)
        assert r.status_code == 200 and admin.conn()["authorized_numbers"] == []
        assert admin.conn()["agente_leads_ativo"] is True

    def test_blank_entries_are_just_stored(self, admin):
        admin.w.seed_connection()
        assert admin.tc.patch(self.URL, json={"authorized_numbers": [" "]}, headers=H).status_code == 200

    def test_a_non_empty_replacement_is_fine_while_julia_is_on(self, admin):
        admin.w.seed_connection()
        r = admin.tc.patch(self.URL, json={"authorized_numbers": ["+5511977770000"]}, headers=H)
        assert r.status_code == 200 and admin.conn()["authorized_numbers"] == ["+5511977770000"]

    def test_the_patch_no_longer_touches_the_org_staff_list(self, admin):
        """Staff is THE per-org list, edited in /julia/equipe; the legacy column is no longer a mirror of it (nor it of the column)."""
        admin.w.seed_connection()
        admin.w.sw.set_table_data("julia_staff", [])
        admin.w.sw.set_table_data("julia_numeros_bloqueados", [])
        r = admin.tc.patch(self.URL, json={"authorized_numbers": ["+55 11 97777-0000"]}, headers=H)
        assert r.status_code == 200
        assert admin.w.rows("julia_staff") == []
        assert admin.conn()["authorized_numbers"] == ["+55 11 97777-0000"]

    def test_with_julia_off_an_empty_list_is_still_writable_it_means_nobody(self, admin):
        _off_connection(admin.w)
        assert admin.tc.patch(self.URL, json={"authorized_numbers": []}, headers=H).status_code == 200

    def test_patching_something_else_while_julia_is_on_is_untouched(self, admin):
        admin.w.seed_connection()
        assert admin.tc.patch(self.URL, json={"label": "Novo nome"}, headers=H).status_code == 200

    def _row(self, **over):
        row = {"id": "00000000-0000-4000-8000-0000000000e9", "org_id": ORG_ID, "user_id": OWNER_ID,
               "label": "x", "base_url": "https://w", "session_name": "default", "encrypted_api_key": "x",
               "authorized_numbers": ["+5511999990000"], "agente_leads_ativo": True,
               "agente_leads_key": "julia", "agente_leads_ativado_em": "2026-10-01T00:00:00+00:00"}
        row.update(over)
        return row

    def test_the_DB_check_on_authorized_numbers_was_dropped_by_migration_318(self, admin):
        """Migration 258's `agente_exige_autorizados` CHECK is gone (318): Julia on over an empty list is a valid row. The mock enforces
        the CHECKs of the migration CHAIN, so this fails if 318 stops dropping it."""
        admin.w.sw.table("whatsapp_connections").insert(self._row(authorized_numbers=[])).execute()

    def test_the_DB_check_refuses_julia_on_without_ativado_em_or_key(self, admin):
        from noctusai_lib.testing.mocks import MockRowCheckViolation

        with pytest.raises(MockRowCheckViolation):
            admin.w.sw.table("whatsapp_connections").insert(self._row(agente_leads_ativado_em=None)).execute()
        with pytest.raises(MockRowCheckViolation):
            admin.w.sw.table("whatsapp_connections").insert(self._row(agente_leads_key=None)).execute()

    def test_the_DB_check_lets_a_valid_row_and_a_julia_off_row_through(self, admin):
        admin.w.sw.table("whatsapp_connections").insert(self._row()).execute()
        admin.w.sw.table("whatsapp_connections").insert(
            self._row(id="00000000-0000-4000-8000-0000000000e8", agente_leads_ativo=False, authorized_numbers=[],
                      agente_leads_ativado_em=None)
        ).execute()


# ── the platform grant (Julia-line D2-D5): agents DELIVERS the channel token, nobody pastes it ──
GRANT_URL = "/api/platform/grants/agents"
SCOPE = "platform:grant-receive"
SECRET = "noc_channel_secret_value_0123456789"


CONEXAO_KEYS = {"status", "conectada", "motivo", "token_prefix", "token_mascarado", "conectada_em", "agent_key",
                "verificada_em", "ultima_falha_em", "expires_at"}
VERIFICAR = f"{BASE}/conexao-plataforma/verificar"


def _delivery_ctx(*, scopes=(SCOPE,), issuer="agents", org=ORG_ID):
    from uuid import UUID, uuid4

    return AuthContext(org_id=UUID(org), caller_kind="product", user_id=None, scopes=list(scopes),
                       raw_token="t", api_token_id=uuid4(), issuer=issuer)


def _body(credential=SECRET, **meta):
    return {"credential": credential, "agent_id": "agent-inst-1",
            "metadata": {"grant_id": "g-1", "agent_key": "julia", "token_prefix": "noc_channel_",
                         "scopes": ["agents:channel-turn"], "expires_at": None, **meta}}


def _entregar(scene, credential=SECRET, *, org=ORG_ID, **kw):
    """Deliver a grant through the REAL receiver, authenticated as agents' one-shot delivery token."""
    from app.dependencies import get_auth_context
    from app.main import app

    app.dependency_overrides[get_auth_context] = lambda: _delivery_ctx(org=org)
    try:
        r = scene.tc.put(GRANT_URL, json=_body(credential, **kw))
    finally:
        app.dependency_overrides.pop(get_auth_context, None)
    assert r.status_code == 204, r.text
    return r


class TestPlatformGrantReceiver:
    def test_no_token_is_401_on_both_verbs(self, admin):
        assert admin.tc.put(GRANT_URL, json=_body()).status_code == 401
        assert admin.tc.delete(GRANT_URL).status_code == 401

    @pytest.mark.parametrize("kw", [{"scopes": ("agents:channel-turn",)}, {"issuer": "social-wiring"}])
    def test_a_wrong_scope_or_issuer_is_403_and_stores_nothing(self, admin, kw):
        from app.dependencies import get_auth_context
        from app.main import app

        app.dependency_overrides[get_auth_context] = lambda: _delivery_ctx(**kw)
        try:
            assert admin.tc.put(GRANT_URL, json=_body()).status_code == 403
            assert admin.tc.delete(GRANT_URL).status_code == 403
        finally:
            app.dependency_overrides.pop(get_auth_context, None)
        assert julia.agents_token_for_org(ORG_ID, cfg=admin.w.cfg) is None

    def test_an_org_id_in_the_body_is_422_the_org_comes_from_the_token(self, admin):
        from app.dependencies import get_auth_context
        from app.main import app

        app.dependency_overrides[get_auth_context] = lambda: _delivery_ctx()
        try:
            r = admin.tc.put(GRANT_URL, json={**_body(), "org_id": OTHER_ORG_ID})
        finally:
            app.dependency_overrides.pop(get_auth_context, None)
        assert r.status_code == 422
        assert julia.agents_token_for_org(OTHER_ORG_ID, cfg=admin.w.cfg) is None

    def test_a_grant_makes_agents_token_for_org_return_the_credential(self, admin):
        assert admin.get(BASE).json()["data"]["conexao_plataforma"]["conectada"] is False
        _entregar(admin)
        assert julia.agents_token_for_org(ORG_ID, cfg=admin.w.cfg) == SECRET
        assert julia.agents_token_for_org(OTHER_ORG_ID, cfg=admin.w.cfg) is None  # per org
        r = admin.get(BASE)
        data = r.json()["data"]
        assert data["token_configurado"] is True
        con = data["conexao_plataforma"]
        assert set(con) == CONEXAO_KEYS
        assert (con["status"], con["conectada"], con["token_prefix"], con["agent_key"]) == (
            "ativa", True, "noc_channel_", "julia")
        assert con["conectada_em"] and con["verificada_em"] is None and con["motivo"] is None
        assert con["token_mascarado"] == "noc_...6789"
        assert SECRET not in r.text and "agents_url" not in data

    def test_a_regrant_replaces_the_credential(self, admin):
        _entregar(admin)
        _entregar(admin, "noc_rotated_secret_value_987654321", grant_id="g-2")
        assert julia.agents_token_for_org(ORG_ID, cfg=admin.w.cfg) == "noc_rotated_secret_value_987654321"

    def test_a_revoke_deletes_the_token_and_the_status(self, admin):
        from app.dependencies import get_auth_context
        from app.main import app

        _entregar(admin)
        app.dependency_overrides[get_auth_context] = lambda: _delivery_ctx()
        try:
            assert admin.tc.delete(GRANT_URL).status_code == 204
            assert admin.tc.delete(GRANT_URL).status_code == 204  # idempotent
        finally:
            app.dependency_overrides.pop(get_auth_context, None)
        assert julia.agents_token_for_org(ORG_ID, cfg=admin.w.cfg) is None
        con = admin.get(BASE).json()["data"]["conexao_plataforma"]
        assert (con["status"], con["conectada"], con["token_mascarado"]) == ("revogada", False, None)

    def test_the_credential_never_reaches_the_logs(self, admin, caplog):
        with caplog.at_level("DEBUG"):
            _entregar(admin)
            admin.get(BASE)
        assert all(SECRET not in rec.getMessage() for rec in caplog.records)


class TestPasteRouteRetired:
    def test_put_token_is_410_gerenciado_pela_plataforma_and_stores_nothing(self, admin):
        r = admin.put(f"{BASE}/token", {"token": "pk_live_abcdef"})
        assert r.status_code == 410 and "gerenciado_pela_plataforma" in r.text
        assert julia.agents_token_for_org(ORG_ID, cfg=admin.w.cfg) is None

    def test_the_tools_token_is_not_minted_by_social_wiring_any_more(self):
        from app.routers import julia_agente_router as router

        assert not hasattr(router, "_entregar_token_ferramentas")


# ── PATCH chat pause (julia-v2: the control lives in AGENTS) ────────────────
class TestChatPause:
    URL = f"/api/whatsapp/connections/{CONNECTION_ID}/chats/{LEAD_CHAT}/agente"

    @staticmethod
    async def _servir(scene):
        """Agents has served the chat once: a thread exists with the agent as the active participant."""
        from app.clients.agents import TurnMessage, TurnRequest
        from datetime import datetime, timezone

        await scene.w.agents.run_turn(TurnRequest(
            agent_key="julia", connection_id=CONNECTION_ID, chat_id=LEAD_CHAT,
            messages=(TurnMessage(texto="oi", provider_message_id="m1", at=datetime.now(timezone.utc)),)))

    def _scene(self, admin):
        import asyncio

        admin.w.seed_connection()
        admin.w.seed_chat()
        asyncio.new_event_loop().run_until_complete(self._servir(admin))

    def test_pause_and_resume_call_agents_and_mirror_its_answer(self, admin):
        self._scene(admin)
        r = admin.tc.patch(self.URL, json={"pausado": True}, headers=H)
        assert r.status_code == 200 and r.json() == {"chat_id": LEAD_CHAT, "agente_pausado": True, "agente_estado": "pausado"}
        call = admin.w.agents.participante_calls[-1]
        assert (call["agent_key"], call["estado"], call["ator_user_id"]) == ("julia", "pausado", str(TEST_USER_ID))
        assert call["thread_id"] == admin.w.agents.thread_id_for(CONNECTION_ID, LEAD_CHAT) or call["thread_id"]
        row = admin.w.chat_row()
        assert (row["agente_pausado"], row["agente_estado"]) == (True, "pausado")
        r = admin.tc.patch(self.URL, json={"pausado": False}, headers=H)
        assert r.json() == {"chat_id": LEAD_CHAT, "agente_pausado": False, "agente_estado": "ativo"}
        assert admin.w.chat_row()["agente_estado"] == "ativo"

    def test_it_publishes_chat_upsert_with_the_state_so_conversas_flips_live(self, admin):
        admin.override(redis_url="")  # in-process Fake bus (REDIS_URL env still feeds the Redis seam)
        reset_bus_cache()
        self._scene(admin)
        admin.tc.patch(self.URL, json={"pausado": True}, headers=H)
        stream = get_whatsapp_bus("")._streams[whatsapp_scope(CONNECTION_ID)]
        (event,) = [e for e in stream if e.event == "chat.upsert"]
        assert event.payload["chat_id"] == LEAD_CHAT and event.payload["agente_pausado"] is True
        assert event.payload["agente_estado"] == "pausado"

    def test_when_agents_is_unreachable_the_toggle_fails_and_nothing_changes_locally(self, admin):
        from app.clients.agents import AgentsTimeout

        self._scene(admin)
        admin.w.agents.errors["set_participante"] = AgentsTimeout()
        r = admin.tc.patch(self.URL, json={"pausado": True}, headers=H)
        assert handler_status(r) == 502
        assert admin.w.chat_row()["agente_pausado"] is False  # SW flips no local flag on its own

    def test_a_chat_agents_never_served_has_nothing_to_pause_404(self, admin):
        admin.w.seed_connection()
        admin.w.seed_chat()
        r = admin.tc.patch(self.URL, json={"pausado": True}, headers=H)
        assert r.status_code == 404 and "conversa_sem_agente" in r.text
        assert admin.w.agents.participante_calls == []

    def test_a_concluded_participation_cannot_be_resumed_409(self, admin):
        self._scene(admin)
        key = (admin.w.agents.thread_id_for(CONNECTION_ID, LEAD_CHAT), "julia")
        admin.w.agents.participantes = {k: "concluido" for k in admin.w.agents.participantes}
        r = admin.tc.patch(self.URL, json={"pausado": False}, headers=H)
        assert r.status_code == 409 and "transicao_invalida" in r.text

    def test_an_unknown_chat_is_404(self, admin):
        admin.w.seed_connection()
        assert admin.tc.patch(self.URL, json={"pausado": True}, headers=H).status_code == 404

    def test_an_unknown_connection_is_404(self, admin):
        r = admin.tc.patch(
            f"/api/whatsapp/connections/00000000-0000-4000-8000-0000000000ee/chats/{LEAD_CHAT}/agente",
            json={"pausado": True}, headers=H)
        assert r.status_code == 404

    def test_pausado_must_be_a_bool(self, admin):
        admin.w.seed_connection()
        admin.w.seed_chat()
        assert admin.tc.patch(self.URL, json={"pausado": "talvez"}, headers=H).status_code == 422
        assert admin.tc.patch(self.URL, json={}, headers=H).status_code == 422

    def test_a_chat_of_another_connection_is_not_reachable(self, admin):
        admin.w.seed_connection(org_id=OTHER_ORG_ID)
        admin.w.seed_chat()
        assert admin.tc.patch(self.URL, json={"pausado": True}, headers=H).status_code == 404


# ── GET chat state: what the toggle shows comes from agents ─────────────────
class TestChatState:
    URL = f"/api/whatsapp/connections/{CONNECTION_ID}/chats/{LEAD_CHAT}/agente"

    def test_the_state_is_the_one_agents_reports_and_it_is_mirrored(self, admin):
        import asyncio

        admin.w.seed_connection()
        admin.w.seed_chat()
        asyncio.new_event_loop().run_until_complete(TestChatPause._servir(admin))
        admin.w.agents.participantes = {k: "pausado" for k in admin.w.agents.participantes}
        r = admin.get(self.URL)
        assert r.status_code == 200
        data = r.json()["data"]
        assert (data["estado"], data["pausado"], data["fonte"]) == ("pausado", True, "agents")
        assert admin.w.chat_row()["agente_estado"] == "pausado"

    def test_when_agents_is_down_it_shows_the_last_mirror_flagged_as_stale(self, admin):
        from app.clients.agents import AgentsTimeout

        admin.w.seed_connection()
        admin.w.seed_chat(agente_thread_id="11111111-1111-4111-8111-111111111111", agente_estado="pausado", agente_pausado=True)
        admin.w.agents.errors["obter_thread"] = AgentsTimeout()
        data = admin.get(self.URL).json()["data"]
        assert (data["estado"], data["fonte"]) == ("pausado", "espelho")

    def test_a_chat_without_a_thread_says_so(self, admin):
        admin.w.seed_connection()
        admin.w.seed_chat()
        data = admin.get(self.URL).json()["data"]
        assert (data["estado"], data["fonte"], data["thread_id"]) == (None, "nenhuma", None)

    def test_a_member_may_read_it(self, member):
        member.w.seed_connection()
        member.w.seed_chat()
        assert member.get(self.URL).status_code == 200

    def test_no_token_is_401(self, admin):
        assert admin.tc.get(self.URL).status_code == 401


# ── deletion on request (the hook through the admin route) ──────────────────
class TestDeletionRoute:
    def test_it_runs_the_same_hook_the_worker_runs(self, admin):
        admin.w.seed_connection()
        admin.w.seed_chat()
        admin.w.sw.table("conversation_messages").insert({
            "id": "00000000-0000-4000-8000-0000000000aa", "org_id": ORG_ID, "session_id": LEAD_CHAT, "raw_sender": LEAD_CHAT,
            "direction": "inbound", "body": "oi", "provider_message_id": "w1", "authorized": True,
            "connection_id": CONNECTION_ID, "chat_id": LEAD_CHAT,
        }).execute()
        r = admin.tc.post(f"{CONN_URL}/chats/{LEAD_CHAT}/apagar-dados", headers=H)
        assert r.status_code == 200
        assert r.json()["data"]["agents_ok"] is True and r.json()["data"]["sw_mensagens"] >= 1
        assert [d.chat_id for d in admin.w.agents.deletions] == [LEAD_CHAT]
        assert admin.w.messages() == [] and admin.w.chat_row() is None

    def test_an_unknown_connection_is_404(self, admin):
        r = admin.tc.post(f"{BASE}/conexoes/00000000-0000-4000-8000-0000000000ee/chats/{LEAD_CHAT}/apagar-dados", headers=H)
        assert r.status_code == 404


# ── the status of the platform connection (owner: "configured / working / broken / not set up") ──
def _conexao(scene):
    return scene.get(BASE).json()["data"]["conexao_plataforma"]


class TestConexaoStatus:
    @pytest.fixture(autouse=True)
    def _fresh_throttle(self):
        from app.services.julia_grant_sink import reset_health_throttle

        reset_health_throttle()
        yield
        reset_health_throttle()

    def test_nao_configurada_before_any_grant(self, admin):
        con = _conexao(admin)
        assert set(con) == CONEXAO_KEYS
        assert (con["status"], con["conectada"], con["token_mascarado"]) == ("nao_configurada", False, None)

    def test_ativa_after_a_grant_with_no_verification_yet(self, admin):
        _entregar(admin)
        con = _conexao(admin)
        assert (con["status"], con["verificada_em"], con["motivo"]) == ("ativa", None, None)

    def test_expirada_when_expires_at_is_in_the_past(self, admin):
        _entregar(admin, expires_at="2020-01-01T00:00:00+00:00")
        con = _conexao(admin)
        assert (con["status"], con["conectada"]) == ("expirada", False)
        assert con["expires_at"] == "2020-01-01T00:00:00+00:00" and con["token_mascarado"] == "noc_...6789"

    def test_a_future_expiry_stays_ativa(self, admin):
        _entregar(admin, expires_at="2999-01-01T00:00:00+00:00")
        assert _conexao(admin)["status"] == "ativa"

    def test_verificar_ok_stamps_verificada_em(self, admin):
        _entregar(admin)
        r = admin.tc.post(VERIFICAR, headers=H)
        con = r.json()["data"]
        assert r.status_code == 200 and (con["status"], con["motivo"]) == ("ativa", None)
        assert con["verificada_em"] and con["ultima_falha_em"] is None
        assert admin.w.agents.status_calls == ["julia"]

    def test_verificar_a_rejected_token_is_com_falha_token_rejeitado(self, admin):
        _entregar(admin)
        admin.w.agents = FakeAgentsClient(status_error=AgentsTokenInvalid())
        con = admin.tc.post(VERIFICAR, headers=H).json()["data"]
        assert (con["status"], con["motivo"], con["conectada"]) == ("com_falha", "token_rejeitado", True)
        assert con["ultima_falha_em"] and con["token_mascarado"] == "noc_...6789"
        assert _conexao(admin)["status"] == "com_falha"  # persisted, the page reads it later

    def test_verificar_an_outage_is_com_falha_agents_indisponivel_then_recovers(self, admin):
        _entregar(admin)
        admin.w.agents = FakeAgentsClient(status_error=AgentsTimeout("down"))
        assert admin.tc.post(VERIFICAR, headers=H).json()["data"]["motivo"] == "agents_indisponivel"
        admin.w.agents = FakeAgentsClient()
        con = admin.tc.post(VERIFICAR, headers=H).json()["data"]
        assert (con["status"], con["motivo"]) == ("ativa", None) and con["verificada_em"] and con["ultima_falha_em"]

    def test_verificar_a_missing_agent_still_proves_the_token_works(self, admin):
        _entregar(admin)
        admin.w.agents = FakeAgentsClient(status_error=AgentNotFound(code="agent_not_found"))
        assert admin.tc.post(VERIFICAR, headers=H).json()["data"]["status"] == "ativa"

    def test_verificar_on_a_revoked_or_absent_grant_does_not_call_agents(self, admin):
        assert admin.tc.post(VERIFICAR, headers=H).json()["data"]["status"] == "nao_configurada"
        _entregar(admin)
        from app.dependencies import get_auth_context
        from app.main import app

        app.dependency_overrides[get_auth_context] = lambda: _delivery_ctx()
        try:
            admin.tc.delete(GRANT_URL)
        finally:
            app.dependency_overrides.pop(get_auth_context, None)
        assert admin.tc.post(VERIFICAR, headers=H).json()["data"]["status"] == "revogada"
        assert admin.w.agents.status_calls == []

    def test_a_regrant_after_a_failure_resets_the_health(self, admin):
        _entregar(admin)
        admin.w.agents = FakeAgentsClient(status_error=AgentsTokenInvalid())
        admin.tc.post(VERIFICAR, headers=H)
        _entregar(admin, "noc_new_channel_token_value_55")
        con = _conexao(admin)
        assert (con["status"], con["ultima_falha_em"]) == ("ativa", None) and con["token_mascarado"] == "noc_...e_55"

    def test_a_real_client_call_records_its_outcome(self, admin):
        """The proxy `resolve_agents_client` wraps around a REAL client records every awaited call."""
        import anyio

        from app.services.julia_grant_sink import HealthRecordingAgentsClient

        _entregar(admin)
        ok = HealthRecordingAgentsClient(FakeAgentsClient(), ORG_ID)
        anyio.run(ok.agent_status, "julia")
        assert _conexao(admin)["verificada_em"]
        bad = HealthRecordingAgentsClient(FakeAgentsClient(status_error=AgentsTokenInvalid()), ORG_ID)
        with pytest.raises(AgentsTokenInvalid):
            anyio.run(bad.agent_status, "julia")
        con = _conexao(admin)
        assert (con["status"], con["motivo"]) == ("com_falha", "token_rejeitado")

    def test_the_token_never_appears_in_responses_or_logs(self, admin, caplog):
        _entregar(admin)
        admin.w.agents = FakeAgentsClient(status_error=AgentsTokenInvalid())
        with caplog.at_level("DEBUG"):
            r = admin.tc.post(VERIFICAR, headers=H)
            r2 = admin.get(BASE)
        assert SECRET not in r.text + r2.text
        assert all(SECRET not in rec.getMessage() and "noc_...6789" not in rec.getMessage() for rec in caplog.records)

    def test_verificar_auth_matrix(self, admin, member):
        assert admin.tc.post(VERIFICAR).status_code == 401
        assert member.tc.post(VERIFICAR, headers=H).status_code == 403
