"""Read a birthdate off an uploaded identity document, once, and record why.

WHAT THIS IS FOR
----------------
`data_nascimento` is the one checklist item this product can satisfy without
asking a human to retype something they already sent us. When an RG or a CPF
lands, the date is on it; the operator should not have to read it off a scan
and key it in.

Because the checklist is DERIVED (`documento_checklist_service`), filling the
column is the whole job — the tick follows on the next read with nothing to
notify and nothing to keep in sync.

🔴 THREE RULES THIS MODULE WILL NOT BEND
----------------------------------------
1. **Only a high-confidence read is written.** The extractor returns a
   confidence, and `IdentityFields.persistable` is the gate. A low-confidence
   read is kept ON THE DOCUMENT ROW as a suggestion for a human to confirm and
   never touches the client record. Storing a guess as a fact is worse than
   storing nothing: nothing is visibly missing, a wrong birthday is not.

2. **First writer wins; a human always outranks the machine.** "Whichever
   comes first" between RG and CPF means exactly that — an existing
   `data_nascimento` is never overwritten, and one whose origin is `manual` is
   never touched even if it is somehow empty-ish. Re-uploading a document must
   not silently rewrite a value someone already corrected by hand.

3. **Extraction is a logged content access.** Opening the bytes is a read
   under migration 057's contract, so it appends to `cliente_documento_acessos`
   with `acao='extract'` (migration 068 widened the CHECK for it). Logging it
   as a `view` by a null user would launder a machine read as a human one and
   break the one question the log exists to answer.

WHY THIS RUNS IN THE BACKGROUND
-------------------------------
The ladder's second rung rasterizes pages and calls a vision model — seconds
to tens of seconds. Doing that inline would make uploading a document feel
broken, and would couple a successful upload to an LLM provider being up. The
upload commits; the read happens after, and its own failure is recorded on the
document rather than lost.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.documents import (
    IdentityFields,
    make_identity_extractor,
)
from noctusai_lib.integrations.storage import StorageBackend

from app.modules.card_hub.deps import BUCKET
from app.modules.card_hub.services import _now, _t

logger = logging.getLogger(__name__)

DOCUMENTOS_TABLE = "cliente_documentos"
CLIENTES_TABLE = "clientes"

#: Document types worth reading a birthdate off. Kept separate from
#: `cliente_documento_tipos.identidade` on purpose: that flag drives LGPD
#: retention policy, this drives a processing decision, and letting one
#: silently change the other is how a retention edit turns into an unplanned
#: OCR bill.
#:
#: `cnh` is listed but is NOT currently a row in `cliente_documento_tipos`
#: (migration 057 seeds rg/cpf only), so no CNH can be uploaded and this entry
#: is unreachable today. It is here because the extractor already classifies
#: and reads one — adding the type later is then a data change, not a code
#: change. Stated rather than left to be discovered as a puzzling dead branch.
TIPOS_EXTRAIVEIS = frozenset({"rg", "cpf", "cnh"})


def deve_extrair(tipo_documento: str) -> bool:
    """Is this a document we read fields from?"""
    return tipo_documento in TIPOS_EXTRAIVEIS


def _marcar(client: Any, documento_id: UUID, **updates: Any) -> None:
    _t(client, DOCUMENTOS_TABLE).update(updates).eq("id", str(documento_id)).execute()


def _log_acesso_extracao(client: Any, org_id: UUID, documento_id: UUID) -> None:
    """Append the machine read to the access log.

    `usuario_id` is null because no user performed it — that is the honest
    record, and `acao='extract'` is what keeps it distinguishable from a
    human's `view` rather than hiding inside it.
    """
    from uuid import uuid4

    _t(client, "cliente_documento_acessos").insert(
        {
            "id": str(uuid4()),
            "org_id": str(org_id),
            "documento_id": str(documento_id),
            "usuario_id": None,
            "acao": "extract",
            "created_at": _now(),
        }
    ).execute()


def _aplicar_ao_cliente(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    documento_id: UUID,
    tipo_documento: str,
    fields: IdentityFields,
) -> bool:
    """Write the birthdate onto the client, if and only if it may be written.

    Returns whether the client record was actually changed, so the caller can
    tell "read it and used it" from "read it and correctly declined to".
    """
    if not fields.persistable:
        return False

    rows = (
        _t(client, CLIENTES_TABLE)
        .select("data_nascimento,data_nascimento_origem")
        .eq("org_id", str(org_id))
        .eq("id", str(cliente_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return False

    atual = rows[0]
    # Rule 2. A value already present wins — whichever document arrived first,
    # and anything a human typed, outranks this read.
    if atual.get("data_nascimento") or atual.get("data_nascimento_origem") == "manual":
        return False

    _t(client, CLIENTES_TABLE).update(
        {
            "data_nascimento": fields.data_nascimento.isoformat(),
            "data_nascimento_origem": tipo_documento,
            "data_nascimento_documento_id": str(documento_id),
            "data_nascimento_em": _now(),
            "updated_at": _now(),
        }
    ).eq("id", str(cliente_id)).execute()
    return True


async def extrair_identidade(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    cliente_id: UUID,
    documento_id: UUID,
    *,
    extractor: Optional[Any] = None,
) -> dict:
    """Read one identity document and record the outcome. Never raises.

    Runs detached from the request that triggered it, so an exception here
    would surface nowhere and the document would sit in `processando` forever.
    Every failure path therefore ends in a recorded `extracao_status`, which is
    also what makes a retry sweep possible later.
    """
    rows = (
        _t(client, DOCUMENTOS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(documento_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        logger.warning("extracao: documento %s not found for org %s", documento_id, org_id)
        return {"status": "erro", "erro": "documento_nao_encontrado"}

    doc = rows[0]
    if doc.get("deleted_at"):
        # Deleted between upload and this job. Reading its bytes now would be
        # an access to something the client asked us to forget.
        return {"status": "erro", "erro": "documento_removido"}
    if not deve_extrair(doc["tipo_documento"]):
        return {"status": "erro", "erro": "tipo_nao_extraivel"}

    _marcar(client, documento_id, extracao_status="processando", extracao_em=_now())

    try:
        blob = await storage.get(bucket=BUCKET, key=doc["storage_path"])
    except Exception as exc:  # noqa: BLE001 - detached job; record, never raise
        logger.warning("extracao %s: storage read failed: %s", documento_id, exc)
        _marcar(
            client, documento_id,
            extracao_status="erro", extracao_erro=f"storage: {exc}", extracao_em=_now(),
        )
        return {"status": "erro", "erro": "storage"}

    if blob is None:
        _marcar(
            client, documento_id,
            extracao_status="erro", extracao_erro="objeto ausente no storage",
            extracao_em=_now(),
        )
        return {"status": "erro", "erro": "objeto_ausente"}

    # Rule 3 — logged BEFORE the read, so a crash mid-extraction still leaves
    # the access recorded. An access log that only records successful reads is
    # not an access log.
    _log_acesso_extracao(client, org_id, documento_id)

    extractor = extractor or make_identity_extractor(real=True, org_id=str(org_id))
    fields: IdentityFields = await extractor.extract(
        blob.data,
        mimetype=doc.get("mime_type"),
        filename=doc.get("nome_original"),
    )

    if fields.error:
        _marcar(
            client, documento_id,
            extracao_status="erro",
            extracao_erro=f"{fields.error}: {fields.error_message or ''}".strip(": "),
            extracao_fonte=fields.source.value,
            extracao_em=_now(),
        )
        return {"status": "erro", "erro": fields.error}

    # Recorded whether or not it is persistable — a low-confidence read is a
    # suggestion the card can offer, and `extracao_rotulo` lets a human audit
    # the reasoning without re-opening the document (another logged access).
    _marcar(
        client,
        documento_id,
        extracao_status="ok" if fields.data_nascimento else "sem_dados",
        extracao_data_nascimento=(
            fields.data_nascimento.isoformat() if fields.data_nascimento else None
        ),
        extracao_confianca=fields.confidence.value,
        extracao_fonte=fields.source.value,
        extracao_rotulo=fields.matched_label,
        extracao_erro=None,
        extracao_em=_now(),
    )

    aplicado = _aplicar_ao_cliente(
        client, org_id, cliente_id, documento_id, doc["tipo_documento"], fields
    )
    return {
        "status": "ok" if fields.data_nascimento else "sem_dados",
        "data_nascimento": (
            fields.data_nascimento.isoformat() if fields.data_nascimento else None
        ),
        "confianca": fields.confidence.value,
        "fonte": fields.source.value,
        "aplicado_ao_cliente": aplicado,
    }


__all__ = [
    "TIPOS_EXTRAIVEIS",
    "deve_extrair",
    "extrair_identidade",
]
