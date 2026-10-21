"""Entry attachments (invoices, receipts, NF-e XML) in a PRIVATE bucket, served as short-lived signed URLs.

The client's declared content type is never trusted alone: the leading bytes must
match (`commerce.media` precedent). Storage keys are server-generated
(`<org_id>/entries/<entry_id>/<attachment_id>.<ext>`), never derived from the upload's
filename, so the bucket's per-org object RLS and the service-layer org filter agree.

HOST NOTE: the upload route is an `UploadFile` route, so the host product MUST list
`ATTACHMENT_UPLOAD_PATH_PATTERN` in its `max_body_path_overrides`:
`{ATTACHMENT_UPLOAD_PATH_PATTERN: ATTACHMENT_UPLOAD_MAX_BYTES}` (the 1 MB webhook default
413s any real PDF, silently, in prod only).

NOC-REMEDIATE[finance-attachment-download-disposition]: contract §3.4 wants
`Content-Disposition: attachment`; `StorageBackend.signed_url` has no `download=` option
yet. Until the seam grows one, XML is stored as `application/octet-stream` (a browser will
not render it) and the response carries `disposition: "attachment"` for the frontend to
honour. -- 2026-10-13
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from noctusai_lib.integrations.storage.protocol import StorageBackend

from ._common import Scope, first, new_id, now_iso
from .config import FinanceConfig
from .entries import check_deletable, delete_entry, get_entry
from .errors import ANEXO_GRANDE_DEMAIS, ANEXO_INVALIDO, ANEXO_LIMITE, FinanceError, invalid, not_found

logger = logging.getLogger(__name__)

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENTS_PER_ENTRY = 20
ATTACHMENT_UPLOAD_PATH_PATTERN = "/api/finance/entries/*/attachments"
ATTACHMENT_UPLOAD_MAX_BYTES = MAX_ATTACHMENT_BYTES + 1024 * 1024  # multipart framing headroom

#: declared content type -> (extension, content type actually stored)
_TYPES: dict[str, tuple[str, str]] = {
    "application/pdf": ("pdf", "application/pdf"),
    "image/png": ("png", "image/png"),
    "image/jpeg": ("jpg", "image/jpeg"),
    "application/xml": ("xml", "application/octet-stream"),
    "text/xml": ("xml", "application/octet-stream"),
}


def _magic_ok(ext: str, data: bytes) -> bool:
    if ext == "pdf":
        return data.startswith(b"%PDF-")
    if ext == "png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if ext == "jpg":
        return data.startswith(b"\xff\xd8\xff")
    if ext == "xml":
        head = data[:4096].lstrip(b"\xef\xbb\xbf \t\r\n")
        # An XML document starts with `<`; refuse entity declarations a downstream parser could expand.
        return head.startswith(b"<") and b"<!ENTITY" not in data[:65536].upper()
    return False


def validate_upload(content_type: str, data: bytes) -> tuple[str, str]:
    """`(extension, stored_content_type)` for an acceptable upload, else a 422/413 `FinanceError`."""
    ctype = (content_type or "").split(";")[0].strip().lower()
    spec = _TYPES.get(ctype)
    if spec is None:
        raise invalid("file", "Envie um PDF, PNG, JPG ou XML.", code=ANEXO_INVALIDO)
    ext, stored = spec
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise FinanceError(ANEXO_GRANDE_DEMAIS, f"O arquivo deve ter no máximo {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB.", 413)
    if not data or not _magic_ok(ext, data):
        raise invalid("file", "O arquivo não corresponde ao tipo informado.", code=ANEXO_INVALIDO)
    return ext, stored


def safe_filename(name: Optional[str]) -> str:
    base = re.split(r"[\\/]", name or "")[-1]
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip().lstrip(".")
    return base[:120] or "anexo"


def _key(org_id: Any, entry_id: Any, attachment_id: str, ext: str) -> str:
    return f"{org_id}/entries/{entry_id}/{attachment_id}.{ext}"


async def _with_url(storage: StorageBackend, cfg: FinanceConfig, row: dict) -> dict:
    url = await storage.signed_url(bucket=cfg.bucket, key=row["storage_path"], expires_in_seconds=cfg.signed_url_ttl_seconds)
    public = {k: v for k, v in row.items() if k != "storage_path"}
    public.update(url=url, expires_in_seconds=cfg.signed_url_ttl_seconds, disposition="attachment")
    return public


async def add_attachment(
    s: Scope,
    storage: StorageBackend,
    entry_id: Any,
    *,
    filename: Optional[str],
    content_type: str,
    data: bytes,
    user_id: Optional[str] = None,
) -> dict:
    get_entry(s, entry_id)
    ext, stored_type = validate_upload(content_type, data)
    if len(s.rows("attachments", eq={"entry_id": str(entry_id)})) >= MAX_ATTACHMENTS_PER_ENTRY:
        raise FinanceError(ANEXO_LIMITE, f"Máximo de {MAX_ATTACHMENTS_PER_ENTRY} anexos por lançamento.", 422)
    att_id = new_id()
    key = _key(s.org_id, entry_id, att_id, ext)
    await storage.put(bucket=s.cfg.bucket, key=key, data=data, content_type=stored_type)
    row = {
        "id": att_id,
        "org_id": s.org_id,
        "entry_id": str(entry_id),
        "storage_path": key,
        "filename": safe_filename(filename),
        "content_type": stored_type,
        "size_bytes": len(data),
        "uploaded_by": user_id,
        "at": now_iso(),
    }
    try:
        saved = first(s.tbl("attachments").insert(row).execute()) or row
    except Exception:
        logger.warning("finance attachment row insert failed; removing the orphan object %s", key)
        await storage.delete(bucket=s.cfg.bucket, key=key)
        raise
    return await _with_url(storage, s.cfg, saved)


async def list_attachments(s: Scope, storage: StorageBackend, entry_id: Any) -> list[dict]:
    get_entry(s, entry_id)
    rows = s.rows("attachments", eq={"entry_id": str(entry_id)})
    rows.sort(key=lambda r: (str(r.get("at")), str(r["id"])))
    return [await _with_url(storage, s.cfg, r) for r in rows]


async def delete_attachment(s: Scope, storage: StorageBackend, attachment_id: Any) -> None:
    row = s.find("attachments", attachment_id)
    if row is None:
        raise not_found("Anexo")
    s.tbl("attachments").delete().eq("org_id", s.org_id).eq("id", str(attachment_id)).execute()
    await storage.delete(bucket=s.cfg.bucket, key=row["storage_path"])


async def delete_entry_with_attachments(s: Scope, storage: StorageBackend, entry_id: Any) -> None:
    """Delete a mistaken entry and the entry's own attachments (rows are deleted explicitly, storage objects after the entry).

    The deletable guard runs FIRST, so a refused delete never touches storage. Objects are removed only after the
    entry row is gone; an object that fails to delete is logged (an orphan blob, never a dangling entry).
    """
    check_deletable(s, entry_id)
    keys = [r["storage_path"] for r in s.rows("attachments", eq={"entry_id": str(entry_id)})]
    s.tbl("attachments").delete().eq("org_id", s.org_id).eq("entry_id", str(entry_id)).execute()  # explicit: never lean on the FK cascade
    delete_entry(s, entry_id)
    for key in keys:
        try:
            await storage.delete(bucket=s.cfg.bucket, key=key)
        except Exception:  # noqa: BLE001 - the money record is already gone; the orphan object is logged for cleanup
            logger.warning("finance: orphan attachment object left after entry delete: %s", key, exc_info=True)


__all__ = [
    "delete_entry_with_attachments",
    "ATTACHMENT_UPLOAD_MAX_BYTES",
    "ATTACHMENT_UPLOAD_PATH_PATTERN",
    "MAX_ATTACHMENTS_PER_ENTRY",
    "MAX_ATTACHMENT_BYTES",
    "add_attachment",
    "delete_attachment",
    "list_attachments",
    "safe_filename",
    "validate_upload",
]
