"""``noctus.dev.drive_pull`` — mirror a Google Drive folder to private local disk, zero agent tokens.

Why this exists: the claude.ai Drive connector returns file bytes base64-encoded *into the agent's
context* (~100k tokens for a 300 KB PDF). Deal folders are tens of MB. This tool streams the bytes
straight to disk through the seed Drive integration (``RealDriveReader`` to walk the tree,
``RealDriveDownloader`` for binaries), so no file content ever reaches the agent. It returns counts
and paths only. Origin: roadmap ``project-history/roadmaps/sw-drive-extraction-2026-09.md`` (R6).

Everything lands under ``private_root()`` (``$NOCTUS_PRIVATE_DIR``, default ``~/.noctusai/private``),
which is outside every repo and worktree. Real PII therefore never sits in a git tree and survives
worktree cleanup (memory ``feedback_sw_document_read_authorization``).

Auth is a two-step, server-less OAuth (PKCE) using the seed ``GoogleProvider`` and the same Google
OAuth client social-wiring uses (``GOOGLE_OAUTH_CLIENT_ID`` / ``_SECRET``):

1. ``action="auth_start"`` returns the consent URL and parks the PKCE verifier in a pending file.
2. The human consents. Google redirects the browser to ``redirect_uri`` (nothing listens there, so
   the page errors, but the URL carries ``code`` + ``state``).
3. ``action="auth_finish" redirected_url=<that URL>`` exchanges the code, verifies via Drive
   ``about.get`` that the granted account IS ``account_email`` (a mismatch is refused, never kept),
   and stores the refresh token (0600) under ``private_root()/google-drive/``.

``action="pull"`` walks ``folder_id`` recursively and writes ``drive-mirror/<folder_id>/tree/…`` plus
``manifest.json`` (per file: drive id, parent, relative path, mime, size, md5, modified time, local
path, sha256, status). Re-running skips files whose Drive modifiedTime is unchanged. Google-native Docs/Sheets/Slides
are exported through the reader's export path (text/csv). Every failure is recorded per file and
surfaced in the result, never swallowed.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import secrets
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from workspace import get_workspace_root

REPO_ROOT = get_workspace_root()

DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
DEFAULT_REDIRECT_URI = "http://localhost:8011/api/integrations/accounts/google_drive/oauth/callback"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
FOLDER_MIME = "application/vnd.google-apps.folder"
_NATIVE_PREFIX = "application/vnd.google-apps."
_NATIVE_EXPORT_SUFFIX = {
    "application/vnd.google-apps.document": ".txt",
    "application/vnd.google-apps.spreadsheet": ".csv",
    "application/vnd.google-apps.presentation": ".txt",
}
_PENDING_TTL_S = 600
_LIST_PAGE_SIZE = 1000
_NATIVE_MAX_BYTES = 20_000_000
_DOWNLOAD_ATTEMPTS = 3  # 1 try + 2 retries (roadmap D3); only transient errors retry
_RETRY_BACKOFF_S = (2.0, 5.0)
_STATE_RE = re.compile(r"[A-Za-z0-9_-]{16,64}")


# ─── paths ────────────────────────────────────────────────────────────────


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


def _secure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def _token_dir() -> Path:
    return _secure_dir(private_root() / "google-drive")


def _token_path(account_email: str) -> Path:
    return _token_dir() / f"{account_email.strip().lower()}.json"


def _write_private_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def safe_segment(name: str) -> str:
    """One path segment from a Drive name: NFC (macOS decomposes Õ), no separators, not empty."""
    seg = unicodedata.normalize("NFC", name).replace("/", "∕").replace("\x00", "").strip()
    if seg in ("", ".", ".."):
        seg = "_"
    return seg


# ─── oauth ────────────────────────────────────────────────────────────────


def _client() -> tuple[str, str]:
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


def _provider():
    from noctusai_lib.security.oauth.google_provider import GoogleProvider

    cid, secret = _client()
    return GoogleProvider(client_id=cid, client_secret=secret, use_pkce=True)


def auth_start(account_email: str, redirect_uri: str = DEFAULT_REDIRECT_URI) -> dict[str, Any]:
    state = secrets.token_urlsafe(24)
    auth = asyncio.run(_provider().authorization_url(state, [DRIVE_READONLY_SCOPE], redirect_uri))
    _write_private_json(
        _token_dir() / f".pending-{state}.json",
        {
            "account_email": account_email.strip().lower(),
            "redirect_uri": redirect_uri,
            "code_verifier": auth.code_verifier,
            "created_at": time.time(),
        },
    )
    return {
        "ok": True,
        "action": "auth_start",
        "account_email": account_email,
        "consent_url": auth.url + f"&login_hint={account_email}",
        "state": state,
        "next": (
            "Open consent_url, sign in as account_email and allow. The browser then lands on a page "
            "that fails to load; pass that page's full URL as redirected_url to action='auth_finish'."
        ),
    }


def _credentials(refresh_token: str, scopes: list[str]):
    from google.oauth2.credentials import Credentials

    cid, secret = _client()
    return Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=GOOGLE_TOKEN_URI,
        client_id=cid,
        client_secret=secret,
        scopes=scopes,
    )


def _about_email(creds) -> str:
    from googleapiclient.discovery import build

    svc = build("drive", "v3", credentials=creds, cache_discovery=False)
    about = svc.about().get(fields="user(emailAddress)").execute()
    return str(about.get("user", {}).get("emailAddress", "")).lower()


def auth_finish(redirected_url: str) -> dict[str, Any]:
    q = parse_qs(urlparse(redirected_url).query)
    if "error" in q:
        return {"ok": False, "action": "auth_finish", "error": f"google refused consent: {q['error'][0]}"}
    code = (q.get("code") or [""])[0]
    state = (q.get("state") or [""])[0]
    if not code or not state:
        return {"ok": False, "action": "auth_finish", "error": "redirected_url has no code/state"}
    if not _STATE_RE.fullmatch(state):
        return {"ok": False, "action": "auth_finish", "error": "malformed state"}
    pending_path = _token_dir() / f".pending-{state}.json"
    if not pending_path.exists():
        return {"ok": False, "action": "auth_finish", "error": "unknown state — run auth_start again"}
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    pending_path.unlink()
    if time.time() - float(pending["created_at"]) > _PENDING_TTL_S:
        return {"ok": False, "action": "auth_finish", "error": "consent expired (>10 min) — run auth_start again"}
    tokens = asyncio.run(
        _provider().exchange_code(code, state, pending["redirect_uri"], pending["code_verifier"])
    )
    if not tokens.refresh_token:
        return {"ok": False, "action": "auth_finish", "error": "google returned no refresh_token"}
    granted = list(tokens.scope or [])
    if DRIVE_READONLY_SCOPE not in granted:
        return {"ok": False, "action": "auth_finish", "error": f"drive.readonly not granted (got {granted})"}
    # Google merges the account's earlier grants on this client into the refresh token
    # (include_granted_scopes). Keep only drive.readonly: every access token minted from this file
    # is then requested with that scope alone, so it cannot send mail or touch YouTube.
    scopes = [DRIVE_READONLY_SCOPE]
    expected = pending["account_email"]
    actual = _about_email(_credentials(tokens.refresh_token, scopes))
    if actual != expected:
        # Never revoke here: Google revokes the whole (user, client) grant, and this is the SAME
        # OAuth client social-wiring's live Gmail/YouTube integrations use — a revoke would silently
        # disconnect production. Discard the token instead.
        return {
            "ok": False,
            "action": "auth_finish",
            "error": f"consent was granted by {actual!r}, expected {expected!r}; token discarded, not stored",
        }
    path = _token_path(expected)
    _write_private_json(
        path,
        {
            "account_email": expected,
            "refresh_token": tokens.refresh_token,
            "scopes": scopes,
            "obtained_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {
        "ok": True,
        "action": "auth_finish",
        "account_email": expected,
        "token_path": str(path),
        "scopes": scopes,
        "granted_scopes": granted,
    }


def _load_credentials(account_email: str):
    path = _token_path(account_email)
    if not path.exists():
        raise FileNotFoundError(
            f"no Drive token for {account_email} — run action='auth_start' then 'auth_finish'"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return _credentials(data["refresh_token"], list(data["scopes"]))


# ─── pull ─────────────────────────────────────────────────────────────────


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _list_children(reader, folder_id: str) -> list[Any]:
    res = asyncio.run(reader.search("", folder_id=folder_id, page_size=_LIST_PAGE_SIZE))
    if res.next_page_token:
        raise RuntimeError(
            f"folder {folder_id} has more than {_LIST_PAGE_SIZE} children — the seed reader "
            "does not page yet; extend RealDriveReader.search with page_token before pulling it"
        )
    return list(res.hits)


def _walk(reader, folder_id: str, rel: Path, parent_id: str, out: list[dict[str, Any]], seen: set[str]) -> None:
    if folder_id in seen:
        return
    seen.add(folder_id)
    for hit in _list_children(reader, folder_id):
        seg = safe_segment(hit.name)
        entry = {
            "drive_id": hit.id,
            "parent_id": folder_id,
            "name": unicodedata.normalize("NFC", hit.name),
            "rel_path": str(rel / seg),
            "mime_type": hit.mime_type,
            "size_bytes": hit.size_bytes,
            "md5": None,
            "modified_time": hit.modified_time,
            "is_folder": hit.mime_type == FOLDER_MIME,
        }
        out.append(entry)
        if entry["is_folder"]:
            _walk(reader, hit.id, rel / seg, folder_id, out, seen)


def _dedupe_rel_paths(entries: list[dict[str, Any]]) -> None:
    """Two Drive siblings may share a name; suffix the drive id so no file overwrites another."""
    counts: dict[str, int] = {}
    for e in entries:
        counts[e["rel_path"]] = counts.get(e["rel_path"], 0) + 1
    for e in entries:
        if counts[e["rel_path"]] > 1 and not e["is_folder"]:
            p = Path(e["rel_path"])
            e["rel_path"] = str(p.with_name(f"{p.stem} [{e['drive_id']}]{p.suffix}"))


def _is_transient(exc: BaseException) -> bool:
    """Timeouts, connection resets and Drive 429/5xx retry. Anything else (404, 403, a truncated
    native export) fails at once; retrying a permanent error only hides it longer."""
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    status = getattr(getattr(exc, "resp", None), "status", None)
    try:
        return int(status) == 429 or int(status) >= 500
    except (TypeError, ValueError):
        return False


def _fetch_with_retry(fetch, attempts: int = _DOWNLOAD_ATTEMPTS, sleep=time.sleep) -> int:
    """Run ``fetch`` up to ``attempts`` times on transient errors; return the attempt that succeeded."""
    for attempt in range(1, attempts + 1):
        try:
            fetch()
            return attempt
        except Exception as exc:
            if attempt == attempts or not _is_transient(exc):
                raise
            sleep(_RETRY_BACKOFF_S[min(attempt - 1, len(_RETRY_BACKOFF_S) - 1)])
    raise AssertionError("unreachable")


def _fetch_one(reader, downloader, e: dict[str, Any], local: Path, is_native: bool, counts: dict[str, int]) -> None:
    if is_native:
        content = asyncio.run(reader.read_file(e["drive_id"], max_bytes=_NATIVE_MAX_BYTES))
        if content is None:
            raise FileNotFoundError("export returned nothing")
        if content.truncated:
            raise RuntimeError(f"export exceeds {_NATIVE_MAX_BYTES} bytes")
        local.write_bytes(content.data)
        e["status"] = "exported"
        counts["exported"] += 1
    else:
        meta = asyncio.run(downloader.download(e["drive_id"], local))
        e["md5"] = meta.md5_checksum or e.get("md5")
        e["status"] = "downloaded"
        counts["downloaded"] += 1


def pull(folder_id: str, account_email: str, dry_run: bool = False) -> dict[str, Any]:
    from noctusai_lib.integrations.google_drive.real import RealDriveDownloader
    from noctusai_lib.integrations.google_drive.real_reader import RealDriveReader

    started = time.monotonic()
    creds = _load_credentials(account_email)
    reader = RealDriveReader(oauth_credentials=creds)
    downloader = RealDriveDownloader(oauth_credentials=creds)

    root_meta = asyncio.run(reader.get_file(folder_id))
    if root_meta is None:
        return {"ok": False, "action": "pull", "error": f"folder {folder_id} not visible to {account_email}"}
    if root_meta.mime_type != FOLDER_MIME:
        return {"ok": False, "action": "pull", "error": f"{folder_id} is not a folder ({root_meta.mime_type})"}

    entries: list[dict[str, Any]] = []
    _walk(reader, folder_id, Path(), folder_id, entries, set())
    _dedupe_rel_paths(entries)

    base = _secure_dir(private_root() / "drive-mirror" / folder_id)
    tree = base / "tree"
    manifest_path = base / "manifest.json"
    previous: dict[str, dict[str, Any]] = {}
    if manifest_path.exists():
        for e in json.loads(manifest_path.read_text(encoding="utf-8")).get("entries", []):
            previous[e["drive_id"]] = e

    counts = {"folders": 0, "downloaded": 0, "exported": 0, "unchanged": 0, "failed": 0}
    total_bytes = 0
    for e in entries:
        if e["is_folder"]:
            counts["folders"] += 1
            e["status"] = "folder"
            continue
        is_native = e["mime_type"].startswith(_NATIVE_PREFIX)
        rel = Path(e["rel_path"])
        if is_native:
            rel = rel.with_name(rel.name + _NATIVE_EXPORT_SUFFIX.get(e["mime_type"], ".txt"))
        local = tree / rel
        e["local_path"] = str(local)
        prev = previous.get(e["drive_id"])
        if (
            prev
            and local.exists()
            and prev.get("modified_time") == e["modified_time"]
            and prev.get("sha256")
        ):
            e.update(status="unchanged", sha256=prev["sha256"], local_bytes=local.stat().st_size)
            counts["unchanged"] += 1
            total_bytes += e["local_bytes"]
            continue
        if dry_run:
            e["status"] = "would_download"
            continue
        try:
            local.parent.mkdir(parents=True, exist_ok=True)
            e["attempts"] = _fetch_with_retry(
                lambda: _fetch_one(reader, downloader, e, local, is_native, counts)
            )
            os.chmod(local, 0o600)
            e["sha256"] = _sha256(local)
            e["local_bytes"] = local.stat().st_size
            total_bytes += e["local_bytes"]
        except Exception as exc:  # recorded per file and surfaced in the result — never swallowed
            e["status"] = "failed"
            e["error"] = f"{type(exc).__name__}: {exc}"
            counts["failed"] += 1

    manifest = {
        "folder_id": folder_id,
        "folder_name": unicodedata.normalize("NFC", root_meta.name),
        "account_email": account_email,
        "pulled_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "entries": entries,
    }
    if not dry_run:
        _write_private_json(manifest_path, manifest)
    failed = [
        {"rel_path": e["rel_path"], "error": e["error"]} for e in entries if e.get("status") == "failed"
    ]
    return {
        "ok": counts["failed"] == 0,
        "action": "pull",
        "dry_run": dry_run,
        "folder_id": folder_id,
        "manifest_path": str(manifest_path),
        "tree_path": str(tree),
        "files": len([e for e in entries if not e["is_folder"]]),
        "counts": counts,
        "total_bytes": total_bytes,
        "failed": failed,
        "elapsed_s": round(time.monotonic() - started, 1),
    }


def drive_pull(
    action: str,
    account_email: str | None = None,
    folder_id: str | None = None,
    redirected_url: str | None = None,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
    dry_run: bool = False,
) -> dict[str, Any]:
    if action == "auth_start":
        if not account_email:
            raise ValueError("auth_start requires account_email")
        return auth_start(account_email, redirect_uri)
    if action == "auth_finish":
        if not redirected_url:
            raise ValueError("auth_finish requires redirected_url")
        return auth_finish(redirected_url)
    if action == "pull":
        if not folder_id or not account_email:
            raise ValueError("pull requires folder_id and account_email")
        return pull(folder_id, account_email, dry_run=dry_run)
    raise ValueError(f"action must be auth_start | auth_finish | pull, got {action!r}")


def register(server) -> None:
    @server.tool(
        name="noctus.dev.drive_pull",
        description=(
            "Mirror a Google Drive folder to PRIVATE local disk (~/.noctusai/private or "
            "$NOCTUS_PRIVATE_DIR, outside every git tree) with zero agent tokens — bytes stream "
            "Drive→disk via the seed Drive integration; the result carries counts + paths only, never "
            "file content. Use instead of the claude.ai Drive connector's download (which returns "
            "base64 into context). action='auth_start' account_email= → consent URL (drive.readonly, "
            "PKCE, social-wiring's Google OAuth client); action='auth_finish' redirected_url= → "
            "exchanges the code, refuses a token granted by a different account, stores it 0600; "
            "action='pull' folder_id= account_email= [dry_run] → recursive mirror + manifest.json "
            "(drive id, parent, path, mime, size, md5, sha256, status per file; files with an "
            "unchanged modifiedTime skipped; Google-native files exported as text/csv; per-file failures surfaced)."
        ),
    )
    def _drive_pull(
        action: str,
        account_email: str | None = None,
        folder_id: str | None = None,
        redirected_url: str | None = None,
        redirect_uri: str = DEFAULT_REDIRECT_URI,
        dry_run: bool = False,
    ) -> dict:
        return drive_pull(
            action=action,
            account_email=account_email,
            folder_id=folder_id,
            redirected_url=redirected_url,
            redirect_uri=redirect_uri,
            dry_run=dry_run,
        )


__all__ = ["drive_pull", "private_root", "safe_segment", "register"]
