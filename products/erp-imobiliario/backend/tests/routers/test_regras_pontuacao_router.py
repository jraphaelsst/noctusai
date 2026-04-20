"""
Tests for the Regras Pontuação router + resolve_rule() precedence.

Focuses on the precedence chain — period-specific rules override
org defaults override platform defaults — since that's the tricky
part. CRUD coverage is intentionally thinner.
"""
from __future__ import annotations

import pytest

from app.services import regras_pontuacao_service as svc


# ── resolve_rule — precedence chain (pure logic, mocked DB) ─────────

class _StubTable:
    """Minimal stand-in that returns a fixed rowset for .execute()."""
    def __init__(self, rows):
        self._rows = rows

    def select(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def execute(self):
        class R:
            pass
        r = R()
        r.data = self._rows
        return r


class _StubDb:
    def __init__(self, rows):
        self._rows = rows

    def table(self, name):
        return _StubTable(self._rows)


class TestResolvePrecedence:
    def _rows(self):
        # Four rules for (venda, padrao) covering the full precedence matrix.
        return [
            {"id": "platform_default",   "org_id": None,    "vigencia_periodo_id": None,    "evento_tipo": "venda", "modalidade": "padrao", "pontos": 50},
            {"id": "org_default",        "org_id": "org-1", "vigencia_periodo_id": None,    "evento_tipo": "venda", "modalidade": "padrao", "pontos": 60},
            {"id": "platform_period",    "org_id": None,    "vigencia_periodo_id": "per-1", "evento_tipo": "venda", "modalidade": "padrao", "pontos": 70},
            {"id": "org_period",         "org_id": "org-1", "vigencia_periodo_id": "per-1", "evento_tipo": "venda", "modalidade": "padrao", "pontos": 80},
        ]

    def test_org_period_wins(self):
        db = _StubDb(self._rows())
        r = svc.resolve_rule(db, org_id="org-1", periodo_id="per-1", evento_tipo="venda", modalidade="padrao")
        assert r["id"] == "org_period"

    def test_platform_period_wins_when_no_org_period(self):
        rows = [r for r in self._rows() if r["id"] != "org_period"]
        db = _StubDb(rows)
        r = svc.resolve_rule(db, org_id="org-1", periodo_id="per-1", evento_tipo="venda", modalidade="padrao")
        assert r["id"] == "platform_period"

    def test_org_default_wins_when_no_period_scoped(self):
        rows = [r for r in self._rows() if r["id"] not in ("org_period", "platform_period")]
        db = _StubDb(rows)
        r = svc.resolve_rule(db, org_id="org-1", periodo_id="per-1", evento_tipo="venda", modalidade="padrao")
        assert r["id"] == "org_default"

    def test_platform_default_is_fallback(self):
        rows = [r for r in self._rows() if r["id"] == "platform_default"]
        db = _StubDb(rows)
        r = svc.resolve_rule(db, org_id="org-1", periodo_id="per-1", evento_tipo="venda", modalidade="padrao")
        assert r["id"] == "platform_default"

    def test_none_returned_when_no_rule_matches(self):
        db = _StubDb([])
        r = svc.resolve_rule(db, org_id="org-1", periodo_id="per-1", evento_tipo="venda", modalidade="padrao")
        assert r is None

    def test_invalid_evento_rejected(self):
        db = _StubDb([])
        with pytest.raises(ValueError):
            svc.resolve_rule(db, org_id=None, periodo_id=None, evento_tipo="bogus", modalidade="padrao")


# ── Router tests ────────────────────────────────────────────────────

class TestListarRegras:
    def test_list_200(self, client):
        client._mock_supabase.set_table_data("regras_pontuacao", [
            {"id": "r1", "org_id": None, "evento_tipo": "venda", "modalidade": "padrao", "pontos": 50},
        ])
        resp = client.get("/api/metas/regras-pontuacao")
        assert resp.status_code == 200

    def test_filter_by_evento_tipo(self, client):
        client._mock_supabase.set_table_data("regras_pontuacao", [])
        resp = client.get("/api/metas/regras-pontuacao?evento_tipo=captacao")
        assert resp.status_code == 200


class TestResolveEndpoint:
    def test_resolve_returns_rule(self, client):
        client._mock_supabase.set_table_data("regras_pontuacao", [
            {"id": "r1", "org_id": None, "vigencia_periodo_id": None,
             "evento_tipo": "venda", "modalidade": "padrao", "pontos": 50},
        ])
        resp = client.get("/api/metas/regras-pontuacao/resolve?evento_tipo=venda&modalidade=padrao")
        assert resp.status_code == 200
        assert float(resp.json()["data"]["pontos"]) == 50

    def test_resolve_404_when_no_rule(self, client):
        client._mock_supabase.set_table_data("regras_pontuacao", [])
        resp = client.get("/api/metas/regras-pontuacao/resolve?evento_tipo=venda")
        assert resp.status_code == 404

    def test_resolve_requires_evento_tipo(self, client):
        resp = client.get("/api/metas/regras-pontuacao/resolve")
        assert resp.status_code == 422

    def test_resolve_invalid_evento_rejected(self, client):
        resp = client.get("/api/metas/regras-pontuacao/resolve?evento_tipo=bogus")
        assert resp.status_code == 422


class TestUpsertRegra:
    def test_create_org_scope(self, client):
        client._mock_supabase.set_table_data("regras_pontuacao", {
            "id": "r-new", "evento_tipo": "venda", "modalidade": "padrao", "pontos": 60,
        })
        resp = client.post("/api/metas/regras-pontuacao", json={
            "evento_tipo": "venda",
            "modalidade": "padrao",
            "pontos": 60,
        })
        assert resp.status_code == 201

    def test_reject_invalid_evento(self, client):
        resp = client.post("/api/metas/regras-pontuacao", json={
            "evento_tipo": "dance",
            "modalidade": "padrao",
            "pontos": 10,
        })
        assert resp.status_code == 422

    def test_reject_invalid_modalidade(self, client):
        resp = client.post("/api/metas/regras-pontuacao", json={
            "evento_tipo": "venda",
            "modalidade": "suprema",
            "pontos": 10,
        })
        assert resp.status_code == 422


class TestDeletarRegra:
    def test_delete_existing(self, client):
        client._mock_supabase.set_table_data("regras_pontuacao", [{"id": "r1"}])
        resp = client.delete("/api/metas/regras-pontuacao/r1")
        assert resp.status_code == 200
