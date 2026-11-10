"""``noctus.dev.google_account_auth`` — mint ONE Google token for one account, scoped by a profile.

Generalises the server-less PKCE flow of ``drive_pull`` (same NoctusAI OAuth client,
``GOOGLE_OAUTH_CLIENT_ID`` / ``_SECRET``) to a named *profile* and a scope allowlist, storing under
``private_root()/google-accounts/<profile>/<email>.json`` (0600) so it never overwrites drive_pull's
token. Decision record: ``project-history/assistant-chatbot/browser-ops-decision.md`` (decisions 1-2).

1. ``auth_start`` → consent URL (offline access + forced consent ⇒ a refresh token) and a per-profile
   pending PKCE file (10 min TTL).
2. The owner consents; the browser lands on a page that fails to load; its full URL is the input of
3. ``auth_finish`` → exchanges the code, verifies the granted account IS ``account_email`` (a mismatch
   is discarded, never stored), records the scopes Google actually granted, and reports
   ``missing_scopes`` when Google granted fewer than requested (``ok`` is then False; the token is
   still stored so the granted subset is usable).
4. ``status`` → scopes + stored-at, never a secret.

Library use (the Assistant backend): :func:`load_credentials`.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import _google_oauth as _oauth
from ._google_oauth import DEFAULT_REDIRECT_URI, private_root, secure_dir, write_private_json

_PREFIX = "https://www.googleapis.com/auth/"
SCOPE_ALLOWLIST = frozenset(
    _PREFIX + s
    for s in ("calendar.events", "drive.readonly", "drive.file", "calendar.readonly", "gmail.readonly")
)
_PROFILE_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
_EMAIL_RE = re.compile(r"[^@\s/\\]+@[^@\s/\\]+\.[^@\s/\\]+")


def normalize_scopes(scopes: list[str]) -> list[str]:
    """Add the Google prefix when absent; refuse anything outside the allowlist (typed ValueError)."""
    if not scopes:
        raise ValueError("scopes must not be empty")
    out: list[str] = []
    for raw in scopes:
        full = raw if raw.startswith("https://") else _PREFIX + raw
        if full not in SCOPE_ALLOWLIST:
            raise ValueError(
                f"scope not allowed: {raw!r}; allowed: {sorted(s.removeprefix(_PREFIX) for s in SCOPE_ALLOWLIST)}"
            )
        if full not in out:
            out.append(full)
    return out


def _profile(profile: str) -> str:
    if not _PROFILE_RE.fullmatch(profile or ""):
        raise ValueError("profile must be a kebab slug (a-z, 0-9, '-', max 40 chars)")
    return profile


def _email(email: str) -> str:
    e = (email or "").strip().lower()
    if not _EMAIL_RE.fullmatch(e):
        raise ValueError("account_email is not a valid email address")
    return e


def _profile_dir(profile: str) -> Path:
    return secure_dir(secure_dir(private_root() / "google-accounts") / _profile(profile))


def token_path(profile: str, account_email: str) -> Path:
    return _profile_dir(profile) / f"{_email(account_email)}.json"


def probe_account_email(creds, granted: list[str]) -> str:
    """Email of the account behind ``creds``, through whichever granted scope can read it."""
    from googleapiclient.discovery import build

    if _PREFIX + "drive.readonly" in granted or _PREFIX + "drive.file" in granted:
        return _oauth.about_email(creds)
    if _PREFIX + "calendar.readonly" in granted or _PREFIX + "calendar.events" in granted:
        svc = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return str(svc.calendars().get(calendarId="primary").execute().get("id", "")).lower()
    svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
    return str(svc.users().getProfile(userId="me").execute().get("emailAddress", "")).lower()


def auth_start(
    profile: str,
    account_email: str,
    scopes: list[str],
    redirect_uri: str = DEFAULT_REDIRECT_URI,
    prov=None,
) -> dict[str, Any]:
    full = normalize_scopes(scopes)
    email = _email(account_email)
    state, url = _oauth.start_consent(
        _profile_dir(profile), email, full, redirect_uri, prov, extra={"profile": profile, "scopes": full}
    )
    return {
        "ok": True,
        "action": "auth_start",
        "profile": profile,
        "account_email": email,
        "scopes": full,
        "consent_url": url,
        "state": state,
        "next": (
            "Open consent_url, sign in as account_email and allow every scope. The browser then lands on "
            "a page that fails to load; pass that page's full URL as redirected_url to action='auth_finish'."
        ),
    }


def auth_finish(
    profile: str,
    redirected_url: str,
    prov=None,
    email_probe: _oauth.EmailProbe = probe_account_email,
) -> dict[str, Any]:
    consent = _oauth.consume_consent(_profile_dir(profile), redirected_url, prov)
    if consent.error:
        return {"ok": False, "action": "auth_finish", "profile": profile, "error": consent.error}
    tokens, pending = consent.tokens, consent.pending
    requested = list(pending.get("scopes", []))
    granted = [s for s in (tokens.scope or []) if s in SCOPE_ALLOWLIST]
    if not granted:
        return {"ok": False, "action": "auth_finish", "profile": profile,
                "error": f"none of the requested scopes were granted (got {list(tokens.scope or [])})"}
    expected = pending["account_email"]
    actual = email_probe(_oauth.credentials(tokens.refresh_token, granted), granted)
    if actual != expected:
        # Never revoke: it would revoke the whole (user, client) grant on the shared OAuth client.
        return {
            "ok": False,
            "action": "auth_finish",
            "profile": profile,
            "error": f"consent was granted by {actual!r}, expected {expected!r}; token discarded, not stored",
        }
    path = token_path(profile, expected)
    write_private_json(
        path,
        {
            "profile": profile,
            "account_email": expected,
            "refresh_token": tokens.refresh_token,
            "scopes": granted,
            "obtained_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    missing = [s for s in requested if s not in granted]
    out: dict[str, Any] = {
        "ok": not missing,
        "action": "auth_finish",
        "profile": profile,
        "account_email": expected,
        "token_path": str(path),
        "scopes": granted,
        "missing_scopes": missing,
    }
    if missing:
        out["error"] = f"google granted fewer scopes than requested: missing {missing}; re-run auth_start"
    return out


def status(profile: str, account_email: str | None = None) -> dict[str, Any]:
    pdir = _profile_dir(profile)
    files = [token_path(profile, account_email)] if account_email else sorted(pdir.glob("*.json"))
    accounts = []
    for f in files:
        if not f.exists():
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        accounts.append(
            {
                "account_email": data["account_email"],
                "scopes": data["scopes"],
                "obtained_at": data["obtained_at"],
                "has_refresh_token": bool(data.get("refresh_token")),
            }
        )
    return {"ok": True, "action": "status", "profile": profile, "authorized": bool(accounts), "accounts": accounts}


def load_credentials(profile: str, account_email: str):
    """``google.oauth2.credentials.Credentials`` for a stored profile token (refreshes on use)."""
    path = token_path(profile, account_email)
    if not path.exists():
        raise FileNotFoundError(
            f"no Google token for profile {profile!r} / {account_email} — run noctus.dev.google_account_auth "
            "action='auth_start' then 'auth_finish'"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return _oauth.credentials(data["refresh_token"], list(data["scopes"]))


def google_account_auth(
    action: str,
    profile: str,
    account_email: str | None = None,
    scopes: list[str] | None = None,
    redirected_url: str | None = None,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
) -> dict[str, Any]:
    if action == "auth_start":
        if not account_email or not scopes:
            raise ValueError("auth_start requires account_email and scopes")
        return auth_start(profile, account_email, scopes, redirect_uri)
    if action == "auth_finish":
        if not redirected_url:
            raise ValueError("auth_finish requires redirected_url")
        return auth_finish(profile, redirected_url)
    if action == "status":
        return status(profile, account_email)
    raise ValueError(f"action must be auth_start | auth_finish | status, got {action!r}")


def register(server) -> None:
    @server.tool(
        name="noctus.dev.google_account_auth",
        description=(
            "Mint ONE Google token for one account under a named profile (NoctusAI OAuth client, "
            "server-less PKCE), stored 0600 at ~/.noctusai/private/google-accounts/<profile>/<email>.json "
            "(outside every git tree; never overwrites drive_pull's token). action='auth_start' profile= "
            "account_email= scopes=[calendar.events, drive.readonly, drive.file, calendar.readonly, "
            "gmail.readonly; Google prefix optional; anything else refused] → consent URL (offline + forced "
            "consent). action='auth_finish' profile= redirected_url= → exchanges, refuses a different "
            "account, records the scopes Google granted, returns missing_scopes (ok=false) if fewer. "
            "action='status' profile= [account_email=] → scopes + stored-at, never secrets. "
            "Library: load_credentials(profile, email)."
        ),
    )
    def _google_account_auth(
        action: str,
        profile: str,
        account_email: str | None = None,
        scopes: list[str] | None = None,
        redirected_url: str | None = None,
        redirect_uri: str = DEFAULT_REDIRECT_URI,
    ) -> dict:
        return google_account_auth(
            action=action,
            profile=profile,
            account_email=account_email,
            scopes=scopes,
            redirected_url=redirected_url,
            redirect_uri=redirect_uri,
        )


__all__ = ["google_account_auth", "load_credentials", "normalize_scopes", "SCOPE_ALLOWLIST", "register"]
