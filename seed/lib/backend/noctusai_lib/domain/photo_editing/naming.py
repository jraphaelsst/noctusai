"""File + storage naming for the photo-editing engine.

- Zip entries: ``NN`` = the photo's position in UPLOAD order (``ordem``,
  1-based), zero-padded to 2 digits, or 3 when the batch holds more than
  99 photos. Numbering follows upload position, not the approved subset,
  so a photo keeps the same name when other decisions change and the
  zip is regenerated.
- Virtual staging adds the ``_imagem-gerada-com-ia`` suffix (the output
  also carries the visible watermark, applied by the imaging organ).
- Storage paths follow the consumer bucket layout
  ``{org_id}/{lote_id}/{foto_id}/<name>`` — the first folder is the org,
  which is what the bucket's RLS policy checks.
"""

from __future__ import annotations

from collections.abc import Iterable

from noctusai_lib.domain.photo_editing.types import EditType
from noctusai_lib.integrations.imaging import DEFAULT_WATERMARK_TEXT

STAGING_SUFFIX = "_imagem-gerada-com-ia"
#: The visible watermark on staged output — the imaging organ's canonical text.
STAGING_WATERMARK_TEXT = DEFAULT_WATERMARK_TEXT
OUTPUT_EXTENSION = "jpg"

UPLOAD_NAME = "upload"
ORIGINAL_NAME = "original.jpg"
EDITED_NAME = "editada.jpg"


def is_staged(tipos: Iterable[EditType]) -> bool:
    return any(EditType(t) is EditType.STAGING_VIRTUAL for t in tipos)


def zip_number_width(total_photos: int) -> int:
    if total_photos < 0:
        raise ValueError(f"total_photos must be >= 0, got {total_photos}")
    return 3 if total_photos > 99 else 2


def zip_entry_name(ordem: int, *, total_photos: int, tipos: Iterable[EditType]) -> str:
    """``"07.jpg"`` / ``"007.jpg"`` / ``"07_imagem-gerada-com-ia.jpg"``."""
    if ordem < 1:
        raise ValueError(f"ordem is 1-based, got {ordem}")
    if ordem > total_photos:
        raise ValueError(f"ordem {ordem} exceeds total_photos {total_photos}")
    width = zip_number_width(total_photos)
    suffix = STAGING_SUFFIX if is_staged(tipos) else ""
    return f"{ordem:0{width}d}{suffix}.{OUTPUT_EXTENSION}"


def zip_file_name(lote_nome: str) -> str:
    """Download name for the batch zip; path separators are neutralized."""
    safe = "".join("-" if c in '/\\:*?"<>|' else c for c in lote_nome).strip() or "lote"
    return f"{safe}.zip"


def storage_path(org_id: str, lote_id: str, foto_id: str, name: str) -> str:
    for part in (org_id, lote_id, foto_id, name):
        if not part or "/" in part or part in (".", ".."):
            raise ValueError(f"invalid storage path segment: {part!r}")
    return f"{org_id}/{lote_id}/{foto_id}/{name}"


def upload_path(org_id: str, lote_id: str, foto_id: str, extension: str) -> str:
    ext = extension.lower().lstrip(".")
    if not ext.isalnum():
        raise ValueError(f"invalid upload extension: {extension!r}")
    return storage_path(org_id, lote_id, foto_id, f"{UPLOAD_NAME}.{ext}")


__all__ = [
    "EDITED_NAME",
    "ORIGINAL_NAME",
    "OUTPUT_EXTENSION",
    "STAGING_SUFFIX",
    "STAGING_WATERMARK_TEXT",
    "UPLOAD_NAME",
    "is_staged",
    "storage_path",
    "upload_path",
    "zip_entry_name",
    "zip_file_name",
    "zip_number_width",
]
