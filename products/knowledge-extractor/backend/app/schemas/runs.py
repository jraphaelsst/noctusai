"""Run wire schemas — trigger + track extraction-pipeline executions."""
from __future__ import annotations

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    drive_url: str | None = Field(default=None)
    fake: bool = Field(default=False)


class RunAccepted(BaseModel):
    accepted: bool
    run_id: str
    mode: str


class RunStatusOut(BaseModel):
    run_id: str
    status: str
    mode: str
    started_at: str
    finished_at: str | None
    detail: str | None


class RunListResponse(BaseModel):
    runs: list[RunStatusOut]
