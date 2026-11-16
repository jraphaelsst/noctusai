"""Estruturas -- AI derivation of a DRAFT Estrutura from a library video (estruturas-contract.md sections 6.2, 8.8, 12).

ONE service shared by the two entry points:

* the auto-draft job ``estruturas.rascunho_do_viral`` (:mod:`.estruturas_autodraft`, ``origem='viral_auto'``,
  ``ator_tipo='sistema_ia'``), and
* ``POST /estruturas/a-partir-do-viral`` (:mod:`routers.estruturas_ia`, ``origem='manual'``, ``ator_tipo='admin'``).

What it does, in order (every refusal is a coded :class:`EstruturaError`, never a partial write):

1. the KILL SWITCH ``biblioteca_ingestao_habilitada`` -- the very first thing, before any other read: OFF or unreadable
   is 503 ``biblioteca_desligada`` (both origins);
2. the UTC-day cap ``estruturas_autodraft_dia`` on model ATTEMPTS (calls of the registry key, ok or not -- spend is
   per call, not per inserted row);
3. the ingestion org, the video (must exist and carry content), its profile (opt-out is refused), the existing
   Estruturas of the video, and (manual) the recent-duplicate and per-admin daily guards;
4. the vendor pin: the registry row must name ``anthropic`` (LGPD sub-processor);
5. the model call (prompt, model and vendor from the platform registry row ``estruturas.derivacao``; metered on the
   INGESTION org's budget and attributed through ``llm_usage_context``);
6. strict validation (:func:`saida_ia_estruturas.validar_derivacao`) and ONE call to the SECURITY DEFINER RPC
   ``cs_estrutura_criar`` (status ``rascunho``, EVERY field ``ia_sugerido``; the RPC writes the events
   ``criada``/``criada_automatica`` + ``ia_preenchida`` in the same transaction). Invalid output = no Estrutura.

What text reaches the model: the video's caption, transcript, stored gancho/blueprint and the active block-type
catalogue -- minimised (@mentions, e-mails, phones, URLs, the creator's handle and display name removed) and fenced
(see ``prompts/estruturas_derivacao``). No profile id, handle, name field, URL, image or org/user id. The reply is
data: the server attaches ids, provenance, origem and status.

Every synchronous read / RPC runs in a worker thread (``anyio.to_thread``); only the model call is awaited on the loop.
"""
from __future__ import annotations

import functools
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

import anyio.to_thread

from noctusai_lib.integrations.llm import attribution
from noctusai_lib.integrations.llm.exceptions import (
    LLMAPIError,
    LLMBudgetExceeded,
    LLMBudgetNotConfigured,
    LLMBudgetUnverifiable,
    LLMCreditsExhausted,
    LLMCreditsUnverifiable,
    LLMNotConfigured,
    ProviderQuotaExhausted,
    SpendCeilingExceeded,
    SpendCeilingUnverifiable,
)
from noctusai_lib.integrations.prompt_registry import RegistroIAIndisponivel, chamar_ia, prompt_e_modelo

from app.modules.media_creation import saida_ia_estruturas as saida
from app.modules.media_creation.estruturas_tipos_bloco import NOME_OUTRO
from app.modules.media_creation.prompts import estruturas_derivacao as prompt
from app.modules.media_creation.saida_ia import SaidaIaFalha
from app.modules.media_creation.services import biblioteca_fonte, biblioteca_optout, geracao_jobs
from app.modules.media_creation.services.estruturas_service import (
    EstruturaError,
    _rpc_detalhes,
    coded,
    mapear_erro_rpc,
)

logger = logging.getLogger(__name__)

ESTRUTURAS = "cs_estruturas"
TIPOS = "cs_estrutura_tipos_bloco"
VIRAIS = "cs_virais"
PERFIS = "cs_perfis_monitorados"
#: Where ``chamar_ia`` records every platform AI call (seed ``prompt_registry``; ok or failed) on the core database.
CHAMADAS = "plataforma_agente_chamadas"

VIRAL_COLS = "id,perfil_id,caption,transcricao_texto,gancho,blueprint,media_type,media_product_type"
FEATURE = "estruturas.derivacao"

#: The registry row must name this vendor (LGPD sub-processor of the ROPA amendment); the registry itself would
#: accept others. NOC-REMEDIATE[estruturas-derivacao-registry-seed]: the seed migration sets it; before switch-on.
VENDOR_PERMITIDO = "anthropic"

#: Manual endpoint guards. NOC-REMEDIATE[estruturas-manual-limites-config]: move both to ``app/config.py`` (C3, the
#: tech-lead owns it) before switch-on.
MANUAL_RECENTE_MIN = 10
MANUAL_MAX_DIA_ADMIN = 20

#: Every exception meaning "the money gate refused or could not verify" (fail closed): the job waits for the next day.
ERROS_ORCAMENTO: tuple[type[BaseException], ...] = (
    LLMBudgetExceeded, LLMBudgetUnverifiable, LLMBudgetNotConfigured, SpendCeilingExceeded, SpendCeilingUnverifiable,
    LLMCreditsExhausted, LLMCreditsUnverifiable,
)

# ── stable codes (the job handler and the router both read them) ─────────────────────────────────────────────
VIRAL_NAO_ENCONTRADO = "viral_nao_encontrado"
VIRAL_SEM_CONTEUDO = "viral_sem_conteudo"
VIRAL_JA_TEM_RASCUNHO = "viral_ja_tem_rascunho"
VIRAL_JA_TEM_ESTRUTURA = "viral_ja_tem_estrutura"
RASCUNHO_MANUAL_RECENTE = "rascunho_manual_recente"
PERFIL_OPTOUT = "perfil_optout"
SEM_ORG = biblioteca_fonte.CODIGO_SEM_ORG
BIBLIOTECA_DESLIGADA = "biblioteca_desligada"
ORCAMENTO = "orcamento_ia_excedido"
SEM_CREDITO_PROVEDOR = "provedor_sem_credito"
IA_INDISPONIVEL = "ia_indisponivel"
IA_NAO_CONFIGURADA = "ia_nao_configurada"
IA_FALHOU = "ia_falhou"
SAIDA_INVALIDA = "saida_ia_invalida"
LIMITE_DIARIO = "limite_diario_autodraft"
LIMITE_MANUAL_DIA = "limite_diario_manual"
LIMITE_NAO_VERIFICAVEL = "limite_nao_verificavel"
CATALOGO_INVALIDO = "catalogo_sem_outro"

ORIGEM_AUTO = "viral_auto"
ORIGEM_MANUAL = "manual"
PROVENIENCIA = "ia_sugerido"


def _jitter_padrao() -> float:
    import random

    return random.uniform(0.0, 3600.0)


@dataclass
class IaPorts:
    """The seams of the derivation (production wiring in :func:`default_ports`; Fakes in tests -- the seed's own
    ``registry`` / ``chat`` seams of ``chamar_ia``, not monkeypatches)."""

    db: Any
    #: ``() -> str | None``: the platform ingestion org (``corestudio_biblioteca_org_id``); every model call is metered here.
    ingestao_org: Callable[[], Optional[str]]
    #: ``() -> str | None``: the system user the usage rows are attributed to (``None`` = attributed to the org only).
    ingestao_user: Callable[[], Optional[str]] = lambda: None
    cfg: Any = None
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(timezone.utc))
    chamar: Callable[..., Awaitable[Any]] = chamar_ia
    registry: Any = None
    chat: Optional[Callable[..., Awaitable[Any]]] = None
    #: ``() -> bool``: the kill switch ``biblioteca_ingestao_habilitada`` (fail closed: unreadable = OFF).
    habilitada: Callable[[], bool] = geracao_jobs.read_ingestao_habilitada
    #: ``() -> core client`` holding the platform AI call ledger (``plataforma_agente_chamadas``).
    core_db: Optional[Callable[[], Any]] = None
    #: ``org_id -> monthly LLM budget (BRL) | None``: ``None`` = no budget row (logged loudly).
    orcamento: Optional[Callable[[str], Awaitable[Optional[float]]]] = None
    #: ``() -> 0..3600`` seconds added to a "wait for tomorrow" reschedule (spreads a backlog over the first hour).
    jitter: Callable[[], float] = _jitter_padrao


def default_ports() -> IaPorts:
    from noctusai_lib.integrations.llm.budget import fetch_budget_brl

    from app.config import settings
    from app.database import get_core_client
    from app.dependencies import get_admin_client

    db = get_admin_client()
    if db is None:
        raise RuntimeError("estruturas_ia: sem cliente admin do Supabase")
    return IaPorts(
        db=db,
        ingestao_org=lambda: biblioteca_fonte.read_ingestao_org(default=settings.corestudio_biblioteca_org_id),
        ingestao_user=lambda: biblioteca_fonte.read_ingestao_user(default=settings.corestudio_biblioteca_user_id),
        cfg=settings, core_db=get_core_client, orcamento=fetch_budget_brl,
    )


# ── pure helpers ─────────────────────────────────────────────────────────────────────────────────────────────


def tem_conteudo(viral: dict[str, Any]) -> bool:
    """A video can be derived from when it carries a blueprint, a transcript or a caption (non-blank)."""
    return any(str(viral.get(k) or "").strip() for k in ("blueprint", "transcricao_texto", "caption"))


def formato_sugerido(viral: dict[str, Any]) -> Optional[str]:
    """Server hint from the media type (contract 8.8): video/reel -> reels, carousel -> carrossel, image -> post."""
    produto = str(viral.get("media_product_type") or "").upper()
    tipo = str(viral.get("media_type") or "").upper()
    if produto == "REELS" or tipo == "VIDEO":
        return "reels"
    if tipo in ("CAROUSEL_ALBUM", "SIDECAR"):
        return "carrossel"
    if tipo in ("IMAGE", "FOTO") or produto == "FEED":
        return "post"
    return None


def inicio_do_dia(agora: datetime) -> datetime:
    return agora.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def segundos_ate_o_proximo_dia(agora: datetime, jitter_s: float = 0.0) -> float:
    """Seconds from ``agora`` to the next UTC midnight, plus ``jitter_s``: when a gated job is tried again."""
    proximo = inicio_do_dia(agora) + timedelta(days=1)
    return (proximo - agora.astimezone(timezone.utc)).total_seconds() + float(jitter_s)


def _parse_dt(valor: Any) -> Optional[datetime]:
    if not valor:
        return None
    try:
        dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def _bloq(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """A synchronous (PostgREST / RPC) call off the event loop."""
    return await anyio.to_thread.run_sync(functools.partial(fn, *args, **kwargs))


# ── reads (synchronous; always called through ``_bloq``) ─────────────────────────────────────────────────────


def carregar_viral(db: Any, viral_id: str) -> dict[str, Any]:
    rows = db.table(VIRAIS).select(VIRAL_COLS).eq("id", str(viral_id)).execute().data
    if not rows:
        raise coded(404, VIRAL_NAO_ENCONTRADO, "Vídeo não encontrado.")
    return rows[0]


def estruturas_do_viral(db: Any, viral_id: str) -> list[dict[str, Any]]:
    return db.table(ESTRUTURAS).select("id,status,origem,created_at").eq("viral_id", str(viral_id)).execute().data or []


def ja_tem_estrutura(db: Any, viral_id: str) -> bool:
    """Any NON-archived Estrutura links the video (the auto-draft's idempotency check)."""
    return any(r.get("status") != "arquivada" for r in estruturas_do_viral(db, viral_id))


def contar_tentativas_do_dia(core_db: Any, agora: datetime) -> int:
    """Model ATTEMPTS of the derivation key since UTC midnight (the registry records every call, ok or not)."""
    res = (
        core_db.table(CHAMADAS).select("id", count="exact").eq("chave", prompt.CHAVE)
        .gte("criado_em", inicio_do_dia(agora).isoformat()).limit(1).execute()
    )
    return res.count if getattr(res, "count", None) is not None else len(res.data or [])


def contar_manuais_do_dia(db: Any, agora: datetime, ator_id: str) -> int:
    res = (
        db.table(ESTRUTURAS).select("id", count="exact").eq("origem", ORIGEM_MANUAL).eq("created_by", str(ator_id))
        .eq("formula_origem", PROVENIENCIA).gte("created_at", inicio_do_dia(agora).isoformat()).limit(1).execute()
    )
    return res.count if getattr(res, "count", None) is not None else len(res.data or [])


def tipos_ativos(db: Any) -> list[dict[str, Any]]:
    return (
        db.table(TIPOS).select("id,nome,ordem,instrucao_referencia,sistema").eq("ativo", True).order("ordem").execute().data or []
    )


def verificar_limite_diario(ports: IaPorts) -> None:
    """Refuse (429 ``limite_diario_autodraft``) when today's attempts reached ``estruturas_autodraft_dia``. An
    unmeasurable count FAILS CLOSED (503 ``limite_nao_verificavel``), never "assume zero"."""
    try:
        db = ports.core_db() if ports.core_db else None
        if db is None:
            raise RuntimeError("sem cliente core")
        feitas = contar_tentativas_do_dia(db, ports.clock())
    except Exception as exc:  # noqa: BLE001 - re-raised as a coded 503: an unmeasurable cap must not read as "under cap"
        logger.error("estruturas_ia: tentativas do dia não medidas (%s)", type(exc).__name__)
        raise coded(503, LIMITE_NAO_VERIFICAVEL, "Não foi possível verificar o limite diário de IA.") from exc
    if feitas >= int(ports.cfg.estruturas_autodraft_dia):
        raise coded(429, LIMITE_DIARIO, "Limite diário de estruturas por IA atingido.")


def exigir_habilitada(ports: IaPorts) -> None:
    """The kill switch (``biblioteca_ingestao_habilitada``): OFF / unreadable -> 503 ``biblioteca_desligada``."""
    try:
        ligada = bool(ports.habilitada())
    except Exception as exc:  # noqa: BLE001 - an unreadable switch reads as OFF (fail closed), coded below
        logger.error("estruturas_ia: chave de ingestão ilegível (%s)", type(exc).__name__)
        ligada = False
    if not ligada:
        raise coded(503, BIBLIOTECA_DESLIGADA, "A biblioteca está desligada no momento.")


def _preparar(ports: IaPorts, viral_id: str, origem: str, ator_id: Optional[str]) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], str]:
    """Every synchronous check, in the contract's order. Returns ``(viral, perfil, tipos, org_id)``."""
    exigir_habilitada(ports)
    verificar_limite_diario(ports)
    org_id = ports.ingestao_org()
    if not org_id:
        raise coded(503, SEM_ORG, biblioteca_fonte.MSG_SEM_ORG)
    viral = carregar_viral(ports.db, viral_id)
    if not tem_conteudo(viral):
        raise coded(422, VIRAL_SEM_CONTEUDO, "Este vídeo ainda não tem conteúdo para gerar uma estrutura.")
    perfil = ports.db.table(PERFIS).select("id,handle,nome").eq("id", str(viral["perfil_id"])).execute().data
    if not perfil:
        raise coded(404, VIRAL_NAO_ENCONTRADO, "Vídeo não encontrado.")
    if biblioteca_optout.esta_bloqueado(ports.db, perfil[0]["handle"]):
        raise coded(409, PERFIL_OPTOUT, "Este criador pediu para não ser monitorado.")
    agora = ports.clock()
    existentes = estruturas_do_viral(ports.db, viral_id)
    vivas_auto = any(r.get("origem") == ORIGEM_AUTO and r.get("status") != "arquivada" for r in existentes)
    if origem == ORIGEM_AUTO:
        if any(r.get("status") != "arquivada" for r in existentes):
            raise coded(409, VIRAL_JA_TEM_ESTRUTURA, "Este vídeo já tem uma estrutura.")
        # An ARCHIVED viral_auto still owns the one-per-video unique key: a second auto-draft would be refused by the
        # database; say so up front instead of spending a model call.
        if any(r.get("origem") == ORIGEM_AUTO for r in existentes):
            raise coded(409, VIRAL_JA_TEM_RASCUNHO, "Este vídeo já tem uma estrutura automática.")
    else:
        if vivas_auto:
            raise coded(409, VIRAL_JA_TEM_RASCUNHO, "Este vídeo já tem uma estrutura automática.")
        limite = agora - timedelta(minutes=MANUAL_RECENTE_MIN)
        if any(r.get("origem") == ORIGEM_MANUAL and r.get("status") != "arquivada"
               and (_parse_dt(r.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc)) >= limite for r in existentes):
            raise coded(409, RASCUNHO_MANUAL_RECENTE, "Este vídeo acabou de receber uma estrutura. Aguarde alguns minutos.")
        if ator_id and contar_manuais_do_dia(ports.db, agora, ator_id) >= MANUAL_MAX_DIA_ADMIN:
            raise coded(429, LIMITE_MANUAL_DIA, "Limite diário de estruturas por vídeo atingido para este usuário.")
    tipos = tipos_ativos(ports.db)
    if NOME_OUTRO not in {t["nome"] for t in tipos}:
        raise coded(503, CATALOGO_INVALIDO, "O catálogo de tipos de bloco não tem o tipo \"Outro\".")
    return viral, perfil[0], tipos, str(org_id)


def _checar_vendor(ports: IaPorts) -> None:
    """The registry row of the derivation key must name the pinned vendor; a missing row is ``ia_indisponivel``."""
    try:
        _prompt, _modelo, vendor = prompt_e_modelo(prompt.CHAVE, registry=ports.registry)
    except RegistroIAIndisponivel as exc:
        raise _erro_ia(exc) from exc
    if str(vendor or "").strip().lower() != VENDOR_PERMITIDO:
        logger.error("estruturas_ia: vendor do registro diferente do fixado (%s)", VENDOR_PERMITIDO)
        raise coded(503, IA_NAO_CONFIGURADA, "A IA de estruturas não está configurada com o fornecedor autorizado.")


# ── the derivation ───────────────────────────────────────────────────────────────────────────────────────────


def _erro_ia(exc: BaseException) -> EstruturaError:
    if isinstance(exc, ProviderQuotaExhausted):
        return coded(503, SEM_CREDITO_PROVEDOR, "O fornecedor de IA está sem crédito no momento.")
    if isinstance(exc, ERROS_ORCAMENTO):
        return coded(503, ORCAMENTO, "O orçamento de IA da organização de ingestão foi atingido.")
    if isinstance(exc, RegistroIAIndisponivel):
        return coded(503, IA_INDISPONIVEL, "A IA de estruturas não está disponível no momento.")
    if isinstance(exc, LLMNotConfigured):
        return coded(503, IA_NAO_CONFIGURADA, "A IA não está configurada para a organização de ingestão.")
    return coded(502, IA_FALHOU, "A IA não respondeu. Tente de novo em instantes.")


async def derivar(
    ports: IaPorts, viral: dict[str, Any], tipos: list[dict[str, Any]], org_id: str, perfil: Optional[dict[str, Any]] = None,
) -> saida.EstruturaDerivada:
    """One model call + strict validation. Raises :class:`EstruturaError` (``ia_*``, ``orcamento_ia_excedido``) or
    ``saida_ia_invalida`` carrying the failure ``codigo`` + ``campo`` (never the model's text)."""
    perfil = perfil or {}
    handle, nome = perfil.get("handle"), perfil.get("nome")
    nomes_catalogo = [t["nome"] for t in tipos if not t.get("sistema")]
    mensagem = prompt.build_user_message(
        legenda=viral.get("caption"), transcricao=viral.get("transcricao_texto"), gancho=viral.get("gancho"),
        blueprint=viral.get("blueprint"), formato_sugerido=formato_sugerido(viral),
        tipos=[(t["nome"], t.get("instrucao_referencia")) for t in tipos if not t.get("sistema")],
        handle=handle, nome=nome,
    )
    if ports.orcamento is not None:
        try:
            if await ports.orcamento(org_id) is None:
                logger.error("estruturas_ia: a org de ingestão NÃO tem orçamento de IA cadastrado (monthly_llm_budget_brl): "
                             "a trava de gasto não protege esta chamada")
        except Exception as exc:  # noqa: BLE001 - a preflight, never the gate itself (enforce_budget runs in the call)
            logger.error("estruturas_ia: orçamento da org de ingestão não lido (%s)", type(exc).__name__)
    extra: dict[str, Any] = {"chat": ports.chat} if ports.chat is not None else {}
    try:
        with attribution.llm_usage_context(feature=FEATURE, org_id=org_id, user_id=ports.ingestao_user()):
            resposta = await ports.chamar(
                prompt.CHAVE, [{"role": "user", "content": mensagem}], org_id=org_id, registry=ports.registry,
                temperature=0, cache=False, purpose="extract", **extra,
            )
    except (RegistroIAIndisponivel, LLMNotConfigured, LLMAPIError, *ERROS_ORCAMENTO) as exc:
        logger.error("estruturas_ia: chamada falhou viral=%s (%s)", viral.get("id"), type(exc).__name__)
        raise _erro_ia(exc) from exc
    origem = saida.Origem(
        legenda=viral.get("caption"), transcricao=viral.get("transcricao_texto"), gancho=viral.get("gancho"),
        blueprint=viral.get("blueprint"), proibidos=tuple(x for x in (handle, nome) if x),
    )
    try:
        return saida.validar_derivacao(resposta.texto, tipos=nomes_catalogo, origem=origem)
    except SaidaIaFalha as exc:
        # content-free by construction: the code and a positional field name only, never the model's text
        logger.warning("estruturas_ia: saída inválida viral=%s codigo=%s campo=%s", viral.get("id"), exc.codigo, exc.campo)
        raise coded(
            422, SAIDA_INVALIDA, "A IA devolveu uma estrutura inválida; nenhum rascunho foi criado.",
            motivo=exc.codigo, campo=exc.campo,
        ) from exc


def montar_payload(
    derivada: saida.EstruturaDerivada, viral: dict[str, Any], tipo_ids: dict[str, str], *, origem: str,
    ator_id: Optional[str], ator_tipo: str,
) -> dict[str, Any]:
    """The ``p`` of ``cs_estrutura_criar``: a rascunho, EVERY field ``ia_sugerido``, ids attached by the server."""
    return {
        "perfil_id": str(viral["perfil_id"]), "viral_id": str(viral["id"]), "status": "rascunho", "origem": origem,
        "formula_headline": derivada.formula_headline, "formato": formato_sugerido(viral), "objetivos": list(derivada.objetivos),
        "formula_origem": PROVENIENCIA, "formato_origem": PROVENIENCIA, "objetivos_origem": PROVENIENCIA,
        "ator_id": ator_id, "ator_tipo": ator_tipo,
        "blocos": [
            {
                "nome": b.nome, "tipo_id": tipo_ids[b.tipo_nome], "tempo": b.tempo, "instrucao": b.instrucao,
                "nome_origem": PROVENIENCIA, "tipo_origem": PROVENIENCIA, "tempo_origem": PROVENIENCIA,
                "instrucao_origem": PROVENIENCIA,
            }
            for b in derivada.blocos
        ],
    }


def _rpc_criar(db: Any, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        res = db.rpc("cs_estrutura_criar", {"p": payload}).execute()
    except Exception as exc:  # noqa: BLE001 - classified below; an unknown failure is re-raised, never swallowed
        erro = mapear_erro_rpc(exc, corpo=True)
        if erro is None:
            # type + SQLSTATE only: the exception text can carry the payload (model-written text)
            logger.error("estruturas_ia: cs_estrutura_criar falhou (%s sqlstate=%s)", type(exc).__name__, _rpc_detalhes(exc)[2] or "?")
            raise
        raise erro from exc
    data = getattr(res, "data", None)
    if isinstance(data, list):
        data = data[0] if data else None
    return data if isinstance(data, dict) else {}


async def criar_rascunho(
    ports: IaPorts, viral_id: str, *, origem: str, ator_id: Optional[str], ator_tipo: str,
) -> dict[str, Any]:
    """The whole path for ONE video. Returns ``{"id", "codigo", "versao"}`` of the new rascunho.

    ``origem='viral_auto'`` (the job): idempotent -- ANY non-archived Estrutura on the video is
    :data:`VIRAL_JA_TEM_ESTRUTURA` (409). ``origem='manual'`` (the admin endpoint): only an existing non-archived
    ``viral_auto`` blocks (:data:`VIRAL_JA_TEM_RASCUNHO`, 409, contract 6.2), plus the recent-duplicate and per-admin
    daily guards. Both: the kill switch first, then the attempt cap."""
    viral, perfil, tipos, org_id = await _bloq(_preparar, ports, viral_id, origem, ator_id)
    await _bloq(_checar_vendor, ports)
    derivada = await derivar(ports, viral, tipos, org_id, perfil)
    tipo_ids = {t["nome"]: str(t["id"]) for t in tipos}
    payload = montar_payload(derivada, viral, tipo_ids, origem=origem, ator_id=ator_id, ator_tipo=ator_tipo)
    return await _bloq(_rpc_criar, ports.db, payload)


__all__ = [
    "BIBLIOTECA_DESLIGADA", "CATALOGO_INVALIDO", "ERROS_ORCAMENTO", "IA_FALHOU", "IA_INDISPONIVEL", "IA_NAO_CONFIGURADA",
    "IaPorts", "LIMITE_DIARIO", "LIMITE_MANUAL_DIA", "LIMITE_NAO_VERIFICAVEL", "MANUAL_MAX_DIA_ADMIN", "MANUAL_RECENTE_MIN",
    "ORCAMENTO", "ORIGEM_AUTO", "ORIGEM_MANUAL", "PERFIL_OPTOUT", "RASCUNHO_MANUAL_RECENTE", "SAIDA_INVALIDA", "SEM_CREDITO_PROVEDOR",
    "SEM_ORG", "VENDOR_PERMITIDO", "VIRAL_JA_TEM_ESTRUTURA", "VIRAL_JA_TEM_RASCUNHO", "VIRAL_NAO_ENCONTRADO",
    "VIRAL_SEM_CONTEUDO", "carregar_viral", "contar_tentativas_do_dia", "criar_rascunho", "default_ports", "derivar",
    "estruturas_do_viral", "exigir_habilitada", "formato_sugerido", "ja_tem_estrutura", "montar_payload",
    "segundos_ate_o_proximo_dia", "tem_conteudo", "tipos_ativos", "verificar_limite_diario",
]
