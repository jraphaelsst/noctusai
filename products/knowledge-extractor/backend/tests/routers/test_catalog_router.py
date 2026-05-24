"""Status-pinned tests for the catalog router + the path-traversal guard."""
from __future__ import annotations

from app.dependencies import get_data_dir
from app.main import app
from app.services.catalog_service import CatalogService


def test_get_catalog_lists_modules(client, seeded_data_dir):
    r = client.get("/api/catalog")
    assert r.status_code == 200
    body = r.json()
    names = {m["name"] for m in body["modules"]}
    assert {"modulo-1", "modulo-2"} <= names
    assert body["totals"]["modules"] >= 2
    m1 = next(m for m in body["modules"] if m["name"] == "modulo-1")
    assert m1["transcripts"] == 1 and m1["summaries"] == 1 and m1["lessons"] == 1


def test_get_catalog_empty(client, tmp_path):
    app.dependency_overrides[get_data_dir] = lambda: tmp_path
    r = client.get("/api/catalog")
    assert r.status_code == 200
    assert r.json()["totals"]["modules"] == 0


def test_module_lessons_200(client, seeded_data_dir):
    r = client.get("/api/catalog/modules/modulo-1")
    assert r.status_code == 200
    lessons = r.json()["lessons"]
    assert any(
        l["lesson"] == "aula-01" and l["has_transcript"] and l["has_summary"]
        for l in lessons
    )


def test_module_lessons_404(client, seeded_data_dir):
    r = client.get("/api/catalog/modules/inexistente")
    assert r.status_code == 404


def test_lesson_content_200(client, seeded_data_dir):
    r = client.get("/api/catalog/lessons/modulo-1/aula-01")
    assert r.status_code == 200
    body = r.json()
    assert "transcrição" in body["transcript"]
    assert "resumo" in body["summary"]


def test_lesson_content_404(client, seeded_data_dir):
    r = client.get("/api/catalog/lessons/modulo-1/inexistente")
    assert r.status_code == 404


def test_service_rejects_path_traversal(seeded_data_dir):
    svc = CatalogService(seeded_data_dir)
    assert svc.lesson_content("..", "x") is None
    assert svc.module_lessons("../etc") is None
