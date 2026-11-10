"""Shared server-less Google OAuth (PKCE) plumbing for the private-disk tools.

Used by ``drive_pull`` (one ``drive.readonly`` token per email) and ``google_account_auth`` (named
profiles, a scope allowlist). Both park a PKCE verifier in a pending file, exchange the redirected
URL's code, verify the granted account, and store a 0600 token under :func:`private_root`. The
provider and the account probe are injectable seams so tests run offline against Fakes.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from workspace import get_workspace_root

REPO_ROOT = get_workspace_root()

DEFAULT_REDIRECT_URI = "http://localhost:8011/api/integrations/accounts/google_drive/oauth/callback"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
PENDING_TTL_S = 600
STATE_RE = re.compile(r"[A-Za-z0-9_-]{16,64}")

EmailProbe = Callable[[Any, "list[str]"], str]


def private_root() -> Path:
    """Root for private (PII-bearing) local data — outside every git tree."""
    raw = os.environ.get("NOCTUS_PRIVATE_DIR") or str(Path.home() / ".noctusai" / "private")
    root = Path(raw).expanduser().resolve()
    repo = Path(REPO_ROOT).resolve()
    if root == repo or repo in root.parents:
        raise ValueError(
            f"private root {root} is inside the repo {repo}; set NOCTUS_PRIVATE_DIR outside any git tree"
        )
    return root


def secure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def write_private_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def client() -> tuple[str, str]:
    from dotenv import load_dotenv

    load_dotenv(Path(REPO_ROOT) / ".env")
    cid = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
    secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
    if not cid or not secret:
        raise RuntimeError(
            "GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET are not set (repo .env) — "
            "the social-wiring Google OAuth client is required"
        )
    return cid, secret


def provider():
    from noctusai_lib.security.oauth.google_provider import GoogleProvider

    cid, secret = client()
    return GoogleProvider(client_id=cid, client_secret=secret, use_pkce=True)


def credentials(refresh_token: str, scopes: list[str]):
    from google.oauth2.credentials import Credentials

    cid, secret = client()
    return Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=GOOGLE_TOKEN_URI,
        client_id=cid,
        client_secret=secret,
        scopes=scopes,
    )


def about_email(creds) -> str:
    from googleapiclient.discovery import build

    svc = build("drive", "v3", credentials=creds, cache_discovery=False)
    about = svc.about().get(fields="user(emailAddress)").execute()
    return str(about.get("user", {}).get("emailAddress", "")).lower()


def start_consent(
    pending_dir: Path,
    account_email: str,
    scopes: list[str],
    redirect_uri: str,
    prov=None,
    extra: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Park a PKCE verifier in ``pending_dir`` and return ``(state, consent_url)``.

    The provider always requests offline access with forced consent, so Google returns a refresh token.
    """
    prov = prov or provider()
    state = secrets.token_urlsafe(24)
    auth = asyncio.run(prov.authorization_url(state, list(scopes), redirect_uri))
    write_private_json(
        pending_dir / f".pending-{state}.json",
        {
            "account_email": account_email.strip().lower(),
            "redirect_uri": redirect_uri,
            "code_verifier": auth.code_verifier,
            "created_at": time.time(),
            **(extra or {}),
        },
    )
    return state, auth.url + f"&login_hint={account_email}"


@dataclass
class Consent:
    error: str | None = None
    pending: dict[str, Any] | None = None
    tokens: Any = None


def consume_consent(pending_dir: Path, redirected_url: str, prov=None) -> Consent:
    """Validate the redirected URL, consume the pending file (never replayable), exchange the code."""
    q = parse_qs(urlparse(redirected_url).query)
    if "error" in q:
        return Consent(error=f"google refused consent: {q['error'][0]}")
    code = (q.get("code") or [""])[0]
    state = (q.get("state") or [""])[0]
    if not code or not state:
        return Consent(error="redirected_url has no code/state")
    if not STATE_RE.fullmatch(state):
        return Consent(error="malformed state")
    pending_path = pending_dir / f".pending-{state}.json"
    if not pending_path.exists():
        return Consent(error="unknown state — run auth_start again")
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    pending_path.unlink()
    if time.time() - float(pending["created_at"]) > PENDING_TTL_S:
        return Consent(error="consent expired (>10 min) — run auth_start again")
    prov = prov or provider()
    tokens = asyncio.run(prov.exchange_code(code, state, pending["redirect_uri"], pending["code_verifier"]))
    if not tokens.refresh_token:
        return Consent(error="google returned no refresh_token")
    return Consent(pending=pending, tokens=tokens)
