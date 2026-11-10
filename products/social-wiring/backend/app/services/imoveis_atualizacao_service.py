"""One Vista imóveis refresh RUN for one org: pick the path, run it under a single-flight lock, persist the report.

Strategy (`modo="auto"`, what the 2-hourly schedule and "Atualizar agora" use): try `listar` first; if Vista's `listar`
is silent while the mirror holds the catalog (`status=listar_vazio`, 2026-10-23 on), fall back to the per-code refresh
(`ImovelSyncService.sync_detalhes`) -- NOT silently: the persisted report names the path that ran, the call counts, and
the first such run of a day raises ONE in-app notice to the org admins. The day `listar` answers again the auto path uses
it (≈ total/50 calls) and the per-code walk stops by itself.

Every run is one row of `social_wiring.imoveis_sync_execucoes` (migration 316): `em_andamento` while it runs (the marker
the manual button polls and a second click re-uses), then its status, path and `relatorio`. Single flight per org:
the DB lease `imoveis_vista_sync:<org>` (cross-process) + the `em_andamento` row (a click while a run is going returns the
running one).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.domain.notifications import write_in_app

from app.services import sync_lease
from app.services.imoveis_service import SyncReport, build_sync_service

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"
_TABLE = "imoveis_sync_execucoes"
MODOS = ("auto", "listar", "detalhes")
ESCOPOS = ("vitrine", "resto", "todos")
#: A run that says `em_andamento` for longer than this crashed (the lease TTL is shorter): it no longer blocks anything.
EM_ANDAMENTO_MAX = timedelta(hours=2)
LEASE_TTL_S = 7200
KIND_AVISO = "imoveis_vista_listar_vazio"
AVISO_TITULO = "Vista não está listando imóveis"
AVISO_MENSAGEM = (
    "O Vista não está listando imóveis — atualização feita imóvel a imóvel. A lista continua sendo atualizada, "
    "mas novos imóveis só aparecem se forem encontrados pela sonda de códigos."
)


def lease_name(org_id: Any) -> str:
    return f"imoveis_vista_sync:{org_id}"


def _tabela(client: Any):
    return client.schema(_SCHEMA).table(_TABLE)


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def execucao_em_andamento(client: Any, org_id: Any) -> Optional[dict]:
    corte = (_agora() - EM_ANDAMENTO_MAX).isoformat()
    rows = (
        _tabela(client).select("*").eq("org_id", str(org_id)).eq("status", "em_andamento").gte("iniciado_em", corte)
        .order("iniciado_em", desc=True).limit(1).execute().data or []
    )
    return rows[0] if rows else None


def ultima_execucao(client: Any, org_id: Any) -> Optional[dict]:
    rows = (
        _tabela(client).select("*").eq("org_id", str(org_id)).order("iniciado_em", desc=True).limit(1).execute().data or []
    )
    return rows[0] if rows else None


def _resto_vencido(client: Any, org_id: Any, intervalo_s: int) -> bool:
    """Is the daily pass over the rest of the catalog (sold / suspended / hidden / removed) due? True when no per-code run
    with a `resto`/`todos` scope finished within `intervalo_s`."""
    corte = (_agora() - timedelta(seconds=intervalo_s)).isoformat()
    rows = (
        _tabela(client).select("id").eq("org_id", str(org_id)).eq("caminho", "detalhes").in_("escopo", ["resto", "todos"])
        .in_("status", ["ok", "incompleto"]).gte("iniciado_em", corte).limit(1).execute().data or []
    )
    return not rows


def escopo_do_agendamento(client: Any, org_id: Any, intervalo_resto_s: int) -> str:
    """Scheduled runs refresh the vitrine; once per `intervalo_resto_s` they also sweep the rest (`todos`)."""
    return "todos" if _resto_vencido(client, org_id, intervalo_resto_s) else "vitrine"


def iniciar(client: Any, org_id: Any, *, origem: str, modo: str, escopo: Optional[str], user_id: Optional[str]) -> tuple[dict, bool]:
    """Open the run row. `(row, False)` when a run is already going (single flight: that one is returned instead)."""
    atual = execucao_em_andamento(client, org_id)
    if atual is not None:
        return atual, False
    row = {"org_id": str(org_id), "origem": origem, "modo": modo, "escopo": escopo, "status": "em_andamento",
           "iniciado_por": str(user_id) if user_id else None, "iniciado_em": _agora().isoformat()}
    criado = _tabela(client).insert(row).execute().data
    return (criado[0] if criado else row), True


def _fechar(client: Any, execucao_id: Any, *, status: str, caminho: Optional[str], relatorio: dict, aviso: bool = False) -> None:
    _tabela(client).update({
        "status": status, "caminho": caminho, "finalizado_em": _agora().isoformat(), "relatorio": relatorio,
        "aviso_listar_vazio": aviso,
    }).eq("id", str(execucao_id)).execute()


def avisar_listar_vazio(client: Any, core: Any, org_id: Any) -> bool:
    """Raise the in-app notice to the org admins unless one already went out in the last 24h. Returns True when sent."""
    corte = (_agora() - timedelta(hours=24)).isoformat()
    ja = (
        _tabela(client).select("id").eq("org_id", str(org_id)).eq("aviso_listar_vazio", True).gte("iniciado_em", corte)
        .limit(1).execute().data or []
    )
    if ja or core is None:
        return False
    from app.services.julia_notificacoes_service import admins_da_org

    try:
        admins = admins_da_org(core, org_id)
        if not admins:
            raise RuntimeError("sem_destinatarios")
        write_in_app(
            core, user_ids=admins, kind=KIND_AVISO, org_id=org_id, title=AVISO_TITULO, message=AVISO_MENSAGEM,
            metadata={"product": "social-wiring", "link": "/imoveis"},
        )
    except Exception as exc:
        logger.error("imoveis refresh: the 'listar vazio' notice failed org=%s (%s)", org_id, type(exc).__name__)
        return False
    return True


async def _digest_de_divergencias(client: Any, core: Any, org: UUID, execucao_id: Any, report: Any, relatorio: dict, enviar: Any) -> None:
    """TRANSITIONAL (`vista_divergencias`): ONE digest per run for the divergences it opened. Never raises."""
    linhas = getattr(report, "divergencias_linhas", None) or []
    if not linhas:
        return
    try:
        from app.config import settings
        from app.services import vista_divergencias

        db = client.schema(_SCHEMA)
        relatorio["divergencias_digest"] = await vista_divergencias.enviar_digest(
            db, core, org, linhas, enviar=enviar or vista_divergencias.enviador_padrao(db),
            base_url=(settings.frontend_base_url or "").rstrip("/"),
        )
        _tabela(client).update({"relatorio": relatorio}).eq("id", str(execucao_id)).execute()
    except Exception as exc:
        logger.error("imoveis refresh: the divergence digest failed org=%s (%s)", org, type(exc).__name__)


#: Run statuses that are NOT a failure the owner must hear about (`listar_vazio` has its own daily notice).
_STATUS_SEM_AVISO = ("ok", "listar_vazio")


def _status_anterior(client: Any, org: UUID) -> Optional[str]:
    """The previous finished run's status (the current one is already closed, so it is row 0) — the failure warning
    fires on the TRANSITION into a bad status, not on every 2-hourly repeat of it."""
    rows = (
        _tabela(client).select("status").eq("org_id", str(org)).neq("status", "em_andamento")
        .order("iniciado_em", desc=True).limit(2).execute().data or []
    )
    return rows[1].get("status") if len(rows) > 1 else None


async def _avisar_dono(
    client: Any, org: UUID, status: str, report: Any, relatorio: dict, notificador: Any, *, aviso_listar_vazio: bool = False,
) -> None:
    """WhatsApp the owner what this run did that he asked to hear about (owner, 2026-11-09): properties that left Vista,
    and a run that did not end ok. Through the scripted notification system (`NotificationService`, catalog-gated, so
    each switch lives on core's Notificações page). Never raises: the run is already persisted."""
    try:
        if notificador is None:
            from app.services.notification_service import build_notification_service

            notificador = build_notification_service(client)
        if aviso_listar_vazio:
            await notificador.notify_imoveis_listar_vazio(org_id=org, texto=AVISO_MENSAGEM)
        pausados = list(getattr(report, "pausados_codigos", None) or [])
        codigos = list(dict.fromkeys(
            [c.strip().upper() for c in (getattr(report, "removidos_codigos", None) or [])] + pausados))
        if codigos:
            await notificador.notify_imoveis_delistados(
                org_id=org, codigos=codigos, exclusivos=list(getattr(report, "removidos_exclusivos", None) or []),
                pausados=pausados,
            )
        novos_vista = list(getattr(report, "novos_vista_codigos", None) or [])
        if novos_vista:
            await notificador.notify_imoveis_novos_vista(org_id=org, codigos=novos_vista)
        if status not in _STATUS_SEM_AVISO and _status_anterior(client, org) != status:
            motivo = relatorio.get("erro") or relatorio.get("motivo")
            await notificador.notify_imoveis_sync_falhou(org_id=org, status=status, motivo=motivo)
    except Exception as exc:  # noqa: BLE001 — loud, never breaks the run
        logger.error("imoveis refresh: the owner WhatsApp warning failed org=%s (%s)", org, type(exc).__name__,
                     exc_info=True)


async def executar(
    client: Any,
    adapter: Any,
    org_id: Any,
    *,
    modo: str = "auto",
    escopo: str = "vitrine",
    origem: str = "agendado",
    user_id: Optional[str] = None,
    execucao_id: Optional[str] = None,
    core: Any = None,
    sync_factory: Optional[Callable[..., Any]] = None,
    sonda_max_falhas: int = 40,
    lease_fn: Any = None,
    enviar_divergencia: Any = None,
    notificador: Any = None,
) -> dict:
    """Run one refresh and return the persisted report row (`status`, `caminho`, `relatorio`)."""
    if modo not in MODOS or escopo not in ESCOPOS:
        raise ValueError(f"modo {modo!r} / escopo {escopo!r} invalid")
    org = UUID(str(org_id))
    if execucao_id is None:
        linha, nova = iniciar(client, org, origem=origem, modo=modo, escopo=escopo, user_id=user_id)
        if not nova:
            return linha
        execucao_id = linha["id"]

    build = sync_factory or build_sync_service
    servico = build(client, adapter, sonda_max_falhas=sonda_max_falhas)
    status, caminho, relatorio, aviso = "falhou", None, {}, False
    report: Optional[SyncReport] = None
    with (lease_fn or sync_lease.lease)(client, lease_name(org), ttl_seconds=LEASE_TTL_S) as adquirido:
        if not adquirido:
            _fechar(client, execucao_id, status="ignorada", caminho=None, relatorio={"motivo": "outro processo já está atualizando"})
            return {"id": str(execucao_id), "status": "ignorada"}
        try:
            listar_vazio = False
            if modo in ("auto", "listar"):
                report = await servico.sync(org)
                caminho = "listar"
                if report.status_final == "listar_vazio" and modo == "auto":
                    listar_vazio = True
                    aviso = avisar_listar_vazio(client, core, org)
                    relatorio["listar"] = {"status": "listar_vazio", "chamadas": dict(report.chamadas)}
            if modo == "detalhes" or listar_vazio:
                report = await servico.sync_detalhes(org, escopo=escopo)
                caminho = "detalhes"
            relatorio = {**relatorio, **report.as_dict()}
            status = report.status_final
        except Exception as exc:
            logger.error("imoveis refresh failed org=%s (%s)", org, type(exc).__name__, exc_info=True)
            relatorio = {**relatorio, "erro": type(exc).__name__}
            status = "falhou"
        _fechar(client, execucao_id, status=status, caminho=caminho, relatorio=relatorio, aviso=aviso)
    await _digest_de_divergencias(client, core, org, execucao_id, report, relatorio, enviar_divergencia)
    await _avisar_dono(client, org, status, report, relatorio, notificador, aviso_listar_vazio=aviso)
    return {"id": str(execucao_id), "status": status, "caminho": caminho, "relatorio": relatorio}


__all__ = [
    "AVISO_MENSAGEM", "ESCOPOS", "MODOS", "escopo_do_agendamento", "execucao_em_andamento", "executar", "iniciar",
    "lease_name", "ultima_execucao",
]
