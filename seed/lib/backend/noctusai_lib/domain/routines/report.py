"""Daily report of the routines -- built on ``BaseDigestService`` (fetch -> aggregate -> narrate -> render).

The report is DETERMINISTIC (no LLM): it counts what the event log recorded in the window --
runs / errors / drafts / auto-published / approved / rejected (with reasons) / kill-switch flips --
per routine, so "did my routines run and what did they do" never depends on a model.
``aggregate_events`` is the pure core shared with the router's ``GET /report``.
"""
from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Sequence

from noctusai_lib.domain.digest.base import BaseDigestService
from noctusai_lib.domain.digest.types import DigestWindow
from noctusai_lib.domain.routines.store import RoutineStore
from noctusai_lib.domain.routines.types import EventKind, Routine, RoutineEvent
from uuid import UUID

_COUNTERS = ("runs", "errors", "collected", "drafts", "published", "duplicates", "approved", "rejected", "flips")


def _blank() -> dict[str, Any]:
    return {**{k: 0 for k in _COUNTERS}, "rejections": []}


def aggregate_events(routines: Sequence[Routine], events: Sequence[RoutineEvent]) -> dict[str, Any]:
    """``{"routines": [{id, name, mode, ativo, killed, runs, errors, ...}], "master_flips": n, "totals": {...}}``."""
    by_id: dict[UUID, dict[str, Any]] = {
        r.id: {"id": str(r.id), "name": r.name, "mode": r.mode, "ativo": r.ativo, "killed": r.killed, **_blank()}
        for r in routines
    }
    master_flips = 0
    for e in events:
        if e.routine_id is None:
            master_flips += 1
            continue
        row = by_id.get(e.routine_id)
        if row is None:
            continue
        d = e.detail or {}
        if e.kind == EventKind.RUN_FINISHED.value:
            row["runs"] += 1
            row["errors"] += int(d.get("status") == "error")
            for k in ("collected", "drafts", "published", "duplicates"):
                row[k] += int(d.get(k) or 0)
        elif e.kind == EventKind.APPROVED.value and not d.get("auto"):
            row["approved"] += 1
        elif e.kind == EventKind.REJECTED.value:
            row["rejected"] += 1
            row["rejections"].append(e.reason)
        elif e.kind in (EventKind.ENABLED.value, EventKind.DISABLED.value, EventKind.KILLED.value):
            row["flips"] += 1
    rows = sorted(by_id.values(), key=lambda r: r["name"])
    totals = {k: sum(r[k] for r in rows) for k in _COUNTERS}
    return {"routines": rows, "master_flips": master_flips, "totals": totals}


class RoutinesDailyReport(BaseDigestService):
    """``await RoutinesDailyReport(client=store, org_id="...").run(DigestWindow(period_days=1))``.

    ``client`` is the ``RoutineStore`` (this service reads nothing else). ``now`` is injectable."""

    def __init__(self, *, client: RoutineStore, org_id: str,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        super().__init__(client=client, org_id=org_id)
        self._now = now

    @property
    def _store(self) -> RoutineStore:
        return self.client

    async def _fetch_window(self, window: DigestWindow) -> Mapping[str, Any]:
        org = UUID(str(self.org_id))
        since = self._now() - timedelta(days=window.period_days or 1)
        return {
            "routines": self._store.list_routines(org),
            "events": self._store.list_events(org, since=since),
            "master": self._store.master_enabled(org),
            "days": window.period_days or 1,
        }

    def _aggregate(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        agg = aggregate_events(raw["routines"], raw["events"])
        agg["master_enabled"] = raw["master"]
        agg["days"] = raw["days"]
        return agg

    async def _generate_narrative(self, agg: Mapping[str, Any], window: DigestWindow) -> str:
        t = agg["totals"]
        head = (
            f"Ultimas {agg['days'] * 24}h: {t['runs']} execucoes ({t['errors']} com erro), "
            f"{t['drafts']} rascunhos, {t['published']} publicados automaticamente, "
            f"{t['approved']} aprovados e {t['rejected']} rejeitados por pessoas."
        )
        notes = []
        if not agg["master_enabled"]:
            notes.append("A chave geral esta DESLIGADA: nenhuma rotina dispara.")
        notes += [f"Rotina {r['name']} MORTA (kill switch)." for r in agg["routines"] if r["killed"]]
        notes += [f"Rotina {r['name']}: {r['errors']} execucao(oes) com erro." for r in agg["routines"] if r["errors"]]
        return " ".join([head, *notes])

    def _render_bodies(self, agg: Mapping[str, Any], narrative: str) -> tuple[str, str]:
        lines = [narrative, ""]
        for r in agg["routines"]:
            state = "morta" if r["killed"] else ("ativa" if r["ativo"] else "desativada")
            lines.append(
                f"- {r['name']} [{r['mode']}, {state}]: {r['runs']} exec, {r['errors']} erro, "
                f"{r['drafts']} rascunhos, {r['published']} auto, {r['approved']} aprov., {r['rejected']} rej."
            )
            lines += [f"    motivo: {m}" for m in r["rejections"]]
        text = "\n".join(lines)
        body = "".join(f"<li>{html.escape(x.strip('- ').strip())}</li>" for x in lines[2:] if x.strip())
        return f"<p>{html.escape(narrative)}</p><ul>{body}</ul>", text

    def _build_subject(self, agg: Mapping[str, Any], window: DigestWindow) -> str:
        t = agg["totals"]
        flag = " (com erros)" if t["errors"] else ""
        return f"Relatorio diario das rotinas: {t['runs']} execucoes{flag}"

    def _build_summary(self, agg: Mapping[str, Any], narrative: str, window: DigestWindow) -> dict[str, Any]:
        return {"narrative": narrative, "totals": agg["totals"], "routines": agg["routines"],
                "master_enabled": agg["master_enabled"]}


__all__ = ["RoutinesDailyReport", "aggregate_events"]
