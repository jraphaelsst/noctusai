"""Julia agent surface (contract sections 5 and 11).

  GET   /api/public/julia/privacidade/{slug}   public, no auth, rate-limited      (slice P)
  GET   /api/julia/agente/aviso                org member                          (slice P)
  PUT   /api/julia/agente/aviso                core org role owner/admin           (slice P)

  GET   /api/julia/agente                      org member: connections, token, link health
  PUT   /api/julia/agente/conexoes/{id}        admin: the Julia switch (11.1 snapshot) + handoff target
  PUT   /api/julia/agente/token                admin: paste the org's agents channel token
  PATCH /api/whatsapp/connections/{id}/chats/{chat_id}/agente   admin: per-chat pause (calls AGENTS, mirrors its answer)
  GET   /api/whatsapp/connections/{id}/chats/{chat_id}/agente   member: the per-chat state as AGENTS reports it
  POST  /api/julia/agente/conexoes/{id}/chats/{chat_id}/apagar-dados   admin: deletion on request (M5)

# NOC-REMEDIATE[seed-promotion]: per-org public privacy notice -- promote to the seed as `org_privacy_notice` (router + table + default template) when the 2nd consumer (store/igig) needs it — 2026-10-14
"""
# No `from __future__ import annotations`: this module carries
# `@limiter.limit` (check_slowapi_with_pep563).
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import ProductTokenAdmin, make_product_token_admin, require_org_admin_for
from noctusai_lib.primitives.exceptions import AppException

from app.clients.agents import (
    AgentNotFound,
    AgentsClient,
    AgentsClientError,
    AgentsTokenInvalid,
    HttpAgentsClient,
    ParticipanteNotFound,
    TransicaoInvalida,
)
from app.services import julia_contatos_service, julia_thread_service
from app.services.julia_contexto_service import (
    TOOLS_TOKEN_ISSUER, TOOLS_TOKEN_LABEL, TOOLS_TOKEN_SCOPE,
)
from app.config import settings
from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_core_client,
    get_current_user_org,
    get_scoped_admin_client,
    get_settings,
)
from app.rate_limit import limiter
from app.routers.whatsapp_connections_router import (  # noqa: F401  (get_agents_client_factory: re-exported, same object)
    get_agents_client_factory,
    get_connection_store,
    get_waha_client_factory,
)
from app.services import api_keys_store
from app.services import julia_agente_service as julia
from app.services import julia_aviso_service as svc
from app.services.conversation_module import get_conversation_module
from app.services.credential_vault import EncryptionNotConfigured
from app.services.whatsapp_chat_store import WhatsAppChatStore
from app.services.whatsapp_connection_store import WhatsAppConnectionRecord, WhatsAppConnectionStore
from app.services.whatsapp_realtime import EVENT_CHAT_UPSERT, get_whatsapp_bus, publish_whatsapp_event

logger = logging.getLogger(__name__)

router = APIRouter(tags=["julia-agente"])


class _Secao(StrictHttpModel):
    n: str = Field(min_length=1, max_length=8)
    title: str = Field(min_length=1, max_length=200)
    blocks: list[dict[str, Any]]


class AvisoUpdate(StrictHttpModel):
    titulo: str = Field(min_length=1, max_length=200)
    empresa_nome: str = Field(min_length=1, max_length=200)
    contato_email: Optional[str] = Field(default=None, max_length=200)
    contato_whatsapp: Optional[str] = Field(default=None, max_length=40)
    secoes: list[_Secao] = Field(min_length=1, max_length=40)
    mensagem_inicial: str = Field(min_length=1, max_length=1000)


def _validar_blocos(secoes: list[_Secao]) -> None:
    for s in secoes:
        for b in s.blocks:
            ok = (
                (set(b) == {"p"} and isinstance(b["p"], str))
                or (set(b) == {"ul"} and isinstance(b["ul"], list)
                    and all(isinstance(i, str) for i in b["ul"]))
            )
            if not ok:
                raise AppException(
                    "secoes_invalidas",
                    "Cada bloco deve ser {p: texto} ou {ul: [textos]}.",
                    status_code=422,
                )


def _admin_row(auth: tuple) -> tuple[dict[str, Any], Any, Any]:
    user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_scoped_admin_client("social_wiring")
    row = svc.obter_ou_criar(client, get_core_client(), org_id)
    return row, client, (user, org_id)


def _saida_admin(row: dict[str, Any]) -> dict[str, Any]:
    return {**row, "incompleto": svc.incompleto(row)}


@router.get("/api/public/julia/privacidade/{slug}")
@limiter.limit(settings.webhook_rate_limit)
def get_aviso_publico(slug: str, request: Request) -> dict[str, Any]:
    """Public notice by slug. Returns ONLY the notice fields (never org ids,
    users or settings)."""
    row = svc.buscar_por_slug(get_scoped_admin_client("social_wiring"), slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Aviso não encontrado")
    return {"data": svc.somente_publico(row)}


@router.get("/api/julia/agente/aviso")
def get_aviso(auth: tuple = Depends(get_current_user_org)) -> dict[str, Any]:
    row, _client, _ctx = _admin_row(auth)
    return {"data": _saida_admin(row)}


@router.put("/api/julia/agente/aviso")
def put_aviso(
    payload: AvisoUpdate, auth: tuple = Depends(get_current_user_org), request: Request = None,
) -> dict[str, Any]:
    user, _token, _raw = auth
    require_org_admin_for(get_core_client(), auth, request, "Aviso de privacidade")
    if not svc.contem_link(payload.mensagem_inicial):
        raise AppException(
            "link_obrigatorio",
            "A mensagem inicial deve conter {link} (link do aviso de privacidade).",
            status_code=422,
        )
    _validar_blocos(payload.secoes)
    row, client, (_u, org_id) = _admin_row(auth)
    dados = payload.model_dump(mode="json")
    dados["secoes"] = [s.model_dump(mode="json") for s in payload.secoes]
    novo = svc.atualizar(client, org_id, row, dados, getattr(user, "id", None))
    return {"data": _saida_admin(novo)}


# ── Julia: the connection switch, the token, the pause (contract 5, 11.1, 11.4) ──
_AGENT_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def get_agents_token_client_builder() -> Callable[[str], AgentsClient]:
    """DI seam: ``token -> AgentsClient`` used to VALIDATE a pasted token against
    the real agents status route before it is stored."""

    def build(token: str) -> AgentsClient:
        base = julia.agents_base_url()
        if not base:
            raise AppException(
                "agents_url_indisponivel",
                "Não foi possível resolver a URL do produto agents (PRODUCT_URL_AGENTS).",
                status_code=503,
            )
        return HttpAgentsClient(base, token)

    return build


def get_julia_token_admin() -> ProductTokenAdmin:
    """DI seam: the service-side `api_tokens` writer used to mint the Julia tools token
    (the seed `ProductTokenAdmin`; the in-memory Fake when no service-role key is set)."""
    return make_product_token_admin(get_admin_client() if settings.supabase_service_role_key else None)


TOOLS_TOKEN_TTL = timedelta(days=90)
_TOOLS_TOKEN_SCHEMA = "social_wiring"


class ConexaoAgenteUpdate(StrictHttpModel):
    agente_leads_ativo: bool
    agente_leads_key: Optional[str] = Field(default=None, max_length=63)
    # Absent = keep; explicit null = back to "the connection owner" (11.4).
    agente_handoff_notificar_user_id: Optional[UUID] = None


class TokenUpdate(StrictHttpModel):
    token: str = Field(min_length=8, max_length=512)


class ChatAgentePatch(StrictHttpModel):
    pausado: bool


def _require_admin(auth: tuple, request: Optional[Request], context: str) -> tuple[Any, UUID]:
    user, _token, raw_org = auth
    # B3: admin IN the selected org (auth tuple org_id), never the home-org role.
    require_org_admin_for(get_core_client(), auth, request, context)
    return user, coerce_org_uuid(raw_org)


def _conexao_out(c: WhatsAppConnectionRecord) -> dict[str, Any]:
    return {
        "connection_id": str(c.id),
        "label": c.label,
        "agente_leads_ativo": c.agente_leads_ativo,
        "agente_leads_key": c.agente_leads_key,
        "agente_leads_ativado_em": c.agente_leads_ativado_em,
        "agente_handoff_notificar_user_id": (
            str(c.agente_handoff_notificar_user_id) if c.agente_handoff_notificar_user_id else None
        ),
        "authorized_numbers_count": len([n for n in (c.authorized_numbers or []) if str(n).strip()]),
    }


def _record_or_404(store: WhatsAppConnectionStore, connection_id: UUID, org_id: UUID, *, decrypt: bool = False):
    try:
        record = store.get_connection(connection_id=connection_id, org_id=org_id, decrypt=decrypt)
    except Exception as exc:  # CredentialStoreError => ENCRYPTION_KEY mismatch
        logger.exception("julia: connection read failed")
        raise HTTPException(status_code=503, detail="connection credentials unreadable") from exc
    if record is None:
        raise HTTPException(status_code=404, detail="connection not found")
    return record


@router.get("/api/julia/agente")
async def get_agente(
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
    cfg=Depends(get_settings),
    client_factory=Depends(get_agents_client_factory),
) -> dict[str, Any]:
    """Page 0: per-connection Julia state, whether the org has an agents token, and
    the link health (live agents status, else the last turn's failure)."""
    raw_org = auth[2]
    org_id = coerce_org_uuid(raw_org)
    conexoes = [_conexao_out(c) for c in store.list_connections(org_id=org_id)]
    token_configurado = julia.agents_token_for_org(org_id, cfg=cfg) is not None

    status_agente: Optional[dict[str, Any]] = None
    erro: Optional[str] = None
    client = client_factory(org_id)
    if client is None:
        erro = julia.LINK_ERROR_MESSAGES["nao_configurado"]
    else:
        try:
            st = await client.agent_status(julia.DEFAULT_AGENT_KEY)
            status_agente = st.as_dict()
            if not st.ativo:
                erro = julia.LINK_ERROR_MESSAGES["agent_unavailable"]
            elif not st.llm_configurado:
                erro = julia.LINK_ERROR_MESSAGES["llm_not_configured"]
        except AgentsTokenInvalid:
            erro = julia.LINK_ERROR_MESSAGES["token_invalido"]
        except AgentNotFound:
            erro = julia.LINK_ERROR_MESSAGES["agent_not_found"]
        except AgentsClientError as exc:
            # L2: the UI gets a generic line, never the upstream detail.
            logger.warning("julia: agents status failed (%s)", type(exc).__name__)
            erro = "Não foi possível consultar o produto agents agora."
    if erro is None:
        erro = julia.ler_erro_link(org_id, cfg=cfg)
    return {"data": {
        "conexoes": conexoes, "token_configurado": token_configurado,
        "status_agente": status_agente, "erro": erro,
        # Where "Editar Julia no Agents" points (resolved server-side from the
        # product-URL registry, never hard-coded in the FE). Null = unresolvable.
        "agents_url": julia.agents_base_url(),
    }}


async def aplicar_conexao(
    *, record: WhatsAppConnectionRecord, org_id: UUID, store: WhatsAppConnectionStore, cfg: Any, waha_factory: Any,
    ativo: bool, key: Optional[str], handoff_definido: bool, handoff_alvo: Optional[UUID],
) -> WhatsAppConnectionRecord:
    """THE line-routing change (shared by the legacy `PUT /agente/conexoes/{id}` and the white-label
    `PUT /roteamento/linhas/{id}`): the "this number feeds the agent" switch + the handoff notification target.
    Turning it ON checks every precondition, then takes the 11.1 snapshot of the WAHA session's chats; if the snapshot
    cannot be proven complete the switch stays OFF (502 ``snapshot_falhou``). This is TRANSPORT config (julia-v2 Q4):
    it decides which numbers reach the agent, never how the agent behaves (that is agents' Controles)."""
    connection_id = record.id
    core = get_core_client()

    patch: dict[str, Any] = {}
    if handoff_definido:
        if handoff_alvo is not None:
            julia.exigir_destinatario_valido(core, org_id, handoff_alvo, dono_id=record.user_id)
        patch["agente_handoff_notificar_user_id"] = str(handoff_alvo) if handoff_alvo else None

    key = key or record.agente_leads_key or julia.DEFAULT_AGENT_KEY
    if not _AGENT_KEY_RE.match(key):
        raise AppException("agente_key_invalida", "Chave de agente inválida.", status_code=422)

    if ativo and not record.agente_leads_ativo:
        # H3 / H1 / 11.3 preconditions first (cheap, no network), THEN the snapshot.
        julia.exigir_autorizados(record.authorized_numbers)
        julia.exigir_hmac_configurado(cfg)
        aviso = svc.obter_ou_criar(get_scoped_admin_client("social_wiring"), core, org_id)
        julia.exigir_aviso_completo(aviso)
        julia.public_privacy_link(aviso)

        waha = waha_factory(base_url=record.base_url or None, api_key=record.api_key, session=record.session_name)
        try:
            chat_ids = await julia.listar_todos_os_chats(waha)
        except julia.SnapshotFalhou as exc:
            logger.error("julia: snapshot failed conn=%s: %s — switch stays OFF", connection_id, exc)
            raise AppException(
                "snapshot_falhou",
                "Não foi possível listar as conversas existentes do número. A Julia continua desligada.",
                status_code=502,
            ) from exc
        try:
            lids = await waha.list_lids()
        except Exception:
            logger.warning("julia: list_lids failed — snapshot keeps phone forms only", exc_info=True)
            lids = []
        # Snapshot rows first, flag last: the switch is never on without a complete
        # snapshot (PostgREST has no multi-statement transaction; this ordering is
        # the fail-closed equivalent — an orphaned snapshot only EXCLUDES chats).
        julia.gravar_snapshot(
            get_scoped_admin_client("social_wiring"), org_id=org_id, connection_id=connection_id,
            chat_ids=julia.expandir_aliases(chat_ids, lids),
        )
        patch.update(
            agente_leads_ativo=True, agente_leads_key=key,
            agente_leads_ativado_em=datetime.now(timezone.utc).isoformat(),
        )
    elif ativo:
        # Already on: key / handoff changes only; never re-snapshot (it would not
        # change who is excluded, and `ativado_em` must keep meaning "first on").
        patch["agente_leads_key"] = key
    else:
        patch.update(agente_leads_ativo=False, agente_leads_key=key)

    updated = store.update_agente(connection_id=connection_id, org_id=org_id, patch=patch)
    if updated is None:
        raise HTTPException(status_code=404, detail="connection not found")
    return updated


@router.put("/api/julia/agente/conexoes/{connection_id}")
async def put_conexao(
    connection_id: UUID,
    payload: ConexaoAgenteUpdate,
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
    cfg=Depends(get_settings),
    waha_factory=Depends(get_waha_client_factory),
    request: Request = None,
) -> dict[str, Any]:
    """The line switch + handoff target (legacy surface; the white-label page uses `/api/julia/roteamento`)."""
    _user, org_id = _require_admin(auth, request, "A Julia")
    record = _record_or_404(store, connection_id, org_id, decrypt=True)
    updated = await aplicar_conexao(
        record=record, org_id=org_id, store=store, cfg=cfg, waha_factory=waha_factory,
        ativo=payload.agente_leads_ativo,
        key=payload.agente_leads_key,
        handoff_definido="agente_handoff_notificar_user_id" in payload.model_fields_set,
        handoff_alvo=payload.agente_handoff_notificar_user_id,
    )
    return {"data": _conexao_out(updated)}


@router.put("/api/julia/agente/token", status_code=status.HTTP_204_NO_CONTENT)
async def put_token(
    payload: TokenUpdate,
    auth: tuple = Depends(get_current_user_org),
    cfg=Depends(get_settings),
    build_client=Depends(get_agents_token_client_builder),
    token_admin: ProductTokenAdmin = Depends(get_julia_token_admin),
    request: Request = None,
) -> Response:
    """Paste the org's agents channel token. It is VALIDATED against agents' status
    route first (``token_invalido`` if refused) and stored Fernet-encrypted; it is
    never returned or logged.

    Then (Julia contract 2.2) SW mints the tools token agents calls back with
    (``social-wiring:lais-tools``, issuer ``agents``, 90 days) and pushes it to agents'
    ``PUT /api/channels/ferramentas-token`` -- so the owner never pastes a second token.
    A failure there still answers 204 (the channel token IS stored and Julia answers):
    the page shows ``Ferramentas da Julia indisponíveis — reenvie o token`` via ``erro``."""
    user, org_id = _require_admin(auth, request, "O token do agente")
    token = payload.token.strip()
    agents_client = build_client(token)
    try:
        await agents_client.agent_status(julia.DEFAULT_AGENT_KEY)
    except AgentsTokenInvalid as exc:
        raise AppException("token_invalido", "O produto agents recusou este token.", status_code=422) from exc
    except AgentNotFound:
        # The token was ACCEPTED; the agent just is not seeded yet. Storing it is right.
        logger.info("julia: token accepted by agents but the agent does not exist yet (org=%s)", org_id)
    except AgentsClientError as exc:
        logger.error("julia: could not validate the agents token (%s)", type(exc).__name__)
        raise AppException(
            "agents_indisponivel", "Não foi possível validar o token com o produto agents agora.", status_code=502
        ) from exc
    try:
        store = api_keys_store.build_api_key_store(encryption_key=cfg.encryption_key)
    except EncryptionNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    api_keys_store.put_api_key(store, str(org_id), julia.AGENTS_KEY_NAME, token)
    julia.limpar_erro_link(org_id, cfg=cfg)
    if not await _entregar_token_ferramentas(token_admin, agents_client, org_id, getattr(user, "id", None)):
        julia.registrar_erro_link(org_id, "ferramentas_indisponiveis", cfg=cfg)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _uuid_ou_none(value: Any) -> Optional[UUID]:
    try:
        return UUID(str(value)) if value else None
    except ValueError:
        return None  # `minted_by` is audit metadata: a non-UUID user id must not block the mint


def _tokens_ferramentas_ativos(org_id: UUID) -> list[UUID]:
    """Ids of the org's non-revoked tools tokens (read through the scoped client)."""
    rows = (
        get_scoped_admin_client("social_wiring").table("api_tokens").select("id, issuer, revoked_at")
        .eq("org_id", str(org_id)).eq("label", TOOLS_TOKEN_LABEL).execute().data or []
    )
    return [UUID(str(r["id"])) for r in rows if not r.get("revoked_at") and r.get("issuer") == TOOLS_TOKEN_ISSUER]


async def _entregar_token_ferramentas(
    token_admin: ProductTokenAdmin, agents_client: AgentsClient, org_id: UUID, minted_by: Any,
) -> bool:
    """Mint the tools token, hand it to agents, retire the previous ones. True = agents has it.
    Never raises: every failure is logged and ends in False (the caller records the page error).
    A token that could not be delivered is revoked at once -- no orphan secret stays valid."""
    try:
        anteriores = _tokens_ferramentas_ativos(org_id)
        minted = token_admin.mint(
            _TOOLS_TOKEN_SCHEMA, org_id=org_id, label=TOOLS_TOKEN_LABEL, scopes=[TOOLS_TOKEN_SCOPE],
            expires_at=datetime.now(timezone.utc) + TOOLS_TOKEN_TTL, issuer=TOOLS_TOKEN_ISSUER,
            minted_by=_uuid_ou_none(minted_by),
        )
    except Exception:
        logger.exception("julia: could not mint the tools token for org=%s", org_id)
        return False
    try:
        await agents_client.put_ferramentas_token(minted.secret)
    except Exception as exc:  # AgentsClientError or anything the transport raises
        logger.error("julia: agents refused the tools token org=%s (%s)", org_id, type(exc).__name__)
        try:
            token_admin.revoke(_TOOLS_TOKEN_SCHEMA, minted.info.id, org_id=org_id)
        except Exception:
            logger.exception("julia: could not revoke the undelivered tools token org=%s id=%s", org_id, minted.info.id)
        return False
    for antigo in anteriores:
        try:
            token_admin.revoke(_TOOLS_TOKEN_SCHEMA, antigo, org_id=org_id)
        except Exception:
            logger.exception("julia: could not retire the previous tools token org=%s id=%s", org_id, antigo)
    return True


@router.patch("/api/whatsapp/connections/{connection_id}/chats/{chat_id:path}/agente")
async def patch_chat_agente(
    connection_id: UUID,
    chat_id: str,
    payload: ChatAgentePatch,
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
    cfg=Depends(get_settings),
    client_factory=Depends(get_agents_client_factory),
    request: Request = None,
) -> dict[str, Any]:
    """Pause / resume the agent on ONE conversation (a human is handling it). julia-v2: the control lives in AGENTS --
    this calls `PATCH /threads/{id}/participantes/{agent}` with the SW user as the actor, then mirrors agents' answer
    onto the chat row for the list chips. SW flips NO local flag on its own: when agents cannot be reached the toggle
    fails (502) and the shown state does not change."""
    user, org_id = _require_admin(auth, request, "A Julia")
    record = _record_or_404(store, connection_id, org_id)
    client = client_factory(org_id)
    if client is None:
        raise AppException("agents_nao_configurado", "O produto agents ainda não está configurado.", status_code=409)
    chat_store = WhatsAppChatStore(admin_supabase=get_admin_client(), org_id=org_id)
    agent_key = record.agente_leads_key or julia.DEFAULT_AGENT_KEY
    try:
        parte = await julia_thread_service.alternar_conversa(
            client, chat_store, connection_id=connection_id, chat_id=chat_id, agent_key=agent_key,
            pausado=payload.pausado, user_id=getattr(user, "id", None) or "", motivo="toggle_sw",
        )
    except (julia_thread_service.ConversaSemThread, ParticipanteNotFound) as exc:
        # agents has no thread / the agent does not take part in it: a lead it never served has nothing to pause
        raise AppException("conversa_sem_agente", "O agente ainda não atendeu esta conversa.", status_code=404) from exc
    except TransicaoInvalida as exc:
        raise AppException("transicao_invalida", "A conversa não pode mudar para esse estado agora.", status_code=409) from exc
    except AgentsClientError as exc:
        logger.error("julia: pause toggle failed at agents (%s) conn=%s", type(exc).__name__, connection_id)
        raise AppException("agents_indisponivel", "Não foi possível falar com o agente agora. Tente novamente.", status_code=502) from exc
    try:  # contract 0.2: a pause/resume invalidates every job queued for this contato
        julia_contatos_service.bump_gen_do_chat(get_scoped_admin_client("social_wiring"), org_id, connection_id, chat_id)
    except Exception:
        logger.exception("julia: gen bump on pause failed conn=%s chat=%s (agents HAS the new state)", connection_id, chat_id)
    pausado = parte.estado == "pausado"
    summary = chat_store.get_chat(connection_id=connection_id, chat_id=chat_id)
    event = {**summary.as_dict(), "agente_pausado": pausado, "agente_estado": parte.estado} if summary else {
        "chat_id": chat_id, "agente_pausado": pausado, "agente_estado": parte.estado,
    }
    await publish_whatsapp_event(
        get_whatsapp_bus(cfg.redis_url), connection_id=connection_id, event=EVENT_CHAT_UPSERT, payload=event,
    )
    return {"chat_id": chat_id, "agente_pausado": pausado, "agente_estado": parte.estado}


@router.get("/api/whatsapp/connections/{connection_id}/chats/{chat_id:path}/agente")
async def get_chat_agente(
    connection_id: UUID,
    chat_id: str,
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
    client_factory=Depends(get_agents_client_factory),
) -> dict[str, Any]:
    """The state of the agent in ONE conversation as AGENTS reports it (`GET thread`): what the Conversas toggle shows.
    `fonte` says where it came from: `agents` (live), `espelho` (agents unreachable: the last mirrored value, stale) or
    `nenhuma` (agents has no thread for this chat)."""
    org_id = coerce_org_uuid(auth[2])
    record = _record_or_404(store, connection_id, org_id)
    chat_store = WhatsAppChatStore(admin_supabase=get_admin_client(), org_id=org_id)
    estado = await julia_thread_service.estado_da_conversa(
        client_factory(org_id), chat_store, connection_id=connection_id, chat_id=chat_id,
        agent_key=record.agente_leads_key or julia.DEFAULT_AGENT_KEY,
    )
    return {"data": estado}


@router.post("/api/julia/agente/conexoes/{connection_id}/chats/{chat_id:path}/apagar-dados")
async def post_apagar_dados(
    connection_id: UUID,
    chat_id: str,
    auth: tuple = Depends(get_current_user_org),
    store: WhatsAppConnectionStore = Depends(get_connection_store),
    client_factory=Depends(get_agents_client_factory),
    request: Request = None,
) -> dict[str, Any]:
    """Deletion on request for a chat (M5), for a human who received the request
    through a handoff. Same hook the lead worker runs on "apagar meus dados"."""
    _user, org_id = _require_admin(auth, request, "A exclusão de dados")
    record = _record_or_404(store, connection_id, org_id)
    module = get_conversation_module()
    res = await julia.apagar_dados_do_chat(
        client=get_scoped_admin_client("social_wiring"), connection=record, chat_id=chat_id,
        agents_client=client_factory(org_id), agent_key=record.agente_leads_key or julia.DEFAULT_AGENT_KEY,
        buffer=module.buffer if module else None,
    )
    return {"data": {
        "sw_mensagens": res.sw_mensagens, "sw_contatos": res.sw_contatos,
        "agents_ok": res.agents_ok, "agents_apagou": res.agents_apagou, "julia_contatos": res.julia_contatos,
    }}


__all__ = ["router"]
