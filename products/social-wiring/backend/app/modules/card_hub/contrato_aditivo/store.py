"""Aditivo persistence (migration 190) — rows, the restated schedule, the
generated versions. Pure IO; no wording, no gate.

- `ordinal` is max+1 over EVERY aditivo of the contract, deleted or not —
  never reused (the migration's UNIQUE index makes a mistake loud);
- a present `parcelas` list REPLACES the schedule (delete + insert, ordem =
  list position);
- content (`alteracoes`, `parcelas`, `estilo`) is frozen once the aditivo
  is `assinado` or `cancelado` — a signed instrument is cited by its words;
- a jump to a "final" status (`enviado_assinatura`/`assinado`) is refused
  while the current version awaits the legal review — the contract's own
  rule (`contratos_service.STATUSES_FINAIS`, migration 177);
- versions reuse `DocumentoStore` (LGPD access log on) and the contract's
  version projection (`contratos_service.saida_versao`).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.primitives.exceptions import AppException, ConflictError, NotFoundError

from app.modules.card_hub import contratos_service as contratos_svc
from app.modules.card_hub import services as svc
from app.modules.card_hub.contrato_aditivo.dados import (
    DadosAditivo,
    alteracoes_de_json,
    alteracoes_para_json,
)
from app.modules.card_hub.contrato_gerador.dados import Parcela
from app.modules.card_hub.deps import BUCKET
from app.services import table_reads
from app.services.documento_store import DocumentoStore, SidecarArquivo, now_iso

TABLE = "atendimento_contrato_aditivos"
TABLE_PARCELAS = "atendimento_contrato_aditivo_parcelas"
TIPO_VERSAO = "aditivo"

#: Statuses that freeze the aditivo's content.
STATUSES_CONGELADOS: tuple[str, ...] = ("assinado", "cancelado")

#: 🔴 `acessos_table` SET — an aditivo re-qualifies every party (LGPD).
VERSOES_STORE = DocumentoStore(
    table="atendimento_contrato_aditivo_versoes",
    owner_col="aditivo_id",
    prefixo="contratos-aditivos",
    bucket=BUCKET,
    tipos=(TIPO_VERSAO,),
    max_bytes=contratos_svc.MAX_UPLOAD_BYTES,
    mimes=contratos_svc.ALLOWED_MIME_TYPES,
    acessos_table="atendimento_contrato_aditivo_versao_acessos",
)


class OriginalNaoAssinado(AppException):
    def __init__(self) -> None:
        super().__init__(
            code="CONTRATO_ORIGINAL_NAO_ASSINADO",
            message="Só um contrato assinado (ou com data de assinatura) recebe aditivo.",
            status_code=409,
        )


class AditivoCongelado(AppException):
    def __init__(self, status: str) -> None:
        super().__init__(
            code="ADITIVO_CONGELADO",
            message=f"Aditivo {status}: o conteúdo não pode mais ser alterado.",
            status_code=409,
            details={"status": status},
        )


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _dec(valor: Any) -> Optional[Decimal]:
    return None if valor in (None, "") else Decimal(str(valor))


def _data(valor: Any) -> Optional[date]:
    if valor in (None, ""):
        return None
    return valor if isinstance(valor, date) else date.fromisoformat(str(valor)[:10])


# ─── reads ────────────────────────────────────────────────────────────────


def contexto_contrato(
    client: Any, org_id: UUID, cliente_id: UUID, contrato_id: UUID
) -> tuple[UUID, dict]:
    """(atendimento_id, original contract row) — 404 for a foreign/deleted
    contract, through the contract's own lookup."""
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    return atendimento_id, contratos_svc.exigir_contrato(client, org_id, atendimento_id, contrato_id)


def exigir_aditivo(client: Any, org_id: UUID, contrato_id: UUID, aditivo_id: UUID) -> dict:
    rows = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("contrato_id", str(contrato_id))
        .eq("id", str(aditivo_id))
        .execute()
    ).data or []
    if not rows or rows[0].get("deleted_at"):
        raise NotFoundError(TABLE, str(aditivo_id))
    return rows[0]


def parcelas_rows(client: Any, org_id: UUID, aditivo_id: Any) -> list[dict]:
    rows = table_reads.paged_rows(
        client, TABLE_PARCELAS, org_id, eq_filters={"aditivo_id": str(aditivo_id)}
    )
    rows.sort(key=lambda r: r.get("ordem", 0))
    return rows


def dados_aditivo(row: dict, parcelas: list[dict], contrato: dict) -> DadosAditivo:
    return DadosAditivo(
        aditivo_id=str(row["id"]),
        contrato_id=str(row["contrato_id"]),
        ordinal=int(row["ordinal"]),
        estilo=row.get("estilo") or "house",
        status=row.get("status") or "rascunho",
        alteracoes=alteracoes_de_json(row.get("alteracoes")),
        parcelas=[
            Parcela(
                id=str(p["id"]),
                tipo=p["tipo"],
                valor=_dec(p.get("valor")),
                vencimento=_data(p.get("vencimento")),
                evento=p.get("evento"),
                forma_pagamento=p.get("forma_pagamento"),
                favorecido_id=str(p["favorecido_id"]) if p.get("favorecido_id") else None,
                confissao_divida=bool(p.get("confissao_divida")),
                ordem=int(p.get("ordem") or 0),
            )
            for p in parcelas
        ],
        assinatura_data=_data(row.get("assinatura_data")),
        modalidade_assinatura=row.get("modalidade_assinatura") or "digital",
        original_status=contrato.get("status") or "rascunho",
        original_assinatura_data=_data(contrato.get("assinatura_data")),
        original_origem=contrato.get("origem") or "upload",
    )


def _parcela_out(p: dict) -> dict:
    valor = _dec(p.get("valor"))
    return {
        "id": p["id"],
        "tipo": p["tipo"],
        "valor": None if valor is None else str(valor),
        "vencimento": p.get("vencimento"),
        "evento": p.get("evento"),
        "forma_pagamento": p.get("forma_pagamento"),
        "favorecido_id": p.get("favorecido_id"),
        "confissao_divida": bool(p.get("confissao_divida")),
        "ordem": p.get("ordem", 0),
    }


def saida(client: Any, org_id: UUID, row: dict) -> dict:
    linhas = VERSOES_STORE.listar_linhas(client, org_id, UUID(str(row["id"])))
    linhas.sort(key=lambda r: r["numero"], reverse=True)
    ids = {r["enviado_por"] for r in linhas if r.get("enviado_por")}
    ids |= {r["revisado_por"] for r in linhas if r.get("revisado_por")}
    if row.get("status_por"):
        ids.add(row["status_por"])
    resolved = table_reads.resolve_actors(ids)
    versoes = [contratos_svc.saida_versao(r, resolved) for r in linhas]
    return {
        "id": row["id"],
        "contrato_id": row["contrato_id"],
        "ordinal": row["ordinal"],
        "estilo": row.get("estilo") or "house",
        "status": row["status"],
        "status_em": row.get("status_em"),
        "status_por": table_reads.actor(resolved, row.get("status_por")),
        "alteracoes": alteracoes_para_json(alteracoes_de_json(row.get("alteracoes"))),
        "parcelas": [_parcela_out(p) for p in parcelas_rows(client, org_id, row["id"])],
        "assinatura_data": row.get("assinatura_data"),
        "modalidade_assinatura": row.get("modalidade_assinatura") or "digital",
        "created_at": row["created_at"],
        "updated_at": row.get("updated_at"),
        "versao_atual": versoes[0] if versoes else None,
        "versoes": versoes,
    }


def listar(client: Any, org_id: UUID, cliente_id: UUID, contrato_id: UUID) -> dict:
    contexto_contrato(client, org_id, cliente_id, contrato_id)
    rows = table_reads.paged_rows(
        client,
        TABLE,
        org_id,
        eq_filters={"contrato_id": str(contrato_id)},
        refine=lambda q: q.is_("deleted_at", "null"),
    )
    rows.sort(key=lambda r: r["ordinal"])
    return {"aditivos": [saida(client, org_id, r) for r in rows]}


# ─── writes ───────────────────────────────────────────────────────────────


def _proximo_ordinal(client: Any, org_id: UUID, contrato_id: UUID) -> int:
    """max+1 over EVERY row, deleted or not — see this module's header."""
    # postgrest-unbounded-ok: one contract's aditivos (a handful); the UNIQUE
    # (contrato_id, ordinal) index turns a stale max into a loud failure.
    rows = (
        _t(client, TABLE)
        .select("ordinal")
        .eq("org_id", str(org_id))
        .eq("contrato_id", str(contrato_id))
        .execute()
    ).data or []
    return max((r["ordinal"] for r in rows), default=0) + 1


def _gravar_parcelas(
    client: Any, org_id: UUID, atendimento_id: UUID, aditivo_id: str, parcelas: list[dict]
) -> None:
    for p in parcelas:
        if p.get("favorecido_id"):
            # 404 for a favorecido of another deal — the same lookup the
            # negociação parcelas use (`atendimento_favorecidos`).
            rows = (
                _t(client, "atendimento_favorecidos")
                .select("id")
                .eq("org_id", str(org_id))
                .eq("atendimento_id", str(atendimento_id))
                .eq("id", str(p["favorecido_id"]))
                .execute()
            ).data or []
            if not rows:
                raise NotFoundError("atendimento_favorecidos", str(p["favorecido_id"]))
    _t(client, TABLE_PARCELAS).delete().eq("org_id", str(org_id)).eq("aditivo_id", aditivo_id).execute()
    for ordem, p in enumerate(parcelas):
        _t(client, TABLE_PARCELAS).insert(
            {
                "id": str(uuid4()),
                "org_id": str(org_id),
                "aditivo_id": aditivo_id,
                "tipo": p["tipo"],
                "valor": str(p["valor"]),
                "vencimento": p["vencimento"].isoformat() if p.get("vencimento") else None,
                "evento": p.get("evento"),
                "forma_pagamento": p.get("forma_pagamento"),
                "favorecido_id": str(p["favorecido_id"]) if p.get("favorecido_id") else None,
                "confissao_divida": bool(p.get("confissao_divida")),
                "ordem": ordem,
                "created_at": now_iso(),
            }
        ).execute()


def original_admite_aditivo(contrato: dict) -> bool:
    return contrato.get("status") != "cancelado" and (
        contrato.get("status") == "assinado" or bool(contrato.get("assinatura_data"))
    )


def criar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    contrato_id: UUID,
    *,
    estilo: str,
    alteracoes: list,
    parcelas: list[dict],
    assinatura_data: Optional[date],
    modalidade_assinatura: str,
    usuario_id: Optional[Any],
) -> dict:
    atendimento_id, contrato = contexto_contrato(client, org_id, cliente_id, contrato_id)
    if not original_admite_aditivo(contrato):
        raise OriginalNaoAssinado()
    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "atendimento_id": str(atendimento_id),
        "contrato_id": str(contrato_id),
        "ordinal": _proximo_ordinal(client, org_id, contrato_id),
        "estilo": estilo,
        "status": "rascunho",
        "status_em": None,
        "status_por": None,
        "alteracoes": alteracoes_para_json(alteracoes),
        "assinatura_data": assinatura_data.isoformat() if assinatura_data else None,
        "modalidade_assinatura": modalidade_assinatura,
        "criado_por": str(usuario_id) if usuario_id else None,
        "deleted_at": None,
        "delete_motivo": None,
        "delete_solicitado_por": None,
        "created_at": now_iso(),
        "updated_at": None,
    }
    _t(client, TABLE).insert(row).execute()
    if parcelas:
        _gravar_parcelas(client, org_id, atendimento_id, row["id"], parcelas)
    return saida(client, org_id, exigir_aditivo(client, org_id, contrato_id, UUID(row["id"])))


def _versao_atual(client: Any, org_id: UUID, aditivo_id: UUID) -> Optional[dict]:
    linhas = VERSOES_STORE.listar_linhas(client, org_id, aditivo_id)
    return max(linhas, key=lambda r: r["numero"]) if linhas else None


def atualizar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    contrato_id: UUID,
    aditivo_id: UUID,
    *,
    valores: dict,
    usuario_id: Optional[Any],
) -> dict:
    """`valores` = the PATCH body's set fields (`model_dump(exclude_unset)`
    with `alteracoes` already as models and `parcelas` as dicts)."""
    atendimento_id, _contrato = contexto_contrato(client, org_id, cliente_id, contrato_id)
    atual = exigir_aditivo(client, org_id, contrato_id, aditivo_id)

    conteudo = {"estilo", "alteracoes", "parcelas"} & set(valores)
    if conteudo and atual["status"] in STATUSES_CONGELADOS:
        raise AditivoCongelado(atual["status"])

    novo_status = valores.get("status")
    if novo_status in contratos_svc.STATUSES_FINAIS and novo_status != atual["status"]:
        versao = _versao_atual(client, org_id, aditivo_id)
        if versao is None:
            raise ConflictError(
                "O aditivo não tem versão gerada para enviar à assinatura.", resource=TABLE
            )
        contratos_svc.exigir_revisao_juridica(versao)

    patch: dict = {}
    for campo in ("estilo", "modalidade_assinatura", "status"):
        if campo in valores and valores[campo] is not None:
            patch[campo] = valores[campo]
    if "assinatura_data" in valores:
        patch["assinatura_data"] = (
            valores["assinatura_data"].isoformat() if valores["assinatura_data"] else None
        )
    if "alteracoes" in valores and valores["alteracoes"] is not None:
        patch["alteracoes"] = alteracoes_para_json(valores["alteracoes"])
    if "status" in patch and patch["status"] != atual["status"]:
        patch["status_em"] = now_iso()
        patch["status_por"] = str(usuario_id) if usuario_id else None
    patch["updated_at"] = now_iso()
    _t(client, TABLE).update(patch).eq("org_id", str(org_id)).eq("id", str(aditivo_id)).execute()

    if "parcelas" in valores and valores["parcelas"] is not None:
        _gravar_parcelas(client, org_id, atendimento_id, str(aditivo_id), valores["parcelas"])
    return saida(client, org_id, exigir_aditivo(client, org_id, contrato_id, aditivo_id))


def _proximo_numero(client: Any, org_id: UUID, aditivo_id: UUID) -> int:
    """max(numero)+1 over every version row, deleted or not."""
    # postgrest-unbounded-ok: one aditivo's versions (a handful); the UNIQUE
    # (aditivo_id, numero) index makes a stale max a loud insert failure.
    rows = (
        _t(client, VERSOES_STORE.table)
        .select("numero")
        .eq("org_id", str(org_id))
        .eq("aditivo_id", str(aditivo_id))
        .execute()
    ).data or []
    return max((r["numero"] for r in rows), default=0) + 1


async def nova_versao_gerada(
    client: Any,
    storage: Any,
    org_id: UUID,
    aditivo_id: UUID,
    *,
    pdf: bytes,
    docx: bytes,
    contexto_sha256: str,
    modalidade_assinatura: str,
    revisao_campos: list[dict],
    usuario_id: Optional[Any],
) -> dict:
    """PDF + .docx sibling in ONE insert (the contract's migration-120
    shape) — never insert-then-update; `revisao_campos` is never empty for
    an aditivo, so every generated version is born awaiting the review."""
    numero = _proximo_numero(client, org_id, aditivo_id)
    inserida = await VERSOES_STORE.guardar(
        client,
        storage,
        org_id,
        aditivo_id,
        filename=f"aditivo-gerado-v{numero}.pdf",
        content_type="application/pdf",
        data=pdf,
        tipo_documento=TIPO_VERSAO,
        enviado_por=usuario_id,
        extra={
            "numero": numero,
            "rotulo": None,
            "origem": "gerado",
            "contexto_sha256": contexto_sha256,
            "modalidade_assinatura": modalidade_assinatura,
            "revisao_juridica_campos": [
                {k: c.get(k) for k in contratos_svc.CAMPOS_REVISAO_CHAVES} for c in revisao_campos
            ],
        },
        sidecar=SidecarArquivo(
            data=docx,
            content_type=contratos_svc.MIME_DOCX,
            nome_original=f"aditivo-gerado-v{numero}.docx",
            suffix=".docx",
            storage_path_col="docx_storage_path",
            tamanho_bytes_col="docx_tamanho_bytes",
        ),
    )
    _t(client, TABLE).update({"updated_at": now_iso()}).eq("id", str(aditivo_id)).execute()
    resolved = table_reads.resolve_actors({inserida["enviado_por"]} - {None})
    return contratos_svc.saida_versao(inserida, resolved)


def aprovar_revisao(
    client: Any, org_id: UUID, aditivo_id: UUID, versao_id: UUID, *, usuario_id: Optional[Any]
) -> None:
    versao = VERSOES_STORE.exigir(client, org_id, aditivo_id, versao_id)
    estado = contratos_svc.revisao_juridica_status(versao)
    if estado == contratos_svc.REVISAO_APROVADA:
        raise ConflictError("A revisão jurídica desta versão já foi aprovada.", resource=VERSOES_STORE.table)
    if estado == contratos_svc.REVISAO_NAO_EXIGIDA:
        raise ConflictError("Esta versão não exige revisão jurídica.", resource=VERSOES_STORE.table)
    _t(client, VERSOES_STORE.table).update(
        {"revisado_por": str(usuario_id) if usuario_id else None, "revisado_em": now_iso()}
    ).eq("org_id", str(org_id)).eq("id", str(versao_id)).execute()


__all__ = [
    "AditivoCongelado",
    "OriginalNaoAssinado",
    "STATUSES_CONGELADOS",
    "TABLE",
    "TABLE_PARCELAS",
    "VERSOES_STORE",
    "aprovar_revisao",
    "atualizar",
    "contexto_contrato",
    "criar",
    "dados_aditivo",
    "exigir_aditivo",
    "listar",
    "nova_versao_gerada",
    "original_admite_aditivo",
    "parcelas_rows",
    "saida",
]
