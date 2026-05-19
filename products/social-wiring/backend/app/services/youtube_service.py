"""YouTube Data API v3 wrapper.

Single chokepoint for every YouTube API call. Routers and other services
talk to this module — never to ``googleapiclient`` directly. Two reasons:

1. **Quota accounting** — every method documents its quota cost so the
   product stays under the daily 10,000-unit budget. Centralising the
   calls keeps that documentation honest.
2. **Token refresh** — access tokens expire after one hour. A method
   takes a ``StoredCredential`` (refresh-capable) and refreshes
   transparently when the access token is stale, persisting the new
   bundle back through ``CredentialStore.upsert``.

The module is structured so the side-effect-free OAuth-URL helpers are
testable without network I/O. The googleapiclient-bound methods get
mocked at the ``_build_service`` seam in tests.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from noctusai_lib.security.oauth import GoogleProvider
from app.services.credential_vault import (
    CredentialStore,
    EncryptionNotConfigured,
    StoredCredential,
)

logger = logging.getLogger(__name__)

# Scopes required for upload + read + edit. force-ssl is the catch-all
# that lets us call videos.update for thumbnail edits later — kept now
# so users don't have to re-consent when Phase 4 grows.
YOUTUBE_SCOPES: list[str] = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


class YouTubeServiceError(Exception):
    """All YouTube-side failures route through this — routers translate to
    HTTP. Wraps the underlying ``HttpError`` / ``RefreshError`` with a
    human-readable message."""


class YouTubeNotConnected(YouTubeServiceError):
    """No credentials persisted for this org — caller should redirect the
    user through OAuth before retrying."""


class YouTubeQuotaExceededError(YouTubeServiceError):
    """Daily quota exhausted on the YouTube Data API. Distinct from generic
    upload failures so callers can surface a clear "tomorrow / retry-in-6h"
    message instead of a confusing 400-Bad-Request explanation."""


# ─── Retry policy for transient YouTube errors ──────────────────────────
# Wraps API calls (videos.insert resumable upload, channels.list, etc.)
# with bounded retry on transient failures. Hand-rolled — the seed's
# ``RetryPolicy`` is pure-data (backoff math), no executor.
#
# Retryable: 5xx server errors, 429 rate-limit, network/transport errors.
# Non-retryable: 4xx auth/permission/not-found, quotaExceeded (special).
# Defaults: 3 attempts (1 initial + 2 retries), exponential backoff
# 2s/8s, max 30s — fits the YT API's typical recovery window.

_MAX_RETRY_ATTEMPTS = 3
_RETRY_BASE_DELAY_S = 2.0
_RETRY_MAX_DELAY_S = 30.0


def _is_quota_exceeded(exc: HttpError) -> bool:
    """Detect the ``quotaExceeded`` sub-error in an HttpError body.

    Google returns 403 with ``reason="quotaExceeded"`` (or sometimes
    ``"dailyLimitExceeded"``) when the daily quota is hit. The status
    code alone (403) can't distinguish quota from permission errors —
    we have to inspect the JSON body.
    """
    try:
        content = exc.content.decode("utf-8") if isinstance(exc.content, bytes) else str(exc.content or "")
    except Exception:
        return False
    lowered = content.lower()
    return (
        "quotaexceeded" in lowered
        or "dailylimitexceeded" in lowered
        or "ratelimitexceeded" in lowered and exc.resp.status == 403
    )


def _is_transient_http_error(exc: HttpError) -> bool:
    """5xx + 429 are transient; everything else is permanent.

    quotaExceeded is special-cased UP in the call site (we raise
    ``YouTubeQuotaExceededError`` before checking transience).
    """
    status = exc.resp.status
    return status == 429 or 500 <= status < 600


def _is_transient_network_error(exc: Exception) -> bool:
    """Match common transport-layer transient errors that the resumable
    upload loop can retry from."""
    import socket
    import ssl
    return isinstance(exc, (ConnectionError, TimeoutError, socket.error, ssl.SSLError))


def _retry_with_backoff(call, *, label: str):
    """Execute ``call()`` with bounded retry on transient errors.

    Args:
        call: zero-arg callable that does the YT API request. Raises
            ``HttpError`` on API failures, transport errors otherwise.
        label: short name for log lines (e.g. ``"upload_video"``).

    Raises:
        YouTubeQuotaExceededError: quota-exhausted (no retry attempted).
        YouTubeServiceError: max attempts exhausted OR non-transient error.
    """
    import time

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRY_ATTEMPTS):
        try:
            return call()
        except HttpError as exc:
            if _is_quota_exceeded(exc):
                logger.error(
                    "%s: YouTube quota exceeded — no retry. Status=%s body=%s",
                    label,
                    exc.resp.status,
                    (exc.content or b"")[:200],
                )
                raise YouTubeQuotaExceededError(
                    "⚠️ YouTube quota esgotada hoje. "
                    "Retry automático em 6h, ou tente novamente amanhã."
                ) from exc
            if not _is_transient_http_error(exc):
                # Non-transient HTTP (4xx auth/perm/notfound) — fail fast.
                logger.warning(
                    "%s: non-transient HttpError status=%s — failing fast.",
                    label, exc.resp.status,
                )
                raise YouTubeServiceError(_format_http_error(exc)) from exc
            last_exc = exc
        except Exception as exc:
            if not _is_transient_network_error(exc):
                raise
            last_exc = exc

        # Decide whether to retry.
        if attempt < _MAX_RETRY_ATTEMPTS - 1:
            delay = min(_RETRY_BASE_DELAY_S * (4 ** attempt), _RETRY_MAX_DELAY_S)
            logger.warning(
                "%s: transient failure (attempt %d/%d) — retrying in %.1fs: %s",
                label, attempt + 1, _MAX_RETRY_ATTEMPTS, delay, last_exc,
            )
            time.sleep(delay)
        else:
            logger.error(
                "%s: max retries (%d) exhausted; raising.",
                label, _MAX_RETRY_ATTEMPTS,
            )

    # Exhausted retries.
    if isinstance(last_exc, HttpError):
        raise YouTubeServiceError(_format_http_error(last_exc)) from last_exc
    raise YouTubeServiceError(
        f"YouTube call '{label}' failed after {_MAX_RETRY_ATTEMPTS} attempts: {last_exc}"
    ) from last_exc


@dataclass
class ChannelInfo:
    """Subset of channels.list response that the UI cares about."""

    channel_id: str
    title: str
    subscriber_count: int
    video_count: int
    view_count: int


@dataclass
class VideoSummary:
    """Subset of videos.list response, matched to the Videos page columns."""

    video_id: str
    title: str
    description: str
    thumbnail_url: str
    published_at: datetime
    duration: str
    privacy_status: str
    view_count: int
    like_count: int
    comment_count: int
    tags: list[str]
    category_id: str


class YouTubeService:
    """Per-request collaborator constructed from settings + a credential
    store. Stateless across requests — each method does its own token
    freshness check and refresh."""

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        credential_store: CredentialStore,
    ):
        if not (client_id and client_secret):
            raise YouTubeServiceError(
                "YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET missing — "
                "configure the OAuth client in Google Cloud Console "
                "and add the values to .env."
            )
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._store = credential_store
    def get_auth_url(self, *, state: str) -> tuple[str, str]:
        """Build the consent-screen URL the user gets redirected to.

    ``state`` is opaque to YouTube; we use it to round-trip the
    ``org_id`` so the callback can persist tokens to the right org
    without trusting the redirect URI alone.

    Lifecycle delegated to ``noctusai_lib.security.oauth.GoogleProvider``
    (the seed-consume seam — see ``app/services/google_oauth.py``). The
    second tuple element used to be a PKCE ``code_verifier``; the seed
    provider is a confidential-client flow (client_secret authenticated)
    that does not use PKCE, so it is now an empty string. The callers
    persist/replay it harmlessly; the return shape is preserved so the
    settings router needs no change.

    Quota cost: 0.
    """
        provider = self._oauth_provider()
        auth_url = _run_sync(
            provider.authorization_url(
                state=state,
                scopes=list(YOUTUBE_SCOPES),
                redirect_uri=self._redirect_uri,
            )
        )
        return auth_url.url, ""
    def exchange_code(self, *, code: str, code_verifier: str | None = None) -> dict[str, Any]:
        """Exchange the OAuth callback's ``code`` for a token bundle.

    Lifecycle delegated to the seed ``GoogleProvider``. ``code_verifier``
    is accepted for signature back-compat with the settings router but is
    unused — the confidential-client exchange the seed performs does not
    use PKCE.

    Returns the raw token dict in the SAME shape the former
    google_auth_oauthlib path produced (``_credentials_to_bundle``), so
    the Phase-5-bound API layer + the credential store consume it
    unchanged:
      - ``access_token`` / ``refresh_token``
      - ``expires_at`` (ISO timestamp UTC)
      - ``token_uri`` (for the Phase-5 googleapiclient refresh path)
      - ``scopes`` (granted, list)

    Quota cost: 0.
    """
        provider = self._oauth_provider()
        token_set = _run_sync(
            provider.exchange_code(
                code=code, state="", redirect_uri=self._redirect_uri
            )
        )
        return _tokenset_to_bundle(token_set)
    def _oauth_provider(self) -> GoogleProvider:
        """Construct the seed Google OAuth provider for this service.

    Separated so tests can inject a Fake via the seed factory. The
    provider owns the authorize/exchange/refresh/revoke lifecycle; the
    googleapiclient API-layer machinery (``_fresh_credentials`` /
    ``_build_service``) is unchanged (Phase-5 scope).
    """
        return GoogleProvider(
            client_id=self._client_id,
            client_secret=self._client_secret,
        )
    def revoke_and_disconnect(self, *, org_id: UUID) -> bool:
        """Best-effort revoke + delete from DB.

    Token revocation is fire-and-forget — if the revoke call fails
    (network blip, token already expired), we still delete the local
    record so the user-facing "disconnect" button is honest. Revocation
    lifecycle delegated to the seed ``GoogleProvider`` (idempotent;
    already-revoked is treated as success seed-side).
    """
        existing = self._store.get(str(org_id), "youtube")
        if existing is None:
            return False

        try:
            token = (
                existing.tokens.get("refresh_token")
                or existing.tokens.get("access_token")
            )
            if token:
                _run_sync(self._oauth_provider().revoke(token))
        except Exception:
            logger.warning(
                "youtube revoke call failed for org_id=%s — deleting local record anyway",
                org_id,
                exc_info=True,
            )

        return self._store.delete(str(org_id), "youtube")

    # ─── Authenticated API calls (require a connected channel) ─────────
    def get_channel_info(self, *, org_id: UUID) -> ChannelInfo:
        """Fetch the connected channel's metadata.

        Quota cost: 1 unit.
        """
        creds = self._fresh_credentials(org_id)
        service = self._build_service(creds)

        try:
            response = (
                service.channels()
                .list(part="snippet,statistics", mine=True)
                .execute()
            )
        except HttpError as exc:
            raise YouTubeServiceError(_format_http_error(exc)) from exc

        items = response.get("items") or []
        if not items:
            raise YouTubeServiceError(
                "OAuth succeeded but no channel is associated with this Google "
                "account. Make sure you authorised with an account that owns "
                "a YouTube channel."
            )
        item = items[0]
        stats = item.get("statistics", {})
        return ChannelInfo(
            channel_id=item["id"],
            title=item["snippet"]["title"],
            subscriber_count=int(stats.get("subscriberCount", 0)),
            video_count=int(stats.get("videoCount", 0)),
            view_count=int(stats.get("viewCount", 0)),
        )

    def list_all_videos(
        self,
        *,
        org_id: UUID,
        page_token: str | None = None,
        max_results: int = 50,
    ) -> tuple[list[VideoSummary], str | None]:
        """List videos owned by the connected channel + their stats.

        Quota cost: 1 (search.list) + 1 (videos.list) per page = 2 units.
        Returns (videos, next_page_token); next is None on the last page.
        """
        creds = self._fresh_credentials(org_id)
        service = self._build_service(creds)

        try:
            search = (
                service.search()
                .list(
                    part="id",
                    forMine=True,
                    type="video",
                    maxResults=max_results,
                    pageToken=page_token,
                )
                .execute()
            )
            video_ids = [
                item["id"]["videoId"]
                for item in search.get("items", [])
                if item.get("id", {}).get("videoId")
            ]
            if not video_ids:
                return [], None

            details = (
                service.videos()
                .list(
                    part="snippet,statistics,status,contentDetails",
                    id=",".join(video_ids),
                )
                .execute()
            )
        except HttpError as exc:
            raise YouTubeServiceError(_format_http_error(exc)) from exc

        return (
            [_video_item_to_summary(item) for item in details.get("items", [])],
            search.get("nextPageToken"),
        )

    def get_video_stats(
        self, *, org_id: UUID, video_ids: list[str]
    ) -> dict[str, dict[str, int]]:
        """Refresh metrics for an explicit set of video IDs.

        Quota cost: 1 unit per 50 IDs (rounded up).
        """
        if not video_ids:
            return {}

        creds = self._fresh_credentials(org_id)
        service = self._build_service(creds)
        result: dict[str, dict[str, int]] = {}

        for chunk_start in range(0, len(video_ids), 50):
            chunk = video_ids[chunk_start : chunk_start + 50]
            try:
                response = (
                    service.videos()
                    .list(part="statistics", id=",".join(chunk))
                    .execute()
                )
            except HttpError as exc:
                raise YouTubeServiceError(_format_http_error(exc)) from exc
            for item in response.get("items", []):
                stats = item.get("statistics", {})
                result[item["id"]] = {
                    "view_count": int(stats.get("viewCount", 0)),
                    "like_count": int(stats.get("likeCount", 0)),
                    "comment_count": int(stats.get("commentCount", 0)),
                }
        return result

    def set_thumbnail(
        self,
        *,
        org_id: UUID,
        video_id: str,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
    ) -> None:
        """Upload a custom thumbnail for ``video_id`` via thumbnails.set.

        Quota cost: 50 units. Channels must have custom-thumbnail
        permissions (most do; new channels require verification). Image
        must be under 2MB + JPEG/PNG/BMP; YouTube enforces server-side.

        Best-effort callers: catch ``YouTubeServiceError`` since
        thumbnail failure shouldn't fail the parent video upload. The
        video stays up with whatever default thumbnail YT picked.
        """
        from googleapiclient.http import MediaInMemoryUpload

        creds = self._fresh_credentials(org_id)
        service = self._build_service(creds)
        media = MediaInMemoryUpload(image_bytes, mimetype=mime_type, resumable=False)

        try:
            service.thumbnails().set(videoId=video_id, media_body=media).execute()
        except HttpError as exc:
            raise YouTubeServiceError(_format_http_error(exc)) from exc

    def get_processing_status(
        self,
        *,
        org_id: UUID,
        video_id: str,
    ) -> dict[str, str]:
        """Probe YT's processing pipeline state for ``video_id``.

        Returns:
            {
                "upload_status": "uploaded" | "processed" | "failed"
                                 | "rejected" | "deleted",
                "processing_status": "processing" | "succeeded"
                                     | "failed" | "terminated",
                "privacy_status": "private" | "unlisted" | "public",
            }

        Used by ``upload_service`` to wait until the video is actually
        playable before delivering the completion message (otherwise
        operators click the URL too early and see "this video is being
        processed"). Quota cost: 1 unit per call.
        """
        creds = self._fresh_credentials(org_id)
        service = self._build_service(creds)

        try:
            response = (
                service.videos()
                .list(part="status,processingDetails", id=video_id)
                .execute()
            )
        except HttpError as exc:
            raise YouTubeServiceError(_format_http_error(exc)) from exc

        items = response.get("items") or []
        if not items:
            raise YouTubeServiceError(
                f"videos.list returned no items for video_id={video_id!r} — "
                "may have been deleted or never finished uploading."
            )
        item = items[0]
        status_block = item.get("status", {}) or {}
        proc_block = item.get("processingDetails", {}) or {}
        return {
            "upload_status": str(status_block.get("uploadStatus") or "unknown"),
            "processing_status": str(proc_block.get("processingStatus") or "unknown"),
            "privacy_status": str(status_block.get("privacyStatus") or "unknown"),
        }

    def upload_video(
        self,
        *,
        org_id: UUID,
        file_path: str,
        title: str,
        description: str,
        tags: list[str],
        privacy_status: str = "private",
        category_id: str = "22",  # People & Blogs
    ) -> str:
        """Resumable upload via ``videos.insert``. Returns the YouTube
        video ID on success.

        Quota cost: 100 units (the heaviest call in the API).
        """
        if privacy_status not in ("public", "unlisted", "private"):
            raise YouTubeServiceError(
                f"privacy_status must be public/unlisted/private, got {privacy_status!r}"
            )

        creds = self._fresh_credentials(org_id)
        service = self._build_service(creds)

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }
        # Resumable upload with per-chunk retry. F3: a transient failure
        # mid-stream no longer restarts the upload from byte 0 — the
        # same ``request`` object is kept across retries so
        # ``request.resumable_uri`` stays valid + ``next_chunk()`` picks
        # up from the last successful chunk. The attempt counter resets
        # on every successful chunk, so a flaky network produces many
        # short retries rather than one long retry sequence.
        media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
        request = service.videos().insert(
            part="snippet,status", body=body, media_body=media
        )

        response = self._resumable_upload_with_chunk_retry(request)
        return response["id"]

    def _resumable_upload_with_chunk_retry(self, request: Any) -> dict:
        """Drive a googleapiclient resumable upload to completion with
        per-chunk retry on transient failures.

        Keep the ``request`` object across retries — its
        ``resumable_uri`` field encodes the upload session ID + offset
        on YT's side, so ``next_chunk()`` resumes seamlessly after a
        transient failure.

        Per-chunk retry budget (`_MAX_RETRY_ATTEMPTS`) RESETS on every
        successful chunk so long uploads with multiple flaky moments
        don't exhaust the budget on the first hiccup.
        """
        import time

        response: dict | None = None
        attempts_this_chunk = 0
        while response is None:
            try:
                _, response = request.next_chunk()
                attempts_this_chunk = 0  # reset on chunk success
            except HttpError as exc:
                if _is_quota_exceeded(exc):
                    logger.error(
                        "upload_video: YouTube quota exceeded — no retry. "
                        "Status=%s body=%s",
                        exc.resp.status,
                        (exc.content or b"")[:200],
                    )
                    raise YouTubeQuotaExceededError(
                        "⚠️ YouTube quota esgotada hoje. "
                        "Retry automático em 6h, ou tente novamente amanhã."
                    ) from exc
                if not _is_transient_http_error(exc):
                    logger.warning(
                        "upload_video: non-transient HttpError status=%s "
                        "— failing fast.",
                        exc.resp.status,
                    )
                    raise YouTubeServiceError(_format_http_error(exc)) from exc
                attempts_this_chunk += 1
                if attempts_this_chunk >= _MAX_RETRY_ATTEMPTS:
                    logger.error(
                        "upload_video: chunk retries (%d) exhausted; raising.",
                        _MAX_RETRY_ATTEMPTS,
                    )
                    raise YouTubeServiceError(_format_http_error(exc)) from exc
                delay = min(
                    _RETRY_BASE_DELAY_S * (4 ** (attempts_this_chunk - 1)),
                    _RETRY_MAX_DELAY_S,
                )
                logger.warning(
                    "upload_video: transient HttpError on chunk (attempt %d/%d) "
                    "— resuming in %.1fs: %s",
                    attempts_this_chunk,
                    _MAX_RETRY_ATTEMPTS,
                    delay,
                    exc,
                )
                time.sleep(delay)
            except Exception as exc:
                if not _is_transient_network_error(exc):
                    raise
                attempts_this_chunk += 1
                if attempts_this_chunk >= _MAX_RETRY_ATTEMPTS:
                    raise YouTubeServiceError(
                        f"YouTube upload failed after {_MAX_RETRY_ATTEMPTS} "
                        f"network retries: {exc}"
                    ) from exc
                delay = min(
                    _RETRY_BASE_DELAY_S * (4 ** (attempts_this_chunk - 1)),
                    _RETRY_MAX_DELAY_S,
                )
                logger.warning(
                    "upload_video: transient network error on chunk "
                    "(attempt %d/%d) — resuming in %.1fs: %s",
                    attempts_this_chunk,
                    _MAX_RETRY_ATTEMPTS,
                    delay,
                    exc,
                )
                time.sleep(delay)
        return response

    # ─── Internals ────────────────────────────────────────────────────
    def _fresh_credentials(self, org_id: UUID) -> Credentials:
        """Load + refresh-if-stale + persist-if-changed.

        The persist-if-changed step is critical: the access_token is
        rotated transparently on refresh; without persisting, the next
        request would re-issue an unnecessary refresh call (extra latency,
        no quota cost but ugly).
        """
        stored = self._store.get(str(org_id), "youtube")
        if stored is None:
            raise YouTubeNotConnected(
                f"No YouTube credentials persisted for org_id={org_id}. "
                "Connect via Settings → YouTube → Connect."
            )
        creds = _bundle_to_credentials(
            stored.tokens, self._client_id, self._client_secret
        )

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            new_bundle = _credentials_to_bundle(creds)
            self._store.put(
                str(org_id), "youtube", new_bundle, metadata={"channel_id": stored.metadata.get("channel_id"), "channel_title": stored.metadata.get("channel_title"), "scopes": stored.metadata.get("scopes", [])})
        return creds

    def _build_service(self, creds: Credentials):
        """Construct a googleapiclient YouTube service instance.

        Test seam: tests monkeypatch this method to return a
        MagicMock-shaped service so quota-bearing calls never escape the
        process.
        """
        return build("youtube", "v3", credentials=creds, cache_discovery=False)


# ─── Module-level helpers (testable in isolation) ──────────────────────
def _credentials_to_bundle(creds: Credentials) -> dict[str, Any]:
    """Translate google.oauth2.credentials.Credentials → JSON-safe dict."""
    expires_at = creds.expiry
    if expires_at is not None and expires_at.tzinfo is None:
        # google-auth returns naive UTC; normalise so downstream consumers
        # never have to guess.
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "token_uri": creds.token_uri,
        "scopes": list(creds.scopes or []),
    }


def _bundle_to_credentials(
    bundle: dict[str, Any], client_id: str, client_secret: str
) -> Credentials:
    """Inverse of :func:`_credentials_to_bundle`. The client_id/secret
    aren't persisted with the token bundle (they live in settings), so
    they're injected here at reconstruction time."""
    expiry = None
    if bundle.get("expires_at"):
        try:
            expiry = datetime.fromisoformat(bundle["expires_at"]).replace(tzinfo=None)
        except ValueError:
            # google-auth wants a naive datetime; if the stored value is
            # malformed treat it as expired so the refresh path kicks in.
            expiry = datetime.utcnow() - timedelta(minutes=1)

    creds = Credentials(
        token=bundle.get("access_token"),
        refresh_token=bundle.get("refresh_token"),
        token_uri=bundle.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=client_id,
        client_secret=client_secret,
        scopes=bundle.get("scopes") or YOUTUBE_SCOPES,
    )
    creds.expiry = expiry
    return creds


def _video_item_to_summary(item: dict[str, Any]) -> VideoSummary:
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    status = item.get("status", {})
    content = item.get("contentDetails", {})
    thumbnails = snippet.get("thumbnails", {})
    # YouTube returns thumbnails at multiple resolutions; pick the
    # largest available so the UI doesn't have to do the picking.
    thumb_url = (
        (thumbnails.get("maxres") or thumbnails.get("high") or
         thumbnails.get("medium") or thumbnails.get("default") or {}).get("url", "")
    )
    return VideoSummary(
        video_id=item["id"],
        title=snippet.get("title", ""),
        description=snippet.get("description", ""),
        thumbnail_url=thumb_url,
        published_at=_parse_published_at(snippet.get("publishedAt")),
        duration=content.get("duration", ""),
        privacy_status=status.get("privacyStatus", "private"),
        view_count=int(stats.get("viewCount", 0)),
        like_count=int(stats.get("likeCount", 0)),
        comment_count=int(stats.get("commentCount", 0)),
        tags=snippet.get("tags") or [],
        category_id=snippet.get("categoryId", ""),
    )


def _parse_published_at(value: str | None) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _format_http_error(exc: HttpError) -> str:
    """Pull the YouTube-side error message out of the binary content
    payload. Surfacing this is essential for diagnosing quota-exhaustion
    + permission errors without server-side log diving."""
    try:
        import json as _json
        payload = _json.loads(exc.content.decode("utf-8"))
        return payload.get("error", {}).get("message") or str(exc)
    except Exception:
        return str(exc)


def _run_sync(awaitable):
    """Drive a seed-provider coroutine to completion from a sync caller.

    The settings/calendar OAuth routes are sync FastAPI handlers (run in
    a threadpool with no running event loop), so ``asyncio.run`` is safe
    and the simplest bridge to the async seed ``GoogleProvider``.
    """
    import asyncio

    return asyncio.run(awaitable)


def _tokenset_to_bundle(token_set) -> dict[str, Any]:
    """Map a seed ``oauth.TokenSet`` to the legacy YouTube bundle dict.

    Identical shape to :func:`_credentials_to_bundle` so the Phase-5
    googleapiclient API layer + the credential store + the bundle-shape
    tests consume it without change.
    """
    expires_at = token_set.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return {
        "access_token": token_set.access_token,
        "refresh_token": token_set.refresh_token,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": list(token_set.scope or YOUTUBE_SCOPES),
    }
