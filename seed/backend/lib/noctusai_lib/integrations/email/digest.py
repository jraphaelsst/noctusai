"""
Generic scheduled-digest helper — P3 pattern from ai-expansion §5a.

Products bring their own `(html, text)` rendering for their domain (ERP
biweekly metas digest, Core weekly audit-log narrative, PF monthly
financial summary, Daily Life Friday review, Mailing campaign debrief).
This module handles the cross-cutting concerns:

  - 3-tier credential chain via `noctusai_lib.credentials.resolve_credential`
    (org → platform → env) for the Resend API key + `from` identity.
  - Structured `DigestSendResult` for callers (sent / dry-run / error +
    optional external_id).
  - Dry-run path when no key resolves — logs the rendered text + subject so
    integration tests + dev environments don't need a real key.
  - All send failures swallowed + returned as `DigestSendResult(error=...)`
    so a Resend outage never crashes the calling endpoint.

Shipped 2026-04-25 by ai-expansion Tier 2 Phase 4 (P3 pattern). The metas
digest service (`products/erp-imobiliario/backend/app/services/metas_digest_service.py`)
is the reference adopter — it brings the metas-specific render functions
and delegates the send through `send_digest()`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

import httpx
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

from noctusai_lib.config.credentials import resolve_credential

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Jinja rendering — shared digest layout (formalized 2026-04-25 after 5
# adopters surfaced; see KB § 04-SHARED-LIBRARY § email/).
# ---------------------------------------------------------------------------

_LIB_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _build_env(search_paths: Sequence[Path | str]) -> Environment:
    """Construct a Jinja env that searches product paths first, then the lib."""
    loaders = [FileSystemLoader(str(p)) for p in search_paths]
    loaders.append(FileSystemLoader(str(_LIB_TEMPLATE_DIR)))
    return Environment(
        loader=ChoiceLoader(loaders),
        autoescape=select_autoescape(["html", "j2", "html.j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def render(
    *,
    html_template: str,
    text_template: str,
    context: dict[str, Any],
    search_paths: Sequence[Path | str],
) -> tuple[str, str]:
    """Render `(html, text)` digest bodies from Jinja templates.

    Templates inherit from the lib-shipped `_digest_base.html.j2` and
    `_digest_base.txt.j2` (always discoverable). Product templates live
    in any of `search_paths` (typically `app/email_templates/`).

    Args:
        html_template: filename like ``"audit_digest.html.j2"``.
        text_template: filename like ``"audit_digest.txt.j2"``.
        context: variables passed to both renders.
        search_paths: where product templates live. Lib path is appended
            after these so product templates take precedence by name.

    Returns:
        ``(html, text)`` strings.

    Raises:
        jinja2.exceptions.TemplateNotFound: when the template can't be
            found in any of the search paths or the lib's defaults. This
            is a programming error — tests should catch it.
    """
    env = _build_env(search_paths)
    html = env.get_template(html_template).render(**context)
    text = env.get_template(text_template).render(**context)
    return html, text


# Default Resend identity — used when the org/platform doesn't override.
_DEFAULT_FROM_EMAIL = "noreply@noctus.app"
_DEFAULT_FROM_NAME = "NoctusAI"


@dataclass
class Digest:
    """The pre-rendered digest. Caller produces this from its domain data
    and hands it to `send_digest`."""

    subject: str
    text: str
    html: Optional[str] = None
    """If `html` is None, the message is sent text-only. Most product
    digests should render both — Resend and most clients prefer multipart."""


@dataclass
class DigestSendResult:
    """Outcome of `send_digest`. Always returned (never raises)."""

    sent: bool
    dry_run: bool = False
    """True when no Resend key resolved — message was logged, not sent."""

    external_id: Optional[str] = None
    """Resend's message ID on success."""

    error: Optional[str] = None
    """Stringified exception when the Resend POST failed."""

    subject: Optional[str] = None
    """Echoed for the caller's logging convenience."""


def _resolve_resend_config(org_id: Optional[str]) -> Optional[dict[str, str]]:
    """Look up Resend identity using the 3-tier credential chain.

    Returns None if no API key is configured (caller should treat as dry-run).
    """
    api_key = resolve_credential("resend_api_key", org_id)
    if not api_key:
        return None
    return {
        "api_key": api_key,
        "from_email": resolve_credential("email_from", org_id) or _DEFAULT_FROM_EMAIL,
        "from_name": resolve_credential("email_from_name", org_id) or _DEFAULT_FROM_NAME,
    }


async def _post_to_resend(
    config: dict[str, str], to: str, digest: Digest,
) -> dict[str, Any]:
    """Single-purpose HTTP POST to Resend. Raises on non-2xx; caller wraps."""
    payload: dict[str, Any] = {
        "from": f"{config['from_name']} <{config['from_email']}>",
        "to": [to],
        "subject": digest.subject,
        "text": digest.text,
    }
    if digest.html:
        payload["html"] = digest.html

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            json=payload,
            headers={
                "Authorization": f"Bearer {config['api_key']}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


def _result_to_dict(outcome: DigestSendResult, *, subject: str) -> dict[str, Any]:
    """Standard `DigestSendResult` → dict shape used by every product's
    `send_*` endpoint. Pulled out so the per-recipient and multi-recipient
    helpers below stay DRY.
    """
    return {
        "sent": outcome.sent,
        "dry_run": outcome.dry_run,
        "external_id": outcome.external_id,
        "error": outcome.error,
        "subject": subject,
    }


async def send_to_one(
    digest: Digest,
    *,
    recipient: str,
    org_id: Optional[str] = None,
    log_prefix: str = "DIGEST",
    summary: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Send a digest to one recipient and return the standard endpoint dict.

    Wraps `send_digest` + the `DigestSendResult` → dict conversion that
    every product's `send_*` endpoint repeats. The `summary` kwarg, when
    provided, is passed through unchanged so callers can attach
    domain-specific aggregate counts to the response.

    Returns:
        ``{"sent", "dry_run", "external_id", "error", "subject", "summary"}``
        — the shape API responses standardize on. Never raises.

    Trip history (recurrence rule N=5 → MUST formalize, 2026-04-30):
    Five `send_*` functions across products were doing the identical dict
    construction.
    """
    outcome = await send_digest(
        digest, recipient=recipient, org_id=org_id, log_prefix=log_prefix,
    )
    response = _result_to_dict(outcome, subject=digest.subject)
    if summary is not None:
        response["summary"] = summary
    return response


async def send_to_many(
    digest: Digest,
    *,
    recipients: Sequence[dict[str, Any]],
    org_id: Optional[str] = None,
    log_prefix: str = "DIGEST",
    summary: Optional[dict[str, Any]] = None,
    email_key: str = "email",
) -> dict[str, Any]:
    """Send a digest to multiple recipients and return an aggregated dict.

    Each recipient is a dict (typically a user record). The function reads
    ``recipient[email_key]`` to address the message; rows with a missing
    or empty email are skipped (NOT an error).

    Returns:
        ``{"sent": <count>, "results": [<per-recipient dict>, ...],
           "summary", "subject"}``. Each per-recipient dict is the same
        shape produced by `send_to_one`, plus a `recipient` field with
        the email used.

    Trip history: audit-digest sweeps across all admins, future digests
    that target multiple users follow the same shape. Single source.
    """
    results: list[dict[str, Any]] = []
    sent_count = 0
    for recipient_record in recipients:
        email = recipient_record.get(email_key)
        if not email:
            continue
        outcome = await send_digest(
            digest, recipient=email, org_id=org_id, log_prefix=log_prefix,
        )
        per_recipient = _result_to_dict(outcome, subject=digest.subject)
        per_recipient["recipient"] = email
        results.append(per_recipient)
        if outcome.sent:
            sent_count += 1
    response: dict[str, Any] = {
        "sent": sent_count,
        "results": results,
        "subject": digest.subject,
    }
    if summary is not None:
        response["summary"] = summary
    return response


async def send_digest(
    digest: Digest,
    *,
    recipient: str,
    org_id: Optional[str] = None,
    log_prefix: str = "DIGEST",
) -> DigestSendResult:
    """Send a pre-rendered digest via Resend, with built-in dry-run fallback.

    Args:
        digest: the rendered subject + text + (optional) html.
        recipient: target email address.
        org_id: passed to `resolve_credential` for per-org Resend keys.
            None resolves through the platform → env tiers only.
        log_prefix: tag for log lines (e.g. "METAS DIGEST", "AUDIT DIGEST").

    Returns:
        `DigestSendResult` — never raises.
    """
    if not recipient or "@" not in recipient:
        return DigestSendResult(
            sent=False, error=f"invalid recipient: {recipient!r}", subject=digest.subject,
        )

    config = _resolve_resend_config(org_id)
    if not config:
        # Dry-run: log + return. Useful for dev + for products whose orgs
        # haven't configured Resend yet.
        logger.info(
            "[%s DRY-RUN] To=%s subject=%s",
            log_prefix, recipient, digest.subject,
        )
        logger.debug("[%s DRY-RUN] body:\n%s", log_prefix, digest.text)
        return DigestSendResult(
            sent=False, dry_run=True, subject=digest.subject,
        )

    try:
        result = await _post_to_resend(config, recipient, digest)
        external_id = result.get("id")
        logger.info(
            "[%s] sent via Resend id=%s to=%s",
            log_prefix, external_id, recipient,
        )
        return DigestSendResult(
            sent=True, external_id=external_id, subject=digest.subject,
        )
    except Exception as exc:
        logger.error("[%s] send failed: %s", log_prefix, exc)
        return DigestSendResult(
            sent=False, error=str(exc), subject=digest.subject,
        )
