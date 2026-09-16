"""The per-photo review rows shared by `GET /lotes/{id}` and
`GET /revisao/{lote_id}` (both return FE `FotoRevisao[]`).

🔴 Evaluations are READ only when `include_verdict` is true — a corretor's
request never even touches `fotos_avaliacoes`."""
from __future__ import annotations

from typing import Any, Optional

from noctusai_lib.domain.photo_editing import Batch, Photo, PhotoEditingPorts

from app.modules.edicao_fotos.errors import api_error
from app.modules.edicao_fotos.presenters import foto_revisao_out

SIGNED_URL_TTL_SECONDS = 3600


async def signed_url(ports: PhotoEditingPorts, path: Optional[str]) -> Optional[str]:
    """A signed URL for a batch photo (the `edicao-fotos` bucket)."""
    return await signed_url_in(ports.storage, path)


async def signed_url_in(storage: Any, path: Optional[str]) -> Optional[str]:
    """A signed URL for `path` in `storage` — shared by batch photos and the
    reference pool (`edicao-fotos-referencias`)."""
    if not path:
        return None
    sign = getattr(storage, "signed_url", None)
    if sign is None:
        # A storage port that cannot sign cannot serve review images; that
        # is a wiring error, not an empty preview.
        raise api_error(503, "armazenamento_sem_url", "Armazenamento não gera URLs assinadas.")
    return await sign(path, expires_in_seconds=SIGNED_URL_TTL_SECONDS)


async def review_rows(
    ports: PhotoEditingPorts,
    batch: Batch,
    photos: list[Photo],
    *,
    include_verdict: bool,
) -> list[dict[str, Any]]:
    decisions = await ports.repo.latest_decisions(batch.id)
    rows: list[dict[str, Any]] = []
    for photo in photos:
        rows.append(
            foto_revisao_out(
                photo,
                url_antes=await signed_url(ports, photo.storage_path_original),
                url_depois=await signed_url(ports, photo.storage_path_editada),
                decision=decisions.get(photo.id),
                evaluation=(
                    await ports.repo.latest_evaluation(photo.id) if include_verdict else None
                ),
                include_verdict=include_verdict,
            )
        )
    return rows


__all__ = ["SIGNED_URL_TTL_SECONDS", "review_rows", "signed_url", "signed_url_in"]
