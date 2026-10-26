"""`/api/julia/agente` routes (contract section 5, 10.1 H1/H3, 11.1, 11.3, 11.4) + the per-chat
pause + the authorized-numbers PATCH invariant. Strict `== 401` on every auth boundary.

Seams: mock DB, seed `FakeWahaClient`, `FakeAgentsClient` -- injected through the routes' own
`Depends` factories (`get_agents_client_factory`, `get_agents_token_client_builder`,
`get_waha_client_factory`), never by patching our own code.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.api.auth.session import FakeProductTokenAdmin
from noctusai_lib.testing import handler_status, TEST_USER_ID, MockUser, MockUserResponse, bind_consent_module_to_mock

from app.clients.agents import (
    AgentNotFound,
    AgentsTimeout,
    AgentsTokenInvalid,
    AgentsUpstreamError,
    AgentStatus,
    FakeAgentsClient,
)
from app.services import julia_agente_service as julia
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
        self.token_builder_agents: FakeAgentsClient | None = None
        self.token_builds: list[str] = []
        self.token_admin = FakeProductTokenAdmin()

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
        from app.routers.julia_agente_router import (
            get_agents_client_factory, get_agents_token_client_builder, get_julia_token_admin,
        )
        from app.routers.whatsapp_connections_router import get_waha_client_factory

        bind_consent_module_to_mock(world.root)
        scene = Scene(TestClient(app), world)
        scene.override = override_settings_factory

        def builder():
            def build(token: str):
                scene.token_builds.append(token)
                return scene.token_builder_agents or FakeAgentsClient()

            return build

        app.dependency_overrides[get_agents_client_factory] = lambda: (lambda org_id: world.agents)
        app.dependency_overrides[get_agents_token_client_builder] = builder
        app.dependency_overrides[get_waha_client_factory] = lambda: (lambda **kw: world.waha)
        app.dependency_overrides[get_julia_token_admin] = lambda: scene.token_admin
        override_settings_factory(
            encryption_key=ENCRYPTION_KEY, waha_webhook_hmac_secret="sekrit", redis_url="redis://fake:6379/0",
        )
        yield scene
        for dep in (get_agents_client_factory, get_agents_token_client_builder, get_waha_client_factory, get_julia_token_admin):
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
        ("put", f"{BASE}/token", {"token": "pk_12345678"}),
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
        assert set(data) == {"token_configurado", "status_agente", "erro", "agents_url"}

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
        assert admin.put(f"{BASE}/token", {"token": "pk_secret_value"}).status_code == 204
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

    def test_H3_empty_authorized_numbers_is_409_and_nothing_is_written(self, admin):
        _off_connection(admin.w, authorized_numbers=[])
        r = self._on(admin)
        assert r.status_code == 409 and "authorized_numbers_required" in r.text
        assert admin.conn()["agente_leads_ativo"] is False and admin.snapshot_ids() == set()

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

    def test_emptying_the_list_while_julia_is_on_is_409(self, admin):
        admin.w.seed_connection()
        r = admin.tc.patch(self.URL, json={"authorized_numbers": []}, headers=H)
        assert r.status_code == 409 and "authorized_numbers_required" in r.text
        assert admin.conn()["authorized_numbers"] == ["+5511999990000"]

    def test_blank_entries_count_as_empty(self, admin):
        admin.w.seed_connection()
        assert admin.tc.patch(self.URL, json={"authorized_numbers": [" "]}, headers=H).status_code == 409

    def test_a_non_empty_replacement_is_fine_while_julia_is_on(self, admin):
        admin.w.seed_connection()
        r = admin.tc.patch(self.URL, json={"authorized_numbers": ["+5511977770000"]}, headers=H)
        assert r.status_code == 200 and admin.conn()["authorized_numbers"] == ["+5511977770000"]

    def test_the_patch_is_written_through_the_org_staff_list(self, admin):
        """Owner 2026-10-21: staff is THE per-org list; `authorized_numbers` is its mirror, not a second list to edit."""
        admin.w.seed_connection()
        admin.w.sw.set_table_data("julia_staff", [])
        admin.w.sw.set_table_data("julia_numeros_bloqueados", [])
        r = admin.tc.patch(self.URL, json={"authorized_numbers": ["+55 11 97777-0000"]}, headers=H)
        assert r.status_code == 200
        linhas = admin.w.rows("julia_staff")
        assert [(x["telefone"], x["papel"], x["ativo"]) for x in linhas] == [("5511977770000", "operador", True)]
        assert admin.conn()["authorized_numbers"] == ["+5511977770000"]

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

    def test_the_DB_check_refuses_julia_on_over_an_empty_authorized_list(self, admin):
        """Migration 258's CHECK, enforced by the mock from the migration file itself
        (INSERT judges the whole row; a partial UPDATE is not judged by the mock)."""
        from noctusai_lib.testing.mocks import MockRowCheckViolation

        with pytest.raises(MockRowCheckViolation) as ei:
            admin.w.sw.table("whatsapp_connections").insert(self._row(authorized_numbers=[])).execute()
        assert "agente_exige_autorizados" in str(ei.value)

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


# ── PUT /token ──────────────────────────────────────────────────────────────
class TestToken:
    def test_a_valid_token_is_validated_against_the_status_route_then_stored_encrypted(self, admin):
        r = admin.put(f"{BASE}/token", {"token": "pk_live_abcdef"})
        assert r.status_code == 204 and r.content == b""
        assert admin.token_builds == ["pk_live_abcdef"]
        assert admin.token_builder_agents is None or admin.token_builder_agents.status_calls == ["julia"]
        # production's admin client is schema-pinned to social_wiring; the mock's is not, so the
        # row sits on the root client's `credentials` table here.
        row = admin.w.admin.table("credentials").select("*").eq("provider", "api_key:agents").execute().data[0]
        assert row["org_id"] == ORG_ID
        assert "pk_live_abcdef" not in str(row), "stored encrypted, never plaintext"
        assert julia.agents_token_for_org(ORG_ID, cfg=admin.w.cfg) == "pk_live_abcdef"

    def test_a_token_agents_refuses_is_422_token_invalido_and_is_not_stored(self, admin):
        admin.token_builder_agents = FakeAgentsClient(status_error=AgentsTokenInvalid(code="issuer_not_allowed"))
        r = admin.put(f"{BASE}/token", {"token": "pk_wrong_token"})
        assert r.status_code == 422 and "token_invalido" in r.text
        assert admin.w.admin.table("credentials").select("*").execute().data == []

    def test_a_token_agents_accepts_but_whose_agent_does_not_exist_yet_is_stored(self, admin):
        admin.token_builder_agents = FakeAgentsClient(status_error=AgentNotFound(code="agent_not_found"))
        assert admin.put(f"{BASE}/token", {"token": "pk_live_abcdef"}).status_code == 204

    def test_agents_being_down_is_502_and_nothing_is_stored(self, admin):
        admin.token_builder_agents = FakeAgentsClient(status_error=AgentsTimeout("down"))
        r = admin.put(f"{BASE}/token", {"token": "pk_live_abcdef"})
        assert handler_status(r) == 502 and "agents_indisponivel" in r.text
        assert admin.w.admin.table("credentials").select("*").execute().data == []

    @pytest.mark.parametrize("body", [{"token": "short"}, {"token": ""}, {}, {"token": "x" * 600}])
    def test_malformed_bodies_are_422(self, admin, body):
        assert admin.put(f"{BASE}/token", body).status_code == 422

    def test_the_token_never_reaches_the_logs_or_any_response(self, admin, caplog):
        with caplog.at_level("DEBUG"):
            r = admin.put(f"{BASE}/token", {"token": "pk_super_secret_value"})
            admin.get(BASE)
        assert "pk_super_secret_value" not in r.text
        assert all("pk_super_secret_value" not in rec.getMessage() for rec in caplog.records)

    def test_replacing_a_token_clears_a_stale_link_error(self, admin):
        julia.registrar_erro_link(ORG_ID, "token_invalido", cfg=admin.w.cfg)
        admin.put(f"{BASE}/token", {"token": "pk_live_abcdef"})
        assert julia.ler_erro_link(ORG_ID, cfg=admin.w.cfg) is None

    def test_a_token_is_per_org_org_B_does_not_see_org_As(self, admin):
        admin.put(f"{BASE}/token", {"token": "pk_live_abcdef"})
        assert julia.agents_token_for_org(OTHER_ORG_ID, cfg=admin.w.cfg) is None


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


# ── PUT /token also mints + pushes the Julia tools token (lais-build-contract 2.2) ──
class TestToolsToken:
    ROWS = lambda self, admin: admin.token_admin.rows.get("social_wiring", [])  # noqa: E731

    def test_a_valid_token_mints_the_scoped_tools_token_and_pushes_it_to_agents(self, admin):
        fake = FakeAgentsClient()
        admin.token_builder_agents = fake
        assert admin.put(f"{BASE}/token", {"token": "pk_live_abcdef"}).status_code == 204
        rows = self.ROWS(admin)
        assert len(rows) == 1
        row = rows[0]
        assert (row["org_id"], row["label"], row["issuer"]) == (ORG_ID, "agents · ferramentas julia", "agents")
        assert row["scopes"] == ["social-wiring:lais-tools"] and row["revoked_at"] is None
        exp = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
        assert timedelta(days=89) < exp - datetime.now(timezone.utc) <= timedelta(days=90, minutes=1)
        # the secret handed to agents is the one whose hash is stored -- and is never stored itself
        assert len(fake.ferramentas_tokens) == 1
        secret = fake.ferramentas_tokens[0]
        assert secret.startswith("pk_") and secret not in str(row)
        assert admin.token_admin.find_by_secret("social_wiring", secret) is not None
        assert admin.get(BASE).json()["data"]["erro"] is None

    def test_the_tools_token_never_reaches_the_response_or_the_logs(self, admin, caplog):
        fake = FakeAgentsClient()
        admin.token_builder_agents = fake
        with caplog.at_level("DEBUG"):
            r = admin.put(f"{BASE}/token", {"token": "pk_live_abcdef"})
            body = admin.get(BASE).text
        secret = fake.ferramentas_tokens[0]
        assert secret not in r.text and secret not in body
        assert all(secret not in rec.getMessage() for rec in caplog.records)

    def test_a_push_failure_is_still_204_records_the_new_erro_and_revokes_the_undelivered_token(self, admin):
        admin.token_builder_agents = FakeAgentsClient(ferramentas_token_error=AgentsUpstreamError(code="encryption_not_configured"))
        assert admin.put(f"{BASE}/token", {"token": "pk_live_abcdef"}).status_code == 204
        assert julia.agents_token_for_org(ORG_ID, cfg=admin.w.cfg) == "pk_live_abcdef"  # channel token IS stored
        assert admin.get(BASE).json()["data"]["erro"] == "Ferramentas da Julia indisponíveis — reenvie o token."
        assert [r["revoked_at"] is not None for r in self.ROWS(admin)] == [True]  # no orphan secret stays valid

    def test_a_mint_failure_is_still_204_with_the_same_erro(self, admin):
        admin.token_admin.fail_mint = True
        assert admin.put(f"{BASE}/token", {"token": "pk_live_abcdef"}).status_code == 204
        assert admin.get(BASE).json()["data"]["erro"] == "Ferramentas da Julia indisponíveis — reenvie o token."
        assert self.ROWS(admin) == []

    def test_a_later_good_paste_clears_the_erro(self, admin):
        admin.token_builder_agents = FakeAgentsClient(ferramentas_token_error=AgentsUpstreamError())
        admin.put(f"{BASE}/token", {"token": "pk_live_abcdef"})
        admin.token_builder_agents = FakeAgentsClient()
        admin.put(f"{BASE}/token", {"token": "pk_live_abcdef"})
        assert admin.get(BASE).json()["data"]["erro"] is None

    def test_a_refused_channel_token_mints_nothing(self, admin):
        admin.token_builder_agents = FakeAgentsClient(status_error=AgentsTokenInvalid())
        assert admin.put(f"{BASE}/token", {"token": "pk_wrong_token"}).status_code == 422
        assert self.ROWS(admin) == []

    def test_repasting_retires_the_previous_tools_token_only_after_the_new_one_is_delivered(self, admin):
        admin.token_builder_agents = FakeAgentsClient()
        admin.put(f"{BASE}/token", {"token": "pk_live_abcdef"})
        old_id = self.ROWS(admin)[0]["id"]
        # the scoped client reads `api_tokens`: mirror the fake's row there (production: same table)
        admin.w.sw.table("api_tokens").insert(dict(self.ROWS(admin)[0])).execute()
        admin.put(f"{BASE}/token", {"token": "pk_live_abcdef"})
        by_id = {r["id"]: r for r in self.ROWS(admin)}
        assert len(by_id) == 2 and by_id[old_id]["revoked_at"] is not None
        assert [r for i, r in by_id.items() if i != old_id][0]["revoked_at"] is None

    def test_the_tools_token_is_per_org(self, admin):
        admin.token_builder_agents = FakeAgentsClient()
        admin.put(f"{BASE}/token", {"token": "pk_live_abcdef"})
        assert {r["org_id"] for r in self.ROWS(admin)} == {ORG_ID}
