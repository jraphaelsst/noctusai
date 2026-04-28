from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from ..data.store import store
from ..auth_deps import get_current_user, require_role

router = APIRouter()


def _reports_for(distributor_id: str) -> list[dict[str, Any]]:
    return [r for r in store.sellout_reports if r["distributorId"] == distributor_id]


@router.get("/reports")
def list_reports(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    did = user.get("distributorId")
    if not did:
        raise HTTPException(401)
    rows = sorted(_reports_for(did), key=lambda r: r["uploadDate"], reverse=True)
    return {"data": rows}


@router.get("/summary")
def summary(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    did = user.get("distributorId")
    if not did:
        raise HTTPException(401)
    rows = _reports_for(did)
    total = len(rows)
    approved = sum(1 for r in rows if r["status"] == "Aprovado")
    pending = sum(1 for r in rows if r["status"] == "Pendente")
    rejected = sum(1 for r in rows if r["status"] == "Rejeitado")
    rate = 0 if total == 0 else round(approved / total * 100)
    return {
        "total": total,
        "approved": approved,
        "pending": pending,
        "rejected": rejected,
        "complianceRate": rate,
    }


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_report(
    file: UploadFile = File(...),
    month: str = Form(...),
    items: int = Form(0),
    totalUnits: int = Form(0),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    did = user.get("distributorId")
    if not did:
        raise HTTPException(401)

    # Em produção os bytes do arquivo iriam para object storage (S3/Supabase).
    await file.read()

    report = {
        "id": f"so-{secrets.token_hex(3)}",
        "distributorId": did,
        "month": month,
        "fileName": file.filename or "sellout.xlsx",
        "uploadDate": datetime.now(timezone.utc).isoformat(),
        "status": "Pendente",
        "items": items,
        "totalUnits": totalUnits,
    }
    store.sellout_reports.append(report)
    return report


class StatusInput(BaseModel):
    status: str


@router.patch("/reports/{report_id}/status")
def set_report_status(
    report_id: str,
    body: StatusInput,
    _: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    r = next((x for x in store.sellout_reports if x["id"] == report_id), None)
    if not r:
        raise HTTPException(404, "Relatório não encontrado")
    if body.status not in ("Aprovado", "Pendente", "Rejeitado"):
        raise HTTPException(400, "Status inválido")
    r["status"] = body.status
    return r


@router.delete("/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_report(
    report_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> None:
    did = user.get("distributorId")
    if not did:
        raise HTTPException(401)
    idx = next(
        (i for i, x in enumerate(store.sellout_reports) if x["id"] == report_id),
        -1,
    )
    if idx < 0:
        raise HTTPException(404)
    if store.sellout_reports[idx]["distributorId"] != did:
        raise HTTPException(403)
    store.sellout_reports.pop(idx)
