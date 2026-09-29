"""noctus.dev.notify — one call to email / WhatsApp the owner.

WRITE tool: ``confirm=False`` (default) returns the PLAN (resolved recipients
per channel, subject, transport) with status ``planned`` and sends NOTHING;
``confirm=True`` sends.

Recipients. ``to_email`` / ``to_phone`` override; otherwise the single active
row of ``social_wiring.notification_recipients`` is read through the toolkit's
existing ``migrate_product.make_sql_executor`` seam (Supabase Management API,
PAT resolved DB-first). No active row / more than one / no executor => a typed
error, never a silent skip.

Email transport order (no vendor HTTP API): Gmail (seed ``GmailClient`` via
the ``GOOGLE_OAUTH_CLIENT_ID`` / ``GOOGLE_OAUTH_CLIENT_SECRET`` /
``GOOGLE_OAUTH_REFRESH_TOKEN`` trio -- same credential source as
``mcp/google_workspace``; needs the gmail.send scope) -> SMTP (seed
``SmtpEmailSender`` via ``SMTP_HOST`` / ``SMTP_PORT`` / ``SMTP_USER`` /
``SMTP_PASSWORD``, optional ``SMTP_SECURITY`` / ``SMTP_FROM`` /
``SMTP_FROM_NAME``) -> channel ``unavailable`` naming the missing credentials.

WhatsApp transport: seed ``WahaClient`` (``WAHA_BASE_URL`` / ``WAHA_API_KEY`` /
``WAHA_SESSION``, default session ``default``). The session status is checked
first; anything but WORKING => channel ``unavailable`` carrying the status.
Phone -> chatId: digits only + ``@c.us``.

Result: ``{ok, status, channels: {name: {status, detail, id}}}`` with per-channel
status sent | failed | unavailable | planned; ``ok`` only if every requested
channel is sent. A failing channel never blocks the others.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import os
import re
from pathlib import Path
from typing import Any, Mapping

from . import migrate_product as _mp

_ALL_CHANNELS = ("email", "whatsapp")
_RECIPIENTS_SQL = (
    "SELECT name, email, whatsapp_number FROM social_wiring.notification_recipients "
    "WHERE is_active = true ORDER BY created_at;"
)
_GMAIL_KEYS = ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REFRESH_TOKEN")
_SMTP_KEYS = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD")
_REPO_ROOT = Path(__file__).resolve().parents[5]
_ENV_FILES = (
    _REPO_ROOT / ".env",
    _REPO_ROOT / "mcp" / "google_workspace" / ".env",
    _REPO_ROOT / "mcp" / "waha" / ".env",
)


def _err(kind: str, msg: str) -> dict[str, Any]:
    return {"ok": False, "status": "error", "error": {"type": kind, "message": msg}, "channels": {}}


def _run(coro: Any) -> Any:
    """Run a coroutine from sync code, even when a loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _resolve_env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    """Explicit mapping wins (tests); else os.environ, backfilled from the
    connector .env files (repo root, google_workspace, waha)."""
    if env is not None:
        return env
    merged: dict[str, str] = {}
    from dotenv import dotenv_values

    for f in reversed(_ENV_FILES):
        if f.is_file():
            merged.update({k: v for k, v in dotenv_values(f).items() if v})
    merged.update({k: v for k, v in os.environ.items() if v})
    return merged


def _first_line(text: str) -> str:
    return (text.strip().splitlines() or [""])[0][:200]


def _resolve_recipients(executor: Any) -> tuple[dict[str, str | None], dict[str, Any] | None]:
    if executor is None:
        executor = _mp.make_sql_executor()
    if executor is None:
        return {}, _err(
            "recipient_resolution_failed",
            "no supabase_access_token resolved; pass to_email/to_phone or set SUPABASE_ACCESS_TOKEN.",
        )
    res = executor.execute(_RECIPIENTS_SQL)
    if not res.get("ok"):
        return {}, _err("recipient_resolution_failed", f"query failed: {res.get('error')}")
    rows = [r for r in (res.get("rows") or []) if isinstance(r, dict)]
    if len(rows) != 1:
        return {}, _err(
            "recipient_resolution_failed",
            f"expected exactly 1 active notification_recipients row, found {len(rows)}; pass to_email/to_phone.",
        )
    return {"email": rows[0].get("email"), "phone": rows[0].get("whatsapp_number")}, None


def _email_transport(env: Mapping[str, str]) -> tuple[str | None, str]:
    """(transport, why). transport is 'gmail' | 'smtp' | None."""
    if all(env.get(k) for k in _GMAIL_KEYS):
        return "gmail", "gmail"
    if all(env.get(k) for k in _SMTP_KEYS):
        return "smtp", "smtp"
    miss_g = [k for k in _GMAIL_KEYS if not env.get(k)]
    miss_s = [k for k in _SMTP_KEYS if not env.get(k)]
    return None, f"missing gmail credentials: {', '.join(miss_g)}; missing smtp credentials: {', '.join(miss_s)}"


def _send_gmail(env: Mapping[str, str], to: str, subject: str, body: str, gmail_client: Any) -> dict[str, Any]:
    if gmail_client is None:
        from noctusai_lib.integrations.gmail import OAuthGmailCredentials, make_gmail_client

        gmail_client = make_gmail_client(
            oauth_credentials=OAuthGmailCredentials(
                refresh_token=env["GOOGLE_OAUTH_REFRESH_TOKEN"],
                client_id=env["GOOGLE_OAUTH_CLIENT_ID"],
                client_secret=env["GOOGLE_OAUTH_CLIENT_SECRET"],
            )
        )
    r = _run(gmail_client.send_message(to=to, subject=subject, body_text=body))
    return {"status": "sent", "detail": "sent via gmail", "id": getattr(r, "message_id", None)}


def _send_smtp(env: Mapping[str, str], to: str, subject: str, body: str, smtp_sender: Any) -> dict[str, Any]:
    from noctusai_lib.integrations.email import OutgoingEmail

    if smtp_sender is None:
        from noctusai_lib.integrations.email import SmtpConfig
        from noctusai_lib.integrations.email.smtp_adapter import SmtpEmailSender

        cfg = SmtpConfig.from_credentials(
            {
                "smtp_host": env["SMTP_HOST"],
                "smtp_port": env["SMTP_PORT"],
                "smtp_username": env["SMTP_USER"],
                "smtp_password": env["SMTP_PASSWORD"],
                "smtp_security": env.get("SMTP_SECURITY"),
                "email_from": env.get("SMTP_FROM"),
                "email_from_name": env.get("SMTP_FROM_NAME"),
            }
        )
        smtp_sender = SmtpEmailSender(config=cfg)
    r = _run(smtp_sender.send(OutgoingEmail(to=[to], subject=subject, text=body)))
    return {"status": "sent", "detail": "sent via smtp", "id": getattr(r, "message_id", None)}


def _send_whatsapp(env: Mapping[str, str], phone: str, body: str, waha_client: Any) -> dict[str, Any]:
    if waha_client is None:
        if not env.get("WAHA_BASE_URL"):
            return {"status": "unavailable", "detail": "missing credential: WAHA_BASE_URL", "id": None}
        from noctusai_lib.integrations.whatsapp import get_whatsapp_client

        waha_client = get_whatsapp_client(
            base_url=env["WAHA_BASE_URL"],
            api_key=env.get("WAHA_API_KEY"),
            session=env.get("WAHA_SESSION") or "default",
        )
    session = _run(waha_client.get_session())
    status = str(session.get("status") or "UNKNOWN")
    if status != "WORKING":
        return {
            "status": "unavailable",
            "detail": f"WAHA session status={status} (needs WORKING; re-scan QR if FAILED)",
            "id": None,
        }
    digits = re.sub(r"\D", "", phone)
    r = _run(waha_client.send_text(f"{digits}@c.us", body))
    mid = r.get("id") if isinstance(r, dict) else None
    if isinstance(mid, dict):
        mid = mid.get("_serialized") or mid.get("id")
    return {"status": "sent", "detail": "sent via waha", "id": mid}


def notify(
    message: str,
    subject: str | None = None,
    channels: list[str] | None = None,
    to_email: str | None = None,
    to_phone: str | None = None,
    confirm: bool = False,
    *,
    executor: Any = None,
    env: Mapping[str, str] | None = None,
    gmail_client: Any = None,
    smtp_sender: Any = None,
    waha_client: Any = None,
) -> dict[str, Any]:
    """Notify the owner. See module docstring. Keyword-only args are DI seams."""
    if not message or not message.strip():
        return _err("invalid_input", "message is required")
    chans = list(channels) if channels else list(_ALL_CHANNELS)
    bad = [c for c in chans if c not in _ALL_CHANNELS]
    if bad:
        return _err("invalid_input", f"unknown channels {bad}; allowed {list(_ALL_CHANNELS)}")
    subj = subject or _first_line(message)
    cfg = _resolve_env(env)

    email_to, phone_to = to_email, to_phone
    if ("email" in chans and not email_to) or ("whatsapp" in chans and not phone_to):
        rec, error = _resolve_recipients(executor)
        if error:
            return error
        email_to = email_to or rec.get("email")
        phone_to = phone_to or rec.get("phone")

    out: dict[str, dict[str, Any]] = {}
    for ch in chans:
        target = email_to if ch == "email" else phone_to
        if not target:
            out[ch] = {"status": "failed", "detail": f"no {ch} recipient resolved", "id": None}
            continue
        transport: str | None
        if ch == "email":
            if gmail_client is not None:
                transport, why = "gmail", "gmail"
            elif smtp_sender is not None:
                transport, why = "smtp", "smtp"
            else:
                transport, why = _email_transport(cfg)
        else:
            transport, why = "waha", "waha"
        if not confirm:
            detail = f"to={target} transport={transport or 'NONE'}"
            if ch == "email":
                detail += f" subject={subj!r}"
            if transport is None:
                detail += f" ({why})"
            out[ch] = {"status": "planned", "detail": detail, "id": None}
            continue
        try:
            if ch == "email":
                if transport is None:
                    out[ch] = {"status": "unavailable", "detail": why, "id": None}
                elif transport == "gmail":
                    out[ch] = _send_gmail(cfg, target, subj, message, gmail_client)
                else:
                    out[ch] = _send_smtp(cfg, target, subj, message, smtp_sender)
            else:
                out[ch] = _send_whatsapp(cfg, target, message, waha_client)
        except Exception as e:  # noqa: BLE001 -- surfaced verbatim per channel
            out[ch] = {"status": "failed", "detail": f"{type(e).__name__}: {e}", "id": None}

    if not confirm:
        return {"ok": False, "status": "planned", "subject": subj, "channels": out}
    ok = all(v["status"] == "sent" for v in out.values())
    return {"ok": ok, "status": "sent" if ok else "partial", "subject": subj, "channels": out}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.notify",
        description=(
            "Email and/or WhatsApp the owner in one call. WRITE: confirm=False returns the plan "
            "(recipients, subject, transport; status 'planned') and sends nothing; confirm=True sends. "
            "Recipients default to the single active social_wiring.notification_recipients row. "
            "Email: Gmail (GOOGLE_OAUTH_CLIENT_ID/SECRET/REFRESH_TOKEN) else SMTP (SMTP_HOST/PORT/USER/PASSWORD) "
            "else 'unavailable' naming missing creds. WhatsApp: WAHA (WAHA_BASE_URL/API_KEY/SESSION), "
            "'unavailable' unless session WORKING. Returns per-channel {status, detail, id}."
        ),
    )
    def _notify(
        message: str,
        subject: str | None = None,
        channels: list[str] | None = None,
        to_email: str | None = None,
        to_phone: str | None = None,
        confirm: bool = False,
    ) -> dict:
        return notify(message, subject, channels, to_email, to_phone, confirm)


__all__ = ["notify", "register"]
