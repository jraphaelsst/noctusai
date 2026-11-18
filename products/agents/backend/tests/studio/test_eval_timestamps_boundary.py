"""PostgREST hands timestamptz as ISO strings: the run/loop row mappers parse them, so progress never 500s
(prod 2026-11-18: ``'str' object has no attribute 'tzinfo'`` on GET .../runs/{id}/progresso)."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.stores.studio_eval_loops import _loop_de
from app.stores.studio_evals import SupabaseEvalStore
from app.studio.eval_progresso import progresso_comportamento

_TS = "2026-11-18T19:14:00.123456+00:00"


def _run_row(**over):
    row = {
        "id": str(uuid4()), "org_id": str(uuid4()), "agent_id": str(uuid4()), "version_id": str(uuid4()),
        "compiled_hash": "h", "status": "executando", "total": 4, "aprovados": 0, "score": None, "limiar": 0.8,
        "started_by": str(uuid4()), "started_at": _TS, "finished_at": None, "erro": None,
        "created_at": _TS, "updated_at": "2026-11-18T19:14:05Z",
    }
    row.update(over)
    return row


def test_run_record_parses_string_timestamps():
    rec = SupabaseEvalStore._run_record(_run_row(finished_at="2026-11-18T19:15:00Z"))
    for v in (rec.started_at, rec.finished_at, rec.created_at, rec.updated_at):
        assert isinstance(v, datetime) and v.tzinfo is not None


def test_progress_with_string_origin_row_does_not_raise():
    rec = SupabaseEvalStore._run_record(_run_row())
    out = progresso_comportamento(rec, [], agora=datetime(2026, 11, 18, 19, 16, tzinfo=timezone.utc))
    assert out["decorrido_s"] == 119.9 and out["ativo"] is True


def test_progress_with_datetime_row():
    rec = SupabaseEvalStore._run_record(_run_row(started_at=datetime(2026, 11, 18, 19, 14, tzinfo=timezone.utc)))
    assert progresso_comportamento(rec, [], agora=datetime(2026, 11, 18, 19, 15, tzinfo=timezone.utc))["decorrido_s"] == 60.0


def test_loop_record_parses_string_timestamps():
    r = {"id": str(uuid4()), "org_id": str(uuid4()), "agent_id": str(uuid4()), "agente_chave": "a", "suite": "comportamento",
         "rodadas_planejadas": 3, "alvo": 0.95, "piso": 0.8, "orcamento_usd": 1, "gasto_usd": 0, "status": "ativo",
         "started_by": str(uuid4()), "started_at": _TS, "stopped_at": None}
    rec = _loop_de(r)
    assert rec.started_at.tzinfo is not None and rec.stopped_at is None
