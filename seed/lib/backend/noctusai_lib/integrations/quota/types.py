"""Quota tracker value objects + Protocol contract.

Frozen dataclasses (`QuotaConfig`, `QuotaCheck`) define the public
shape every backend produces. The `QuotaTracker` Protocol lives in
`protocol.py` so the type module stays purely declarative.

**Sliding-window choice.** The seed default is a *sliding* window
(deque-of-timestamps for InMemory; ZSET-of-timestamps for Redis),
because the YouTube / WhatsApp / LLM-RPM / Google-Maps consumers
universally enforce "≤ N units in the last X seconds" (NOT "≤ N units
since the top of the hour"). Fixed-window allows a 2x burst at window
boundaries (cap-1 at 23:59:59 + cap at 00:00:00) which matches none of
the real vendor contracts. The implementation cost (one extra
ZREMRANGEBYSCORE per consume on the Redis side) is paid for by the
correctness gain.

Optional `burst` field on `QuotaConfig` reserves capacity for short
spikes above the steady-state cap; today every consumer leaves
`burst=0` and gets pure sliding-window. Documented as a forward-compat
seam for token-bucket consumers without forcing a second Protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class QuotaConfig:
    """Quota declaration: how many units allowed within how big a window.

    - `cap` — maximum units permitted within `window_seconds`.
    - `window_seconds` — sliding-window length in seconds.
    - `burst` — additional units permitted in a brief spike. Defaults
      to 0 (pure sliding-window). Consumers that want a token-bucket
      shape (steady-state cap + transient burst) can set this; today
      no consumer uses it but it's forward-compat for the YouTube
      "search burst then resume" pattern.
    """

    cap: int
    window_seconds: int
    burst: int = 0

    def __post_init__(self) -> None:
        if self.cap < 0:
            raise ValueError(f"QuotaConfig.cap must be >= 0; got {self.cap}")
        if self.window_seconds <= 0:
            raise ValueError(
                f"QuotaConfig.window_seconds must be > 0; got {self.window_seconds}"
            )
        if self.burst < 0:
            raise ValueError(f"QuotaConfig.burst must be >= 0; got {self.burst}")

    @property
    def effective_cap(self) -> int:
        """Cap including burst allowance."""
        return self.cap + self.burst


@dataclass(frozen=True)
class QuotaCheck:
    """Result of `consume(...)` or `peek(...)`.

    - `allowed` — True if the consume was admitted (or, for peek, if a
      1-unit consume *would* be admitted right now).
    - `remaining` — units available within the current window AFTER
      this call (`max(0, cap - used)`). For a denied consume, equals 0
      iff the cap is exactly hit; can also report the slack the call
      *needed* but didn't have (still floored at 0 to keep the surface
      monotonic).
    - `used` — units consumed within the current sliding window
      *including* this call (for `consume`) or as-of-now (for `peek`).
      For a denied consume, reflects pre-call usage (the units were
      NOT recorded — atomic).
    - `reset_at` — earliest UTC datetime at which `remaining` will
      change (i.e., the oldest in-window record's expiry). Equals
      `now()` when `used == 0`.
    - `key` — echoed for caller convenience (loggers that want to see
      which key tripped without threading state through).
    """

    allowed: bool
    remaining: int
    used: int
    reset_at: datetime
    key: str
