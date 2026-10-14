"""Categories (a tree per org) and cost centers.

Default categories are seeded per org on first use (`ensure_default_categories`),
idempotently: re-running adds only what is missing, never duplicates.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from ._common import Scope, first, new_id, now_iso
from .errors import (
    CATEGORIA_DUPLICADA,
    CATEGORIA_EM_USO,
    CENTRO_CUSTO_DUPLICADO,
    conflict,
    invalid,
)
from .types import ActivityKind, CategoryBehavior, CategoryDirection, DreLine, values

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class DefaultCategory:
    """One starter category and its DRE mapping (`KB § PATTERNS/finance/dre-structure.md §2a`, owner D56).

    `dre_line` / `behavior` None = no line (the group rows and `Entre contas`). `das` flags the category holding the
    DAS payable: its line is decided by the store's tax regime (`dre.py`), not by `dre_line` alone."""

    name: str
    dre_line: Optional[DreLine] = None
    behavior: Optional[CategoryBehavior] = None
    das: bool = False
    #: MEI Relatório Mensal group (E21); only meaningful on gross-revenue categories.
    activity: Optional[ActivityKind] = None


_V, _F = CategoryBehavior.VARIABLE, CategoryBehavior.FIXED
_L = DreLine

#: `(group, direction, children)` -- the pt-BR starter tree every org gets. Lines follow §2a; the table is DATA the
#: owner/accountant can re-map per store (`PATCH /categories/{id}`), never behaviour hidden in code.
DEFAULT_CATEGORIES: tuple[tuple[str, str, tuple[DefaultCategory, ...]], ...] = (
    (
        "Receitas operacionais",
        "income",
        (
            DefaultCategory("Vendas", _L.GROSS_REVENUE, _V, activity=ActivityKind.COMERCIO),
            DefaultCategory("Serviços", _L.GROSS_REVENUE, _V, activity=ActivityKind.SERVICOS),
            DefaultCategory("Mensalidades", _L.GROSS_REVENUE, _V, activity=ActivityKind.SERVICOS),
            DefaultCategory("Juros de parcelamento", _L.GROSS_REVENUE, _V),
            DefaultCategory("Outras receitas", _L.OTHER_OPERATING),
            DefaultCategory("Rendimentos e juros recebidos", _L.FINANCIAL_REVENUE),
        ),
    ),
    (
        "Despesas operacionais",
        "expense",
        (
            DefaultCategory("Impostos sobre vendas", _L.DEDUCTIONS, _V, das=True),
            DefaultCategory("Mercadorias / insumos para revenda", _L.COST_OF_SALES, _V),
            DefaultCategory("Terceiros na produção / entrega", _L.COST_OF_SALES, _V),
            DefaultCategory("Pessoal", _L.ADMINISTRATIVE_EXPENSES, _F),
            DefaultCategory("Aluguel e condomínio", _L.ADMINISTRATIVE_EXPENSES, _F),
            DefaultCategory("Software e assinaturas", _L.ADMINISTRATIVE_EXPENSES, _F),
            DefaultCategory("Fornecedores gerais", _L.ADMINISTRATIVE_EXPENSES, _F),
            DefaultCategory("Contabilidade / jurídico / consultoria", _L.ADMINISTRATIVE_EXPENSES, _F),
            DefaultCategory("Taxas e licenças", _L.ADMINISTRATIVE_EXPENSES, _F),
            DefaultCategory("DAS-MEI", _L.ADMINISTRATIVE_EXPENSES, _F, das=True),
            DefaultCategory("Marketing", _L.SELLING_EXPENSES, _V),
            DefaultCategory("Frete de envio", _L.SELLING_EXPENSES, _V),
            DefaultCategory("Comissões (marketplace/afiliados)", _L.SELLING_EXPENSES, _V),
            DefaultCategory("Taxas de cartão/gateway", _L.SELLING_EXPENSES, _V),
            DefaultCategory("Tarifa de chargeback", _L.SELLING_EXPENSES, _V),
            DefaultCategory("Tarifas bancárias", _L.FINANCIAL_EXPENSES),
            DefaultCategory("Antecipação de recebíveis", _L.FINANCIAL_EXPENSES),
            DefaultCategory("Juros e multas pagos", _L.FINANCIAL_EXPENSES),
            DefaultCategory("IRPJ / CSLL", _L.INCOME_TAXES),
            DefaultCategory("Outras despesas", _L.OTHER_OPERATING),
        ),
    ),
    ("Transferências", "transfer", (DefaultCategory("Entre contas"),)),
)

#: What `behavior` means when a category leaves it NULL: the line's natural behaviour (CONTRACT §10.5.6).
LINE_DEFAULT_BEHAVIOR: dict[str, CategoryBehavior] = {
    DreLine.GROSS_REVENUE.value: _V,
    DreLine.DEDUCTIONS.value: _V,
    DreLine.COST_OF_SALES.value: _V,
    DreLine.SELLING_EXPENSES.value: _V,
}


def default_behavior(line: Optional[str]) -> CategoryBehavior:
    return LINE_DEFAULT_BEHAVIOR.get(str(line), CategoryBehavior.FIXED)


def _plain(value: Any) -> Any:
    return getattr(value, "value", value)


def clean_code(value: Any) -> Optional[str]:
    """An accounting code is free text the contador chose (`1.1.01.001`, `31102`...): trimmed, blank -> NULL."""
    text = str(value).strip() if value is not None else ""
    return text or None


# ─── categories ──────────────────────────────────────────────────────────────


def _insert_category(
    s: Scope,
    *,
    name: str,
    direction: str,
    parent_id: Optional[str],
    is_default: bool,
    dre_line: Optional[str] = None,
    behavior: Optional[str] = None,
    is_das: bool = False,
    accounting_code: Optional[str] = None,
    activity_kind: Optional[str] = None,
) -> dict:
    now = now_iso()
    row = {
        "id": new_id(),
        "org_id": s.org_id,
        "parent_id": parent_id,
        "name": name,
        "direction": direction,
        "is_default": is_default,
        "dre_line": dre_line,
        "behavior": behavior,
        "is_das": is_das,
        "active": True,
        "created_at": now,
        "updated_at": now,
        # E21 additive columns: sent only when set (a database that has not applied them yet still seeds its tree)
        **({"accounting_code": accounting_code} if accounting_code is not None else {}),
        **({"activity_kind": activity_kind} if activity_kind is not None else {}),
    }
    try:
        return first(s.tbl("categories").insert(row).execute()) or row
    except Exception as exc:
        if is_unique_violation(exc):
            raise conflict(CATEGORIA_DUPLICADA, "Já existe uma categoria com este nome neste nível.") from exc
        raise


def seed_default_categories(s: Scope) -> list[dict]:
    """Insert the starter tree and map it to DRE lines. Idempotent and NON-DESTRUCTIVE:

    * a (parent, lower(name)) pair that already exists is never recreated or renamed;
    * on an existing DEFAULT row, `dre_line` / `behavior` / `is_das` are filled ONLY where they are NULL / unset,
      so an owner's or accountant's edit is never overwritten."""
    existing = s.rows("categories")
    seen = {(r.get("parent_id"), str(r["name"]).lower()): r for r in existing}
    created: list[dict] = []

    def ensure(name: str, direction: str, parent: Optional[str], spec: Optional[DefaultCategory]) -> dict:
        key = (parent, name.lower())
        line = spec.dre_line.value if spec and spec.dre_line else None
        behavior = spec.behavior.value if spec and spec.behavior else None
        das = bool(spec and spec.das)
        activity = spec.activity.value if spec and spec.activity else None
        if key in seen:
            row = seen[key]
            if row.get("is_default") and spec is not None:
                patch: dict[str, Any] = {}
                if line and row.get("dre_line") is None:
                    patch["dre_line"] = line
                if behavior and row.get("behavior") is None:
                    patch["behavior"] = behavior
                if das and not row.get("is_das"):
                    patch["is_das"] = True
                if activity and row.get("activity_kind") is None:
                    patch["activity_kind"] = activity
                if patch:
                    patch["updated_at"] = now_iso()
                    s.tbl("categories").update(patch).eq("org_id", s.org_id).eq("id", str(row["id"])).execute()
                    row = {**row, **patch}
                    seen[key] = row
            return row
        try:
            row = _insert_category(
                s, name=name, direction=direction, parent_id=parent, is_default=True,
                dre_line=line, behavior=behavior, is_das=das, activity_kind=activity,
            )
        except Exception:
            # Lost a seed race with a concurrent first request: take the winner's row.
            again = {(r.get("parent_id"), str(r["name"]).lower()): r for r in s.rows("categories")}
            if key in again:
                return again[key]
            raise
        seen[key] = row
        created.append(row)
        return row

    for group, direction, children in DEFAULT_CATEGORIES:
        parent = ensure(group, direction, None, None)
        for child in children:
            ensure(child.name, direction, str(parent["id"]), child)
    return created


def ensure_default_categories(s: Scope) -> None:
    """Seed / upgrade the starter tree the first time an org touches categories (no-op afterwards).

    "First time" = no category carries a DRE line yet: a brand-new org (nothing at all) and a LEGACY org whose
    tree predates the DRE mapping both qualify, exactly once -- afterwards a deleted default stays deleted."""
    resp = s.tbl("categories").select("id").eq("org_id", s.org_id).not_.is_("dre_line", "null").limit(1).execute()
    if not resp.data:
        seed_default_categories(s)


def list_categories(s: Scope) -> list[dict]:
    ensure_default_categories(s)
    rows = s.rows("categories")
    rows.sort(key=lambda r: (str(r.get("parent_id") or ""), str(r["name"]).lower(), str(r["id"])))
    return rows


def get_category(s: Scope, category_id: Any) -> dict:
    return s.get("categories", category_id, what="Categoria")


def descendant_ids(s: Scope, category_id: Any) -> list[str]:
    """`category_id` and every category beneath it."""
    rows = s.rows("categories")
    children: dict[str, list[str]] = {}
    for r in rows:
        if r.get("parent_id"):
            children.setdefault(str(r["parent_id"]), []).append(str(r["id"]))
    out, stack = [], [str(category_id)]
    while stack:
        cur = stack.pop()
        out.append(cur)
        stack.extend(children.get(cur, []))
    return out


def _name_taken(s: Scope, name: str, parent_id: Optional[str], *, except_id: Any = None) -> bool:
    for r in s.rows("categories"):
        if (
            str(r["name"]).lower() == name.lower()
            and (r.get("parent_id") or None) == (parent_id or None)
            and (except_id is None or str(r["id"]) != str(except_id))
        ):
            return True
    return False


def create_category(s: Scope, data: Mapping[str, Any]) -> dict:
    ensure_default_categories(s)
    name = str(data["name"]).strip()
    direction = _plain(data["direction"])
    parent_id = str(data["parent_id"]) if data.get("parent_id") else None
    if parent_id:
        parent = s.require_owned("categories", parent_id, what="Categoria pai", field="parent_id")
        if parent["direction"] != direction:
            raise invalid("direction", "A categoria precisa ter a mesma direção da categoria pai.", code="categoria_direcao_invalida")
    if _name_taken(s, name, parent_id):
        raise conflict(CATEGORIA_DUPLICADA, "Já existe uma categoria com este nome neste nível.")
    return _insert_category(
        s, name=name, direction=direction, parent_id=parent_id, is_default=False,
        dre_line=_plain(data.get("dre_line")), behavior=_plain(data.get("behavior")), is_das=bool(data.get("is_das") or False),
        accounting_code=clean_code(data.get("accounting_code")), activity_kind=_plain(data.get("activity_kind")),
    )


def update_category(s: Scope, category_id: Any, data: Mapping[str, Any]) -> dict:
    current = get_category(s, category_id)
    patch: dict[str, Any] = {}
    if "name" in data and data["name"] is not None:
        patch["name"] = str(data["name"]).strip()
    if "active" in data and data["active"] is not None:
        patch["active"] = bool(data["active"])
    for col in ("dre_line", "behavior", "activity_kind"):  # None is a value here: it unclassifies / returns to the default
        if col in data:
            patch[col] = _plain(data[col])
    if "accounting_code" in data:
        patch["accounting_code"] = clean_code(data["accounting_code"])
    if data.get("is_das") is not None:
        patch["is_das"] = bool(data["is_das"])
    if "parent_id" in data:
        new_parent = str(data["parent_id"]) if data["parent_id"] else None
        if new_parent:
            parent = s.require_owned("categories", new_parent, what="Categoria pai", field="parent_id")
            if parent["direction"] != current["direction"]:
                raise invalid("parent_id", "A categoria pai precisa ter a mesma direção.", code="categoria_direcao_invalida")
            if new_parent in descendant_ids(s, category_id):
                raise invalid("parent_id", "Uma categoria não pode ficar abaixo de si mesma.", code="categoria_ciclo")
        patch["parent_id"] = new_parent
    if not patch:
        return current
    target_parent = patch.get("parent_id", current.get("parent_id"))
    target_name = patch.get("name", current["name"])
    if ("name" in patch or "parent_id" in patch) and _name_taken(s, target_name, target_parent, except_id=category_id):
        raise conflict(CATEGORIA_DUPLICADA, "Já existe uma categoria com este nome neste nível.")
    patch["updated_at"] = now_iso()
    try:
        s.tbl("categories").update(patch).eq("org_id", s.org_id).eq("id", str(category_id)).execute()
    except Exception as exc:
        if is_unique_violation(exc):
            raise conflict(CATEGORIA_DUPLICADA, "Já existe uma categoria com este nome neste nível.") from exc
        raise
    return {**current, **patch}


def _category_in_use(s: Scope, category_id: str) -> bool:
    for table, col in (("categories", "parent_id"), ("entries", "category_id")):
        resp = s.tbl(table).select("id").eq("org_id", s.org_id).eq(col, category_id).limit(1).execute()
        if resp.data:
            return True
    for rec in s.rows("recurrences"):
        if str((rec.get("template") or {}).get("category_id") or "") == category_id:
            return True
    return False


def delete_category(s: Scope, category_id: Any) -> None:
    get_category(s, category_id)
    if _category_in_use(s, str(category_id)):
        raise conflict(CATEGORIA_EM_USO, "A categoria tem subcategorias ou lançamentos e não pode ser excluída.")
    s.tbl("categories").delete().eq("org_id", s.org_id).eq("id", str(category_id)).execute()


def find_category_by_hint(s: Scope, hint: Optional[str], direction: CategoryDirection) -> Optional[str]:
    """Resolve a bridge's `category_hint` (a category name) to an id of the right direction; None if unknown."""
    if not hint:
        return None
    ensure_default_categories(s)
    wanted = hint.strip().lower()
    for r in s.rows("categories"):
        if str(r["name"]).lower() == wanted and r["direction"] == direction.value and r.get("active", True):
            return str(r["id"])
    return None


# ─── cost centers ────────────────────────────────────────────────────────────


def list_cost_centers(s: Scope) -> list[dict]:
    rows = s.rows("cost_centers")
    rows.sort(key=lambda r: (str(r["code"]).lower(), str(r["id"])))
    return rows


def get_cost_center(s: Scope, cost_center_id: Any) -> dict:
    return s.get("cost_centers", cost_center_id, what="Centro de custo")


def _code_taken(s: Scope, code: str, *, except_id: Any = None) -> bool:
    return any(
        str(r["code"]).lower() == code.lower() and (except_id is None or str(r["id"]) != str(except_id))
        for r in s.rows("cost_centers")
    )


def create_cost_center(s: Scope, data: Mapping[str, Any]) -> dict:
    code = str(data["code"]).strip()
    if _code_taken(s, code):
        raise conflict(CENTRO_CUSTO_DUPLICADO, "Já existe um centro de custo com este código.")
    now = now_iso()
    row = {
        "id": new_id(),
        "org_id": s.org_id,
        "code": code,
        "name": str(data["name"]).strip(),
        "active": True,
        "created_at": now,
        "updated_at": now,
    }
    try:
        return first(s.tbl("cost_centers").insert(row).execute()) or row
    except Exception as exc:
        if is_unique_violation(exc):
            raise conflict(CENTRO_CUSTO_DUPLICADO, "Já existe um centro de custo com este código.") from exc
        raise


def update_cost_center(s: Scope, cost_center_id: Any, data: Mapping[str, Any]) -> dict:
    current = get_cost_center(s, cost_center_id)
    patch: dict[str, Any] = {}
    if data.get("code") is not None:
        patch["code"] = str(data["code"]).strip()
        if _code_taken(s, patch["code"], except_id=cost_center_id):
            raise conflict(CENTRO_CUSTO_DUPLICADO, "Já existe um centro de custo com este código.")
    if data.get("name") is not None:
        patch["name"] = str(data["name"]).strip()
    if data.get("active") is not None:
        patch["active"] = bool(data["active"])
    if not patch:
        return current
    patch["updated_at"] = now_iso()
    try:
        s.tbl("cost_centers").update(patch).eq("org_id", s.org_id).eq("id", str(cost_center_id)).execute()
    except Exception as exc:
        if is_unique_violation(exc):
            raise conflict(CENTRO_CUSTO_DUPLICADO, "Já existe um centro de custo com este código.") from exc
        raise
    return {**current, **patch}


__all__ = [
    "DEFAULT_CATEGORIES",
    "DefaultCategory",
    "LINE_DEFAULT_BEHAVIOR",
    "default_behavior",
    "create_category",
    "create_cost_center",
    "delete_category",
    "descendant_ids",
    "ensure_default_categories",
    "find_category_by_hint",
    "get_category",
    "get_cost_center",
    "list_categories",
    "list_cost_centers",
    "seed_default_categories",
    "update_category",
    "update_cost_center",
]
