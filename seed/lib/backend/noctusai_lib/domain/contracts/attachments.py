"""Contract attachments (the signed scan, annexes) in a PRIVATE bucket, served as short-lived signed URLs.

Validation (declared type + magic bytes, size cap, safe filename) is finance's, imported rather than
copied; keys are server-generated `<org_id>/contracts/<contract_id>/<attachment_id>.<ext>`.

HOST NOTE: the upload route is an `UploadFile` route -- list `ATTACHMENT_UPLOAD_PATH_PATTERN` in
`max_body_path_overrides`: `{ATTACHMENT_UPLOAD_PATH_PATTERN: ATTACHMENT_UPLOAD_MAX_BYTES}`.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from noctusai_lib.domain.finance.attachments import MAX_ATTACHMENT_BYTES, safe_filename, validate_upload
from noctusai_lib.integrations.storage.protocol import StorageBackend

from ._common import Scope, first, new_id, now_iso
from .contracts import get_contract
from .errors import ANEXO_LIMITE, ContractsError, not_found
from .types import AttachmentKind, values

logger = logging.getLogger(__name__)

MAX_ATTACHMENTS_PER_CONTRACT = 30
ATTACHMENT_UPLOAD_PATH_PATTERN = "/api/contracts/*/attachments"
ATTACHMENT_UPLOAD_MAX_BYTES = MAX_ATTACHMENT_BYTES + 1024 * 1024  # multipart framing headroom


def _validate(content_type: str, data: bytes) -> tuple[str, str]:
    """Finance's validator raises `FinanceError` (an `AppException`); re-raise as ours so the code namespace stays contracts'."""
    from noctusai_lib.domain.finance.errors import FinanceError

    try:
        return validate_upload(content_type, data)
    except FinanceError as exc:
        raise ContractsError(exc.code, exc.message, exc.status_code, details=getattr(exc, "details", None)) from exc


async def _with_url(storage: StorageBackend, cfg, row: dict) -> dict:
    url = await storage.signed_url(bucket=cfg.bucket, key=row["storage_path"], expires_in_seconds=cfg.signed_url_ttl_seconds)
    public = {k: v for k, v in row.items() if k != "storage_path"}
    public.update(url=url, expires_in_seconds=cfg.signed_url_ttl_seconds)
    return public


async def add_attachment(s: Scope, storage: StorageBackend, contract_id: Any, *, filename: Optional[str], content_type: str,
                         data: bytes, kind: str = AttachmentKind.OTHER.value, user_id: Optional[str] = None) -> dict:
    get_contract(s, contract_id)
    if kind not in values(AttachmentKind):
        raise ContractsError("invalid", "Tipo de anexo inválido.", 422, field="kind")
    ext, stored_type = _validate(content_type, data)
    if len(s.rows("contract_attachments", eq={"contract_id": str(contract_id)})) >= MAX_ATTACHMENTS_PER_CONTRACT:
        raise ContractsError(ANEXO_LIMITE, f"Máximo de {MAX_ATTACHMENTS_PER_CONTRACT} anexos por contrato.", 422)
    att_id = new_id()
    key = f"{s.org_id}/contracts/{contract_id}/{att_id}.{ext}"
    await storage.put(bucket=s.cfg.bucket, key=key, data=data, content_type=stored_type)
    row = {"id": att_id, "org_id": s.org_id, "contract_id": str(contract_id), "kind": kind, "storage_path": key,
           "filename": safe_filename(filename), "content_type": stored_type, "size_bytes": len(data), "uploaded_by": user_id,
           "created_at": now_iso()}
    try:
        saved = first(s.tbl("contract_attachments").insert(row).execute()) or row
    except Exception:
        logger.warning("contract attachment row insert failed; removing the orphan object %s", key)
        await storage.delete(bucket=s.cfg.bucket, key=key)
        raise
    return await _with_url(storage, s.cfg, saved)


async def list_attachments(s: Scope, storage: StorageBackend, contract_id: Any) -> list[dict]:
    get_contract(s, contract_id)
    rows = s.rows("contract_attachments", eq={"contract_id": str(contract_id)})
    rows.sort(key=lambda r: (str(r.get("created_at")), str(r["id"])))
    return [await _with_url(storage, s.cfg, r) for r in rows]


async def delete_attachment(s: Scope, storage: StorageBackend, contract_id: Any, attachment_id: Any) -> None:
    row = s.find("contract_attachments", attachment_id)
    if row is None or str(row["contract_id"]) != str(contract_id):
        raise not_found("Anexo")
    await storage.delete(bucket=s.cfg.bucket, key=row["storage_path"])
    s.tbl("contract_attachments").delete().eq("org_id", s.org_id).eq("id", str(attachment_id)).execute()


__all__ = ["MAX_ATTACHMENT_BYTES", "ATTACHMENT_UPLOAD_MAX_BYTES", "ATTACHMENT_UPLOAD_PATH_PATTERN", "add_attachment", "delete_attachment", "list_attachments"]
