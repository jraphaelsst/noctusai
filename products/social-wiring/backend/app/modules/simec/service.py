"""SIMEC service — config layering + readouts, computed by the seed's pure
``content_performance`` calculator over readings from a ``SimecMetricsSource``.

Config resolution (per platform): seed defaults ⊕ org layer ⊕ profile layer.
Each stored layer is a PARTIAL override with its own version; the resolved
config's version label names every layer (``instagram-defaults-1.0.0+org.v3
+perfil.v1``) and its fingerprint is stored on every readout, so a number is
always traceable to the exact settings that produced it.

The service never invents a number: it validates, delegates the arithmetic
to the seed, and persists what the seed returned.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.domain.content_performance import (
    ConfigError,
    PerformanceConfig,
    compute_readout,
    load_default_config,
    merge_overrides,
)

from app.modules.simec.repository import SimecRepository
from app.modules.simec.sources import SimecMetricsSource

#: Longest period one readout may cover — a request guard (bounds the rows a
#: single synchronous call reads), not a methodology value.
MAX_PERIOD_DAYS = 366


class SimecConfigInvalid(ValueError):
    """The requested/stored overrides do not resolve to a valid config."""


class SimecPeriodInvalid(ValueError):
    """The requested period is malformed."""


@dataclass(frozen=True)
class ResolvedConfig:
    config: PerformanceConfig
    defaults_version: str
    org_layer: Optional[dict[str, Any]]
    account_layer: Optional[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        def layer(row: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
            if row is None:
                return None
            return {"version": row["version"], "overrides": row.get("overrides") or {},
                    "updated_at": row.get("updated_at"), "updated_by": row.get("updated_by")}

        return {
            "platform": self.config.platform,
            "version": self.config.version,
            "fingerprint": self.config.fingerprint,
            "config": self.config.to_dict(),
            "layers": {
                "defaults": {"version": self.defaults_version},
                "org": layer(self.org_layer),
                "account": layer(self.account_layer),
            },
        }


def _layer(base: PerformanceConfig, row: Optional[dict[str, Any]], prefix: str) -> PerformanceConfig:
    if row is None:
        return base
    return merge_overrides(base, row.get("overrides") or {}, f"{prefix}.v{row['version']}")


class SimecService:
    def __init__(
        self,
        repo: SimecRepository,
        source: SimecMetricsSource,
        *,
        today: Callable[[], date],
    ) -> None:
        self._repo = repo
        self._source = source
        self._today = today

    @property
    def source_name(self) -> str:
        return self._source.name

    # config ----------------------------------------------------------------
    def _resolve(
        self,
        platform: str,
        org_row: Optional[dict[str, Any]],
        account_row: Optional[dict[str, Any]],
    ) -> ResolvedConfig:
        try:
            defaults = load_default_config(platform)
            cfg = _layer(_layer(defaults, org_row, "org"), account_row, "perfil")
        except ConfigError as exc:
            raise SimecConfigInvalid(str(exc)) from exc
        return ResolvedConfig(cfg, defaults.version, org_row, account_row)

    def resolve_config(
        self, org_id: UUID, platform: str, account_id: Optional[UUID] = None
    ) -> ResolvedConfig:
        org_row = self._repo.get_config_layer(org_id, platform, None)
        acc_row = self._repo.get_config_layer(org_id, platform, account_id) if account_id else None
        return self._resolve(platform, org_row, acc_row)

    def save_config(
        self,
        org_id: UUID,
        platform: str,
        account_id: Optional[UUID],
        overrides: dict[str, Any],
        *,
        user_id: Optional[str],
    ) -> ResolvedConfig:
        """Validate the NEW layer on top of the layers below it, then store
        it (version + 1, history row). Invalid → ``SimecConfigInvalid``,
        nothing written."""
        org_row = self._repo.get_config_layer(org_id, platform, None)
        if account_id is None:
            self._resolve(platform, {"overrides": overrides, "version": 0}, None)
        else:
            self._resolve(platform, org_row, {"overrides": overrides, "version": 0})
        self._repo.save_config_layer(org_id, platform, account_id, overrides, user_id=user_id)
        return self.resolve_config(org_id, platform, account_id)

    # readouts --------------------------------------------------------------
    def default_period(self, config: PerformanceConfig, cadence: str) -> tuple[date, date]:
        try:
            return config.review_period(cadence, self._today())
        except ConfigError as exc:
            raise SimecPeriodInvalid(str(exc)) from exc

    def compute(
        self,
        org_id: UUID,
        account_id: UUID,
        platform: str,
        *,
        period_start: Optional[date],
        period_end: Optional[date],
        cadence: str,
        user_id: Optional[str],
    ) -> dict[str, Any]:
        resolved = self.resolve_config(org_id, platform, account_id)
        cfg = resolved.config
        if (period_start is None) != (period_end is None):
            raise SimecPeriodInvalid("period_start and period_end go together (or both omitted)")
        if period_start is None:
            period_start, period_end = self.default_period(cfg, cadence)
        assert period_end is not None
        if period_start > period_end:
            raise SimecPeriodInvalid(f"period_start {period_start} > period_end {period_end}")
        if (period_end - period_start).days + 1 > MAX_PERIOD_DAYS:
            raise SimecPeriodInvalid(f"period longer than {MAX_PERIOD_DAYS} days")
        history_start = period_start - timedelta(days=cfg.baseline.lookback_days)
        readings = self._source.collect(
            org_id=org_id, account_id=account_id,
            published_from=history_start, published_to=period_end,
            observed_until=self._today(), config=cfg,
        )
        ro = compute_readout(readings, cfg, period_start=period_start, period_end=period_end)
        d = ro.to_dict()
        row = {
            "org_id": str(org_id), "account_id": str(account_id), "platform": platform,
            "source": self._source.name,
            "period_start": d["period_start"], "period_end": d["period_end"],
            "history_start": d["history_start"],
            "config_version": d["config_version"], "config_fingerprint": d["config_fingerprint"],
            "config": cfg.to_dict(), "status_counts": d["status_counts"], "panel": d["panel"],
            "baselines": d["baselines"], "alerts": d["alerts"], "computed_by": user_id,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }
        reading_rows = [
            {
                "org_id": str(org_id), "account_id": str(account_id),
                "content_id": r["content_id"], "janela": r["window"],
                "published_on": r["published_at"], "collected_on": r["collected_at"],
                "formato": r["format"], "tema": r["topic"], "status": r["status"],
                "age_days": r["age_days"], "metrics": r["metrics"],
                "indicators": r["indicators"], "source_ref": r["source_ref"],
            }
            for r in d["readings"]
        ]
        stored = self._repo.insert_readout(row, reading_rows)
        return self.readout_payload(org_id, UUID(str(stored["id"]))) or {}

    def readout_payload(self, org_id: UUID, readout_id: UUID) -> Optional[dict[str, Any]]:
        row = self._repo.get_readout(org_id, readout_id)
        if row is None:
            return None
        readings = sorted(
            self._repo.list_readings(org_id, readout_id),
            key=lambda r: (str(r.get("published_on") or ""), str(r.get("content_id") or ""),
                           str(r.get("janela") or "")),
        )
        return {**row, "readings": readings}

    def latest_readout_id(self, org_id: UUID, account_id: UUID) -> Optional[UUID]:
        rows = self._repo.list_readouts(org_id, account_id, limit=1)
        return UUID(str(rows[0]["id"])) if rows else None


__all__ = [
    "MAX_PERIOD_DAYS",
    "ResolvedConfig",
    "SimecConfigInvalid",
    "SimecPeriodInvalid",
    "SimecService",
]
