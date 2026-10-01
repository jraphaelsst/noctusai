"""`chat_completion_stream`'s end-of-stream report — whether it was cut off.

A stream yields bare text deltas, so a caller cannot tell "the model finished"
from "the model hit `max_tokens`" — both just end the iterator. Measured live
2026-10-01: the IgIg help chat answered a long how-to at `max_tokens=1200`,
stopped mid-section, and the router still emitted `done` — the user got half
an answer presented as a whole one.

A caller that wants to know passes a `StreamOutcome` to
`chat_completion_stream(..., outcome=...)`; the provider fills it once the
stream is fully drained. Same normalization as `vision_types.VisionResult`:
`truncated` is the ONE field to branch on, computed from the vendor's own stop
signal (Anthropic `stop_reason == "max_tokens"`, OpenAI
`finish_reason == "length"`, Gemini `FinishReason.MAX_TOKENS`); `stop_reason`
is the raw vendor value, for logs only.

`truncated is None` means the provider did not report (stream not drained, or
no stop signal arrived) — "unknown", never silently "complete".

Stdlib-only on purpose, for the same import-cycle reason as `vision_types`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class StreamOutcome:
    """Filled by the provider when its stream ends. See module docstring."""

    truncated: Optional[bool] = None
    #: Raw vendor value (e.g. `"max_tokens"`, `"length"`, `"MAX_TOKENS"`) —
    #: for logs only. Compare `truncated`, never this, across providers.
    stop_reason: Optional[str] = None


__all__ = ["StreamOutcome"]
