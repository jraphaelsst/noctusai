"""
Rewards engine — pure-function-on-DB-rows accrual.

Two entry points:
  - `accrue_for_pedido(db, *, pedido_id, pedido_row)` — fires when an order
    transitions to a state that triggers cashback (e.g. "delivered"). The
    caller passes the order row directly; we don't depend on a `pedidos`
    table existing yet (Phase 3 / Wave 3 is out-of-scope here).
  - `accrue_for_sellout_approval(db, *, relatorio_id, relatorio_row)` —
    fires when a brand admin approves a sellout report.

For both, we match the source row against the brand's active
`regras_recompensa`, filter by category / product / distributor /
valor_minimo / quantidade_minima / valido_de / valido_ate, and insert
`recompensas_acumuladas` rows. The function is pure on top of DB rows —
testable in isolation by passing seeded mock data.

**No silent errors:** if the source row is missing (`None` passed in), the
function returns `[]` and logs at WARN — no insert is silently skipped.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

REGRAS_TABLE = "regras_recompensa"
LEDGER_TABLE = "recompensas_acumuladas"
SELLOUT_TABLE = "relatorios_sellout"
RESGATES_TABLE = "resgates_recompensa"


def _to_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _within_validity(rule: dict[str, Any], today: date) -> bool:
    valido_de = _to_date(rule.get("valido_de"))
    valido_ate = _to_date(rule.get("valido_ate"))
    if valido_de and today < valido_de:
        return False
    if valido_ate and today > valido_ate:
        return False
    return True


def _matches_targets(rule: dict[str, Any], *, distributor_id: str, items: list[dict[str, Any]], categorias: Iterable[str], produtos: Iterable[str]) -> bool:
    """Empty filter array = match-all (per migration default `'{}'`)."""
    aplicavel_distrib = rule.get("aplicavel_distribuidores") or []
    if aplicavel_distrib and distributor_id not in aplicavel_distrib:
        return False

    aplicavel_cat = rule.get("aplicavel_categorias") or []
    if aplicavel_cat:
        if not any(c in aplicavel_cat for c in categorias):
            return False

    aplicavel_prod = rule.get("aplicavel_produtos") or []
    if aplicavel_prod:
        if not any(p in aplicavel_prod for p in produtos):
            return False

    return True


def _passes_thresholds(rule: dict[str, Any], *, valor_total: float, quantidade: int) -> bool:
    minimo = float(rule.get("valor_minimo_pedido") or 0)
    if valor_total < minimo:
        return False
    qtd_min = int(rule.get("quantidade_minima") or 0)
    if quantidade < qtd_min:
        return False
    return True


def _fetch_active_rules(db: Any, org_id: Optional[str]) -> list[dict[str, Any]]:
    """SELECT active rules for the org. Falls back to all-rows when org_id is
    None (test harness convenience)."""
    builder = db.table(REGRAS_TABLE).select("*").eq("ativa", True)
    if org_id is not None:
        builder = builder.eq("org_id", org_id)
    res = builder.execute()
    return list(res.data or [])


def _items_categories_products(items: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    cats: list[str] = []
    prods: list[str] = []
    for it in items:
        cat = it.get("category") or it.get("categoria") or it.get("categoryId")
        if cat:
            cats.append(str(cat))
        sku = it.get("sku") or it.get("cProd") or it.get("product_id")
        if sku:
            prods.append(str(sku))
    return cats, prods


def _build_accrual_row(
    *,
    rule: dict[str, Any],
    org_id: Optional[str],
    distributor_id: str,
    valor_total: float,
    source_pedido_id: Optional[str],
    source_relatorio_sellout_id: Optional[str],
) -> dict[str, Any]:
    pct = float(rule.get("valor") or 0)
    valor = round(valor_total * pct / 100.0, 2)
    payload = {
        "org_id": org_id,
        "distributor_id": distributor_id,
        "regra_id": rule.get("id"),
        "tipo": rule.get("tipo") or "cashback",
        "valor": valor,
        "moeda": "BRL",
        "source_pedido_id": source_pedido_id,
        "source_relatorio_sellout_id": source_relatorio_sellout_id,
        "status": "pendente",
        "descricao": f"Acúmulo via regra '{rule.get('nome', '?')}' ({pct}% sobre R$ {valor_total:.2f})",
        "accrued_at": datetime.now(timezone.utc).isoformat(),
    }
    return payload


def accrue_for_pedido(
    db: Any,
    *,
    pedido_id: str,
    pedido_row: Optional[dict[str, Any]] = None,
) -> list[str]:
    """Apply active reward rules to a pedido and write ledger entries.

    Args:
        db: Supabase client (real or MockSupabaseClient).
        pedido_id: order id; stamped on the ledger row as `source_pedido_id`.
        pedido_row: order dict — if absent, we attempt a SELECT against the
            `pedidos` table; the table may not exist yet (Wave 3) — in that
            case the function logs at WARN and returns []. We do NOT silently
            no-op without surfacing the absence.

    Returns:
        List of inserted accrual ids.
    """
    if pedido_row is None:
        try:
            res = db.table("pedidos").select("*").eq("id", pedido_id).execute()
            pedido_row = (res.data or [None])[0]
        except Exception as exc:  # pragma: no cover - depends on Wave 3 schema
            logger.warning(
                "rewards.accrue_for_pedido: pedidos lookup failed (%s) — Wave 3 not landed?",
                exc,
            )
            return []
    if pedido_row is None:
        logger.warning("rewards.accrue_for_pedido: pedido %s not found; no accrual", pedido_id)
        return []

    distributor_id = str(pedido_row.get("distributor_id") or "")
    if not distributor_id:
        logger.warning("rewards.accrue_for_pedido: pedido %s lacks distributor_id", pedido_id)
        return []

    org_id = pedido_row.get("org_id")
    valor_total = float(pedido_row.get("valor_total") or pedido_row.get("total") or 0)
    items = list(pedido_row.get("items") or pedido_row.get("itens") or [])
    quantidade = sum(int(i.get("quantidade") or i.get("quantity") or 0) for i in items)
    cats, prods = _items_categories_products(items)
    today = date.today()

    rules = _fetch_active_rules(db, org_id)
    inserted: list[str] = []
    for rule in rules:
        if not _within_validity(rule, today):
            continue
        if not _matches_targets(rule, distributor_id=distributor_id, items=items, categorias=cats, produtos=prods):
            continue
        if not _passes_thresholds(rule, valor_total=valor_total, quantidade=quantidade):
            continue
        payload = _build_accrual_row(
            rule=rule,
            org_id=org_id,
            distributor_id=distributor_id,
            valor_total=valor_total,
            source_pedido_id=pedido_id,
            source_relatorio_sellout_id=None,
        )
        res = db.table(LEDGER_TABLE).insert(payload).execute()
        rid = (res.data or [{}])[0].get("id") if res.data else None
        if rid:
            inserted.append(str(rid))
    return inserted


def accrue_for_sellout_approval(
    db: Any,
    *,
    relatorio_id: str,
    relatorio_row: Optional[dict[str, Any]] = None,
) -> list[str]:
    """Apply active reward rules to an approved sellout report.

    Args:
        db: Supabase client.
        relatorio_id: sellout report id; stamped as `source_relatorio_sellout_id`.
        relatorio_row: report dict — if absent, SELECT from `relatorios_sellout`.

    Returns:
        List of inserted accrual ids.
    """
    if relatorio_row is None:
        res = db.table(SELLOUT_TABLE).select("*").eq("id", relatorio_id).execute()
        relatorio_row = (res.data or [None])[0]
    if relatorio_row is None:
        logger.warning(
            "rewards.accrue_for_sellout_approval: relatorio %s not found",
            relatorio_id,
        )
        return []

    if relatorio_row.get("status") != "aprovado":
        logger.info(
            "rewards.accrue_for_sellout_approval: relatorio %s status=%s — skip",
            relatorio_id,
            relatorio_row.get("status"),
        )
        return []

    distributor_id = str(relatorio_row.get("distributor_id") or "")
    if not distributor_id:
        logger.warning(
            "rewards.accrue_for_sellout_approval: relatorio %s lacks distributor_id",
            relatorio_id,
        )
        return []

    org_id = relatorio_row.get("org_id")
    valor_total = float(relatorio_row.get("valor_total") or 0)
    items = list(relatorio_row.get("items_json") or [])
    quantidade = int(relatorio_row.get("quantidade_itens") or len(items))
    cats, prods = _items_categories_products(items)
    today = date.today()

    rules = _fetch_active_rules(db, org_id)
    inserted: list[str] = []
    for rule in rules:
        if not _within_validity(rule, today):
            continue
        if not _matches_targets(rule, distributor_id=distributor_id, items=items, categorias=cats, produtos=prods):
            continue
        if not _passes_thresholds(rule, valor_total=valor_total, quantidade=quantidade):
            continue
        payload = _build_accrual_row(
            rule=rule,
            org_id=org_id,
            distributor_id=distributor_id,
            valor_total=valor_total,
            source_pedido_id=None,
            source_relatorio_sellout_id=relatorio_id,
        )
        res = db.table(LEDGER_TABLE).insert(payload).execute()
        rid = (res.data or [{}])[0].get("id") if res.data else None
        if rid:
            inserted.append(str(rid))
    return inserted


def summarize_ledger(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Aggregate ledger rows into the balance summary the frontend renders."""
    def _amt(tipo: str, status: str) -> float:
        return float(sum(
            float(r.get("valor") or 0)
            for r in rows
            if r.get("tipo") == tipo and r.get("status") == status
        ))

    return {
        "cashbackAvailable": _amt("cashback", "liberado") - _amt("cashback", "utilizado"),
        "cashbackPending": _amt("cashback", "pendente"),
        "cashbackUsed": _amt("cashback", "utilizado"),
        "verbaMktAvailable": _amt("verba_mkt", "liberado") - _amt("verba_mkt", "utilizado"),
        "verbaMktPending": _amt("verba_mkt", "pendente"),
        "verbaMktUsed": _amt("verba_mkt", "utilizado"),
    }


__all__ = [
    "REGRAS_TABLE",
    "LEDGER_TABLE",
    "SELLOUT_TABLE",
    "RESGATES_TABLE",
    "accrue_for_pedido",
    "accrue_for_sellout_approval",
    "summarize_ledger",
]
