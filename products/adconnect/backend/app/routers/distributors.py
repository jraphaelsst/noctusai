from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..data.store import store
from ..auth_deps import get_current_user, require_role

router = APIRouter()


def _find(id_: str) -> dict[str, Any]:
    d = next((x for x in store.distributors if x["id"] == id_), None)
    if not d:
        raise HTTPException(404, "Distribuidor não encontrado")
    return d


def _check_ownership(user: dict[str, Any], id_: str) -> None:
    if user.get("role") == "admin":
        return
    if user.get("distributorId") != id_:
        raise HTTPException(403)


@router.get("/")
def list_all(_: dict[str, Any] = Depends(require_role("admin"))) -> dict[str, Any]:
    return {"data": store.distributors}


@router.get("/me")
def me(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    did = user.get("distributorId")
    if not did:
        raise HTTPException(401)
    return _find(did)


@router.get("/{id}")
def get_one(id: str, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    _check_ownership(user, id)
    return _find(id)


@router.get("/{id}/cnpjs")
def list_cnpjs(
    id: str, user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    _check_ownership(user, id)
    return {"data": _find(id).get("cnpjs", [])}


class CnpjInput(BaseModel):
    cnpj: str
    razaoSocial: str
    cidade: str
    uf: str
    isPrimary: bool = False


@router.post("/{id}/cnpjs", status_code=status.HTTP_201_CREATED)
def add_cnpj(
    id: str,
    body: CnpjInput,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    _check_ownership(user, id)
    d = _find(id)
    if any(c["cnpj"] == body.cnpj for c in d["cnpjs"]):
        raise HTTPException(409, "CNPJ já cadastrado no grupo")
    cnpj = {"id": f"cnpj-{secrets.token_hex(3)}", **body.model_dump()}
    if cnpj["isPrimary"]:
        for c in d["cnpjs"]:
            c["isPrimary"] = False
    d["cnpjs"].append(cnpj)
    return cnpj


@router.delete(
    "/{id}/cnpjs/{cnpj_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_cnpj(
    id: str,
    cnpj_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> None:
    _check_ownership(user, id)
    d = _find(id)
    idx = next((i for i, c in enumerate(d["cnpjs"]) if c["id"] == cnpj_id), -1)
    if idx < 0:
        raise HTTPException(404, "CNPJ não encontrado")
    if d["cnpjs"][idx]["isPrimary"]:
        raise HTTPException(400, "Não é possível remover o CNPJ principal")
    d["cnpjs"].pop(idx)


@router.patch("/{id}/cnpjs/{cnpj_id}/primary")
def set_primary(
    id: str,
    cnpj_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    _check_ownership(user, id)
    d = _find(id)
    target = next((c for c in d["cnpjs"] if c["id"] == cnpj_id), None)
    if not target:
        raise HTTPException(404, "CNPJ não encontrado")
    for c in d["cnpjs"]:
        c["isPrimary"] = c["id"] == cnpj_id
    return target
