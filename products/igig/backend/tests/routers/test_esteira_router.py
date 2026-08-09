"""Esteira + public approval portal — Módulo 4.

The public-portal tests are the important ones. That surface is
unauthenticated and reachable by anyone with a URL, so its security
properties are asserted explicitly: the token must be unguessable, the
projection must not leak the agency's internals, a decision must be
single-use, and unknown/expired/spent must be indistinguishable.
"""
from datetime import timedelta

import pytest
from noctusai_lib.integrations.persistence import SqliteRecordStore

from app.repositories import ETAPAS, Repositorios
from app.store import aplicar_schema_sqlite, get_repositorios, get_repositorios_admin

from app.dependencies import coerce_org_uuid

#: The org the AUTHED endpoints actually resolve to. The conftest mock user
#: carries the opaque fixture org "test-org-123", which `coerce_org_uuid`
#: maps deterministically onto a UUID before any store call. Seeding data
#: under the raw string instead would write to an org the API never reads —
#: the tests would then pass or fail for the wrong reason.
ORG = str(coerce_org_uuid("test-org-123"))


@pytest.fixture
def repos() -> Repositorios:
    store = SqliteRecordStore(":memory:")
    aplicar_schema_sqlite(store)
    return Repositorios(store)


@pytest.fixture
def api(client, repos):
    from app.main import app

    # BOTH scopes point at the same throwaway store: the authed routes use
    # `get_repositorios` (RLS-scoped in production) and the public portal uses
    # `get_repositorios_admin` (service-role). Overriding only the first would
    # leave the portal hitting a real Supabase client.
    app.dependency_overrides[get_repositorios] = lambda: repos
    app.dependency_overrides[get_repositorios_admin] = lambda: repos
    yield client
    app.dependency_overrides.pop(get_repositorios, None)
    app.dependency_overrides.pop(get_repositorios_admin, None)


@pytest.fixture
def tarefa(repos) -> dict:
    cliente = repos.cliente.criar(ORG, {"nome": "Padaria Sol"})
    pauta = repos.pauta.criar(
        ORG,
        {
            "cliente_id": cliente["id"],
            "titulo": "Post institucional",
            "copy_texto": "Pão quentinho todo dia às 6h.",
            "formato": "feed",
        },
    )
    return repos.tarefa.criar(ORG, {"pauta_id": pauta["id"], "titulo": "Arte do post"})


# ── Kanban ──────────────────────────────────────────────────────────
class TestQuadro:
    def test_requires_auth(self, api):
        assert api.raw().get("/api/esteira/quadro").status_code == 401

    def test_returns_all_eight_columns(self, api, tarefa):
        resp = api.get("/api/esteira/quadro")
        assert resp.status_code == 200
        body = resp.json()
        assert body["etapas"] == list(ETAPAS)
        assert set(body["colunas"]) == set(ETAPAS)
        assert len(body["colunas"]["aguardando_roteiro"]) == 1

    def test_mover_advances_the_task(self, api, tarefa):
        resp = api.post(
            f"/api/esteira/tarefas/{tarefa['id']}/mover", json={"etapa": "design_em_producao"}
        )
        assert resp.status_code == 200
        assert resp.json()["etapa"] == "design_em_producao"

    def test_mover_to_invalid_etapa_returns_422(self, api, tarefa):
        resp = api.post(
            f"/api/esteira/tarefas/{tarefa['id']}/mover", json={"etapa": "inventada"}
        )
        assert resp.status_code == 422

    def test_mover_missing_task_returns_404(self, api):
        resp = api.post("/api/esteira/tarefas/nao-existe/mover", json={"etapa": "agendado"})
        assert resp.status_code == 404

    def test_create_task_for_missing_pauta_returns_404(self, api):
        resp = api.post(
            "/api/esteira/tarefas", json={"pauta_id": "nao-existe", "titulo": "X"}
        )
        assert resp.status_code == 404


# ── Timesheet ───────────────────────────────────────────────────────
class TestTimesheet:
    def test_iniciar_requires_auth(self, api, tarefa):
        resp = api.raw().post(
            f"/api/esteira/tarefas/{tarefa['id']}/timer/iniciar", json={"usuario_id": "u1"}
        )
        assert resp.status_code == 401

    def test_iniciar_opens_a_segment(self, api, tarefa):
        resp = api.post(
            f"/api/esteira/tarefas/{tarefa['id']}/timer/iniciar", json={"usuario_id": "u1"}
        )
        assert resp.status_code == 201
        assert resp.json()["encerrado_em"] is None

    def test_encerrar_closes_it(self, api, tarefa):
        api.post(f"/api/esteira/tarefas/{tarefa['id']}/timer/iniciar", json={"usuario_id": "u1"})
        resp = api.post(
            f"/api/esteira/tarefas/{tarefa['id']}/timer/encerrar", json={"usuario_id": "u1"}
        )
        assert resp.status_code == 200
        assert resp.json()["encerrado_em"] is not None

    def test_encerrar_without_a_running_timer_returns_404(self, api, tarefa):
        resp = api.post(
            f"/api/esteira/tarefas/{tarefa['id']}/timer/encerrar", json={"usuario_id": "u1"}
        )
        assert resp.status_code == 404

    def test_starting_a_second_task_closes_the_first(self, api, tarefa, repos):
        outra = repos.tarefa.criar(ORG, {"pauta_id": tarefa["pauta_id"], "titulo": "Outra"})
        api.post(f"/api/esteira/tarefas/{tarefa['id']}/timer/iniciar", json={"usuario_id": "u1"})
        api.post(f"/api/esteira/tarefas/{outra['id']}/timer/iniciar", json={"usuario_id": "u1"})

        primeiros = api.get(f"/api/esteira/tarefas/{tarefa['id']}/apontamentos").json()
        assert primeiros[0]["encerrado_em"] is not None


# ── Approval link minting ───────────────────────────────────────────
class TestLinkAprovacao:
    def test_requires_auth(self, api, tarefa):
        resp = api.raw().post(f"/api/esteira/tarefas/{tarefa['id']}/link-aprovacao")
        assert resp.status_code == 401

    def test_mints_a_link(self, api, tarefa):
        resp = api.post(f"/api/esteira/tarefas/{tarefa['id']}/link-aprovacao")
        assert resp.status_code == 201
        assert resp.json()["token"]

    def test_token_is_long_and_unpredictable(self, api, tarefa):
        """A guessable token exposes unpublished client content."""
        tokens = {
            api.post(f"/api/esteira/tarefas/{tarefa['id']}/link-aprovacao").json()["token"]
            for _ in range(5)
        }
        assert len(tokens) == 5, "tokens must not repeat"
        for token in tokens:
            _org, _, secret = token.partition(".")
            assert len(secret) >= 32, "secret half must carry real entropy"

    def test_missing_task_returns_404(self, api):
        assert api.post("/api/esteira/tarefas/nao-existe/link-aprovacao").status_code == 404


# ── PUBLIC portal ───────────────────────────────────────────────────
class TestPortalPublico:
    @pytest.fixture
    def token(self, repos, tarefa) -> str:
        return str(repos.aprovacao.emitir(ORG, tarefa["id"])["token"])

    def test_view_needs_no_auth(self, api, token):
        """The whole point: the agency's client has no noc account."""
        resp = api.raw().get(f"/api/esteira/aprovar/{token}")
        assert resp.status_code == 200

    def test_view_shows_the_content(self, api, token):
        body = api.raw().get(f"/api/esteira/aprovar/{token}").json()
        assert body["titulo"] == "Arte do post"
        assert body["copy_texto"] == "Pão quentinho todo dia às 6h."
        assert body["cliente_nome"] == "Padaria Sol"

    def test_view_leaks_no_agency_internals(self, api, token):
        """Narrow projection — no ids, no org, no refação counter."""
        body = api.raw().get(f"/api/esteira/aprovar/{token}").json()
        for proibido in ("org_id", "id", "tarefa_id", "refacoes", "responsavel_id", "pauta_id"):
            assert proibido not in body, f"public payload leaked {proibido}"

    def test_unknown_token_returns_404(self, api):
        assert api.raw().get("/api/esteira/aprovar/nao-existe").status_code == 404

    def test_malformed_token_returns_404(self, api):
        assert api.raw().get("/api/esteira/aprovar/sem-ponto-nenhum").status_code == 404

    def test_expired_token_returns_404(self, api, repos, tarefa):
        vencido = repos.aprovacao.emitir(ORG, tarefa["id"], validade=timedelta(days=-1))
        resp = api.raw().get(f"/api/esteira/aprovar/{vencido['token']}")
        assert resp.status_code == 404

    def test_unknown_and_expired_are_indistinguishable(self, api, repos, tarefa):
        """Otherwise the endpoint is a token oracle."""
        vencido = repos.aprovacao.emitir(ORG, tarefa["id"], validade=timedelta(days=-1))
        desconhecido = api.raw().get("/api/esteira/aprovar/org.naoexiste")
        expirado = api.raw().get(f"/api/esteira/aprovar/{vencido['token']}")
        assert desconhecido.status_code == expirado.status_code == 404
        assert desconhecido.json() == expirado.json()

    def test_aprovar_moves_task_to_scheduling(self, api, repos, tarefa, token):
        resp = api.raw().post(
            f"/api/esteira/aprovar/{token}", json={"decisao": "aprovado", "observacao": ""}
        )
        assert resp.status_code == 200
        assert repos.tarefa.buscar(ORG, tarefa["id"])["etapa"] == "pronto_para_agendamento"

    def test_ajuste_reopens_and_increments_refacoes(self, api, repos, tarefa, token):
        resp = api.raw().post(
            f"/api/esteira/aprovar/{token}",
            json={"decisao": "ajuste", "observacao": "trocar a cor do fundo"},
        )
        assert resp.status_code == 200
        atual = repos.tarefa.buscar(ORG, tarefa["id"])
        assert atual["etapa"] == "revisao_interna"
        assert atual["refacoes"] == 1
        assert atual["observacao_cliente"] == "trocar a cor do fundo"

    def test_a_link_can_only_be_decided_once(self, api, token):
        primeira = api.raw().post(f"/api/esteira/aprovar/{token}", json={"decisao": "aprovado"})
        assert primeira.status_code == 200
        segunda = api.raw().post(f"/api/esteira/aprovar/{token}", json={"decisao": "ajuste"})
        assert segunda.status_code == 404, "a spent link must not flip the decision"

    def test_invalid_decision_returns_422(self, api, token):
        resp = api.raw().post(f"/api/esteira/aprovar/{token}", json={"decisao": "talvez"})
        assert resp.status_code == 422

    def test_unknown_field_returns_422(self, api, token):
        resp = api.raw().post(
            f"/api/esteira/aprovar/{token}", json={"decisao": "aprovado", "extra": "x"}
        )
        assert resp.status_code == 422

    def test_a_token_cannot_reach_another_orgs_tarefa(self, api, repos, tarefa):
        """The org half of the token is parsed, not trusted as a bypass."""
        forjado = f"outra-org.{'x' * 40}"
        assert api.raw().get(f"/api/esteira/aprovar/{forjado}").status_code == 404


class TestPublicPortalWiring:
    """Structural guarantees the request-level tests cannot give.

    `test_view_needs_no_auth` overrides `get_repositorios`, and an override
    replaces that dependency's whole subtree — including the auth dep nested
    inside it. So it passes even when the public routes are wired to the
    AUTHENTICATED repository provider, which is exactly the bug the Supabase
    flip introduced: in production those routes would have 401'd, while the
    tests stayed green. These assertions inspect the wiring itself.
    """

    @staticmethod
    def _deps(path: str, method: str):
        from app.main import app

        for route in app.routes:
            if getattr(route, "path", None) == path and method in getattr(route, "methods", ()):
                return {d.call for d in route.dependant.dependencies if d.call}
        raise AssertionError(f"route not found: {method} {path}")

    def _flat(self, path: str, method: str):
        """Direct + nested dependencies for a route."""
        from app.main import app

        seen = set()
        for route in app.routes:
            if getattr(route, "path", None) == path and method in getattr(route, "methods", ()):
                stack = list(route.dependant.dependencies)
                while stack:
                    d = stack.pop()
                    if d.call:
                        seen.add(d.call)
                    stack.extend(d.dependencies)
                return seen
        raise AssertionError(f"route not found: {method} {path}")

    @pytest.mark.parametrize("method", ["GET", "POST"])
    def test_public_routes_never_require_auth(self, method):
        from app.dependencies import get_current_user_org

        assert get_current_user_org not in self._flat("/api/esteira/aprovar/{token}", method), (
            "the public approval portal must not depend on authentication — "
            "its caller is the agency's client, who has no noc account"
        )

    @pytest.mark.parametrize("method", ["GET", "POST"])
    def test_public_routes_use_the_service_role_provider(self, method):
        from app.store import get_repositorios, get_repositorios_admin

        deps = self._flat("/api/esteira/aprovar/{token}", method)
        assert get_repositorios_admin in deps
        assert get_repositorios not in deps

    def test_authed_routes_use_the_rls_scoped_provider(self):
        """The inverse: the agency's own routes must stay RLS-scoped."""
        from app.dependencies import get_current_user_org
        from app.store import get_repositorios, get_repositorios_admin

        deps = self._flat("/api/esteira/quadro", "GET")
        assert get_repositorios in deps
        assert get_repositorios_admin not in deps
        assert get_current_user_org in deps
