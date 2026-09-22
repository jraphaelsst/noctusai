"""Eval-run WRITER — the state transitions the eval runner drives on
``agents.eval_runs`` / ``agents.eval_results`` (Agent Studio contract §E6,
§B2; slice BE-RT).

Why a separate module from ``app/stores/studio_evals.py``: that store (cases,
run creation, reads, cancel) is owned by another slice; the runner's writes
are BE-RT's. They touch the same two tables, so the Fake here operates on the
SAME in-memory rows as :class:`~app.stores.studio_evals.FakeEvalStore` (it is
constructed over one) — a run created through the evals route is the run this
writer advances.

Every transition is CONDITIONAL on the current status (security review of
wave 1): ``pendente → executando`` only from ``pendente``; a result is written
only while it is still ``pendente``; ``executando → concluida|falhou`` only
from ``executando`` — so a run an admin cancelled can never be flipped to
``concluida`` by a runner that was mid-case.

Seed IO shape: ``EvalRunWriter`` Protocol + ``FakeEvalRunWriter`` +
``SupabaseEvalRunWriter`` + ``get_eval_run_writer(settings)``.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Callable, Protocol
from uuid import UUID

import httpx

from app.stores._util import utcnow, utcnow_iso
from app.stores.errors import NotFound
from app.stores.studio_evals import (
    ACTIVE_RUN_STATUSES,
    EvalRunRecord,
    FakeEvalStore,
    SupabaseEvalStore,
)

__all__ = [
    "RESULT_FINAL_STATUSES",
    "RUN_FINAL_STATUSES",
    "EvalRunWriter",
    "FakeEvalRunWriter",
    "SupabaseEvalRunWriter",
    "get_eval_run_writer",
]

_SCHEMA = "agents"
_RUNS_TABLE = "eval_runs"
_RESULTS_TABLE = "eval_results"

RESULT_FINAL_STATUSES = ("aprovado", "reprovado", "erro")
RUN_FINAL_STATUSES = ("concluida", "falhou")


class EvalRunWriter(Protocol):
    def claim_run(self, org_id: UUID, run_id: UUID) -> EvalRunRecord | None:
        """``pendente → executando`` (conditional). Returns the claimed run, or
        ``None`` when the run is no longer ``pendente`` (cancelled/failed
        before the runner reached it). Raises :class:`NotFound`."""
        ...

    def get_run_status(self, org_id: UUID, run_id: UUID) -> str:
        """Raises :class:`NotFound`."""
        ...

    def set_result(
        self, org_id: UUID, run_id: UUID, case_id: UUID, *, status: str, saida: str | None,
        score: float | None, veredito: list[dict[str, Any]] | None, notas_juiz: str | None,
        duracao_ms: int | None,
    ) -> bool:
        """UPDATE the pre-created ``pendente`` result row of ``(run_id,
        case_id)`` — never an insert. ``False`` when it was not ``pendente``."""
        ...

    def finish_run(
        self, org_id: UUID, run_id: UUID, *, status: str, aprovados: int, score: float | None,
        erro: str | None = None,
    ) -> bool:
        """``executando → concluida|falhou`` (conditional). ``False`` when the
        run is no longer ``executando`` (e.g. cancelled mid-run)."""
        ...

    def fail_orphaned_runs(self, *, started_before: datetime, erro: str) -> int:
        """Startup sweep: every ``pendente``/``executando`` run created before
        this process started becomes ``falhou`` with ``erro``. Returns the
        number of runs failed."""
        ...


def _check(status: str, allowed: tuple[str, ...], what: str) -> None:
    if status not in allowed:
        raise ValueError(f"{what} status must be one of {allowed}; got {status!r}")


class FakeEvalRunWriter:
    """In-memory writer over a :class:`FakeEvalStore`'s own rows."""

    def __init__(self, store: FakeEvalStore) -> None:
        self._store = store

    def _run_row(self, org_id: UUID, run_id: UUID) -> dict[str, Any]:
        row = self._store._runs.get(run_id)
        if row is None or row["org_id"] != org_id:
            raise NotFound(f"eval run {run_id} not found")
        return row

    def claim_run(self, org_id: UUID, run_id: UUID) -> EvalRunRecord | None:
        row = self._run_row(org_id, run_id)
        if row["status"] != "pendente":
            return None
        row["status"] = "executando"
        row["updated_at"] = utcnow()
        return FakeEvalStore._run_record(row)

    def get_run_status(self, org_id: UUID, run_id: UUID) -> str:
        return self._run_row(org_id, run_id)["status"]

    def set_result(
        self, org_id: UUID, run_id: UUID, case_id: UUID, *, status: str, saida: str | None,
        score: float | None, veredito: list[dict[str, Any]] | None, notas_juiz: str | None,
        duracao_ms: int | None,
    ) -> bool:
        _check(status, RESULT_FINAL_STATUSES, "result")
        self._run_row(org_id, run_id)
        for row in self._store._results.get(run_id, []):
            if row["case_id"] == case_id and row["org_id"] == org_id:
                if row["status"] != "pendente":
                    return False
                row.update({
                    "status": status, "saida": saida, "score": score, "veredito": veredito,
                    "notas_juiz": notas_juiz, "duracao_ms": duracao_ms, "updated_at": utcnow(),
                })
                return True
        raise NotFound(f"eval result ({run_id}, {case_id}) not found")

    def finish_run(
        self, org_id: UUID, run_id: UUID, *, status: str, aprovados: int, score: float | None,
        erro: str | None = None,
    ) -> bool:
        _check(status, RUN_FINAL_STATUSES, "run")
        row = self._run_row(org_id, run_id)
        if row["status"] != "executando":
            return False
        now = utcnow()
        row.update({
            "status": status, "aprovados": aprovados, "score": score, "erro": erro,
            "finished_at": now, "updated_at": now,
        })
        return True

    def fail_orphaned_runs(self, *, started_before: datetime, erro: str) -> int:
        n = 0
        now = utcnow()
        for row in self._store._runs.values():
            if row["status"] in ACTIVE_RUN_STATUSES and row["started_at"] < started_before:
                row.update({"status": "falhou", "erro": erro, "finished_at": now, "updated_at": now})
                n += 1
        return n


logger = logging.getLogger(__name__)

#: Transient transport failures retried on the runner's writes. A single eval
#: case can hold its turn + judge for minutes, and the idle keep-alive
#: connection to PostgREST gets dropped server-side — the next write then
#: fails with ``httpx.ReadError: Broken pipe`` (live run 2026-09-21: one such
#: error aborted a 32-case run at 14/32). Every write here is an idempotent,
#: status-conditional UPDATE, so a retry is safe.
_RETRY_DELAYS = (0.25, 1.0, 3.0)


def _with_retry(
    what: str, call: Callable[[], Any], *, delays: tuple[float, ...] = _RETRY_DELAYS,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[Any, bool]:
    """Run ``call``; on a transport error retry per :data:`_RETRY_DELAYS`.
    Returns ``(result, retried)`` — ``retried`` tells a conditional UPDATE that
    came back empty to check whether the lost first attempt already landed.
    Re-raises the last error when every attempt failed (the runner then fails
    the run loudly — never a silent skip)."""
    retried = False
    for attempt, delay in enumerate((*delays, None)):
        try:
            return call(), retried
        except httpx.TransportError as exc:
            if delay is None:
                raise
            logger.warning("agents.eval_runs.transport_retry what=%s attempt=%d: %s", what, attempt + 1, exc)
            retried = True
            sleep(delay)
    raise AssertionError("unreachable")


class SupabaseEvalRunWriter:
    """Real :class:`EvalRunWriter` — conditional PostgREST UPDATEs (one
    request = one statement, so each transition is atomic)."""

    def __init__(self, client: Any, *, retry_delays: tuple[float, ...] = _RETRY_DELAYS) -> None:
        self._client = client
        self._retry_delays = retry_delays

    def _retry(self, what: str, call: Callable[[], Any]) -> tuple[Any, bool]:
        return _with_retry(what, call, delays=self._retry_delays)

    def _runs(self):
        return self._client.schema(_SCHEMA).table(_RUNS_TABLE)

    def _results(self):
        return self._client.schema(_SCHEMA).table(_RESULTS_TABLE)

    def claim_run(self, org_id: UUID, run_id: UUID) -> EvalRunRecord | None:
        resp, retried = self._retry("claim_run", lambda: (
            self._runs().update({"status": "executando", "updated_at": utcnow_iso()})
            .eq("org_id", str(org_id)).eq("id", str(run_id)).eq("status", "pendente")
            .execute()
        ))
        rows = resp.data or []
        if rows:
            return SupabaseEvalStore._run_record(rows[0])
        status = self.get_run_status(org_id, run_id)  # NotFound for an unknown id
        if retried and status == "executando":
            # The lost first attempt claimed it — this runner owns the run.
            row = self._retry("claim_run.reread", lambda: (
                self._runs().select("*").eq("org_id", str(org_id)).eq("id", str(run_id)).execute()
            ))[0].data[0]
            return SupabaseEvalStore._run_record(row)
        return None

    def get_run_status(self, org_id: UUID, run_id: UUID) -> str:
        resp, _ = self._retry("get_run_status", lambda: (
            self._runs().select("status").eq("org_id", str(org_id)).eq("id", str(run_id)).execute()
        ))
        rows = resp.data or []
        if not rows:
            raise NotFound(f"eval run {run_id} not found")
        return rows[0]["status"]

    def set_result(
        self, org_id: UUID, run_id: UUID, case_id: UUID, *, status: str, saida: str | None,
        score: float | None, veredito: list[dict[str, Any]] | None, notas_juiz: str | None,
        duracao_ms: int | None,
    ) -> bool:
        _check(status, RESULT_FINAL_STATUSES, "result")
        resp, retried = self._retry("set_result", lambda: (
            self._results().update({
                "status": status, "saida": saida, "score": score, "veredito": veredito,
                "notas_juiz": notas_juiz, "duracao_ms": duracao_ms, "updated_at": utcnow_iso(),
            })
            .eq("org_id", str(org_id)).eq("run_id", str(run_id)).eq("case_id", str(case_id))
            .eq("status", "pendente")
            .execute()
        ))
        if resp.data:
            return True
        if retried:
            # Did the lost first attempt land? Then it IS written (same values).
            row = self._retry("set_result.reread", lambda: (
                self._results().select("status").eq("org_id", str(org_id)).eq("run_id", str(run_id))
                .eq("case_id", str(case_id)).execute()
            ))[0].data
            return bool(row) and row[0]["status"] == status
        return False

    def finish_run(
        self, org_id: UUID, run_id: UUID, *, status: str, aprovados: int, score: float | None,
        erro: str | None = None,
    ) -> bool:
        _check(status, RUN_FINAL_STATUSES, "run")
        now = utcnow_iso()
        resp, retried = self._retry("finish_run", lambda: (
            self._runs().update({
                "status": status, "aprovados": aprovados, "score": score, "erro": erro,
                "finished_at": now, "updated_at": now,
            })
            .eq("org_id", str(org_id)).eq("id", str(run_id)).eq("status", "executando")
            .execute()
        ))
        if resp.data:
            return True
        return retried and self.get_run_status(org_id, run_id) == status

    def fail_orphaned_runs(self, *, started_before: datetime, erro: str) -> int:
        now = utcnow_iso()
        # postgrest-unbounded-ok: the `.in_()` list is the 2-element status constant.
        resp = (
            self._runs().update({"status": "falhou", "erro": erro, "finished_at": now, "updated_at": now})
            .in_("status", list(ACTIVE_RUN_STATUSES))
            .lt("started_at", started_before.isoformat())
            .execute()
        )
        return len(resp.data or [])


def get_eval_run_writer(settings: Any) -> EvalRunWriter:
    """Real when a Supabase service-role key is configured; otherwise a Fake
    over a fresh :class:`FakeEvalStore` (same per-call shape as every other
    Fake factory in this product — tests bind a shared one through the
    ``get_eval_run_writer_dep`` seam)."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeEvalRunWriter(FakeEvalStore())
    from app.database import get_admin_client

    return SupabaseEvalRunWriter(get_admin_client())
