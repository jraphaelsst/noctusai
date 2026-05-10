"""Digest pipeline — shared upstream of `integrations/email/digest.py`.

The `integrations/email/digest.py` module owns the Resend transport
(send_digest, render_digest, Digest dataclass). This module owns the
*upstream* narrative pipeline shared by the four narrative-using
product digest services (core/audit_digest, daily-life/weekly_review,
mailing/campaign_debrief, personal-finance/monthly_narrative):

Helpers (Wave C 2026-04-30, `digest-helpers-absorption` 2026-05-03)
------------------------------------------------------------------
- `narrative(...)` — wraps `chat_completion(...)` with the standard
  digest posture (temperature=0, max_tokens=600, configurable cache,
  org_id threaded) and returns a fallback string when the LLM is
  unavailable.
- `render_with_narrative(...)` — wraps `render_digest(...)` and
  auto-derives `narrative_paragraphs` (the `\\n\\n` split) +
  `prompt_version` threading.
- `render_digest_pair(...)` — convenience for the
  `<basename>.html.j2` + `<basename>.txt.j2` convention.
- `build_and_send(...)` — wraps `send_digest(...)` and normalizes the
  per-recipient return shape.

Base class (this project — 2026-05-10, `seed-digest-base-class`)
----------------------------------------------------------------
- `BaseDigestService` — template-method orchestrator. Subclasses
  implement `_fetch_window`, `_aggregate`, `_generate_narrative`,
  `_render_bodies`, `_build_subject`; the base's `run(window)` threads
  them in order and returns a `DigestResult` envelope.
- `DigestWindow` / `DigestResult` — input + output envelopes for
  `BaseDigestService.run(...)`.

ERP/`metas_digest` and Daily-Life/`daily_brief` are excluded —
see `KB § PATTERNS/accept-with-rationale.md` and `base.py` docstring.
"""
from __future__ import annotations

from .base import BaseDigestService
from .narrative import narrative
from .orchestrate import build_and_send
from .render import email_template_dir, render_digest_pair, render_with_narrative
from .types import DigestResult, DigestWindow

__all__ = [
    "BaseDigestService",
    "DigestResult",
    "DigestWindow",
    "narrative",
    "render_with_narrative",
    "render_digest_pair",
    "email_template_dir",
    "build_and_send",
]
