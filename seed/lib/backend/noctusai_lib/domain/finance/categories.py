"""Categories (a tree per org) and cost centers.

Default categories are seeded per org on first use (`ensure_default_categories`),
idempotently: re-running adds only what is missing, never duplicates.
"""
from __future__ import annotations

import logging
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
from .types import CategoryDirection

logger = logging.getLogger(__name__)

#: `(group, direction, children)` -- the pt-BR starter tree every org gets.
DEFAULT_CATEGORIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Receitas operacionais", "income", ("Vendas", "Serviços", "Mensalidades", "Outras receitas")),
    (
        "Despesas operacionais",
        "expense",
        (
            "Fornecedores",
            "Pessoal",
            "Aluguel e condomínio",
            "Marketing",
            "Impostos e taxas",
            "Tarifas bancárias",
            "Software e assinaturas",
            "Serviços de terceiros",
            "Outras despesas",
        ),
    ),
    ("Transferências", "transfer", ("Entre contas",)),
)


def _plain(value: Any) -> Any:
    return getattr(value, "value", value)


# ─── categories ──────────────────────────────────────────────────────────────


def _insert_category(s: Scope, *, name: str, direction: str, parent_id: Optional[str], is_default: bool) -> dict:
    now = now_iso()
    row = {
        "id": new_id(),
        "org_id": s.org_id,
        "parent_id": parent_id,
        "name": name,
        "direction": direction,
        "is_default": is_default,
        "active": True,
        "created_at": now,
        "updated_at": now,
    }
    try:
        return first(s.tbl("categories").insert(row).execute()) or row
    except Exception as exc:
        if is_unique_violation(exc):
            raise conflict(CATEGORIA_DUPLICADA, "Já existe uma categoria com este nome neste nível.") from exc
        raise


def seed_default_categories(s: Scope) -> list[dict]:
    """Insert the starter tree. Idempotent: existing (parent, lower(name)) pairs are left alone."""
    existing = s.rows("categories")
    seen = {(r.get("parent_id"), str(r["name"]).lower()): r for r in existing}
    created: list[dict] = []

    def ensure(name: str, direction: str, parent: Optional[str]) -> dict:
        key = (parent, name.lower())
        if key in seen:
            return seen[key]
        try:
            row = _insert_category(s, name=name, direction=direction, parent_id=parent, is_default=True)
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
        parent = ensure(group, direction, None)
        for child in children:
            ensure(child, direction, str(parent["id"]))
    return created


def ensure_default_categories(s: Scope) -> None:
    """Seed the starter tree the first time an org touches categories (no-op afterwards)."""
    resp = s.tbl("categories").select("id").eq("org_id", s.org_id).limit(1).execute()
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
    return _insert_category(s, name=name, direction=direction, parent_id=parent_id, is_default=False)


def update_category(s: Scope, category_id: Any, data: Mapping[str, Any]) -> dict:
    current = get_category(s, category_id)
    patch: dict[str, Any] = {}
    if "name" in data and data["name"] is not None:
        patch["name"] = str(data["name"]).strip()
    if "active" in data and data["active"] is not None:
        patch["active"] = bool(data["active"])
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
