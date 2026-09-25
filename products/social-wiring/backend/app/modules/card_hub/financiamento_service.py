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

import logging
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.api import scheduler as seed_scheduler
from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.exceptions import ValidationError_

from app.modules.card_hub import services as svc
from app.modules.card_hub.deps import BUCKET, get_card_hub_client
from app.services import documento_retencao, table_reads
from app.services.documento_store import DocumentoStore, documento_base, now_iso

logger = logging.getLogger(__name__)

TABLE = "atendimento_financiamento"
#: `STORE.table`, exposed so a sibling module (`negociacao_extracao_service`)
#: can address the same rows without re-typing the literal.
DOCUMENTOS_TABLE = "atendimento_documentos"

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

#: S2 contract §A — the ITBI/financiamento deal facts, shown under a NEW
#: "Financiamento" section (as opposed to `TIPOS_ESCRITURA`'s always-shown
#: section). `comprovante_itbi` is uploaded but never extracted (§H10,
#: archive-only — see `deve_extrair`); `dps` is DELIBERATELY not a member of
#: this tuple — see the module docstring below.
TIPOS_NEGOCIACAO: tuple[str, ...] = (
    "guia_itbi",
    "comprovante_itbi",
    "proposta_financiamento",
    "contrato_financiamento",
)

#: 🔴 DPS (Declaração Pessoal de Saúde) IS NEVER STORED (owner H8, contract
#: §A/§H8). It is not a member of `TIPOS_NEGOCIACAO`, `TIPOS_ESCRITURA` or
#: `TIPOS_FGTS` — `STORE.validar` rejects `tipo_documento='dps'` by
#: construction (`tipo_documento not in self.tipos` — refused-by-construction,
#: not a runtime special case that could silently drift). Do not add it.

#: Extractable subset of `TIPOS_NEGOCIACAO` — `comprovante_itbi` is stored for
#: the archive only (§H10: the contract prints only who pays ITBI, never a
#: read value off the receipt itself).
TIPOS_NEGOCIACAO_EXTRAIVEIS: tuple[str, ...] = (
    "guia_itbi",
    "proposta_financiamento",
    "contrato_financiamento",
)

#: The bank-financing document subset of `TIPOS_NEGOCIACAO` — distinct from
#: `guia_itbi`/`comprovante_itbi` (a tax formality, not a bank document).
#: Returned on `obter()` (FE consumer note, 2026-09-25) so the panel never
#: hardcodes these two tipos to decide when to show the "Financiamento"
#: document slots.
TIPOS_FINANCIAMENTO_DOCS: tuple[str, ...] = (
    "proposta_financiamento",
    "contrato_financiamento",
)

TIPOS_DOCUMENTO: tuple[str, ...] = TIPOS_ESCRITURA + TIPOS_FGTS + TIPOS_NEGOCIACAO

#: 30 MB — raised from 25 MB (S2 contract §A) to cover `contrato_
#: financiamento`: a 25-page image-only bank contract, same reasoning
#: `empresas` gave for its own 25MB->30MB bump. `app/main.py`'s
#: `_MAX_BODY_PATH_OVERRIDES["/api/clientes/*/financiamento/documentos"]`
#: already sits at 30MB — this keeps `STORE.validar`'s own ceiling from
#: being the tighter (and therefore silently wrong) one.
MAX_UPLOAD_BYTES = 30 * 1024 * 1024
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

CAMPOS_EDITAVEIS: tuple[str, ...] = (
    "situacao",
    "situacao_motivo",
    "fgts",
    "observacoes",
    # Migration 100. Which bank, chosen from the org's registry rather than
    # typed — see `app/modules/agentes_financeiros` for why that is a table.
    # NULLABLE and editable at any time: `pendente` is exactly the state where
    # the agent has not been decided yet.
    "agente_financeiro_id",
    "numero_proposta",
)


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


def deve_extrair(tipo_documento: str) -> bool:
    """Does this tipo get a background extraction (S2 contract §A/§E1)?

    `comprovante_itbi` is a `TIPOS_NEGOCIACAO` member (uploaded on the same
    section, retained the same way) but is NOT extracted — §H10: the
    contract prints only WHO pays ITBI, never a value read off the receipt.
    """
    return tipo_documento in TIPOS_NEGOCIACAO_EXTRAIVEIS


def _grupo(tipo_documento: str) -> str:
    """The section this document renders under — derived from tuple
    membership (contract §A: "never from name patterns")."""
    if tipo_documento in TIPOS_FGTS:
        return "fgts"
    if tipo_documento in TIPOS_NEGOCIACAO:
        return "financiamento_negociacao"
    return "escritura"


def _documento_out(row: dict, resolved: dict) -> dict:
    return {
        **documento_base(row, resolved),
        "grupo": _grupo(row["tipo_documento"]),
        "categoria_lgpd": row.get("categoria_lgpd"),
        "retencao_ate": row.get("retencao_ate"),
        # S2 contract §E5.5 — `obter()`'s per-document extraction block.
        "extracao_status": row.get("extracao_status"),
        "extracao_fonte": row.get("extracao_fonte"),
        "extracao_erro": row.get("extracao_erro"),
        "extracao_aviso": row.get("extracao_aviso"),
        "extracao_dados": row.get("extracao_dados"),
        "extracao_descartada_em": row.get("extracao_descartada_em"),
        "extracao_descartada_por": table_reads.actor(
            resolved, row.get("extracao_descartada_por")
        ),
    }


def _saida(
    row: Optional[dict],
    atendimento_id: UUID,
    documentos: list[dict],
    agente: Optional[dict] = None,
    *,
    tem_parcela_financiamento: bool = False,
) -> dict:
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
        "agente_financeiro_id": None,
        "numero_proposta": None,
        "created_at": None,
        "updated_at": None,
    }
    # S2 contract §C.7/§E5.5 — the provenance quintet per column, so the FE
    # can render a machine-pending badge without a second request.
    prov: dict[str, Any] = {}
    for campo in _CAMPOS_PROVENIENCIA:
        prefixo = _PREFIXO_PROVENIENCIA[campo]
        prov[f"{campo}_proveniencia"] = {
            "origem": base.get(f"{prefixo}_origem"),
            "documento_id": base.get(f"{prefixo}_documento_id"),
            "em": base.get(f"{prefixo}_em"),
            "confirmado_por": base.get(f"{prefixo}_confirmado_por"),
            "confirmado_em": base.get(f"{prefixo}_confirmado_em"),
        }
    return {
        "atendimento_id": str(atendimento_id),
        "situacao": base.get("situacao", "pendente"),
        "situacao_em": base.get("situacao_em"),
        "situacao_motivo": base.get("situacao_motivo"),
        # S2 contract §C.5/H6 — flat, NOT nested under a `_proveniencia`
        # dict (unlike `fgts`/`numero_proposta`/`agente_financeiro_id` above
        # — FE consumer note, 2026-09-25: S3 reads this key directly).
        "situacao_origem": base.get("situacao_origem"),
        "fgts": bool(base.get("fgts")),
        "observacoes": base.get("observacoes"),
        "agente_financeiro_id": base.get("agente_financeiro_id"),
        **prov,
        # 🔴 The RESOLVED agent rides along, and is resolved WITHOUT the
        # `ativo` filter the dropdown uses. A bank retired after it financed
        # this deal must keep rendering here — otherwise the panel would blank
        # the name of the institution on a signed contract because somebody
        # tidied a settings list. See migration 100's RESTRICT note.
        "agente_financeiro": agente,
        "numero_proposta": base.get("numero_proposta"),
        "created_at": base.get("created_at"),
        "updated_at": base.get("updated_at"),
        "existe": row is not None,
        # The two groups are returned SEPARATELY rather than as one list with a
        # `grupo` field to sort by — the UI renders them as two sections, and
        # sorting a mixed list at every call site is how one of them ends up
        # showing the other's documents.
        "tipos_escritura": list(TIPOS_ESCRITURA),
        "tipos_fgts": list(TIPOS_FGTS),
        # S2 contract §A/§E5.5 — FE consumer note, 2026-09-25: the panel
        # never hardcodes which tipos are "the financiamento docs" section,
        # nor re-derives "is there a financiamento parcela yet" from the
        # negociação estruturada payload (a second request it would rather
        # not make just to decide whether to show that section at all).
        "tipos_financiamento_docs": list(TIPOS_FINANCIAMENTO_DOCS),
        "tem_parcela_financiamento": tem_parcela_financiamento,
        "documentos": documentos,
    }


#: Columns of the financing agent the panel renders beside the dropdown. A
#: subset of the registry's own `FIELDS` — the card shows who the bank is, not
#: its full contact sheet, which lives on the management page. `origem`
#: (migration 171, H7) lets the panel mark "criado automaticamente".
_AGENTE_RESUMO = ("id", "nome", "codigo_banco", "agencia", "ativo", "origem")


def _agente(client: Any, org_id: UUID, row: Optional[dict]) -> Optional[dict]:
    """Resolve this deal's financing agent, INCLUDING a retired one.

    🔴 NO `ativo` FILTER, deliberately. The dropdown must not offer a retired
    bank, but a deal that already went through one must keep naming it — the
    two are different questions and only the dropdown asks the first. Filtering
    here would blank the institution on a signed contract because somebody
    tidied a settings list, which is the exact loss migration 100's ON DELETE
    RESTRICT exists to prevent.

    `ativo` is returned so the UI can mark a retired agent rather than pretend
    it is still selectable.
    """
    agente_id = (row or {}).get("agente_financeiro_id")
    if not agente_id:
        return None
    rows = (
        client.schema("social_wiring")
        .table("agentes_financeiros")
        .select(",".join(_AGENTE_RESUMO))
        .eq("org_id", str(org_id))
        .eq("id", str(agente_id))
        .limit(1)
        .execute()
    ).data or []
    return {k: rows[0].get(k) for k in _AGENTE_RESUMO} if rows else None


def _tem_parcela_financiamento(client: Any, org_id: UUID, atendimento_id: UUID) -> bool:
    rows = (
        _t(client, "atendimento_negociacao_parcelas")
        .select("id")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento_id))
        .eq("tipo", "financiamento")
        .limit(1)
        .execute()
    ).data or []
    return bool(rows)


def obter(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    row = _linha(client, org_id, atendimento_id)
    linhas = STORE.listar_linhas(client, org_id, atendimento_id)
    resolved = table_reads.resolve_actors(
        {r["enviado_por"] for r in linhas if r.get("enviado_por")}
        | {r["extracao_descartada_por"] for r in linhas if r.get("extracao_descartada_por")}
    )
    documentos = [_documento_out(r, resolved) for r in linhas]
    return _saida(
        row, atendimento_id, documentos, _agente(client, org_id, row),
        tem_parcela_financiamento=_tem_parcela_financiamento(client, org_id, atendimento_id),
    )


#: The provenance-tracked columns `atualizar` may stamp `origem='manual'` on
#: (S2 contract §C.7 — "manual writers must stamp provenance"). `situacao`
#: is handled SEPARATELY, just below (its `_em` stamp is on-CHANGE, unlike
#: these four's on-PRESENCE stamp — see the `atualizar` comment).
_CAMPOS_PROVENIENCIA: tuple[str, ...] = ("fgts", "numero_proposta", "agente_financeiro_id")
#: `<campo>_origem` prefix per editable column — `agente_financeiro_id`'s
#: quintet is prefixed `agente_financeiro`, not `agente_financeiro_id`.
_PREFIXO_PROVENIENCIA: dict[str, str] = {
    "fgts": "fgts",
    "numero_proposta": "numero_proposta",
    "agente_financeiro_id": "agente_financeiro",
}


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
    # A human PATCH of `situacao` is ALWAYS 'manual', confirmed-by-
    # construction (H6/§C.7) — so a LATER `contrato_financiamento` read
    # opens a conflict instead of silently reopening a human's decision.
    if "situacao" in patch and patch["situacao"] != (atual or {}).get("situacao"):
        patch["situacao_em"] = now_iso()
        patch["situacao_por"] = str(usuario_id) if usuario_id else None
        patch["situacao_origem"] = "manual"
        patch["situacao_documento_id"] = None
        patch["situacao_confirmado_por"] = str(usuario_id) if usuario_id else None
        patch["situacao_confirmado_em"] = patch["situacao_em"]

    # 🔴 A human edit of a provenance-tracked value is ALWAYS 'manual',
    # confirmed-by-construction (the person editing it right now confirmed
    # it) — same convention `clientes_service.update_cliente` uses. Without
    # this, a human PATCH over a machine-pending value would leave it
    # reading as still-pending and block `gerar` (409) on a value a person
    # just typed.
    now_prov = now_iso()
    for campo in _CAMPOS_PROVENIENCIA:
        if campo not in patch:
            continue
        prefixo = _PREFIXO_PROVENIENCIA[campo]
        patch[f"{prefixo}_origem"] = "manual"
        patch[f"{prefixo}_documento_id"] = None
        patch[f"{prefixo}_em"] = now_prov
        patch[f"{prefixo}_confirmado_por"] = str(usuario_id) if usuario_id else None
        patch[f"{prefixo}_confirmado_em"] = now_prov

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
            # 🔴 STILL NULL AT UPLOAD, and now for a POSITIVE reason rather
            # than a missing one. Migration 079 gave this surface a policy,
            # but its clock is anchored to `atendimentos.closed_at`, not to
            # the upload — Lei 9.613/98 art. 10 III counts "da conclusão da
            # transação". An open deal's paperwork has no expiry; `varrer`
            # below stamps the date once the deal closes, and re-stamps it if
            # the policy or the close date moves.
            "retencao_ate": None,
            # `pendente` at upload — the sweep's claim path, same reasoning
            # every sibling extraction lifecycle gives: a job that never
            # starts must be visibly waiting, not invisibly lost. `None` for
            # `comprovante_itbi` (archive-only, §H10) and for every escritura/
            # FGTS tipo — this column stays a real "not applicable" rather
            # than a fake `pendente` a sweep would spin on forever.
            "extracao_status": "pendente" if deve_extrair(tipo_documento) else None,
            "extracao_tentativas": 0,
        },
    )
    resolved = table_reads.resolve_actors(
        {row["enviado_por"]} if row["enviado_por"] else set()
    )
    return _documento_out(row, resolved)


def descartar_extracao(
    client: Any, org_id: UUID, cliente_id: UUID, documento_id: UUID, *,
    usuario_id: Optional[UUID],
) -> dict:
    """Turn the reading down — kept on the document (`extracao_dados`
    survives), just stops being offered as machine-pending. Mirrors
    `empresas.documentos_service.descartar_extracao` / `identidade_
    extracao_service.descartar_sugestao`'s posture (S2 contract §E5.3)."""
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    documento = STORE.exigir(client, org_id, atendimento_id, documento_id)
    patch = {
        "extracao_descartada_em": now_iso(),
        "extracao_descartada_por": str(usuario_id) if usuario_id else None,
    }
    _t(client, DOCUMENTOS_TABLE).update(patch).eq(
        "id", str(documento_id)
    ).execute()
    resolved = table_reads.resolve_actors(
        {usuario_id} if usuario_id else set()
    )
    return _documento_out({**documento, **patch}, resolved)


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


# ─── Retention sweep ──────────────────────────────────────────────────
#
# 🔴 THIS RECOMPUTES `retencao_ate` EVERY RUN — it does not stamp-once.
#
# The date is a function of two inputs that both move: the deal's `closed_at`
# (a deal can be reopened) and the org's policy (a human can change it on the
# Settings screen). Stamping once would make the column a snapshot of whatever
# those were on the day the sweep first saw the row — so a user who shortened
# a retention period would keep seeing the old expiry, and a reopened deal's
# documents would still expire on the closed deal's clock. Treating the column
# as a materialized view of (closed_at, policy) instead makes the sweep
# idempotent and self-healing, at the cost of one extra read per run.


def _expiracao_esperada(
    closed_at: Optional[str], dias: Optional[int]
) -> Optional[str]:
    """`closed_at + dias` as a DATE string, or None when there is no clock.

    None when the deal is still open (no anchor) OR when the policy says keep
    indefinitely. Both are real answers meaning "this document does not
    expire", and collapsing them here is safe because the only consumer is a
    comparison against `retencao_ate`.
    """
    if not closed_at or dias is None:
        return None
    # `closed_at` is a PostgREST timestamptz string; only the date matters.
    fechado = datetime.fromisoformat(str(closed_at).replace("Z", "+00:00")).date()
    return (fechado + timedelta(days=dias)).isoformat()


def varrer_retencao(client: Any, org_id: UUID) -> dict:
    """Re-derive every live document's expiry, then sweep what has expired.

    Returns `{"reavaliados": n, "removidos": n}` — both counts, because a run
    that re-dated forty documents and deleted none is a different event from
    one that deleted forty, and a single number could not tell them apart.
    """
    linhas = table_reads.paged_rows(
        client,
        "atendimento_documentos",
        org_id,
        refine=lambda q: q.is_("deleted_at", "null"),
    )
    if not linhas:
        return {"reavaliados": 0, "removidos": 0}

    fechamentos = {
        str(row["id"]): row.get("closed_at")
        for row in table_reads.in_batched_rows(
            client,
            "atendimentos",
            org_id,
            "id",
            sorted({str(r["atendimento_id"]) for r in linhas}),
            select="id,closed_at",
        )
    }

    # 🔴 Hoisted out of the loop deliberately. `dias_para` reads the policy
    # table on every call; asking it per DOCUMENT would turn a two-query sweep
    # into one query per file. The policy cannot change mid-sweep in a way
    # that matters — the next run re-derives everything anyway.
    dias_por_tipo = {
        p["tipo_documento"]: p["retencao_dias"]
        for p in documento_retencao.politicas(client, org_id)
        if p["superficie"] == "atendimento"
    }

    reavaliados = 0
    for linha in linhas:
        dias = dias_por_tipo.get(linha["tipo_documento"])
        esperado = _expiracao_esperada(
            fechamentos.get(str(linha["atendimento_id"])), dias
        )
        if linha.get("retencao_ate") == esperado:
            continue
        table_reads.table(client, "atendimento_documentos").update(
            {"retencao_ate": esperado}
        ).eq("id", linha["id"]).execute()
        reavaliados += 1

    return {"reavaliados": reavaliados, "removidos": STORE.varrer_expirados(client, org_id)}


def varrer_retencao_todas_orgs(*, client: Any = None) -> dict:
    """The scheduled body — every org that owns at least one document."""
    resolvido = client if client is not None else get_card_hub_client()
    totais = {"reavaliados": 0, "removidos": 0}
    for org_id in _orgs_com_documentos(resolvido):
        parcial = varrer_retencao(resolvido, org_id)
        totais["reavaliados"] += parcial["reavaliados"]
        totais["removidos"] += parcial["removidos"]
    return totais


def _orgs_com_documentos(client: Any) -> list[UUID]:
    """Every org owning at least one `atendimento_documentos` row.

    Same shape as `documentos_service._list_org_ids` — one column, paged,
    deduped in Python, because PostgREST has no DISTINCT.
    """

    def fetch_page(start: int, end: int):
        return (
            table_reads.table(client, "atendimento_documentos")
            .select("org_id")
            .order("id")
            .range(start, end)
            .execute()
        ).data

    vistos: set[str] = set()
    for row in iter_paged_rows(fetch_page, label="atendimento_documentos org_id scan"):
        if row.get("org_id"):
            vistos.add(str(row["org_id"]))
    return [UUID(o) for o in sorted(vistos)]


def _job_varrer_retencao(*, run_fn: Any = None) -> None:
    """Scheduler entrypoint — swallows everything so a bug in one run never
    de-registers the job (mirrors `documentos_service._run_retention_sweep_job`).
    `run_fn` is the test seam."""
    try:
        (run_fn or varrer_retencao_todas_orgs)()
    except Exception:
        logger.error(
            "card_hub.financiamento: retention sweep failed", exc_info=True
        )


def configure(*, scheduler: Any = None) -> None:
    """Register the sweep on the seed scheduler, at import time — before
    `start_scheduler()` fires in `app/lifespan.py`."""
    (scheduler or seed_scheduler).register(
        "card_hub_financiamento_retention_sweep",
        _job_varrer_retencao,
        hours=24,
    )
    logger.info("card_hub financiamento retention sweep configured: every 24h")


__all__ = [
    "ALLOWED_MIME_TYPES",
    "CAMPOS_EDITAVEIS",
    "MAX_UPLOAD_BYTES",
    "SITUACOES",
    "STORE",
    "TIPOS_DOCUMENTO",
    "TIPOS_ESCRITURA",
    "TIPOS_FGTS",
    "TIPOS_NEGOCIACAO",
    "TIPOS_NEGOCIACAO_EXTRAIVEIS",
    "atualizar",
    "configure",
    "descartar_extracao",
    "deve_extrair",
    "listar_acessos",
    "obter",
    "remover",
    "upload",
    "varrer_retencao",
    "varrer_retencao_todas_orgs",
    "url_do_documento",
]
