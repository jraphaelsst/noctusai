"""BIService — the custo real / taxa de refação numbers Módulo 5's BI, the
DRE and the financeiro report all read.

Tech-lead addendum (2026-09): `duracao_segundos` (migration 028) fixed the
Esteira UI's own "Total" display (achado 22 — three 40-second sessions used
to sum to 0 instead of 2 minutes, because `minutos` floors PER SEGMENT
before anything is summed), but BIService kept reading `minutos` directly —
the exact same truncation, just one layer deeper, silently understating
every client's measured cost and margin.
"""
import pytest
from noctusai_lib.integrations.persistence import SqliteRecordStore

from app.dependencies import coerce_org_uuid
from app.repositories import Repositorios
from app.services.bi_service import BIService

ORG = str(coerce_org_uuid("test-org-123"))


@pytest.fixture
def repos() -> Repositorios:
    store = SqliteRecordStore(":memory:")
    from app.store import aplicar_schema_sqlite

    aplicar_schema_sqlite(store)
    return Repositorios(store)


@pytest.fixture
def cliente(repos) -> dict:
    return repos.cliente.criar(ORG, {"nome": "Padaria Sol"})


@pytest.fixture
def profissional(repos) -> dict:
    funcao = repos.funcao.criar(ORG, {"nome": "designer", "custo_hora_padrao": 100.0})
    return repos.profissional.criar(
        ORG, {"nome": "Ana", "usuario_id": "user-1", "funcao_id": funcao["id"]}
    )


@pytest.fixture
def tarefa(repos, cliente) -> dict:
    pauta = repos.pauta.criar(ORG, {"cliente_id": cliente["id"], "titulo": "Post"})
    return repos.tarefa.criar(
        ORG, {"pauta_id": pauta["id"], "titulo": "Arte", "etapa_id": "etapa-1"}
    )


def _apontar(repos, tarefa, *, usuario_id="user-1", minutos=0, duracao_segundos=None, iniciado_em=None):
    # A partial unique index allows at most ONE OPEN segment
    # (`encerrado_em IS NULL`) per usuário — every test segment here is a
    # finished one, so each needs its own `encerrado_em`.
    inicio = iniciado_em or "2026-08-01T09:00:00"
    dados = {
        "tarefa_id": tarefa["id"], "usuario_id": usuario_id,
        "iniciado_em": inicio, "encerrado_em": inicio,
        "minutos": minutos,
    }
    if duracao_segundos is not None:
        dados["duracao_segundos"] = duracao_segundos
    return repos.apontamento.criar(ORG, dados)


class TestEficienciaPorClienteSubMinuto:
    def test_three_forty_second_sessions_sum_to_two_minutes_not_zero(
        self, repos, cliente, profissional, tarefa
    ):
        for _ in range(3):
            _apontar(repos, tarefa, minutos=0, duracao_segundos=40)
        [linha] = BIService(repos).eficiencia_por_cliente(ORG)
        assert linha.minutos == 2  # 120s // 60, not 3× floor(40/60)=0

    def test_cost_uses_precise_seconds_not_floored_minutes(
        self, repos, cliente, profissional, tarefa
    ):
        """100 R$/h × (120s / 3600) = R$ 3.33 — a floored-minutes calc would
        have costed R$ 0.00 (3 × floor(40s → 0 min))."""
        for _ in range(3):
            _apontar(repos, tarefa, minutos=0, duracao_segundos=40)
        [linha] = BIService(repos).eficiencia_por_cliente(ORG)
        assert linha.custo_reais == pytest.approx(3.33, abs=0.01)

    def test_legacy_rows_without_duracao_segundos_still_use_minutos(
        self, repos, cliente, profissional, tarefa
    ):
        _apontar(repos, tarefa, minutos=65, duracao_segundos=None)
        [linha] = BIService(repos).eficiencia_por_cliente(ORG)
        assert linha.minutos == 65
        assert linha.custo_reais == pytest.approx((65 / 60) * 100.0, abs=0.01)

    def test_mixed_precise_and_legacy_rows_sum_correctly(
        self, repos, cliente, profissional, tarefa
    ):
        _apontar(repos, tarefa, minutos=10, duracao_segundos=None)  # 600s
        _apontar(repos, tarefa, minutos=0, duracao_segundos=30)     # 30s
        [linha] = BIService(repos).eficiencia_por_cliente(ORG)
        assert linha.minutos == 10  # 630s // 60 == 10
        assert linha.custo_reais == pytest.approx((630 / 3600) * 100.0, abs=0.01)


class TestEficienciaPorClienteCompetencia:
    """`competencia` scopes `custo_reais`/`minutos` — never `tarefas`/
    `refacoes`, which stay all-time regardless (a refação count is not a
    monthly fact). `None` (the default) is exactly the pre-existing
    full-history behaviour every OTHER call site here still relies on."""

    def test_none_is_full_history_the_unchanged_default(self, repos, cliente, profissional, tarefa):
        _apontar(repos, tarefa, minutos=600, iniciado_em="2026-07-15T09:00:00")
        _apontar(repos, tarefa, minutos=240, iniciado_em="2026-08-01T09:00:00")
        [linha] = BIService(repos).eficiencia_por_cliente(ORG)
        assert linha.minutos == 840
        assert linha.custo_reais == pytest.approx(1400.0, abs=0.01)

    def test_a_competencia_scopes_cost_to_that_month_only(self, repos, cliente, profissional, tarefa):
        _apontar(repos, tarefa, minutos=600, iniciado_em="2026-07-15T09:00:00")
        _apontar(repos, tarefa, minutos=240, iniciado_em="2026-08-01T09:00:00")
        [linha] = BIService(repos).eficiencia_por_cliente(ORG, "2026-08")
        assert linha.minutos == 240
        assert linha.custo_reais == pytest.approx(400.0, abs=0.01)

    def test_a_competencia_with_nothing_apontado_is_zero_not_an_error(
        self, repos, cliente, profissional, tarefa
    ):
        _apontar(repos, tarefa, minutos=600, iniciado_em="2026-07-15T09:00:00")
        [linha] = BIService(repos).eficiencia_por_cliente(ORG, "2026-09")
        assert linha.minutos == 0
        assert linha.custo_reais == 0.0

    def test_task_and_refacao_counts_are_never_scoped_by_competencia(
        self, repos, cliente, profissional, tarefa
    ):
        """Only cost is a monthly fact; a task's own refação history is not."""
        repos.tarefa.atualizar(ORG, tarefa["id"], {"refacoes": 2})
        _apontar(repos, tarefa, minutos=600, iniciado_em="2026-07-15T09:00:00")
        [linha] = BIService(repos).eficiencia_por_cliente(ORG, "2026-09")  # no apontamento this month
        assert linha.tarefas == 1
        assert linha.refacoes == 2

    def test_uncosted_alert_is_also_scoped_to_the_competencia(self, repos, cliente, tarefa):
        _apontar(repos, tarefa, usuario_id="sem-rate", minutos=300, iniciado_em="2026-07-15T09:00:00")
        [linha] = BIService(repos).eficiencia_por_cliente(ORG, "2026-08")
        assert linha.apontamentos_sem_custo == 0
        assert linha.alertas == []


class TestCustoDaTarefaSubMinuto:
    def test_sub_minute_segments_are_not_costed_as_free(self, repos, profissional, tarefa):
        _apontar(repos, tarefa, minutos=0, duracao_segundos=40)
        _apontar(repos, tarefa, minutos=0, duracao_segundos=40)
        total, alertas = BIService(repos).custo_da_tarefa(ORG, tarefa["id"])
        assert total == pytest.approx((80 / 3600) * 100.0, abs=0.01)
        assert alertas == []

    def test_an_uncosted_apontamento_is_alerted_not_silently_dropped(self, repos, tarefa):
        # No profissional/funcao registered at all ⇒ no resolvable rate.
        _apontar(repos, tarefa, minutos=0, duracao_segundos=90)
        total, alertas = BIService(repos).custo_da_tarefa(ORG, tarefa["id"])
        assert total == 0.0
        assert len(alertas) == 1
