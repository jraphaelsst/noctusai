"""
Jobs Router — Background job management endpoints.

Submit, list, and check status of background jobs.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import Field
from app.dependencies import get_current_user, get_org_id
from app.services.job_service import submit_job, get_job, list_jobs
from app.responses import success_response
from noctusai_lib.api import StrictHttpModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobSubmitRequest(StrictHttpModel):
    name: str = Field(..., min_length=1, max_length=100)
    params: dict = Field(default_factory=dict)


@router.post("/submit")
async def submit_background_job(
    body: JobSubmitRequest,
    auth = Depends(get_current_user)):
    """Submit a new background job."""
    user, token = auth
    org_id = get_org_id(user)

    job = submit_job(body.name, org_id, body.params)

    return success_response(job.to_dict())


@router.get("/{job_id}")
async def get_job_status(
    job_id: str,
    auth = Depends(get_current_user)):
    """Get the status of a background job."""
    user, token = auth
    org_id = get_org_id(user)

    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    if job.org_id != org_id:
        raise HTTPException(status_code=403, detail="Acesso negado")

    return success_response(job.to_dict())


@router.get("")
async def listar_jobs(
    auth = Depends(get_current_user)):
    """List recent background jobs for the org."""
    user, token = auth
    org_id = get_org_id(user)

    jobs = list_jobs(org_id)

    return success_response(jobs, total=len(jobs))
