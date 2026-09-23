"""GET /api/relatorios/{tipo} — HTTP plumbing over `app/services/relatorios.py`.

The actual computation is tested in `tests/services/test_relatorios.py`;
these tests are about routing, auth, format selection and error mapping.
"""
import pytest
from noctusai_lib.integrations.persistence import SqliteRecordStore

from app.dependencies import coerce_org_uuid
from app.repositories import Repositorios
from app.store import aplicar_schema_sqlite, get_repositorios, get_repositorios_admin

ORG = str(coerce_org_uuid("test-org-123"))


@pytest.fixture
def repos() -> Repositorios:
    store = SqliteRecordStore(":memory:")
    aplicar_schema_sqlite(store)
    return Repositorios(store)


@pytest.fixture
def api(client, repos):
    from app.main import app

    app.dependency_overrides[get_repositorios] = lambda: repos
    app.dependency_overrides[get_repositorios_admin] = lambda: repos
    yield client
    app.dependency_overrides.pop(get_repositorios, None)
    app.dependency_overrides.pop(get_repositorios_admin, None)


class TestRelatorioRouter:
    def test_requires_auth(self, api):
        resp = api.raw().get(
            "/api/relatorios/comercial?inicio=2026-08-01&fim=2026-08-31"
        )
        assert resp.status_code == 401

    def test_invalid_tipo_is_a_422_not_a_500(self, api):
        # `tipo` is a path Literal — FastAPI 422s an out-of-set value before
        # the handler (and `gerar_relatorio`'s own ValueError guard) ever run.
        resp = api.get("/api/relatorios/invalido?inicio=2026-08-01&fim=2026-08-31")
        assert resp.status_code == 422

    def test_missing_period_is_422(self, api):
        resp = api.get("/api/relatorios/comercial")
        assert resp.status_code == 422

    def test_inverted_period_is_422_not_500(self, api):
        resp = api.get(
            "/api/relatorios/comercial?inicio=2026-08-31&fim=2026-08-01"
        )
        assert resp.status_code == 422

    def test_json_is_the_default_format(self, api):
        resp = api.get("/api/relatorios/comercial?inicio=2026-08-01&fim=2026-08-31")
        assert resp.status_code == 200
        corpo = resp.json()["data"]
        assert corpo["tipo"] == "comercial"
        assert corpo["periodo"]["inicio"] == "2026-08-01"
        assert corpo["comercial"] is not None
        assert corpo["financeiro"] is None

    def test_financeiro_json(self, api):
        resp = api.get("/api/relatorios/financeiro?inicio=2026-08-01&fim=2026-08-31")
        assert resp.status_code == 200
        corpo = resp.json()["data"]
        assert corpo["financeiro"] is not None
        assert corpo["comercial"] is None

    def test_csv_format_downloads_a_csv(self, api):
        resp = api.get(
            "/api/relatorios/comercial?inicio=2026-08-01&fim=2026-08-31&formato=csv"
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "attachment" in resp.headers["content-disposition"]
        assert len(resp.content) > 0

    def test_pdf_format_downloads_a_pdf(self, api):
        resp = api.get(
            "/api/relatorios/financeiro?inicio=2026-08-01&fim=2026-08-31&formato=pdf"
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content[:5] == b"%PDF-"
