"""Runtime-settings store — admin overrides in ``agents.runtime_settings``
(migration 010). Plain JSON values, never secrets.

Seed IO shape: ``RuntimeSettingsStore`` Protocol + ``FakeRuntimeSettingsStore``
+ ``SupabaseRuntimeSettingsStore`` + ``get_runtime_settings_store(settings)``
factory (``KB § PATTERNS/backend/seed-fake-real-adapter.md``). Product-wide
(one Julia runtime per deployment), so no ``org_id``.
"""
from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from app.stores._util import utcnow_iso

__all__ = [
    "FakeRuntimeSettingsStore",
    "RuntimeSettingsStore",
    "SupabaseRuntimeSettingsStore",
    "get_runtime_settings_store",
]

_TABLE = "runtime_settings"


class RuntimeSettingsStore(Protocol):
    def get_all(self) -> dict[str, Any]:
        """Every stored override, ``{key: value}``."""
        ...

    def put(self, key: str, value: Any, *, updated_by: UUID | None) -> None:
        """UPSERT one override."""
        ...

    def delete(self, key: str) -> None:
        """Drop an override (back to the env default). Idempotent."""
        ...


class FakeRuntimeSettingsStore:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    def get_all(self) -> dict[str, Any]:
        return {k: row["value"] for k, row in self.rows.items()}

    def put(self, key: str, value: Any, *, updated_by: UUID | None) -> None:
        self.rows[key] = {"value": value, "updated_by": updated_by}

    def delete(self, key: str) -> None:
        self.rows.pop(key, None)


class SupabaseRuntimeSettingsStore:
    def __init__(self, admin_client: Any) -> None:
        self._sb = admin_client

    def get_all(self) -> dict[str, Any]:
        resp = self._sb.table(_TABLE).select("key, value").execute()
        return {r["key"]: r["value"] for r in (resp.data or [])}

    def put(self, key: str, value: Any, *, updated_by: UUID | None) -> None:
        self._sb.table(_TABLE).upsert(
            {
                "key": key,
                "value": value,
                "updated_by": str(updated_by) if updated_by else None,
                "updated_at": utcnow_iso(),
            },
            on_conflict="key",
        ).execute()

    def delete(self, key: str) -> None:
        self._sb.table(_TABLE).delete().eq("key", key).execute()


def get_runtime_settings_store(settings: Any) -> RuntimeSettingsStore:
    """Real when a service-role key is configured (same signal as every
    other agents store); Fake otherwise."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeRuntimeSettingsStore()
    from app.database import get_admin_client

    return SupabaseRuntimeSettingsStore(get_admin_client())
