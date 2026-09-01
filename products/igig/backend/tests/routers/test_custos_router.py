"""Custos router — funções e profissionais (the custo/hora table).

The tables, RLS and ``custo_hora_efetivo`` shipped in migration `008`; this
router is the HTTP boundary that was missing, so the rate could never be
entered and M1's calculadora, M5's BI and M6's DRE all reported R$ 0,00.

The interesting behaviour is not the CRUD — it is the resolution rule:
override wins over the função default, `0` is a real rate rather than
"unset", and a person with neither is reported as UNDEFINED instead of being
flattened to zero. A zero that means "no input" is the silent-error shape
these tests pin.

Every assertion pins ``.status_code`` per ``check_test_status_assertion``.
"""
from __future__ import annotations

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


class TestAuthBoundary:
    """Unauth'd callers never reach the store."""

    def test_listar_funcoes_sem_auth_retorna_401(self, api):
        assert api.raw().get("/api/custos/funcoes").status_code == 401

    def test_criar_funcao_sem_auth_retorna_401(self, api):
        resposta = api.raw().post("/api/custos/funcoes", json={"nome": "X"})
        assert resposta.status_code == 401

    def test_listar_profissionais_sem_auth_retorna_401(self, api):
        assert api.raw().get("/api/custos/profissionais").status_code == 401

    def test_criar_profissional_sem_auth_retorna_401(self, api):
        resposta = api.raw().post("/api/custos/profissionais", json={"nome": "X"})
        assert resposta.status_code == 401


class TestFuncoes:
    def test_criar_e_listar(self, api):
        criada = api.post(
            "/api/custos/funcoes", json={"nome": "Designer", "custo_hora_padrao": 85}
        )
        assert criada.status_code == 201
        assert criada.json()["custo_hora_padrao"] == 85

        listadas = api.get("/api/custos/funcoes")
        assert listadas.status_code == 200
        assert [f["nome"] for f in listadas.json()] == ["Designer"]

    def test_custo_zero_e_aceito(self, api):
        """0 is a real rate (an unpaid role), not a missing one."""
        resposta = api.post(
            "/api/custos/funcoes", json={"nome": "Estagiário", "custo_hora_padrao": 0}
        )
        assert resposta.status_code == 201
        assert resposta.json()["custo_hora_padrao"] == 0

    def test_custo_negativo_e_rejeitado(self, api):
        resposta = api.post(
            "/api/custos/funcoes", json={"nome": "Erro", "custo_hora_padrao": -5}
        )
        assert resposta.status_code == 422

    def test_campo_desconhecido_e_rejeitado(self, api):
        """StrictHttpModel — a typo'd field must not be silently dropped."""
        resposta = api.post(
            "/api/custos/funcoes", json={"nome": "X", "custo_hota_padrao": 10}
        )
        assert resposta.status_code == 422

    def test_atualizar(self, api):
        fid = api.post(
            "/api/custos/funcoes", json={"nome": "Designer", "custo_hora_padrao": 85}
        ).json()["id"]
        resposta = api.patch(
            f"/api/custos/funcoes/{fid}", json={"custo_hora_padrao": 95}
        )
        assert resposta.status_code == 200
        assert resposta.json()["custo_hora_padrao"] == 95

    def test_atualizar_inexistente_retorna_404(self, api):
        resposta = api.patch(
            "/api/custos/funcoes/00000000-0000-0000-0000-000000000000",
            json={"nome": "X"},
        )
        assert resposta.status_code == 404

    def test_patch_vazio_retorna_400(self, api):
        fid = api.post("/api/custos/funcoes", json={"nome": "D"}).json()["id"]
        assert api.patch(f"/api/custos/funcoes/{fid}", json={}).status_code == 400

    def test_remover(self, api):
        fid = api.post("/api/custos/funcoes", json={"nome": "D"}).json()["id"]
        assert api.delete(f"/api/custos/funcoes/{fid}").status_code == 200
        assert api.get("/api/custos/funcoes").json() == []

    def test_remover_inexistente_retorna_404(self, api):
        resposta = api.delete(
            "/api/custos/funcoes/00000000-0000-0000-0000-000000000000"
        )
        assert resposta.status_code == 404


class TestResolucaoDeCustoHora:
    """The rule M1, M5 and M6 all share — pinned here once."""

    def test_herda_o_padrao_da_funcao(self, api):
        fid = api.post(
            "/api/custos/funcoes", json={"nome": "Designer", "custo_hora_padrao": 85}
        ).json()["id"]
        criado = api.post(
            "/api/custos/profissionais", json={"nome": "Ana", "funcao_id": fid}
        )
        assert criado.status_code == 201
        assert criado.json()["custo_hora_efetivo"] == 85
        assert criado.json()["custo_hora_indefinido"] is False

    def test_override_vence_o_padrao(self, api):
        fid = api.post(
            "/api/custos/funcoes", json={"nome": "Designer", "custo_hora_padrao": 85}
        ).json()["id"]
        criado = api.post(
            "/api/custos/profissionais",
            json={"nome": "Bea", "funcao_id": fid, "custo_hora_override": 120},
        )
        assert criado.status_code == 201
        assert criado.json()["custo_hora_efetivo"] == 120

    def test_override_zero_nao_colapsa_para_o_padrao(self, api):
        """`0` and `None` must stay distinguishable — an intern costs nothing,
        which is NOT the same as inheriting the role's R$ 85."""
        fid = api.post(
            "/api/custos/funcoes", json={"nome": "Designer", "custo_hora_padrao": 85}
        ).json()["id"]
        criado = api.post(
            "/api/custos/profissionais",
            json={"nome": "Caio", "funcao_id": fid, "custo_hora_override": 0},
        )
        assert criado.status_code == 201
        assert criado.json()["custo_hora_efetivo"] == 0

    def test_sem_funcao_e_sem_override_e_reportado_como_indefinido(self, api):
        """The whole point: this must NOT come back as 0.0, which would read
        as a real rate and silently overstate every margin."""
        criado = api.post("/api/custos/profissionais", json={"nome": "Dani"})
        assert criado.status_code == 201
        corpo = criado.json()
        assert corpo["custo_hora_indefinido"] is True
        assert corpo["custo_hora_efetivo"] is None


class TestProfissionais:
    def test_listar_apenas_ativos(self, api):
        api.post("/api/custos/profissionais", json={"nome": "Ativa", "ativo": True})
        api.post("/api/custos/profissionais", json={"nome": "Inativa", "ativo": False})

        todos = api.get("/api/custos/profissionais")
        assert todos.status_code == 200
        assert len(todos.json()) == 2

        ativos = api.get("/api/custos/profissionais?apenas_ativos=true")
        assert ativos.status_code == 200
        assert [p["nome"] for p in ativos.json()] == ["Ativa"]

    def test_desativar_nao_exige_reenviar_o_nome(self, api):
        """A PATCH that toggles `ativo` must not have to resend `nome` — doing
        so would overwrite a concurrent rename."""
        pid = api.post("/api/custos/profissionais", json={"nome": "Ana"}).json()["id"]
        resposta = api.patch(f"/api/custos/profissionais/{pid}", json={"ativo": False})
        assert resposta.status_code == 200
        assert resposta.json()["ativo"] is False
        assert resposta.json()["nome"] == "Ana"

    def test_atualizar_inexistente_retorna_404(self, api):
        resposta = api.patch(
            "/api/custos/profissionais/00000000-0000-0000-0000-000000000000",
            json={"ativo": False},
        )
        assert resposta.status_code == 404

    def test_remover(self, api):
        pid = api.post("/api/custos/profissionais", json={"nome": "Ana"}).json()["id"]
        assert api.delete(f"/api/custos/profissionais/{pid}").status_code == 200
        assert api.get("/api/custos/profissionais").json() == []

    def test_remover_inexistente_retorna_404(self, api):
        resposta = api.delete(
            "/api/custos/profissionais/00000000-0000-0000-0000-000000000000"
        )
        assert resposta.status_code == 404
