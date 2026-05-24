"""Runs router — trigger + track extraction-pipeline runs.

``POST`` schedules the (long-running) pipeline on a BackgroundTask and returns
202; ``GET`` reports the in-memory run registry. The executor is a DI seam tests
override with a fake (no Drive/OpenAI).
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.dependencies import get_current_user_org
from app.schemas.runs import RunAccepted, RunListResponse, RunRequest, RunStatusOut
from app.services import runs_service

router = APIRouter(prefix="/api/runs", tags=["runs"])


def get_run_executor() -> runs_service.RunExecutor:
    """DI seam — the pipeline executor. Tests override with a fake (no Drive/OpenAI)."""
    return runs_service.default_executor


@router.post("", response_model=RunAccepted, status_code=status.HTTP_202_ACCEPTED)
async def start_run(
    payload: RunRequest,
    background_tasks: BackgroundTasks,
    auth: tuple = Depends(get_current_user_org),
    executor: runs_service.RunExecutor = Depends(get_run_executor),
) -> RunAccepted:
    if not payload.fake and not payload.drive_url:
        raise HTTPException(status_code=400, detail="informe drive_url ou use o modo fake")
    mode = "fake" if payload.fake else "drive"
    run = runs_service.register_run(mode)
    background_tasks.add_task(
        runs_service.run_and_track, executor, run.run_id, mode, payload.drive_url
    )
    return RunAccepted(accepted=True, run_id=run.run_id, mode=mode)


@router.get("", response_model=RunListResponse)
async def list_runs(
    auth: tuple = Depends(get_current_user_org),
) -> RunListResponse:
    return RunListResponse(
        runs=[
            RunStatusOut(
                run_id=r.run_id,
                status=r.status,
                mode=r.mode,
                started_at=r.started_at,
                finished_at=r.finished_at,
                detail=r.detail,
            )
            for r in runs_service.list_runs()
        ]
    )
