"""Item categories -- a tree per org. No default tree is seeded (a catalog's taxonomy is the host's)."""
from __future__ import annotations

from typing import Any, Mapping, Optional

from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from ._common import Scope, first, new_id, now_iso
from .errors import CATEGORIA_CICLO, CATEGORIA_DUPLICADA, CATEGORIA_EM_USO, conflict, invalid

_DUP_MSG = "Já existe uma categoria com este nome neste nível."


def list_categories(s: Scope) -> list[dict]:
    rows = s.rows("item_categories")
    rows.sort(key=lambda r: (str(r.get("parent_id") or ""), str(r["name"]).lower(), str(r["id"])))
    return rows


def get_category(s: Scope, category_id: Any) -> dict:
    return s.get("item_categories", category_id, what="Categoria")


def descendant_ids(s: Scope, category_id: Any) -> list[str]:
    """`category_id` and every category beneath it."""
    children: dict[str, list[str]] = {}
    for r in s.rows("item_categories"):
        if r.get("parent_id"):
            children.setdefault(str(r["parent_id"]), []).append(str(r["id"]))
    out, stack = [], [str(category_id)]
    while stack:
        cur = stack.pop()
        out.append(cur)
        stack.extend(children.get(cur, []))
    return out


def category_paths(s: Scope) -> dict[str, str]:
    """`{id: "Pai > Filho"}` for every category (CSV export/import speak paths, never ids)."""
    rows = {str(r["id"]): r for r in s.rows("item_categories")}

    def path(cid: str) -> str:
        parts, seen = [], set()
        while cid and cid in rows and cid not in seen:
            seen.add(cid)
            parts.append(str(rows[cid]["name"]))
            cid = str(rows[cid].get("parent_id") or "")
        return " > ".join(reversed(parts))

    return {cid: path(cid) for cid in rows}


def _name_taken(s: Scope, name: str, parent_id: Optional[str], *, except_id: Any = None) -> bool:
    return any(
        str(r["name"]).lower() == name.lower()
        and (r.get("parent_id") or None) == (parent_id or None)
        and (except_id is None or str(r["id"]) != str(except_id))
        for r in s.rows("item_categories")
    )


def create_category(s: Scope, data: Mapping[str, Any]) -> dict:
    name = str(data["name"]).strip()
    if not name:
        raise invalid("name", "Informe o nome da categoria.", "campo_obrigatorio")
    parent_id = str(data["parent_id"]) if data.get("parent_id") else None
    if parent_id:
        s.require_owned("item_categories", parent_id, what="Categoria pai", field="parent_id")
    if _name_taken(s, name, parent_id):
        raise conflict(CATEGORIA_DUPLICADA, _DUP_MSG)
    now = now_iso()
    row = {
        "id": new_id(), "org_id": s.org_id, "parent_id": parent_id, "name": name,
        "is_active": True, "created_at": now, "updated_at": now,
    }
    try:
        return first(s.tbl("item_categories").insert(row).execute()) or row
    except Exception as exc:
        if is_unique_violation(exc):
            raise conflict(CATEGORIA_DUPLICADA, _DUP_MSG) from exc
        raise


def update_category(s: Scope, category_id: Any, data: Mapping[str, Any]) -> dict:
    current = get_category(s, category_id)
    patch: dict[str, Any] = {}
    if data.get("name") is not None:
        patch["name"] = str(data["name"]).strip()
        if not patch["name"]:
            raise invalid("name", "Informe o nome da categoria.", "campo_obrigatorio")
    if data.get("is_active") is not None:
        patch["is_active"] = bool(data["is_active"])
    if "parent_id" in data:
        new_parent = str(data["parent_id"]) if data["parent_id"] else None
        if new_parent:
            s.require_owned("item_categories", new_parent, what="Categoria pai", field="parent_id")
            if new_parent in descendant_ids(s, category_id):
                raise invalid("parent_id", "Uma categoria não pode ficar abaixo de si mesma.", CATEGORIA_CICLO)
        patch["parent_id"] = new_parent
    if not patch:
        return current
    target_parent = patch.get("parent_id", current.get("parent_id"))
    target_name = patch.get("name", current["name"])
    if ("name" in patch or "parent_id" in patch) and _name_taken(s, target_name, target_parent, except_id=category_id):
        raise conflict(CATEGORIA_DUPLICADA, _DUP_MSG)
    patch["updated_at"] = now_iso()
    try:
        s.tbl("item_categories").update(patch).eq("org_id", s.org_id).eq("id", str(category_id)).execute()
    except Exception as exc:
        if is_unique_violation(exc):
            raise conflict(CATEGORIA_DUPLICADA, _DUP_MSG) from exc
        raise
    return {**current, **patch}


def _in_use(s: Scope, category_id: str) -> bool:
    for table, col in (("item_categories", "parent_id"), ("items", "category_id")):
        resp = s.tbl(table).select("id").eq("org_id", s.org_id).eq(col, category_id).limit(1).execute()
        if resp.data:
            return True
    return False


def delete_category(s: Scope, category_id: Any) -> None:
    get_category(s, category_id)
    if _in_use(s, str(category_id)):
        raise conflict(CATEGORIA_EM_USO, "A categoria tem subcategorias ou itens e não pode ser excluída.")
    s.tbl("item_categories").delete().eq("org_id", s.org_id).eq("id", str(category_id)).execute()


__all__ = [
    "category_paths",
    "create_category",
    "delete_category",
    "descendant_ids",
    "get_category",
    "list_categories",
    "update_category",
]
