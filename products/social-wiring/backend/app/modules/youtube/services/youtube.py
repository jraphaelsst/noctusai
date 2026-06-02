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
from googleapiclient.errors import HttpError

from noctusai_lib.integrations.youtube import (
    VideoFull,
    YoutubeClient,
    make_youtube_client,
)
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
    """Subset of channels.list response that the UI cares about.

    ``thumbnail_url`` is populated when the seed YoutubeClient exposes it.
    The seed ``ChannelInfo`` type (noctusai_lib.integrations.youtube.types)
    does NOT include a thumbnail field as of this writing — the field is left
    empty string here to keep the product shape forward-compatible. When the
    seed lifts ``thumbnail_url`` into ``ChannelInfo``, the mapping in
    ``get_channel_info`` below auto-picks it up via ``getattr(..., '')``.
    """

    channel_id: str
    title: str
    subscriber_count: int
    video_count: int
    view_count: int
    thumbnail_url: str = ""


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
    (the seed-consume seam) in PKCE mode (`use_pkce=True`). The seed
    provider generates a fresh RFC 7636 verifier per call, embeds the
    SHA256 challenge in the consent URL as
    ``code_challenge`` + ``code_challenge_method=S256``, and returns the
    verifier on ``AuthorizationURL.code_verifier`` for the caller to
    persist (settings_router stores it in Redis keyed by ``state``).
    Methodology: ``KB § PATTERNS/absorbed-product-seed-shape-seam.md`` —
    the N=3 worked instance restoring social-wiring's pre-absorption
    PKCE through the seed seam without forking.

    Returns ``(auth_url, code_verifier)``; the verifier MUST be
    persisted and replayed at ``exchange_code(code=..., code_verifier=...)``.

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
        return auth_url.url, auth_url.code_verifier or ""
    def exchange_code(self, *, code: str, code_verifier: str | None = None) -> dict[str, Any]:
        """Exchange the OAuth callback's ``code`` for a token bundle.

    Lifecycle delegated to the seed ``GoogleProvider`` in PKCE mode.
    ``code_verifier`` is the value persisted from ``get_auth_url``
    (settings_router replays it from Redis keyed by ``state``). The
    seed provider includes it in the token POST per RFC 7636 §4.5.
    Missing verifier → seed raises ``ValueError`` (loud, before any
    network hop); mismatched verifier → Google returns 400 invalid_grant.

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
                code=code,
                state="",
                redirect_uri=self._redirect_uri,
                code_verifier=code_verifier,
            )
        )
        return _tokenset_to_bundle(token_set)
    def _oauth_provider(self) -> GoogleProvider:
        """Construct the seed Google OAuth provider for this service.

    Separated so tests can inject a Fake via the seed factory.
    ``use_pkce=True`` opts into the seed's PKCE seam (Phase 3c) —
    restoring social-wiring's pre-absorption PKCE without forking.
    The provider owns the authorize/exchange/refresh/revoke
    lifecycle; the googleapiclient API-layer machinery
    (``_fresh_credentials`` / ``_build_service``) is unchanged
    (Phase-5 scope).
    """
        return GoogleProvider(
            client_id=self._client_id,
            client_secret=self._client_secret,
            use_pkce=True,
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

        Quota cost: 1 unit. Delegates to the seed
        ``YoutubeClient.get_channel_info_mine`` (Phase 6a-youtube of
        ``social-wiring-google-seed-consume`` →
        ``seed-youtube-read-projection-enrichment``) — the seed Real
        adapter drives ``channels.list?mine=True&part=snippet,statistics``.
        Translates the seed ``ChannelInfo`` (engagement-counters
        projection) to the product's identically-named view-model.
        """
        creds = self._fresh_credentials(org_id)
        client = self._youtube_client(creds)

        try:
            info = _run_sync(client.get_channel_info_mine())
        except HttpError as exc:
            raise YouTubeServiceError(_format_http_error(exc)) from exc
        except ValueError as exc:
            # Seed surfaces the "no OAuth-associated YT channel" branch
            # as ValueError; translate to the product-level error.
            raise YouTubeServiceError(
                "OAuth succeeded but no channel is associated with this Google "
                "account. Make sure you authorised with an account that owns "
                "a YouTube channel."
            ) from exc

        return ChannelInfo(
            channel_id=info.channel_id,
            title=info.title,
            subscriber_count=info.subscriber_count,
            video_count=info.video_count,
            view_count=info.view_count,
            # seed ChannelInfo does not expose thumbnail_url yet; default to
            # empty string. When the seed adds it, getattr picks it up
            # automatically without a product-side change.
            thumbnail_url=getattr(info, "thumbnail_url", ""),
        )

    def list_all_videos(
        self,
        *,
        org_id: UUID,
        account_id: UUID | None = None,
        page_token: str | None = None,
        max_results: int = 50,
    ) -> tuple[list[VideoSummary], str | None]:
        """List videos owned by the connected channel + their stats.

        Quota cost: ~3 units / page (uploads-playlist path — includes
        private + unlisted). Returns (videos, next_page_token); next is None
        on the last page. Delegates to the seed
        ``YoutubeClient.list_owned_videos_via_uploads`` (Phase 3 fix — replaces
        the old ``list_owned_videos`` / search.list?forMine path that returned
        ZERO for private libraries).

        ``account_id`` (optional) pins to a specific channel; ``None`` resolves
        the org's default account.
        """
        creds = self._fresh_credentials(org_id)
        client = self._youtube_client(creds)

        try:
            result = _run_sync(
                client.list_owned_videos_via_uploads(
                    page_token=page_token, page_size=max_results
                )
            )
        except HttpError as exc:
            raise YouTubeServiceError(_format_http_error(exc)) from exc

        return (
            [_video_full_to_summary(v) for v in result.items],
            result.next_page_token,
        )

    def list_all_videos_full(
        self,
        *,
        org_id: UUID,
        account_id: UUID | None = None,
        page_token: str | None = None,
        page_size: int = 50,
    ) -> tuple[list[VideoFull], str | None]:
        """List ALL owned videos with the full VideoFull projection.

        Quota cost: ~3 units / page (uploads-playlist path — includes
        private + unlisted). Returns (videos, next_page_token); next is None
        on the last page. Used by SnapshotService for shorts classification +
        catalog upserts.

        ``account_id`` (optional) pins to a specific channel; ``None`` resolves
        the org's default account.
        """
        creds = self._fresh_credentials(org_id)
        client = self._youtube_client(creds)

        try:
            result = _run_sync(
                client.list_owned_videos_via_uploads(
                    page_token=page_token, page_size=page_size
                )
            )
        except HttpError as exc:
            raise YouTubeServiceError(_format_http_error(exc)) from exc

        return result.items, result.next_page_token

    def get_video_stats(
        self, *, org_id: UUID, video_ids: list[str]
    ) -> dict[str, dict[str, int]]:
        """Refresh metrics for an explicit set of video IDs.

        Quota cost: 1 unit per id (single-id ``videos.list``). Delegates
        to the seed ``YoutubeClient.get_video_full`` per id; the rich
        projection carries ``view_count`` + ``like_count`` +
        ``comment_count`` so the dict-shape contract is preserved
        exactly. Videos that don't resolve (deleted / unknown id) are
        omitted — matches the prior batched-call behavior (YT just
        doesn't return an item for missing ids).

        **Quota note** — the prior implementation batched up to 50 ids
        into a single ``videos.list`` (1 unit total). The seed
        ``get_video_full`` is single-id (1 unit each). For large
        refresh sets this is more expensive; a future seed lift could
        add a batch ``get_videos_full(ids)`` — tracked as a
        follow-up (this path is currently dead code in the consumer;
        the rich-projection refresh is performed by
        ``list_all_videos``).
        """
        if not video_ids:
            return {}

        creds = self._fresh_credentials(org_id)
        client = self._youtube_client(creds)
        result: dict[str, dict[str, int]] = {}

        try:
            for vid in video_ids:
                v = _run_sync(client.get_video_full(vid))
                if v is None:
                    continue
                result[v.id] = {
                    "view_count": v.view_count,
                    "like_count": v.like_count,
                    "comment_count": v.comment_count,
                }
        except HttpError as exc:
            raise YouTubeServiceError(_format_http_error(exc)) from exc
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

        Delegates to the seed
        ``noctusai_lib.integrations.youtube.YoutubeClient.set_thumbnail``
        (Phase 4 of social-wiring-google-seed-consume; the formalized
        seed seam takes ``thumbnail_path: str`` per its Protocol, so
        the product writes the in-memory bytes to a NamedTemporaryFile
        and hands the path to the seed — the seed Real adapter then
        streams it via ``MediaFileUpload``).
        """
        import tempfile

        creds = self._fresh_credentials(org_id)
        client = self._youtube_client(creds)

        suffix = _mime_to_suffix(mime_type)
        # delete=False so we control cleanup explicitly — the seed Real
        # adapter reads the file via MediaFileUpload (non-resumable) and
        # the read happens inside `_run_sync` below.
        with tempfile.NamedTemporaryFile(
            suffix=suffix, delete=False
        ) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        try:
            _run_sync(
                client.set_thumbnail(
                    video_id=video_id,
                    thumbnail_path=tmp_path,
                    mime_type=mime_type,
                )
            )
        except HttpError as exc:
            raise YouTubeServiceError(_format_http_error(exc)) from exc
        finally:
            import os
            try:
                os.unlink(tmp_path)
            except OSError:
                logger.warning(
                    "set_thumbnail: failed to unlink temp file %s — leaving for OS sweep",
                    tmp_path,
                )

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

        Delegates to the seed
        ``noctusai_lib.integrations.youtube.YoutubeClient.get_processing_status``
        (Phase 4 of social-wiring-google-seed-consume). The seed returns
        a :class:`ProcessingStatus` dataclass; this wrapper translates
        it to the dict shape the upload pipeline already consumes
        (back-compat with ``_wait_for_yt_processing``).
        """
        creds = self._fresh_credentials(org_id)
        client = self._youtube_client(creds)

        try:
            status = _run_sync(client.get_processing_status(video_id))
        except HttpError as exc:
            raise YouTubeServiceError(_format_http_error(exc)) from exc
        except ValueError as exc:
            # Seed surfaces the "no items returned" branch as ValueError
            # (video deleted / never finished uploading). Translate to
            # the product-level error shape so callers branch the same way.
            raise YouTubeServiceError(str(exc)) from exc

        return {
            "upload_status": str(status.upload_status),
            "processing_status": str(status.processing_status),
            "privacy_status": str(status.privacy_status),
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

        Quota cost: 1600 units (the heaviest call in the API; corrected
        from prior docstring's "100").

        Delegates to the seed
        ``noctusai_lib.integrations.youtube.YoutubeClient.upload_video``
        (Phase 4 of social-wiring-google-seed-consume). The seed drives
        the resumable transfer (``MediaFileUpload(resumable=True)`` +
        ``next_chunk()`` loop) — see
        ``noctusai_lib.integrations.youtube.real.RealYoutubeClient.upload_video``.

        **Known deviation from pre-refactor behavior** — the per-chunk
        retry loop (``_resumable_upload_with_chunk_retry``, S4-2) is
        NOT yet in the seed: a transient mid-stream failure now raises
        instead of resuming from the last successful chunk. Phase-4
        scope was the 2 named gaps + the call-replacement; lifting the
        chunked-retry primitive into the seed is a follow-up
        (see findings.md → seed-upload-chunk-retry). The outer
        ``_retry_with_backoff`` policy in the upload pipeline still
        catches quota-exceeded + non-transient errors uniformly.
        """
        if privacy_status not in ("public", "unlisted", "private"):
            raise YouTubeServiceError(
                f"privacy_status must be public/unlisted/private, got {privacy_status!r}"
            )

        creds = self._fresh_credentials(org_id)
        client = self._youtube_client(creds)

        try:
            upload = _run_sync(
                client.upload_video(
                    file_path=file_path,
                    title=title,
                    description=description,
                    tags=tags or None,
                    privacy_status=privacy_status,  # type: ignore[arg-type]
                    category_id=category_id,
                )
            )
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
            raise YouTubeServiceError(_format_http_error(exc)) from exc

        return upload.video_id

    def update_video_metadata(
        self,
        *,
        org_id: UUID,
        video_id: str,
        title: str | None = None,
        description: str | None = None,
        privacy_status: str | None = None,
    ) -> "VideoFull":
        """Update title, description, and/or privacy for an existing video.

        Write-through to the YouTube Data API via ``videos.update``.

        **Quota cost: ~50 units/update** — the update itself costs 50 units.
        When the ``snippet`` part is needed (title or description change),
        the seed adapter internally fetches the existing snippet first (1
        unit) before the update write (49 units) to satisfy YouTube's
        requirement that ``snippet.title`` + ``snippet.categoryId`` are
        always present even when only changing the description.

        Delegates to ``YoutubeClient.update_video`` (Phase 7 of
        social-wiring video CRUD — feat/yt-card-crud).

        Returns:
            The updated :class:`VideoFull` re-fetched from the YouTube API
            after the write so the returned state is authoritative.

        Raises:
            YouTubeNotConnected: when no credentials are stored for the org.
            YouTubeServiceError: on any YouTube API error or missing video.
        """
        if privacy_status is not None and privacy_status not in ("public", "unlisted", "private"):
            raise YouTubeServiceError(
                f"privacy_status must be public/unlisted/private, got {privacy_status!r}"
            )

        creds = self._fresh_credentials(org_id)
        client = self._youtube_client(creds)

        try:
            updated = _run_sync(
                client.update_video(
                    video_id,
                    title=title,
                    description=description,
                    privacy_status=privacy_status,
                )
            )
        except HttpError as exc:
            raise YouTubeServiceError(_format_http_error(exc)) from exc
        except ValueError as exc:
            raise YouTubeServiceError(str(exc)) from exc

        return updated

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

    def _youtube_client(self, creds: Credentials) -> YoutubeClient:
        """Build a seed-backed YouTube client for every API method.

        The product feeds ``credentials=creds`` into the seed factory;
        the seed ``RealYoutubeClient`` then drives
        ``googleapiclient.discovery.build`` itself. This is the
        canonical seam — every YT API method routes through it. Phase
        4 lifted ``set_thumbnail`` / ``get_processing_status`` /
        ``upload_video``; Phase 6a-youtube
        (``seed-youtube-read-projection-enrichment``) lifted the
        remaining 3 read methods (``get_channel_info`` /
        ``list_all_videos`` / ``get_video_stats``) via the new
        ``VideoFull`` / ``ChannelInfo`` projection-enrichment surface
        (``get_channel_info_mine`` / ``list_owned_videos`` /
        ``get_video_full``). The product's ``_build_service`` is gone;
        the YouTube API surface lives entirely at the seed level.
        """
        return make_youtube_client(oauth_credentials=creds)


# ─── Module-level helpers (testable in isolation) ──────────────────────
def _mime_to_suffix(mime_type: str) -> str:
    """Map a thumbnail MIME type to a tempfile suffix.

    The seed ``set_thumbnail`` takes a file path and passes the MIME
    explicitly to ``MediaFileUpload(mimetype=...)`` — the suffix here
    is just for human-debuggability of the tempfile name + matches the
    MIME so a defensive consumer reading the path can pick the right
    decoder. Defaults to ``.jpg`` for the JPEG case + falls back to
    ``.bin`` for anything else.
    """
    suffix_map = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/bmp": ".bmp",
    }
    return suffix_map.get(mime_type.lower(), ".bin")


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


def _video_full_to_summary(v: VideoFull) -> VideoSummary:
    """Translate the seed rich projection to the product view-model.

    The two shapes were deliberately aligned at Phase 6a-youtube — the
    seed ``VideoFull`` carries every field ``VideoSummary`` needs, so
    this mapping is a near-1:1 translation. ``duration`` is the raw
    ISO-8601 echo (``duration_iso`` on the seed side) — historical
    field-name carried for back-compat with the UI / SQLite schema.
    ``tags`` re-materialises as a list (the seed stores a frozen tuple
    to satisfy the ``dataclass(frozen=True)`` contract; the UI / DB
    layer expects a list)."""
    return VideoSummary(
        video_id=v.id,
        title=v.title,
        description=v.description,
        thumbnail_url=v.thumbnail_url,
        published_at=v.published_at,
        duration=v.duration_iso,
        privacy_status=str(v.privacy_status),
        view_count=v.view_count,
        like_count=v.like_count,
        comment_count=v.comment_count,
        tags=list(v.tags),
        category_id=v.category_id,
    )


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
