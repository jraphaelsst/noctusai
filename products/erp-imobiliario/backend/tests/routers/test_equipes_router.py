"""
Tests for the Equipes router — /api/metas/equipes

Covers team CRUD + membership management. Auth and RLS are mocked at the
client layer; these tests verify endpoint wiring, payload validation,
and happy-path shape. Real RLS behavior is exercised by
tests/realdb/test_metas_realdb.py.
"""
from __future__ import annotations

import pytest


# ── Team endpoints ──────────────────────────────────────────────────

class TestListarEquipes:
    def test_list_returns_200(self, client):
        client._mock_supabase.set_table_data("equipes", [
            {"id": "e1", "nome": "DRAGÃO", "cor": "#E63946", "ativo": True},
            {"id": "e2", "nome": "LEÃO", "cor": "#F1C40F", "ativo": True},
            {"id": "e3", "nome": "ÁGUIA", "cor": "#3498DB", "ativo": True},
        ])
        resp = client.get("/api/metas/equipes")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_includes_inactive_when_flag_false(self, client):
        client._mock_supabase.set_table_data("equipes", [])
        resp = client.get("/api/metas/equipes?ativas_apenas=false")
        assert resp.status_code == 200


class TestCriarEquipe:
    def test_create_team(self, client):
        client._mock_supabase.set_table_data("equipes", {
            "id": "e-new",
            "nome": "FÊNIX",
            "cor": "#FF6B35",
            "ativo": True,
        })
        resp = client.post("/api/metas/equipes", json={
            "nome": "FÊNIX",
            "cor": "#FF6B35",
        })
        assert resp.status_code == 201
        assert resp.json()["data"]["nome"] == "FÊNIX"

    def test_create_team_missing_name(self, client):
        resp = client.post("/api/metas/equipes", json={"cor": "#000000"})
        assert resp.status_code == 422

    def test_create_team_empty_name_rejected(self, client):
        resp = client.post("/api/metas/equipes", json={"nome": ""})
        assert resp.status_code == 422

    def test_create_team_with_leader(self, client):
        # When lider_id is given, service also creates a membership row
        client._mock_supabase.set_table_data("equipes", {
            "id": "e-new",
            "nome": "FÊNIX",
            "lider_id": "user-42",
            "ativo": True,
        })
        client._mock_supabase.set_table_data("equipe_membros", {
            "id": "m-new",
            "equipe_id": "e-new",
            "user_id": "user-42",
            "papel": "lider",
        })
        resp = client.post("/api/metas/equipes", json={
            "nome": "FÊNIX",
            "lider_id": "user-42",
        })
        assert resp.status_code == 201


class TestObterEquipe:
    def test_get_existing(self, client):
        client._mock_supabase.set_table_data("equipes", [
            {"id": "e1", "nome": "DRAGÃO", "ativo": True}
        ])
        resp = client.get("/api/metas/equipes/e1")
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == "e1"

    def test_get_missing_returns_404(self, client):
        client._mock_supabase.set_table_data("equipes", [])
        resp = client.get("/api/metas/equipes/nonexistent")
        assert resp.status_code == 404


class TestAtualizarEquipe:
    def test_update_name(self, client):
        client._mock_supabase.set_table_data("equipes", {
            "id": "e1",
            "nome": "DRAGÃO V2",
            "ativo": True,
        })
        resp = client.patch("/api/metas/equipes/e1", json={"nome": "DRAGÃO V2"})
        assert resp.status_code == 200

    def test_update_empty_body_no_op(self, client):
        client._mock_supabase.set_table_data("equipes", [
            {"id": "e1", "nome": "DRAGÃO", "ativo": True}
        ])
        resp = client.patch("/api/metas/equipes/e1", json={})
        assert resp.status_code == 200


class TestDesativarEquipe:
    def test_disband_soft_marks(self, client):
        client._mock_supabase.set_table_data("equipes", {
            "id": "e1",
            "nome": "DRAGÃO",
            "ativo": False,
            "disbanded_at": "2026-04-18T12:00:00Z",
        })
        resp = client.delete("/api/metas/equipes/e1")
        assert resp.status_code == 200
        assert resp.json()["data"]["ativo"] is False

    def test_disband_missing_returns_404(self, client):
        client._mock_supabase.set_table_data("equipes", [])
        resp = client.delete("/api/metas/equipes/ghost")
        assert resp.status_code == 404


# ── Membership endpoints ────────────────────────────────────────────

class TestListarMembros:
    def test_list_active_members(self, client):
        client._mock_supabase.set_table_data("equipe_membros", [
            {"id": "m1", "equipe_id": "e1", "user_id": "u1", "papel": "lider"},
            {"id": "m2", "equipe_id": "e1", "user_id": "u2", "papel": "corretor"},
        ])
        resp = client.get("/api/metas/equipes/e1/membros")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    def test_list_includes_history_when_flag(self, client):
        client._mock_supabase.set_table_data("equipe_membros", [])
        resp = client.get("/api/metas/equipes/e1/membros?incluir_historico=true")
        assert resp.status_code == 200


class TestAdicionarMembro:
    def test_add_member(self, client):
        client._mock_supabase.set_table_data("equipe_membros", {
            "id": "m-new",
            "equipe_id": "e1",
            "user_id": "u-new",
            "papel": "corretor",
        })
        resp = client.post("/api/metas/equipes/e1/membros", json={
            "user_id": "u-new",
            "papel": "corretor",
        })
        assert resp.status_code == 201
        assert resp.json()["data"]["user_id"] == "u-new"

    def test_add_member_default_papel_is_corretor(self, client):
        client._mock_supabase.set_table_data("equipe_membros", {
            "id": "m-new",
            "equipe_id": "e1",
            "user_id": "u-new",
            "papel": "corretor",
        })
        resp = client.post("/api/metas/equipes/e1/membros", json={"user_id": "u-new"})
        assert resp.status_code == 201

    def test_add_member_invalid_papel(self, client):
        resp = client.post("/api/metas/equipes/e1/membros", json={
            "user_id": "u-new",
            "papel": "diretor",   # not in {lider, corretor}
        })
        assert resp.status_code == 422

    def test_add_member_missing_user_id(self, client):
        resp = client.post("/api/metas/equipes/e1/membros", json={"papel": "corretor"})
        assert resp.status_code == 422


class TestAtualizarMembro:
    def test_promote_to_leader(self, client):
        client._mock_supabase.set_table_data("equipe_membros", {
            "id": "m1",
            "equipe_id": "e1",
            "user_id": "u1",
            "papel": "lider",
        })
        resp = client.patch("/api/metas/equipes/e1/membros/m1", json={"papel": "lider"})
        assert resp.status_code == 200
        assert resp.json()["data"]["papel"] == "lider"

    def test_invalid_papel_rejected(self, client):
        resp = client.patch("/api/metas/equipes/e1/membros/m1", json={"papel": "ceo"})
        assert resp.status_code == 422


class TestRemoverMembro:
    def test_soft_remove(self, client):
        client._mock_supabase.set_table_data("equipe_membros", {
            "id": "m1",
            "equipe_id": "e1",
            "user_id": "u1",
            "papel": "corretor",
            "left_at": "2026-04-18T12:00:00Z",
        })
        resp = client.delete("/api/metas/equipes/e1/membros/m1")
        assert resp.status_code == 200
        assert resp.json()["data"]["left_at"] is not None

    def test_remove_missing_returns_404(self, client):
        client._mock_supabase.set_table_data("equipe_membros", [])
        resp = client.delete("/api/metas/equipes/e1/membros/ghost")
        assert resp.status_code == 404
