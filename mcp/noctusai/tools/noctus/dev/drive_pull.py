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
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import _google_oauth as _oauth
from ._google_oauth import (
    DEFAULT_REDIRECT_URI,
    REPO_ROOT,
    private_root,
    secure_dir,
    write_private_json,
)

DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
FOLDER_MIME = "application/vnd.google-apps.folder"
_NATIVE_PREFIX = "application/vnd.google-apps."
_NATIVE_EXPORT_SUFFIX = {
    "application/vnd.google-apps.document": ".txt",
    "application/vnd.google-apps.spreadsheet": ".csv",
    "application/vnd.google-apps.presentation": ".txt",
}
_PENDING_TTL_S = _oauth.PENDING_TTL_S
_LIST_PAGE_SIZE = 1000
_NATIVE_MAX_BYTES = 20_000_000
_DOWNLOAD_ATTEMPTS = 3  # 1 try + 2 retries (roadmap D3); only transient errors retry
_RETRY_BACKOFF_S = (2.0, 5.0)


# ─── paths ────────────────────────────────────────────────────────────────


def _secure_dir(path: Path) -> Path:
    return secure_dir(path)


def _token_dir() -> Path:
    return secure_dir(private_root() / "google-drive")


def _token_path(account_email: str) -> Path:
    return _token_dir() / f"{account_email.strip().lower()}.json"


_write_private_json = write_private_json


def safe_segment(name: str) -> str:
    """One path segment from a Drive name: NFC (macOS decomposes Õ), no separators, not empty."""
    seg = unicodedata.normalize("NFC", name).replace("/", "∕").replace("\x00", "").strip()
    if seg in ("", ".", ".."):
        seg = "_"
    return seg


# ─── oauth ────────────────────────────────────────────────────────────────

_client = _oauth.client
_provider = _oauth.provider
_credentials = _oauth.credentials
_about_email = _oauth.about_email


def auth_start(account_email: str, redirect_uri: str = DEFAULT_REDIRECT_URI) -> dict[str, Any]:
    state, url = _oauth.start_consent(_token_dir(), account_email, [DRIVE_READONLY_SCOPE], redirect_uri)
    return {
        "ok": True,
        "action": "auth_start",
        "account_email": account_email,
        "consent_url": url,
        "state": state,
        "next": (
            "Open consent_url, sign in as account_email and allow. The browser then lands on a page "
            "that fails to load; pass that page's full URL as redirected_url to action='auth_finish'."
        ),
    }


def auth_finish(redirected_url: str) -> dict[str, Any]:
    consent = _oauth.consume_consent(_token_dir(), redirected_url)
    if consent.error:
        return {"ok": False, "action": "auth_finish", "error": consent.error}
    tokens, pending = consent.tokens, consent.pending
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
