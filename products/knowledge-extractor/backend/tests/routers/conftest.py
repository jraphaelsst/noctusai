"""Router-test fixtures: an authed TestClient + DI-seam overrides (no live IO).

Auth is overridden by default (every test is "logged in"); the data dir, vector
store, embedder and run executor are DI seams individual tests override — never
monkeypatching our own code. The in-memory run registry is reset per test.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_current_user_org, get_data_dir
from app.main import app
from app.services import runs_service


@pytest.fixture(autouse=True)
def _isolate():
    app.dependency_overrides[get_current_user_org] = lambda: (object(), "test-token", "test-org")
    yield
    app.dependency_overrides.clear()
    runs_service._RUNS.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def seeded_data_dir(tmp_path):
    """A KE data dir with two modules + a methodology manual; wired via get_data_dir."""
    t = tmp_path / "transcripts"
    s = tmp_path / "summaries"
    (t / "modulo-1").mkdir(parents=True)
    (s / "modulo-1").mkdir(parents=True)
    (t / "modulo-1" / "aula-01.md").write_text("# aula-01\n\ncorpo da transcrição", encoding="utf-8")
    (s / "modulo-1" / "aula-01.md").write_text("# Resumo\n\ncorpo do resumo", encoding="utf-8")
    (t / "modulo-2").mkdir(parents=True)
    (t / "modulo-2" / "aula-02.md").write_text("transcrição só", encoding="utf-8")
    (tmp_path / "METHODOLOGY.md").write_text("# Metodologia\n\nmanual do curso", encoding="utf-8")
    (tmp_path / "methodology").mkdir()
    (tmp_path / "methodology" / "modulo-1.md").write_text("# síntese m1", encoding="utf-8")
    app.dependency_overrides[get_data_dir] = lambda: tmp_path
    return tmp_path
