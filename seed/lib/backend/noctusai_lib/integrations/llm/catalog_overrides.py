"""Operator overrides of the static model catalog — the runtime overlay.

WHY
───
`models.MODELS` is code: a vendor price change, a newly published rate or a
model to switch off would otherwise need a deploy. Worse, a model whose rate
was never published (`gpt-image-2`, edicao-fotos C8) can only be declared as
a gap. This module lets an operator (a platform admin, through a product UI)
supply those facts as DATA, and every catalog consumer sees them — because
`models.models_for` applies the overlay, and pricing
(`usage.estimate_cost_usd`), capability gates
(`image_edit.capabilities_for_model`) and cost records all read the catalog
through `models_for`.

SHAPE
─────
- :class:`ModelOverride` — one FULL operator row for `(provider, kind,
  model_id)`. It replaces every mutable field of the static row (a `None`
  price means "no rate", explicitly — not "keep the static one"); a row
  with `enabled=False` removes the model; a row with no static counterpart
  ADDS the model.
- The overlay — a process-wide immutable snapshot, swapped atomically by
  :func:`set_model_overrides`. `models_for` is synchronous and hot, so it
  never touches a database: the consumer refreshes the snapshot
  (:func:`refresh_model_overrides`) at startup, after every write, and on
  a timer (another process may have written).
- :class:`ModelCatalogStore` — where overrides live. Protocol +
  :class:`InMemoryModelCatalogStore` (Fake) + :class:`SupabaseModelCatalogStore`
  (Real) + :func:`make_model_catalog_store` (factory). Every save bumps a
  version and appends an immutable history row, so a price change is never
  lost. Table contract: `migrations/llm_model_overrides.sql.template`.

Price snapshots: a cost record stores the dollar amount computed at call
time (`llm_usage.cost_estimate_usd`), so changing a price here never
re-prices history; the version table says which rate was in force when.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional, Protocol, runtime_checkable

from .models import ModelEntry, ModelKind

logger = logging.getLogger(__name__)

TAG_PERFORMANCE_VALUES = ("performance", "economico")


class ModelOverrideConflict(RuntimeError):
    """Another writer saved the same row concurrently (version collision)."""

    code = "modelo_versao_conflito"


@dataclass(frozen=True)
class ModelOverride:
    provider: str
    kind: ModelKind
    model_id: str
    enabled: bool = True
    label: Optional[str] = None
    description: Optional[str] = None
    snapshot: Optional[str] = None
    cost_per_1m_input_tokens: Optional[float] = None
    cost_per_1m_output_tokens: Optional[float] = None
    cost_per_1m_image_input_tokens: Optional[float] = None
    cost_per_1m_image_output_tokens: Optional[float] = None
    supports_batch: bool = False
    tag_performance: Optional[str] = None
    version: int = 0
    updated_by: Optional[str] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if self.tag_performance is not None and self.tag_performance not in TAG_PERFORMANCE_VALUES:
            raise ValueError(f"tag_performance must be one of {TAG_PERFORMANCE_VALUES} or None")
        for name in _PRICE_FIELDS:
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be >= 0")

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.provider, self.kind, self.model_id)

    @classmethod
    def from_entry(cls, entry: ModelEntry, **changes: Any) -> "ModelOverride":
        """A full override row seeded from a static entry (the edit form's
        starting point)."""
        base = cls(
            provider=entry.provider,
            kind=entry.kind,
            model_id=entry.id,
            label=entry.label,
            description=entry.description or None,
            snapshot=entry.snapshot,
            cost_per_1m_input_tokens=entry.cost_per_1m_input_tokens,
            cost_per_1m_output_tokens=entry.cost_per_1m_output_tokens,
            cost_per_1m_image_input_tokens=entry.cost_per_1m_image_input_tokens,
            cost_per_1m_image_output_tokens=entry.cost_per_1m_image_output_tokens,
            supports_batch=entry.supports_batch,
            tag_performance=entry.tag_performance,
        )
        return dataclasses.replace(base, **changes)

    def to_entry(self, base: Optional[ModelEntry] = None) -> ModelEntry:
        return ModelEntry(
            id=self.model_id,
            label=self.label or (base.label if base else self.model_id),
            provider=self.provider,
            kind=self.kind,
            stub=base.stub if base else False,
            description=self.description or (base.description if base else ""),
            cost_per_1m_input_tokens=self.cost_per_1m_input_tokens,
            cost_per_1m_output_tokens=self.cost_per_1m_output_tokens,
            cost_per_1m_image_input_tokens=self.cost_per_1m_image_input_tokens,
            cost_per_1m_image_output_tokens=self.cost_per_1m_image_output_tokens,
            supports_batch=self.supports_batch,
            snapshot=self.snapshot,
            tag_performance=self.tag_performance,
        )


_PRICE_FIELDS = (
    "cost_per_1m_input_tokens",
    "cost_per_1m_output_tokens",
    "cost_per_1m_image_input_tokens",
    "cost_per_1m_image_output_tokens",
)


# ---------------------------------------------------------------------------
# The process-wide overlay
# ---------------------------------------------------------------------------

_overlay: dict[tuple[str, str, str], ModelOverride] = {}
_overlay_lock = threading.Lock()


def set_model_overrides(overrides: Iterable[ModelOverride]) -> None:
    """Replace the whole overlay atomically (readers never see a mix)."""
    snapshot = {o.key: o for o in overrides}
    global _overlay
    with _overlay_lock:
        _overlay = snapshot


def clear_model_overrides() -> None:
    set_model_overrides(())


def get_model_overrides() -> list[ModelOverride]:
    return list(_overlay.values())


def get_model_override(provider: str, kind: str, model_id: str) -> Optional[ModelOverride]:
    return _overlay.get((provider, kind, model_id))


def apply_overlay(
    base: list[ModelEntry], provider: str, kind: Optional[ModelKind] = None
) -> list[ModelEntry]:
    """`base` (already filtered to `provider`/`kind`) with the overlay applied."""
    overlay = _overlay  # one read: a concurrent swap cannot split this call
    if not overlay:
        return list(base)
    out: list[ModelEntry] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in base:
        key = (entry.provider, entry.kind, entry.id)
        seen.add(key)
        override = overlay.get(key)
        if override is None:
            out.append(entry)
        elif override.enabled:
            out.append(override.to_entry(entry))
    added = [
        o
        for key, o in overlay.items()
        if key not in seen
        and o.enabled
        and o.provider == provider
        and (kind is None or o.kind == kind)
    ]
    out.extend(o.to_entry() for o in sorted(added, key=lambda o: (o.kind, o.model_id)))
    return out


# ---------------------------------------------------------------------------
# Store — Protocol + Fake + Real + factory
# ---------------------------------------------------------------------------


@runtime_checkable
class ModelCatalogStore(Protocol):
    async def list_overrides(self) -> list[ModelOverride]: ...

    async def save_override(
        self, override: ModelOverride, *, changed_by: Optional[str]
    ) -> ModelOverride:
        """Persist `override` as the next version; returns the stored row."""
        ...

    async def list_versions(
        self, provider: str, kind: str, model_id: str, *, limit: int = 50
    ) -> list[ModelOverride]:
        """History, newest first."""
        ...


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class InMemoryModelCatalogStore:
    now: Callable[[], datetime] = _utcnow
    _current: dict[tuple[str, str, str], ModelOverride] = field(default_factory=dict)
    _history: list[ModelOverride] = field(default_factory=list)

    async def list_overrides(self) -> list[ModelOverride]:
        return sorted(self._current.values(), key=lambda o: o.key)

    async def save_override(
        self, override: ModelOverride, *, changed_by: Optional[str]
    ) -> ModelOverride:
        current = self._current.get(override.key)
        stored = dataclasses.replace(
            override,
            version=(current.version if current else 0) + 1,
            updated_by=changed_by,
            updated_at=self.now(),
        )
        self._current[stored.key] = stored
        self._history.append(stored)
        return stored

    async def list_versions(
        self, provider: str, kind: str, model_id: str, *, limit: int = 50
    ) -> list[ModelOverride]:
        rows = [o for o in self._history if o.key == (provider, kind, model_id)]
        return sorted(rows, key=lambda o: o.version, reverse=True)[:limit]


_COLUMNS = (
    "provider",
    "kind",
    "model_id",
    "enabled",
    "label",
    "description",
    "snapshot",
    *_PRICE_FIELDS,
    "supports_batch",
    "tag_performance",
    "version",
    "updated_by",
    "updated_at",
)


def _row_of(o: ModelOverride) -> dict[str, Any]:
    row = {name: getattr(o, name) for name in _COLUMNS}
    row["updated_at"] = o.updated_at.isoformat() if o.updated_at else None
    return row


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _override_of(row: dict[str, Any]) -> ModelOverride:
    kwargs = {name: row.get(name) for name in _COLUMNS}
    for name in _PRICE_FIELDS:
        if kwargs[name] is not None:
            kwargs[name] = float(kwargs[name])
    kwargs["enabled"] = bool(kwargs["enabled"])
    kwargs["supports_batch"] = bool(kwargs["supports_batch"])
    kwargs["version"] = int(kwargs["version"] or 0)
    kwargs["updated_at"] = _parse_dt(kwargs["updated_at"])
    if kwargs["updated_by"] is not None:
        kwargs["updated_by"] = str(kwargs["updated_by"])
    return ModelOverride(**kwargs)


class SupabaseModelCatalogStore:
    """Tables `<schema>.llm_model_overrides` (current row per model) and
    `<schema>.llm_model_override_versions` (append-only history, UNIQUE on
    `(provider, kind, model_id, version)`).

    Save order: the HISTORY row is inserted first — its unique key is the
    optimistic lock, so two concurrent saves of the same row cannot both
    claim version N (the loser gets :class:`ModelOverrideConflict`); only
    then is the current row upserted."""

    CURRENT = "llm_model_overrides"
    HISTORY = "llm_model_override_versions"

    def __init__(self, client: Any, *, schema: str, now: Callable[[], datetime] = _utcnow) -> None:
        self._client = client
        self._schema = schema
        self._now = now

    def _t(self, table: str) -> Any:
        return self._client.schema(self._schema).from_(table)

    async def _execute(self, builder: Any) -> list[dict[str, Any]]:
        result = await asyncio.to_thread(builder.execute)
        data = getattr(result, "data", None) or []
        return data if isinstance(data, list) else [data]

    async def list_overrides(self) -> list[ModelOverride]:
        rows = await self._execute(self._t(self.CURRENT).select("*"))
        return sorted((_override_of(r) for r in rows), key=lambda o: o.key)

    async def save_override(
        self, override: ModelOverride, *, changed_by: Optional[str]
    ) -> ModelOverride:
        current_rows = await self._execute(
            self._t(self.CURRENT)
            .select("version")
            .eq("provider", override.provider)
            .eq("kind", override.kind)
            .eq("model_id", override.model_id)
            .limit(1)
        )
        current_version = int(current_rows[0]["version"]) if current_rows else 0
        stored = dataclasses.replace(
            override,
            version=current_version + 1,
            updated_by=changed_by,
            updated_at=self._now(),
        )
        row = _row_of(stored)
        try:
            await self._execute(self._t(self.HISTORY).insert(row))
        except Exception as exc:
            if getattr(exc, "code", None) == "23505":
                raise ModelOverrideConflict(
                    f"{override.model_id}: version {stored.version} already written"
                ) from exc
            raise
        saved = await self._execute(
            self._t(self.CURRENT).upsert(row, on_conflict="provider,kind,model_id")
        )
        return _override_of(saved[0]) if saved else stored

    async def list_versions(
        self, provider: str, kind: str, model_id: str, *, limit: int = 50
    ) -> list[ModelOverride]:
        rows = await self._execute(
            self._t(self.HISTORY)
            .select("*")
            .eq("provider", provider)
            .eq("kind", kind)
            .eq("model_id", model_id)
            .order("version", desc=True)
            .limit(limit)
        )
        return [_override_of(r) for r in rows]


def make_model_catalog_store(
    *,
    supabase_client: Any = None,
    schema: str = "public",
    use_fake: bool = False,
) -> ModelCatalogStore:
    if use_fake:
        return InMemoryModelCatalogStore()
    if supabase_client is None:
        raise RuntimeError("make_model_catalog_store: supabase_client is required (or use_fake=True)")
    return SupabaseModelCatalogStore(supabase_client, schema=schema)


async def refresh_model_overrides(store: ModelCatalogStore) -> int:
    """Load every override from `store` into the process overlay.

    A failed read RAISES and leaves the previous snapshot in place — the
    caller decides whether that is fatal (a stale-but-known overlay beats
    an empty one, which would silently revert operator prices)."""
    overrides = await store.list_overrides()
    set_model_overrides(overrides)
    return len(overrides)


__all__ = [
    "InMemoryModelCatalogStore",
    "ModelCatalogStore",
    "ModelOverride",
    "ModelOverrideConflict",
    "SupabaseModelCatalogStore",
    "TAG_PERFORMANCE_VALUES",
    "apply_overlay",
    "clear_model_overrides",
    "get_model_override",
    "get_model_overrides",
    "make_model_catalog_store",
    "refresh_model_overrides",
    "set_model_overrides",
]
