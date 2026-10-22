"""Julia wave 12 -- Cloud-API pages: transport status, Modelos, Disparos, Atualizacao de imoveis (contract 14).

  GET  /api/julia/cloud/status                              org member   transport + "Aguardando verificacao da Meta" flag
  PUT  /api/julia/cloud/conexoes/{id}                       org admin    transporte waha|cloud + Cloud ids + access token
  POST /api/julia/cloud/perfil/aplicar                      org admin    push the perfil_whatsapp section to Meta (Cloud only)

  GET  /api/julia/modelos[?status=&categoria=]              org member   {modelos, catalogo}
  POST /api/julia/modelos                                   org admin    201
  POST /api/julia/modelos/preview                           org member   live preview / "Simule com exemplos"
  GET|PATCH|DELETE /api/julia/modelos/{id}                  member | admin
  POST /api/julia/modelos/{id}/enviar                       org admin    409 transporte_indisponivel unless Cloud

  GET  /api/julia/disparos[?aba=]                           org member   {disparos, catalogo}
  POST /api/julia/disparos                                  org admin    201
  POST /api/julia/disparos/primeiro-contato                 org admin    Meta lead-form first contact (Cloud only)
  GET|PATCH|DELETE /api/julia/disparos/{id}                 member | admin
  GET  /api/julia/disparos/{id}/alvos | /previa             org member
  POST /api/julia/disparos/{id}/agendar | /cancelar         org admin    (any transport: nothing is sent now)
  POST /api/julia/disparos/{id}/enviar                      org admin    409 transporte_indisponivel unless Cloud

  GET  /api/julia/proprietarios[?opt_out=&busca=]           org member
  POST /api/julia/proprietarios                             org admin    201
  POST /api/julia/proprietarios/{id}/confirmar              org admin    updates SW imoveis (needs a reply to a Cloud template)
  POST /api/julia/proprietarios/{id}/opt-out                org admin    "parar"
  DELETE /api/julia/proprietarios/{id}                      org admin

Envelope `{"data": ...}` (errors: `AppException` -> `{"error": {...}}`); request models are strict. The org is the
session's selected org (auth tuple), never a body field.
"""
import anyio
# No `from __future__ import annotations`: FastAPI resolves the body models from the real annotations.
from datetime import datetime
from typing import Any, Callable, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import require_org_admin_for
from noctusai_lib.integrations.whatsapp.mappers import chat_id_for_phone
from noctusai_lib.primitives.exceptions import AppException
from noctusai_lib.primitives.phone import normalize_phone

from app.dependencies import (
    coerce_org_uuid, get_admin_client, get_core_client, get_current_user_org, get_scoped_admin_client,
)
from app.routers.julia_conhecimento_router import get_nome_agente
from app.routers.whatsapp_connections_router import get_agents_client_factory, get_connection_store
from app.services import (
    julia_aviso_service, julia_conhecimento_service, julia_contatos_service, julia_disparos_service, julia_modelos_service,
    julia_proprietarios_service, julia_transporte,
)
from app.services.imoveis_service import build_imoveis_service
from app.services.whatsapp_connection_store import WhatsAppConnectionStore

router = APIRouter(prefix="/api/julia", tags=["julia-cloud"])


# ── DI seams (tests override) ───────────────────────────────────────────────
def get_cloud_db() -> Any:
    """The schema-scoped service-role client."""
    return get_scoped_admin_client("social_wiring")


def get_imoveis_service() -> Any:
    return build_imoveis_service(get_admin_client())


def get_transporte_factory() -> Callable[[Any], julia_transporte.Transporte]:
    """connection -> `Transporte`. Default: the real seam (WAHA text / Cloud over the seed Meta client)."""
    return julia_transporte.transporte_da_conexao


def _admin(auth: tuple, request: Request, context: str) -> UUID:
    require_org_admin_for(get_core_client(), auth, request, context)
    return coerce_org_uuid(auth[2])


def _user_id(auth: tuple) -> Any:
    user = auth[0]
    return getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)


def _conexao(store: WhatsAppConnectionStore, org_id: UUID, connection_id: Optional[UUID]) -> Any:
    """The connection a send goes through, with the decrypted token: the named one; else the org's configured
    Cloud one; else its first line (which then fails the Cloud gate with the 409)."""
    if connection_id is not None:
        c = store.get_connection(connection_id=connection_id, org_id=org_id, decrypt=True)
        if c is None:
            raise AppException("conexao_nao_encontrada", "Conexão não encontrada.", status_code=404)
        return c
    todas = store.list_connections(org_id=org_id)
    for c in todas:
        if c.transporte == julia_transporte.TRANSPORTE_CLOUD:
            full = store.get_connection(connection_id=c.id, org_id=org_id, decrypt=True)
            if julia_transporte.cloud_configurada(full):
                return full
    return todas[0] if todas else None


def _contexto_envio(db: Any, org_id: UUID, nome_agente: Optional[str]) -> dict[str, str]:
    return {
        "nome_julia": nome_agente or julia_conhecimento_service.PERSONA_NOME,
        "nome_imobiliaria": julia_aviso_service.nome_da_org(get_core_client(), org_id) or "",
    }


def _meta(store: WhatsAppConnectionStore, org_id: UUID, **extra: Any) -> dict[str, Any]:
    """`meta.transporte`: "cloud" once the org has a configured Cloud connection, else "waha" (the FE shows the
    "Aguardando verificação da Meta" badge while it is not "cloud")."""
    cloud = False
    for c in store.list_connections(org_id=org_id):
        if c.transporte == julia_transporte.TRANSPORTE_CLOUD:
            full = store.get_connection(connection_id=c.id, org_id=org_id, decrypt=True)
            cloud = cloud or julia_transporte.cloud_configurada(full)
    return {"transporte": "cloud" if cloud else "waha", **extra}


def _modelo_out(m: dict[str, Any]) -> dict[str, Any]:
    return {**m, "conteudo": m["corpo"]}


def _disparo_out(d: dict[str, Any]) -> dict[str, Any]:
    return {**d, "template_id": d.get("modelo_id"), "agendado_para": d.get("agendado_para")}


def _dump(m: StrictHttpModel) -> dict[str, Any]:
    return m.model_dump(mode="json", exclude_unset=True)


# ── transport status ────────────────────────────────────────────────────────
def _conexao_out(c: Any) -> dict[str, Any]:
    return {
        "id": str(c.id), "label": c.label, "transporte": c.transporte,
        "cloud_phone_number_id": c.cloud_phone_number_id, "cloud_waba_id": c.cloud_waba_id,
        "cloud_configurada": julia_transporte.cloud_configurada(c),
    }


@router.get("/cloud/status")
def cloud_status(
    auth: tuple = Depends(get_current_user_org), store: WhatsAppConnectionStore = Depends(get_connection_store),
) -> dict[str, Any]:
    org_id = coerce_org_uuid(auth[2])
    conexoes = []
    for c in store.list_connections(org_id=org_id):
        # the token never rides a list response: configured = cloud + ids + a stored token
        full = store.get_connection(connection_id=c.id, org_id=org_id, decrypt=True)
        conexoes.append({**_conexao_out(full), "label": c.label})
    cloud = any(c["cloud_configurada"] for c in conexoes)
    return {"data": {"cloud_configurada": cloud, "aguardando_verificacao_meta": not cloud, "conexoes": conexoes}}


class ConexaoTransporteUpdate(StrictHttpModel):
    transporte: Optional[Literal["waha", "cloud"]] = None
    cloud_phone_number_id: Optional[str] = Field(default=None, max_length=64)
    cloud_waba_id: Optional[str] = Field(default=None, max_length=64)
    access_token: Optional[str] = Field(default=None, min_length=1, max_length=2048)


@router.put("/cloud/conexoes/{connection_id}")
def put_conexao_transporte(
    connection_id: UUID, body: ConexaoTransporteUpdate, request: Request, auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
) -> dict[str, Any]:
    org_id = _admin(auth, request, "julia cloud conexao")
    campos = {k: v for k, v in _dump(body).items() if k in ("transporte", "cloud_phone_number_id", "cloud_waba_id")}
    if body.transporte == julia_transporte.TRANSPORTE_CLOUD and body.access_token is None:
        atual = store.get_connection(connection_id=connection_id, org_id=org_id)
        if atual is not None and atual.transporte != julia_transporte.TRANSPORTE_CLOUD:
            raise AppException(
                "access_token_obrigatorio",
                "Ao mudar para a API oficial, informe o token de acesso da Meta (ele substitui a chave do WAHA).",
                status_code=422,
            )
    record = store.update_transporte(connection_id=connection_id, org_id=org_id, patch=campos, access_token=body.access_token)
    if record is None:
        raise AppException("conexao_nao_encontrada", "Conexão não encontrada.", status_code=404)
    return {"data": _conexao_out(store.get_connection(connection_id=connection_id, org_id=org_id, decrypt=True))}


class PerfilAplicar(StrictHttpModel):
    connection_id: Optional[UUID] = None


@router.post("/cloud/perfil/aplicar")
async def aplicar_perfil(
    body: PerfilAplicar, request: Request, auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store), db: Any = Depends(get_cloud_db),
    nome_agente: Optional[str] = Depends(get_nome_agente),
    fabrica: Callable[[Any], julia_transporte.Transporte] = Depends(get_transporte_factory),
) -> dict[str, Any]:
    """Push the saved `perfil_whatsapp` section to the WhatsApp Business profile. Cloud only; the display name
    is the agent's status name (per-org persona), not a literal."""
    org_id = _admin(auth, request, "julia cloud perfil")
    conexao = _conexao(store, org_id, body.connection_id)
    julia_disparos_service.exigir_cloud(conexao)
    secoes = (await anyio.to_thread.run_sync(lambda: julia_conhecimento_service.ler_secoes(db, org_id, nome_agente)))
    perfil = secoes["perfil_whatsapp"]["dados"]
    nome = nome_agente or perfil.get("nome_exibicao") or julia_conhecimento_service.PERSONA_NOME
    try:
        await fabrica(conexao).atualizar_perfil({
            "nome_exibicao": nome, "about": perfil.get("sobre"), "description": perfil.get("descricao"),
            "address": perfil.get("endereco"), "email": perfil.get("email"),
            "websites": [perfil["site"]] if perfil.get("site") else [],
        })
    except julia_transporte.OperacaoRequerApiOficial as exc:
        raise julia_transporte.transporte_indisponivel() from exc
    return {"data": {"aplicado": True, "nome_exibicao": nome}}


# ── modelos ─────────────────────────────────────────────────────────────────
class ModeloCreate(StrictHttpModel):
    nome: str = Field(min_length=1, max_length=julia_modelos_service.NOME_MAX)
    categoria: str
    conteudo: str = Field(min_length=1, max_length=julia_modelos_service.CORPO_MAX)


class ModeloPatch(StrictHttpModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=julia_modelos_service.NOME_MAX)
    categoria: Optional[str] = None
    conteudo: Optional[str] = Field(default=None, min_length=1, max_length=julia_modelos_service.CORPO_MAX)


class ModeloPreview(StrictHttpModel):
    corpo: str = Field(min_length=1, max_length=julia_modelos_service.CORPO_MAX)
    valores: Optional[dict[str, str]] = None


@router.get("/modelos")
def list_modelos(
    status_: Optional[str] = Query(default=None, alias="status"), categoria: Optional[str] = None,
    auth: tuple = Depends(get_current_user_org), db: Any = Depends(get_cloud_db),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
) -> dict[str, Any]:
    org_id = coerce_org_uuid(auth[2])
    rows = julia_modelos_service.listar(db, org_id, status=status_, categoria=categoria)
    return {"data": [_modelo_out(m) for m in rows], "meta": _meta(store, org_id, catalogo=julia_modelos_service.catalogo())}


@router.post("/modelos", status_code=status.HTTP_201_CREATED)
def create_modelo(
    body: ModeloCreate, request: Request, auth: tuple = Depends(get_current_user_org), db: Any = Depends(get_cloud_db),
) -> dict[str, Any]:
    org_id = _admin(auth, request, "julia modelos")
    return {"data": _modelo_out(julia_modelos_service.criar(db, org_id, nome=body.nome, categoria=body.categoria, corpo=body.conteudo, user_id=_user_id(auth)))}


@router.post("/modelos/preview")
def preview_modelo(body: ModeloPreview, auth: tuple = Depends(get_current_user_org)) -> dict[str, Any]:
    return {"data": julia_modelos_service.preview(body.corpo, body.valores)}


@router.get("/modelos/{modelo_id}")
def get_modelo(modelo_id: UUID, auth: tuple = Depends(get_current_user_org), db: Any = Depends(get_cloud_db)) -> dict[str, Any]:
    return {"data": _modelo_out(julia_modelos_service.obter(db, coerce_org_uuid(auth[2]), modelo_id))}


@router.patch("/modelos/{modelo_id}")
def patch_modelo(
    modelo_id: UUID, body: ModeloPatch, request: Request, auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_cloud_db),
) -> dict[str, Any]:
    org_id = _admin(auth, request, "julia modelos")
    patch = _dump(body)
    if "conteudo" in patch:
        patch["corpo"] = patch.pop("conteudo")
    return {"data": _modelo_out(julia_modelos_service.atualizar(db, org_id, modelo_id, patch))}


@router.delete("/modelos/{modelo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_modelo(
    modelo_id: UUID, request: Request, auth: tuple = Depends(get_current_user_org), db: Any = Depends(get_cloud_db),
) -> Response:
    julia_modelos_service.apagar(db, _admin(auth, request, "julia modelos"), modelo_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/modelos/{modelo_id}/enviar")
async def enviar_modelo_para_aprovacao(
    modelo_id: UUID, request: Request, auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store), db: Any = Depends(get_cloud_db),
    fabrica: Callable[[Any], julia_transporte.Transporte] = Depends(get_transporte_factory),
) -> dict[str, Any]:
    org_id = _admin(auth, request, "julia modelos")
    (await anyio.to_thread.run_sync(lambda: julia_modelos_service.obter(db, org_id, modelo_id)))  # 404 before the transport gate
    conexao = _conexao(store, org_id, None)
    julia_disparos_service.exigir_cloud(conexao)
    return {"data": _modelo_out(await julia_modelos_service.enviar_para_aprovacao(db, org_id, modelo_id, transporte=fabrica(conexao)))}


# ── disparos ────────────────────────────────────────────────────────────────
class DisparoCreate(StrictHttpModel):
    nome: str = Field(min_length=1, max_length=80)
    tipo: str
    segmento: str
    template_id: UUID
    agendado_para: Optional[datetime] = None
    connection_id: Optional[UUID] = None


class DisparoPatch(StrictHttpModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=80)
    segmento: Optional[str] = None
    template_id: Optional[UUID] = None
    connection_id: Optional[UUID] = None


class DisparoAgendar(StrictHttpModel):
    quando: datetime


class PrimeiroContato(StrictHttpModel):
    telefone: str = Field(min_length=8, max_length=24)
    nome: Optional[str] = Field(default=None, max_length=120)
    abordagem: Literal["comercial", "neutra"]
    connection_id: Optional[UUID] = None


@router.get("/disparos")
def list_disparos(
    aba: str = "todos", auth: tuple = Depends(get_current_user_org), db: Any = Depends(get_cloud_db),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
) -> dict[str, Any]:
    org_id = coerce_org_uuid(auth[2])
    rows = julia_disparos_service.listar(db, org_id, aba=aba)
    return {"data": [_disparo_out(d) for d in rows], "meta": _meta(store, org_id, catalogo=julia_disparos_service.catalogo())}


@router.get("/disparos/segmentos")
def list_segmentos(auth: tuple = Depends(get_current_user_org)) -> dict[str, Any]:
    return {"data": julia_disparos_service.lista_segmentos()}


@router.post("/disparos", status_code=status.HTTP_201_CREATED)
def create_disparo(
    body: DisparoCreate, request: Request, auth: tuple = Depends(get_current_user_org), db: Any = Depends(get_cloud_db),
) -> dict[str, Any]:
    org_id = _admin(auth, request, "julia disparos")
    criado = julia_disparos_service.criar(
        db, org_id, nome=body.nome, tipo=body.tipo, segmento=body.segmento, modelo_id=body.template_id,
        connection_id=body.connection_id, user_id=_user_id(auth),
    )
    if body.agendado_para is not None:
        try:
            criado = julia_disparos_service.agendar(db, org_id, criado["id"], body.agendado_para)
        except AppException:
            julia_disparos_service.apagar(db, org_id, criado["id"])  # a refused schedule must not leave a stray draft
            raise
    return {"data": _disparo_out(criado)}


@router.post("/disparos/primeiro-contato")
async def primeiro_contato(
    body: PrimeiroContato, request: Request, auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store), db: Any = Depends(get_cloud_db),
    nome_agente: Optional[str] = Depends(get_nome_agente),
    fabrica: Callable[[Any], julia_transporte.Transporte] = Depends(get_transporte_factory),
    agents_factory: Any = Depends(get_agents_client_factory),
) -> dict[str, Any]:
    """Meta lead-form first contact (template "Abordagem comercial|neutra"). Cloud only: 409 otherwise. A phone that is
    already a SW lead is checked against agents' opt-out (`motivo` `lead_opt_out`); an unknown phone has no consent record."""
    org_id = _admin(auth, request, "julia primeiro contato")
    conexao = _conexao(store, org_id, body.connection_id)
    julia_disparos_service.exigir_cloud(conexao)
    telefone = normalize_phone(body.telefone)
    contato = (await anyio.to_thread.run_sync(lambda: julia_contatos_service.buscar_contato(db, org_id, conexao.id, chat_id_for_phone(telefone)))) if telefone else None
    resultado = await julia_disparos_service.primeiro_contato_meta(
        db, org_id, connection=conexao, transporte=fabrica(conexao), telefone=body.telefone, nome=body.nome,
        abordagem=body.abordagem, contexto=_contexto_envio(db, org_id, nome_agente),
        contato_id=contato["id"] if contato else None, agents=agents_factory(org_id),
    )
    return {"data": resultado}


@router.get("/disparos/{disparo_id}")
def get_disparo(disparo_id: UUID, auth: tuple = Depends(get_current_user_org), db: Any = Depends(get_cloud_db)) -> dict[str, Any]:
    return {"data": _disparo_out(julia_disparos_service.detalhe(db, coerce_org_uuid(auth[2]), disparo_id))}


@router.get("/disparos/{disparo_id}/alvos")
def get_alvos(disparo_id: UUID, auth: tuple = Depends(get_current_user_org), db: Any = Depends(get_cloud_db)) -> dict[str, Any]:
    return {"data": julia_disparos_service.alvos(db, coerce_org_uuid(auth[2]), disparo_id)}


@router.get("/disparos/{disparo_id}/previa")
def get_previa(disparo_id: UUID, auth: tuple = Depends(get_current_user_org), db: Any = Depends(get_cloud_db)) -> dict[str, Any]:
    return {"data": julia_disparos_service.previa(db, coerce_org_uuid(auth[2]), disparo_id)}


@router.patch("/disparos/{disparo_id}")
def patch_disparo(
    disparo_id: UUID, body: DisparoPatch, request: Request, auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_cloud_db),
) -> dict[str, Any]:
    org_id = _admin(auth, request, "julia disparos")
    patch = _dump(body)
    if "template_id" in patch:
        patch["modelo_id"] = patch.pop("template_id")
    return {"data": _disparo_out(julia_disparos_service.atualizar(db, org_id, disparo_id, patch))}


@router.delete("/disparos/{disparo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_disparo(
    disparo_id: UUID, request: Request, auth: tuple = Depends(get_current_user_org), db: Any = Depends(get_cloud_db),
) -> Response:
    julia_disparos_service.apagar(db, _admin(auth, request, "julia disparos"), disparo_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/disparos/{disparo_id}/agendar")
def agendar_disparo(
    disparo_id: UUID, body: DisparoAgendar, request: Request, auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_cloud_db),
) -> dict[str, Any]:
    org_id = _admin(auth, request, "julia disparos")
    return {"data": _disparo_out(julia_disparos_service.agendar(db, org_id, disparo_id, body.quando))}


@router.post("/disparos/{disparo_id}/cancelar")
def cancelar_disparo(
    disparo_id: UUID, request: Request, auth: tuple = Depends(get_current_user_org), db: Any = Depends(get_cloud_db),
) -> dict[str, Any]:
    return {"data": _disparo_out(julia_disparos_service.cancelar(db, _admin(auth, request, "julia disparos"), disparo_id))}


@router.post("/disparos/{disparo_id}/enviar")
async def disparar_disparo(
    disparo_id: UUID, request: Request, auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store), db: Any = Depends(get_cloud_db),
    nome_agente: Optional[str] = Depends(get_nome_agente),
    fabrica: Callable[[Any], julia_transporte.Transporte] = Depends(get_transporte_factory),
    agents_factory: Any = Depends(get_agents_client_factory),
) -> dict[str, Any]:
    org_id = _admin(auth, request, "julia disparos")
    disparo = (await anyio.to_thread.run_sync(lambda: julia_disparos_service.obter(db, org_id, disparo_id)))  # 404 before the transport gate
    conexao = _conexao(store, org_id, UUID(disparo["connection_id"]) if disparo.get("connection_id") else None)
    julia_disparos_service.exigir_cloud(conexao)
    return {"data": _disparo_out(await julia_disparos_service.disparar(
        db, org_id, disparo_id, connection=conexao, transporte=fabrica(conexao),
        contexto=_contexto_envio(db, org_id, nome_agente), agents=agents_factory(org_id),
    ))}


# ── proprietarios (Atualizacao de imoveis) ──────────────────────────────────
class ProprietarioCreate(StrictHttpModel):
    telefone: str = Field(min_length=8, max_length=24)
    imovel_codigo: str = Field(min_length=1, max_length=60)
    nome: Optional[str] = Field(default=None, max_length=120)


class ProprietarioConfirmar(StrictHttpModel):
    status: Optional[str] = Field(default=None, min_length=1, max_length=40)
    preco: Optional[float] = Field(default=None, gt=0)
    preco_tipo: Literal["venda", "locacao"] = "venda"


@router.get("/proprietarios")
def list_proprietarios(
    status_: Optional[str] = Query(default=None, alias="status"), q: Optional[str] = None,
    auth: tuple = Depends(get_current_user_org), db: Any = Depends(get_cloud_db),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
) -> dict[str, Any]:
    org_id = coerce_org_uuid(auth[2])
    return {"data": julia_proprietarios_service.listar(db, org_id, busca=q, status=status_), "meta": _meta(store, org_id)}


@router.post("/proprietarios", status_code=status.HTTP_201_CREATED)
def create_proprietario(
    body: ProprietarioCreate, request: Request, auth: tuple = Depends(get_current_user_org), db: Any = Depends(get_cloud_db),
) -> dict[str, Any]:
    org_id = _admin(auth, request, "julia proprietarios")
    return {"data": julia_proprietarios_service.criar(db, org_id, telefone=body.telefone, imovel_codigo=body.imovel_codigo, nome=body.nome)}


@router.post("/proprietarios/{pid}/confirmar")
def confirmar_proprietario(
    pid: UUID, body: ProprietarioConfirmar, request: Request, auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_cloud_db), imoveis: Any = Depends(get_imoveis_service),
) -> dict[str, Any]:
    org_id = _admin(auth, request, "julia proprietarios")
    return {"data": julia_proprietarios_service.confirmar(
        db, org_id, pid, imoveis, status=body.status, preco=body.preco, preco_tipo=body.preco_tipo,
    )}


class ProprietarioSolicitar(StrictHttpModel):
    template_id: Optional[UUID] = None


@router.post("/proprietarios/{pid}/solicitar")
async def solicitar_proprietario(
    pid: UUID, body: Optional[ProprietarioSolicitar] = None, request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store), db: Any = Depends(get_cloud_db),
    nome_agente: Optional[str] = Depends(get_nome_agente),
    fabrica: Callable[[Any], julia_transporte.Transporte] = Depends(get_transporte_factory),
) -> dict[str, Any]:
    """Ask this owner to confirm status/price now (an approved Cloud template). 409 unless Cloud."""
    org_id = _admin(auth, request, "julia proprietarios")
    p = (await anyio.to_thread.run_sync(lambda: julia_proprietarios_service.obter(db, org_id, pid)))  # 404 before the transport gate
    conexao = _conexao(store, org_id, None)
    julia_disparos_service.exigir_cloud(conexao)
    return {"data": await julia_disparos_service.solicitar_proprietario(
        db, org_id, p, connection=conexao, transporte=fabrica(conexao),
        modelo_id=body.template_id if body else None, contexto=_contexto_envio(db, org_id, nome_agente),
    )}


@router.post("/proprietarios/{pid}/opt-out")
def opt_out_proprietario(
    pid: UUID, request: Request, auth: tuple = Depends(get_current_user_org), db: Any = Depends(get_cloud_db),
) -> dict[str, Any]:
    org_id = _admin(auth, request, "julia proprietarios")
    p = julia_proprietarios_service.obter(db, org_id, pid)
    julia_proprietarios_service.registrar_opt_out(db, org_id, p["telefone"])
    return {"data": julia_proprietarios_service.obter(db, org_id, pid)}


@router.delete("/proprietarios/{pid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_proprietario(
    pid: UUID, request: Request, auth: tuple = Depends(get_current_user_org), db: Any = Depends(get_cloud_db),
) -> Response:
    julia_proprietarios_service.apagar(db, _admin(auth, request, "julia proprietarios"), pid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = [
    "get_cloud_db", "get_imoveis_service", "get_transporte_factory", "router",
]
