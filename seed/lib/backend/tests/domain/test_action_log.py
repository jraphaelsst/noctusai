"""``domain.action_log.log_action`` — the failure path used to swallow
silently (``except Exception as e: logger.warning(...)``, no counter,
no fallback). Now goes through
``noctusai_lib.api.audit.sink.log_overflow_or_failure`` — same
contract ``RealAuditSink`` uses on a failed flush.
"""
from __future__ import annotations

import json

from noctusai_lib.api.audit.sink import overflow_or_failure_count
from noctusai_lib.domain.action_log import log_action


class _OkQuery:
    def __init__(self, recorder: list) -> None:
        self._recorder = recorder

    def insert(self, row):
        self._recorder.append(row)
        return self

    def execute(self):
        return None


class _OkDb:
    def __init__(self) -> None:
        self.inserted: list[dict] = []

    def table(self, name: str):
        self.table_name = name
        return _OkQuery(self.inserted)


class _FailingQuery:
    def insert(self, row):
        return self

    def execute(self):
        raise RuntimeError("db unreachable")


class _FailingDb:
    def table(self, name: str):
        return _FailingQuery()


def test_log_action_still_writes_to_the_caller_specified_table() -> None:
    """The destination must NOT change — see `action_log.py`'s module
    docstring on why silently redirecting to `public.audit_logs` would
    be a regression, not an adapter."""
    db = _OkDb()
    log_action(db, "user_actions_log", "usuario_id", "u1", "criar", "documento", "doc-1")
    assert db.table_name == "user_actions_log"
    assert db.inserted == [{
        "usuario_id": "u1",
        "tipo_acao": "criar",
        "tipo_entidade": "documento",
        "entidade_id": "doc-1",
        "descricao": "",
        "detalhes": {},
    }]


def test_log_action_failure_is_reported_never_silently_swallowed(capsys) -> None:
    before = overflow_or_failure_count()
    log_action(_FailingDb(), "user_actions_log", "usuario_id", "u1", "criar", "documento", "doc-1")
    assert overflow_or_failure_count() == before + 1
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    payload = json.loads(lines[-1])
    assert payload["audit_fallback"] == "action_log_write_failed"
    assert payload["entry"]["table_name"] == "user_actions_log"
    assert payload["entry"]["usuario_id"] == "u1"
