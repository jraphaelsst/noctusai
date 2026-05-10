"""Value objects for the digest base-class orchestration.

The four narrative-using digest services (core/audit_digest,
daily-life/weekly_review, mailing/campaign_debrief,
personal-finance/monthly_narrative) converged on the same template-method
shape:

    fetch a window of raw rows
      → aggregate into structured input for the LLM
      → generate a narrative via `noctusai_lib.domain.digest.narrative`
      → render html+text bodies
      → assemble Digest(subject, html, text)

The `BaseDigestService` template method (see `base.py`) orchestrates this
pipeline. `DigestWindow` is the input envelope; `DigestResult` is the
output envelope.

Design notes
------------
- `DigestWindow` is intentionally **loose**: each subclass takes what it
  needs. Some services drive off `period_days: int` (and compute
  start/end internally); some off `campaign_id: str` (a campaign IS the
  window). Forcing `(start_date, end_date)` here would break
  campaign_debrief. Pass the per-product knobs you need; the base just
  routes the envelope to `_fetch_window`.
- `DigestResult` carries the assembled `Digest` (subject + html + text),
  the LLM `narrative` string, and a `summary: dict` shaped per product.
  The per-product top-level wrapper (`build_review`, `build_debrief`, …)
  adapts this envelope to its legacy tuple shape so router callers and
  tests stay green.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from noctusai_lib.integrations.email.digest import Digest


@dataclass(frozen=True)
class DigestWindow:
    """Input envelope for `BaseDigestService.run(...)`.

    All fields optional — the per-subclass `_fetch_window` reads what it
    needs. Common fields are surfaced as named attributes; less common
    ones go through `extra` to keep the dataclass strict-kwargs-friendly
    without growing N positional fields.

    Attributes:
        org_id: Organization id for org-scoped fetches + LLM credential
            resolution. Optional because some products (daily-life
            weekly_review) operate on user-scoped data; org_id is purely
            an optional tag for credential resolution.
        period_days: Window length in days. Most services default to a
            product-appropriate value (7 for weekly digests, 30 for
            monthly narrative).
        start: Optional explicit start datetime (ISO string or datetime).
            When omitted, subclass derives from `period_days`.
        end: Optional explicit end datetime.
        extra: Free-form per-subclass kwargs. campaign_debrief uses
            `extra={"campaign_id": "..."}`; weekly_review uses
            `extra={"user_id": "...", "user_label": "..."}`.

    Subclasses are encouraged to provide a classmethod constructor
    (e.g. `WeeklyReviewService.window(user_id="u1")`) so callers don't
    touch `extra` directly.
    """
    org_id: Optional[str] = None
    period_days: Optional[int] = None
    start: Any = None
    end: Any = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class DigestResult:
    """Output envelope from `BaseDigestService.run(...)`.

    Attributes:
        digest: Assembled `Digest(subject, text, html)` ready for
            `send_digest(...)`.
        narrative: The LLM-generated narrative string (or the
            deterministic fallback when the LLM was unavailable).
        summary: Per-product summary dict. Shape varies by subclass —
            this is the "domain payload" surface that routers and
            dashboards inspect (e.g. PF surfaces savings rate; core
            surfaces high-priority count).
        recipients: Optional list of recipient dicts (e.g. core's
            audit-digest fans out to all admins of an org). Most
            subclasses leave this empty; the per-product wrapper
            handles fan-out.
    """
    digest: Digest
    narrative: str
    summary: dict[str, Any]
    recipients: list[dict[str, Any]] = field(default_factory=list)
