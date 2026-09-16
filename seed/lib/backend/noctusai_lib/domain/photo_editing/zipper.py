"""Batch zip — approved photos only.

A zip is available only once every non-failed photo has a decision
(contract §3: ``409`` until every photo is decided). ``falhou`` photos
never block and are never included. The archive is byte-deterministic
for the same inputs (fixed timestamps, stable order), so a regenerated
zip after an unrelated decision change is identical for unchanged
entries.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from typing import TYPE_CHECKING

from noctusai_lib.domain.photo_editing.naming import zip_entry_name
from noctusai_lib.domain.photo_editing.types import (
    Decision,
    EditType,
    Photo,
    PhotoStatus,
    ReviewDecision,
)

if TYPE_CHECKING:  # pragma: no cover
    from noctusai_lib.domain.photo_editing.ports import PhotoEditingPorts

_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


class BatchNotDecidedError(RuntimeError):
    """At least one photo still awaits processing or a decision (HTTP 409)."""

    code = "lote_nao_decidido"

    def __init__(self, pending_ids: list[str]) -> None:
        self.pending_ids = pending_ids
        super().__init__(f"{len(pending_ids)} foto(s) ainda sem decisão")


class NothingApprovedError(RuntimeError):
    """Every photo was decided but none approved — there is nothing to zip."""

    code = "nenhuma_foto_aprovada"


@dataclass(frozen=True)
class ZipEntry:
    name: str
    storage_path: str
    foto_id: str


def plan_zip(
    photos: list[Photo],
    decisions: dict[str, ReviewDecision],
    tipos_by_foto: dict[str, tuple[EditType, ...]],
) -> list[ZipEntry]:
    """Pure: which stored files go into the zip, under which names.

    ``tipos_by_foto`` is the edit-type set each photo was ACTUALLY edited
    with (its latest edit attempt) — not the org's current settings, which
    may have changed since submit.

    Raises ``BatchNotDecidedError`` when any non-failed photo is undecided,
    ``NothingApprovedError`` when no photo is approved.
    """
    total = len(photos)
    pending = [
        p.id
        for p in photos
        if PhotoStatus(p.status) is not PhotoStatus.FALHOU and p.id not in decisions
    ]
    if pending:
        raise BatchNotDecidedError(pending)
    entries: list[ZipEntry] = []
    for p in sorted(photos, key=lambda x: x.ordem):
        if PhotoStatus(p.status) is PhotoStatus.FALHOU:
            continue
        if decisions[p.id].decisao is not Decision.APROVAR:
            continue
        if not p.storage_path_editada:
            raise RuntimeError(f"approved photo {p.id} has no edited file")
        entries.append(
            ZipEntry(
                name=zip_entry_name(
                    p.ordem, total_photos=total, tipos=tipos_by_foto.get(p.id, ())
                ),
                storage_path=p.storage_path_editada,
                foto_id=p.id,
            )
        )
    if not entries:
        raise NothingApprovedError("nenhuma foto aprovada neste lote")
    return entries


def build_zip(files: list[tuple[str, bytes]]) -> bytes:
    """Deterministic zip of ``(name, bytes)`` pairs. JPEGs are already
    compressed, so entries are STORED."""
    names = [n for n, _ in files]
    if len(set(names)) != len(names):
        raise ValueError("duplicate zip entry names")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, data in files:
            info = zipfile.ZipInfo(filename=name, date_time=_FIXED_ZIP_TIME)
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)
    return buf.getvalue()


async def build_batch_zip(ports: "PhotoEditingPorts", lote_id: str) -> bytes:
    """Read the batch, plan it, fetch the approved files, return zip bytes."""
    photos = await ports.repo.list_photos(lote_id)
    decisions = await ports.repo.latest_decisions(lote_id)
    tipos_by_foto: dict[str, tuple[EditType, ...]] = {}
    for p in photos:
        edit = await ports.repo.latest_edit(p.id)
        if edit is not None:
            tipos_by_foto[p.id] = edit.tipos_edicao
    entries = plan_zip(photos, decisions, tipos_by_foto)
    files = [(e.name, await ports.storage.get(e.storage_path)) for e in entries]
    return build_zip(files)


__all__ = [
    "BatchNotDecidedError",
    "build_batch_zip",
    "NothingApprovedError",
    "ZipEntry",
    "build_zip",
    "plan_zip",
]
