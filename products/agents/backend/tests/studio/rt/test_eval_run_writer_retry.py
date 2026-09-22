"""The eval-run writer survives transient transport errors (live run 2026-09-21:
one ``httpx.ReadError: Broken pipe`` on a result write aborted a 32-case run).

The Supabase client is replaced by a small recording double injected through
the writer's constructor (DI) — nothing of ours is patched."""
from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.stores.studio_eval_runs import SupabaseEvalRunWriter


class _Resp:
    def __init__(self, data):
        self.data = data


class _Builder:
    """Chainable stand-in for a PostgREST request builder."""

    def __init__(self, table: "_Table", op: str, payload=None):
        self.table, self.op, self.payload, self.filters = table, op, payload, {}

    def eq(self, col, val):
        self.filters[col] = val
        return self

    def in_(self, col, vals):
        return self

    def lt(self, col, val):
        return self

    def execute(self):
        return self.table.execute(self)


class _Table:
    def __init__(self, rows, script):
        self.rows, self.script = rows, script  # script: list of "fail" | "fail_after_write" | "ok"

    def update(self, payload):
        return _Builder(self, "update", payload)

    def select(self, _cols):
        return _Builder(self, "select")

    def _matching(self, filters):
        return [r for r in self.rows if all(str(r.get(k)) == str(v) for k, v in filters.items())]

    def execute(self, b: _Builder):
        mode = self.script.pop(0) if self.script else "ok"
        if mode == "fail":
            raise httpx.ReadError("Broken pipe")
        hit = self._matching(b.filters)
        if b.op == "update":
            for r in hit:
                r.update(b.payload)
            if mode == "fail_after_write":  # the write landed, the response was lost
                raise httpx.ReadError("Broken pipe")
            return _Resp([dict(r) for r in hit])
        return _Resp([dict(r) for r in hit])


class _Client:
    def __init__(self, tables):
        self.tables = tables

    def schema(self, _s):
        return self

    def table(self, name):
        return self.tables[name]


def _setup(results_script=(), runs_script=()):
    org, run, case = uuid4(), uuid4(), uuid4()
    results = _Table([{"org_id": org, "run_id": run, "case_id": case, "status": "pendente"}], list(results_script))
    runs = _Table([{"org_id": org, "id": run, "status": "executando"}], list(runs_script))
    writer = SupabaseEvalRunWriter(_Client({"eval_results": results, "eval_runs": runs}), retry_delays=(0.0, 0.0, 0.0))
    return writer, org, run, case, results, runs


def _write(writer, org, run, case):
    return writer.set_result(org, run, case, status="aprovado", saida="x", score=1.0, veredito=[], notas_juiz="", duracao_ms=1)


def test_set_result_retries_a_dropped_connection():
    writer, org, run, case, results, _ = _setup(results_script=["fail", "ok"])
    assert _write(writer, org, run, case) is True
    assert results.rows[0]["status"] == "aprovado"


def test_set_result_counts_a_lost_first_attempt_that_landed():
    # First attempt wrote the row but the response was lost; the retry's
    # conditional UPDATE (status=pendente) now matches nothing — the re-read
    # must report it as written, or the case would silently score 0.
    writer, org, run, case, results, _ = _setup(results_script=["fail_after_write", "ok", "ok"])
    assert _write(writer, org, run, case) is True


def test_set_result_reraises_when_the_database_stays_unreachable():
    writer, org, run, case, _, _ = _setup(results_script=["fail"] * 4)
    with pytest.raises(httpx.TransportError):
        _write(writer, org, run, case)


def test_finish_run_retries_and_honours_a_lost_first_attempt():
    writer, org, run, _, _, runs = _setup(runs_script=["fail_after_write", "ok", "ok"])
    assert writer.finish_run(org, run, status="concluida", aprovados=1, score=1.0) is True
    assert runs.rows[0]["status"] == "concluida"


def test_a_real_conflict_is_still_not_written():
    # No transport error: a result that is no longer pendente is NOT written.
    writer, org, run, case, results, _ = _setup()
    results.rows[0]["status"] = "reprovado"
    assert _write(writer, org, run, case) is False
