"""Patients organ mounted on Monica (`mount_clients` in `app/main.py`) + the lead -> patient conversion.

Pins: (a) the rendered clients migration equals the generator's output (re-render with
`noctus.dev.render_organ_migration`, never hand-edit); (b) the routes are mounted and strictly 401 without auth;
(c) the config is Monica's vocabulary and the funnel stages carry their colours + tags; (d) moving a lead to
`fechado` creates ONE patient through the leads organ's hook, end to end over the Mock PostgREST.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from noctusai_lib.testing.migrations import migration_sql
from noctusai_lib.testing.organs import assert_organ_migration_current

from app.crm import CLIENTS_CONFIG, LEADS_CONFIG

PRODUCT_DIR = Path(__file__).resolve().parents[1]
SCHEMA = "monica"
X = uuid.uuid4()


@pytest.fixture
def auth_org_id():
    """A real UUID org: the organs scope by the raw org id."""
    return "11111111-1111-1111-1111-111111111111"


def test_clients_migration_is_the_generators_output():
    assert_organ_migration_current(PRODUCT_DIR, "clients", schema=SCHEMA)


def test_status_pagina_rows_for_the_patients_pages():
    sql = migration_sql(PRODUCT_DIR, "status_pagina_pacientes")
    assert "('pacientes', 'producao')" in sql and "('pacientes_agenda', 'producao')" in sql


def test_clients_routes_are_mounted():
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert {"/api/clients", "/api/clients/config", "/api/clients/sessions", "/api/clients/{client_id}/payments"} <= paths


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/clients/config"), ("GET", "/api/clients"), ("POST", "/api/clients"), ("GET", "/api/clients/tags"),
        ("GET", "/api/clients/sessions?from=2026-11-01&to=2026-11-07"), ("GET", f"/api/clients/{X}"),
        ("PATCH", f"/api/clients/{X}"), ("DELETE", f"/api/clients/{X}"), ("GET", f"/api/clients/{X}/sessions"),
        ("POST", f"/api/clients/{X}/sessions"), ("GET", f"/api/clients/{X}/finance"), ("POST", f"/api/clients/{X}/payments"),
        ("PATCH", f"/api/clients/sessions/{X}"), ("DELETE", f"/api/clients/schedules/{X}"),
    ],
)
def test_clients_routes_are_strictly_401_without_auth(client, method, path):
    assert client.raw().request(method, path).status_code == 401


def test_config_is_monicas_vocabulary(client):
    resp = client.get("/api/clients/config")
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body == CLIENTS_CONFIG.as_dict()
    assert (body["noun_singular"], body["noun_plural"], body["timezone"]) == ("Paciente", "Pacientes", "America/Sao_Paulo")
    assert body["finance_enabled"] is True and body["default_duration_min"] == 50


def test_funnel_stages_carry_colour_and_tag(client):
    stages = client.get("/api/leads/config").json()["data"]["stages"]
    assert [(s["slug"], s["color"], s["tag"]) for s in stages] == [
        ("lead", "destructive", "Lead"),
        ("atendimento", "warning", "Em atendimento"),
        ("negociacao", "warning", "Em atendimento"),
        ("fechado", "success", "Paciente"),
    ]
    assert LEADS_CONFIG.on_stage_entered is not None


def test_closing_a_lead_creates_one_patient(client):
    lead = client.post("/api/leads", json={"name": "Lia", "phone": "11 99457-3387", "tags": ["indicação"]})
    assert lead.status_code == 201, lead.text
    lead_id = lead.json()["data"]["id"]
    for _ in range(2):  # re-entering the stage never duplicates the patient
        moved = client.post(f"/api/leads/{lead_id}/move", json={"stage": "atendimento", "position": 0})
        assert moved.status_code == 200, moved.text
        moved = client.post(f"/api/leads/{lead_id}/move", json={"stage": "fechado", "position": 0})
        assert moved.status_code == 200, moved.text
        assert "stage_hook_error" not in moved.json()["data"]
    patients = client.get("/api/clients", params={"lead_id": lead_id})
    assert patients.status_code == 200, patients.text
    (patient,) = patients.json()["data"]
    assert (patient["name"], patient["phone"], patient["status"], patient["tags"]) == ("Lia", "+5511994573387", "ativo", ["indicação"])
    assert patient["lead_id"] == lead_id
