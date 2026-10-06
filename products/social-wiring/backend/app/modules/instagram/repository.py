"""Supabase IO for the Instagram insights module (``208_instagram_insights.sql``).

Every read filters ``org_id`` AND ``account_id`` explicitly — the client is the
service-role admin client (RLS bypassed), so the filters ARE the tenant
boundary (same defence-in-depth as ``IntegrationAccountService``).

Typed vs jsonb split for metrics: the columns in ``MEDIA_TYPED_METRICS`` /
``PROFILE_TYPED_METRICS`` are first-class (indexable, cheap to chart); every
other metric lands in ``extra_metrics``. ``row_metrics`` folds them back into
one ``{key: value|None}`` map for the API.
"""
from __future__ import annotations

import base64
import binascii
import logging
from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"
INSTAGRAM_PROVIDER = "instagram"

MEDIA_TYPED_METRICS: tuple[str, ...] = (
    "views",
    "reach",
    "likes",
    "comments",
    "shares",
    "saved",
    "total_interactions",
    "follows",
    "profile_visits",
    "ig_reels_avg_watch_time",
    "ig_reels_video_view_total_time",
)
PROFILE_TYPED_METRICS: tuple[str, ...] = (
    "reach",
    "views",
    "accounts_engaged",
    "total_interactions",
    "likes",
    "comments",
    "shares",
    "saves",
)
PROFILE_FIELD_COLUMNS: tuple[str, ...] = ("followers_count", "follows_count", "media_count")

_MEDIA_COLUMNS = (
    "ig_media_id, media_type, media_product_type, caption, permalink, thumbnail_url, "
    "media_url, published_at, like_count, comments_count, is_shared_to_feed, "
    "latest_metrics, latest_snapshot_date, synced_at"
)


class InvalidCursor(ValueError):
    """The media-list cursor is not one this API issued."""


# ─── value helpers ───────────────────────────────────────────────────────
def utc_iso(value: datetime) -> str:
    """Canonical UTC ISO string — the ONE format written to and compared on
    ``published_at`` (keyset cursors depend on a stable representation)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def as_bigint(value: Any) -> Optional[int]:
    """A metric bound for a BIGINT column: numbers round to int, ``None``
    stays ``None`` (never 0)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(round(value))
    return None


def split_metrics(
    values: dict[str, Any], typed: Iterable[str]
) -> tuple[dict[str, Optional[int]], dict[str, Any]]:
    typed_set = set(typed)
    typed_out = {k: as_bigint(values.get(k)) for k in typed_set}
    extra = {k: v for k, v in values.items() if k not in typed_set}
    return typed_out, extra


def row_metrics(row: dict[str, Any], typed: Iterable[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    extra = row.get("extra_metrics") or {}
    if isinstance(extra, dict):
        out.update(extra)
    for k in typed:
        out[k] = row.get(k)
    return out


def encode_cursor(published_at: str, ig_media_id: str) -> str:
    raw = f"{published_at}|{ig_media_id}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        published_at, ig_media_id = raw.split("|", 1)
        parsed = datetime.fromisoformat(published_at)
    except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise InvalidCursor(f"invalid cursor: {cursor!r}") from exc
    if not ig_media_id:
        raise InvalidCursor(f"invalid cursor: {cursor!r}")
    return utc_iso(parsed), ig_media_id


# ─── repository ──────────────────────────────────────────────────────────
class IgInsightsRepository:
    """Thin, explicit PostgREST access for the module. ``client`` is a
    service-role Supabase client (``get_admin_client()``)."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def _t(self, name: str):
        return self._client.schema(_SCHEMA).table(name)

    @property
    def client(self) -> Any:
        return self._client

    # integration_accounts ------------------------------------------------
    def get_account(self, account_id: UUID, org_id: UUID) -> Optional[dict[str, Any]]:
        resp = (
            self._t("integration_accounts")
            .select(
                "id, org_id, provider, status, marca_id, account_label, metadata, "
                "channel_info, last_synced_at"
            )
            .eq("id", str(account_id))
            .eq("org_id", str(org_id))
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return rows[0] if rows else None

    def list_validated_accounts(self) -> list[dict[str, Any]]:
        """Every validated Instagram-Login connection across orgs (the daily
        job's work list — service role, so no org filter at this level)."""
        resp = (
            self._t("integration_accounts")
            .select("id, org_id, metadata")
            .eq("provider", INSTAGRAM_PROVIDER)
            .eq("status", "validated")
            .execute()
        )
        return list(resp.data or [])

    def update_account_sync(
        self,
        account_id: UUID,
        org_id: UUID,
        *,
        channel_info: dict[str, Any],
        last_synced_at: datetime,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        (
            self._t("integration_accounts")
            .update(
                {
                    "channel_info": channel_info,
                    "last_synced_at": utc_iso(last_synced_at),
                    "updated_at": now,
                }
            )
            .eq("id", str(account_id))
            .eq("org_id", str(org_id))
            .execute()
        )

    # writes --------------------------------------------------------------
    def upsert_catalog(self, rows: list[dict[str, Any]]) -> None:
        if rows:
            self._t("ig_media").upsert(rows, on_conflict="account_id,ig_media_id").execute()

    def upsert_latest(self, rows: list[dict[str, Any]]) -> None:
        """``latest_metrics``/``latest_snapshot_date`` only — a separate,
        uniform-key batch so a media whose insights failed today keeps its
        previous ``latest_metrics`` instead of being nulled."""
        if rows:
            self._t("ig_media").upsert(rows, on_conflict="account_id,ig_media_id").execute()

    def upsert_media_snapshots(self, rows: list[dict[str, Any]]) -> None:
        if rows:
            (
                self._t("ig_media_snapshots")
                .upsert(rows, on_conflict="account_id,ig_media_id,snapshot_date")
                .execute()
            )

    def upsert_profile_snapshot(self, row: dict[str, Any]) -> None:
        (
            self._t("ig_profile_snapshots")
            .upsert(row, on_conflict="account_id,snapshot_date")
            .execute()
        )

    # reads ---------------------------------------------------------------
    def list_media_page(
        self,
        account_id: UUID,
        org_id: UUID,
        *,
        limit: int,
        cursor: Optional[str] = None,
    ) -> tuple[list[dict[str, Any]], Optional[str]]:
        """One grid page ordered ``published_at DESC, ig_media_id DESC``
        (keyset — stable under concurrent inserts, unlike OFFSET)."""
        q = (
            self._t("ig_media")
            .select(_MEDIA_COLUMNS)
            .eq("account_id", str(account_id))
            .eq("org_id", str(org_id))
        )
        if cursor:
            ts, mid = decode_cursor(cursor)
            q = q.or_(
                f'published_at.lt."{ts}",'
                f'and(published_at.eq."{ts}",ig_media_id.lt."{mid}")'
            )
        resp = (
            q.order("published_at", desc=True)
            .order("ig_media_id", desc=True)
            .limit(limit + 1)
            .execute()
        )
        rows = list(resp.data or [])
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            last = rows[-1]
            next_cursor = encode_cursor(
                utc_iso(datetime.fromisoformat(str(last["published_at"]).replace("Z", "+00:00"))),
                str(last["ig_media_id"]),
            )
        return rows, next_cursor

    def get_media(
        self, account_id: UUID, org_id: UUID, ig_media_id: str
    ) -> Optional[dict[str, Any]]:
        resp = (
            self._t("ig_media")
            .select(_MEDIA_COLUMNS)
            .eq("account_id", str(account_id))
            .eq("org_id", str(org_id))
            .eq("ig_media_id", ig_media_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return rows[0] if rows else None

    def media_history(
        self,
        account_id: UUID,
        org_id: UUID,
        ig_media_id: str,
        *,
        since: date,
    ) -> list[dict[str, Any]]:
        resp = (
            self._t("ig_media_snapshots")
            .select(
                "snapshot_date, " + ", ".join(MEDIA_TYPED_METRICS)
                + ", extra_metrics, unsupported_metrics"
            )
            .eq("account_id", str(account_id))
            .eq("org_id", str(org_id))
            .eq("ig_media_id", ig_media_id)
            .gte("snapshot_date", since.isoformat())
            .order("snapshot_date", desc=False)
            .execute()
        )
        return list(resp.data or [])

    def profile_trend(
        self, account_id: UUID, org_id: UUID, *, since: date
    ) -> list[dict[str, Any]]:
        resp = (
            self._t("ig_profile_snapshots")
            .select(
                "snapshot_date, " + ", ".join(PROFILE_FIELD_COLUMNS + PROFILE_TYPED_METRICS)
                + ", extra_metrics, unsupported_metrics"
            )
            .eq("account_id", str(account_id))
            .eq("org_id", str(org_id))
            .gte("snapshot_date", since.isoformat())
            .order("snapshot_date", desc=False)
            .execute()
        )
        return list(resp.data or [])


__all__ = [
    "IgInsightsRepository",
    "InvalidCursor",
    "INSTAGRAM_PROVIDER",
    "MEDIA_TYPED_METRICS",
    "PROFILE_TYPED_METRICS",
    "PROFILE_FIELD_COLUMNS",
    "as_bigint",
    "decode_cursor",
    "encode_cursor",
    "row_metrics",
    "split_metrics",
    "utc_iso",
]
