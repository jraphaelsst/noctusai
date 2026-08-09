"""Distribuição, métricas e BI — Módulo 5.

Two properties carry the weight here:

  1. A publication is NEVER marked `publicada` without a platform-confirmed
     external id. A post the client never saw showing as published is the one
     outcome that destroys trust in this module.
  2. The BI numbers are arithmetic the agency will bill against, so the
     rollup is checked against hand-computed values — including the case
     where hours cannot be costed, which must be reported rather than
     silently treated as free.
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


@pytest.fixture
def pauta(repos) -> dict:
    cliente = repos.cliente.criar(ORG, {"nome": "Padaria Sol"})
    return repos.pauta.criar(
        ORG, {"cliente_id": cliente["id"], "titulo": "Post", "copy_texto": "Legenda"}
    )


class TestAgendamento:
    def test_requires_auth(self, api):
        assert api.raw().get("/api/distribuicao/publicacoes").status_code == 401

    def test_schedule_returns_201(self, api, pauta):
        resp = api.post("/api/distribuicao/publicacoes", json={
            "pauta_id": pauta["id"], "canal": "instagram",
            "agendada_para": "2026-09-01T09:00:00",
        })
        assert resp.status_code == 201
        assert resp.json()["status"] == "agendada"

    def test_invalid_channel_returns_422(self, api, pauta):
        resp = api.post("/api/distribuicao/publicacoes", json={
            "pauta_id": pauta["id"], "canal": "orkut",
            "agendada_para": "2026-09-01T09:00:00",
        })
        assert resp.status_code == 422

    def test_duplicate_channel_returns_409(self, api, pauta):
        """A duplicate would double-post to the client's real account."""
        corpo = {
            "pauta_id": pauta["id"], "canal": "instagram",
            "agendada_para": "2026-09-01T09:00:00",
        }
        assert api.post("/api/distribuicao/publicacoes", json=corpo).status_code == 201
        assert api.post("/api/distribuicao/publicacoes", json=corpo).status_code == 409

    def test_same_pauta_on_two_channels_is_allowed(self, api, pauta):
        for canal in ("instagram", "tiktok"):
            resp = api.post("/api/distribuicao/publicacoes", json={
                "pauta_id": pauta["id"], "canal": canal,
                "agendada_para": "2026-09-01T09:00:00",
            })
            assert resp.status_code == 201

    def test_cancelling_frees_the_slot(self, api, pauta):
        corpo = {
            "pauta_id": pauta["id"], "canal": "instagram",
            "agendada_para": "2026-09-01T09:00:00",
        }
        primeira = api.post("/api/distribuicao/publicacoes", json=corpo).json()
        api.post(f"/api/distribuicao/publicacoes/{primeira['id']}/cancelar")
        assert api.post("/api/distribuicao/publicacoes", json=corpo).status_code == 201

    def test_unknown_pauta_returns_404(self, api):
        resp = api.post("/api/distribuicao/publicacoes", json={
            "pauta_id": "nao-existe", "canal": "instagram",
            "agendada_para": "2026-09-01T09:00:00",
        })
        assert resp.status_code == 404

    def test_queue_lists_only_due_items(self, api, pauta):
        api.post("/api/distribuicao/publicacoes", json={
            "pauta_id": pauta["id"], "canal": "instagram",
            "agendada_para": "2026-01-01T09:00:00",
        })
        api.post("/api/distribuicao/publicacoes", json={
            "pauta_id": pauta["id"], "canal": "tiktok",
            "agendada_para": "2030-01-01T09:00:00",
        })
        fila = api.get("/api/distribuicao/fila?ate=2026-06-01T00:00:00").json()
        assert [p["canal"] for p in fila] == ["instagram"]


class TestExecucao:
    def _agendar(self, api, pauta, canal="instagram"):
        return api.post("/api/distribuicao/publicacoes", json={
            "pauta_id": pauta["id"], "canal": canal,
            "agendada_para": "2026-09-01T09:00:00",
        }).json()

    def test_publish_records_a_platform_id(self, api, pauta):
        pub = self._agendar(api, pauta)
        resp = api.post(f"/api/distribuicao/publicacoes/{pub['id']}/executar")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "publicada"
        assert body["external_id"], "a published post MUST carry the platform's id"
        assert body["publicada_em"]

    def test_republishing_returns_409(self, api, pauta):
        pub = self._agendar(api, pauta)
        api.post(f"/api/distribuicao/publicacoes/{pub['id']}/executar")
        assert api.post(
            f"/api/distribuicao/publicacoes/{pub['id']}/executar"
        ).status_code == 409

    def test_a_failing_channel_is_never_marked_published(self, api, pauta, monkeypatch):
        """The property this module lives or dies on."""
        import app.routers.distribuicao_router as dr
        from app.services.publicacao_publisher import PublisherNotConfigured

        class Quebrado:
            canal = "instagram"

            def publicar(self, **_kwargs):
                raise PublisherNotConfigured("sem credenciais")

        monkeypatch.setattr(dr, "get_publisher", lambda *_a, **_k: Quebrado())
        pub = self._agendar(api, pauta)
        body = api.post(f"/api/distribuicao/publicacoes/{pub['id']}/executar").json()
        assert body["status"] == "falhou"
        assert body["external_id"] is None
        assert "sem credenciais" in body["erro"]
        assert body["tentativas"] == 1

    def test_retries_accumulate(self, api, pauta, monkeypatch):
        import app.routers.distribuicao_router as dr

        class Quebrado:
            canal = "instagram"

            def publicar(self, **_kwargs):
                raise RuntimeError("timeout")

        monkeypatch.setattr(dr, "get_publisher", lambda *_a, **_k: Quebrado())
        pub = self._agendar(api, pauta)
        for _ in range(2):
            body = api.post(f"/api/distribuicao/publicacoes/{pub['id']}/executar").json()
        assert body["tentativas"] == 2

    def test_cannot_cancel_a_published_post(self, api, pauta):
        pub = self._agendar(api, pauta)
        api.post(f"/api/distribuicao/publicacoes/{pub['id']}/executar")
        assert api.post(
            f"/api/distribuicao/publicacoes/{pub['id']}/cancelar"
        ).status_code == 409


class TestMetricas:
    def _publicada(self, api, pauta):
        pub = api.post("/api/distribuicao/publicacoes", json={
            "pauta_id": pauta["id"], "canal": "instagram",
            "agendada_para": "2026-09-01T09:00:00",
        }).json()
        api.post(f"/api/distribuicao/publicacoes/{pub['id']}/executar")
        return pub

    def test_snapshot_is_appended(self, api, pauta):
        pub = self._publicada(api, pauta)
        resp = api.post(f"/api/distribuicao/publicacoes/{pub['id']}/metricas",
                        json={"curtidas": 10, "alcance": 500})
        assert resp.status_code == 201
        assert resp.json()["curtidas"] == 10

    def test_history_is_preserved_not_overwritten(self, api, pauta):
        """Metrics move; overwriting destroys the only record of a post's week."""
        pub = self._publicada(api, pauta)
        for curtidas in (10, 25):
            api.post(f"/api/distribuicao/publicacoes/{pub['id']}/metricas",
                     json={"curtidas": curtidas})
        historico = api.get(f"/api/distribuicao/publicacoes/{pub['id']}/metricas").json()
        assert len(historico) == 2
        assert {m["curtidas"] for m in historico} == {10, 25}

    def test_negative_counters_are_rejected(self, api, pauta):
        pub = self._publicada(api, pauta)
        resp = api.post(f"/api/distribuicao/publicacoes/{pub['id']}/metricas",
                        json={"curtidas": -5})
        assert resp.status_code == 422

    def test_unknown_publication_returns_404(self, api):
        assert api.post("/api/distribuicao/publicacoes/nao-existe/metricas",
                        json={"curtidas": 1}).status_code == 404


class TestBIEficiencia:
    """Numbers the agency bills against — checked against hand-computed values."""

    def _cenario(self, repos, *, custo_hora=100.0, minutos=90, refacoes=2, com_rate=True):
        cliente = repos.cliente.criar(ORG, {"nome": "Padaria Sol"})
        pauta = repos.pauta.criar(ORG, {"cliente_id": cliente["id"], "titulo": "Post"})
        tarefa = repos.tarefa.criar(
            ORG, {"pauta_id": pauta["id"], "titulo": "Arte", "refacoes": refacoes}
        )
        if com_rate:
            funcao = repos.funcao.criar(
                ORG, {"nome": "designer", "custo_hora_padrao": custo_hora}
            )
            repos.profissional.criar(
                ORG, {"nome": "Ana", "usuario_id": "user-1", "funcao_id": funcao["id"]}
            )
        repos.apontamento.criar(
            ORG,
            {"tarefa_id": tarefa["id"], "usuario_id": "user-1",
             "iniciado_em": "2026-01-01T09:00:00", "minutos": minutos},
        )
        return cliente

    def test_cost_is_minutes_times_rate(self, api, repos):
        self._cenario(repos, custo_hora=100.0, minutos=90)
        linha = api.get("/api/distribuicao/bi/eficiencia").json()[0]
        assert linha["horas"] == 1.5
        assert linha["custo_reais"] == 150.0  # 1.5 h × R$100
        assert linha["alertas"] == []

    def test_taxa_de_refacao_is_per_task(self, api, repos):
        self._cenario(repos, refacoes=2)
        linha = api.get("/api/distribuicao/bi/eficiencia").json()[0]
        assert linha["tarefas"] == 1
        assert linha["refacoes"] == 2
        assert linha["taxa_refacao"] == 2.0

    def test_uncosted_hours_are_flagged_not_treated_as_free(self, api, repos):
        """Silently costing 0 would understate every job that person touched."""
        self._cenario(repos, com_rate=False)
        linha = api.get("/api/distribuicao/bi/eficiencia").json()[0]
        assert linha["custo_reais"] == 0.0
        assert linha["alertas"], "an uncosted apontamento must be reported"
        assert "SUBESTIMADO" in linha["alertas"][0]

    def test_client_with_no_work_has_no_division_error(self, api, repos):
        repos.cliente.criar(ORG, {"nome": "Sem trabalho"})
        linha = api.get("/api/distribuicao/bi/eficiencia").json()[0]
        assert linha["taxa_refacao"] == 0.0
        assert linha["custo_reais"] == 0.0

    def test_bi_is_org_scoped(self, api, repos):
        self._cenario(repos)
        repos.cliente.criar("outra-org", {"nome": "Concorrente"})
        nomes = {l["cliente_nome"] for l in api.get("/api/distribuicao/bi/eficiencia").json()}
        assert nomes == {"Padaria Sol"}

    def test_requires_auth(self, api):
        assert api.raw().get("/api/distribuicao/bi/eficiencia").status_code == 401
