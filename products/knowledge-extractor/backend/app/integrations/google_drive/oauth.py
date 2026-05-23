"""OAuth credentials for Drive — required for files shared privately *with you*.

Reuses noc's working Google OAuth client (`GOOGLE_OAUTH_CLIENT_ID` /
`GOOGLE_OAUTH_CLIENT_SECRET` / `GOOGLE_OAUTH_REDIRECT_URI`, same account). On the
first run a browser opens for one-time consent; the resulting token is cached to
disk and silently refreshed thereafter.

Because noc's OAuth client registers a redirect WITH a path
(`http://localhost:8140/oauth/google/callback`), we replicate that exact redirect
with a tiny local callback server — so no change is needed in Google Cloud Console.

Files (paths from settings, resolved relative to the repo root):
  - cached token : settings.google_oauth_token_file  (created on first consent)
Both the token and any client_secret.json live under `secrets/` (gitignored).
"""
from __future__ import annotations

import http.server
import json
import os
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

# This Google account already granted YouTube scopes to noc's OAuth client, so
# Google returns the union (youtube.* + drive.readonly) on consent. oauthlib
# raises on any scope change by default; relax it (we only USE drive.readonly).
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

from app.config import REPO_ROOT, Settings, get_settings
from app.integrations.google_drive.drive_v3_adapter import DriveError, DriveNotConfigured
from app.logging_config import get_logger

logger = get_logger(__name__)

# Read-only is all we need to download shared classes.
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
# Write surface (publishing docx back to Drive): keep read AND add per-file write.
# drive.file = manage only files this app creates — least privilege; the app
# still cannot touch the user's other Drive content. We request the union so a
# single token both lists the existing tree (readonly) and uploads (drive.file).
WRITE_SCOPES = SCOPES + ["https://www.googleapis.com/auth/drive.file"]
_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
_TOKEN_URI = "https://oauth2.googleapis.com/token"


def _resolve(path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else (REPO_ROOT / p)


def _granted_scopes(token_path: Path) -> set[str]:
    """The scopes actually granted in the cached token (empty if unreadable)."""
    try:
        return set(json.loads(token_path.read_text()).get("scopes") or [])
    except (OSError, ValueError) as e:  # corrupt/missing → force a fresh consent
        logger.warning("could not read scopes from %s (%s) — will re-consent", token_path, e)
        return set()


def oauth_configured(settings: Settings | None = None) -> bool:
    """True if usable OAuth config is present (env client, cached token, or json)."""
    settings = settings or get_settings()
    return bool(
        (settings.google_oauth_client_id and settings.google_oauth_client_secret)
        or _resolve(settings.google_oauth_token_file).exists()
        or _resolve(settings.google_oauth_client_secret_file).exists()
    )


def get_oauth_credentials(
    settings: Settings | None = None, *, scopes: list[str] | None = None
) -> Any:
    """Return valid Drive OAuth credentials, running consent once if needed.

    Pass `scopes=WRITE_SCOPES` to require the upload (drive.file) grant. If the
    cached token doesn't already carry every requested scope, a fresh consent is
    run and the broadened token is cached (never silently downgraded).
    """
    from google.auth.transport.requests import Request  # lazy
    from google.oauth2.credentials import Credentials  # lazy

    settings = settings or get_settings()
    scopes = list(scopes or SCOPES)
    token_path = _resolve(settings.google_oauth_token_file)

    creds = None
    if token_path.exists() and set(scopes).issubset(_granted_scopes(token_path)):
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        logger.info("refreshing Drive OAuth token")
        creds.refresh(Request())
        _save(token_path, creds)
        return creds

    # No valid token with the requested scopes → run consent.
    if settings.google_oauth_client_id and settings.google_oauth_client_secret:
        creds = _consent_env_client(settings, scopes)
    elif _resolve(settings.google_oauth_client_secret_file).exists():
        from google_auth_oauthlib.flow import InstalledAppFlow  # lazy

        flow = InstalledAppFlow.from_client_secrets_file(
            str(_resolve(settings.google_oauth_client_secret_file)), scopes
        )
        creds = flow.run_local_server(port=0)
    else:
        raise DriveNotConfigured(
            "No OAuth credentials. Set GOOGLE_OAUTH_CLIENT_ID + "
            "GOOGLE_OAUTH_CLIENT_SECRET in .env (reused from noc), or provide a "
            "Desktop-app client_secret.json under secrets/."
        )

    _save(token_path, creds)
    return creds


def _consent_env_client(settings: Settings, scopes: list[str]) -> Any:
    """Run the consent flow using noc's env-based OAuth client + its redirect."""
    from google_auth_oauthlib.flow import Flow  # lazy

    redirect_uri = settings.google_oauth_redirect_uri
    client_config = {
        "web": {
            "client_id": settings.google_oauth_client_id,
            "client_secret": settings.google_oauth_client_secret,
            "auth_uri": _AUTH_URI,
            "token_uri": _TOKEN_URI,
            "redirect_uris": [redirect_uri],
        }
    }
    flow = Flow.from_client_config(client_config, scopes=scopes, redirect_uri=redirect_uri)
    auth_url, _state = flow.authorization_url(access_type="offline", prompt="consent")
    code = _capture_code_via_local_server(redirect_uri, auth_url, scopes)
    flow.fetch_token(code=code)
    return flow.credentials


def _capture_code_via_local_server(redirect_uri: str, auth_url: str, scopes: list[str]) -> str:
    """Serve the registered redirect locally and capture the ?code= it receives."""
    pr = urlparse(redirect_uri)
    host = pr.hostname or "localhost"
    port = pr.port or 80
    expected_path = pr.path or "/"
    captured: dict[str, str | None] = {}

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (BaseHTTPRequestHandler API)
            parsed = urlparse(self.path)
            if parsed.path != expected_path:
                self.send_response(404)
                self.end_headers()
                return
            q = parse_qs(parsed.query)
            captured["code"] = q.get("code", [None])[0]
            captured["error"] = q.get("error", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Authorization received.</h2>"
                b"<p>You can close this tab and return to the terminal.</p></body></html>"
            )

        def log_message(self, *args):  # silence default request logging
            pass

    try:
        server = http.server.HTTPServer((host, port), _Handler)
    except OSError as e:
        raise DriveError(
            f"Could not bind the OAuth callback server on {host}:{port} ({e}). "
            f"Is a noc service already using that port? Stop it and retry."
        ) from e

    access = "read + write (upload)" if "drive.file" in " ".join(scopes) else "read-only"
    banner = (
        "\n" + "=" * 72 + "\n"
        f"  Sign in as your Google account and approve Drive {access} access.\n"
        "  If a browser didn't open, paste this URL into one:\n\n"
        f"  {auth_url}\n"
        + "=" * 72 + "\n"
    )
    print(banner, flush=True)
    try:
        webbrowser.open(auth_url)
    except Exception:  # headless / no browser — the printed URL still works
        pass

    try:
        while "code" not in captured and "error" not in captured:
            server.handle_request()
    finally:
        server.server_close()

    if captured.get("error"):
        raise DriveError(f"OAuth consent failed: {captured['error']}")
    if not captured.get("code"):
        raise DriveError("OAuth consent did not return an authorization code.")
    return captured["code"]  # type: ignore[return-value]


def _save(token_path: Path, creds: Any) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())
    logger.info("saved Drive OAuth token → %s", token_path)


__all__ = ["get_oauth_credentials", "oauth_configured", "SCOPES", "WRITE_SCOPES"]
