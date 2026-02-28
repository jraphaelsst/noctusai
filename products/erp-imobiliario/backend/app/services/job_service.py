"""
Job Service — Lightweight async background job system.

Uses asyncio tasks for in-process background work. For production scale,
replace with Celery + Redis or a similar distributed task queue.

Jobs are tracked in memory and optionally persisted to a Supabase table.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Job:
    """Represents a background job."""

    def __init__(self, name: str, org_id: str, params: Optional[Dict] = None):
        self.id = uuid.uuid4().hex[:16]
        self.name = name
        self.org_id = org_id
        self.params = params or {}
        self.status = JobStatus.PENDING
        self.result: Optional[Any] = None
        self.error: Optional[str] = None
        self.created_at = datetime.now(timezone.utc)
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.progress: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "org_id": self.org_id,
            "status": self.status.value,
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


# Global in-memory job registry
_jobs: Dict[str, Job] = {}
_handlers: Dict[str, Callable] = {}


def register_handler(name: str, handler: Callable[..., Coroutine]):
    """Register a named job handler function."""
    _handlers[name] = handler
    logger.info(f"[JOBS] Registered handler: {name}")


def get_job(job_id: str) -> Optional[Job]:
    """Get a job by ID."""
    return _jobs.get(job_id)


def list_jobs(org_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """List recent jobs for an org."""
    org_jobs = [j for j in _jobs.values() if j.org_id == org_id]
    org_jobs.sort(key=lambda j: j.created_at, reverse=True)
    return [j.to_dict() for j in org_jobs[:limit]]


async def _run_job(job: Job):
    """Execute a job's handler in the background."""
    handler = _handlers.get(job.name)
    if not handler:
        job.status = JobStatus.FAILED
        job.error = f"No handler registered for '{job.name}'"
        logger.error(f"[JOBS] {job.error}")
        return

    job.status = JobStatus.RUNNING
    job.started_at = datetime.now(timezone.utc)
    logger.info(f"[JOBS] Starting job {job.id}: {job.name}")

    try:
        result = await handler(job)
        job.status = JobStatus.COMPLETED
        job.result = result
        job.progress = 100
        logger.info(f"[JOBS] Completed job {job.id}: {job.name}")
    except Exception as e:
        job.status = JobStatus.FAILED
        job.error = str(e)
        logger.error(f"[JOBS] Failed job {job.id}: {job.name} — {e}")
    finally:
        job.completed_at = datetime.now(timezone.utc)


def submit_job(name: str, org_id: str, params: Optional[Dict] = None) -> Job:
    """Submit a new background job for async execution."""
    job = Job(name, org_id, params)
    _jobs[job.id] = job

    # Clean old jobs (keep last 200)
    if len(_jobs) > 200:
        sorted_jobs = sorted(_jobs.values(), key=lambda j: j.created_at)
        for old_job in sorted_jobs[:len(_jobs) - 200]:
            del _jobs[old_job.id]

    # Schedule execution
    asyncio.ensure_future(_run_job(job))
    logger.info(f"[JOBS] Submitted job {job.id}: {name} for org {org_id}")
    return job


# ── Built-in job handlers ───────────────────────────────────

async def _job_enviar_campanha(job: Job):
    """Send a marketing campaign to all recipients."""
    from app.dependencies import get_admin_client
    db = get_admin_client()

    campanha_id = job.params.get("campanha_id")
    if not campanha_id:
        raise ValueError("campanha_id é obrigatório")

    # Fetch campaign
    result = db.table("campanhas").select("*").eq("id", campanha_id).single().execute()
    if not result.data:
        raise ValueError(f"Campanha {campanha_id} não encontrada")

    campanha = result.data
    tipo = campanha.get("tipo", "email")

    # Fetch target clients based on filters
    filtros = campanha.get("filtros") or {}
    query = db.table("clientes").select("id, nome, email, telefone")
    if filtros.get("etapa_atual"):
        query = query.eq("etapa_atual", filtros["etapa_atual"])
    clients_result = query.execute()
    clientes = clients_result.data or []

    total = len(clientes)
    enviados = 0

    for i, cliente in enumerate(clientes):
        job.progress = int((i / max(total, 1)) * 100)

        if tipo == "email" and cliente.get("email"):
            # Record the send
            db.table("envios_email").insert({
                "org_id": job.org_id,
                "campanha_id": campanha_id,
                "cliente_id": cliente["id"],
                "email": cliente["email"],
                "status": "enviado",
            }).execute()
            enviados += 1

        elif tipo == "whatsapp" and cliente.get("telefone"):
            enviados += 1

        # Small delay to avoid overwhelming APIs
        await asyncio.sleep(0.05)

    # Update campaign stats
    db.table("campanhas").update({
        "total_enviados": enviados,
        "status": "concluida",
    }).eq("id", campanha_id).execute()

    return {"enviados": enviados, "total": total}


async def _job_sync_meta_leads(job: Job):
    """Sync leads from Meta/Facebook Lead Ads."""
    from app.services.meta_api_service import sync_leads
    from app.dependencies import get_admin_client

    db = get_admin_client()
    config_result = db.table("meta_config").select("*").limit(1).single().execute()
    if not config_result.data:
        raise ValueError("Meta API não configurada")

    result = await sync_leads(db, config_result.data)
    return result


async def _job_gerar_parcelas(job: Job):
    """Generate installments for a contract."""
    from app.dependencies import get_admin_client
    from datetime import timedelta

    db = get_admin_client()
    contrato_id = job.params.get("contrato_id")
    if not contrato_id:
        raise ValueError("contrato_id é obrigatório")

    result = db.table("contratos").select("*").eq("id", contrato_id).single().execute()
    if not result.data:
        raise ValueError(f"Contrato {contrato_id} não encontrado")

    contrato = result.data
    num_parcelas = int(contrato.get("num_parcelas", 1))
    valor_total = float(contrato.get("valor_total", 0))
    valor_entrada = float(contrato.get("valor_entrada", 0))
    valor_restante = valor_total - valor_entrada
    valor_parcela = round(valor_restante / max(num_parcelas, 1), 2)

    data_inicio = contrato.get("data_inicio", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    parcelas = []
    for i in range(num_parcelas):
        try:
            dt = datetime.fromisoformat(data_inicio) + timedelta(days=30 * (i + 1))
        except (ValueError, TypeError):
            dt = datetime.now(timezone.utc) + timedelta(days=30 * (i + 1))

        parcelas.append({
            "org_id": contrato.get("org_id", job.org_id),
            "contrato_id": contrato_id,
            "numero": i + 1,
            "valor": valor_parcela,
            "data_vencimento": dt.strftime("%Y-%m-%d"),
            "status": "pendente",
        })

    if parcelas:
        db.table("parcelas_contrato").insert(parcelas).execute()

    job.progress = 100
    return {"parcelas_geradas": len(parcelas)}


# Register built-in handlers
register_handler("enviar_campanha", _job_enviar_campanha)
register_handler("sync_meta_leads", _job_sync_meta_leads)
register_handler("gerar_parcelas", _job_gerar_parcelas)
