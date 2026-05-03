"""Digest pipeline — shared upstream of `integrations/email/digest.py`.

The `integrations/email/digest.py` module owns the Resend transport
(send_digest, render_digest, Digest dataclass). This module owns the
*upstream* narrative pipeline shared by N=5 product digest services
(audit, metas, monthly-narrative, weekly-review, campaign-debrief):

- `narrative(...)` — wraps `chat_completion(...)` with the standard
  digest posture (temperature=0, max_tokens=600, configurable cache,
  org_id threaded) and returns a fallback string when the LLM is
  unavailable. The 4 narrative-using services (all but ERP metas) used
  to hand-roll this try/except + warn + fallback dance.
- `render_with_narrative(...)` — wraps `render_digest(...)` and
  auto-derives `narrative_paragraphs` (the `\\n\\n` split) +
  `prompt_version` threading. Every narrative-using service merged
  these into its template context the same way.
- `build_and_send(...)` — wraps `send_digest(...)` and normalizes the
  per-recipient return shape. Every service translated the
  `DigestSendResult` into a 5-key `{"sent", "dry_run", "external_id",
  "error", "subject"}` dict at the end of `send_X(...)`.

Adopted by Wave C of `execution-workflow-codequality-rollout`
(2026-04-30) — see `projects/digest-pipeline-absorption/PROJECT.md`.
"""
from __future__ import annotations

from .narrative import narrative
from .orchestrate import build_and_send
from .render import email_template_dir, render_digest_pair, render_with_narrative

__all__ = [
    "narrative",
    "render_with_narrative",
    "render_digest_pair",
    "email_template_dir",
    "build_and_send",
]
