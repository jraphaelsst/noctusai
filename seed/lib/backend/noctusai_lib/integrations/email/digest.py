"""
Generic scheduled-digest helper — P3 pattern from ai-expansion §5a.

Products bring their own `(html, text)` rendering for their domain (ERP
biweekly metas digest, Core weekly audit-log narrative, PF monthly
financial summary, Daily Life Friday review, Mailing campaign debrief).
This module handles the cross-cutting concerns:

  - 3-tier credential chain via `noctusai_lib.credentials.resolve_credential`
    (org → platform → env) for the chosen backend's identity.
  - Two send backends, picked per-org by which credentials resolve:
      Resend (HTTP API) — default when `resend_api_key` is set.
      SMTP   (stdlib `smtplib`) — engages when SMTP host/port/username/
             password resolve. Useful for self-hosted or vendor-flexible
             deploys where Resend isn't acceptable.
    Explicit override via the `email_backend` credential ("resend" | "smtp")
    when both backends are configured at once.
  - Structured `DigestSendResult` for callers (sent / dry-run / error +
    optional external_id — Resend only; SMTP returns no message id).
  - Dry-run path when neither backend resolves — logs the rendered text +
    subject so integration tests + dev environments don't need real keys.
  - All send failures swallowed + returned as `DigestSendResult(error=...)`
    so a backend outage never crashes the calling endpoint.

Shipped 2026-04-25 by ai-expansion Tier 2 Phase 4 (P3 pattern). The metas
digest service (`products/erp-imobiliario/backend/app/services/metas_digest_service.py`)
is the reference adopter — it brings the metas-specific render functions
and delegates the send through `send_digest()`.

SMTP backend added 2026-05-04 (alongside Resend) — youtube-crawler
seed-hardening Batch A. Module remains a flat-function shape; the
canonical Protocol+Fake+Real+factory absorption is a planned follow-up
under the seed-hardening umbrella.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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


# SMTP security modes. `starttls` is the modern default (port 587 typical);
# `ssl` is implicit-TLS / SMTPS (port 465); `none` is plain — only useful
# for local test servers like aiosmtpd.
_SMTP_SECURITY_MODES = ("starttls", "ssl", "none")
_DEFAULT_SMTP_SECURITY = "starttls"
_DEFAULT_SMTP_TIMEOUT = 15


def _resolve_smtp_config(org_id: Optional[str]) -> Optional[dict[str, Any]]:
    """Look up SMTP identity using the 3-tier credential chain.

    Returns None if any of host / port / username / password is missing
    (caller falls through to the next backend or dry-run). Security mode
    defaults to ``starttls``; override with credential ``smtp_security``
    set to one of: ``"starttls"``, ``"ssl"``, ``"none"``.
    """
    host = resolve_credential("smtp_host", org_id)
    port = resolve_credential("smtp_port", org_id)
    username = resolve_credential("smtp_username", org_id)
    password = resolve_credential("smtp_password", org_id)
    if not (host and port and username and password):
        return None

    try:
        port_int = int(port)
    except (TypeError, ValueError):
        logger.warning("[EMAIL SMTP] non-integer smtp_port %r — ignoring SMTP backend", port)
        return None

    security = (resolve_credential("smtp_security", org_id) or _DEFAULT_SMTP_SECURITY).lower()
    if security not in _SMTP_SECURITY_MODES:
        logger.warning(
            "[EMAIL SMTP] invalid smtp_security %r (allowed: %s) — defaulting to starttls",
            security, _SMTP_SECURITY_MODES,
        )
        security = _DEFAULT_SMTP_SECURITY

    return {
        "host": host,
        "port": port_int,
        "username": username,
        "password": password,
        "security": security,
        "from_email": resolve_credential("email_from", org_id) or _DEFAULT_FROM_EMAIL,
        "from_name": resolve_credential("email_from_name", org_id) or _DEFAULT_FROM_NAME,
    }


def _resolve_email_backend(
    org_id: Optional[str],
) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    """Pick the email backend for this org.

    Selection rules (first match wins):
      1. Explicit override via ``email_backend`` credential — when set to
         ``"resend"`` or ``"smtp"`` AND that backend's config resolves.
      2. Resend config resolves → Resend (back-compat default).
      3. SMTP config resolves → SMTP.
      4. Otherwise → ``(None, None)``; caller treats as dry-run.

    Returns ``(backend_name, config)``. Backend name is one of
    ``"resend"``, ``"smtp"``, or ``None``.
    """
    explicit = (resolve_credential("email_backend", org_id) or "").lower() or None

    resend_cfg = _resolve_resend_config(org_id)
    smtp_cfg = _resolve_smtp_config(org_id)

    if explicit == "smtp" and smtp_cfg:
        return ("smtp", smtp_cfg)
    if explicit == "resend" and resend_cfg:
        return ("resend", resend_cfg)

    if resend_cfg:
        return ("resend", resend_cfg)
    if smtp_cfg:
        return ("smtp", smtp_cfg)
    return (None, None)


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


def _build_mime_message(config: dict[str, Any], to: str, digest: Digest):
    """Construct the MIME message that SMTP sends. Multipart when html
    is present; plain text otherwise. From/To/Subject set on the envelope.
    """
    if digest.html:
        msg: Any = MIMEMultipart("alternative")
        msg.attach(MIMEText(digest.text, "plain", "utf-8"))
        msg.attach(MIMEText(digest.html, "html", "utf-8"))
    else:
        msg = MIMEText(digest.text, "plain", "utf-8")
    msg["From"] = f"{config['from_name']} <{config['from_email']}>"
    msg["To"] = to
    msg["Subject"] = digest.subject
    return msg


def _send_via_smtp_sync(config: dict[str, Any], to: str, digest: Digest) -> None:
    """Sync SMTP send via stdlib smtplib. Called from a thread by the async
    wrapper so the event loop doesn't block on network I/O. Raises on any
    smtplib error; caller wraps.
    """
    msg = _build_mime_message(config, to, digest)
    if config["security"] == "ssl":
        smtp_cls: Any = smtplib.SMTP_SSL
    else:
        smtp_cls = smtplib.SMTP

    with smtp_cls(config["host"], config["port"], timeout=_DEFAULT_SMTP_TIMEOUT) as smtp:
        if config["security"] == "starttls":
            smtp.starttls()
        smtp.login(config["username"], config["password"])
        smtp.send_message(msg)


async def _send_via_smtp(config: dict[str, Any], to: str, digest: Digest) -> None:
    """Async wrapper for stdlib smtplib (which is sync). Returns None — SMTP
    has no message-id to surface back to the caller (unlike Resend's `id`).
    """
    await asyncio.to_thread(_send_via_smtp_sync, config, to, digest)


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
    """Send a pre-rendered digest via the org's configured backend, with
    built-in dry-run fallback.

    Backend selection:
      - Resend if `resend_api_key` resolves (default).
      - SMTP if `smtp_host` + `smtp_port` + `smtp_username` + `smtp_password`
        all resolve and Resend doesn't.
      - Either can be forced via the `email_backend` credential
        (``"resend"`` | ``"smtp"``) when both are configured at once.
      - Neither configured → dry-run (log only).

    Args:
        digest: the rendered subject + text + (optional) html.
        recipient: target email address.
        org_id: passed to `resolve_credential` for per-org keys.
            None resolves through the platform → env tiers only.
        log_prefix: tag for log lines (e.g. "METAS DIGEST", "AUDIT DIGEST").

    Returns:
        `DigestSendResult` — never raises. SMTP path leaves
        ``external_id`` as None since SMTP returns no message id.
    """
    if not recipient or "@" not in recipient:
        return DigestSendResult(
            sent=False, error=f"invalid recipient: {recipient!r}", subject=digest.subject,
        )

    backend, config = _resolve_email_backend(org_id)
    if not backend or not config:
        # Dry-run: log + return. Useful for dev + for products whose orgs
        # haven't configured any backend yet.
        logger.info(
            "[%s DRY-RUN] To=%s subject=%s",
            log_prefix, recipient, digest.subject,
        )
        logger.debug("[%s DRY-RUN] body:\n%s", log_prefix, digest.text)
        return DigestSendResult(
            sent=False, dry_run=True, subject=digest.subject,
        )

    try:
        if backend == "resend":
            result = await _post_to_resend(config, recipient, digest)
            external_id = result.get("id")
        elif backend == "smtp":
            await _send_via_smtp(config, recipient, digest)
            external_id = None
        else:
            return DigestSendResult(
                sent=False,
                error=f"unknown email backend: {backend!r}",
                subject=digest.subject,
            )

        logger.info(
            "[%s] sent via %s id=%s to=%s",
            log_prefix, backend, external_id, recipient,
        )
        return DigestSendResult(
            sent=True, external_id=external_id, subject=digest.subject,
        )
    except Exception as exc:
        logger.error("[%s] %s send failed: %s", log_prefix, backend, exc)
        return DigestSendResult(
            sent=False, error=str(exc), subject=digest.subject,
        )
