"""Contratos — the deal's contract, in revision (migration 106).

WHAT THIS PINS
---------------
- an atendimento may carry more than one contract (an original plus a
  permuta side-letter, for instance) — so this is a LIST, not the one-row-
  per-deal shape `financiamento_service` uses;
- a contract is a STATUS plus a list of immutable VERSIONS, never a file
  replaced in place — legal cites "REV 25.07" and that citation has to keep
  meaning the same bytes forever, including after a later revision lands;
- `numero` is NEVER reused, even past a soft-deleted version — migration
  106's UNIQUE index enforces this across ALL rows, not just live ones;
- 🔴 every CONTENT read of a version appends to the access log, same
  contract `financiamento_service`'s documents carry — a compra e venda
  contract names CPF/RG and bank data for every party;
- a contract cannot be left with zero live versions short of deleting the
  contract itself — "which citation still means something" has to stay
  answerable while the contract exists.

Auth is not re-tested here — `test_auth_boundary.py` enumerates every
mounted card_hub route and asserts a strict 401 on each.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError_,
)

from app.modules.card_hub import services as svc
from app.modules.card_hub.deps import BUCKET
from app.services import table_reads
from app.services.documento_store import (
    SIGNED_URL_TTL_SECONDS,
    DocumentoStore,
    documento_base,
    now_iso,
)

TABLE = "atendimento_contratos"

#: The version store's single `tipo_documento` value — the store's own
#: `validar` is the one place this surface's file-type allow-list lives
#: (migration 078's header), so this is a 1-tuple rather than a CHECK on the
#: `atendimento_contrato_versoes` table.
TIPO_VERSAO = "contrato"

MODELOS: tuple[str, ...] = (
    "compra_venda",
    "compra_venda_permuta",
    "compra_venda_a_vista",
    "outro",
)

STATUSES: tuple[str, ...] = (
    "rascunho",
    "em_revisao",
    "enviado_assinatura",
    "assinado",
    "cancelado",
)

CAMPOS_EDITAVEIS: tuple[str, ...] = (
    "titulo",
    "modelo",
    "status",
    # Migration 114.
    "assinatura_data",
    "prazo_pendencias_dias",
)

#: The docx sibling `nova_versao_gerada` stores beside a gerado version's PDF
#: (migration 120) is always this — never a column, see that migration's
#: header.
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

#: A compra e venda contract PDF/DOCX with its anexos. Same ceiling
#: `financiamento_service` uses for the deal's other closing paperwork.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_MIME_TYPES = frozenset(
    {
        "application/pdf",
        MIME_DOCX,
        "application/msword",
    }
)

#: `_guardar_versao`'s `filename=None` fallback (a GENERATED version has no
#: upload name) names the file from this — an unrecognized `content_type`
#: is a defect elsewhere (`VERSOES_STORE.validar` already refused it before
#: this is ever consulted), never silently mis-extensioned.
_EXTENSAO_GERADA: dict[str, str] = {
    "application/pdf": "pdf",
    MIME_DOCX: "docx",
}

#: 🔴 `acessos_table` is SET — LGPD-logged, same posture as
#: `financiamento_service.STORE`.
VERSOES_STORE = DocumentoStore(
    table="atendimento_contrato_versoes",
    owner_col="contrato_id",
    prefixo="contratos",
    bucket=BUCKET,
    tipos=(TIPO_VERSAO,),
    max_bytes=MAX_UPLOAD_BYTES,
    mimes=ALLOWED_MIME_TYPES,
    acessos_table="atendimento_contrato_versao_acessos",
)


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def exigir_contrato(
    client: Any, org_id: UUID, atendimento_id: UUID, contrato_id: UUID
) -> dict:
    """The live contract row, scoped to this org AND this atendimento.

    404 for a wrong org, a wrong atendimento, or a soft-deleted contract —
    same non-distinguishing shape `DocumentoStore.exigir` uses, so a probe
    cannot tell "not yours" from "does not exist".
    """
    rows = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento_id))
        .eq("id", str(contrato_id))
        .execute()
    ).data or []
    if not rows or rows[0].get("deleted_at"):
        raise NotFoundError(TABLE, str(contrato_id))
    return rows[0]


def _versao_out(row: dict, resolved: dict) -> dict:
    return {
        **documento_base(row, resolved),
        "numero": row["numero"],
        "rotulo": row.get("rotulo"),
        "origem": row.get("origem", "upload"),
        # Migration 120. Always False for an upload; a gerado version has
        # both a PDF (this row's own mime_type/tamanho_bytes) and this docx
        # sibling — `formato=docx` on `.../versoes/{id}/url` needs it.
        "docx_disponivel": bool(row.get("docx_storage_path")),
    }


def _contrato_saida(client: Any, org_id: UUID, row: dict) -> dict:
    contrato_id = UUID(str(row["id"]))
    linhas = VERSOES_STORE.listar_linhas(client, org_id, contrato_id)
    linhas.sort(key=lambda r: r["numero"], reverse=True)

    ids = {r["enviado_por"] for r in linhas if r.get("enviado_por")}
    if row.get("status_por"):
        ids.add(row["status_por"])
    resolved = table_reads.resolve_actors(ids)

    versoes = [_versao_out(r, resolved) for r in linhas]
    return {
        "id": row["id"],
        "atendimento_id": row["atendimento_id"],
        "titulo": row["titulo"],
        "modelo": row["modelo"],
        "status": row["status"],
        "status_em": row.get("status_em"),
        "status_por": table_reads.actor(resolved, row.get("status_por")),
        "origem": row.get("origem", "upload"),
        # Migration 114. `prazo_pendencias_dias` null = the office default.
        "assinatura_data": row.get("assinatura_data"),
        "prazo_pendencias_dias": row.get("prazo_pendencias_dias"),
        "created_at": row["created_at"],
        "updated_at": row.get("updated_at"),
        # Highest `numero` among LIVE versions — `linhas` above already
        # excludes soft-deleted rows (`DocumentoStore.listar_linhas`) and is
        # sorted numero DESC, so the head of the list IS the current version.
        "versao_atual": versoes[0] if versoes else None,
        "versoes": versoes,
    }


def _proximo_numero(client: Any, org_id: UUID, contrato_id: UUID) -> int:
    """max(numero) + 1 over EVERY row for this contrato, deleted or not.

    🔴 Deliberately NOT scoped to live rows — reusing a soft-deleted
    version's number would let a NEW file answer to an old citation
    ("versão 2" would stop meaning the bytes legal actually cited). The
    migration's UNIQUE index on `(contrato_id, numero)` is what turns a
    mistake here into a loud insert failure instead of a silent collision.
    """
    # postgrest-unbounded-ok: one contract's versions (a handful of legal
    # revisions); even past the 1 000-row cap the UNIQUE (contrato_id, numero)
    # index turns a stale max into a loud insert failure, never a reuse.
    rows = (
        _t(client, VERSOES_STORE.table)
        .select("numero")
        .eq("org_id", str(org_id))
        .eq("contrato_id", str(contrato_id))
        .execute()
    ).data or []
    return max((r["numero"] for r in rows), default=0) + 1


# ─── reads ────────────────────────────────────────────────────────────────


def listar(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    rows = table_reads.paged_rows(
        client,
        TABLE,
        org_id,
        eq_filters={"atendimento_id": str(atendimento_id)},
        refine=lambda q: q.is_("deleted_at", "null"),
    )
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return {"contratos": [_contrato_saida(client, org_id, r) for r in rows]}


# ─── writes ───────────────────────────────────────────────────────────────


async def criar(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    cliente_id: UUID,
    *,
    titulo: str,
    modelo: str,
    rotulo: Optional[str],
    filename: str,
    content_type: str,
    data: bytes,
    criado_por: Optional[UUID],
) -> dict:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))

    if modelo not in MODELOS:
        raise ValidationError_(
            f"modelo inválido: {modelo!r}. Permitidos: {', '.join(MODELOS)}",
            field="modelo",
        )
    # Validate BEFORE writing anything — a rejected upload must leave no
    # orphan contrato row with zero versions ("no incomplete commits").
    VERSOES_STORE.validar(
        tipo_documento=TIPO_VERSAO,
        content_type=content_type,
        tamanho_bytes=len(data),
    )

    contrato_id = uuid4()
    row = {
        "id": str(contrato_id),
        "org_id": str(org_id),
        "atendimento_id": str(atendimento_id),
        "titulo": titulo,
        "modelo": modelo,
        "status": "rascunho",
        "status_em": None,
        "status_por": None,
        "origem": "upload",
        "criado_por": str(criado_por) if criado_por else None,
        "deleted_at": None,
        "delete_motivo": None,
        "delete_solicitado_por": None,
        "created_at": now_iso(),
        "updated_at": None,
    }
    _t(client, TABLE).insert(row).execute()

    await VERSOES_STORE.guardar(
        client,
        storage,
        org_id,
        contrato_id,
        filename=filename,
        content_type=content_type,
        data=data,
        tipo_documento=TIPO_VERSAO,
        enviado_por=criado_por,
        extra={"numero": 1, "rotulo": rotulo, "origem": "upload"},
    )
    return _contrato_saida(client, org_id, row)


def criar_para_gerar(
    client: Any,
    org_id: UUID,
    atendimento_id: UUID,
    *,
    titulo: str,
    modelo: str,
    criado_por: Optional[UUID],
) -> dict:
    """A contract the F5 generator will fill — origem='gerado', NO version yet.

    Unlike `criar` (an upload always carries its v1), the generator cannot
    produce a version before the contract exists: the matrícula acts it
    transcribes are selected PER CONTRACT (`atendimento_contrato_matricula_atos`)
    and the signature date / pendências prazo live on this row. So the row is
    the generator's input, created first and honestly marked `rascunho` with
    zero versions — the panel already renders that state — and v1 lands via
    `contrato_gerador.service.gerar` once the readiness check passes.
    """
    if modelo not in MODELOS:
        raise ValidationError_(
            f"modelo inválido: {modelo!r}. Permitidos: {', '.join(MODELOS)}",
            field="modelo",
        )
    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "atendimento_id": str(atendimento_id),
        "titulo": titulo,
        "modelo": modelo,
        "status": "rascunho",
        "status_em": None,
        "status_por": None,
        "origem": "gerado",
        "criado_por": str(criado_por) if criado_por else None,
        "deleted_at": None,
        "delete_motivo": None,
        "delete_solicitado_por": None,
        "created_at": now_iso(),
        "updated_at": None,
    }
    _t(client, TABLE).insert(row).execute()
    return row


def definir_modelo(client: Any, org_id: UUID, contrato_id: UUID, modelo: str) -> None:
    """Set the modelo the generator derived — `criar_para_gerar`'s row is
    created before the data can be read, so its modelo is corrected here."""
    _t(client, TABLE).update({"modelo": modelo, "updated_at": now_iso()}).eq(
        "org_id", str(org_id)
    ).eq("id", str(contrato_id)).execute()


def saida(client: Any, org_id: UUID, row: dict) -> dict:
    """Public view of one contract row — the same shape `listar` returns."""
    return _contrato_saida(client, org_id, row)


async def nova_versao(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    cliente_id: UUID,
    contrato_id: UUID,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    rotulo: Optional[str],
    usuario_id: Optional[UUID],
) -> dict:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    row = exigir_contrato(client, org_id, atendimento_id, contrato_id)

    if row["status"] == "cancelado":
        raise ConflictError(
            "Contrato cancelado não recebe novas versões.", resource=TABLE
        )

    _, atualizado = await _guardar_versao(
        client,
        storage,
        org_id,
        atendimento_id,
        contrato_id,
        filename=filename,
        content_type=content_type,
        data=data,
        rotulo=rotulo,
        usuario_id=usuario_id,
        extra={"origem": "upload"},
    )
    return _contrato_saida(client, org_id, atualizado)


async def _guardar_versao(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    atendimento_id: UUID,
    contrato_id: UUID,
    *,
    filename: Optional[str],
    content_type: str,
    data: bytes,
    rotulo: Optional[str],
    usuario_id: Optional[UUID],
    extra: dict,
) -> tuple[dict, dict]:
    """The ONE version-write path, upload or gerado: cancelado refusal ->
    validate -> next never-reused numero -> `DocumentoStore.guardar` (same
    bucket, same LGPD access-log table) -> bump the contract's updated_at.
    Returns (inserted version row, refreshed contract row). `filename=None`
    names the file from its numero (a generated version has no upload name)."""
    row = exigir_contrato(client, org_id, atendimento_id, contrato_id)
    if row["status"] == "cancelado":
        raise ConflictError(
            "Contrato cancelado não recebe novas versões.", resource=TABLE
        )

    VERSOES_STORE.validar(
        tipo_documento=TIPO_VERSAO,
        content_type=content_type,
        tamanho_bytes=len(data),
    )

    owner = UUID(str(contrato_id))
    numero = _proximo_numero(client, org_id, owner)
    inserida = await VERSOES_STORE.guardar(
        client,
        storage,
        org_id,
        owner,
        filename=filename or f"contrato-gerado-v{numero}.{_EXTENSAO_GERADA.get(content_type, 'bin')}",
        content_type=content_type,
        data=data,
        tipo_documento=TIPO_VERSAO,
        enviado_por=usuario_id,
        extra={"numero": numero, "rotulo": rotulo, **extra},
    )
    _t(client, TABLE).update({"updated_at": now_iso()}).eq(
        "id", str(contrato_id)
    ).execute()

    atualizado = exigir_contrato(client, org_id, atendimento_id, contrato_id)
    return inserida, atualizado


async def nova_versao_gerada(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    atendimento_id: UUID,
    contrato_id: UUID,
    *,
    data: bytes,
    content_type: str,
    docx: bytes,
    contexto_sha256: str,
    usuario_id: Optional[UUID],
) -> dict:
    """A version produced by the F5 generator (`card_hub/contrato_gerador`):
    origem='gerado' plus the SHA-256 of the data it was rendered from
    (migration 112 — required for 'gerado', forbidden for 'upload').

    Stores TWO artifacts for this ONE version (migration 120): `data` (the
    ABNT PDF, through the normal `_guardar_versao` path — same row shape
    every version has) and `docx` (the editable rendering that PDF was
    derived from) as a SIBLING object under the same storage key, same
    bucket, same org-first path convention — never a second `numero`. See
    that migration's header for why this is one row with two artifacts
    rather than two version rows.

    Returns the version in the same shape `listar` returns it."""
    inserida, _ = await _guardar_versao(
        client,
        storage,
        org_id,
        atendimento_id,
        contrato_id,
        filename=None,
        content_type=content_type,
        data=data,
        rotulo=None,
        usuario_id=usuario_id,
        extra={"origem": "gerado", "contexto_sha256": contexto_sha256},
    )

    docx_path = f"{inserida['storage_path']}.docx"
    await storage.put(
        bucket=VERSOES_STORE.bucket,
        key=docx_path,
        data=docx,
        content_type=MIME_DOCX,
        metadata={"nome_original": f"contrato-gerado-v{inserida['numero']}.docx"},
    )
    _t(client, VERSOES_STORE.table).update(
        {"docx_storage_path": docx_path, "docx_tamanho_bytes": len(docx)}
    ).eq("id", inserida["id"]).execute()
    inserida["docx_storage_path"] = docx_path
    inserida["docx_tamanho_bytes"] = len(docx)

    resolved = table_reads.resolve_actors({inserida["enviado_por"]} - {None})
    return _versao_out(inserida, resolved)


def atualizar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    contrato_id: UUID,
    *,
    valores: dict,
    usuario_id: Optional[UUID],
) -> dict:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    atual = exigir_contrato(client, org_id, atendimento_id, contrato_id)

    recusados = sorted(set(valores) - set(CAMPOS_EDITAVEIS))
    if recusados:
        raise ValidationError_(
            f"Campos não editáveis: {', '.join(recusados)}", field=recusados[0]
        )
    # Belt-and-suspenders with the router's `Literal` fields (which already
    # 422 an unknown value before this runs) — mirrors
    # `financiamento_service.atualizar`'s identical redundant check.
    if "modelo" in valores and valores["modelo"] not in MODELOS:
        raise ValidationError_(
            f"modelo inválido: {valores['modelo']!r}. "
            f"Permitidos: {', '.join(MODELOS)}",
            field="modelo",
        )
    if "status" in valores and valores["status"] not in STATUSES:
        raise ValidationError_(
            f"status inválido: {valores['status']!r}. "
            f"Permitidos: {', '.join(STATUSES)}",
            field="status",
        )

    patch = {k: v for k, v in valores.items() if k in CAMPOS_EDITAVEIS}

    # Migration 114. `assinatura_data`: an ISO date or null (cleared).
    # `prazo_pendencias_dias`: null = the office default
    # (`contrato_gerador.politica.prazo_pendencias_dias`), otherwise > 0 —
    # same rule as the DB CHECK, raised here as a named 400.
    if "assinatura_data" in patch:
        bruto = patch["assinatura_data"]
        if bruto in (None, ""):
            patch["assinatura_data"] = None
        else:
            try:
                patch["assinatura_data"] = date.fromisoformat(str(bruto)).isoformat()
            except ValueError:
                raise ValidationError_(
                    "data de assinatura inválida — use o formato AAAA-MM-DD",
                    field="assinatura_data",
                ) from None
    if "prazo_pendencias_dias" in patch and patch["prazo_pendencias_dias"] is not None:
        prazo = patch["prazo_pendencias_dias"]
        if isinstance(prazo, bool) or not isinstance(prazo, int) or prazo <= 0:
            raise ValidationError_(
                "o prazo de pendências deve ser um número inteiro de dias maior que zero",
                field="prazo_pendencias_dias",
            )

    # Stamped only when it CHANGES — otherwise "when did this reach
    # enviado_assinatura" silently becomes "when was this last edited"
    # (same rule `financiamento_service.atualizar` follows for `situacao`).
    if "status" in patch and patch["status"] != atual.get("status"):
        patch["status_em"] = now_iso()
        patch["status_por"] = str(usuario_id) if usuario_id else None

    patch["updated_at"] = now_iso()
    _t(client, TABLE).update(patch).eq("org_id", str(org_id)).eq(
        "id", str(contrato_id)
    ).execute()

    atualizado = exigir_contrato(client, org_id, atendimento_id, contrato_id)
    return _contrato_saida(client, org_id, atualizado)


async def url_versao(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    cliente_id: UUID,
    contrato_id: UUID,
    versao_id: UUID,
    *,
    usuario_id: Optional[UUID],
    intent: str = "view",
    formato: str = "pdf",
) -> dict:
    """Mint a short-TTL signed URL for a version's content.

    `formato='pdf'` (default) delegates to `VERSOES_STORE.url` unchanged —
    every version, upload or gerado, has one. `formato='docx'` (migration
    120) is only ever populated on a `gerado` row; a foreign/missing/upload
    `versao_id` still 404s first (`VERSOES_STORE.exigir`), so a probe cannot
    distinguish "not yours" from "has no docx" from "does not exist" any
    more finely than the pdf path already lets it. Same short TTL, same
    access-log call (`VERSOES_STORE.log_acesso`, keyed to this version's own
    id — not a separate artifact identity) as the PDF path.
    """
    if formato not in ("pdf", "docx"):
        raise ValidationError_(
            f"formato inválido: {formato!r}. Permitidos: pdf, docx", field="formato"
        )

    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    exigir_contrato(client, org_id, atendimento_id, contrato_id)
    owner = UUID(str(contrato_id))

    if formato == "pdf":
        return await VERSOES_STORE.url(
            client, storage, org_id, owner, versao_id,
            usuario_id=usuario_id, intent=intent,
        )

    if intent not in ("view", "download"):
        raise ValidationError_(f"intent inválido: {intent!r}", field="intent")
    documento = VERSOES_STORE.exigir(client, org_id, owner, versao_id)
    docx_path = documento.get("docx_storage_path")
    if not docx_path:
        raise NotFoundError(VERSOES_STORE.table, f"{versao_id} (.docx)")

    signed = await storage.signed_url(
        bucket=VERSOES_STORE.bucket, key=docx_path,
        expires_in_seconds=SIGNED_URL_TTL_SECONDS,
    )
    VERSOES_STORE.log_acesso(client, org_id, versao_id, usuario_id, intent)
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=SIGNED_URL_TTL_SECONDS)
    ).isoformat()
    return {"url": signed, "expires_at": expires_at}


def remover_versao(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    contrato_id: UUID,
    versao_id: UUID,
    *,
    motivo: str,
    usuario_id: Optional[UUID],
) -> None:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    exigir_contrato(client, org_id, atendimento_id, contrato_id)

    owner = UUID(str(contrato_id))
    # Raises 404 first for a wrong/foreign/already-deleted versao_id — the
    # live-count check below must only ever fire for a REAL target.
    VERSOES_STORE.exigir(client, org_id, owner, versao_id)

    linhas = VERSOES_STORE.listar_linhas(client, org_id, owner)
    if len(linhas) <= 1:
        raise ConflictError(
            "Um contrato precisa de pelo menos uma versão — exclua o contrato.",
            resource=VERSOES_STORE.table,
        )
    VERSOES_STORE.remover(
        client, org_id, owner, versao_id, motivo=motivo, usuario_id=usuario_id
    )


def remover_contrato(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    contrato_id: UUID,
    *,
    motivo: str,
    usuario_id: Optional[UUID],
) -> None:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    exigir_contrato(client, org_id, atendimento_id, contrato_id)

    owner = UUID(str(contrato_id))
    # Every live version is soft-deleted too — a "deleted" contract whose
    # versions still list live would let its files keep showing up wherever
    # versions are read independently of their contract.
    for linha in VERSOES_STORE.listar_linhas(client, org_id, owner):
        VERSOES_STORE.remover(
            client,
            org_id,
            owner,
            UUID(str(linha["id"])),
            motivo=motivo,
            usuario_id=usuario_id,
        )

    _t(client, TABLE).update(
        {
            "deleted_at": now_iso(),
            "delete_motivo": motivo,
            "delete_solicitado_por": str(usuario_id) if usuario_id else None,
        }
    ).eq("id", str(contrato_id)).execute()


__all__ = [
    "ALLOWED_MIME_TYPES",
    "CAMPOS_EDITAVEIS",
    "MAX_UPLOAD_BYTES",
    "MIME_DOCX",
    "MODELOS",
    "STATUSES",
    "TABLE",
    "TIPO_VERSAO",
    "VERSOES_STORE",
    "atualizar",
    "criar",
    "exigir_contrato",
    "listar",
    "nova_versao",
    "nova_versao_gerada",
    "remover_contrato",
    "remover_versao",
    "url_versao",
]
