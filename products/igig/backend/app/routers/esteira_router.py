"""Esteira de Produção Criativa — Módulo 4.

Three surfaces in one router, because they are one workflow:

  AUTHED (the agency's team)
    GET/POST/PATCH/DELETE /api/esteira/stages …     stage editor (seed router;
                                                    writes = org admins)
    GET   /api/esteira/board?cliente_id=            the kanban (seed columns)
    POST  /api/esteira/tarefas                      create a tarefa (entry stage)
    DELETE /api/esteira/tarefas/{id}                delete a tarefa (204)
    POST  /api/esteira/tarefas/{id}/mover-etapa     drag: +1 forward, back w/ motivo
    GET   /api/esteira/tarefas/{id}/apontamentos    timesheet segments
    POST  /api/esteira/tarefas/{id}/timer/iniciar   play  (the CALLER's timer)
    POST  /api/esteira/tarefas/{id}/timer/encerrar  pause (the CALLER's timer)
    POST  /api/esteira/tarefas/{id}/link-aprovacao  mint the client link AND move
                                                    the tarefa into approval

  PUBLIC (the agency's CLIENT — no noc account, token IS the auth)
    GET   /api/esteira/aprovar/{token}              what the client sees
    POST  /api/esteira/aprovar/{token}              [Aprovar] / [Solicitar Ajuste]

Board rules live in `app/services/esteira_quadro.py` on the seed pipeline; this
router only maps HTTP to them. The legacy `/quadro` + `/tarefas/{id}/mover`
pair is GONE, not aliased: it validated against a hardcoded 8-value tuple, and
since migration 017 the stages are the org's own editable rows.

The public pair runs on the service-role providers (`get_repositorios_admin`,
`get_admin_db`) because an anonymous caller has no org for RLS to scope by —
the same split Orbity uses. `org_id` comes out of the token and is passed
explicitly on every call, so even that client cannot read across tenants. It
is rate-limited, returns a NARROW projection, and never distinguishes
"unknown" from "expired" from "already decided" (all the same 404).
"""
# NOTE: deliberately NO `from __future__ import annotations` here.
# The public endpoints are wrapped by `@limiter.limit(...)`, and with
# postponed annotations FastAPI cannot resolve the body model through the
# wrapper — it degrades `payload: DecisaoIn` into
# `Annotated[ForwardRef('DecisaoIn'), Query(...)]` and the whole app fails to
# build at import. Eager annotations keep the body a body.
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from noctusai_lib.domain.pipeline import pipeline_stages_router
from noctusai_lib.integrations.persistence import RecordNotFound
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.responses import success_response

from app.config import settings
from app.automacoes_deps import get_portas_automacao_esteira
from app.dependencies import coerce_org_uuid, get_current_user_org
from app.pipelines import (
    PAPEL_APROVACAO_CLIENTE,
    PIPELINE_ESTEIRA,
    exigir_admin_da_org,
    get_admin_db,
    get_core_db,
    get_db,
    get_pipeline_auth,
    pipeline_context,
)
from app.rate_limit import limiter
from app.repositories import Repositorios
from app.schemas.esteira import (
    ApontamentoOut,
    AprovacaoPublicaOut,
    DecisaoIn,
    DecisaoOut,
    LinkAprovacaoOut,
    PecaPublica,
    TarefaOut,
)
from app.schemas.pipeline import MoverCardIn, TarefaCreate
from app.services import automacoes, esteira_quadro
from app.services.notificacoes import notificar
from app.services.regras import RegraViolada, http_de
from app.storage import get_storage
from app.store import get_repositorios, get_repositorios_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/esteira", tags=["esteira"])

#: The esteira's stage editor — the seed router, mounted as-is. Writes need an
#: org admin; system-role stages (`aprovacao_cliente`, `agendado`) are
#: renamable/reorderable but the seed refuses to delete or deactivate them.
stages_router = pipeline_stages_router(
    PIPELINE_ESTEIRA,
    auth_dependency=get_pipeline_auth,
    resolve_context=lambda pa: pipeline_context(pa, PIPELINE_ESTEIRA),
    success_response=success_response,
    prefix="/api/esteira/stages",
    tags=["esteira-etapas"],
    require_stage_admin=exigir_admin_da_org,
)

#: One message for every public-lookup failure. Distinct messages would let a
#: caller probe which tokens exist.
_LINK_INVALIDO = "Link inválido ou expirado"


def _org(auth: tuple) -> str:
    _user, _token, raw_org = auth
    return str(coerce_org_uuid(raw_org))


def _usuario(auth: tuple) -> str:
    """The AUTHENTICATED caller — the only identity a timer may run under."""
    return str(auth[0].id)


# ── AUTHED — the agency's team ──────────────────────────────────────
@router.get("/board")
async def obter_board(
    cliente_id: str | None = None,
    limite_por_etapa: int | None = None,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
) -> dict:
    """Every active stage as a column (empty ones included), `?cliente_id=` to
    show one cliente's esteira (roadmap R9)."""
    return success_response(
        esteira_quadro.quadro(
            db, _org(auth), cliente_id=cliente_id, limite_por_etapa=limite_por_etapa
        )
    )


@router.post("/tarefas", response_model=TarefaOut, status_code=status.HTTP_201_CREATED)
async def criar_tarefa(
    payload: TarefaCreate,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
) -> TarefaOut:
    """New tarefa at the first stage. The pauta must exist (404 otherwise —
    without the check the FK error would surface as an opaque 500)."""
    try:
        tarefa = esteira_quadro.criar_tarefa(
            db, _org(auth),
            pauta_id=payload.pauta_id,
            titulo=payload.titulo,
            responsavel_id=payload.responsavel_id,
            prazo=payload.prazo,
            user_id=_usuario(auth),
        )
    except RegraViolada as erro:
        raise http_de(erro) from erro
    return TarefaOut(**tarefa)


@router.delete("/tarefas/{tarefa_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_tarefa(
    tarefa_id: str,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
) -> Response:
    """Delete a tarefa of the caller's org. 404 when it is not theirs."""
    esteira_quadro.excluir_tarefa(db, _org(auth), tarefa_id=tarefa_id, user_id=_usuario(auth))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/tarefas/{tarefa_id}/mover-etapa")
async def mover_etapa(
    tarefa_id: str,
    payload: MoverCardIn,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
    portas: automacoes.PortasAutomacao = Depends(get_portas_automacao_esteira),
) -> dict:
    """Drag a card. 409 `etapa_invalida` (skip forward / inactive stage),
    422 `motivo_obrigatorio` (backwards without a reason). Backwards out of
    the approval stage counts a refação."""
    try:
        linha = esteira_quadro.mover_tarefa(
            db, _org(auth),
            tarefa_id=tarefa_id,
            para_etapa_id=payload.para_etapa_id,
            user_id=_usuario(auth),
            novo_indice=payload.novo_indice,
            motivo=payload.motivo,
        )
    except RegraViolada as erro:
        raise http_de(erro) from erro
    await automacoes.ao_entrar_etapa(portas, _org(auth), pipeline="esteira", card_id=tarefa_id, user_id=_usuario(auth))
    return success_response(linha)


@router.get("/tarefas/{tarefa_id}/apontamentos", response_model=list[ApontamentoOut])
async def listar_apontamentos(
    tarefa_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> list[ApontamentoOut]:
    return [ApontamentoOut(**a) for a in repos.apontamento.da_tarefa(_org(auth), tarefa_id)]


@router.post("/tarefas/{tarefa_id}/timer/iniciar", response_model=ApontamentoOut,
             status_code=status.HTTP_201_CREATED)
async def iniciar_timer(
    tarefa_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> ApontamentoOut:
    """Play — for the AUTHENTICATED caller. Auto-closes whatever else they had
    running.

    There is deliberately no body: the timer used to trust a payload
    `usuario_id`, so anyone could book hours onto a colleague (smoke finding
    3). A legacy client still sending one is simply ignored. The segment also
    records the caller's `profissional` (resolved by `profissional.usuario_id`)
    — the same record `tarefa.responsavel_id` points at (smoke finding 8).
    """
    org_id = _org(auth)
    usuario_id = _usuario(auth)
    try:
        repos.tarefa.buscar(org_id, tarefa_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    profissional = repos.profissional.do_usuario(org_id, usuario_id)
    if profissional is None:
        logger.warning(
            "timer sem profissional vinculado org=%s usuario=%s — horas sem custo/hora",
            org_id, usuario_id,
        )
    return ApontamentoOut(**repos.apontamento.iniciar(
        org_id, tarefa_id, usuario_id,
        profissional_id=str(profissional["id"]) if profissional else None,
    ))


@router.post("/tarefas/{tarefa_id}/timer/encerrar", response_model=ApontamentoOut)
async def encerrar_timer(
    tarefa_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> ApontamentoOut:
    """Pause the CALLER's running segment. 404 when they have none here."""
    org_id = _org(auth)
    aberto = repos.apontamento.aberto_do_usuario(org_id, _usuario(auth))
    if aberto is None or str(aberto.get("tarefa_id")) != tarefa_id:
        raise HTTPException(status_code=404, detail="Nenhum apontamento aberto nesta tarefa")
    return ApontamentoOut(**repos.apontamento.encerrar(org_id, str(aberto["id"])))


@router.post("/tarefas/{tarefa_id}/link-aprovacao", response_model=LinkAprovacaoOut,
             status_code=status.HTTP_201_CREATED)
async def emitir_link_aprovacao(
    tarefa_id: str,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
    repos: Repositorios = Depends(get_repositorios),
) -> LinkAprovacaoOut:
    """Mint the white-label link the agency sends to its client.

    Minting MEANS "this is with the client now": the tarefa moves into the
    `aprovacao_cliente` stage in the same request (smoke finding 4 — the link
    used to leave the card wherever it was, and the portal then acted on a
    tarefa nobody had sent for approval). 409 `etapa_invalida` when the tarefa
    is already past approval.
    """
    org_id = _org(auth)
    try:
        esteira_quadro.levar_para_aprovacao(
            db, org_id, tarefa_id=tarefa_id, user_id=_usuario(auth)
        )
    except RegraViolada as erro:
        raise http_de(erro) from erro
    link = repos.aprovacao.emitir(org_id, tarefa_id, emitido_por=_usuario(auth))
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
    storage: StorageBackend = Depends(get_storage),
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
            url = await storage.signed_url(
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
        aguardando_aprovacao=_aguardando_aprovacao(repos, org_id, tarefa),
    )


def _aguardando_aprovacao(repos: Repositorios, org_id: str, tarefa: dict) -> bool:
    """Whether the portal may still decide — the tarefa sits in the approval stage.

    A tarefa whose stage row is missing is a data fault: logged, and shown as
    not awaiting (the POST would refuse it anyway) rather than 500-ing a page
    the client can still read.
    """
    try:
        return repos.etapa.papel_de(org_id, str(tarefa["etapa_id"])) == PAPEL_APROVACAO_CLIENTE
    except RecordNotFound:
        logger.error("tarefa %s aponta para etapa inexistente %s",
                     tarefa.get("id"), tarefa.get("etapa_id"))
        return False


@router.post("/aprovar/{token}", response_model=DecisaoOut)
@limiter.limit(settings.webhook_rate_limit)
async def decidir_aprovacao_publica(
    request: Request,
    token: str,
    payload: DecisaoIn,
    repos: Repositorios = Depends(get_repositorios_admin),
    db: Any = Depends(get_admin_db),
    core: Any = Depends(get_core_db),
) -> DecisaoOut:
    """[Aprovar Conteúdo] or [Solicitar Ajuste].

    Single-decision: a spent link is a 404 like any other unusable link, so a
    client cannot flip a decision after the fact — or discover that a token
    was once valid. Valid only while the tarefa is IN the approval stage (409
    `fora_de_aprovacao` once the agency pulled it back). The agency is told
    through an in-app notification — the decision stands even if that write
    fails, because it is the client's action and it already happened.
    """
    aprovacao = _resolver_link(repos, token)
    if repos.aprovacao.decidida(aprovacao):
        raise HTTPException(status_code=404, detail=_LINK_INVALIDO)

    org_id = str(aprovacao["org_id"])
    tarefa_id = str(aprovacao["tarefa_id"])
    try:
        esteira_quadro.decidir_aprovacao(
            db, org_id, tarefa_id=tarefa_id, decisao=payload.decisao,
            observacao=payload.observacao,
        )
    except RegraViolada as erro:
        raise http_de(erro) from erro

    repos.aprovacao.registrar_decisao(
        org_id, str(aprovacao["id"]), payload.decisao, payload.observacao
    )
    logger.info("aprovação decidida org=%s tarefa=%s decisao=%s",
                org_id, tarefa_id, payload.decisao)
    _avisar_agencia(repos, core, org_id, aprovacao, payload)
    return DecisaoOut(ok=True, decisao=payload.decisao)


def _avisar_agencia(
    repos: Repositorios, core: Any, org_id: str, aprovacao: dict, payload: DecisaoIn
) -> None:
    """Notify who sent the link + the tarefa's responsável (smoke finding 4:
    the portal said "agência notificada" and nobody ever was)."""
    tarefa = repos.tarefa.buscar(org_id, str(aprovacao["tarefa_id"]))
    destinatarios = [aprovacao.get("emitido_por")]
    if tarefa.get("responsavel_id"):
        try:
            destinatarios.append(
                repos.profissional.buscar(org_id, str(tarefa["responsavel_id"])).get("usuario_id")
            )
        except RecordNotFound:
            logger.warning("tarefa %s aponta para responsável ausente", tarefa.get("id"))
    aprovado = payload.decisao == "aprovado"
    titulo = (
        f"Cliente aprovou: {tarefa.get('titulo')}" if aprovado
        else f"Cliente pediu ajuste: {tarefa.get('titulo')}"
    )
    try:
        notificar(
            core,
            org_id=org_id,
            user_ids=destinatarios,
            tipo="igig_aprovacao_cliente",
            titulo=titulo,
            mensagem=payload.observacao or ("Conteúdo aprovado." if aprovado else "Ajuste solicitado."),
            metadata={
                "tarefa_id": str(tarefa.get("id")),
                "decisao": payload.decisao,
                "link": "/esteira",
            },
        )
    except Exception:  # noqa: BLE001 — the client's decision already stands
        logger.exception("falha ao notificar a agência org=%s tarefa=%s", org_id, tarefa.get("id"))
