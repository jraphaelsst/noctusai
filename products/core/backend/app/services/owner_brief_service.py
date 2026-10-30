"""Owner daily brief — what changed and what broke in the last 24h, code only.

Runs as the core job `core_owner_daily_brief` (07:00 on the platform clock,
`app/scheduler.py`). Zero LLM / paid-API spend by construction: every line
is a database read or a docker status read, rendered by f-strings. (The
seed `BaseDigestService` is deliberately NOT used — its narrative step is an
LLM call; this brief has no narrative.)

Sections:
  * Rotinas      — failed and missing scheduler runs per product (24h).
  * IA           — LLM spend yesterday per product (and per org once the
                   ai-usage ledger lands — see `operations_service`).
  * Custos       — `cost_ledger` yesterday per org.
  * Frota        — containers not running / unhealthy (docker socket).
  * Deploy       — core's own build sha.
  * Lembretes    — owner reminders live outside the container: n/a.

Delivery: in-app (bell) to every platform admin + e-mail to the core
notification address (`settings.website_leads_notify_email` — the address
core already notifies; never a literal here). Every brief is stored in
`public.owner_briefs`; the job itself lands in `public.scheduler_runs`
(it is a seed-scheduler job), which is what the Operação dead-man reads.
"""
from __future__ import annotations

import html
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

from noctusai_lib.domain.scheduler_runs import notify_platform_admins
from noctusai_lib.primitives.timeutil import platform_timezone_name, platform_tz

from app.services.operations_service import (
    ROUTINES_WINDOW,
    LlmSpendSource,
    cost_ledger_by_org,
    default_llm_spend,
    list_routines,
    safe_llm_spend,
    yesterday_window,
)

logger = logging.getLogger(__name__)

BRIEF_KIND = "owner_daily_brief"
BRIEF_LINK = "/admin/operacao/brief"

FleetStatusSource = Callable[[], list[dict]]
EmailSender = Callable[[str, str, str], bool]


def default_fleet_status() -> list[dict]:
    """Container statuses from the seed fleet controller. Raises when only
    the Fake is available (no docker socket) — a fabricated "all running"
    must never reach the brief."""
    from noctusai_lib.domain.fleet_control import FakeContainerController, get_fleet_controller

    controller = get_fleet_controller()
    if isinstance(controller, FakeContainerController):
        raise RuntimeError("docker socket indisponível neste contêiner")
    return [s.as_dict() for s in controller.status()]


def _fleet_section(source: FleetStatusSource) -> dict:
    try:
        statuses = source()
    except Exception as exc:  # noqa: BLE001 — reported in the brief + logged
        logger.warning("owner brief: fleet status unavailable: %s", exc)
        return {"available": False, "error": f"{type(exc).__name__}: {exc}", "problems": [], "total": 0}
    problems = [
        {"slug": s.get("slug"), "state": s.get("state"), "health": s.get("health")}
        for s in statuses
        if s.get("state") != "absent" and (not s.get("running") or s.get("health") == "unhealthy")
    ]
    return {"available": True, "error": None, "problems": problems, "total": len(statuses)}


def compose_brief(
    db: Any,
    now: datetime,
    *,
    llm_source: LlmSpendSource = default_llm_spend,
    fleet_source: FleetStatusSource = default_fleet_status,
    build_sha: Optional[str] = None,
) -> dict:
    """The brief's structured payload (no delivery, no write)."""
    routines = list_routines(db, now)
    failed, missing = [], []
    for product in routines["products"]:
        if not product["active"]:
            continue
        for job in product["jobs"]:
            last = job["last_run"] or {}
            if job["errors_24h"] or last.get("status") == "error":
                failed.append({
                    "product": product["product"], "job": job["job"], "errors_24h": job["errors_24h"],
                    "last_error": last.get("error"), "last_at": last.get("started_at"),
                })
            if job["overdue"]:
                missing.append({"product": product["product"], "job": job["job"], "expected_at": job["expected_at"]})

    y_start, y_end = yesterday_window(now)
    llm = safe_llm_spend(llm_source, db, y_start, y_end)
    costs = cost_ledger_by_org(db, y_start, y_end)
    fleet = _fleet_section(fleet_source)
    sha = build_sha if build_sha is not None else (os.environ.get("GIT_SHA") or os.environ.get("NOCTUS_BUILD_SHA"))

    exceptions = len(failed) + len(missing) + len(fleet["problems"])
    exceptions += 0 if llm["available"] else 1
    exceptions += 0 if fleet["available"] else 1
    return {
        "generated_at": now.isoformat(),
        "timezone": platform_timezone_name(),
        "period": {"from": (now - ROUTINES_WINDOW).isoformat(), "to": now.isoformat()},
        "yesterday": {"from": y_start.isoformat(), "to": y_end.isoformat()},
        "scheduler": {
            "runs_24h": routines["totals"]["runs_24h"],
            "jobs": routines["totals"]["jobs"],
            "failed": failed,
            "missing": missing,
        },
        "llm": llm,
        "costs": costs,
        "fleet": fleet,
        "deploy": {"core_build_sha": sha},
        "reminders": {"available": False, "note": "lembretes do owner vivem fora do contêiner (n/a)"},
        "exceptions_count": exceptions,
    }


def _local(ts: Optional[str]) -> str:
    if not ts:
        return "—"
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone(platform_tz()).strftime("%d/%m %H:%M")
    except ValueError:
        return str(ts)


def _usd(value: Optional[float]) -> str:
    return "—" if value is None else f"US$ {value:,.2f}"


def _brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def render_lines(payload: dict) -> list[tuple[str, list[str]]]:
    """(section title, lines) pairs — the single rendering both bodies use."""
    sched = payload["scheduler"]
    rot = [f"{sched['runs_24h']} execuções de {sched['jobs']} rotinas nas últimas 24h."]
    if not sched["failed"] and not sched["missing"]:
        rot.append("Nenhuma falha e nenhuma execução faltando.")
    for f in sched["failed"]:
        rot.append(f"FALHOU · {f['product']} / {f['job']} — {f['errors_24h']} erro(s), último {_local(f['last_at'])}: "
                   f"{f['last_error'] or 'sem detalhe'}")
    for m in sched["missing"]:
        rot.append(f"FALTANDO · {m['product']} / {m['job']} — esperada {_local(m['expected_at'])}")

    llm = payload["llm"]
    ia: list[str] = []
    if not llm["available"]:
        ia.append(f"Fonte de uso de IA indisponível: {llm['error']}")
    else:
        ia.append(f"Ontem: {_usd(llm['total_usd'])} em {llm['calls']} chamadas.")
        for p in llm["per_product"]:
            if p["calls"]:
                ia.append(f"{p['product']}: {_usd(p['cost_usd'])} ({p['calls']} chamadas)")
        if llm.get("per_org"):
            for o in llm["per_org"]:
                ia.append(f"org {o.get('org_name') or o.get('org_id')}: {_usd(o.get('cost_usd'))}")
        else:
            ia.append("Divisão por organização: aguardando o ledger public.ai_usage.")

    costs = payload["costs"]
    cus = [f"Ontem: {_brl(costs['total_brl'])} no cost_ledger."]
    for o in costs["per_org"][:10]:
        cus.append(f"{o['org_name']}: {_brl(o['amount_brl'])}" + (f" (+{o['pending_fx']} aguardando câmbio)" if o["pending_fx"] else ""))

    fleet = payload["fleet"]
    fro: list[str] = []
    if not fleet["available"]:
        fro.append(f"Status da frota indisponível: {fleet['error']}")
    elif not fleet["problems"]:
        fro.append(f"{fleet['total']} contêineres, todos saudáveis.")
    else:
        for p in fleet["problems"]:
            fro.append(f"{p['slug']}: {p['state']} / {p['health']}")

    dep = [f"Core build: {payload['deploy']['core_build_sha'] or 'não informado'}"]
    lem = ["n/a (lembretes do owner vivem fora do contêiner)"]
    return [("Rotinas", rot), ("IA", ia), ("Custos", cus), ("Frota", fro), ("Deploy", dep), ("Lembretes", lem)]


def subject_for(payload: dict) -> str:
    day = _local(payload["generated_at"])[:5]
    n = payload["exceptions_count"]
    flag = f"{n} exceção(ões)" if n else "tudo em ordem"
    return f"[NoctusAI] Brief diário {day} — {flag}"


def render_text(payload: dict) -> str:
    out = [subject_for(payload), ""]
    for title, lines in render_lines(payload):
        out.append(f"## {title}")
        out.extend(f"- {line}" for line in lines)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_html(payload: dict) -> str:
    parts = ['<div style="font-family: sans-serif; max-width: 640px; margin: 0 auto;">',
             f"<h2>{html.escape(subject_for(payload))}</h2>"]
    for title, lines in render_lines(payload):
        parts.append(f"<h3>{html.escape(title)}</h3><ul>")
        parts.extend(f"<li>{html.escape(line)}</li>" for line in lines)
        parts.append("</ul>")
    parts.append("</div>")
    return "".join(parts)


@dataclass
class BriefResult:
    brief_id: Optional[str]
    exceptions_count: int
    in_app_sent: int
    email_status: str


def _default_email_sender(to: str, subject: str, body_html: str) -> bool:
    from app.services.email_service import send_owner_brief

    return send_owner_brief(to, subject, body_html)


def _default_owner_email() -> str:
    from app.config import settings

    return getattr(settings, "website_leads_notify_email", "") or ""


def run_owner_brief(
    db: Any,
    now: datetime,
    *,
    trigger: str = "schedule",
    deliver: bool = True,
    llm_source: LlmSpendSource = default_llm_spend,
    fleet_source: FleetStatusSource = default_fleet_status,
    email_sender: Optional[EmailSender] = None,
    owner_email: Optional[str] = None,
    build_sha: Optional[str] = None,
) -> BriefResult:
    """Compose, store and (optionally) deliver the brief.

    A delivery failure is recorded on the stored row (`email_status`) and
    logged at ERROR — which also marks the scheduler run `error`, so the
    Operação page shows it — but never loses the brief itself."""
    payload = compose_brief(db, now, llm_source=llm_source, fleet_source=fleet_source, build_sha=build_sha)
    text_body = render_text(payload)
    in_app = 0
    email_status = "not_sent"

    if deliver:
        try:
            in_app = notify_platform_admins(
                db, kind=BRIEF_KIND, title=subject_for(payload),
                message=text_body[:1500], metadata={"link": BRIEF_LINK},
            )
        except Exception:  # noqa: BLE001 — recorded + loud; the brief is still stored
            logger.error("owner brief: in-app delivery FAILED", exc_info=True)
        to = owner_email if owner_email is not None else _default_owner_email()
        if not to:
            email_status = "not_configured"
            logger.warning("owner brief: e-mail skipped — WEBSITE_LEADS_NOTIFY_EMAIL is not set")
        else:
            sender = email_sender or _default_email_sender
            try:
                email_status = "sent" if sender(to, subject_for(payload), render_html(payload)) else "failed"
            except Exception:  # noqa: BLE001 — recorded + loud
                logger.error("owner brief: e-mail delivery raised", exc_info=True)
                email_status = "failed"
            if email_status == "failed":
                logger.error("owner brief: e-mail delivery FAILED (provider unset or send error)")

    row = {
        "generated_at": now.isoformat(),
        "period_start": (now - ROUTINES_WINDOW).isoformat(),
        "period_end": now.isoformat(),
        "trigger": trigger,
        "payload": payload,
        "text_body": text_body,
        "exceptions_count": payload["exceptions_count"],
        "in_app_sent": in_app,
        "email_status": email_status,
    }
    inserted = db.table("owner_briefs").insert(row).execute().data or []
    brief_id = str(inserted[0]["id"]) if inserted and inserted[0].get("id") else None
    return BriefResult(brief_id=brief_id, exceptions_count=payload["exceptions_count"],
                       in_app_sent=in_app, email_status=email_status)


def get_brief(db: Any, brief_id: Optional[str]) -> Optional[dict]:
    """One stored brief by id (None when absent)."""
    if not brief_id:
        return None
    rows = db.table("owner_briefs").select("*").eq("id", brief_id).limit(1).execute().data or []
    return rows[0] if rows else None


def list_briefs(db: Any, *, limit: int = 30) -> list[dict]:
    """Brief history, newest first (payload included)."""
    return (
        db.table("owner_briefs").select("*").order("generated_at", desc=True).limit(limit).execute().data
        or []
    )


__all__ = [
    "BRIEF_KIND",
    "BRIEF_LINK",
    "BriefResult",
    "compose_brief",
    "default_fleet_status",
    "get_brief",
    "list_briefs",
    "render_html",
    "render_text",
    "run_owner_brief",
    "subject_for",
]
