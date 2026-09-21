"""``FakeEvalStore`` behaviour (contract §B2/§D4) + `SupabaseEvalGate`
shape (contract §J2.1)."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.stores.errors import Conflict, NotFound
from app.stores.studio_evals import EvalCaseInput, FakeEvalStore, SupabaseEvalGate

ORG = uuid4()
AGENT = uuid4()
VERSION = uuid4()
USER = uuid4()


@pytest.fixture
def store() -> FakeEvalStore:
    s = FakeEvalStore()
    s.seed_version(ORG, AGENT, VERSION, compiled_hash="sha256:abc123")
    return s


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
        with pytest.raises(ValueError):
            store.create_case(ORG, AGENT, _case_input())

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


class TestVersionRef:
    def test_get_version_ref(self, store):
        ref = store.get_version_ref(ORG, AGENT, VERSION)
        assert ref.compiled_hash == "sha256:abc123"

    def test_foreign_version_not_found(self, store):
        with pytest.raises(NotFound):
            store.get_version_ref(ORG, AGENT, uuid4())
        other_org = uuid4()
        with pytest.raises(NotFound):
            store.get_version_ref(other_org, AGENT, VERSION)


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
        with pytest.raises(Conflict):
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
        with pytest.raises(Conflict):
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
    def test_no_concluded_run_returns_none_without_importing_studio_models(self):
        """The 'not found' branch never touches `app.studio.models` — this
        must pass standalone in THIS branch, before BE-DEF merges 012."""

        class _EmptyTable:
            def select(self, *_a, **_k):
                return self

            def eq(self, *_a, **_k):
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
        """Exercises the lazy `from app.studio.models import GateRun`
        branch — only meaningful once BE-DEF's `app/studio/models.py`
        merges (contract §J2.1); skipped in this standalone branch."""
        pytest.importorskip("app.studio.models")

        run_id = uuid4()

        class _FoundTable:
            def select(self, *_a, **_k):
                return self

            def eq(self, *_a, **_k):
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
