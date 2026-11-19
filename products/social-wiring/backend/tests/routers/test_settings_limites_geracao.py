"""Daily generation limits (geracao-contract.md §9.4.1): the resolver, the API, the event, every cap site.

Real seams only: the seed credential chain reads through its external Supabase boundary
(`noctusai_lib.testing.credentials.patch_credentials_to_mock`) over a `MockSupabaseClient` holding the
`org_settings` / `platform_settings` rows; the env tier is the process environment (`monkeypatch.setenv`, an
external input); the write RPC is migration 361's contract fake (`tests/support/rpc_fakes.py`, pinned on a real
Postgres by `tests/test_migration_361_limites_geracao.py`).

**Strict `== 401` / `== 403`, never `in (...)`** per `KB § PATTERNS/compliance/auth-boundary-false-green.md`.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.testing import (
    TEST_USER_ID,
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    bind_consent_module_to_mock,
)
from noctusai_lib.testing.credentials import patch_credentials_to_mock

from app.dependencies import coerce_org_uuid
from app.modules.media_creation import limites_geracao as lg

URL = "/api/settings/limites-geracao"
ORG_RAW = "test-org-123"
ORG = str(coerce_org_uuid(ORG_RAW))
CHAVE = "roteiros_dia_usuario"
EVENTOS = "cs_limite_geracao_eventos"


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _db(*, org_rows=(), platform_rows=(), org_role: str | None = "owner") -> MockSupabaseClient:
    sb = MockSupabaseClient()
    sb.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id=ORG_RAW, org_role=org_role)))
    sb.set_table_data("noctus_users", [{"id": TEST_USER_ID, "org_id": ORG_RAW, "org_role": org_role}])
    sb.set_table_data("org_settings", [dict(r) for r in org_rows])
    sb.set_table_data("platform_settings", [dict(r) for r in platform_rows])
    return sb


# ─── the resolver: precedence + bounds ──────────────────────────────────


class TestResolver:
    cfg = SimpleNamespace(**{s.chave: s.padrao_codigo for s in lg.LIMITES})

    def _resolver(self, sb, org=ORG):
        with patch_credentials_to_mock(sb):
            return lg.limite_geracao(CHAVE, org, self.cfg)

    def test_config_default_when_no_tier_answers(self, monkeypatch):
        monkeypatch.delenv(CHAVE.upper(), raising=False)
        assert self._resolver(_db()) == 20

    def test_env_beats_config(self, monkeypatch):
        monkeypatch.setenv(CHAVE.upper(), "33")
        assert self._resolver(_db()) == 33

    def test_platform_beats_env(self, monkeypatch):
        monkeypatch.setenv(CHAVE.upper(), "33")
        sb = _db(platform_rows=[{"key": CHAVE, "value": "44"}])
        assert self._resolver(sb) == 44

    def test_org_override_beats_platform(self, monkeypatch):
        monkeypatch.setenv(CHAVE.upper(), "33")
        sb = _db(org_rows=[{"org_id": ORG, "key": CHAVE, "value": "55"}], platform_rows=[{"key": CHAVE, "value": "44"}])
        assert self._resolver(sb) == 55

    def test_another_orgs_override_does_not_apply(self, monkeypatch):
        monkeypatch.delenv(CHAVE.upper(), raising=False)
        sb = _db(org_rows=[{"org_id": "outra-org", "key": CHAVE, "value": "55"}])
        assert self._resolver(sb) == 20

    @pytest.mark.parametrize("ruim", ["0", "-4", "abc", "201", "1e3"])
    def test_an_invalid_override_falls_back_to_the_default_never_unlimited(self, monkeypatch, ruim):
        monkeypatch.delenv(CHAVE.upper(), raising=False)
        sb = _db(org_rows=[{"org_id": ORG, "key": CHAVE, "value": ruim}], platform_rows=[{"key": CHAVE, "value": "44"}])
        assert self._resolver(sb) == 44

    def test_the_ceiling_is_ten_times_the_code_default_and_finite(self):
        assert {s.chave: s.maximo for s in lg.LIMITES} == {
            "headline_lotes_dia_usuario": 300, "headlines_sugeridas_por_dia_marca": 50, "roteiros_dia_usuario": 200,
            "legendas_dia_usuario": 400, "chat_mensagens_dia_usuario": 1000, "chat_mensagens_dia_org": 4000,
        }

    def test_the_code_defaults_equal_app_config(self):
        from app.config import SocialWiringSettings

        campos = SocialWiringSettings.model_fields
        assert {s.chave: s.padrao_codigo for s in lg.LIMITES} == {s.chave: campos[s.chave].default for s in lg.LIMITES}


# ─── every cap site goes through the resolver ───────────────────────────


def test_no_cap_site_reads_a_limit_off_the_config_directly():
    """AST: under app/, an attribute named like one of the six limits is read only inside the resolver module."""
    app_dir = Path(__file__).resolve().parents[2] / "app"
    resolver = (app_dir / "modules" / "media_creation" / "limites_geracao.py").resolve()
    achados = []
    for f in app_dir.rglob("*.py"):
        if f.resolve() in (resolver, (app_dir / "config.py").resolve()):
            continue
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and node.attr in lg.CHAVES:
                achados.append(f"{f.relative_to(app_dir)}:{node.lineno} .{node.attr}")
    assert achados == []


def test_the_scanned_tree_really_uses_the_resolver():
    """The AST test above would pass on an empty tree; each limit is read through `limite_geracao` somewhere."""
    app_dir = Path(__file__).resolve().parents[2] / "app" / "modules" / "media_creation"
    usadas: set[str] = set()
    for f in app_dir.rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "limite_geracao"
                    and node.args and isinstance(node.args[0], ast.Constant)):
                usadas.add(node.args[0].value)
    assert usadas == set(lg.CHAVES)


# ─── the API ────────────────────────────────────────────────────────────


def _client_for(sb: MockSupabaseClient):
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=sb),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=sb),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=sb),
        patch_credentials_to_mock(sb),
    ):
        from app.main import app

        bind_consent_module_to_mock(sb)
        tc = TestClient(app, raise_server_exceptions=True)
        tc.sb = sb  # type: ignore[attr-defined]
        yield tc


@pytest.fixture
def admin_client(monkeypatch):
    for s in lg.LIMITES:
        monkeypatch.delenv(s.chave.upper(), raising=False)
    yield from _client_for(_db(org_role="owner"))


@pytest.fixture
def member_client():
    yield from _client_for(_db(org_role=None))


def _por_chave(body: dict) -> dict:
    return {i["chave"]: i for i in body["items"]}


def _eventos(tc) -> list[dict]:
    return tc.sb.table(EVENTOS).select("*").execute().data or []


class TestAuth:
    def test_get_without_a_token_is_401(self, admin_client):
        assert admin_client.get(URL).status_code == 401

    def test_put_without_a_token_is_401(self, admin_client):
        assert admin_client.put(URL, json={"limites": {CHAVE: 30}}).status_code == 401

    def test_a_member_can_read(self, member_client):
        assert member_client.get(URL, headers=_auth()).status_code == 200

    def test_a_member_cannot_write(self, member_client):
        r = member_client.put(URL, json={"limites": {CHAVE: 30}}, headers=_auth())
        assert r.status_code == 403
        assert _eventos(member_client) == []
        assert member_client.sb.table("org_settings").select("*").execute().data == []

    def test_an_admin_can_write(self):
        yield_ = _client_for(_db(org_role="admin"))
        tc = next(yield_)
        try:
            assert tc.put(URL, json={"limites": {CHAVE: 30}}, headers=_auth()).status_code == 200
        finally:
            yield_.close()


class TestLeitura:
    def test_every_limit_with_value_default_and_ceiling(self, admin_client):
        body = admin_client.get(URL, headers=_auth()).json()
        assert body["total"] == 6
        item = _por_chave(body)[CHAVE]
        assert item == {
            "chave": CHAVE, "rotulo": "Roteiros por pessoa", "descricao": item["descricao"], "escopo": "usuario",
            "valor": 20, "padrao": 20, "maximo": 200, "personalizado": False,
        }

    def test_a_platform_default_is_the_padrao_not_an_override(self):
        gen = _client_for(_db(platform_rows=[{"key": CHAVE, "value": "25"}]))
        tc = next(gen)
        try:
            item = _por_chave(tc.get(URL, headers=_auth()).json())[CHAVE]
            assert (item["valor"], item["padrao"], item["personalizado"]) == (25, 25, False)
        finally:
            gen.close()


class TestEscrita:
    def test_put_overrides_records_the_event_and_returns_the_whole_list(self, admin_client):
        r = admin_client.put(URL, json={"limites": {CHAVE: 50}}, headers=_auth())
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 6
        assert _por_chave(body)[CHAVE] | {"descricao": ""} == {
            "chave": CHAVE, "rotulo": "Roteiros por pessoa", "descricao": "", "escopo": "usuario",
            "valor": 50, "padrao": 20, "maximo": 200, "personalizado": True,
        }
        [ev] = _eventos(admin_client)
        assert (ev["org_id"], ev["chave"], ev["evento"], ev["valor_anterior"], ev["valor_novo"], ev["ator_id"]) == (
            ORG, CHAVE, "limite_definido", None, 50, TEST_USER_ID,
        )

    def test_a_second_raise_records_the_old_value(self, admin_client):
        admin_client.put(URL, json={"limites": {CHAVE: 50}}, headers=_auth())
        admin_client.put(URL, json={"limites": {CHAVE: 80}}, headers=_auth())
        assert [(e["valor_anterior"], e["valor_novo"]) for e in _eventos(admin_client)] == [(None, 50), (50, 80)]

    def test_the_new_value_is_served_to_the_cap_sites_at_once(self, admin_client):
        admin_client.put(URL, json={"limites": {CHAVE: 50}}, headers=_auth())
        cfg = SimpleNamespace(**{s.chave: s.padrao_codigo for s in lg.LIMITES})
        assert lg.limite_geracao(CHAVE, ORG, cfg) == 50

    def test_null_restores_the_default(self, admin_client):
        admin_client.put(URL, json={"limites": {CHAVE: 50}}, headers=_auth())
        body = admin_client.put(URL, json={"limites": {CHAVE: None}}, headers=_auth()).json()
        item = _por_chave(body)[CHAVE]
        assert (item["valor"], item["personalizado"]) == (20, False)
        assert [e["evento"] for e in _eventos(admin_client)] == ["limite_definido", "limite_restaurado"]

    def test_several_keys_in_one_save(self, admin_client):
        body = admin_client.put(
            URL, json={"limites": {CHAVE: 21, "chat_mensagens_dia_org": 1000}}, headers=_auth()
        ).json()
        por = _por_chave(body)
        assert (por[CHAVE]["valor"], por["chat_mensagens_dia_org"]["valor"]) == (21, 1000)
        assert len(_eventos(admin_client)) == 2

    @pytest.mark.parametrize("limites", [
        {CHAVE: 201},                       # above the ceiling
        {CHAVE: 0},                         # never zero
        {CHAVE: -1},
        {CHAVE: "30"},                      # a string is not an integer
        {CHAVE: 30.5},
        {CHAVE: True},
        {"limite_que_nao_existe": 5},
        {},                                 # nothing to save
        {CHAVE: 30, "chat_mensagens_dia_org": 999_999},  # one bad key refuses the whole body
    ])
    def test_out_of_bounds_or_malformed_is_422_and_writes_nothing(self, admin_client, limites):
        r = admin_client.put(URL, json={"limites": limites}, headers=_auth())
        assert r.status_code == 422
        assert _eventos(admin_client) == []
        assert admin_client.sb.table("org_settings").select("*").execute().data == []
