"""Campanhas CRUD — /api/campanhas (sw-lead-to-contract CONTRACT §1.1).

    GET    /api/campanhas        → {"data": [Campanha]}
    POST   /api/campanhas        → {"data": Campanha}   (201)
    PATCH  /api/campanhas/{id}   → {"data": Campanha}
    DELETE /api/campanhas/{id}   → soft delete, frees the Meta ids (204)

Distinct from `campanhas_router` (the /solicitacoes signal), which keeps its
own prefix and is mounted untouched. Auth: `get_current_user_org` on every
route; org comes from the trusted resolver, never user_metadata.
"""
from __future__ import annotations

import logging
from typing import Literal, Optional

from typing import Callable

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse
from pydantic import Field
from noctusai_lib.api import StrictHttpModel

from app.dependencies import coerce_org_uuid, get_admin_client, get_current_user_org
from app.services.campanhas_service import CampanhaError
from app.services.campanhas_veiculacao_service import (
    CampanhaNaoEncontrada,
    CodigosDesconhecidos,
    VeiculacaoEmUso,
    VeiculacaoInvalida,
    build_campanhas_veiculacao_service,
)

logger = logging.getLogger(__name__)

class _WrongValueRoute(APIRoute):
    """CONTRACT Conventions: a WRONG value is 400, not FastAPI's 422.

    Scoped to this router only (no app-wide handler). Auth still runs first:
    the dependency's 401 is raised before validation errors surface.
    """

    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError as exc:
                campos = sorted({".".join(str(p) for p in e["loc"][1:]) for e in exc.errors()})
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": "Valor inválido: " + (", ".join(c for c in campos if c) or "corpo da requisição"),
                             "code": "valor_invalido"},
                )

        return handler


router = APIRouter(prefix="/api/campanhas", tags=["campanhas"], route_class=_WrongValueRoute)


class VeiculacaoIn(StrictHttpModel):
    canal: Literal["meta_ads"]
    nivel: Literal["campaign", "adset", "ad", "form"]
    ref_codigo: str = Field(..., min_length=1, max_length=64)


class CampanhaCreateIn(StrictHttpModel):
    nome: str = Field(..., min_length=1, max_length=200)
    imovel_codigos: list[str] = Field(default_factory=list)
    veiculacoes: list[VeiculacaoIn] = Field(default_factory=list)


class CampanhaPatchIn(StrictHttpModel):
    nome: Optional[str] = Field(None, min_length=1, max_length=200)
    imovel_codigos: Optional[list[str]] = None
    veiculacoes: Optional[list[VeiculacaoIn]] = None


def _veics(items: Optional[list[VeiculacaoIn]]) -> Optional[list[dict]]:
    if items is None:
        return None
    return [
        {"canal": v.canal, "nivel": v.nivel, "ref_codigo": v.ref_codigo.strip()}
        for v in items
    ]


def _err(code_http: int, detail: str, code: Optional[str] = None, **extra) -> JSONResponse:
    body = {"detail": detail, **({"code": code} if code else {}), **extra}
    return JSONResponse(status_code=code_http, content=body)


def _http(exc: Exception) -> JSONResponse:
    """Contract errors: top-level `{"detail", "code"}`; 400 wrong value, 404 unknown, 409 conflict."""
    if isinstance(exc, CampanhaNaoEncontrada):
        return _err(status.HTTP_404_NOT_FOUND, "Campanha não encontrada.", "campanha_nao_encontrada")
    if isinstance(exc, CodigosDesconhecidos):
        return _err(
            status.HTTP_400_BAD_REQUEST, "Imóveis desconhecidos: " + ", ".join(exc.codigos),
            "imoveis_desconhecidos", codigos=exc.codigos,
        )
    if isinstance(exc, VeiculacaoInvalida):
        return _err(status.HTTP_400_BAD_REQUEST, f"Veiculação repetida: {exc}", "veiculacao_repetida")
    if isinstance(exc, VeiculacaoEmUso):
        # The FE pins this error to the veiculação row by finding `ref_codigo`
        # verbatim in `detail` — keep it in the message.
        objeto = {"campaign": "A campanha Meta", "adset": "O conjunto", "ad": "O anúncio",
                  "form": "O formulário"}.get(exc.nivel, "O objeto")
        onde = f' "{exc.campanha_nome}"' if exc.campanha_nome else " de outra campanha"
        return _err(
            status.HTTP_409_CONFLICT,
            f"{objeto} {exc.ref_codigo} já está na campanha{onde}", "veiculacao_em_uso",
        )
    logger.error("campanhas crud failed: %s", exc, exc_info=True)
    return _err(status.HTTP_503_SERVICE_UNAVAILABLE, "Não foi possível salvar a campanha.")


@router.get("")
async def listar(auth=Depends(get_current_user_org), db=Depends(get_admin_client)) -> Response:
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return {"data": build_campanhas_veiculacao_service(db).listar(org_id)}
    except CampanhaError as exc:
        return _http(exc)


@router.post("", status_code=status.HTTP_201_CREATED)
async def criar(
    payload: CampanhaCreateIn, auth=Depends(get_current_user_org), db=Depends(get_admin_client)
) -> Response:
    user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        data = build_campanhas_veiculacao_service(db).criar(
            org_id, nome=payload.nome.strip(), imovel_codigos=payload.imovel_codigos,
            veiculacoes=_veics(payload.veiculacoes) or [],
            created_by=getattr(user, "id", None),
        )
    except CampanhaError as exc:
        return _http(exc)
    return {"data": data}


@router.patch("/{campanha_id}")
async def atualizar(
    campanha_id: str, payload: CampanhaPatchIn,
    auth=Depends(get_current_user_org), db=Depends(get_admin_client),
) -> Response:
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        data = build_campanhas_veiculacao_service(db).atualizar(
            org_id, campanha_id,
            nome=payload.nome.strip() if payload.nome is not None else None,
            imovel_codigos=payload.imovel_codigos, veiculacoes=_veics(payload.veiculacoes),
        )
    except CampanhaError as exc:
        return _http(exc)
    return {"data": data}


@router.delete("/{campanha_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir(
    campanha_id: str, auth=Depends(get_current_user_org), db=Depends(get_admin_client)
) -> Response:
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        build_campanhas_veiculacao_service(db).excluir(org_id, campanha_id)
    except CampanhaError as exc:
        return _http(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
