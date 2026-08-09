"""Calendário editorial, copywriting e peças — Módulo 3.

Also covers the Módulo 4 portal gap this module closes: once a pauta has a
peça, the client's approval page must show it beside the legenda — and must
still work when it doesn't.
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
def api(client, repos, monkeypatch):
    """`client` with a throwaway store and an in-memory storage backend."""
    from app.config import settings
    from app.main import app
    import app.storage as storage_mod

    monkeypatch.setattr(settings, "igig_storage_kind", "fake")
    storage_mod.reset_storage()
    app.dependency_overrides[get_repositorios] = lambda: repos
    app.dependency_overrides[get_repositorios_admin] = lambda: repos
    yield client
    app.dependency_overrides.pop(get_repositorios, None)
    app.dependency_overrides.pop(get_repositorios_admin, None)
    storage_mod.reset_storage()


@pytest.fixture
def cliente(repos) -> dict:
    return repos.cliente.criar(ORG, {"nome": "Padaria Sol"})


def _criar(api, cliente, **extra):
    return api.post("/api/pautas", json={
        "cliente_id": cliente["id"], "titulo": "Post institucional", **extra,
    })


class TestPautaCrud:
    def test_requires_auth(self, api):
        assert api.raw().get("/api/pautas").status_code == 401

    def test_create_returns_201(self, api, cliente):
        resp = _criar(api, cliente, formato="feed", funil="topo")
        assert resp.status_code == 201
        assert resp.json()["funil"] == "topo"

    def test_invalid_formato_returns_422(self, api, cliente):
        assert _criar(api, cliente, formato="tiktok-dance").status_code == 422

    def test_invalid_funil_returns_422(self, api, cliente):
        assert _criar(api, cliente, funil="lateral").status_code == 422

    def test_unknown_client_returns_404(self, api):
        resp = api.post("/api/pautas", json={"cliente_id": "nao-existe", "titulo": "X"})
        assert resp.status_code == 404

    def test_filter_by_funil(self, api, cliente):
        _criar(api, cliente, funil="topo")
        _criar(api, cliente, funil="fundo")
        got = api.get("/api/pautas?funil=fundo").json()
        assert len(got) == 1 and got[0]["funil"] == "fundo"

    def test_miss_returns_404(self, api):
        assert api.get("/api/pautas/nao-existe").status_code == 404

    def test_pauta_is_org_scoped(self, api, repos, cliente):
        alheia = repos.pauta.criar("outra-org", {"cliente_id": cliente["id"], "titulo": "Rival"})
        assert api.get(f"/api/pautas/{alheia['id']}").status_code == 404


class TestContadorDeCaracteres:
    """The spec's live character counter, defined once on the server."""

    def test_counts_the_copy(self, api, cliente):
        texto = "Pão quentinho todo dia às 6h."
        resp = _criar(api, cliente, copy_texto=texto)
        assert resp.json()["caracteres_copy"] == len(texto)

    def test_zero_without_copy(self, api, cliente):
        assert _criar(api, cliente).json()["caracteres_copy"] == 0

    def test_updates_after_an_edit(self, api, cliente):
        criada = _criar(api, cliente, copy_texto="curto").json()
        resp = api.patch(f"/api/pautas/{criada['id']}", json={"copy_texto": "um texto bem maior"})
        assert resp.json()["caracteres_copy"] == len("um texto bem maior")


class TestCalendario:
    def _agendar(self, api, cliente, titulo, data):
        return _criar(api, cliente, titulo=titulo, data_publicacao=data).json()

    def test_window_filters_by_date(self, api, cliente):
        self._agendar(api, cliente, "jan", "2026-01-10T09:00:00")
        self._agendar(api, cliente, "fev", "2026-02-10T09:00:00")
        body = api.get(
            "/api/pautas/calendario?inicio=2026-01-01T00:00:00&fim=2026-01-31T23:59:59"
        ).json()
        assert [p["titulo"] for p in body["itens"]] == ["jan"]
        assert body["inicio"] == "2026-01-01T00:00:00"

    def test_unscheduled_pautas_are_excluded(self, api, cliente):
        """A pauta with no date has no place on a date grid."""
        _criar(api, cliente, titulo="sem data")
        body = api.get(
            "/api/pautas/calendario?inicio=2020-01-01T00:00:00&fim=2030-01-01T00:00:00"
        ).json()
        assert body["itens"] == []

    def test_inverted_window_returns_422(self, api):
        resp = api.get("/api/pautas/calendario?inicio=2026-02-01T00:00:00&fim=2026-01-01T00:00:00")
        assert resp.status_code == 422

    def test_reschedule_moves_it_in_the_window(self, api, cliente):
        pauta = self._agendar(api, cliente, "post", "2026-01-10T09:00:00")
        api.patch(f"/api/pautas/{pauta['id']}", json={"data_publicacao": "2026-02-10T09:00:00"})
        jan = api.get(
            "/api/pautas/calendario?inicio=2026-01-01T00:00:00&fim=2026-01-31T23:59:59"
        ).json()
        fev = api.get(
            "/api/pautas/calendario?inicio=2026-02-01T00:00:00&fim=2026-02-28T23:59:59"
        ).json()
        assert jan["itens"] == []
        assert [p["titulo"] for p in fev["itens"]] == ["post"]

    def test_unscheduling_is_possible(self, api, cliente):
        """`exclude_unset` — an explicit null must clear the date.

        With `exclude_none` this would silently do nothing, and a pauta could
        never be taken off the calendar.
        """
        pauta = self._agendar(api, cliente, "post", "2026-01-10T09:00:00")
        resp = api.patch(f"/api/pautas/{pauta['id']}", json={"data_publicacao": None})
        assert resp.status_code == 200
        assert resp.json()["data_publicacao"] is None


class TestPecas:
    def _enviar(self, api, pauta_id, *, nome="arte.png", tipo="image/png", dados=b"\x89PNG..."):
        return api.raw().post(
            f"/api/pautas/{pauta_id}/pecas",
            files={"arquivo": (nome, dados, tipo)},
            headers={"Authorization": "Bearer test-token-valid"},
        )

    def test_upload_returns_201_and_records_the_key(self, api, cliente):
        pauta = _criar(api, cliente).json()
        resp = self._enviar(api, pauta["id"])
        assert resp.status_code == 201
        body = resp.json()
        assert body["mime_type"] == "image/png"
        assert pauta["id"] in body["storage_key"]

    def test_rejects_an_unsupported_type(self, api, cliente):
        pauta = _criar(api, cliente).json()
        resp = self._enviar(api, pauta["id"], nome="x.exe", tipo="application/x-msdownload")
        assert resp.status_code == 422

    def test_upload_to_a_missing_pauta_returns_404(self, api):
        assert self._enviar(api, "nao-existe").status_code == 404

    def test_listing_returns_uploads_in_order(self, api, cliente):
        pauta = _criar(api, cliente).json()
        for n in ("a.png", "b.png"):
            self._enviar(api, pauta["id"], nome=n)
        got = api.get(f"/api/pautas/{pauta['id']}/pecas").json()
        assert [p["ordem"] for p in got] == [0, 1]


class TestPortalMostraAPeca:
    """The Módulo 4 gap this module closes."""

    def _link(self, api, repos, cliente, *, com_peca: bool):
        pauta = _criar(api, cliente, copy_texto="Legenda").json()
        if com_peca:
            api.raw().post(
                f"/api/pautas/{pauta['id']}/pecas",
                files={"arquivo": ("arte.png", b"\x89PNG...", "image/png")},
                headers={"Authorization": "Bearer test-token-valid"},
            )
        tarefa = repos.tarefa.criar(ORG, {"pauta_id": pauta["id"], "titulo": "Arte"})
        return repos.aprovacao.emitir(ORG, tarefa["id"])["token"]

    def test_peca_appears_beside_the_legenda(self, api, repos, cliente):
        token = self._link(api, repos, cliente, com_peca=True)
        body = api.raw().get(f"/api/esteira/aprovar/{token}").json()
        assert body["copy_texto"] == "Legenda"
        assert len(body["pecas"]) == 1
        assert body["pecas"][0]["mime_type"] == "image/png"

    def test_portal_still_works_without_a_peca(self, api, repos, cliente):
        """Copy-only must remain reviewable — no broken frame."""
        token = self._link(api, repos, cliente, com_peca=False)
        resp = api.raw().get(f"/api/esteira/aprovar/{token}")
        assert resp.status_code == 200
        assert resp.json()["pecas"] == []

    def test_peca_payload_leaks_no_internals(self, api, repos, cliente):
        """No storage key or id — those would let a caller probe the bucket."""
        token = self._link(api, repos, cliente, com_peca=True)
        peca = api.raw().get(f"/api/esteira/aprovar/{token}").json()["pecas"][0]
        assert set(peca) == {"url", "mime_type"}
