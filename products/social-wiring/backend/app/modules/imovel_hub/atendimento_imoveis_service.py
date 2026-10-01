"""The imóveis an atendimento is about — `atendimento_imoveis` (migration 181).

Contract `atendimento-partes-imoveis` §3. Until this junction an atendimento
reached an imóvel by two free-text códigos (the originating lead's and
`atendimento_negociacao.imovel_codigo`, "the one under negotiation"). Now:

* the junction lists EVERY imóvel the atendimento is about (`origem` says how
  the link arose: lead | manual | campanha | negociacao);
* at most ONE live row is `principal` (partial unique index backstop);
* `atendimento_negociacao.imovel_codigo` MUST be ∈ the junction — enforced HERE,
  in `garantir_vinculo`, called by `card_hub/negociacao_service._gravar` (the
  single writer of that column). Service-enforced, no DB trigger: the
  negociação row is created lazily;
* an atendimento with zero live rows is `imovel_pendente` — DERIVED on read,
  never stored.

THE INGEST WRITER — `vincular_lead` (§3.5)
------------------------------------------
Every path that creates a lead (manual `POST /api/leads`, the Meta sync, OLX,
imovelweb) calls it, so the lead's imóvel lands in the junction AND in the
cliente's interesses. Two facts shape it:

1. A DB trigger (034/090) spawns the atendimento on the lead insert, but the
   cliente is attached LATER (`clientes_service.attach_lead_now` or the
   6-hourly sweep). So the junction link can be written at once while the
   interesse needs a cliente that may not exist yet.
2. A Meta lead arrives as TWO atendimentos (one per `leads`/`meta_ads_leads`
   spawn) which the sweep collapses (`substituida_por`) — the survivor is not
   known at ingest time.

Hence `reconcile` (below), called from the sweep AFTER the repoint+collapse
steps: it re-derives every missing (survivor atendimento, código) junction row
and every missing (cliente, código) interesse in a handful of batched reads, so
a late cliente attach, a collapse or a failed ingest-time call all converge.

🔴 NEITHER WRITER RESURRECTS A REMOVAL. A (atendimento, código) or (cliente,
código) that has ANY row — live or soft-deleted — is left alone; otherwise the
sweep would undo a human's removal every six hours.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.primitives.exceptions import (
    AppException,
    ConflictError,
    NotFoundError,
)

from app.modules.card_hub.services import (
    AmbiguousAtendimento,
    _atendimentos_do_cliente,
    ensure_cliente,
    resolve_atendimento_id,
)
from app.modules.imovel_hub import _relacionamentos as rel
from app.modules.imovel_hub import busca_service, dados_service, interesses_service
from app.services import table_reads

logger = logging.getLogger(__name__)

TABLE = "atendimento_imoveis"
NEGOCIACAO_TABLE = "atendimento_negociacao"

#: What a person may type through the API (§3.2). `lead`/`negociacao` are
#: system-only — written by `vincular_lead` / `garantir_vinculo`.
ORIGENS_USUARIO = ("manual", "campanha")
ORIGENS = ("lead", "manual", "campanha", "negociacao")


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _vivas(query):
    return query.is_("deleted_at", "null")


# ── reads ──────────────────────────────────────────────────────────────


def _linhas_vivas(client: Any, org_id: UUID, atendimento_id: str) -> list[dict]:
    rows = table_reads.paged_rows(
        client,
        TABLE,
        org_id,
        eq_filters={"atendimento_id": str(atendimento_id)},
        refine=_vivas,
    )
    rows.sort(
        key=lambda r: (0 if r.get("principal") else 1, str(r.get("created_at") or ""))
    )
    return rows


def _codigo_em_negociacao(client: Any, org_id: UUID, atendimento_id: str) -> Optional[str]:
    rows = (
        _t(client, NEGOCIACAO_TABLE)
        .select("imovel_codigo")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento_id))
        .limit(1)
        .execute()
    ).data or []
    codigo = (rows[0].get("imovel_codigo") if rows else None) or None
    return busca_service.canonical(codigo) if codigo else None


def _item(row: dict, imovel: Optional[dict], em_negociacao: Optional[str]) -> dict:
    codigo = str(row["codigo"])
    return {
        "id": str(row["id"]),
        "codigo": codigo,
        "origem": row.get("origem"),
        "principal": bool(row.get("principal")),
        "em_negociacao": bool(em_negociacao) and codigo == em_negociacao,
        "created_at": row.get("created_at"),
        "created_by": str(row["created_by"]) if row.get("created_by") else None,
        "imovel": imovel
        or {"codigo": codigo, "registrado": False, "fonte": "nenhuma"},
    }


def listar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    atendimento_id: Optional[UUID] = None,
) -> dict:
    """§3.1 — `{items, total, atendimento_id, imovel_pendente}`.

    A read with nothing to show is EMPTY, never a 409 (§0): the card asks on
    every open. Only `AmbiguousAtendimento` is caught — a NotFoundError for an
    explicit `atendimento_id` that is someone else's must still surface.
    """
    ensure_cliente(client, org_id, cliente_id)
    try:
        alvo = resolve_atendimento_id(client, org_id, cliente_id, atendimento_id)
    except AmbiguousAtendimento:
        return {"items": [], "total": 0, "atendimento_id": None, "imovel_pendente": False}

    rows = _linhas_vivas(client, org_id, alvo)
    imoveis = busca_service.enriquecer(client, org_id, [r["codigo"] for r in rows])
    negociado = _codigo_em_negociacao(client, org_id, alvo)
    itens = [_item(r, imoveis.get(str(r["codigo"])), negociado) for r in rows]
    return {
        "items": itens,
        "total": len(itens),
        "atendimento_id": alvo,
        "imovel_pendente": not itens,
    }


def codigos_por_atendimento(
    client: Any, org_id: UUID, atendimento_ids: list[str]
) -> dict[str, list[str]]:
    """`{atendimento_id: [codigo, ...]}` (live, principal first) in ONE batched
    read — the person-page resumo's `imoveis`/`imovel_pendente` source."""
    rows = table_reads.in_batched_rows(
        client, TABLE, org_id, "atendimento_id", atendimento_ids, order_col="id"
    )
    por: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("deleted_at") is None:
            por.setdefault(str(r["atendimento_id"]), []).append(r)
    return {
        aid: [
            str(r["codigo"])
            for r in sorted(
                lista,
                key=lambda r: (
                    0 if r.get("principal") else 1,
                    str(r.get("created_at") or ""),
                ),
            )
        ]
        for aid, lista in por.items()
    }


# ── user writes ────────────────────────────────────────────────────────


def _demover_principais(
    client: Any, org_id: UUID, atendimento_id: str, *, exceto_id: Optional[str] = None
) -> None:
    for r in _linhas_vivas(client, org_id, atendimento_id):
        if r.get("principal") and str(r["id"]) != exceto_id:
            _t(client, TABLE).update({"principal": False}).eq(
                "org_id", str(org_id)
            ).eq("id", str(r["id"])).execute()


def _resolver_para_escrita(
    client: Any, org_id: UUID, cliente_id: UUID, atendimento_id: Optional[UUID]
) -> str:
    ensure_cliente(client, org_id, cliente_id)
    # AmbiguousAtendimento propagates → 409 AMBIGUOUS_ATENDIMENTO (§0).
    return resolve_atendimento_id(client, org_id, cliente_id, atendimento_id)


def adicionar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    codigo: str,
    principal: bool = False,
    origem: str = "manual",
    atendimento_id: Optional[UUID] = None,
    usuario_id: Optional[Any] = None,
) -> dict:
    """§3.2. 404 unknown imóvel · 409 already linked · 409 ambiguous."""
    if origem not in ORIGENS_USUARIO:
        raise ValueError(f"origem inválida para vínculo manual: {origem!r}")
    alvo = _resolver_para_escrita(client, org_id, cliente_id, atendimento_id)
    canonico = rel.exigir_imovel_cadastrado(client, org_id, codigo)

    todas = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", alvo)
        .eq("codigo", canonico)
        .execute()
    ).data or []
    if any(r.get("deleted_at") is None for r in todas):
        raise ConflictError("Este imóvel já está vinculado ao atendimento.", resource=TABLE)

    vivas = _linhas_vivas(client, org_id, alvo)
    # The first imóvel of an atendimento is principal regardless (§3.2).
    ficar_principal = bool(principal) or not vivas
    if ficar_principal:
        _demover_principais(client, org_id, alvo)

    por_usuario = str(usuario_id) if usuario_id else None
    if todas:
        # Revive the soft-deleted (atendimento, código) instead of inserting.
        antiga = max(todas, key=lambda r: str(r.get("created_at") or ""))
        patch = {
            "deleted_at": None,
            "origem": origem,
            "principal": ficar_principal,
            "created_by": por_usuario,
        }
        _t(client, TABLE).update(patch).eq("org_id", str(org_id)).eq(
            "id", str(antiga["id"])
        ).execute()
        row = {**antiga, **patch}
    else:
        row = {
            "id": str(uuid4()),
            "org_id": str(org_id),
            "atendimento_id": alvo,
            "codigo": canonico,
            "origem": origem,
            "principal": ficar_principal,
            "created_by": por_usuario,
            "created_at": rel.agora(),
            "deleted_at": None,
        }
        _t(client, TABLE).insert(row).execute()

    imovel = busca_service.enriquecer(client, org_id, [canonico]).get(canonico)
    return _item(row, imovel, _codigo_em_negociacao(client, org_id, alvo))


def _linha_viva_do_cliente(
    client: Any, org_id: UUID, cliente_id: UUID, item_id: UUID
) -> dict:
    """The live row `item_id`, only if it belongs to one of THIS cliente's
    atendimentos — never someone else's (404, not 403: no existence oracle)."""
    ids = {str(a["id"]) for a in _atendimentos_do_cliente(client, org_id, cliente_id)}
    rows = (
        _vivas(
            _t(client, TABLE)
            .select("*")
            .eq("org_id", str(org_id))
            .eq("id", str(item_id))
        )
        .limit(1)
        .execute()
    ).data or []
    if not rows or str(rows[0]["atendimento_id"]) not in ids:
        raise NotFoundError("atendimento_imoveis", str(item_id))
    return rows[0]


def definir_principal(
    client: Any, org_id: UUID, cliente_id: UUID, item_id: UUID
) -> dict:
    """§3.3 — idempotent; demotes the previous principal FIRST."""
    ensure_cliente(client, org_id, cliente_id)
    row = _linha_viva_do_cliente(client, org_id, cliente_id, item_id)
    atendimento_id = str(row["atendimento_id"])
    if not row.get("principal"):
        _demover_principais(client, org_id, atendimento_id, exceto_id=str(row["id"]))
        _t(client, TABLE).update({"principal": True}).eq("org_id", str(org_id)).eq(
            "id", str(row["id"])
        ).execute()
        row = {**row, "principal": True}
    imovel = busca_service.enriquecer(client, org_id, [row["codigo"]]).get(str(row["codigo"]))
    return _item(row, imovel, _codigo_em_negociacao(client, org_id, atendimento_id))


def remover(client: Any, org_id: UUID, cliente_id: UUID, item_id: UUID) -> None:
    """§3.4 — soft delete; refuses the imóvel under negotiation and the last
    one; promotes the oldest remaining live row when the principal goes."""
    ensure_cliente(client, org_id, cliente_id)
    row = _linha_viva_do_cliente(client, org_id, cliente_id, item_id)
    atendimento_id = str(row["atendimento_id"])
    codigo = str(row["codigo"])

    if _codigo_em_negociacao(client, org_id, atendimento_id) == codigo:
        raise AppException(
            code="IMOVEL_EM_NEGOCIACAO",
            message=(
                "Este imóvel está em negociação neste atendimento — "
                "altere a negociação antes de removê-lo."
            ),
            status_code=409,
        )
    vivas = _linhas_vivas(client, org_id, atendimento_id)
    if len(vivas) <= 1:
        raise AppException(
            code="ULTIMO_IMOVEL",
            message="O atendimento precisa de pelo menos um imóvel.",
            status_code=409,
        )

    # Read BEFORE the write: the PostgREST row is a plain value, but a test
    # double may hand back the stored dict itself, which the update mutates.
    era_principal = bool(row.get("principal"))
    restantes = [r for r in vivas if str(r["id"]) != str(row["id"])]

    # `principal` must go False in the SAME update as `deleted_at`: the partial
    # unique index only covers live rows, but a dead principal would confuse
    # every reader that forgets the deleted_at filter.
    _t(client, TABLE).update({"deleted_at": rel.agora(), "principal": False}).eq(
        "org_id", str(org_id)
    ).eq("id", str(row["id"])).execute()

    if era_principal:
        proximo = min(restantes, key=lambda r: (str(r.get("created_at") or ""), str(r["codigo"])))
        _t(client, TABLE).update({"principal": True}).eq("org_id", str(org_id)).eq(
            "id", str(proximo["id"])
        ).execute()


# ── system writers ─────────────────────────────────────────────────────


def garantir_vinculo(
    client: Any,
    org_id: UUID,
    atendimento_id: Any,
    codigo: str,
    *,
    origem: str,
    usuario_id: Optional[Any] = None,
) -> dict:
    """§3.5 — idempotent "this código ∈ the atendimento's junction".

    Read-then-write, NEVER `upsert()` (the mock's upsert is a no-op, so an
    upsert path tests green and duplicates live).

    * live row exists → left alone, except `origem="negociacao"` UPGRADES a
      weaker origem (the negotiated imóvel is the stronger statement);
    * soft-deleted row exists → revived (the deal is now explicitly about it);
    * none → inserted. The first live imóvel of an atendimento is principal,
      and so is a `negociacao` one (matches migration 181's backfill rule:
      "principal = the negociação código when one exists").
    """
    if origem not in ORIGENS:
        raise ValueError(f"origem inválida: {origem!r}")
    alvo = str(atendimento_id)
    canonico = rel.exigir_imovel_cadastrado(client, org_id, codigo)

    todas = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", alvo)
        .eq("codigo", canonico)
        .execute()
    ).data or []
    vivas_do_par = [r for r in todas if r.get("deleted_at") is None]
    negociacao = origem == "negociacao"

    if origem == "lead" and todas and not vivas_do_par:
        # A removed link stays removed: the ingest writer and the sweep
        # reconcile both come through here, and reviving would undo a human's
        # removal every six hours. Only `negociacao` (the deal now explicitly
        # names it) and a manual add revive.
        return max(todas, key=lambda r: str(r.get("created_at") or ""))

    if vivas_do_par:
        existente = vivas_do_par[0]
        patch: dict = {}
        if negociacao and existente.get("origem") != "negociacao":
            patch["origem"] = "negociacao"
        if negociacao and not existente.get("principal"):
            _demover_principais(client, org_id, alvo, exceto_id=str(existente["id"]))
            patch["principal"] = True
        if patch:
            _t(client, TABLE).update(patch).eq("org_id", str(org_id)).eq(
                "id", str(existente["id"])
            ).execute()
        return {**existente, **patch}

    outras_vivas = _linhas_vivas(client, org_id, alvo)
    ficar_principal = negociacao or not outras_vivas
    if ficar_principal:
        _demover_principais(client, org_id, alvo)

    por_usuario = str(usuario_id) if usuario_id else None
    if todas:
        antiga = max(todas, key=lambda r: str(r.get("created_at") or ""))
        patch = {"deleted_at": None, "origem": origem, "principal": ficar_principal}
        _t(client, TABLE).update(patch).eq("org_id", str(org_id)).eq(
            "id", str(antiga["id"])
        ).execute()
        return {**antiga, **patch}

    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "atendimento_id": alvo,
        "codigo": canonico,
        "origem": origem,
        "principal": ficar_principal,
        "created_by": por_usuario,
        "created_at": rel.agora(),
        "deleted_at": None,
    }
    _t(client, TABLE).insert(row).execute()
    return row


def resolver_codigo_para_lead(client: Any, org_id: UUID, codigo: str) -> str:
    """The canonical código of a MANUAL lead, validated (contract §3.6).

    Known = in `imovel_registry`, or in the Vista mirror (then registered on the
    spot — the nightly sync registers the whole mirror, so this only bridges the
    gap between a listing appearing and the next sync). Anything else is a
    typed 422 `IMOVEL_DESCONHECIDO` and NOTHING has been written: a typo'd
    código must never become a lead whose card is about no imóvel.
    """
    canonico = busca_service.canonical(codigo or "")
    if canonico:
        registro = (
            _t(client, busca_service.REGISTRY_TABLE)
            .select("codigo_canonical")
            .eq("org_id", str(org_id))
            .eq("codigo_canonical", canonico)
            .limit(1)
            .execute()
        ).data or []
        if registro:
            return canonico
        espelho = (
            _t(client, busca_service.MIRROR_TABLE)
            .select("codigo")
            .eq("org_id", str(org_id))
            .eq("codigo_norm", canonico)
            .limit(1)
            .execute()
        ).data or []
        if espelho:
            dados_service.registrar_imovel(client, org_id, canonico, origem="vista_sync")
            return canonico
    raise AppException(
        code="IMOVEL_DESCONHECIDO",
        message=(
            f"Imóvel {canonico or codigo} não está cadastrado. "
            "Selecione um imóvel do catálogo."
        ),
        status_code=422,
        details={"codigo": canonico or codigo},
    )


def _codigo_da_linha(row: dict) -> Optional[str]:
    """`codigo_imovel_norm` (the trigger-derived key) with the raw column as a
    fallback — a row written before/without the trigger still resolves."""
    bruto = row.get("codigo_imovel_norm") or row.get("codigo_imovel")
    canonico = busca_service.canonical(bruto) if bruto else ""
    return canonico or None


def _codigo_meta(row: dict) -> Optional[str]:
    """A meta lead's código: the 180 columns, else `answers.REF` (the form
    field migration 180's trigger reads — mirrored here so a row the trigger
    has not touched yet still links)."""
    direto = _codigo_da_linha(row)
    if direto:
        return direto
    ref = (row.get("answers") or {}).get("REF") if isinstance(row.get("answers"), dict) else None
    ref = str(ref).strip() if ref is not None else ""
    return busca_service.canonical(ref) if ref else None


def _atendimentos_do_lead(
    client: Any,
    org_id: UUID,
    lead_row: Optional[dict],
    meta_row: Optional[dict],
) -> list[dict]:
    """Every atendimento spawned by this lead and/or its meta twin."""
    achados: dict[str, dict] = {}

    def _por(coluna: str, valor: Any) -> None:
        if not valor:
            return
        rows = (
            _t(client, "atendimentos")
            .select("id,cliente_id,lead_id,meta_ads_lead_id,substituida_por,created_at")
            .eq("org_id", str(org_id))
            .eq(coluna, str(valor))
            .execute()
        ).data or []
        for r in rows:
            achados[str(r["id"])] = r

    if lead_row is not None:
        _por("lead_id", lead_row.get("id"))
    if meta_row is not None:
        _por("meta_ads_lead_id", meta_row.get("id"))
    return list(achados.values())


def _ler_um(client: Any, org_id: UUID, tabela: str, id_: Any) -> Optional[dict]:
    rows = (
        _t(client, tabela)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(id_))
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def vincular_lead(
    client: Any,
    org_id: UUID,
    *,
    lead_id: Optional[Any] = None,
    meta_ads_lead_id: Optional[str] = None,
) -> dict:
    """§3.5 — link a lead's imóvel to its atendimento(s) AND its cliente.

    Reads the lead's (and its Meta twin's) código, registers it the way
    `registrar_imovel` does, links `origem="lead"` (principal when the
    atendimento had none) on every atendimento the lead spawned, and writes the
    cliente interesse when a cliente is already attached. A missing cliente is
    NOT a failure: `reconcile` (the clientes sweep) completes the interesse once
    the cliente exists.

    Returns `{"codigo", "atendimentos": [ids], "interesse": bool|None}` —
    `codigo=None` when the lead carries none (accepted → `imovel_pendente`,
    never an error: a real lead without a resolvable código is never dropped).
    """
    if not lead_id and not meta_ads_lead_id:
        raise ValueError("vincular_lead: informe lead_id ou meta_ads_lead_id")

    lead_row = _ler_um(client, org_id, "leads", lead_id) if lead_id else None
    meta_row = (
        _ler_um(client, org_id, "meta_ads_leads", meta_ads_lead_id)
        if meta_ads_lead_id
        else None
    )
    # The twin: a `leads` row mapped from Meta carries `meta_lead_id`; a meta
    # row may already have its mapped `leads` row. Either direction, both feed
    # the same card, so both feed the same código.
    if lead_row is not None and meta_row is None and lead_row.get("meta_lead_id"):
        meta_row = _ler_um(client, org_id, "meta_ads_leads", lead_row["meta_lead_id"])
    if meta_row is not None and lead_row is None:
        rows = (
            _t(client, "leads")
            .select("*")
            .eq("org_id", str(org_id))
            .eq("meta_lead_id", str(meta_row["id"]))
            .limit(1)
            .execute()
        ).data or []
        lead_row = rows[0] if rows else None

    codigo = (
        (_codigo_da_linha(lead_row) if lead_row else None)
        or (_codigo_meta(meta_row) if meta_row else None)
    )
    saida: dict = {"codigo": codigo, "atendimentos": [], "interesse": None}
    if not codigo:
        return saida

    dados_service.registrar_imovel(client, org_id, codigo, origem="lead")

    atendimentos = _atendimentos_do_lead(client, org_id, lead_row, meta_row)
    for a in atendimentos:
        garantir_vinculo(client, org_id, a["id"], codigo, origem="lead")
        saida["atendimentos"].append(str(a["id"]))

    cliente_id = next((a["cliente_id"] for a in atendimentos if a.get("cliente_id")), None)
    if cliente_id:
        # The Meta row, when there is one, is the TRUE submission (its
        # `created_time`); the mapped `leads` row is a derived copy.
        if meta_row is not None:
            origem_lead = {"meta_ads_lead_id": str(meta_row["id"])}
            criado = meta_row.get("created_time") or meta_row.get("created_at")
        else:
            origem_lead = {"lead_id": str(lead_row["id"])}
            criado = lead_row.get("created_at")
        saida["interesse"] = interesses_service.registrar_de_lead(
            client,
            org_id,
            UUID(str(cliente_id)),
            codigo,
            criado_em=criado,
            **origem_lead,
        )
    return saida


def vincular_lead_seguro(
    client: Any,
    org_id: UUID,
    *,
    lead_id: Optional[Any] = None,
    meta_ads_lead_id: Optional[str] = None,
    contexto: str = "ingest",
) -> Optional[dict]:
    """`vincular_lead` for an INGEST path: never raises, never silent.

    The lead row (and, for portals, the lossless ledger row) is already
    committed when this runs; raising would turn a missing link into a failed
    delivery that the vendor retries or a 500 that invites a duplicate. So a
    failure is logged at ERROR with the traceback and `None` is returned —
    `reconcile` (the clientes sweep) re-derives the link from the lead's own
    código on its next pass, so nothing is lost, only delayed.
    """
    try:
        return vincular_lead(
            client, org_id, lead_id=lead_id, meta_ads_lead_id=meta_ads_lead_id
        )
    except Exception:
        logger.error(
            "vincular_lead failed (%s) lead_id=%s meta_ads_lead_id=%s org=%s — "
            "left for the clientes sweep's reconcile",
            contexto, lead_id, meta_ads_lead_id, org_id, exc_info=True,
        )
        return None


# ── the clientes-sweep reconcile ───────────────────────────────────────


def reconcile(client: Any, org_id: UUID) -> dict:
    """Converge the junction + interesses with what the leads say. Idempotent.

    Called by `clientes_service.run_backfill` AFTER `_repoint_atendimentos` and
    `_collapse_atendimentos` — the order matters: a cliente must be attached
    (for the interesse) and the survivor of a collapse known (for the
    junction). Contract §11.9: ingest linking is service-level + this
    reconcile, not a DB trigger.

    Reads (all org-wide, paged, no N+1): atendimentos, the junction (live AND
    deleted — a removal must stay removed), interesses (same), the leads and
    Meta leads that carry a código, the registry's known códigos. Writes only
    the DELTA.

    A Meta lead's two atendimentos both resolve to the collapse SURVIVOR
    (`substituida_por`), and a loser's lead código (a person who enquired on two
    imóveis) is linked to the survivor too — the card is about both.
    """
    atendimentos = table_reads.paged_rows(
        client,
        "atendimentos",
        org_id,
        select="id,cliente_id,lead_id,meta_ads_lead_id,substituida_por,created_at",
    )
    leads = {
        str(r["id"]): r
        for r in table_reads.paged_rows(
            client,
            "leads",
            org_id,
            select="id,codigo_imovel,codigo_imovel_norm,meta_lead_id,created_at",
            refine=lambda q: q.not_.is_("codigo_imovel_norm", "null"),
        )
    }
    metas = {
        str(r["id"]): r
        for r in table_reads.paged_rows(
            client,
            "meta_ads_leads",
            org_id,
            select="id,codigo_imovel,codigo_imovel_norm,created_at,created_time",
            refine=lambda q: q.not_.is_("codigo_imovel_norm", "null"),
        )
    }
    por_id = {str(a["id"]): a for a in atendimentos}

    # (survivor, código, lead_id|None, meta_id|None, criado_em, cliente_id|None)
    desejados: list[tuple[str, str, Optional[str], Optional[str], Any, Optional[str]]] = []
    for a in sorted(atendimentos, key=lambda x: (str(x.get("created_at") or ""), str(x["id"]))):
        sobrevivente = str(a.get("substituida_por") or a["id"])
        if sobrevivente not in por_id:
            continue
        lead = leads.get(str(a["lead_id"])) if a.get("lead_id") else None
        meta = metas.get(str(a["meta_ads_lead_id"])) if a.get("meta_ads_lead_id") else None
        if meta is None and lead is not None and lead.get("meta_lead_id"):
            meta = metas.get(str(lead["meta_lead_id"]))
        codigo = _codigo_da_linha(lead) if lead else None
        codigo = codigo or (_codigo_da_linha(meta) if meta else None)
        if not codigo:
            continue
        cliente_id = a.get("cliente_id") or por_id[sobrevivente].get("cliente_id")
        # Same preference as `vincular_lead`: the Meta row is the true submission.
        if meta is not None:
            criado = meta.get("created_time") or meta.get("created_at")
        else:
            criado = (lead or {}).get("created_at")
        desejados.append(
            (
                sobrevivente,
                codigo,
                None if meta else (str(lead["id"]) if lead else None),
                str(meta["id"]) if meta else None,
                criado,
                str(cliente_id) if cliente_id else None,
            )
        )

    relatorio = {
        "desejados": len(desejados),
        "imoveis_registrados": 0,
        "vinculos_criados": 0,
        "interesses_criados": 0,
    }
    if not desejados:
        return relatorio

    registrados = {
        str(r["codigo_canonical"])
        for r in table_reads.in_batched_rows(
            client,
            busca_service.REGISTRY_TABLE,
            org_id,
            "codigo_canonical",
            sorted({d[1] for d in desejados}),
            select="codigo_canonical",
            order_col="codigo_canonical",
        )
    }
    for codigo in sorted({d[1] for d in desejados} - registrados):
        dados_service.registrar_imovel(client, org_id, codigo, origem="lead")
        relatorio["imoveis_registrados"] += 1

    juncao = table_reads.paged_rows(client, TABLE, org_id, select="id,atendimento_id,codigo,deleted_at")
    pares_juncao = {(str(r["atendimento_id"]), str(r["codigo"])) for r in juncao}
    com_vivo = {str(r["atendimento_id"]) for r in juncao if r.get("deleted_at") is None}

    interesses = table_reads.paged_rows(
        client, interesses_service.TABLE, org_id, select="id,cliente_id,codigo"
    )
    pares_interesse = {(str(r["cliente_id"]), str(r["codigo"])) for r in interesses}

    for sobrevivente, codigo, lead_id, meta_id, criado, cliente_id in desejados:
        if (sobrevivente, codigo) not in pares_juncao:
            principal = sobrevivente not in com_vivo
            _t(client, TABLE).insert(
                {
                    "id": str(uuid4()),
                    "org_id": str(org_id),
                    "atendimento_id": sobrevivente,
                    "codigo": codigo,
                    "origem": "lead",
                    "principal": principal,
                    "created_by": None,
                    "created_at": criado or rel.agora(),
                    "deleted_at": None,
                }
            ).execute()
            pares_juncao.add((sobrevivente, codigo))
            com_vivo.add(sobrevivente)
            relatorio["vinculos_criados"] += 1
        if cliente_id and (cliente_id, codigo) not in pares_interesse:
            interesses_service.registrar_de_lead(
                client,
                org_id,
                UUID(cliente_id),
                codigo,
                lead_id=lead_id,
                meta_ads_lead_id=meta_id,
                criado_em=criado,
            )
            pares_interesse.add((cliente_id, codigo))
            relatorio["interesses_criados"] += 1
    return relatorio


__all__ = [
    "ORIGENS",
    "ORIGENS_USUARIO",
    "TABLE",
    "adicionar",
    "codigos_por_atendimento",
    "definir_principal",
    "garantir_vinculo",
    "listar",
    "reconcile",
    "remover",
    "resolver_codigo_para_lead",
    "vincular_lead",
    "vincular_lead_seguro",
]
