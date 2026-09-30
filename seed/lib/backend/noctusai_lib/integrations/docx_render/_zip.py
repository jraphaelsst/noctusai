"""Zip-level determinism for saved `.docx` bytes — shared by the Fake adapter
and `inline_markup` (both re-save a document through python-docx)."""
from __future__ import annotations

import io
import zipfile

_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


def without_wall_clock(docx_bytes: bytes) -> bytes:
    """Re-pack a saved `.docx` with every entry stamped at the zip epoch.

    python-docx's `save()` stamps each zip entry with the current time, so
    two identical renders differ whenever they straddle a second boundary —
    which is what made `test_fake_is_deterministic` flake in CI. Entry
    order, names, compression and content are preserved; only the
    timestamp is pinned.
    """
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as src, zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            pinned = zipfile.ZipInfo(info.filename, date_time=_ZIP_EPOCH)
            pinned.compress_type = info.compress_type
            pinned.external_attr = info.external_attr
            dst.writestr(pinned, src.read(info.filename))
    return out.getvalue()


__all__ = ["without_wall_clock"]
