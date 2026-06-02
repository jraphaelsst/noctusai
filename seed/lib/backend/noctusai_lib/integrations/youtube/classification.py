"""Shorts-vs-regular-video classification for the YouTube adapter.

The YouTube Data API v3 has **no `is_short` field** — Shorts are
ordinary `videos.list` resources, indistinguishable at the schema
level from long-form uploads. We infer the classification from
observable signals, in three tiers of decreasing certainty:

1. **`#Shorts` hashtag** (title/description) → high confidence. Authors
   tag Shorts to opt into the Shorts shelf; a present tag is a strong
   author-declared signal.
2. **Duration** (:data:`SHORTS_MAX_DURATION_SECONDS` = 180s since the
   Oct-2024 ceiling raise) → `≤ 60s` is a high-confidence Short;
   `61–180s` is the AMBIGUOUS band (a 90s upload may be a Short *or* a
   short long-form video — duration alone cannot decide), so we default
   to **not-short** and set ``needs_probe=True``; `> 180s` is a
   high-confidence not-Short.
3. **HTTP probe** (`GET youtube.com/shorts/{id}` → 200 = Short, a 30x
   redirect to `/watch` = not) — the ONLY authoritative signal, but it
   is an **un-quota'd public HTTP call** (no Data-API quota cost) with
   rate-limit + latency risk. The PURE classifier here never performs
   it: it sets ``needs_probe`` so the caller (a sync/snapshot service,
   server-side + cached + feature-flagged) can resolve the ambiguous
   band out-of-band.

`classify_short` is pure (no IO) so it is trivially testable and the
probe tier stays an explicit, opt-in adapter concern — never a hidden
network call on a hot path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from noctusai_lib.integrations.youtube.types import (
    SHORTS_MAX_DURATION_SECONDS,
    VideoFull,
)

DetectedVia = Literal["hashtag", "duration", "probe", "manual"]
"""How a Short classification was reached. ``"hashtag"`` / ``"duration"``
come from :func:`classify_short` (pure); ``"probe"`` is set by a caller
that resolved the ambiguous band with the HTTP probe; ``"manual"`` is an
operator override."""

Confidence = Literal["high", "medium", "low"]
"""Classification confidence. ``"medium"`` is the `61–180s` ambiguous
band (duration says maybe); ``"low"`` is unknown duration with no
hashtag. Both carry ``needs_probe=True``."""


@dataclass(frozen=True)
class ShortClassification:
    """Result of :func:`classify_short`.

    ``is_short`` is the best inference from the pure signals available.
    ``needs_probe`` flags that an authoritative HTTP probe would resolve
    a ``medium``/``low`` confidence verdict — the caller decides whether
    to spend that probe (it has no Data-API quota cost but is a network
    call). A ``high`` confidence result never needs a probe."""

    is_short: bool
    detected_via: DetectedVia
    confidence: Confidence
    needs_probe: bool


def _has_shorts_hashtag(video: VideoFull) -> bool:
    """Case-insensitive `#shorts` (or `#short`) tag in title/description
    or the structured `tags` tuple. `#short` is a prefix of `#shorts`,
    so the substring check covers both spellings."""
    haystack = f"{video.title}\n{video.description}".lower()
    if "#shorts" in haystack or "#short " in haystack or haystack.endswith("#short"):
        return True
    return any(tag.lower().lstrip("#") in ("short", "shorts") for tag in video.tags)


def classify_short(video: VideoFull) -> ShortClassification:
    """Classify a :class:`VideoFull` as a Short or a regular video.

    Pure (no IO). See the module docstring for the three-tier rationale.
    Returns a :class:`ShortClassification`; when ``needs_probe`` is True
    the caller may run an HTTP probe (`youtube.com/shorts/{id}`) to
    promote a ``medium``/``low`` verdict to ``high`` and override
    ``is_short``."""
    if _has_shorts_hashtag(video):
        return ShortClassification(
            is_short=True, detected_via="hashtag", confidence="high", needs_probe=False
        )

    duration = video.duration_seconds
    if duration <= 0:
        # Unknown duration + no hashtag — cannot infer; default not-short,
        # flag for probe (no silent guess).
        return ShortClassification(
            is_short=False, detected_via="duration", confidence="low", needs_probe=True
        )
    if duration <= 60:
        return ShortClassification(
            is_short=True, detected_via="duration", confidence="high", needs_probe=False
        )
    if duration <= SHORTS_MAX_DURATION_SECONDS:
        # 61–180s: genuinely ambiguous. Default not-short (safer — most
        # 1–3min uploads are short long-form, not Shorts), flag for probe.
        return ShortClassification(
            is_short=False,
            detected_via="duration",
            confidence="medium",
            needs_probe=True,
        )
    return ShortClassification(
        is_short=False, detected_via="duration", confidence="high", needs_probe=False
    )


__all__ = [
    "Confidence",
    "DetectedVia",
    "ShortClassification",
    "classify_short",
]
