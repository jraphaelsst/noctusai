"""Esteira de Produção Criativa — Módulo 4.

Three surfaces in one router, because they are one workflow:

  AUTHED (the agency's team)
    GET   /api/esteira/quadro                       the 8-column kanban
    POST  /api/esteira/tarefas                      create a tarefa
    POST  /api/esteira/tarefas/{id}/mover           advance the etapa
    GET   /api/esteira/tarefas/{id}/apontamentos    timesheet segments
    POST  /api/esteira/tarefas/{id}/timer/iniciar   play
    POST  /api/esteira/tarefas/{id}/timer/encerrar  pause
    POST  /api/esteira/tarefas/{id}/link-aprovacao  mint the client link

  PUBLIC (the agency's CLIENT — no noc account, token IS the auth)
    GET   /api/esteira/aprovar/{token}              what the client sees
    POST  /api/esteira/aprovar/{token}              [Aprovar] / [Solicitar Ajuste]

The public pair runs on `get_repositorios_admin` (service-role, RLS bypassed)
because an anonymous caller has no org for RLS to scope by — the same split
Orbity uses. `org_id` is still passed explicitly on every repository call, so
even that client cannot read across tenants.

The public pair is unauthenticated by design and therefore:
  * rate-limited (public surface, DDOS guard),
  * returns a NARROW projection that leaks none of the agency's internals,
  * never distinguishes "unknown token" from "expired token" from "already
    decided" in a way that turns the endpoint into an oracle — all three are
    404 with the same body.

Mirrors the shape Orbity already ships (`/aprovar/:token`), so the eventual
IgIg→Orbity merge does not have to reconcile two different portals.
"""
# NOTE: deliberately NO `from __future__ import annotations` here.
# The public endpoints are wrapped by `@limiter.limit(...)`, and with
# postponed annotations FastAPI cannot resolve the body model through the
# wrapper — it degrades `payload: DecisaoIn` into
# `Annotated[ForwardRef('DecisaoIn'), Query(...)]` and the whole app fails to
# build at import. Eager annotations keep the body a body.
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from noctusai_lib.integrations.persistence import RecordNotFound

from app.config import settings
from app.dependencies import coerce_org_uuid, get_current_user_org
from app.rate_limit import limiter
from app.repositories import ETAPAS, Repositorios
from app.schemas.esteira import (
    ApontamentoOut,
    AprovacaoPublicaOut,
    PecaPublica,
    DecisaoIn,
    DecisaoOut,
    IniciarTimer,
    LinkAprovacaoOut,
    MoverTarefa,
    QuadroResponse,
    TarefaCreate,
    TarefaOut,
)
from app.storage import get_storage
from app.store import get_repositorios, get_repositorios_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/esteira", tags=["esteira"])

#: One message for every public-lookup failure. Distinct messages would let a
#: caller probe which tokens exist.
_LINK_INVALIDO = "Link inválido ou expirado"


# ── AUTHED — the agency's team ──────────────────────────────────────
@router.get("/quadro", response_model=QuadroResponse)
async def obter_quadro(
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> QuadroResponse:
    """The full kanban. All 8 columns always present, empty ones included."""
    _user, _token, raw_org = auth
    org_id = str(coerce_org_uuid(raw_org))
    quadro = repos.tarefa.quadro(org_id)
    return QuadroResponse(
        etapas=list(ETAPAS),
        colunas={
            etapa: [TarefaOut(**t) for t in tarefas] for etapa, tarefas in quadro.items()
        },
    )


@router.post("/tarefas", response_model=TarefaOut, status_code=status.HTTP_201_CREATED)
async def criar_tarefa(
    payload: TarefaCreate,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> TarefaOut:
    _user, _token, raw_org = auth
    org_id = str(coerce_org_uuid(raw_org))
    try:
        repos.pauta.buscar(org_id, payload.pauta_id)
    except RecordNotFound:
        # Checked explicitly: without it the FK error surfaces as an opaque
        # 500 from the store instead of naming the actual problem.
        raise HTTPException(status_code=404, detail="Pauta não encontrada")
    return TarefaOut(**repos.tarefa.criar(org_id, payload.model_dump(exclude_none=True)))


@router.post("/tarefas/{tarefa_id}/mover", response_model=TarefaOut)
async def mover_tarefa(
    tarefa_id: str,
    payload: MoverTarefa,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> TarefaOut:
    _user, _token, raw_org = auth
    org_id = str(coerce_org_uuid(raw_org))
    try:
        return TarefaOut(**repos.tarefa.mover(org_id, tarefa_id, payload.etapa))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")


@router.get("/tarefas/{tarefa_id}/apontamentos", response_model=list[ApontamentoOut])
async def listar_apontamentos(
    tarefa_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> list[ApontamentoOut]:
    _user, _token, raw_org = auth
    org_id = str(coerce_org_uuid(raw_org))
    return [ApontamentoOut(**a) for a in repos.apontamento.da_tarefa(org_id, tarefa_id)]


@router.post("/tarefas/{tarefa_id}/timer/iniciar", response_model=ApontamentoOut,
             status_code=status.HTTP_201_CREATED)
async def iniciar_timer(
    tarefa_id: str,
    payload: IniciarTimer,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> ApontamentoOut:
    """Play. Auto-closes whatever else this user had running."""
    _user, _token, raw_org = auth
    org_id = str(coerce_org_uuid(raw_org))
    try:
        repos.tarefa.buscar(org_id, tarefa_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return ApontamentoOut(**repos.apontamento.iniciar(org_id, tarefa_id, payload.usuario_id))


@router.post("/tarefas/{tarefa_id}/timer/encerrar", response_model=ApontamentoOut)
async def encerrar_timer(
    tarefa_id: str,
    payload: IniciarTimer,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> ApontamentoOut:
    """Pause. 404 when this user has no running segment."""
    _user, _token, raw_org = auth
    org_id = str(coerce_org_uuid(raw_org))
    aberto = repos.apontamento.aberto_do_usuario(org_id, payload.usuario_id)
    if aberto is None or str(aberto.get("tarefa_id")) != tarefa_id:
        raise HTTPException(status_code=404, detail="Nenhum apontamento aberto nesta tarefa")
    return ApontamentoOut(**repos.apontamento.encerrar(org_id, str(aberto["id"])))


@router.post("/tarefas/{tarefa_id}/link-aprovacao", response_model=LinkAprovacaoOut,
             status_code=status.HTTP_201_CREATED)
async def emitir_link_aprovacao(
    tarefa_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> LinkAprovacaoOut:
    """Mint the white-label link the agency sends to its client."""
    _user, _token, raw_org = auth
    org_id = str(coerce_org_uuid(raw_org))
    try:
        repos.tarefa.buscar(org_id, tarefa_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    link = repos.aprovacao.emitir(org_id, tarefa_id)
    logger.info("link de aprovação emitido org=%s tarefa=%s", org_id, tarefa_id)
    return LinkAprovacaoOut(**link)


# ── PUBLIC — the agency's client. Token IS the auth. ────────────────
def _resolver_link(repos: Repositorios, token: str) -> dict:
    """Resolve a usable link or raise the single opaque 404.

    Unknown, malformed, expired and already-decided all produce the SAME
    response so the endpoint cannot be used to enumerate tokens.
    """
    aprovacao = repos.aprovacao.por_token(token)
    if aprovacao is None or repos.aprovacao.expirada(aprovacao):
        raise HTTPException(status_code=404, detail=_LINK_INVALIDO)
    return aprovacao


@router.get("/aprovar/{token}", response_model=AprovacaoPublicaOut)
@limiter.limit(settings.webhook_rate_limit)
async def ver_aprovacao_publica(
    request: Request,
    token: str,
    repos: Repositorios = Depends(get_repositorios_admin),
) -> AprovacaoPublicaOut:
    """What the client sees. No auth; narrow projection."""
    aprovacao = _resolver_link(repos, token)
    org_id = str(aprovacao["org_id"])
    tarefa = repos.tarefa.buscar(org_id, str(aprovacao["tarefa_id"]))
    pauta = repos.pauta.buscar(org_id, str(tarefa["pauta_id"]))

    cliente_nome = None
    try:
        cliente_nome = repos.cliente.buscar(org_id, str(pauta["cliente_id"])).get("nome")
    except RecordNotFound:
        # The client's own name is cosmetic on this page; a deleted cliente
        # row must not take down an otherwise valid approval link.
        logger.warning("aprovação %s aponta para cliente ausente", aprovacao.get("id"))

    # Signed URLs so an anonymous client can fetch the asset without the
    # bucket being public. A failure here must NOT take down the approval
    # page — the copy alone is still reviewable.
    pecas: list[PecaPublica] = []
    for peca in repos.peca.da_pauta(org_id, str(pauta["id"])):
        try:
            url = await get_storage().signed_url(
                bucket=settings.igig_storage_bucket, key=str(peca["storage_key"])
            )
        except Exception:  # noqa: BLE001 — storage outage must not block approval
            logger.warning("peça sem URL assinada: %s", peca.get("storage_key"))
            url = None
        pecas.append(PecaPublica(url=url, mime_type=peca.get("mime_type")))

    return AprovacaoPublicaOut(
        pecas=pecas,
        titulo=str(tarefa["titulo"]),
        copy_texto=pauta.get("copy_texto"),
        direcao_video=pauta.get("direcao_video"),
        formato=pauta.get("formato"),
        cliente_nome=cliente_nome,
        ja_decidida=repos.aprovacao.decidida(aprovacao),
    )


@router.post("/aprovar/{token}", response_model=DecisaoOut)
@limiter.limit(settings.webhook_rate_limit)
async def decidir_aprovacao_publica(
    request: Request,
    token: str,
    payload: DecisaoIn,
    repos: Repositorios = Depends(get_repositorios_admin),
) -> DecisaoOut:
    """[Aprovar Conteúdo] or [Solicitar Ajuste].

    Single-decision: a spent link is a 404 like any other unusable link, so a
    client cannot flip a decision after the fact — or discover that a token
    was once valid.
    """
    aprovacao = _resolver_link(repos, token)
    if repos.aprovacao.decidida(aprovacao):
        raise HTTPException(status_code=404, detail=_LINK_INVALIDO)

    org_id = str(aprovacao["org_id"])
    tarefa_id = str(aprovacao["tarefa_id"])

    if payload.decisao == "aprovado":
        repos.tarefa.aprovar(org_id, tarefa_id)
    else:
        repos.tarefa.solicitar_ajuste(org_id, tarefa_id, payload.observacao)

    repos.aprovacao.registrar_decisao(
        org_id, str(aprovacao["id"]), payload.decisao, payload.observacao
    )
    logger.info("aprovação decidida org=%s tarefa=%s decisao=%s",
                org_id, tarefa_id, payload.decisao)
    return DecisaoOut(ok=True, decisao=payload.decisao)
