"""In-app notifications for the agency — rows in core's `public.notifications`.

The seed's standard `notificacoes` router (mounted in `app/main.py`) already
READS this table for the bell; this is the write half. Same row shape as
social-wiring's `modules/edicao_fotos/services/notifier.py::_write_in_app`.
"""
from __future__ import annotations

# NOC-REMEDIATE[in-app-notification-writer]: second product hand-writing
# public.notifications rows (social-wiring edicao_fotos is the first; N=2 ->
# triage); the third lifts a noctusai_lib.domain.notifications writer. — 2026-09-23

import logging
from datetime import datetime, timezone
from typing import Any, Iterable

from noctusai_lib.integrations.persistence.table_reads import in_batched_rows, paged_rows
from noctusai_lib.primitives.roles import ADMIN_ROLES

from app.services.varredura import linhas_cross_org

logger = logging.getLogger(__name__)

__all__ = ["notificar", "processar_lembretes_pendentes"]


def notificar(
    core_client: Any,
    *,
    org_id: str,
    user_ids: Iterable[Any],
    tipo: str,
    titulo: str,
    mensagem: str,
    metadata: dict | None = None,
) -> int:
    """Insert one notification per distinct recipient. Returns how many.

    Raises on a failed insert — the CALLER decides whether a notification
    failure may fail its operation. Zero recipients is logged at WARNING: an
    event nobody hears about is worth seeing in the logs.
    """
    destinatarios = sorted({str(u) for u in user_ids if u})
    if not destinatarios:
        logger.warning("notificação %s sem destinatários org=%s", tipo, org_id)
        return 0
    core_client.table("notifications").insert(
        [
            {
                "user_id": uid,
                "org_id": org_id,
                "type": tipo,
                "title": titulo,
                "message": mensagem,
                "metadata": metadata or {},
            }
            for uid in destinatarios
        ]
    ).execute()
    return len(destinatarios)


def _usuarios_dos_membros(admin_db: Any, cfg: Any, org_id: str, entity_id: str) -> list[str]:
    """Linked-login users of a card's members — the same set the Geral
    subpage's "Membros" list shows (`igig.profissional.usuario_id`)."""
    links = paged_rows(
        admin_db, cfg.tables.membros, org_id,
        eq_filters={cfg.entity_fk: str(entity_id)},
        order_col=cfg.member_source.fk, id_key=cfg.member_source.fk,
    )
    membro_ids = [link[cfg.member_source.fk] for link in links]
    if not membro_ids:
        return []
    profissionais = in_batched_rows(admin_db, cfg.member_source.table, org_id, "id", membro_ids)
    return sorted({str(p["usuario_id"]) for p in profissionais if p.get("usuario_id")})


def _admins_da_org(core_client: Any, org_id: str) -> list[str]:
    linhas = (
        core_client.table("noctus_users").select("id").eq("org_id", org_id)
        .in_("org_role", list(ADMIN_ROLES)).execute().data or []
    )
    return [str(r["id"]) for r in linhas if r.get("id")]


#: `(config, notification type, title field, deep-link query param)` per
#: card hub this drain covers.
_LEMBRETE_ALVOS = (("cliente", "nome", "id"), ("negocio", "titulo", "negocio"))


def processar_lembretes_pendentes(admin_db: Any, core_client: Any) -> dict:
    """Deliver every DUE, undelivered card-hub reminder as an in-app
    notification — the drain `NOC-REMEDIATE[reminder-delivery]`
    (`noctusai_lib.domain.card_hub.lembretes`) names: rows were materialised
    correctly but nothing ever turned one into something a user saw (plat
    achado #9).

    Schedule-agnostic on purpose — `app/scheduler.py` owns the cadence and the
    admin/core clients; this is the plain unit of work it calls.

    Recipients: the card's members' linked-login users (Custos), falling back
    to the org's admins when nobody is linked (same last-line rule
    `automacoes._destinatarios` uses for an unowned SLA alert) — never a
    silent no-recipient drop. A reminder with genuinely nobody to tell (no
    members, no admins yet) is logged at WARNING and left PENDING, so it
    still fires once someone exists to receive it, instead of being marked
    sent and lost.

    Returns counts for the job log: `{processados, notificados,
    sem_destinatario, falhas}`. One reminder failing is isolated — the sweep
    continues, matching `automacoes.varrer_sla`'s per-rule isolation.
    """
    from app.card_hub import CARD_HUB_CLIENTE, CARD_HUB_NEGOCIO

    cfgs = {"cliente": CARD_HUB_CLIENTE, "negocio": CARD_HUB_NEGOCIO}
    agora = datetime.now(timezone.utc).isoformat()
    resumo = {"processados": 0, "notificados": 0, "sem_destinatario": 0, "falhas": 0}

    for entidade, campo_titulo, param in _LEMBRETE_ALVOS:
        cfg = cfgs[entidade]
        pendentes = linhas_cross_org(
            admin_db, cfg.tables.lembretes,
            filtros=lambda q: q.lte("dispara_em", agora).is_("enviado_em", "null").is_("cancelado_em", "null"),
            label=f"igig.{cfg.tables.lembretes} (lembretes pendentes)",
        )
        for lembrete in pendentes:
            resumo["processados"] += 1
            try:
                org_id = str(lembrete["org_id"])
                entity_id = str(lembrete[cfg.entity_fk])
                linhas = (
                    admin_db.table(cfg.entity_table).select(f"id, {campo_titulo}")
                    .eq("id", entity_id).eq("org_id", org_id).execute().data or []
                )
                nome = (linhas[0].get(campo_titulo) if linhas else None) or entidade
                destinatarios = _usuarios_dos_membros(admin_db, cfg, org_id, entity_id)
                if not destinatarios:
                    destinatarios = _admins_da_org(core_client, org_id)
                if not destinatarios:
                    resumo["sem_destinatario"] += 1
                    logger.warning(
                        "lembrete %s sem destinatário (sem membro vinculado, sem admin) org=%s "
                        "%s=%s", lembrete["id"], org_id, entidade, entity_id,
                    )
                    continue
                notificar(
                    core_client, org_id=org_id, user_ids=destinatarios,
                    tipo=f"lembrete_{entidade}", titulo=f"Lembrete: {nome}",
                    mensagem=f"Lembrete agendado para “{nome}”.",
                    metadata={"link": f"/{'clientes' if entidade == 'cliente' else 'comercial'}"
                                       f"?{param}={entity_id}"},
                )
                admin_db.table(cfg.tables.lembretes).update({"enviado_em": agora}).eq(
                    "id", lembrete["id"]
                ).execute()
                resumo["notificados"] += 1
            except Exception:  # noqa: BLE001 — one bad reminder must not stop the sweep
                resumo["falhas"] += 1
                logger.exception(
                    "falha ao processar lembrete %s org=%s", lembrete.get("id"),
                    lembrete.get("org_id"),
                )
    return resumo
