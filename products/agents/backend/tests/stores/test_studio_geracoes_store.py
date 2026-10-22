"""The Real generation store (PostgREST shapes + error mapping) and the Fake it must agree with. The vendor client is a
scripted DI double (never a patch of our own code)."""
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.stores._db_errors import StudioConflict
from app.stores.errors import NotFound
from app.stores.studio_geracoes import AREAS, FakeGeracaoStore, SupabaseGeracaoStore

ORG, AGENT, USER = uuid4(), uuid4(), uuid4()
NOW = "2026-10-22T00:00:00+00:00"


class _APIError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


class _Resp:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, rec, table):
        self._rec, self._table, self.calls = rec, table, []

    def __getattr__(self, name):
        def _chain(*a, **kw):
            self.calls.append((name, a, kw))
            return self
        return _chain

    def execute(self):
        self._rec.executed.append((self._table, list(self.calls)))
        out = self._rec.outcomes.pop(0) if self._rec.outcomes else []
        if isinstance(out, Exception):
            raise out
        return _Resp(out)


class _Client:
    def __init__(self, outcomes):
        self.outcomes, self.executed = list(outcomes), []

    def schema(self, name):
        assert name == "agents"
        return self

    def table(self, name):
        assert "." not in name, "bare table names only"
        return _Query(self, name)


def _row(gid: UUID | None = None, status: str = "pendente", **extra) -> dict:
    return {
        "id": str(gid or uuid4()), "org_id": str(ORG), "agent_id": str(AGENT), "status": status, "briefing": {"nome": "x"},
        "areas_solicitadas": ["secoes"], "forcar": False, "versao_gerador": 1, "modelo": "claude-opus-5",
        "provider": "anthropic", "plano": None, "custo_usd": "0.0000", "limite_usd": "5.00", "erro": None,
        "aprendizado": None, "criado_por": str(USER), "iniciado_em": None, "concluido_em": None,
        "created_at": NOW, "updated_at": NOW, **extra,
    }


def _create(store, **kw):
    return store.create_geracao(
        ORG, AGENT, briefing={"nome": "x"}, areas=["secoes", "textos"], forcar=False, modelo="claude-opus-5",
        provider="anthropic", limite_usd=kw.pop("limite_usd", 5.0), versao_gerador=1, criado_por=USER)


class TestReal:
    def test_create_inserts_the_run_then_one_pending_row_per_area(self):
        run = _row()
        client = _Client([[run], []])
        rec = _create(SupabaseGeracaoStore(client))
        (t1, c1), (t2, c2) = client.executed
        assert t1 == "geracoes" and t2 == "geracao_areas"
        payload = c1[0][1][0]
        assert payload["status"] == "pendente" and payload["limite_usd"] == 5.0 and payload["areas_solicitadas"] == ["secoes", "textos"]
        assert [r["area"] for r in c2[0][1][0]] == ["secoes", "textos"] and {r["status"] for r in c2[0][1][0]} == {"pendente"}
        assert rec.limite_usd == 5.0 and rec.status == "pendente"

    def test_a_second_active_run_is_the_typed_conflict(self):
        client = _Client([_APIError("23505", 'duplicate key value violates unique constraint "geracoes_one_active_idx"')])
        with pytest.raises(StudioConflict) as exc:
            _create(SupabaseGeracaoStore(client))
        assert exc.value.code == "geracao_em_andamento"

    def test_the_cap_is_refused_before_any_request(self):
        client = _Client([])
        with pytest.raises(ValueError):
            _create(SupabaseGeracaoStore(client), limite_usd=5.01)
        assert client.executed == []

    def test_a_conditional_update_filters_on_the_status_and_reports_a_lost_race_as_none(self):
        gid = uuid4()
        client = _Client([[], [_row(gid, "cancelada")]])  # no row matched; the run exists (cancelled)
        out = SupabaseGeracaoStore(client).update_geracao(ORG, gid, {"status": "concluida"}, only_if_status=("pendente", "executando"))
        assert out is None
        calls = client.executed[0][1]
        assert ("in_", ("status", ["pendente", "executando"]), {}) in calls

    def test_an_unknown_run_is_not_found(self):
        client = _Client([[], []])
        with pytest.raises(NotFound):
            SupabaseGeracaoStore(client).update_geracao(ORG, uuid4(), {"status": "falhou"}, only_if_status=("pendente",))

    def test_unknown_fields_are_refused(self):
        with pytest.raises(ValueError):
            SupabaseGeracaoStore(_Client([])).update_geracao(ORG, uuid4(), {"org_id": str(uuid4())})

    def test_the_orphan_sweep_fails_active_runs_and_their_unfinished_areas(self):
        a, b = uuid4(), uuid4()
        client = _Client([[{"id": str(a)}, {"id": str(b)}], [], []])
        assert SupabaseGeracaoStore(client).fail_orphans(erro="interrompida") == 2
        runs, areas_a, areas_b = client.executed
        assert ("in_", ("status", ["pendente", "executando"]), {}) in runs[1]
        assert ("eq", ("geracao_id", str(a)), {}) in areas_a[1] and ("eq", ("geracao_id", str(b)), {}) in areas_b[1]


class TestFakeAgreesWithTheReal:
    def test_same_refusals(self):
        fake = FakeGeracaoStore()
        _create(fake)
        with pytest.raises(StudioConflict) as exc:
            _create(fake)
        assert exc.value.code == "geracao_em_andamento"
        with pytest.raises(ValueError):
            _create(FakeGeracaoStore(), limite_usd=5.01)

    def test_conditional_updates_and_areas_in_order(self):
        fake = FakeGeracaoStore()
        rec = _create(fake)
        assert [a.area for a in fake.list_areas(ORG, rec.id)] == ["secoes", "textos"]
        assert fake.update_geracao(ORG, rec.id, {"status": "cancelada"}, only_if_status=("pendente",)).status == "cancelada"
        assert fake.update_geracao(ORG, rec.id, {"status": "concluida"}, only_if_status=("pendente", "executando")) is None
        assert fake.update_area(ORG, rec.id, "secoes", {"status": "executando"}, only_if_status=("cancelada",)) is None
        with pytest.raises(NotFound):
            fake.get_geracao(uuid4(), rec.id)
        assert set(AREAS) == {"secoes", "textos", "ferramentas", "decisoes", "specs", "skills", "configuracoes"}
