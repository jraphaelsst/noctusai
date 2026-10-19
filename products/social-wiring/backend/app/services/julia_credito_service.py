"""Lais wave 13 -- Analise de credito (contract section 15, LGPD section 17).

Flow (aluguel only, at the visit step -- composes wave 5, never forks it):

  contexto        `estado.credito = {ativo, consentimento: null|true|false}` while the analysis applies to the
                  contato (org config ativo + aluguel), and `consentimento_credito` joins `acoes` unless the lead
                  already consented (an additive `ACOES_EXTRAS` entry).
  action          `consentimento_credito{aceito}` -> `lais_credito_consentimentos` (append-only; latest wins).
                  aceito=true with a live visit -> start the analysis.
  pedido_visita   a POS_ACAO hook on the wave-5 handler: visit stored + consent already true -> start the analysis;
                  no consent yet -> nothing (the contexto makes Julia ask; the consent action then starts it).
  analysis        a `lais_credito_analises` row (pendente) + a seed job; at fire time the job re-checks the LATEST
                  consent is the same row and still aceito=true (stale guard -- NOT `gen`, which every inbound bumps),
                  then calls the provider and stores `status` + a one-sentence `resumo`. Emits `credito_analisado`.

THE invariant: the provider is NEVER called without a stored consent aceito=true -- enforced three times: the
starter refuses, the job re-checks, and the table can only hold an analysis behind an accepted consent (composite
FK, migration 281). A refused consent is stored and nothing else happens.

Routes live in `lais_credito_router`. Visibility (A7) follows the contato (`lais_acesso`).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from uuid import UUID, uuid4

from noctusai_lib.domain.jobs import Job
from noctusai_lib.integrations.persistence.paging import iter_paged_rows
from noctusai_lib.primitives.exceptions import AppException

from app.services import lais_acesso, lais_acoes_service, lais_contexto_service
from app.services import lais_eventos_service as eventos
from app.services.lais_credito_provider import (
    PROVIDERS_CONHECIDOS, RESUMO_MAX, ConsultaCredito, CreditoNaoConfigurado, CreditoProvider, CreditoProviderErro,
    credencial_da_org, make_credito_provider,
)

logger = logging.getLogger(__name__)

T_CONFIG = "lais_credito_config"
T_CONSENT = "lais_credito_consentimentos"
T_ANALISES = "lais_credito_analises"
T_CONTATOS = "lais_contatos"
T_VISITAS = "lais_visitas"
STATUS = ("pendente", "aprovado", "reprovado", "erro")
PAGE_SIZES = (5, 10, 15, 20)
ACAO_CONSENTIMENTO = "consentimento_credito"
#: the wording version the prompt asks consent with; bump it whenever the asked text changes materially
TEXTO_VERSAO = "2026-10-v1"
JOB_ANALISE = "lais_credito_analise"
JOB_MAX_RETRIES = 1
VISITAS_VIVAS = ("solicitada", "confirmada", "remarcada")
CONFIG_PADRAO: dict[str, Any] = {"ativo": False, "provider": None, "apenas_aluguel": True}

_client_provider: Optional[Callable[[], Any]] = None
_repo: Any = None
_provider_factory: Optional[Callable[[Any, dict[str, Any]], CreditoProvider]] = None


def registrar_client_provider(fn: Optional[Callable[[], Any]]) -> None:
    global _client_provider
    _client_provider = fn


def registrar_repo(repo: Any) -> None:
    global _repo
    _repo = repo


def registrar_provider_factory(fn: Optional[Callable[[Any, dict[str, Any]], CreditoProvider]]) -> None:
    """DI seam: `fn(org_id, config) -> CreditoProvider` (tests inject a Fake; production resolves per org)."""
    global _provider_factory
    _provider_factory = fn


def _client() -> Any:
    if _client_provider is not None:
        return _client_provider()
    from app.dependencies import get_scoped_admin_client

    return get_scoped_admin_client("social_wiring")


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolver_provider(org_id: Any, config: dict[str, Any]) -> CreditoProvider:
    """The org's provider: the injected factory, else the real resolution (config name + per-org credential)."""
    if _provider_factory is not None:
        return _provider_factory(org_id, config)
    from noctusai_lib.config.deploy_config import is_deploy_context

    nome = config.get("provider")
    return make_credito_provider(
        nome, credencial=credencial_da_org(org_id) if nome and nome != "fake" else None, allow_fake=not is_deploy_context(),
    )


# -- config ---------------------------------------------------------------------------
def ler_config(client: Any, org_id: UUID | str) -> dict[str, Any]:
    rows = client.table(T_CONFIG).select("*").eq("org_id", str(org_id)).limit(1).execute().data or []
    if not rows:
        return dict(CONFIG_PADRAO)
    r = rows[0]
    return {"ativo": bool(r.get("ativo")), "provider": r.get("provider"), "apenas_aluguel": bool(r.get("apenas_aluguel", True))}


def salvar_config(client: Any, org_id: UUID | str, *, ativo: bool, provider: Optional[str], apenas_aluguel: bool) -> dict[str, Any]:
    if provider is not None and provider not in PROVIDERS_CONHECIDOS:
        raise AppException("provider_invalido", "Provedor de crédito desconhecido.", status_code=422,
                           details={"validos": list(PROVIDERS_CONHECIDOS)})
    if ativo and not provider:
        raise AppException("provider_obrigatorio", "Escolha um provedor antes de ativar a análise de crédito.", status_code=422)
    corpo = {"org_id": str(org_id), "ativo": ativo, "provider": provider, "apenas_aluguel": apenas_aluguel, "updated_at": _agora()}
    client.table(T_CONFIG).upsert(corpo, on_conflict="org_id").execute()
    return {"ativo": ativo, "provider": provider, "apenas_aluguel": apenas_aluguel}


def aplica(config: dict[str, Any], contato: dict[str, Any]) -> bool:
    """The analysis applies to this contato: org switch on AND (aluguel, unless the org lifted that limit)."""
    if not config.get("ativo"):
        return False
    return (contato.get("operacao") == "aluguel") if config.get("apenas_aluguel", True) else True


# -- consent --------------------------------------------------------------------------
def consentimento_atual(client: Any, contato_id: UUID | str) -> Optional[dict[str, Any]]:
    """The LATEST consent row of the contato (registrado_at, then id), or None -- never asked / answered."""
    rows = client.table(T_CONSENT).select("*").eq("contato_id", str(contato_id)).execute().data or []
    if not rows:
        return None
    return max(rows, key=lambda r: (str(r.get("registrado_at") or ""), str(r.get("id"))))


def consentimento_estado(client: Any, contato_id: UUID | str) -> Optional[bool]:
    atual = consentimento_atual(client, contato_id)
    return None if atual is None else bool(atual["aceito"])


def registrar_consentimento(client: Any, org_id: UUID | str, contato_id: UUID | str, aceito: bool) -> dict[str, Any]:
    linha = {
        "id": str(uuid4()), "org_id": str(org_id), "contato_id": str(contato_id), "aceito": bool(aceito),
        "registrado_at": _agora(), "texto_versao": TEXTO_VERSAO,
    }
    res = client.table(T_CONSENT).insert(linha).execute().data or []
    return res[0] if res else linha


# -- contexto -------------------------------------------------------------------------
def _estado_extra(ctx: lais_contexto_service.ContextoCtx) -> dict[str, Any]:
    """`estado.credito` while the analysis applies to the contato (absent otherwise: the agent sees nothing)."""
    if not aplica(ler_config(ctx.client, ctx.org_id), ctx.contato):
        return {}
    return {"credito": {"ativo": True, "consentimento": consentimento_estado(ctx.client, ctx.contato["id"])}}


def _acoes_extra(ctx: lais_contexto_service.ContextoCtx) -> list[str]:
    """`consentimento_credito` is offered while the analysis applies and the lead has not already consented."""
    if not aplica(ler_config(ctx.client, ctx.org_id), ctx.contato):
        return []
    return [] if consentimento_estado(ctx.client, ctx.contato["id"]) is True else [ACAO_CONSENTIMENTO]


# -- the analysis ---------------------------------------------------------------------
def _visita_viva(client: Any, contato_id: UUID | str) -> Optional[dict[str, Any]]:
    rows = [r for r in (client.table(T_VISITAS).select("*").eq("contato_id", str(contato_id)).execute().data or [])
            if r.get("status") in VISITAS_VIVAS]
    return max(rows, key=lambda r: str(r.get("created_at") or r.get("inicio") or "")) if rows else None


def _analises_do_contato(client: Any, contato_id: UUID | str) -> list[dict[str, Any]]:
    return client.table(T_ANALISES).select("*").eq("contato_id", str(contato_id)).execute().data or []


def _nova_analise(client: Any, org_id: UUID | str, contato_id: Any, consentimento: dict[str, Any], provider: Optional[str]) -> dict[str, Any]:
    linha = {
        "id": str(uuid4()), "org_id": str(org_id), "contato_id": str(contato_id), "consentimento_id": str(consentimento["id"]),
        "consentimento_aceito": True, "provider": provider or "desconhecido", "status": "pendente", "resumo": None,
        "created_at": _agora(), "updated_at": _agora(),
    }
    res = client.table(T_ANALISES).insert(linha).execute().data or []
    return res[0] if res else linha


async def _enfileirar(client: Any, org_id: UUID | str, contato: dict[str, Any], analise: dict[str, Any]) -> str:
    """Queue the run on the Lais worker's repository; with no repository (worker off) run it inline -- the
    analysis must not rot in `pendente`. Returns how it went: `enfileirada` | `executada`."""
    if _repo is None:
        logger.warning("lais credito: no job repository (worker off) -- running analise=%s inline", analise["id"])
        await executar_analise(client, org_id, analise["id"])
        return "executada"
    await _repo.enqueue(
        type=JOB_ANALISE,
        payload={"org_id": str(org_id), "contato_id": str(contato["id"]), "analise_id": str(analise["id"]),
                 "consentimento_id": str(analise["consentimento_id"])},
        max_retries=JOB_MAX_RETRIES, scheduled_for=datetime.now(timezone.utc),
        dedupe_key=f"lais:credito:{analise['id']}",
    )
    return "enfileirada"


async def iniciar(client: Any, org_id: UUID | str, contato: dict[str, Any], *, forcar: bool = False) -> dict[str, Any]:
    """Start the analysis for `contato` when every precondition holds. Returns `{iniciada, motivo?, analise_id?}`.

    Preconditions, each refused WITHOUT calling anything: org config applies (ativo + aluguel), the LATEST consent
    is aceito=true, and (unless `forcar`, the admin reprocess) there is a live visit and no analysis for that consent yet."""
    config = ler_config(client, org_id)
    if not aplica(config, contato):
        return {"iniciada": False, "motivo": "nao_se_aplica"}
    consentimento = consentimento_atual(client, contato["id"])
    if consentimento is None or consentimento.get("aceito") is not True:
        return {"iniciada": False, "motivo": "sem_consentimento"}
    if not forcar:
        if _visita_viva(client, contato["id"]) is None:
            return {"iniciada": False, "motivo": "sem_visita"}
        if any(str(a["consentimento_id"]) == str(consentimento["id"]) for a in _analises_do_contato(client, contato["id"])):
            return {"iniciada": False, "motivo": "ja_analisada"}
    analise = _nova_analise(client, org_id, contato["id"], consentimento, config.get("provider"))
    como = await _enfileirar(client, org_id, contato, analise)
    return {"iniciada": True, "analise_id": str(analise["id"]), "como": como}


def _resumo(texto: Any) -> Optional[str]:
    if not isinstance(texto, str):
        return None
    return " ".join(texto.split())[:RESUMO_MAX] or None


def _finalizar(client: Any, org_id: UUID | str, analise: dict[str, Any], status: str, resumo: Optional[str]) -> str:
    client.table(T_ANALISES).update({"status": status, "resumo": _resumo(resumo), "updated_at": _agora()}) \
        .eq("org_id", str(org_id)).eq("id", str(analise["id"])).execute()
    eventos.emitir(client, org_id, "credito_analisado", analise["contato_id"], {"analise_id": str(analise["id"]), "status": status})
    return status


async def executar_analise(client: Any, org_id: UUID | str, analise_id: UUID | str) -> str:
    """Fire time. Outcome: `ja_processada | obsoleto | politica_desligada | aprovado | reprovado | pendente | erro`.

    The stale guard is the CONSENT, not `gen`: the job dies as `obsoleto` unless the contato still exists and its
    latest consent is the very row the analysis was created from and is still aceito=true."""
    rows = client.table(T_ANALISES).select("*").eq("org_id", str(org_id)).eq("id", str(analise_id)).limit(1).execute().data or []
    if not rows:
        return "obsoleto"
    analise = rows[0]
    if analise.get("status") != "pendente":
        return "ja_processada"
    contato_rows = client.table(T_CONTATOS).select("*").eq("org_id", str(org_id)).eq("id", str(analise["contato_id"])).limit(1).execute().data or []
    if not contato_rows:
        return "obsoleto"
    contato = contato_rows[0]
    atual = consentimento_atual(client, contato["id"])
    if atual is None or atual.get("aceito") is not True or str(atual["id"]) != str(analise["consentimento_id"]):
        return "obsoleto"  # revoked or superseded since the job was queued: the provider is never called
    config = ler_config(client, org_id)
    if not aplica(config, contato):
        return "politica_desligada"
    visita = _visita_viva(client, contato["id"])
    consulta = ConsultaCredito(
        org_id=str(org_id), contato_id=str(contato["id"]), nome=contato.get("nome"), telefone_e164=contato.get("telefone_e164"),
        operacao=contato.get("operacao"), codigo_imovel=(visita or {}).get("codigo_imovel"),
    )
    try:
        provider = resolver_provider(org_id, config)
        resultado = await provider.analisar(consulta)
    except CreditoNaoConfigurado as exc:
        logger.warning("lais credito: provider not configured (org=%s): %s", org_id, exc.motivo)
        return _finalizar(client, org_id, analise, "erro", exc.motivo)
    except CreditoProviderErro:
        logger.exception("lais credito: provider failed (org=%s analise=%s)", org_id, analise["id"])
        return _finalizar(client, org_id, analise, "erro", "falha na consulta ao provedor")
    except Exception:
        logger.exception("lais credito: unexpected provider failure (org=%s analise=%s)", org_id, analise["id"])
        return _finalizar(client, org_id, analise, "erro", "falha na consulta ao provedor")
    return _finalizar(client, org_id, analise, resultado.status, resultado.resumo)


def handlers(*, client_provider: Optional[Callable[[], Any]] = None) -> dict[str, Callable[[Job], Any]]:
    """`{job type: handler}` merged into the Lais worker. The client is built at FIRE time."""

    async def _analise(job: Job) -> None:
        p = job.payload or {}
        if not (p.get("org_id") and p.get("analise_id")):
            logger.error("lais credito: job %s has no org/analise -- dropped", job.id)
            return
        outcome = await executar_analise((client_provider or _client)(), p["org_id"], p["analise_id"])
        logger.info("lais credito %s job=%s -> %s", JOB_ANALISE, job.id, outcome)

    return {JOB_ANALISE: _analise}


# -- action handler + hook ------------------------------------------------------------
async def _h_consentimento(ctx: lais_acoes_service.AcaoCtx, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    aceito = (payload or {}).get("aceito")
    if not isinstance(aceito, bool):
        return {"erro": "aceito_invalido"}
    if not aplica(ler_config(ctx.client, ctx.org_id), ctx.contato):
        return {"erro": "nao_se_aplica"}
    registrar_consentimento(ctx.client, ctx.org_id, ctx.contato["id"], aceito)
    if not aceito:
        return {"aceito": False}
    return {"aceito": True, **(await iniciar(ctx.client, ctx.org_id, ctx.contato))}


async def _pos_pedido_visita(ctx: lais_acoes_service.AcaoCtx, _payload: dict[str, Any], resultado: Optional[dict[str, Any]]) -> None:
    """After the wave-5 `pedido_visita` handler stored a visit: start the analysis if the lead already consented."""
    if not (resultado or {}).get("visita_id"):
        return
    await iniciar(ctx.client, ctx.org_id, ctx.contato)


def registrar() -> None:
    """Bind every registry slot wave 13 owns (idempotent); called once at import of the router."""
    lais_acoes_service.registrar_handler(ACAO_CONSENTIMENTO, _h_consentimento)
    lais_acoes_service.registrar_pos_acao("pedido_visita", _pos_pedido_visita)
    lais_contexto_service.registrar_estado_extra(_estado_extra)
    lais_contexto_service.registrar_acoes_extra(_acoes_extra)


# -- reads ----------------------------------------------------------------------------
def credito_por_contato(client: Any, org_id: UUID | str, contato_ids: list[str]) -> dict[str, dict[str, Any]]:
    """`{contato_id: {status, atualizado_at}}` of each contato's latest analysis (the Interacoes line)."""
    out: dict[str, dict[str, Any]] = {}
    for i in range(0, len(contato_ids), 200):
        rows = client.table(T_ANALISES).select("contato_id, status, updated_at, created_at") \
            .eq("org_id", str(org_id)).in_("contato_id", contato_ids[i:i + 200]).execute().data or []
        for r in rows:
            chave = str(r["contato_id"])
            stamp = str(r.get("created_at") or "")
            if chave not in out or stamp >= out[chave]["_ord"]:
                out[chave] = {"status": r["status"], "atualizado_at": r.get("updated_at"), "_ord": stamp}
    return {k: {"status": v["status"], "atualizado_at": v["atualizado_at"]} for k, v in out.items()}


def _serializar(a: dict[str, Any], contato: Optional[dict[str, Any]]) -> dict[str, Any]:
    c = contato or {}
    return {
        "id": a["id"], "contato_id": a["contato_id"], "provider": a["provider"], "status": a["status"], "resumo": a.get("resumo"),
        "created_at": a["created_at"], "updated_at": a.get("updated_at"),
        "contato": {"id": c.get("id"), "nome": c.get("nome"), "telefone_e164": c.get("telefone_e164"), "canal": c.get("canal")},
    }


def listar(client: Any, org_id: UUID | str, ctx: lais_acesso.AcessoCtx, *, status: Optional[str], page: int, page_size: int) -> dict[str, Any]:
    """`{items, total}`, newest first, A7-filtered (a member sees the analyses of their contatos only)."""
    def pagina(a: int, b: int) -> Any:
        q = client.table(T_ANALISES).select("*").eq("org_id", str(org_id))
        if status:
            q = q.eq("status", status)
        return q.order("id").range(a, b).execute().data

    todas = sorted(iter_paged_rows(pagina, label="lais credito"), key=lambda r: r["created_at"], reverse=True)
    linhas = lais_acesso.filtrar_por_contato(client, ctx, todas)
    fatia = linhas[(page - 1) * page_size: page * page_size]
    ids = sorted({str(r["contato_id"]) for r in fatia})
    contatos_por_id: dict[str, dict[str, Any]] = {}
    for i in range(0, len(ids), 200):
        for c in client.table(T_CONTATOS).select("id, nome, telefone_e164, canal").eq("org_id", str(org_id)).in_("id", ids[i:i + 200]).execute().data or []:
            contatos_por_id[str(c["id"])] = c
    return {"items": [_serializar(r, contatos_por_id.get(str(r["contato_id"]))) for r in fatia], "total": len(linhas)}


async def reprocessar(client: Any, org_id: UUID | str, contato_id: UUID | str) -> dict[str, Any]:
    """Admin: run a NEW analysis for the contato. Needs the stored consent (409 otherwise) -- never overrides it."""
    rows = client.table(T_CONTATOS).select("*").eq("org_id", str(org_id)).eq("id", str(contato_id)).limit(1).execute().data or []
    if not rows:
        raise AppException("contato_nao_encontrado", "Contato não encontrado.", status_code=404)
    contato = rows[0]
    if not ler_config(client, org_id).get("ativo"):
        raise AppException("credito_desativado", "A análise de crédito está desativada.", status_code=409)
    if consentimento_estado(client, contato["id"]) is not True:
        raise AppException("consentimento_ausente", "O cliente ainda não consentiu com a análise de crédito.", status_code=409)
    res = await iniciar(client, org_id, contato, forcar=True)
    if not res.get("iniciada"):
        raise AppException("credito_nao_se_aplica", "A análise de crédito não se aplica a este contato.", status_code=409)
    return {"analise_id": res["analise_id"], "como": res["como"]}


__all__ = [
    "ACAO_CONSENTIMENTO", "CONFIG_PADRAO", "JOB_ANALISE", "PAGE_SIZES", "STATUS", "TEXTO_VERSAO", "aplica",
    "consentimento_atual", "consentimento_estado", "credito_por_contato", "executar_analise", "handlers", "iniciar",
    "ler_config", "listar", "registrar", "registrar_client_provider", "registrar_consentimento", "registrar_provider_factory",
    "registrar_repo", "reprocessar", "resolver_provider", "salvar_config",
]
