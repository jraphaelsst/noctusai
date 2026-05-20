"""Tests for the Vista Showcase router — /api/vista-showcase/*

Covers:
- Admin gating (403 for non-admin, 200 for admin/owner/platform_admin)
- Config error → 503 when Vista creds are missing
- Tab catalog reports `not_configured` for live tabs when creds missing
- Per-tab fetch path stubs the Vista HTTP layer (we test our adapter, not Vista's API)
- Audit-log row written on every successful AND failed Vista call
- Pagination envelope shape
- Error mapping: 401 → 403, 404 → 404, timeout → 504, upstream → 502

Vista is mocked at the `httpx.AsyncClient.request` boundary — that's the only
place where bytes leave our process. Per CLAUDE.md "no monkey-patching of
our own code in tests", we mock the EXTERNAL boundary, never our own
client/normalizer/service.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


# ---------------------------------------------------------------------------
# Fixtures — small layer over the shared `client` fixture in conftest.py
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_client(client):
    """Promote the default mock user to ERP admin."""
    user = client._mock_supabase.auth.get_user.return_value.user
    user.user_metadata = {**(user.user_metadata or {}), "erp_role": "admin"}
    return client


@pytest.fixture
def non_admin_client(client):
    user = client._mock_supabase.auth.get_user.return_value.user
    user.user_metadata = {**(user.user_metadata or {}), "erp_role": "corretor"}
    return client


def _vista_response(status: int = 200, body: Any = None, *, text: str = "") -> MagicMock:
    """Build a fake httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.text = text or (json.dumps(body) if body is not None else "")
    resp.json = MagicMock(return_value=body if body is not None else {})
    return resp


def _patch_vista(*, return_value=None, side_effect=None):
    """Patch the only place Vista bytes leave the process."""
    target = "httpx.AsyncClient.request"
    if side_effect is not None:
        return patch(target, new_callable=AsyncMock, side_effect=side_effect)
    return patch(target, new_callable=AsyncMock, return_value=return_value)


def _set_vista_settings(monkeypatch, base_url="https://test.vistahost.com.br", api_key="test-key"):
    """Wire test Vista settings without touching the real env file."""
    from app.config import settings
    monkeypatch.setattr(settings, "vista_base_url", base_url, raising=False)
    monkeypatch.setattr(settings, "vista_api_key", api_key, raising=False)


# ---------------------------------------------------------------------------
# Admin gating
# ---------------------------------------------------------------------------


class TestAdminGating:
    def test_non_admin_blocked(self, non_admin_client, monkeypatch):
        _set_vista_settings(monkeypatch)
        resp = non_admin_client.get("/api/vista-showcase/tabs")
        assert resp.status_code == 403

    def test_owner_allowed(self, client, monkeypatch):
        _set_vista_settings(monkeypatch)
        user = client._mock_supabase.auth.get_user.return_value.user
        user.user_metadata = {**(user.user_metadata or {}), "erp_role": "owner"}
        resp = client.get("/api/vista-showcase/tabs")
        assert resp.status_code == 200

    def test_platform_admin_allowed(self, client, monkeypatch):
        _set_vista_settings(monkeypatch)
        user = client._mock_supabase.auth.get_user.return_value.user
        user.user_metadata = {**(user.user_metadata or {}), "noctus_role": "admin"}
        resp = client.get("/api/vista-showcase/tabs")
        assert resp.status_code == 200

    def test_admin_allowed(self, admin_client):
        # tabs endpoint never hits Vista when creds are present (returns
        # the static catalog), so no patch needed
        resp = admin_client.get("/api/vista-showcase/tabs")
        assert resp.status_code == 200

    # ------------------------------------------------------------------
    # SSO short-circuit gap tests (Phase 7 vista_showcase audit)
    # ------------------------------------------------------------------
    # `resolve_sso_role(user)` (seed `noctusai_lib.api.auth:118`) has TWO
    # short-circuit paths to `"platform_admin"`:
    #
    #   Path 1: `user_metadata.org_role in ("owner", "admin")`
    #   Path 2: `user_metadata.noctus_role == "admin"`
    #
    # Phase 0 audit + Phase 3 wiring (PROJECT.md Q-B / Q-F): the bespoke
    # `require_admin` body was retired in favor of the seed
    # `make_require_role(get_current_user, get_erp_user_role)` composition.
    # `get_erp_user_role` (`app/dependencies.py:99`) calls `resolve_sso_role`
    # FIRST so the SSO short-circuit composes with the role gate.
    #
    # Existing `test_platform_admin_allowed` exercises Path 2 only. The
    # following two tests close the Path 1 gap (org_role=owner / admin)
    # + pin the negative case (no SSO + no erp_role → 403). Without these,
    # a regression that disabled `resolve_sso_role`'s Path 1 would land
    # silently — admin owners coming via Core SSO would lose vista
    # access without any test catching it.

    def test_sso_org_role_owner_allowed(self, client, monkeypatch):
        """SSO Path 1a: `org_role == "owner"` → short-circuit to
        `platform_admin` → `require_role(*ALLOWED_ADMIN_ROLES)` passes."""
        _set_vista_settings(monkeypatch)
        user = client._mock_supabase.auth.get_user.return_value.user
        # Only org_role set — NO erp_role/noctus_role. Tests Path 1 in
        # isolation from Path 2.
        user.user_metadata = {"org_role": "owner"}
        resp = client.get("/api/vista-showcase/tabs")
        assert resp.status_code == 200

    def test_sso_org_role_admin_allowed(self, client, monkeypatch):
        """SSO Path 1b: `org_role == "admin"` → short-circuit to
        `platform_admin` → admin gate passes (org-tier admin, not a
        NoctusAI platform admin)."""
        _set_vista_settings(monkeypatch)
        user = client._mock_supabase.auth.get_user.return_value.user
        user.user_metadata = {"org_role": "admin"}
        resp = client.get("/api/vista-showcase/tabs")
        assert resp.status_code == 200

    def test_no_role_metadata_blocked(self, client, monkeypatch):
        """Negative pin: a user with NO `org_role`, NO `noctus_role`,
        NO `erp_role` is rejected with 403. `get_erp_user_role` returns
        the `"user"` sentinel which is not in `ALLOWED_ADMIN_ROLES`."""
        _set_vista_settings(monkeypatch)
        user = client._mock_supabase.auth.get_user.return_value.user
        user.user_metadata = {}  # explicit empty — no SSO, no ERP role
        resp = client.get("/api/vista-showcase/tabs")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tabs catalog
# ---------------------------------------------------------------------------


class TestTabs:
    def test_with_creds_reports_live(self, admin_client, monkeypatch):
        _set_vista_settings(monkeypatch)
        resp = admin_client.get("/api/vista-showcase/tabs")
        assert resp.status_code == 200
        body = resp.json()
        tabs = {t["tab"]: t for t in body["tabs"]}
        assert tabs["imoveis"]["status"] == "live"
        assert tabs["clientes"]["status"] == "permission_denied"
        # Phase 4 live re-probe (2026-05-02) confirmed /imoveis/fotos returns
        # 404 on this tenant, not 401 — adjusted from Phase 1's misclassification.
        assert tabs["fotos"]["status"] == "not_found"
        assert "diagnostico" in tabs

    def test_without_creds_reports_not_configured(self, admin_client, monkeypatch):
        _set_vista_settings(monkeypatch, base_url=None, api_key=None)
        resp = admin_client.get("/api/vista-showcase/tabs")
        assert resp.status_code == 200
        tabs = {t["tab"]: t for t in resp.json()["tabs"]}
        # Without creds, every data tab flips to not_configured (the
        # "permission_denied" note would be misleading). Diagnóstico stays
        # live so the user can run a probe to confirm the absence.
        assert tabs["imoveis"]["status"] == "not_configured"
        assert tabs["clientes"]["status"] == "not_configured"
        assert tabs["diagnostico"]["status"] == "live"


# ---------------------------------------------------------------------------
# Imóveis happy path
# ---------------------------------------------------------------------------


class TestImoveis:
    def test_listar_happy_path(self, admin_client, monkeypatch):
        _set_vista_settings(monkeypatch)
        vista_payload = {
            "CA2830": {
                "Codigo": "CA2830",
                "TituloSite": "Casa em Cotia",
                "Cidade": "Cotia",
                "Bairro": "Granja Viana",
                "Status": "ATIVO",
                "Categoria": "Casa",
                "ValorVenda": "1250000.00",
                "Dormitorios": "3",
                "Foto": "https://cdn.vista/CA2830.jpg",
            },
            "TE0080": {"Codigo": "TE0080", "Cidade": "Cotia", "Categoria": "Terreno"},
            "total": 1784,
            "paginas": 892,
            "pagina": 1,
            "quantidade": 2,
        }
        with _patch_vista(return_value=_vista_response(200, vista_payload)):
            resp = admin_client.get("/api/vista-showcase/imoveis?page=1&page_size=2")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tab"] == "imoveis"
        assert body["pagination"]["total"] == 1784
        assert body["pagination"]["pagina"] == 1
        assert len(body["items"]) == 2
        codes = {it["codigo"] for it in body["items"]}
        assert codes == {"CA2830", "TE0080"}
        # Audit log was written
        assert admin_client._mock_log.call_count == 1
        kwargs = admin_client._mock_log.call_args.kwargs
        assert kwargs["tipo_acao"] == "consulta_externa"
        assert kwargs["tipo_entidade"] == "integracao_vista"

    def test_filter_passthrough(self, admin_client, monkeypatch):
        """Filter query params reach the Vista request as a `pesquisa.filter`."""
        _set_vista_settings(monkeypatch)
        with _patch_vista(return_value=_vista_response(200, {"total": 0, "paginas": 0, "pagina": 1, "quantidade": 0})) as m:
            resp = admin_client.get(
                "/api/vista-showcase/imoveis?status=ATIVO&cidade=Cotia&bairro=Centro"
            )
        assert resp.status_code == 200
        # Inspect the call: pesquisa is JSON-encoded inside `params`
        call = m.call_args
        params = call.kwargs.get("params") or {}
        pesquisa = json.loads(params["pesquisa"])
        assert pesquisa["filter"] == {"Status": "ATIVO", "Cidade": "Cotia", "Bairro": "Centro"}

    def test_detalhes_happy_path(self, admin_client, monkeypatch):
        _set_vista_settings(monkeypatch)
        # Two calls: prefetch listing + detalhes. We need to alternate responses.
        listing_resp = _vista_response(200, {
            "CA2830": {"Codigo": "CA2830", "Foto": "https://cdn.vista/CA2830.jpg"},
            "total": 1, "paginas": 1, "pagina": 1, "quantidade": 1,
        })
        detalhes_resp = _vista_response(200, {
            "Codigo": "CA2830",
            "TituloSite": "Casa em Cotia",
            "Caracteristicas": {"Piscina": "Sim", "Lareira": "Sim"},
        })
        with _patch_vista(side_effect=[listing_resp, detalhes_resp]):
            resp = admin_client.get("/api/vista-showcase/imoveis/CA2830")
        assert resp.status_code == 200
        body = resp.json()
        item = body["items"][0]
        assert item["codigo"] == "CA2830"
        assert item["caracteristicas"]["Piscina"] == "Sim"
        # `Foto` came from the listing prefetch since detalhes doesn't expose it
        assert item["base"]["foto_url"] == "https://cdn.vista/CA2830.jpg"
        # Two audit-log rows: one for listing prefetch, one for detalhes
        assert admin_client._mock_log.call_count == 2


# ---------------------------------------------------------------------------
# Usuários + Agência tabs
# ---------------------------------------------------------------------------


class TestUsuariosAgencias:
    def test_usuarios(self, admin_client, monkeypatch):
        _set_vista_settings(monkeypatch)
        payload = {
            "U001": {"Codigo": "U001", "Nome": "Ana", "Email": "ana@one.com", "Setor": "Vendas"},
            "U002": {"Codigo": "U002", "Nome": "Bruno", "Email": "bruno@one.com"},
        }
        with _patch_vista(return_value=_vista_response(200, payload)):
            resp = admin_client.get("/api/vista-showcase/usuarios")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 2
        assert {it["codigo"] for it in items} == {"U001", "U002"}

    def test_agencias(self, admin_client, monkeypatch):
        _set_vista_settings(monkeypatch)
        payload = {
            "A001": {"Codigo": "A001", "Nome": "ONE", "Cidade": "Cotia"},
        }
        with _patch_vista(return_value=_vista_response(200, payload)):
            resp = admin_client.get("/api/vista-showcase/agencias")
        assert resp.status_code == 200
        assert resp.json()["items"][0]["nome"] == "ONE"


# ---------------------------------------------------------------------------
# Error mapping + audit-on-failure
# ---------------------------------------------------------------------------


class TestErrorMapping:
    def test_no_creds_503(self, admin_client, monkeypatch):
        _set_vista_settings(monkeypatch, base_url=None, api_key=None)
        resp = admin_client.get("/api/vista-showcase/imoveis")
        assert resp.status_code == 503

    def test_401_maps_to_403(self, admin_client, monkeypatch):
        _set_vista_settings(monkeypatch)
        with _patch_vista(return_value=_vista_response(401, text="Permissão Negada")):
            resp = admin_client.get("/api/vista-showcase/imoveis")
        assert resp.status_code == 403
        assert admin_client._mock_log.call_count == 1
        assert admin_client._mock_log.call_args.kwargs["descricao"].startswith("ERRO")

    def test_404_maps_to_404(self, admin_client, monkeypatch):
        _set_vista_settings(monkeypatch)
        with _patch_vista(return_value=_vista_response(404, text="not found")):
            resp = admin_client.get("/api/vista-showcase/imoveis")
        assert resp.status_code == 404

    def test_timeout_maps_to_504(self, admin_client, monkeypatch):
        _set_vista_settings(monkeypatch)
        with _patch_vista(side_effect=httpx.TimeoutException("slow")):
            resp = admin_client.get("/api/vista-showcase/imoveis")
        assert resp.status_code == 504

    def test_upstream_5xx_maps_to_502(self, admin_client, monkeypatch):
        _set_vista_settings(monkeypatch)
        with _patch_vista(return_value=_vista_response(500, text="oops")):
            resp = admin_client.get("/api/vista-showcase/imoveis")
        assert resp.status_code == 502


# ---------------------------------------------------------------------------
# Diagnóstico
# ---------------------------------------------------------------------------


class TestDiagnostico:
    def test_with_creds_runs_probes(self, admin_client, monkeypatch):
        _set_vista_settings(monkeypatch)
        # All 7 probes succeed (200) — keep the mock generic.
        ok = _vista_response(200, {"total": 0, "paginas": 0, "pagina": 1, "quantidade": 0})
        with _patch_vista(return_value=ok):
            resp = admin_client.get("/api/vista-showcase/diagnostico")
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is True
        assert body["tenant_base_url"].startswith("https://")
        assert len(body["probes"]) >= 4  # at least 4 known endpoints

    def test_without_creds_reports_unconfigured(self, admin_client, monkeypatch):
        _set_vista_settings(monkeypatch, base_url=None, api_key=None)
        resp = admin_client.get("/api/vista-showcase/diagnostico")
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is False
        assert body["probes"] == []
