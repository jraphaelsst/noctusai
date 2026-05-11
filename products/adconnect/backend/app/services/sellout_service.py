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
from datetime import date, datetime, timezone
from typing import Any, Optional, Protocol

from noctusai_lib.integrations.email import Digest, send_to_one
from noctusai_lib.integrations.storage import FakeStorageBackend, StorageBackend
from noctusai_lib.primitives.timeutil import now_utc_iso

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


def _iso_date(value: Any) -> Optional[str]:
    """Coerce a date / datetime / ISO-string into the ISO-date string the
    DB expects. Accepts None → None for callers that don't carry period
    fields (e.g. nfe_xml flow when XML lacks period coverage)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


async def submit_estruturado(
    db: Any,
    *,
    org_id: Optional[str],
    distributor_id: str,
    submitted_by: Optional[str],
    valor_total: float,
    quantidade_itens: int,
    periodo_inicio: Optional[Any] = None,
    periodo_fim: Optional[Any] = None,
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
    # `org_id` is intentionally NOT in the payload — `relatorios_sellout`
    # has no `org_id` column; tenant scoping flows through
    # `distributor_id → distributors.org_id` via RLS. Kept as a kwarg for
    # the notification email (admin lookup) only.
    payload: dict[str, Any] = {
        "distributor_id": distributor_id,
        "submitted_by": submitted_by,
        "submission_mode": "estruturado",
        "periodo_inicio": _iso_date(periodo_inicio),
        "periodo_fim": _iso_date(periodo_fim),
        "cnpj_cliente_final": cnpj_cliente_final,
        "valor_total": valor_total,
        "quantidade_itens": quantidade_itens,
        "descricao_resumida": descricao_resumida,
        "items_json": items_json,
        "observacoes": observacoes,
        "status": "pendente",
        "submitted_at": now_utc_iso(),
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
    periodo_inicio: Optional[Any] = None,
    periodo_fim: Optional[Any] = None,
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

    # `org_id` is intentionally NOT in the payload — see submit_estruturado.
    payload: dict[str, Any] = {
        "distributor_id": distributor_id,
        "submitted_by": submitted_by,
        "submission_mode": "nfe_xml",
        "periodo_inicio": _iso_date(periodo_inicio),
        "periodo_fim": _iso_date(periodo_fim),
        "observacoes": observacoes,
        "nfe_xml_url": nfe_url,
        "status": "pendente",
        "submitted_at": now_utc_iso(),
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
    periodo_inicio: Optional[Any] = None,
    periodo_fim: Optional[Any] = None,
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
    # `org_id` is intentionally NOT in the payload — see submit_estruturado.
    # `submission_mode` is `freeform` per DB CHECK; the route is still
    # named `/upload-attachment` because that's the UX surface (frontend
    # already labels the persisted mode `freeform`).
    payload: dict[str, Any] = {
        "distributor_id": distributor_id,
        "submitted_by": submitted_by,
        "submission_mode": "freeform",
        "periodo_inicio": _iso_date(periodo_inicio),
        "periodo_fim": _iso_date(periodo_fim),
        "observacoes": observacoes,
        "attachment_url": attachment_url,
        "status": "pendente",
        "submitted_at": now_utc_iso(),
    }
    row = _insert_row(db, payload)
    await _notify_admin_submission(
        org_id=org_id,
        distributor_id=distributor_id,
        submission_mode="freeform",
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
    """Brand-admin review write. Returns the updated row.

    DB CHECK constrains `status` to ('pendente','em_analise','aprovado',
    'recusado') — the reviewer uses the terminal pair only. Pre-fix the
    code accepted `'rejeitado'` which would CHECK-violate on write.
    """
    if status not in {"aprovado", "recusado"}:
        raise SubmissionError("status deve ser 'aprovado' ou 'recusado'")
    payload = {
        "status": status,
        "review_notes": review_notes,
        "reviewed_by": reviewed_by,
        "reviewed_at": now_utc_iso(),
        "updated_at": now_utc_iso(),
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
