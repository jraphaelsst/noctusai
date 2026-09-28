"""Calendar pautas an accepted orçamento generates — shared by `orcamentos.py`
(the modal's ✓ Aceitar) and `comercial_funil.py` (drag-to-Fechado), so the
SAME generation runs no matter which door closed the deal (achado 2 /
comercial achado 1: drag-to-Fechado used to skip this entirely because only
`orcamentos.aceitar` called it).

Lives in its own module — not in `orcamentos.py` — because `comercial_funil.py`
closing a negócio (`_fechar`) needs to call it too, and `orcamentos.py` already
imports `comercial_funil`; a shared leaf module is what breaks that cycle.

Generation is per-DAY idempotent (`orcamento_item_id` + `data_publicacao` date),
not per-item: the original shape only ever asked "does this item have ANY
pauta yet?", which is exactly why nothing extended the calendar past the first
30 days (achado 17) — a day-level check is both a superset of the old
whole-item idempotency (a re-accept still creates nothing new) AND what makes
:func:`estender` able to keep filling forward as today's date moves.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any

from noctusai_lib.integrations.persistence.table_reads import in_batched_rows

from app.services import quadro_comum as qc

logger = logging.getLogger(__name__)

__all__ = [
    "DIAS_DE_PAUTA",
    "HORA_PAUTA",
    "gerar",
    "estender",
    "contar_geradas",
    "estender_pendentes",
]

#: How far ahead an accept (or the daily rolling job) fills the calendar.
DIAS_DE_PAUTA = 30
#: Local publishing hour of a generated pauta — a placeholder slot the
#: operator reschedules; midnight UTC would land on the previous day in Brazil.
HORA_PAUTA = time(10, 0)


def _itens_recorrentes(itens: list[dict]) -> list[dict]:
    """Only recurring "Criação de conteúdo" items ever generate a pauta —
    Gestão de conta and non-recurring criação items are delivered, not
    scheduled."""
    return [i for i in itens if i.get("recorrente") and i.get("secao") == "criacao_conteudo"]


def _dias_cobertos(db: Any, org_id: str, item_ids: list[str]) -> dict[str, set[str]]:
    """`{item_id: {ISO dates a generation SLOT was already claimed for this
    item}}` — read from the append-only `pauta_slot_gerado` LEDGER, never
    from the live `pauta` rows (leftovers item 6): a pauta the user deleted,
    or dragged to a different `data_publicacao`, must never free its slot
    back up for the next accept retry or the daily job to regenerate. The
    ledger is what makes "generated exactly once, ever" independent of
    whatever happens to the card the slot produced afterwards.
    """
    cobertos: dict[str, set[str]] = {iid: set() for iid in item_ids}
    if not item_ids:
        return cobertos
    for p in in_batched_rows(db, "pauta_slot_gerado", org_id, "orcamento_item_id", item_ids,
                             select="orcamento_item_id, slot_date"):
        iid = str(p.get("orcamento_item_id"))
        dia = str(p.get("slot_date"))[:10]
        cobertos.setdefault(iid, set()).add(dia)
    return cobertos


def _registrar_slots(db: Any, org_id: str, novas: list[dict]) -> None:
    """Claim every (item, day) slot this batch just generated, in the
    append-only ledger — idempotent (`ON CONFLICT DO NOTHING`), so calling
    this twice for the same slot is a no-op, never a duplicate row. A `qtd_
    por_dia > 1` item produces several pauta rows for the SAME slot; the
    ledger only needs one claim per (item, day), not one per card.
    """
    vistas: set[tuple[str, str]] = set()
    linhas: list[dict] = []
    for p in novas:
        chave = (str(p["orcamento_item_id"]), str(p["data_publicacao"])[:10])
        if chave in vistas:
            continue
        vistas.add(chave)
        linhas.append({"org_id": org_id, "orcamento_item_id": chave[0], "slot_date": chave[1]})
    if linhas:
        db.table("pauta_slot_gerado").upsert(
            linhas, on_conflict="org_id,orcamento_item_id,slot_date", ignore_duplicates=True
        ).execute()


def _linhas_da_janela(
    db: Any, org_id: str, itens: list[dict], *, cliente_id: str, inicio: date, fim: date,
    cobertos: dict[str, set[str]],
) -> list[dict]:
    produtos = qc.por_ids(db, "produto_servico", org_id,
                          (i.get("produto_servico_id") for i in itens), select="id, formato")
    dias_total = (fim - inicio).days + 1
    novas: list[dict] = []
    for item in itens:
        item_id = str(item["id"])
        ja = cobertos.get(item_id, set())
        formato = (produtos.get(str(item.get("produto_servico_id"))) or {}).get("formato")
        qtd = int(item["qtd_por_dia"])
        dias_semana = int(item["dias_semana"])
        for delta in range(dias_total):
            dia = inicio + timedelta(days=delta)
            if not dias_semana & (1 << dia.weekday()):
                continue
            if dia.isoformat() in ja:
                continue
            quando = datetime.combine(dia, HORA_PAUTA, tzinfo=qc.FUSO).isoformat()
            for n in range(qtd):
                novas.append({
                    "org_id": org_id,
                    "cliente_id": cliente_id,
                    "titulo": item["descricao"] if qtd == 1 else f"{item['descricao']} ({n + 1}/{qtd})",
                    "formato": formato,
                    "data_publicacao": quando,
                    "gerada_automaticamente": True,
                    "orcamento_item_id": item["id"],
                })
    return novas


def _inserir(db: Any, novas: list[dict]) -> list[dict]:
    criadas: list[dict] = []
    for lote_inicio in range(0, len(novas), 500):
        lote = novas[lote_inicio:lote_inicio + 500]
        criadas.extend(db.table("pauta").insert(lote).execute().data or [])
    if len(criadas) != len(novas):
        raise RuntimeError(f"insert de pautas retornou {len(criadas)} de {len(novas)} linhas")
    return criadas


def gerar(
    db: Any, org_id: str, *, itens: list[dict], cliente_id: str, inicio: date,
    dias: int = DIAS_DE_PAUTA,
) -> list[dict]:
    """Fill `[inicio, inicio + dias - 1]` for every recurring criação item.

    Per-day idempotent — safe to call again (a re-accept, or the recovery
    "Gerar pautas" button on a deal closed before this generation moved
    into the shared close path).
    """
    recorrentes = _itens_recorrentes(itens)
    if not recorrentes:
        return []
    cobertos = _dias_cobertos(db, org_id, [str(i["id"]) for i in recorrentes])
    fim = inicio + timedelta(days=dias - 1)
    novas = _linhas_da_janela(db, org_id, recorrentes, cliente_id=cliente_id, inicio=inicio, fim=fim,
                              cobertos=cobertos)
    criadas = _inserir(db, novas)
    _registrar_slots(db, org_id, novas)
    return criadas


def estender(db: Any, org_id: str, *, itens: list[dict], cliente_id: str, ate: date) -> list[dict]:
    """Rolling extension: fill `[hoje, ate]`, skipping days already covered.

    The daily job's leg — keeps the calendar `DIAS_DE_PAUTA` ahead and across
    month boundaries (achado 17: the accept-time `gerar` only ever covered the
    first 30 days, with nothing renewing it)."""
    recorrentes = _itens_recorrentes(itens)
    if not recorrentes:
        return []
    hoje = qc.hoje_local()
    if ate < hoje:
        return []
    cobertos = _dias_cobertos(db, org_id, [str(i["id"]) for i in recorrentes])
    novas = _linhas_da_janela(db, org_id, recorrentes, cliente_id=cliente_id, inicio=hoje, fim=ate,
                              cobertos=cobertos)
    criadas = _inserir(db, novas)
    _registrar_slots(db, org_id, novas)
    return criadas


def contar_geradas(db: Any, org_id: str, itens: list[dict]) -> int:
    """Total pautas on the calendar for this orçamento's recurring items —
    the honest "how many pautas does this deal have", regardless of whether
    they were created by this call, an earlier one, or the daily job."""
    recorrentes = _itens_recorrentes(itens)
    item_ids = [str(i["id"]) for i in recorrentes]
    if not item_ids:
        return 0
    return len(list(in_batched_rows(db, "pauta", org_id, "orcamento_item_id", item_ids, select="id")))


def estender_pendentes(admin_db: Any, *, dias_a_frente: int = DIAS_DE_PAUTA) -> dict:
    """Daily job (`app/scheduler.py`): keep every ACCEPTED orçamento's
    calendar `dias_a_frente` days ahead.

    Eligible = orçamento `aceito` AND (sem contrato ainda OR contrato ativo) —
    a contrato parado (`aguardando_assinatura`) is unusual but still counted
    as "no live contract yet" is wrong to silently stop scheduling for, so it
    stays eligible too; only an `encerrado` contract (or a live one that is
    explicitly NOT `ativo`, i.e. was reset by the signature webhook and needs
    a human decision) pauses the rolling fill. Runs on the admin (service-role)
    client — every query below still filters `org_id`.
    """
    hoje = qc.hoje_local()
    ate = hoje + timedelta(days=dias_a_frente - 1)
    aceitos = (
        admin_db.table("orcamento").select("id, org_id, cliente_id")
        .eq("status", "aceito").execute().data or []
    )
    resumo = {"orcamentos": len(aceitos), "elegiveis": 0, "pautas_criadas": 0, "falhas": 0}
    for row in aceitos:
        org_id = str(row["org_id"])
        orcamento_id = str(row["id"])
        cliente_id = row.get("cliente_id")
        if not cliente_id:
            continue
        try:
            contratos = (
                admin_db.table("contrato").select("status").eq("org_id", org_id)
                .eq("orcamento_id", orcamento_id).execute().data or []
            )
            parado = [c for c in contratos if c.get("status") not in ("ativo",)]
            ativo_existe = any(c.get("status") == "ativo" for c in contratos)
            if parado and not ativo_existe:
                continue
            itens = list(
                admin_db.table("orcamento_item").select(
                    "id, secao, recorrente, dias_semana, qtd_por_dia, descricao, produto_servico_id"
                ).eq("org_id", org_id).eq("orcamento_id", orcamento_id).execute().data or []
            )
            resumo["elegiveis"] += 1
            criadas = estender(admin_db, org_id, itens=itens, cliente_id=str(cliente_id), ate=ate)
            resumo["pautas_criadas"] += len(criadas)
        except Exception:  # noqa: BLE001 — one orçamento's failure must not stop the sweep
            resumo["falhas"] += 1
            logger.exception("pautas: extensão diária falhou org=%s orcamento=%s", org_id, orcamento_id)
    logger.info("pautas: extensão diária %s", resumo)
    return resumo
