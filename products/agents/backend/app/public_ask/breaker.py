"""Global daily cost circuit breaker for the anonymous public-ask route.

Counts model-spending requests per UTC day, in process. When the cap is hit the
service answers with the editorial fallback (never an error page) until the
day rolls over. Holds a counter only — never text.

NOC-REMEDIATE[public-ask-breaker-shared]: in-process ⇒ the cap is per worker;
move the counter to Redis (INCR + EXPIREAT) when the prod deploy runs >1 worker
or the cap must survive restarts — 2026-10-04
"""
from __future__ import annotations

import threading
from datetime import date, datetime, timezone
from typing import Callable


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


class DailyCostBreaker:
    def __init__(self, max_per_day: int, *, today: Callable[[], date] = _utc_today) -> None:
        self._max = max_per_day
        self._today = today
        self._lock = threading.Lock()
        self._day: date | None = None
        self._count = 0

    def try_acquire(self) -> bool:
        """Reserve one unit; False when today's cap is spent."""
        with self._lock:
            day = self._today()
            if day != self._day:
                self._day, self._count = day, 0
            if self._count >= self._max:
                return False
            self._count += 1
            return True


__all__ = ["DailyCostBreaker"]
