"""`/api/edicao-fotos/processamento` — worker control + health (W8).

    GET  /processamento          platform admin — switch, worker, queue, last error, last probe
    PUT  /processamento          platform admin — {"ativo": bool}: pause/resume live
    POST /processamento/sonda    platform admin — OpenAI key/credit probe (costs one token)

"Processamento ativo" is `fotos_platform_settings.processamento_ativo`: the
worker (always running when `EDICAO_FOTOS_WORKER_ENABLED` allows it) reads
it before every claim. Turning it off never interrupts a job already
running; it stops the NEXT claim.

The worker block describes the process that answered this request
(`escopo: "este_processo"`); the queue block reads the shared job table,
so it covers every process.

"Sem créditos" is reported from two independent sources: the last probe,
and the most recent job error carrying a quota marker.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends

from noctusai_lib.domain.photo_editing import Actor, JobType, PhotoEditingPorts
from noctusai_lib.integrations.llm import CreditProbeResult, classify_provider_failure

from app.modules.edicao_fotos.deps import (
    get_credit_probe,
    get_edicao_ports,
    get_platform_openai_key,
    get_worker_control,
    require_platform_admin,
)
from app.modules.edicao_fotos.schemas import ProcessamentoBody

router = APIRouter(prefix="/api/edicao-fotos/processamento", tags=["edicao-fotos"])


class ProbeMemory:
    """The last probe answer, per process (a probe costs money — it runs
    only on an explicit click, and its answer is kept for the panel)."""

    def __init__(self) -> None:
        self.ultima: Optional[CreditProbeResult] = None


_memoria = ProbeMemory()


def get_probe_memory() -> ProbeMemory:
    """Seam: where the last probe answer lives."""
    return _memoria


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _sonda_out(result: Optional[CreditProbeResult]) -> Optional[dict[str, Any]]:
    if result is None:
        return None
    return {
        "status": result.status,
        "mensagem": result.message,
        "verificado_em": _iso(result.checked_at),
        "modelo": result.model,
        "http_status": result.http_status,
    }


async def _painel(ports: PhotoEditingPorts, control: Any, memoria: ProbeMemory) -> dict[str, Any]:
    platform = await ports.repo.get_platform_settings()
    stats = await ports.jobs.queue_stats(job_types=list(JobType.ALL))
    worker = control.status()
    erro_sem_credito = (
        stats.last_error is not None
        and classify_provider_failure(None, stats.last_error) == "sem_credito"
    )
    sonda_sem_credito = memoria.ultima is not None and memoria.ultima.status == "sem_credito"
    return {
        "ativo": bool(platform.processamento_ativo),
        "worker": {
            "escopo": "este_processo",
            "kill_switch_ativo": worker.kill_switch_ativo,
            "rodando": worker.rodando,
            "pausado": worker.rodando and not platform.processamento_ativo,
            "worker_id": worker.worker_id,
            "iniciado_em": _iso(worker.iniciado_em),
            "motivo_parado": worker.motivo_parado,
            "erro_gate": worker.erro_gate,
            "catalogo_atualizado_em": _iso(worker.catalogo_atualizado_em),
            "erro_catalogo": worker.erro_catalogo,
        },
        "fila": {
            "pendentes": stats.pending,
            "prontos_para_rodar": stats.due,
            "em_execucao": stats.running,
            "lease_expirado": stats.lease_expired,
            "mortos": stats.dead_letter,
            "workers_ativos": list(stats.active_workers),
        },
        "ultimo_erro": (
            {
                "mensagem": stats.last_error,
                "tipo_job": stats.last_error_type,
                "em": _iso(stats.last_error_at),
            }
            if stats.last_error
            else None
        ),
        "sem_creditos": erro_sem_credito or sonda_sem_credito,
        "sonda": _sonda_out(memoria.ultima),
    }


@router.get("")
async def get_processamento_route(
    _actor: Actor = Depends(require_platform_admin),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
    control: Any = Depends(get_worker_control),
    memoria: ProbeMemory = Depends(get_probe_memory),
) -> dict:
    return await _painel(ports, control, memoria)


@router.put("")
async def put_processamento_route(
    body: ProcessamentoBody,
    _actor: Actor = Depends(require_platform_admin),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
    control: Any = Depends(get_worker_control),
    memoria: ProbeMemory = Depends(get_probe_memory),
) -> dict:
    await ports.repo.update_platform_settings(processamento_ativo=body.ativo)
    control.invalidate_gate()
    return await _painel(ports, control, memoria)


@router.post("/sonda")
async def post_sonda_route(
    _actor: Actor = Depends(require_platform_admin),
    probe: Any = Depends(get_credit_probe),
    platform_key: Callable[[], Optional[str]] = Depends(get_platform_openai_key),
    memoria: ProbeMemory = Depends(get_probe_memory),
) -> dict:
    memoria.ultima = await probe.probe(platform_key())
    return _sonda_out(memoria.ultima) or {}


__all__ = ["ProbeMemory", "get_probe_memory", "router"]
