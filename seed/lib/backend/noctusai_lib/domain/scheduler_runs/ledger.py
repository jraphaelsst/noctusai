"""Scheduler run ledger — core's `public.scheduler_runs` + `public.scheduler_jobs`.

The seed scheduler (`noctusai_lib.api.scheduler`) wraps every registered job
and hands each finished run to a `RunObserver`. This module is the observer
the seed framework installs in every product (`create_product_app`): one row
per run in core's `public.scheduler_runs`, and the product's schedules in
`public.scheduler_jobs` (published when the scheduler starts). Core's
Operação page and the owner daily brief read both.

On an `error` run it also writes ONE in-app notification to the platform
admins (`noctus_users.role = 'admin'`) — at most one per (product, job) per
`ALERT_WINDOW`, deduped on the ledger itself (`alerted = true` rows), so a
job failing every 5 minutes does not bury the bell.

Code only, zero LLM/API spend: two PostgREST writes per run, one read + one
notification insert on a (deduped) failure.

Layering: this is `domain/`; the run/spec objects come from `api/` and are
read by attribute (duck-typed) so nothing here imports `api/`.

Shipped Fake + Real + factory (`KB § PATTERNS/backend/seed-fake-real-adapter.md`).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

from noctusai_lib.domain.notifications import write_in_app

logger = logging.getLogger(__name__)

RUNS_TABLE = "scheduler_runs"
JOBS_TABLE = "scheduler_jobs"
STATUSES = ("ok", "error", "skipped")
ALERT_KIND = "scheduler_job_failed"
ALERT_WINDOW = timedelta(hours=6)
ERROR_MAX_CHARS = 1000
OPERATIONS_LINK = "/admin/operacao/rotinas"

_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    # JWTs / Supabase keys (three base64url segments).
    (re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "[jwt]"),
    # Authorization headers.
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 [redacted]"),
    # key=value / key: value for secret-ish keys.
    (re.compile(r"(?i)\b(api[_-]?key|apikey|token|secret|password|passwd|senha|authorization)"
                r"(\"?\s*[:=]\s*\"?)[^\s\"',;&]+"), r"\1\2[redacted]"),
    # Vendor-shaped secrets (sk-..., pk_..., re_..., whsec_...).
    (re.compile(r"\b(sk|pk|rk|re|whsec)[-_][A-Za-z0-9_-]{12,}"), "[secret]"),
    # Credentials in URLs.
    (re.compile(r"(://[^/\s:@]+):[^@\s/]+@"), r"\1:[redacted]@"),
    # E-mail addresses (LGPD: an error text is operator-visible, not data).
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[email]"),
)


def sanitize_error(text: Optional[str], *, max_chars: int = ERROR_MAX_CHARS) -> Optional[str]:
    """Redact secrets / e-mails and cap the length of a run's error text."""
    if not text:
        return None
    out = str(text)
    for pattern, repl in _REDACTIONS:
        out = pattern.sub(repl, out)
    out = " ".join(out.split())
    if len(out) > max_chars:
        out = out[: max_chars - 1] + "…"
    return out


def run_row(product: str, run: Any, *, alerted: bool = False) -> dict:
    """The `public.scheduler_runs` row for a finished run."""
    status = run.status if run.status in STATUSES else "error"
    return {
        "product": product,
        "job": run.job,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat(),
        "status": status,
        "error": sanitize_error(run.error),
        "duration_ms": max(0, int(run.duration_ms)),
        "alerted": bool(alerted),
    }


def job_row(product: str, spec: Any, *, seen_at: datetime) -> dict:
    """The `public.scheduler_jobs` row for a registered schedule."""
    return {
        "product": product,
        "job": spec.job,
        "cron": spec.cron,
        "interval_seconds": spec.interval_seconds,
        "timezone": spec.timezone or None,
        "misfire_grace_time": spec.misfire_grace_time,
        "last_seen_at": seen_at.isoformat(),
    }


def platform_admin_ids(core: Any) -> list[str]:
    """User ids of every platform admin (`public.noctus_users.role = 'admin'`,
    the same trusted column `resolve_platform_admin_role` reads)."""
    rows = core.table("noctus_users").select("id").eq("role", "admin").execute().data or []
    return sorted({str(r["id"]) for r in rows if r.get("id")})


def notify_platform_admins(
    core: Any, *, kind: str, title: str, message: str, metadata: Optional[dict] = None,
) -> int:
    """One in-app (bell) notification per platform admin; returns how many."""
    return write_in_app(
        core,
        user_ids=platform_admin_ids(core),
        kind=kind,
        title=title,
        message=message,
        metadata=metadata,
    )


class SupabaseRunLedger:
    """Real `RunObserver`: writes to core's tables through a `public`-schema
    service-role client (resolved per call — late binding)."""

    def __init__(
        self,
        product: str,
        core_client_factory: Callable[[], Any],
        *,
        alert_window: timedelta = ALERT_WINDOW,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if not product:
            raise ValueError("a run ledger needs the product slug")
        self.product = product
        self._core = core_client_factory
        self._alert_window = alert_window
        self._clock = clock

    def _recently_alerted(self, core: Any, job: str) -> bool:
        since = (self._clock() - self._alert_window).isoformat()
        rows = (
            core.table(RUNS_TABLE)
            .select("id")
            .eq("product", self.product)
            .eq("job", job)
            .eq("alerted", True)
            .gte("started_at", since)
            .limit(1)
            .execute()
            .data
            or []
        )
        return bool(rows)

    def _alert(self, core: Any, run: Any) -> bool:
        try:
            if self._recently_alerted(core, run.job):
                return False
            sent = notify_platform_admins(
                core,
                kind=ALERT_KIND,
                title=f"Rotina falhou: {self.product} · {run.job}",
                message=sanitize_error(run.error, max_chars=280) or "A rotina terminou com erro.",
                metadata={"product": self.product, "job": run.job, "link": OPERATIONS_LINK},
            )
        except Exception:  # noqa: BLE001 — the row must still be written; loud, not silent
            logger.error(
                "scheduler failure alert FAILED for %s/%s — the run is recorded, the admins were not notified",
                self.product, run.job, exc_info=True,
            )
            return False
        if sent == 0:
            logger.warning(
                "scheduler failure alert for %s/%s reached nobody: no platform admin exists",
                self.product, run.job,
            )
        return sent > 0

    def record(self, run: Any) -> None:
        core = self._core()
        alerted = self._alert(core, run) if run.status == "error" else False
        core.table(RUNS_TABLE).insert(run_row(self.product, run, alerted=alerted)).execute()

    def register_jobs(self, specs: Iterable[Any]) -> None:
        seen = self._clock()
        rows = [job_row(self.product, s, seen_at=seen) for s in specs]
        if rows:
            self._core().table(JOBS_TABLE).upsert(rows, on_conflict="product,job").execute()


class FakeRunLedger:
    """In-memory `RunObserver` for tests: keeps what it was handed."""

    def __init__(self, product: str = "test-product") -> None:
        self.product = product
        self.runs: list[Any] = []
        self.rows: list[dict] = []
        self.registered: list[Any] = []

    def record(self, run: Any) -> None:
        self.runs.append(run)
        self.rows.append(run_row(self.product, run))

    def register_jobs(self, specs: Iterable[Any]) -> None:
        self.registered.extend(specs)


def make_run_ledger(product: str, core_client_factory: Optional[Callable[[], Any]]) -> Any:
    """The ledger for a product: Real when a core client factory is supplied,
    else the Fake (a product with no core client cannot write the ledger)."""
    if core_client_factory is None:
        logger.warning("scheduler run ledger for %s: no core client — runs are kept in memory only", product)
        return FakeRunLedger(product)
    return SupabaseRunLedger(product, core_client_factory)


__all__ = [
    "ALERT_KIND",
    "ALERT_WINDOW",
    "ERROR_MAX_CHARS",
    "FakeRunLedger",
    "JOBS_TABLE",
    "OPERATIONS_LINK",
    "RUNS_TABLE",
    "STATUSES",
    "SupabaseRunLedger",
    "job_row",
    "make_run_ledger",
    "notify_platform_admins",
    "platform_admin_ids",
    "run_row",
    "sanitize_error",
]
