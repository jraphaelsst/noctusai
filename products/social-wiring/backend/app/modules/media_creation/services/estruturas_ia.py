"""Estruturas -- AI derivation of a DRAFT Estrutura from a library video (estruturas-contract.md sections 6.2, 8.8, 12).

ONE service shared by the two entry points:

* the auto-draft job ``estruturas.rascunho_do_viral`` (:mod:`.estruturas_autodraft`, ``origem='viral_auto'``,
  ``ator_tipo='sistema_ia'``), and
* ``POST /estruturas/a-partir-do-viral`` (:mod:`routers.estruturas_ia`, ``origem='manual'``, ``ator_tipo='admin'``).

What it does, in order (every refusal is a coded :class:`EstruturaError`, never a partial write):
the video must exist and carry content (blueprint | transcript | caption) -> its profile must not be opted out ->
no non-archived Estrutura may already link it -> (auto only) the UTC-day cap ``estruturas_autodraft_dia`` ->
the model call (prompt, model and vendor from the platform registry row ``estruturas.derivacao``; metered on the
INGESTION org's budget and attributed through ``llm_usage_context``) -> strict validation
(:func:`saida_ia_estruturas.validar_derivacao`) -> ONE call to the SECURITY DEFINER RPC ``cs_estrutura_criar``
(status ``rascunho``, EVERY field ``ia_sugerido``; the RPC writes the events ``criada``/``criada_automatica`` +
``ia_preenchida`` in the same transaction). Invalid output = no Estrutura, never a trimmed one.

What text reaches the model: the video's caption, transcript, stored gancho/blueprint and the active block-type
catalogue -- all fenced (see ``prompts/estruturas_derivacao``). No profile handle, no person name field, no URL, no
org/user id, no image. The reply is data: the server attaches ids, provenance, origem and status.

The service is synchronous in its DB access (PostgREST + RPC) and async only around the model call.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

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
from noctusai_lib.integrations.prompt_registry import RegistroIAIndisponivel, chamar_ia

from app.modules.media_creation import saida_ia_estruturas as saida
from app.modules.media_creation.estruturas_tipos_bloco import NOME_OUTRO
from app.modules.media_creation.prompts import estruturas_derivacao as prompt
from app.modules.media_creation.saida_ia import SaidaIaFalha
from app.modules.media_creation.services import biblioteca_fonte, biblioteca_optout
from app.modules.media_creation.services.estruturas_service import (
    EstruturaError,
    coded,
    mapear_erro_rpc,
)

logger = logging.getLogger(__name__)

ESTRUTURAS = "cs_estruturas"
TIPOS = "cs_estrutura_tipos_bloco"
VIRAIS = "cs_virais"
PERFIS = "cs_perfis_monitorados"

VIRAL_COLS = "id,perfil_id,caption,transcricao_texto,gancho,blueprint,media_type,media_product_type"
FEATURE = "estruturas.derivacao"

#: Every exception meaning "the money gate refused or could not verify" (fail closed).
ERROS_ORCAMENTO: tuple[type[BaseException], ...] = (
    LLMBudgetExceeded, LLMBudgetUnverifiable, LLMBudgetNotConfigured, SpendCeilingExceeded, SpendCeilingUnverifiable,
    LLMCreditsExhausted, LLMCreditsUnverifiable,
    ProviderQuotaExhausted,  # the provider account itself is out of credit: permanent until topped up, never retried
)

# ── stable codes (the job handler and the router both read them) ─────────────────────────────────────────────
VIRAL_NAO_ENCONTRADO = "viral_nao_encontrado"
VIRAL_SEM_CONTEUDO = "viral_sem_conteudo"
VIRAL_JA_TEM_RASCUNHO = "viral_ja_tem_rascunho"
VIRAL_JA_TEM_ESTRUTURA = "viral_ja_tem_estrutura"
PERFIL_OPTOUT = "perfil_optout"
SEM_ORG = biblioteca_fonte.CODIGO_SEM_ORG
ORCAMENTO = "orcamento_ia_excedido"
IA_INDISPONIVEL = "ia_indisponivel"
IA_NAO_CONFIGURADA = "ia_nao_configurada"
IA_FALHOU = "ia_falhou"
SAIDA_INVALIDA = "saida_ia_invalida"
LIMITE_DIARIO = "limite_diario_autodraft"
CATALOGO_INVALIDO = "catalogo_sem_outro"

ORIGEM_AUTO = "viral_auto"
ORIGEM_MANUAL = "manual"
PROVENIENCIA = "ia_sugerido"


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


def default_ports() -> IaPorts:
    from app.config import settings
    from app.dependencies import get_admin_client

    db = get_admin_client()
    if db is None:
        raise RuntimeError("estruturas_ia: sem cliente admin do Supabase")
    return IaPorts(
        db=db,
        ingestao_org=lambda: biblioteca_fonte.read_ingestao_org(default=settings.corestudio_biblioteca_org_id),
        ingestao_user=lambda: biblioteca_fonte.read_ingestao_user(default=settings.corestudio_biblioteca_user_id),
        cfg=settings,
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


# ── reads ────────────────────────────────────────────────────────────────────────────────────────────────────


def carregar_viral(db: Any, viral_id: str) -> dict[str, Any]:
    rows = db.table(VIRAIS).select(VIRAL_COLS).eq("id", str(viral_id)).execute().data
    if not rows:
        raise coded(404, VIRAL_NAO_ENCONTRADO, "Vídeo não encontrado.")
    return rows[0]


def estruturas_do_viral(db: Any, viral_id: str) -> list[dict[str, Any]]:
    return db.table(ESTRUTURAS).select("id,status,origem").eq("viral_id", str(viral_id)).execute().data or []


def ja_tem_estrutura(db: Any, viral_id: str) -> bool:
    """Any NON-archived Estrutura links the video (the auto-draft's idempotency check)."""
    return any(r.get("status") != "arquivada" for r in estruturas_do_viral(db, viral_id))


def contar_autodrafts_do_dia(db: Any, agora: datetime) -> int:
    res = (
        db.table(ESTRUTURAS).select("id", count="exact").eq("origem", ORIGEM_AUTO)
        .gte("created_at", inicio_do_dia(agora).isoformat()).limit(1).execute()
    )
    return res.count if getattr(res, "count", None) is not None else len(res.data or [])


def tipos_ativos(db: Any) -> list[dict[str, Any]]:
    return (
        db.table(TIPOS).select("id,nome,ordem,instrucao_referencia,sistema").eq("ativo", True).order("ordem").execute().data or []
    )


# ── the derivation ───────────────────────────────────────────────────────────────────────────────────────────


def _erro_ia(exc: BaseException) -> EstruturaError:
    if isinstance(exc, ERROS_ORCAMENTO):
        return coded(503, ORCAMENTO, "O orçamento de IA da organização de ingestão foi atingido.")
    if isinstance(exc, RegistroIAIndisponivel):
        return coded(503, IA_INDISPONIVEL, "A IA de estruturas não está disponível no momento.")
    if isinstance(exc, LLMNotConfigured):
        return coded(503, IA_NAO_CONFIGURADA, "A IA não está configurada para a organização de ingestão.")
    return coded(502, IA_FALHOU, "A IA não respondeu. Tente de novo em instantes.")


async def derivar(ports: IaPorts, viral: dict[str, Any], tipos: list[dict[str, Any]], org_id: str) -> saida.EstruturaDerivada:
    """One model call + strict validation. Raises :class:`EstruturaError` (``ia_*``, ``orcamento_ia_excedido``) or
    ``saida_ia_invalida`` carrying the failure ``codigo`` + ``campo`` (never the model's text)."""
    mensagem = prompt.build_user_message(
        legenda=viral.get("caption"), transcricao=viral.get("transcricao_texto"), gancho=viral.get("gancho"),
        blueprint=viral.get("blueprint"), formato_sugerido=formato_sugerido(viral),
        tipos=[(t["nome"], t.get("instrucao_referencia")) for t in tipos if not t.get("sistema")],
    )
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
    try:
        return saida.validar_derivacao(
            resposta.texto, tipos=[t["nome"] for t in tipos if not t.get("sistema")],
            fontes=(viral.get("caption"), viral.get("transcricao_texto"), viral.get("gancho"), viral.get("blueprint")),
        )
    except SaidaIaFalha as exc:
        # content-free by construction: the code and the field name only, never the model's text
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
            logger.exception("estruturas_ia: cs_estrutura_criar falhou")
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
    :data:`VIRAL_JA_TEM_ESTRUTURA` (409), the UTC-day cap applies (:data:`LIMITE_DIARIO`, 429). ``origem='manual'``
    (the admin endpoint): only an existing non-archived ``viral_auto`` blocks (:data:`VIRAL_JA_TEM_RASCUNHO`, 409,
    contract 6.2)."""
    org_id = ports.ingestao_org()
    if not org_id:
        raise coded(503, SEM_ORG, biblioteca_fonte.MSG_SEM_ORG)
    viral = carregar_viral(ports.db, viral_id)
    if not tem_conteudo(viral):
        raise coded(422, VIRAL_SEM_CONTEUDO, "Este vídeo ainda não tem conteúdo para gerar uma estrutura.")
    perfil = ports.db.table(PERFIS).select("id,handle").eq("id", str(viral["perfil_id"])).execute().data
    if not perfil:
        raise coded(404, VIRAL_NAO_ENCONTRADO, "Vídeo não encontrado.")
    if biblioteca_optout.esta_bloqueado(ports.db, perfil[0]["handle"]):
        raise coded(409, PERFIL_OPTOUT, "Este criador pediu para não ser monitorado.")
    existentes = estruturas_do_viral(ports.db, viral_id)
    if origem == ORIGEM_AUTO:
        if any(r.get("status") != "arquivada" for r in existentes):
            raise coded(409, VIRAL_JA_TEM_ESTRUTURA, "Este vídeo já tem uma estrutura.")
        # An ARCHIVED viral_auto still owns the one-per-video unique key: a second auto-draft would be refused by the
        # database; say so up front instead of spending a model call.
        if any(r.get("origem") == ORIGEM_AUTO for r in existentes):
            raise coded(409, VIRAL_JA_TEM_RASCUNHO, "Este vídeo já tem uma estrutura automática.")
        if contar_autodrafts_do_dia(ports.db, ports.clock()) >= int(ports.cfg.estruturas_autodraft_dia):
            raise coded(429, LIMITE_DIARIO, "Limite diário de estruturas automáticas atingido.")
    elif any(r.get("origem") == ORIGEM_AUTO and r.get("status") != "arquivada" for r in existentes):
        raise coded(409, VIRAL_JA_TEM_RASCUNHO, "Este vídeo já tem uma estrutura automática.")

    tipos = tipos_ativos(ports.db)
    tipo_ids = {t["nome"]: str(t["id"]) for t in tipos}
    if NOME_OUTRO not in tipo_ids:
        raise coded(503, CATALOGO_INVALIDO, "O catálogo de tipos de bloco não tem o tipo \"Outro\".")
    derivada = await derivar(ports, viral, tipos, str(org_id))
    payload = montar_payload(derivada, viral, tipo_ids, origem=origem, ator_id=ator_id, ator_tipo=ator_tipo)
    return _rpc_criar(ports.db, payload)


__all__ = [
    "CATALOGO_INVALIDO", "ERROS_ORCAMENTO", "IA_FALHOU", "IA_INDISPONIVEL", "IA_NAO_CONFIGURADA", "IaPorts", "LIMITE_DIARIO",
    "ORCAMENTO", "ORIGEM_AUTO", "ORIGEM_MANUAL", "PERFIL_OPTOUT", "SAIDA_INVALIDA", "SEM_ORG", "VIRAL_JA_TEM_ESTRUTURA",
    "VIRAL_JA_TEM_RASCUNHO", "VIRAL_NAO_ENCONTRADO", "VIRAL_SEM_CONTEUDO", "carregar_viral", "contar_autodrafts_do_dia",
    "criar_rascunho", "default_ports", "derivar", "estruturas_do_viral", "formato_sugerido", "ja_tem_estrutura",
    "montar_payload", "tem_conteudo", "tipos_ativos",
]
