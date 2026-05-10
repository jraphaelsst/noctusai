"""
Sellout submission orchestration.

The router stays thin — it receives the request, validates auth, and hands
off to one of the three submission entrypoints here. Each entrypoint:
  1. Validates input.
  2. (For nfe_xml / attachment) uploads bytes to the storage backend.
  3. (For nfe_xml) parses the XML to extract structured fields.
  4. Inserts the `relatorios_sellout` row.
  5. Schedules the brand-admin notification email.

Storage backend is consumer-injected (Protocol seam from
`noctusai_lib.integrations.storage`) so tests pass a `FakeStorageBackend`
and production routes get whatever the app boot wired (Supabase in real
deployments).
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

from noctusai_lib.integrations.email import Digest, send_to_one
from noctusai_lib.integrations.storage import FakeStorageBackend, StorageBackend

from .nfe_xml_parser import NFeParseError, parse_nfe_xml

logger = logging.getLogger(__name__)

SELLOUT_TABLE = "relatorios_sellout"
SELLOUT_BUCKET = "adconnect-sellout"


class SubmissionError(ValueError):
    """Raised when a sellout submission fails validation."""


# Module-level default storage backend for non-test deployments. Production
# wires `make_storage_backend(kind='supabase', client=...)` via lifespan.
# Tests pass an explicit `storage=` kwarg to bypass.
_default_storage: StorageBackend = FakeStorageBackend()


def configure_storage(backend: StorageBackend) -> None:
    """Bind the module-level storage backend (called from app boot)."""
    global _default_storage
    _default_storage = backend


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_storage_key(distributor_id: str, suffix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    nonce = secrets.token_hex(4)
    return f"{distributor_id}/{stamp}-{nonce}{suffix}"


async def _upload_blob(
    storage: StorageBackend,
    *,
    distributor_id: str,
    filename: str,
    data: bytes,
    content_type: str,
) -> str:
    """Upload bytes and return a signed/dev URL the row can persist."""
    suffix = ""
    if "." in filename:
        suffix = "." + filename.rsplit(".", 1)[-1].lower()
    key = _gen_storage_key(distributor_id, suffix)
    await storage.put(
        bucket=SELLOUT_BUCKET,
        key=key,
        data=data,
        content_type=content_type,
        metadata={"original_filename": filename},
    )
    try:
        return await storage.signed_url(
            bucket=SELLOUT_BUCKET, key=key, expires_in_seconds=3600
        )
    except Exception as exc:  # pragma: no cover - best-effort URL generation
        logger.warning(
            "sellout_service: signed_url failed for %s/%s (%s) — storing key only",
            SELLOUT_BUCKET,
            key,
            exc,
        )
        return f"{SELLOUT_BUCKET}://{key}"


def _insert_row(db: Any, payload: dict[str, Any]) -> dict[str, Any]:
    res = db.table(SELLOUT_TABLE).insert(payload).execute()
    if not res.data:
        raise SubmissionError("Falha ao gravar relatório de sellout")
    return res.data[0]


def _schedule_email(coro) -> None:
    """Fire-and-forget email delivery without blocking the request.

    Falls back to direct asyncio.run when no loop is running (e.g. sync
    contexts in tests). Never raises into the caller.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        try:
            asyncio.run(coro)
        except Exception as exc:
            logger.warning("sellout_service: email send failed (%s)", exc)


async def _notify_admin_submission(
    *,
    org_id: Optional[str],
    distributor_id: str,
    submission_mode: str,
    admin_email: Optional[str],
) -> None:
    if not admin_email:
        logger.debug("sellout_service: no admin_email — skipping notification")
        return
    digest = Digest(
        subject=f"[AdConnect] Novo sellout {submission_mode} — distribuidor {distributor_id}",
        text=(
            f"Um novo relatório de sellout foi submetido pelo distribuidor "
            f"{distributor_id} (modo: {submission_mode}). Acesse o painel "
            f"para revisar."
        ),
    )
    try:
        await send_to_one(digest, recipient=admin_email, org_id=org_id, log_prefix="ADCONNECT_SELLOUT")
    except Exception as exc:
        logger.warning("sellout_service: notification email failed (%s)", exc)


async def submit_estruturado(
    db: Any,
    *,
    org_id: Optional[str],
    distributor_id: str,
    submitted_by: Optional[str],
    valor_total: float,
    quantidade_itens: int,
    periodo: Optional[str] = None,
    cnpj_cliente_final: Optional[str] = None,
    descricao_resumida: Optional[str] = None,
    items_json: Optional[list[dict[str, Any]]] = None,
    observacoes: Optional[str] = None,
    admin_email: Optional[str] = None,
) -> dict[str, Any]:
    if valor_total < 0:
        raise SubmissionError("valor_total não pode ser negativo")
    if quantidade_itens < 0:
        raise SubmissionError("quantidade_itens não pode ser negativa")
    payload: dict[str, Any] = {
        "org_id": org_id,
        "distributor_id": distributor_id,
        "submitted_by": submitted_by,
        "submission_mode": "estruturado",
        "periodo": periodo,
        "cnpj_cliente_final": cnpj_cliente_final,
        "valor_total": valor_total,
        "quantidade_itens": quantidade_itens,
        "descricao_resumida": descricao_resumida,
        "items_json": items_json,
        "observacoes": observacoes,
        "status": "pendente",
        "submitted_at": _now_iso(),
    }
    row = _insert_row(db, payload)
    await _notify_admin_submission(
        org_id=org_id,
        distributor_id=distributor_id,
        submission_mode="estruturado",
        admin_email=admin_email,
    )
    return row


async def submit_nfe(
    db: Any,
    *,
    org_id: Optional[str],
    distributor_id: str,
    submitted_by: Optional[str],
    xml_bytes: bytes,
    filename: str,
    periodo: Optional[str] = None,
    observacoes: Optional[str] = None,
    storage: Optional[StorageBackend] = None,
    admin_email: Optional[str] = None,
) -> dict[str, Any]:
    if not xml_bytes:
        raise SubmissionError("Arquivo NF-e vazio")
    backend = storage or _default_storage
    try:
        parsed = parse_nfe_xml(xml_bytes, strict=False)
    except NFeParseError as exc:
        raise SubmissionError(f"NF-e inválida: {exc}") from exc

    nfe_url = await _upload_blob(
        backend,
        distributor_id=distributor_id,
        filename=filename,
        data=xml_bytes,
        content_type="application/xml",
    )

    payload: dict[str, Any] = {
        "org_id": org_id,
        "distributor_id": distributor_id,
        "submitted_by": submitted_by,
        "submission_mode": "nfe_xml",
        "periodo": periodo,
        "observacoes": observacoes,
        "nfe_xml_url": nfe_url,
        "status": "pendente",
        "submitted_at": _now_iso(),
        **parsed.as_payload(),
    }
    row = _insert_row(db, payload)
    await _notify_admin_submission(
        org_id=org_id,
        distributor_id=distributor_id,
        submission_mode="nfe_xml",
        admin_email=admin_email,
    )
    return row


async def submit_attachment(
    db: Any,
    *,
    org_id: Optional[str],
    distributor_id: str,
    submitted_by: Optional[str],
    file_bytes: bytes,
    filename: str,
    content_type: str,
    periodo: Optional[str] = None,
    observacoes: Optional[str] = None,
    storage: Optional[StorageBackend] = None,
    admin_email: Optional[str] = None,
) -> dict[str, Any]:
    if not file_bytes:
        raise SubmissionError("Anexo vazio")
    backend = storage or _default_storage
    attachment_url = await _upload_blob(
        backend,
        distributor_id=distributor_id,
        filename=filename,
        data=file_bytes,
        content_type=content_type or "application/octet-stream",
    )
    payload: dict[str, Any] = {
        "org_id": org_id,
        "distributor_id": distributor_id,
        "submitted_by": submitted_by,
        "submission_mode": "attachment",
        "periodo": periodo,
        "observacoes": observacoes,
        "attachment_url": attachment_url,
        "status": "pendente",
        "submitted_at": _now_iso(),
    }
    row = _insert_row(db, payload)
    await _notify_admin_submission(
        org_id=org_id,
        distributor_id=distributor_id,
        submission_mode="attachment",
        admin_email=admin_email,
    )
    return row


async def review(
    db: Any,
    *,
    relatorio_id: str,
    status: str,
    review_notes: Optional[str],
    reviewed_by: Optional[str],
    distributor_email: Optional[str] = None,
    org_id: Optional[str] = None,
) -> dict[str, Any]:
    """Brand-admin review write. Returns the updated row."""
    if status not in {"aprovado", "rejeitado"}:
        raise SubmissionError("status deve ser 'aprovado' ou 'rejeitado'")
    payload = {
        "status": status,
        "review_notes": review_notes,
        "reviewed_by": reviewed_by,
        "reviewed_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    res = db.table(SELLOUT_TABLE).update(payload).eq("id", relatorio_id).execute()
    if not res.data:
        raise SubmissionError("Relatório não encontrado")
    row = res.data[0]
    if distributor_email:
        digest = Digest(
            subject=f"[AdConnect] Sellout {status}",
            text=(
                f"Seu relatório de sellout foi {status}. "
                + (f"Notas do revisor: {review_notes}" if review_notes else "")
            ),
        )
        try:
            await send_to_one(
                digest,
                recipient=distributor_email,
                org_id=org_id,
                log_prefix="ADCONNECT_SELLOUT_REVIEW",
            )
        except Exception as exc:
            logger.warning("sellout_service: review email failed (%s)", exc)
    return row


__all__ = [
    "SELLOUT_BUCKET",
    "SELLOUT_TABLE",
    "SubmissionError",
    "configure_storage",
    "review",
    "submit_attachment",
    "submit_estruturado",
    "submit_nfe",
]
