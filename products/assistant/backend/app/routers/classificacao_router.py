"""The classifier's two admin routes (tier `org`, org ADMIN only). Nothing here classifies inline or sends anything.

* ``POST /api/classificacao/replay`` -- enqueue a re-classification of chosen intake rows under the registry's CURRENT
  prompt_version/model (new ai_outputs rows only; old rows and the intake outcome are never touched).
* ``GET /api/classificacao/amostra`` -- the stratified sample S4 labels. ``modo=cego`` (default) returns the message
  and opaque ids ONLY: the model's verdict, confidence, reason code and stratum never leave the backend, so the
  labeller cannot anchor on them. ``modo=revelado`` adds them (for reviewing disagreements after labelling).

S4 contract: label against ``intake_id`` (the message); ``output_id`` is the ai_outputs row the label is later compared
with. Both are uuids that carry no verdict.
"""
from __future__ import annotations

from typing import Any, Literal, Optional
from uuid import UUID

import anyio.to_thread
from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.integrations.prompt_registry import RegistroIAIndisponivel
from noctusai_seed.organ_auth import make_organ_auth

from app.dependencies import _db, coerce_org_uuid, get_admin_client, get_current_user_org
from app.shadow import classificador as clf
from app.shadow.worker import REPLAY_MAX, enfileirar_replay, job_repository

_organ_auth = make_organ_auth(get_current_user_org, lambda: _db.get_core_client(), context="A classificação")


async def require_org_admin(a: Any = Depends(_organ_auth.admin)) -> Any:
    """403 unless the caller is an admin of the selected org (the seed organ-auth admin gate)."""
    return a


router = make_router(tier="org", guard=require_org_admin, prefix="/api/classificacao", tags=["Classificação"])

_CAMPOS_VEREDITO = ("label", "confidence", "reason_code", "estrato")


class ReplayBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intake_ids: list[UUID] = Field(min_length=1, max_length=REPLAY_MAX)


def _registro_indisponivel(exc: RegistroIAIndisponivel) -> HTTPException:
    return HTTPException(status_code=503, detail="O prompt do classificador não está disponível no registro.")


@router.post("/replay")
async def replay(body: ReplayBody, auth: Any = Depends(require_org_admin)) -> dict:
    org_id = coerce_org_uuid(auth[2])
    try:
        return await enfileirar_replay(
            job_repository(get_admin_client()), get_admin_client, org_id=org_id, intake_ids=body.intake_ids,
        )
    except RegistroIAIndisponivel as exc:
        raise _registro_indisponivel(exc) from None


@router.get("/amostra")
async def amostra(
    por_estrato: int = Query(10, ge=1, le=100),
    modo: Literal["cego", "revelado"] = "cego",
    prompt_version: Optional[str] = Query(None, max_length=120),
    modelo: Optional[str] = Query(None, max_length=80),
    auth: Any = Depends(require_org_admin),
) -> dict:
    org_id = coerce_org_uuid(auth[2])
    if prompt_version is None or modelo is None:
        try:
            atual_versao, atual_modelo = await anyio.to_thread.run_sync(clf.versao_atual)
        except RegistroIAIndisponivel as exc:
            raise _registro_indisponivel(exc) from None
        prompt_version = prompt_version or atual_versao
        modelo = modelo or atual_modelo
    rows = await anyio.to_thread.run_sync(lambda: get_admin_client().rpc("amostra_classificacoes", {
        "p_org_id": str(org_id), "p_prompt_version": prompt_version, "p_model": modelo, "p_por_estrato": por_estrato,
    }).execute().data or [])
    itens = []
    for r in rows:
        item = {"intake_id": r["intake_id"], "output_id": r["output_id"], "texto": r["body"],
                "recebida_em": r["received_at"]}
        if modo == "revelado":
            item.update({k: r.get(k) for k in _CAMPOS_VEREDITO})
        itens.append(item)
    return {"modo": modo, "prompt_version": prompt_version, "modelo": modelo, "itens": itens}
