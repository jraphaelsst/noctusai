"""Reference pool + guide-lifecycle route entry points (contract §5–§6).

What a consumer's pool / guide ROUTES call:

- ``add_reference_pair``      — normalize + store a before/after pair,
  enforce the pair limit, schedule the (debounced) guide rebuild.
- ``archive_reference_pair``  — "delete" = archive; schedule the rebuild.
- ``request_guide_regen``     — the manual "regenerate" button: enqueue a
  ``fotos.regen_guia`` that runs NOW (no debounce).
- ``pool_status``             — active count + limit, for the admin screen.

The pool is GLOBAL (platform scope, no ``org_id``). Authorization (platform
admin or ``photo_curator``) is the consumer's route guard — this module has
no notion of who is calling beyond recording ``criado_por``.

The limit is counted in PAIRS; ``None``/``0`` = unlimited; archived pairs
never count. It is checked here (the friendly path) AND refused by the
repository write itself (the race-free path — the Supabase implementation
maps the migration-129 trigger to :class:`PoolFullError`).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from noctusai_lib.domain.photo_editing.pipeline import (
    PoolEmptyError,
    request_guide_regen,
    schedule_guide_regen,
)
from noctusai_lib.domain.photo_editing.ports import PhotoEditingPorts
from noctusai_lib.domain.photo_editing.types import (
    MAX_BYTES_PER_PHOTO,
    EditType,
    PlatformSettings,
    PoolFullError,
    ReferencePair,
    Room,
)

logger = logging.getLogger(__name__)

#: Folder of the reference bucket every pair's two objects live under.
REFERENCE_PREFIX = "referencias"


class ReferenceNotFoundError(LookupError):
    code = "referencia_nao_encontrada"


class ReferenceStorageNotConfigured(RuntimeError):
    """``PhotoEditingPorts.reference_storage`` is not wired."""

    code = "armazenamento_referencias_indisponivel"


class ReferenceImageError(ValueError):
    """An uploaded side of a pair is empty or too large. ``code`` is the API code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class PoolStatus:
    pares_ativos: int
    limite_pares: int | None

    @property
    def cheio(self) -> bool:
        return bool(self.limite_pares) and self.pares_ativos >= (self.limite_pares or 0)


def effective_limit(settings: PlatformSettings) -> int | None:
    """``None`` for unlimited (``None`` or ``0`` stored)."""
    return settings.limite_pares_referencia or None


async def pool_status(ports: PhotoEditingPorts) -> PoolStatus:
    settings = await ports.repo.get_platform_settings()
    return PoolStatus(
        pares_ativos=await ports.repo.count_active_references(),
        limite_pares=effective_limit(settings),
    )


def reference_key(pair_token: str, side: str) -> str:
    return f"{REFERENCE_PREFIX}/{pair_token}/{side}.jpg"


async def add_reference_pair(
    ports: PhotoEditingPorts,
    *,
    antes: bytes,
    depois: bytes,
    comodo: Room | str,
    tipos_edicao: Sequence[EditType | str],
    nota: str | None,
    criado_por: str,
    max_bytes: int = MAX_BYTES_PER_PHOTO,
) -> ReferencePair:
    """Store one pair and schedule the guide rebuild.

    Both images go through ``imaging.normalize_for_edit`` (JPEG, sRGB,
    EXIF transposed, GPS stripped — LGPD) before anything is stored. If
    the row insert fails, the two stored objects are removed again so a
    refused pair leaves nothing behind.
    """
    storage = ports.reference_storage
    if storage is None:
        raise ReferenceStorageNotConfigured("reference_storage port is not wired")
    for side, data in (("antes", antes), ("depois", depois)):
        if not data:
            raise ReferenceImageError("arquivo_vazio", f"imagem '{side}' vazia")
        if len(data) > max_bytes:
            raise ReferenceImageError(
                "arquivo_grande_demais", f"imagem '{side}' acima de {max_bytes} bytes"
            )
    status = await pool_status(ports)
    if status.cheio:
        raise PoolFullError(f"pool de referências cheio ({status.limite_pares} pares)")
    # Raises UnsupportedImageFormatError for undecodable input (API: 415).
    antes_n = await asyncio.to_thread(ports.imaging.normalize_for_edit, antes)
    depois_n = await asyncio.to_thread(ports.imaging.normalize_for_edit, depois)
    token = uuid.uuid4().hex
    keys = (reference_key(token, "antes"), reference_key(token, "depois"))
    await storage.put(keys[0], antes_n.jpeg_bytes, content_type="image/jpeg")
    await storage.put(keys[1], depois_n.jpeg_bytes, content_type="image/jpeg")
    try:
        pair = await ports.repo.add_reference(
            antes_url=keys[0],
            depois_url=keys[1],
            comodo=Room(comodo),
            tipos_edicao=tuple(dict.fromkeys(EditType(t) for t in tipos_edicao)),
            nota=(nota or "").strip() or None,
            criado_por=criado_por,
        )
    except Exception:
        logger.warning("photo_editing.pool.add_failed cleanup keys=%s", keys)
        for key in keys:
            await storage.delete(key)
        raise
    await schedule_guide_regen(ports)
    return pair


async def archive_reference_pair(ports: PhotoEditingPorts, referencia_id: str) -> ReferencePair:
    """Archive (never delete) a pair. Idempotent: an already-archived pair
    is returned unchanged and schedules nothing."""
    current = await ports.repo.get_reference(referencia_id)
    if current is None:
        raise ReferenceNotFoundError(f"referência {referencia_id} não existe")
    if current.arquivado_em is not None:
        return current
    archived = await ports.repo.archive_reference(referencia_id, at=ports.clock())
    if archived is None:
        # Lost a race with another archive — the pair IS archived now.
        again = await ports.repo.get_reference(referencia_id)
        if again is None:
            raise ReferenceNotFoundError(f"referência {referencia_id} não existe")
        return again
    await schedule_guide_regen(ports)
    return archived


__all__ = [
    "PoolEmptyError",
    "PoolStatus",
    "REFERENCE_PREFIX",
    "ReferenceImageError",
    "ReferenceNotFoundError",
    "ReferenceStorageNotConfigured",
    "add_reference_pair",
    "archive_reference_pair",
    "effective_limit",
    "pool_status",
    "reference_key",
    "request_guide_regen",
]
