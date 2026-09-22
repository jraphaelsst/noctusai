"""``FakeEvalStore`` behaviour (contract §B2/§D4) + `SupabaseEvalGate`
shape (contract §J2.1). Version resolution lives in BE-DEF's store — the
eval store takes the version id as given."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.stores._db_errors import StudioConflict
from app.stores.errors import NotFound
from app.stores.studio_evals import EvalCaseInput, FakeEvalStore, SupabaseEvalGate

ORG = uuid4()
AGENT = uuid4()
VERSION = uuid4()
USER = uuid4()


@pytest.fixture
def store() -> FakeEvalStore:
    return FakeEvalStore()


def _case_input(slug: str = "case-1", **overrides) -> EvalCaseInput:
    defaults = dict(
        slug=slug, titulo="Caso 1", entrada="Escreva um roteiro",
        criterios={"deve": ["menciona reciclagem"], "nao_deve": []},
    )
    defaults.update(overrides)
    return EvalCaseInput(**defaults)


class TestCases:
    def test_create_and_list(self, store):
        store.create_case(ORG, AGENT, _case_input())
        items = store.list_cases(ORG, AGENT)
        assert [c.slug for c in items] == ["case-1"]

    def test_criterios_requires_at_least_one_item(self, store):
        with pytest.raises(ValueError):
            store.create_case(ORG, AGENT, _case_input(criterios={"deve": [], "nao_deve": []}))

    def test_duplicate_slug_rejected(self, store):
        store.create_case(ORG, AGENT, _case_input())
        with pytest.raises(StudioConflict) as exc:
            store.create_case(ORG, AGENT, _case_input())
        assert exc.value.code == "slug_taken"

    def test_update_partial_fields(self, store):
        case = store.create_case(ORG, AGENT, _case_input())
        updated = store.update_case(ORG, AGENT, case.id, titulo="Caso 1 revisado")
        assert updated.titulo == "Caso 1 revisado"
        assert updated.entrada == case.entrada

    def test_delete_then_get_not_found(self, store):
        case = store.create_case(ORG, AGENT, _case_input())
        store.delete_case(ORG, AGENT, case.id)
        with pytest.raises(NotFound):
            store.get_case(ORG, AGENT, case.id)

    def test_foreign_case_id_not_found(self, store):
        with pytest.raises(NotFound):
            store.get_case(ORG, AGENT, uuid4())


class TestCreateRun:
    def test_runs_against_all_active_cases_when_case_ids_omitted(self, store):
        c1 = store.create_case(ORG, AGENT, _case_input("case-1"))
        store.create_case(ORG, AGENT, _case_input("case-2", ativo=False))
        run = store.create_run(
            ORG, AGENT, VERSION, compiled_hash="sha256:abc123", limiar=0.8,
            case_ids=None, started_by=USER,
        )
        assert run.total == 1
        assert run.status == "pendente"
        results = store.list_results_with_cases(ORG, AGENT, run.id)
        assert [r.result.case_id for r in results] == [c1.id]

    def test_explicit_case_ids_validated_against_agent(self, store):
        store.create_case(ORG, AGENT, _case_input("case-1"))
        with pytest.raises(NotFound):
            store.create_run(
                ORG, AGENT, VERSION, compiled_hash="sha256:abc123", limiar=0.8,
                case_ids=[uuid4()], started_by=USER,
            )

    def test_empty_case_set_rejected(self, store):
        with pytest.raises(ValueError):
            store.create_run(
                ORG, AGENT, VERSION, compiled_hash="sha256:abc123", limiar=0.8,
                case_ids=None, started_by=USER,
            )

    def test_second_run_for_same_version_conflicts_while_first_is_active(self, store):
        store.create_case(ORG, AGENT, _case_input())
        store.create_run(
            ORG, AGENT, VERSION, compiled_hash="sha256:abc123", limiar=0.8,
            case_ids=None, started_by=USER,
        )
        with pytest.raises(StudioConflict):
            store.create_run(
                ORG, AGENT, VERSION, compiled_hash="sha256:abc123", limiar=0.8,
                case_ids=None, started_by=USER,
            )

    def test_new_run_allowed_once_prior_run_is_cancelled(self, store):
        store.create_case(ORG, AGENT, _case_input())
        first = store.create_run(
            ORG, AGENT, VERSION, compiled_hash="sha256:abc123", limiar=0.8,
            case_ids=None, started_by=USER,
        )
        store.cancel_run(ORG, AGENT, first.id)
        second = store.create_run(
            ORG, AGENT, VERSION, compiled_hash="sha256:abc123", limiar=0.8,
            case_ids=None, started_by=USER,
        )
        assert second.id != first.id


class TestCreateRunCostControl:
    """Contract §L — `modelo_geracao` / `limite_usd` on `create_run`."""

    def test_modelo_geracao_and_limite_usd_round_trip(self, store):
        store.create_case(ORG, AGENT, _case_input())
        run = store.create_run(
            ORG, AGENT, VERSION, compiled_hash="sha256:abc123", limiar=0.8,
            case_ids=None, started_by=USER, modelo_geracao="claude-haiku-4-5", limite_usd=1.5,
        )
        assert run.modelo_geracao == "claude-haiku-4-5"
        assert run.limite_usd == 1.5
        assert run.custo_usd is None

    def test_modelo_geracao_defaults_to_none(self, store):
        store.create_case(ORG, AGENT, _case_input())
        run = store.create_run(
            ORG, AGENT, VERSION, compiled_hash="sha256:abc123", limiar=0.8,
            case_ids=None, started_by=USER,
        )
        assert run.modelo_geracao is None
        assert run.limite_usd is None

    def test_modelo_geracao_outside_allowlist_rejected(self, store):
        store.create_case(ORG, AGENT, _case_input())
        with pytest.raises(ValueError):
            store.create_run(
                ORG, AGENT, VERSION, compiled_hash="sha256:abc123", limiar=0.8,
                case_ids=None, started_by=USER, modelo_geracao="claude-opus-5",
            )

    def test_limite_usd_out_of_range_rejected(self, store):
        store.create_case(ORG, AGENT, _case_input())
        with pytest.raises(ValueError):
            store.create_run(
                ORG, AGENT, VERSION, compiled_hash="sha256:abc123", limiar=0.8,
                case_ids=None, started_by=USER, limite_usd=0,
            )
        with pytest.raises(ValueError):
            store.create_run(
                ORG, AGENT, VERSION, compiled_hash="sha256:abc123", limiar=0.8,
                case_ids=None, started_by=USER, limite_usd=50.01,
            )


class TestRunLifecycle:
    def test_mark_run_failed(self, store):
        store.create_case(ORG, AGENT, _case_input())
        run = store.create_run(
            ORG, AGENT, VERSION, compiled_hash="sha256:abc123", limiar=0.8,
            case_ids=None, started_by=USER,
        )
        failed = store.mark_run_failed(ORG, run.id, erro="eval_runner_unavailable")
        assert failed.status == "falhou"
        assert failed.erro == "eval_runner_unavailable"
        assert failed.finished_at is not None

    def test_cancel_non_active_run_conflicts(self, store):
        store.create_case(ORG, AGENT, _case_input())
        run = store.create_run(
            ORG, AGENT, VERSION, compiled_hash="sha256:abc123", limiar=0.8,
            case_ids=None, started_by=USER,
        )
        store.cancel_run(ORG, AGENT, run.id)
        with pytest.raises(StudioConflict):
            store.cancel_run(ORG, AGENT, run.id)

    def test_list_runs_filters_by_version_and_orders_newest_first(self, store):
        store.create_case(ORG, AGENT, _case_input())
        first = store.create_run(
            ORG, AGENT, VERSION, compiled_hash="sha256:abc123", limiar=0.8,
            case_ids=None, started_by=USER,
        )
        store.cancel_run(ORG, AGENT, first.id)
        second = store.create_run(
            ORG, AGENT, VERSION, compiled_hash="sha256:abc123", limiar=0.8,
            case_ids=None, started_by=USER,
        )
        runs = store.list_runs(ORG, AGENT, VERSION)
        assert [r.id for r in runs] == [second.id, first.id]


class TestSupabaseEvalGateShape:
    def test_no_concluded_run_returns_none(self):

        class _EmptyTable:
            def select(self, *_a, **_k):
                return self

            def eq(self, *_a, **_k):
                return self

            def is_(self, *_a, **_k):
                return self

            def order(self, *_a, **_k):
                return self

            def limit(self, *_a, **_k):
                return self

            def execute(self):
                class _Resp:
                    data = []

                return _Resp()

        class _EmptyClient:
            def schema(self, _name):
                return self

            def table(self, _name):
                return _EmptyTable()

        gate = SupabaseEvalGate(_EmptyClient())
        assert gate.latest_concluded_run(ORG, VERSION) is None

    def test_found_run_constructs_gate_run(self):
        run_id = uuid4()

        class _FoundTable:
            def select(self, *_a, **_k):
                return self

            def eq(self, *_a, **_k):
                return self

            def is_(self, *_a, **_k):
                return self

            def order(self, *_a, **_k):
                return self

            def limit(self, *_a, **_k):
                return self

            def execute(self):
                class _Resp:
                    data = [{
                        "id": str(run_id), "score": 0.9, "limiar": 0.8,
                        "compiled_hash": "sha256:abc123", "status": "concluida",
                        "completa": True, "total": 4,
                    }]

                return _Resp()

        class _FoundClient:
            def schema(self, _name):
                return self

            def table(self, _name):
                return _FoundTable()

        gate = SupabaseEvalGate(_FoundClient())
        result = gate.latest_concluded_run(ORG, VERSION)
        assert result is not None
        assert result.id == run_id
        assert result.score == 0.9
        assert result.compiled_hash == "sha256:abc123"
        assert (result.completa, result.total) == (True, 4)

    def test_filters_out_a_cheaper_iteration_run_via_modelo_geracao_is_null(self):
        """Contract §L: the gate query itself excludes a run started with a
        `modelo_geracao` override — the SPY records the exact filter chain
        (rather than trying to simulate real PostgREST filtering in this
        hand-rolled stub) so the assertion fails loudly if the `.is_(...)`
        call is ever dropped."""

        class _SpyTable:
            def __init__(self):
                self.calls: list[tuple[str, tuple, dict]] = []

            def _record(self, name, *a, **k):
                self.calls.append((name, a, k))
                return self

            def select(self, *a, **k):
                return self._record("select", *a, **k)

            def eq(self, *a, **k):
                return self._record("eq", *a, **k)

            def is_(self, *a, **k):
                return self._record("is_", *a, **k)

            def order(self, *a, **k):
                return self._record("order", *a, **k)

            def limit(self, *a, **k):
                return self._record("limit", *a, **k)

            def execute(self):
                class _Resp:
                    data = []

                return _Resp()

        class _SpyClient:
            def __init__(self):
                self.table_obj = _SpyTable()

            def schema(self, _name):
                return self

            def table(self, _name):
                return self.table_obj

        client = _SpyClient()
        gate = SupabaseEvalGate(client)
        gate.latest_concluded_run(ORG, VERSION)
        assert ("is_", ("modelo_geracao", "null"), {}) in client.table_obj.calls
