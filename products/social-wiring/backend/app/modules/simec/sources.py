"""Where SIMEC readings come from — one source per PLATFORM (Instagram and
TikTok never share a method, per SIMEC's separation rule).

``SimecMetricsSource`` is the seam. Two Instagram implementations share ONE
row→reading builder (``readings_from_ig_rows``), so the Fake exercises the
exact window-picking and metric mapping the Real one does:

* ``InstagramSnapshotSource`` (Real) — reads OUR stored catalog + daily
  snapshots written by ``app/modules/instagram`` (no Graph call here).
* ``FakeInstagramSource`` — an in-memory catalog (``demo_instagram_rows``
  by default). No org has an Instagram account connected yet (DECISIONS.md
  2026-10-19, P0 finding), so this is what dev/demo runs on.

``make_metrics_source`` picks one by name (``settings.simec_metrics_source``);
every readout records ``source.name`` so a fake readout is never mistaken
for real data.

Which day's snapshot represents a window is the seed's
``select_window_observation`` (earliest snapshot inside the window's
configured tolerance; the latest for an open window) — the tolerances are
config, never code.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Iterable, Optional, Protocol, runtime_checkable
from uuid import UUID

from noctusai_lib.domain.content_performance import (
    PerformanceConfig,
    Reading,
    select_window_observation,
)
from noctusai_lib.integrations.meta import effective_product_type

from app.modules.instagram.repository import MEDIA_TYPED_METRICS, IgInsightsRepository, row_metrics
from app.modules.instagram.sync_service import TZ_BR

#: Platform field → SIMEC metric key, with the unit conversion the platform
#: needs. This is ADAPTER knowledge (what Meta names a field and in which
#: unit it answers), not methodology — no threshold or window lives here.
#: NOC-REMEDIATE[simec-ig-units]: `ig_reels_avg_watch_time` is stored in ms
#: (migration 208 comment) and Meta documents `reels_skip_rate` as a
#: percentage; confirm both units against the first connected account
#: (Mônica's, P0) before the pilot readout is trusted — 2026-10-19
IG_METRIC_MAP: dict[str, tuple[str, float]] = {
    "views": ("views", 1.0),
    "reach": ("reach", 1.0),
    "likes": ("likes", 1.0),
    "comments": ("comments", 1.0),
    "shares": ("shares", 1.0),
    "saves": ("saved", 1.0),
    "follows": ("follows", 1.0),
    "avg_watch_time_s": ("ig_reels_avg_watch_time", 0.001),
    "skip_rate": ("reels_skip_rate", 0.01),
}

IG_SOURCE_LABEL = "Instagram Insights (snapshot diário)"


@runtime_checkable
class SimecMetricsSource(Protocol):
    """Readings for one account of ONE platform."""

    platform: str
    name: str

    def collect(
        self,
        *,
        org_id: UUID,
        account_id: UUID,
        published_from: date,
        published_to: date,
        observed_until: date,
        config: PerformanceConfig,
    ) -> list[Reading]:
        """Every reading (content × configured window) for content published
        in ``[published_from, published_to]``, observed no later than
        ``observed_until``. A window with no snapshot inside its tolerance
        yields no reading (never an estimate)."""
        ...


# ─── shared Instagram row → reading builder ──────────────────────────────
def ig_format(media_product_type: Optional[str], media_type: Optional[str]) -> str:
    """The workbook's Formato vocabulary (Reel / Carrossel / Foto / Story / Outro)."""
    ptype = effective_product_type(media_product_type, media_type)
    mt = (media_type or "").upper()
    if ptype == "REELS":
        return "Reel"
    if ptype == "STORY":
        return "Story"
    if mt == "CAROUSEL_ALBUM":
        return "Carrossel"
    if mt == "IMAGE":
        return "Foto"
    return "Outro"


def _published_on(value: Any) -> date:
    dt_ = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt_.tzinfo is None:
        dt_ = dt_.replace(tzinfo=timezone.utc)
    return dt_.astimezone(TZ_BR).date()


def _as_date(value: Any) -> date:
    return value if isinstance(value, date) and not isinstance(value, datetime) else date.fromisoformat(str(value)[:10])


def _topic(caption: Optional[str]) -> Optional[str]:
    if not caption:
        return None
    first = caption.strip().splitlines()[0].strip() if caption.strip() else ""
    return (first[:120] or None)


def _metric_values(snapshot: dict[str, Any]) -> dict[str, Optional[float]]:
    raw = row_metrics(snapshot, MEDIA_TYPED_METRICS)
    out: dict[str, Optional[float]] = {}
    for key, (ig_key, scale) in IG_METRIC_MAP.items():
        v = raw.get(ig_key)
        out[key] = (v * scale) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    return out


def readings_from_ig_rows(
    media_rows: Iterable[dict[str, Any]],
    snapshot_rows: Iterable[dict[str, Any]],
    config: PerformanceConfig,
    *,
    source_label: str = IG_SOURCE_LABEL,
) -> list[Reading]:
    by_media: dict[str, list[tuple[date, dict[str, Any]]]] = {}
    for s in snapshot_rows:
        by_media.setdefault(str(s["ig_media_id"]), []).append((_as_date(s["snapshot_date"]), s))
    readings: list[Reading] = []
    for m in sorted(media_rows, key=lambda r: (str(r["published_at"]), str(r["ig_media_id"]))):
        mid = str(m["ig_media_id"])
        published_on = _published_on(m["published_at"])
        observations = by_media.get(mid, [])
        for window in config.active_windows:
            picked = select_window_observation(published_on, observations, window.key, config)
            if picked is None:
                continue
            observed_on, snap = picked
            readings.append(Reading(
                content_id=mid,
                published_at=published_on,
                collected_at=observed_on,
                window=window.key,
                values=_metric_values(snap),
                format=ig_format(m.get("media_product_type"), m.get("media_type")),
                topic=_topic(m.get("caption")),
                source=source_label,
                source_ref={
                    "ig_media_id": mid,
                    "snapshot_date": observed_on.isoformat(),
                    "snapshot_id": snap.get("id"),
                    "permalink": m.get("permalink"),
                    "unsupported_metrics": list(snap.get("unsupported_metrics") or []),
                },
            ))
    return readings


# ─── Real ────────────────────────────────────────────────────────────────
class InstagramSnapshotSource:
    """Readings from the daily snapshots ``app/modules/instagram`` stores."""

    platform = "instagram"
    name = "instagram_snapshots"

    def __init__(self, repo: IgInsightsRepository) -> None:
        self._repo = repo

    def collect(self, *, org_id, account_id, published_from, published_to, observed_until, config):
        since = datetime.combine(published_from, time.min, tzinfo=TZ_BR)
        until = datetime.combine(published_to, time.max, tzinfo=TZ_BR)
        media = self._repo.list_media_published_between(account_id, org_id, since=since, until=until)
        if not media:
            return []
        snaps = self._repo.media_snapshots_for(
            account_id, org_id, [str(m["ig_media_id"]) for m in media],
            since=published_from, until=observed_until,
        )
        return readings_from_ig_rows(media, snaps, config)


# ─── Fake ────────────────────────────────────────────────────────────────
class FakeInstagramSource:
    """In-memory Instagram catalog: ``{account_id: (media_rows, snapshot_rows)}``.
    ``default`` serves any account not in ``catalogs`` (the demo data)."""

    platform = "instagram"
    name = "fake"

    def __init__(
        self,
        catalogs: Optional[dict[str, tuple[list[dict], list[dict]]]] = None,
        default: Optional[Callable[[date], tuple[list[dict], list[dict]]]] = None,
    ) -> None:
        self._catalogs = {str(k): v for k, v in (catalogs or {}).items()}
        self._default = default
        self.calls: list[dict[str, Any]] = []

    def collect(self, *, org_id, account_id, published_from, published_to, observed_until, config):
        self.calls.append({"org_id": str(org_id), "account_id": str(account_id),
                           "published_from": published_from, "published_to": published_to,
                           "observed_until": observed_until})
        if str(account_id) in self._catalogs:
            media, snaps = self._catalogs[str(account_id)]
        elif self._default is not None:
            media, snaps = self._default(observed_until)
        else:
            return []
        media = [m for m in media if published_from <= _published_on(m["published_at"]) <= published_to]
        snaps = [s for s in snaps if _as_date(s["snapshot_date"]) <= observed_until]
        return readings_from_ig_rows(media, snaps, config, source_label="Fake (dados de demonstração)")


def demo_instagram_rows(today: date, *, days: int = 120, every: int = 3) -> tuple[list[dict], list[dict]]:
    """A deterministic demo catalog: one post every ``every`` days over the
    last ``days`` days, rotating Reel/Carrossel/Foto, with a daily snapshot
    whose counts grow with age. Reels lack ``follows`` (as on Instagram);
    one post in five lacks ``reach`` that day (a gap, never a 0)."""
    kinds = [("REELS", "VIDEO"), ("FEED", "CAROUSEL_ALBUM"), ("FEED", "IMAGE")]
    media: list[dict] = []
    snaps: list[dict] = []
    for n, offset in enumerate(range(days, 0, -every)):
        pub = today - timedelta(days=offset)
        mpt, mt = kinds[n % 3]
        mid = f"demo-{n:03d}"
        media.append({
            "ig_media_id": mid, "media_product_type": mpt, "media_type": mt,
            "caption": f"Post de demonstração {n}\nlegenda", "permalink": None,
            "published_at": datetime.combine(pub, time(12), tzinfo=TZ_BR).isoformat(),
        })
        base = 400 + 37 * (n % 7)
        for age in range(0, min(offset, 40) + 1):
            grow = 1 + min(age, 30) / 10
            reach = int(base * grow)
            snaps.append({
                "id": f"{mid}-{age}", "ig_media_id": mid,
                "snapshot_date": (pub + timedelta(days=age)).isoformat(),
                "views": int(reach * 1.4), "reach": None if (n % 5 == 4 and age == 8) else reach,
                "likes": int(reach * 0.06), "comments": int(reach * 0.006),
                "shares": int(reach * 0.01) + n % 3, "saved": int(reach * 0.012),
                "follows": None if mpt == "REELS" else int(reach * 0.002),
                "ig_reels_avg_watch_time": 9000 + 150 * (n % 9) if mpt == "REELS" else None,
                "extra_metrics": {"reels_skip_rate": 38 + n % 11} if mpt == "REELS" else {},
                "unsupported_metrics": [],
            })
    return media, snaps


# ─── factory ─────────────────────────────────────────────────────────────
SOURCE_KINDS = ("instagram", "fake")


def make_metrics_source(platform: str, kind: str, *, ig_repo: Optional[IgInsightsRepository] = None) -> SimecMetricsSource:
    """``kind`` ∈ ``SOURCE_KINDS``; anything else raises (no silent fallback)."""
    if platform != "instagram":
        raise ValueError(f"SIMEC has no metrics source for platform {platform!r} yet (TikTok is parked, owner 2026-10-16)")
    if kind == "instagram":
        if ig_repo is None:
            raise ValueError("the instagram source needs an IgInsightsRepository")
        return InstagramSnapshotSource(ig_repo)
    if kind == "fake":
        return FakeInstagramSource(default=demo_instagram_rows)
    raise ValueError(f"unknown SIMEC metrics source {kind!r}; expected one of {SOURCE_KINDS}")


__all__ = [
    "FakeInstagramSource",
    "IG_METRIC_MAP",
    "InstagramSnapshotSource",
    "SOURCE_KINDS",
    "SimecMetricsSource",
    "demo_instagram_rows",
    "ig_format",
    "make_metrics_source",
    "readings_from_ig_rows",
]
