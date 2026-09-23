"""Documents, LGPD-complete (contract §2 `057`, ruling S2 / D5) —
social-wiring's half of them.

The mechanics — upload validation, storage layout, the access log
(`cliente_documento_acessos`), the short-TTL signed URL, LGPD soft delete
with a recorded reason, the retention sweep — are the seed's
`noctusai_lib.domain.card_hub.documentos`, lifted out of THIS file as a MOVE
(wave A, 2026-09-22). The functions below keep their historical
`(client, ...)` signatures as thin shims over it, bound to social-wiring's
`CardHubConfig` (`app.modules.card_hub.config.CARD_HUB`), whose
`DocumentoPolicy` carries what is ABOUT this product: retention read from the
editable policy table (migration 079), and the identity-extraction state
(migration 068) stamped at upload and served on reads. What genuinely stays
here is `reextrair_documento` — the re-run half of that extraction.

Every read of a document's CONTENT (a minted signed URL) and every delete
appends to the access log. Listing document METADATA or listing the access
log itself does NOT — neither one accesses the file's bytes.

Retention is table-driven, never a hardcoded `if`; the upload allow-list is
`ativo = true` on the type catalogue (`cliente_documento_tipos`) — enabling a
withheld type (RG/CPF-class, seeded `ativo = false`) is a data change, not a
deploy. Object path `{org_id}/clientes/{cliente_id}/{document_id}` — see
migration `057`'s object-RLS policies for why the first path segment must
always be the literal `org_id`.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.domain.card_hub import documentos as seed_docs
from noctusai_lib.domain.card_hub.documentos import (
    DOCUMENTO_RESUMO_COLUNAS,
    documento_resumo,
)
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.exceptions import ValidationError_

from app.modules.card_hub import identidade_extracao_service as identidade_svc
from app.modules.card_hub.deps import card_hub_config, get_card_hub_client
from app.modules.card_hub.services import _now, _resolve_actors, _t

logger = logging.getLogger(__name__)

# Conservative server-side limits (contract §3: "Limits enforced
# server-side ... A rejected upload returns a typed error naming the
# limit it hit"). Module-local constants — a fixed platform policy, not
# per-deployment configuration. `app.modules.card_hub.config.CARD_HUB`'s
# `DocumentoPolicy` is built FROM these; they stay the one place the policy
# is written.
#
# This is the REAL business-policy limit, not a value squeezed under the
# platform's flat body-size guard: `app/main.py` declares a per-route
# override for this exact endpoint (`/api/clientes/*/documentos`, 30 MB —
# see that file's `_MAX_BODY_PATH_OVERRIDES` comment), so 25 MB sits
# comfortably under the platform's own ceiling with headroom for multipart
# boundary/header overhead. Covers a phone photo (3-8 MB) and a larger
# HDR/RAW-derived export (25 MB+) — see `_format_bytes_human` for why the
# rejection message stays truthful at both this size AND the legacy 800 KB
# one (which used to integer-divide to a misleading "0MB").
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB — see the note above
ALLOWED_MIME_TYPES = frozenset(
    {"application/pdf", "image/jpeg", "image/png", "image/webp"}
)

#: The retention sweep's scheduler job id. STABLE across releases:
#: re-registering the same id replaces the job, a changed id would register a
#: second sweep next to the first.
RETENTION_SWEEP_JOB_ID = "card_hub_documento_retention_sweep"

_format_bytes_human = seed_docs.format_bytes_human


def list_tipos_documento(client: Any) -> dict:
    return seed_docs.list_tipos_documento(card_hub_config(), client)


def _documento_out(row: dict, resolved_actors: dict) -> dict:
    return seed_docs.documento_out(card_hub_config(), row, resolved_actors)


def list_documentos(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    return seed_docs.list_documentos(card_hub_config(), client, org_id, cliente_id)


async def upload_documento(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    cliente_id: UUID,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    tipo_documento: str,
    enviado_por: Optional[UUID],
) -> dict:
    """Validate → put → insert (seed). `max_bytes` is THIS module's
    `MAX_UPLOAD_BYTES`, read at CALL time — the one place the limit is
    written, not a value frozen into the config when it was built."""
    return await seed_docs.upload_documento(
        card_hub_config(),
        client,
        storage,
        org_id,
        cliente_id,
        filename=filename,
        content_type=content_type,
        data=data,
        tipo_documento=tipo_documento,
        enviado_por=enviado_por,
        max_bytes=MAX_UPLOAD_BYTES,
    )


def _require_documento(client: Any, org_id: UUID, cliente_id: UUID, documento_id: UUID) -> dict:
    return seed_docs.require_documento(card_hub_config(), client, org_id, cliente_id, documento_id)


async def get_documento_url(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    cliente_id: UUID,
    documento_id: UUID,
    *,
    usuario_id: Optional[UUID],
    intent: str = "view",
) -> dict:
    return await seed_docs.get_documento_url(
        card_hub_config(), client, storage, org_id, cliente_id, documento_id,
        usuario_id=usuario_id, intent=intent,
    )


async def delete_documento(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    cliente_id: UUID,
    documento_id: UUID,
    *,
    motivo: str,
    usuario_id: Optional[UUID],
) -> None:
    await seed_docs.delete_documento(
        card_hub_config(), client, storage, org_id, cliente_id, documento_id,
        motivo=motivo, usuario_id=usuario_id,
    )


#: Non-terminal extraction states — mirrors
#: `identidade_extracao_service._ESTADOS_NAO_TERMINAIS` (not imported: that
#: name is private to that module, and the two lists are checked for
#: opposite reasons — the sweep decides what it may STALL-RECOVER, this
#: decides what it must REFUSE to double-schedule).
_EXTRACAO_EM_ANDAMENTO = ("pendente", "processando")


def reextrair_documento(client: Any, org_id: UUID, cliente_id: UUID, documento_id: UUID) -> dict:
    """Re-queue extraction for a document that was never read, or whose
    reading ended in `erro` (contract §4 — the re-run endpoint).

    For a document uploaded before its type was reachable (filed as `outro`
    at the time, or as a since-activated type before this org's LGPD intake
    closed) or whose extraction ended in `erro` (a transient OpenAI 429, a
    once-corrupt storage read), the only recovery before this endpoint was
    delete + re-upload — which destroys the LGPD access history this module
    exists to keep (`cliente_documento_acessos`). This resets the document's
    OWN row back to `pendente` and clears the stale `extracao_erro`; the
    router schedules the SAME background task `upload_documento`'s route
    schedules for a brand-new upload, immediately, rather than waiting for
    `identidade_extracao_service.varrer_extracoes_pendentes`'s next pass.

    Refuses (`ValidationError_`, `field="tipo_documento"`) when the
    document's `tipo_documento` is not one `identidade_svc.deve_extrair`
    reads at all — re-typing an already-uploaded document is a separate,
    prerequisite fix this endpoint cannot make for it.

    Refuses (`ValidationError_`, `field="extracao_status"`) when an
    extraction is already `pendente` or `processando` — a second trigger
    while one is in flight would race the same document row and pay for a
    second vision call for nothing.

    🔴 `extracao_tentativas` IS DELIBERATELY NOT RESET.
    `identidade_extracao_service.MAX_TENTATIVAS` bounds how many times the
    unattended SWEEP may restart a document that stalled — it is not a limit
    on a human explicitly asking to retry, and every click here is already a
    conscious decision, not an automatic loop. Resetting the counter would
    silently hide from that sweep's own accounting how many times a document
    has genuinely been attempted; the response's `extracao_tentativas`
    reports the count UNCHANGED, precisely so this is visible rather than
    implicit — never a bypass of the accounting, just a deliberate choice not
    to touch it.
    """
    documento = _require_documento(client, org_id, cliente_id, documento_id)
    tipo_documento = documento["tipo_documento"]
    if not identidade_svc.deve_extrair(tipo_documento):
        raise ValidationError_(
            f"tipo_documento {tipo_documento!r} não é extraível — nenhuma "
            "leitura de campos está definida para este tipo. Elegíveis: "
            f"{', '.join(sorted(identidade_svc.TIPOS_EXTRAIVEIS))}",
            field="tipo_documento",
        )
    status_atual = documento.get("extracao_status")
    if status_atual in _EXTRACAO_EM_ANDAMENTO:
        raise ValidationError_(
            f"extração já está {status_atual!r} para este documento — "
            "aguarde a conclusão antes de reenviar.",
            field="extracao_status",
        )

    patch = {
        "extracao_status": "pendente",
        "extracao_erro": None,
        "extracao_em": _now(),
    }
    _t(client, "cliente_documentos").update(patch).eq("id", str(documento_id)).execute()
    documento.update(patch)
    resolved = _resolve_actors(
        {documento["enviado_por"]} if documento.get("enviado_por") else set()
    )
    return _documento_out(documento, resolved)


def list_acessos(client: Any, org_id: UUID, cliente_id: UUID, documento_id: UUID) -> dict:
    return seed_docs.list_acessos(card_hub_config(), client, org_id, cliente_id, documento_id)


# ─── Retention sweep ──────────────────────────────────────────────────


def run_retention_sweep(client: Any, org_id: UUID) -> int:
    """Soft-delete every live document past its `retencao_ate` for `org_id`
    (seed body — a `delete` access-log entry attributed to no user). Returns
    the count swept."""
    return seed_docs.run_retention_sweep(card_hub_config(), client, org_id)


def run_retention_sweep_all_orgs(*, client: Any = None) -> int:
    """The scheduled sweep's body — every org, one pass."""
    return seed_docs.run_retention_sweep_all_orgs(
        card_hub_config(), client or get_card_hub_client()
    )


def configure(*, scheduler: Any = None) -> None:
    """Register the retention sweep on the seed-side scheduler — ONCE, under
    the job id this product has always used (`RETENTION_SWEEP_JOB_ID`).
    Called from `app.modules.card_hub.register()` before `start_scheduler()`
    fires in `app/lifespan.py`. `get_card_hub_client` is resolved per run,
    never captured."""
    seed_docs.register_retention_sweep(
        card_hub_config(),
        get_db=get_card_hub_client,
        scheduler=scheduler,
        job_id=RETENTION_SWEEP_JOB_ID,
        hours=24,
    )


__all__ = [
    "ALLOWED_MIME_TYPES",
    "DOCUMENTO_RESUMO_COLUNAS",
    "MAX_UPLOAD_BYTES",
    "RETENTION_SWEEP_JOB_ID",
    "configure",
    "documento_resumo",
    "delete_documento",
    "get_documento_url",
    "list_acessos",
    "list_documentos",
    "list_tipos_documento",
    "reextrair_documento",
    "run_retention_sweep",
    "run_retention_sweep_all_orgs",
    "upload_documento",
]
