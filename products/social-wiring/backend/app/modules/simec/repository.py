"""Supabase IO for SIMEC (migration ``284_simec.sql``).

The client is the service-role admin client (RLS bypassed), so every read and
write filters ``org_id`` explicitly — the filter IS the tenant boundary (same
defence-in-depth as ``app/modules/instagram/repository.py``). Table names are
bare: the admin client is already pinned to ``social_wiring``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.persistence import iter_paged_rows

CONFIGS = "simec_configs"
CONFIG_HISTORY = "simec_config_historico"
READOUTS = "simec_readouts"
READINGS = "simec_leituras"

READOUT_SUMMARY_COLUMNS = (
    "id, org_id, account_id, platform, source, period_start, period_end, history_start, "
    "config_version, config_fingerprint, status_counts, computed_by, computed_at"
)
READOUT_FULL_COLUMNS = READOUT_SUMMARY_COLUMNS + ", config, panel, baselines, alerts"
READING_COLUMNS = (
    "id, content_id, janela, published_on, collected_on, formato, tema, status, age_days, "
    "metrics, indicators, source_ref"
)
#: Readings of one readout are written in chunks this size (one request each).
INSERT_CHUNK = 500


class SimecRepository:
    def __init__(self, client: Any) -> None:
        self._client = client

    def _t(self, name: str):
        return self._client.table(name)

    # configs ---------------------------------------------------------------
    def get_config_layer(
        self, org_id: UUID, platform: str, account_id: Optional[UUID]
    ) -> Optional[dict[str, Any]]:
        q = (
            self._t(CONFIGS)
            .select("id, org_id, platform, account_id, overrides, version, updated_by, updated_at")
            .eq("org_id", str(org_id))
            .eq("platform", platform)
        )
        q = q.eq("account_id", str(account_id)) if account_id is not None else q.is_("account_id", "null")
        rows = q.limit(1).execute().data or []
        return rows[0] if rows else None

    def save_config_layer(
        self,
        org_id: UUID,
        platform: str,
        account_id: Optional[UUID],
        overrides: dict[str, Any],
        *,
        user_id: Optional[str],
    ) -> dict[str, Any]:
        """Insert or bump the layer's version, then append the history row."""
        now = datetime.now(timezone.utc).isoformat()
        current = self.get_config_layer(org_id, platform, account_id)
        if current is None:
            row = (
                self._t(CONFIGS)
                .insert({
                    "org_id": str(org_id), "platform": platform,
                    "account_id": str(account_id) if account_id else None,
                    "overrides": overrides, "version": 1, "updated_by": user_id,
                    "created_at": now, "updated_at": now,
                })
                .execute()
                .data[0]
            )
        else:
            version = int(current["version"]) + 1
            (
                self._t(CONFIGS)
                .update({"overrides": overrides, "version": version,
                         "updated_by": user_id, "updated_at": now})
                .eq("id", str(current["id"]))
                .eq("org_id", str(org_id))
                .execute()
            )
            row = {**current, "overrides": overrides, "version": version,
                   "updated_by": user_id, "updated_at": now}
        self._t(CONFIG_HISTORY).insert({
            "config_id": str(row["id"]), "org_id": str(org_id), "platform": platform,
            "account_id": str(account_id) if account_id else None,
            "version": row["version"], "overrides": overrides,
            "changed_by": user_id, "changed_at": now,
        }).execute()
        return row

    # readouts --------------------------------------------------------------
    def insert_readout(self, row: dict[str, Any], readings: list[dict[str, Any]]) -> dict[str, Any]:
        stored = self._t(READOUTS).insert(row).execute().data[0]
        rid = str(stored["id"])
        for i in range(0, len(readings), INSERT_CHUNK):
            chunk = [{**r, "readout_id": rid} for r in readings[i : i + INSERT_CHUNK]]
            self._t(READINGS).insert(chunk).execute()
        return stored

    def list_readouts(self, org_id: UUID, account_id: UUID, *, limit: int) -> list[dict[str, Any]]:
        rows = (
            self._t(READOUTS)
            .select(READOUT_SUMMARY_COLUMNS)
            .eq("org_id", str(org_id))
            .eq("account_id", str(account_id))
            .order("computed_at", desc=True)
            .limit(limit)
            .execute()
            .data
            or []
        )
        return sorted(rows, key=lambda r: str(r["computed_at"]), reverse=True)

    def get_readout(self, org_id: UUID, readout_id: UUID) -> Optional[dict[str, Any]]:
        rows = (
            self._t(READOUTS)
            .select(READOUT_FULL_COLUMNS)
            .eq("org_id", str(org_id))
            .eq("id", str(readout_id))
            .limit(1)
            .execute()
            .data
            or []
        )
        return rows[0] if rows else None

    def list_readings(self, org_id: UUID, readout_id: UUID) -> list[dict[str, Any]]:
        def page(start: int, end: int):
            return (
                self._t(READINGS)
                .select(READING_COLUMNS)
                .eq("org_id", str(org_id))
                .eq("readout_id", str(readout_id))
                .order("id")
                .range(start, end)
                .execute()
                .data
            )

        return list(iter_paged_rows(page, label=f"simec_leituras readout={readout_id}"))


__all__ = ["SimecRepository", "CONFIGS", "CONFIG_HISTORY", "READOUTS", "READINGS"]
