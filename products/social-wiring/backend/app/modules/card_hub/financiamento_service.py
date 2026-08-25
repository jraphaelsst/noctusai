"""Financiamento / Escritura — the deal's closing paperwork (migration 078).

One set per ATENDIMENTO, not per person: a certidão de casamento belongs to
the transaction rather than to either spouse, and filing it under one of them
would make it invisible from the other's card.

🔴 THESE DOCUMENTS ARE LGPD-RELEVANT
------------------------------------
An imposto de renda com recibo de entrega is a person's full declared income;
a carteira de trabalho is their employment history; extratos do FGTS are their
savings. Unlike `imovel_documentos` (public registry documents about a
property), every CONTENT read here appends to an access log — the store is
constructed with `acessos_table` set, which is what turns that on.

WHY THE FGTS DOCUMENTS LIVE HERE AND NOT IN THEIR OWN TABLE
-----------------------------------------------------------
See migration 078's header: an FGTS table whose entire contents are four file
uploads would hold an id, an org_id and nothing else. The four are
`tipo_documento` values in this table, and the UI groups them under a section
that appears when `fgts` is on.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.exceptions import ValidationError_

from app.modules.card_hub import services as svc
from app.modules.card_hub.deps import BUCKET
from app.services import table_reads
from app.services.documento_store import DocumentoStore, now_iso

TABLE = "atendimento_financiamento"

SITUACOES: tuple[str, ...] = ("pendente", "aprovado", "recusado")

#: The escritura/financiamento set — always shown.
TIPOS_ESCRITURA: tuple[str, ...] = (
    "certidao_casamento",
    "escritura_pacto",
    "registro_pacto",
    "comprovante_residencia",
)

#: The FGTS set — shown only when `fgts` is on. Separate tuple, not a flag on
#: each type: the UI needs the GROUPING, and deriving a group from a naming
#: convention is how a new type silently lands in the wrong section.
TIPOS_FGTS: tuple[str, ...] = (
    "imposto_renda_com_recibo",
    "carteira_trabalho",
    "extratos_fgts",
    "comprovante_residencia_1ano",
)

TIPOS_DOCUMENTO: tuple[str, ...] = TIPOS_ESCRITURA + TIPOS_FGTS

#: 25 MB — an imposto de renda PDF with its recibo, or a photographed carteira
#: de trabalho. Between the client-document ceiling and the imóvel's, and free
#: to move independently of both.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_MIME_TYPES = frozenset(
    {"application/pdf", "image/jpeg", "image/png", "image/webp"}
)

#: 🔴 `acessos_table` is SET — the switch that makes this surface LGPD-logged.
STORE = DocumentoStore(
    table="atendimento_documentos",
    owner_col="atendimento_id",
    prefixo="atendimentos",
    bucket=BUCKET,
    tipos=TIPOS_DOCUMENTO,
    max_bytes=MAX_UPLOAD_BYTES,
    mimes=ALLOWED_MIME_TYPES,
    acessos_table="atendimento_documento_acessos",
)

CAMPOS_EDITAVEIS: tuple[str, ...] = ("situacao", "situacao_motivo", "fgts", "observacoes")


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _linha(client: Any, org_id: UUID, atendimento_id: UUID) -> Optional[dict]:
    rows = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento_id))
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def _documento_out(row: dict, resolved: dict) -> dict:
    return {
        "id": row["id"],
        "nome_original": row["nome_original"],
        "mime_type": row["mime_type"],
        "tamanho_bytes": row["tamanho_bytes"],
        "tipo_documento": row["tipo_documento"],
        "grupo": "fgts" if row["tipo_documento"] in TIPOS_FGTS else "escritura",
        "categoria_lgpd": row.get("categoria_lgpd"),
        "retencao_ate": row.get("retencao_ate"),
        "enviado_por": table_reads.actor(resolved, row.get("enviado_por")),
        "created_at": row["created_at"],
    }


def _saida(row: Optional[dict], atendimento_id: UUID, documentos: list[dict]) -> dict:
    """An atendimento with no financiamento row reads as `pendente`, empty.

    Not a 404: no financing recorded is the normal state of a deal that has
    not reached the bank yet.
    """
    base = row or {
        "atendimento_id": str(atendimento_id),
        "situacao": "pendente",
        "situacao_em": None,
        "situacao_motivo": None,
        "fgts": False,
        "observacoes": None,
        "created_at": None,
        "updated_at": None,
    }
    return {
        "atendimento_id": str(atendimento_id),
        "situacao": base.get("situacao", "pendente"),
        "situacao_em": base.get("situacao_em"),
        "situacao_motivo": base.get("situacao_motivo"),
        "fgts": bool(base.get("fgts")),
        "observacoes": base.get("observacoes"),
        "created_at": base.get("created_at"),
        "updated_at": base.get("updated_at"),
        "existe": row is not None,
        # The two groups are returned SEPARATELY rather than as one list with a
        # `grupo` field to sort by — the UI renders them as two sections, and
        # sorting a mixed list at every call site is how one of them ends up
        # showing the other's documents.
        "tipos_escritura": list(TIPOS_ESCRITURA),
        "tipos_fgts": list(TIPOS_FGTS),
        "documentos": documentos,
    }


def obter(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    row = _linha(client, org_id, atendimento_id)
    linhas = STORE.listar_linhas(client, org_id, atendimento_id)
    resolved = table_reads.resolve_actors(
        {r["enviado_por"] for r in linhas if r.get("enviado_por")}
    )
    documentos = [_documento_out(r, resolved) for r in linhas]
    return _saida(row, atendimento_id, documentos)


def atualizar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    valores: dict,
    usuario_id: Optional[UUID],
) -> dict:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))

    recusados = sorted(set(valores) - set(CAMPOS_EDITAVEIS))
    if recusados:
        raise ValidationError_(
            f"Campos não editáveis: {', '.join(recusados)}", field=recusados[0]
        )
    if "situacao" in valores and valores["situacao"] not in SITUACOES:
        raise ValidationError_(
            f"situacao inválida: {valores['situacao']!r}. "
            f"Permitidas: {', '.join(SITUACOES)}",
            field="situacao",
        )

    atual = _linha(client, org_id, atendimento_id)
    patch = {k: v for k, v in valores.items() if k in CAMPOS_EDITAVEIS}

    # A decision is stamped when it CHANGES, not on every save — otherwise
    # "when was this approved" silently becomes "when was this last edited".
    if "situacao" in patch and patch["situacao"] != (atual or {}).get("situacao"):
        patch["situacao_em"] = now_iso()
        patch["situacao_por"] = str(usuario_id) if usuario_id else None

    if atual is None:
        _t(client, TABLE).insert(
            {
                "atendimento_id": str(atendimento_id),
                "org_id": str(org_id),
                "situacao": "pendente",
                "fgts": False,
                "created_at": now_iso(),
                "created_por": str(usuario_id) if usuario_id else None,
                **patch,
            }
        ).execute()
    else:
        patch["updated_at"] = now_iso()
        patch["updated_por"] = str(usuario_id) if usuario_id else None
        _t(client, TABLE).update(patch).eq("org_id", str(org_id)).eq(
            "atendimento_id", str(atendimento_id)
        ).execute()

    return obter(client, org_id, cliente_id)


# ─── Documents ──────────────────────────────────────────────────────────


async def upload(
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
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    row = await STORE.guardar(
        client,
        storage,
        org_id,
        atendimento_id,
        filename=filename,
        content_type=content_type,
        data=data,
        tipo_documento=tipo_documento,
        enviado_por=enviado_por,
        extra={
            "categoria_lgpd": "financeiro",
            "delete_solicitado_por": None,
            # No retention clock is SET here: the correct span for a
            # transaction's paperwork is the transaction's own record-keeping
            # obligation, which nobody has stated yet. Left null and visible
            # rather than guessed — a wrong clock deletes evidence.
            "retencao_ate": None,
        },
    )
    resolved = table_reads.resolve_actors(
        {row["enviado_por"]} if row["enviado_por"] else set()
    )
    return _documento_out(row, resolved)


async def url_do_documento(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    cliente_id: UUID,
    documento_id: UUID,
    *,
    usuario_id: Optional[UUID],
    intent: str = "view",
) -> dict:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    return await STORE.url(
        client,
        storage,
        org_id,
        atendimento_id,
        documento_id,
        usuario_id=usuario_id,
        intent=intent,
    )


def remover(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    documento_id: UUID,
    *,
    motivo: str,
    usuario_id: Optional[UUID],
) -> None:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    STORE.remover(
        client,
        org_id,
        atendimento_id,
        documento_id,
        motivo=motivo,
        usuario_id=usuario_id,
    )


def listar_acessos(
    client: Any, org_id: UUID, cliente_id: UUID, documento_id: UUID
) -> dict:
    _ = svc.resolve_atendimento_id(client, org_id, cliente_id)
    rows = STORE.listar_acessos(client, org_id, documento_id)
    resolved = table_reads.resolve_actors(
        {r["usuario_id"] for r in rows if r.get("usuario_id")}
    )
    items = [
        {
            "id": r["id"],
            "acao": r["acao"],
            "usuario": table_reads.actor(resolved, r.get("usuario_id")),
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    return {"items": items, "total": len(items)}


__all__ = [
    "ALLOWED_MIME_TYPES",
    "CAMPOS_EDITAVEIS",
    "MAX_UPLOAD_BYTES",
    "SITUACOES",
    "STORE",
    "TIPOS_DOCUMENTO",
    "TIPOS_ESCRITURA",
    "TIPOS_FGTS",
    "atualizar",
    "listar_acessos",
    "obter",
    "remover",
    "upload",
    "url_do_documento",
]
