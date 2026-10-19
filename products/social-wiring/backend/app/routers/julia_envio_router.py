"""Julia > Envio + Julia > Leads (wave 3, contract 5).

  GET  /api/julia/envio/regras                    member    {data: {diferenciar, regras: [{operacao, estagio_minimo, versao}]}}
  PUT  /api/julia/envio/regras                    admin     {diferenciar, regras: [{operacao, estagio_minimo}]} -> same shape
  GET  /api/julia/envio/politicas                 member    {data: {frios, captacoes, whatsapp_invalido, pesquisa}}
  PUT  /api/julia/envio/politicas                 admin     partial body -> same shape
  GET  /api/julia/leads?de&ate&nome&email&telefone&imovel&link&operacao[]&atendimento[]&status[]&canal[]&campanha&anuncio&page&page_size  member    {data: {items, total}}  (a member sees only their contatos, A7)
  GET  /api/julia/leads/canais                    member    {data: [{slug, label}]}
  POST /api/julia/leads/{contato_id}/enviar       member    200 {data: {status_envio, lead_id}} | 409 `ja_enviado` | 422 `contato_sem_telefone`
  POST /api/julia/leads/enviar-lote  {ids<=100}   member    {data: {ok: [id], erro: [{id, code}]}}
  GET  /api/julia/leads/{contato_id}/resumo       member    {data: {contato, slots, interacoes, entregas}}
  GET  /api/julia/leads/export.csv?<filters>&ids=a,b  admin     text/csv

Errors use the AppException envelope: 422 `estagio_invalido` / `operacoes_invalidas` /
`politica_invalida` / `filtro_invalido`; 403 `sem_acesso`; 404 `contato_nao_encontrado`; 409 `ja_enviado`
(`details.lead_id`); 502 `envio_falhou` (status stays `erro`, retry with the same call).
"""
# No `from __future__ import annotations`: FastAPI body/param models are resolved from the signature.
import logging
from datetime import date
from typing import Any, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import require_org_admin_for
from noctusai_lib.primitives.exceptions import AppException

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org, get_scoped_admin_client
from app.services import julia_acesso, julia_envio_service as envio, julia_leads_service as leads

logger = logging.getLogger(__name__)

router = APIRouter(tags=["julia-envio"])

envio.registrar()  # binds the qualificar_lead/captacao handlers, the policy hooks and the contexto/perguntas links

LOTE_MAX = 100


def get_envio_client() -> Any:
    """DI seam: the schema-scoped service-role client (tests override)."""
    return get_scoped_admin_client("social_wiring")


class RegraIn(StrictHttpModel):
    operacao: Literal["compra", "aluguel", "ambas"]
    #: Q6 (julia-v2): the stage agents computes at which the lead is sent to the CRM. Replaces the slot `grupos`.
    estagio_minimo: str = Field(min_length=2, max_length=64)


class RegrasIn(StrictHttpModel):
    diferenciar: Optional[bool] = None
    regras: list[RegraIn] = Field(min_length=1, max_length=2)


class FriosIn(StrictHttpModel):
    ativo: Optional[bool] = None
    modo: Optional[str] = Field(default=None, max_length=30)
    minutos: Optional[int] = None


class PoliticasIn(StrictHttpModel):
    frios: Optional[FriosIn] = None
    captacoes: Optional[str] = Field(default=None, max_length=20)
    whatsapp_invalido: Optional[bool] = None
    pesquisa: Optional[bool] = None


class LoteIn(StrictHttpModel):
    ids: list[UUID] = Field(min_length=1, max_length=LOTE_MAX)


def _org(auth: tuple) -> UUID:
    return coerce_org_uuid(auth[2])


def _ctx(auth: tuple, request: Optional[Request]) -> julia_acesso.AcessoCtx:
    return julia_acesso.contexto(auth, request)


# ── rules + policies ────────────────────────────────────────────────────────
@router.get("/api/julia/envio/regras")
def get_regras(auth: tuple = Depends(get_current_user_org), client: Any = Depends(get_envio_client)) -> dict[str, Any]:
    return {"data": envio.montar_regras(client, _org(auth))}


@router.put("/api/julia/envio/regras")
def put_regras(
    corpo: RegrasIn,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_envio_client),
) -> dict[str, Any]:
    require_org_admin_for(get_core_client(), auth, request, "As regras de envio")
    return {"data": envio.substituir_regras(client, _org(auth), corpo.diferenciar, [r.model_dump() for r in corpo.regras])}


@router.get("/api/julia/envio/politicas")
def get_politicas(auth: tuple = Depends(get_current_user_org), client: Any = Depends(get_envio_client)) -> dict[str, Any]:
    return {"data": envio.ler_politicas(client, _org(auth))}


@router.put("/api/julia/envio/politicas")
def put_politicas(
    corpo: PoliticasIn,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_envio_client),
) -> dict[str, Any]:
    require_org_admin_for(get_core_client(), auth, request, "As políticas de envio")
    patch = corpo.model_dump(exclude_unset=True)
    if "frios" in patch and patch["frios"] is not None:
        patch["frios"] = {k: v for k, v in patch["frios"].items() if v is not None}
    return {"data": envio.salvar_politicas(client, _org(auth), patch)}


def _ids_csv(ids: Optional[str]) -> list[str]:
    """`ids=a,b` -> validated UUID strings (<= LOTE_MAX); anything else is a typed 422."""
    if not ids:
        return []
    try:
        lista = [str(UUID(i.strip())) for i in ids.split(",") if i.strip()]
    except ValueError:
        raise AppException("filtro_invalido", "ids inválidos.", status_code=422, details={"filtro": "ids"})
    if len(lista) > LOTE_MAX:
        raise AppException("filtro_invalido", f"No máximo {LOTE_MAX} ids.", status_code=422, details={"filtro": "ids"})
    return lista


# ── Julia > Leads ────────────────────────────────────────────────────────────
def _filtros(
    de: Optional[date] = None, ate: Optional[date] = None,
    nome: Optional[str] = Query(default=None, max_length=120), email: Optional[str] = Query(default=None, max_length=120),
    telefone: Optional[str] = Query(default=None, max_length=40), imovel: Optional[str] = Query(default=None, max_length=60),
    link: Optional[str] = Query(default=None, max_length=300), operacao: list[str] = Query(default=[]),
    atendimento: list[str] = Query(default=[]), status: list[str] = Query(default=[]),
    canal: list[str] = Query(default=[], max_length=80),
    campanha: Optional[str] = Query(default=None, max_length=120), anuncio: Optional[str] = Query(default=None, max_length=120),
) -> dict[str, Any]:
    return {
        "de": de, "ate": ate, "nome": nome,
        "email": email, "telefone": telefone, "imovel": imovel, "link": link, "operacao": operacao,
        "atendimento": atendimento, "status": status, "canal": canal, "campanha": campanha, "anuncio": anuncio,
    }


@router.get("/api/julia/leads")
def listar_leads(
    request: Request = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=leads.PAGE_SIZE_MAX),
    filtros: dict[str, Any] = Depends(_filtros),
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_envio_client),
) -> dict[str, Any]:
    out = leads.listar(client, _org(auth), filtros, ctx=_ctx(auth, request), page=page, page_size=page_size)
    return {"data": out}


@router.get("/api/julia/leads/canais")
def listar_canais(auth: tuple = Depends(get_current_user_org), client: Any = Depends(get_envio_client)) -> dict[str, Any]:
    return {"data": leads.canais(client, _org(auth))}


@router.post("/api/julia/leads/enviar-lote")
def enviar_lote(
    corpo: LoteIn,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_envio_client),
) -> dict[str, Any]:
    org, ctx = _org(auth), _ctx(auth, request)
    ok: list[str] = []
    erro: list[dict[str, str]] = []
    for cid in dict.fromkeys(str(i) for i in corpo.ids):
        try:
            contato = leads.obter_contato(client, ctx, cid)
            res = envio.enviar(client, org, contato, "manual")
        except AppException as exc:
            erro.append({"id": cid, "code": exc.code})
            continue
        if res["ja_enviado"]:
            erro.append({"id": cid, "code": "ja_enviado"})
        else:
            ok.append(cid)
    return {"data": {"ok": ok, "erro": erro}}


@router.get("/api/julia/leads/export.csv")
def exportar(
    request: Request = None,
    ids: Optional[str] = Query(default=None, max_length=LOTE_MAX * 40),
    filtros: dict[str, Any] = Depends(_filtros),
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_envio_client),
) -> Response:
    require_org_admin_for(get_core_client(), auth, request, "A exportação de leads")
    lista = _ids_csv(ids)
    corpo = leads.exportar_csv(client, _org(auth), {**filtros, "ids": lista})
    return Response(
        content=corpo, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="julia-leads.csv"'},
    )


@router.post("/api/julia/leads/{contato_id}/enviar")
def enviar_contato(
    contato_id: UUID,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_envio_client),
) -> dict[str, Any]:
    org = _org(auth)
    contato = leads.obter_contato(client, _ctx(auth, request), contato_id)
    res = envio.enviar(client, org, contato, "manual")
    if res["ja_enviado"]:
        raise AppException("ja_enviado", "Este lead já foi enviado ao SW.", status_code=409, details={"lead_id": res["lead_id"]})
    return {"data": {"status_envio": res["status_envio"], "lead_id": res["lead_id"]}}


@router.get("/api/julia/leads/{contato_id}/resumo")
def resumo_contato(
    contato_id: UUID,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_envio_client),
) -> dict[str, Any]:
    org = _org(auth)
    contato = leads.obter_contato(client, _ctx(auth, request), contato_id)
    return {"data": leads.resumo(client, org, contato)}
