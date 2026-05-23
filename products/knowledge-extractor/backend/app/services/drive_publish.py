"""Publish locally-generated docx back into the Drive course folder.

Mirrors the methodology docx layout onto the per-module summaries/transcripts
trees: for each ``<module>/docx/*.docx`` under a local root, the file is uploaded
into ``<parent>/<module>/docx/`` in Drive (folders created on demand, idempotent
by file name). The Drive surface is the seam (Protocol) — injected, never a bare
SDK call — so this stays testable with the Fake and absorbable into noc.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.integrations.google_drive.drive_v3_adapter import FOLDER_MIME
from app.integrations.google_drive.protocol import DriveDownloader
from app.integrations.google_drive.types import DriveFile
from app.logging_config import get_logger

logger = get_logger(__name__)

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@dataclass(frozen=True)
class PublishedDoc:
    """One docx considered for upload: where it went and whether it was skipped."""

    module: str
    name: str
    drive_file_id: str
    skipped: bool


async def ensure_child_folder(
    downloader: DriveDownloader, name: str, parent_id: str
) -> DriveFile:
    """Return the subfolder `name` under `parent_id`, creating it if absent."""
    for child in await downloader.list_children(parent_id):
        if child.mime_type == FOLDER_MIME and child.name == name:
            return child
    return await downloader.create_folder(name, parent_id)


async def publish_docx_tree(
    downloader: DriveDownloader,
    *,
    parent_id: str,
    local_root: Path,
    overwrite: bool = False,
) -> list[PublishedDoc]:
    """Mirror local ``<module>/docx/*.docx`` into Drive under ``parent_id``.

    For each local module dir holding a ``docx/`` subfolder, ensure
    ``<parent_id>/<module>/docx/`` exists in Drive and upload each .docx into it.
    A file already present (by name) is skipped unless ``overwrite`` is set.
    """
    results: list[PublishedDoc] = []
    if not local_root.exists():
        logger.warning("local root %s does not exist — nothing to publish", local_root)
        return results

    for module_dir in sorted(p for p in local_root.iterdir() if p.is_dir()):
        local_docx_dir = module_dir / "docx"
        docs = sorted(local_docx_dir.glob("*.docx")) if local_docx_dir.exists() else []
        if not docs:
            continue

        module_folder = await ensure_child_folder(downloader, module_dir.name, parent_id)
        docx_folder = await ensure_child_folder(downloader, "docx", module_folder.id)
        existing = {c.name for c in await downloader.list_children(docx_folder.id)}

        for doc in docs:
            if doc.name in existing and not overwrite:
                results.append(PublishedDoc(module_dir.name, doc.name, "", skipped=True))
                continue
            created = await downloader.upload_file(
                doc, docx_folder.id, name=doc.name, mime_type=DOCX_MIME
            )
            results.append(
                PublishedDoc(module_dir.name, doc.name, created.id, skipped=False)
            )
    return results


__all__ = ["PublishedDoc", "DOCX_MIME", "ensure_child_folder", "publish_docx_tree"]
