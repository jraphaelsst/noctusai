"""
Pydantic schemas for the /api/automation/* endpoints.

StrictHttpModel (extra="forbid") on all inbound models.
Outbound models use extra="ignore" (DB may return extra columns).

Vocabulary mirrors Orbity FE builder (WhatsAppAutomationFlows.tsx):
  trigger_type — lead_created / pipeline_stage_entered / lead_idle / ...
  step_type    — send_message / send_whatsapp_media / wait / condition /
                 action / branch / end
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import Field, model_validator

from noctusai_lib.api import StrictHttpModel

# ---------------------------------------------------------------------------
# Vocabularies
# ---------------------------------------------------------------------------

TriggerType = Literal[
    "lead_created",
    "pipeline_stage_entered",
    "lead_idle",
    "whatsapp_message_received",
    "keyword_received",
    "tag_added",
    "owner_changed",
    "task_created",
    "task_completed",
    "meeting_created",
    "proposal_sent",
    "client_created",
    "lead_status_changed",
    "manual",
]

StepType = Literal[
    "send_message",
    "send_whatsapp_media",
    "wait",
    "condition",
    "action",
    "branch",
    "end",
]

ExecutionStatus = Literal["running", "done", "canceled", "failed"]
PendingActionStatus = Literal["pending", "sent", "skipped", "failed"]


# ---------------------------------------------------------------------------
# Flow inbound / outbound
# ---------------------------------------------------------------------------

class FlowCreate(StrictHttpModel):
    name: str = Field(..., min_length=1, max_length=255)
    trigger_type: TriggerType
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    active: bool = True
    schedule_window: dict[str, Any] = Field(default_factory=dict)
    stop_rules: dict[str, Any] = Field(default_factory=dict)


class FlowUpdate(StrictHttpModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    trigger_type: Optional[TriggerType] = None
    trigger_config: Optional[dict[str, Any]] = None
    active: Optional[bool] = None
    schedule_window: Optional[dict[str, Any]] = None
    stop_rules: Optional[dict[str, Any]] = None


class FlowOut(StrictHttpModel):
    """Outbound flow shape — allow extra DB columns."""
    model_config = {"extra": "ignore"}

    id: UUID
    org_id: UUID
    name: str
    trigger_type: str
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    active: bool
    schedule_window: dict[str, Any] = Field(default_factory=dict)
    stop_rules: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Step inbound / outbound
# ---------------------------------------------------------------------------

class StepCreate(StrictHttpModel):
    ord: int = Field(..., ge=0, description="Step sequence (0-based, ascending)")
    step_type: StepType
    config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_config(self) -> "StepCreate":
        """Basic config shape checks per step_type.

        Steps that require specific config keys:
          wait            → duration_minutes (positive number)
          send_message    → template
          send_whatsapp_media → template
          condition       → field, operator

        Steps that require no mandatory config (config may be empty {}):
          end, action, branch
        """
        cfg = self.config
        if self.step_type == "wait":
            if "duration_minutes" not in cfg:
                raise ValueError("wait step requires config.duration_minutes")
            if not isinstance(cfg["duration_minutes"], (int, float)) or cfg["duration_minutes"] <= 0:
                raise ValueError("wait.duration_minutes must be a positive number")
        elif self.step_type in ("send_message", "send_whatsapp_media"):
            if "template" not in cfg:
                raise ValueError(f"{self.step_type} step requires config.template")
        elif self.step_type == "condition":
            for key in ("field", "operator"):
                if key not in cfg:
                    raise ValueError(f"condition step requires config.{key}")
        # end / action / branch: no mandatory config keys
        return self


class StepUpdate(StrictHttpModel):
    ord: Optional[int] = Field(default=None, ge=0)
    step_type: Optional[StepType] = None
    config: Optional[dict[str, Any]] = None


class StepOut(StrictHttpModel):
    model_config = {"extra": "ignore"}

    id: UUID
    org_id: UUID
    flow_id: UUID
    ord: int
    step_type: str
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Execution outbound (created internally by the engine — no inbound Create)
# ---------------------------------------------------------------------------

class ExecutionOut(StrictHttpModel):
    model_config = {"extra": "ignore"}

    id: UUID
    org_id: UUID
    flow_id: UUID
    lead_id: UUID
    status: str
    current_step_ord: int
    started_at: Optional[datetime] = None
    next_action_at: Optional[datetime] = None
    context: dict[str, Any] = Field(default_factory=dict)
    error_detail: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Pending action outbound
# ---------------------------------------------------------------------------

class PendingActionOut(StrictHttpModel):
    model_config = {"extra": "ignore"}

    id: UUID
    org_id: UUID
    execution_id: UUID
    step_id: UUID
    scheduled_for: datetime
    status: str
    payload: dict[str, Any] = Field(default_factory=dict)
    processed_at: Optional[datetime] = None
    error_detail: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Trigger request (POST /api/automation/flows/{id}/trigger)
# ---------------------------------------------------------------------------

class FlowTriggerRequest(StrictHttpModel):
    lead_id: UUID
    context: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# run-due response
# ---------------------------------------------------------------------------

class RunDueResult(StrictHttpModel):
    model_config = {"extra": "ignore"}

    processed: int = 0
    sent: int = 0
    skipped: int = 0
    failed: int = 0
