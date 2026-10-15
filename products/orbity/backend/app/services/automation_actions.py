"""
`action` step executor — the side-effects an automation flow can perform.

Supported `config.action_type` values (anything else FAILS explicitly — an
action is never silently acknowledged):

  add_tag          {"tag": "interessado"}            lead only
  remove_tag       {"tag": "interessado"}            lead only
  move_stage       {"stage_id": "<uuid>"}            lead only (alias: move_lead_stage)
  set_temperature  {"temperature": "cold|warm|hot"}  lead only
  create_task      {"title": "...", "description"?, "priority"?: low|med|high,
                    "due_in_days"?: int}             any subject (client_id is
                                                     linked when the subject is a client)

Actions do NOT emit automation triggers (no `pipeline_stage_entered` from a
`move_stage` action): a flow that moves a lead into the stage that triggers
itself would loop. Triggers fire from user-driven writes (routers) only.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from app.services.automation_engine import ActionError
from app.services.crm_service import CRMService
from app.services.tasks_service import TasksService

logger = logging.getLogger(__name__)

_LEAD_ONLY = {"add_tag", "remove_tag", "move_stage", "move_lead_stage", "set_temperature"}
SUPPORTED_ACTION_TYPES = frozenset(_LEAD_ONLY | {"create_task"})


def execute_action(db: Any, org_id: str, payload: dict[str, Any]) -> None:
    """Run one `action` pending-action payload. Raises `ActionError` (pt-BR)."""
    config: dict[str, Any] = payload.get("config") or {}
    action_type = str(payload.get("action_type") or config.get("action_type") or "")
    if action_type not in SUPPORTED_ACTION_TYPES:
        raise ActionError(
            f"Tipo de ação não suportado: {action_type or 'vazio'}. "
            f"Disponíveis: {', '.join(sorted(SUPPORTED_ACTION_TYPES))}."
        )

    subject_type = payload.get("subject_type") or "lead"
    subject_id = payload.get("subject_id") or payload.get("lead_id") or ""
    lead_id = str(subject_id) if subject_type == "lead" else ""

    if action_type in _LEAD_ONLY and not lead_id:
        raise ActionError("Esta ação só pode ser executada em fluxos de lead.")

    org = UUID(str(org_id))
    crm = CRMService(db, org_id=org)

    if action_type in ("add_tag", "remove_tag"):
        tag = str(config.get("tag") or "").strip()
        if not tag:
            raise ActionError("Ação de tag sem o nome da tag.")
        lead = crm.get_lead(lead_id)
        if not lead:
            raise ActionError("Lead não encontrado para aplicar a ação.")
        tags = list(lead.get("tags") or [])
        if action_type == "add_tag" and tag not in tags:
            tags.append(tag)
        elif action_type == "remove_tag":
            tags = [t for t in tags if t != tag]
        crm.update_lead(lead_id, {"tags": tags})

    elif action_type in ("move_stage", "move_lead_stage"):
        stage_id = str(config.get("stage_id") or "").strip()
        if not stage_id:
            raise ActionError("Ação de mover etapa sem stage_id.")
        try:
            moved = crm.move_lead_stage(lead_id, stage_id)
        except ValueError as exc:
            raise ActionError("Etapa de destino não encontrada.") from exc
        if not moved:
            raise ActionError("Lead não encontrado para mover de etapa.")

    elif action_type == "set_temperature":
        temperature = str(config.get("temperature") or "")
        if temperature not in ("cold", "warm", "hot"):
            raise ActionError("Temperatura inválida (use cold, warm ou hot).")
        if not crm.update_lead(lead_id, {"temperature": temperature}):
            raise ActionError("Lead não encontrado para aplicar a ação.")

    elif action_type == "create_task":
        title = str(config.get("title") or "").strip()
        if not title:
            raise ActionError("Ação de criar tarefa sem título.")
        priority = str(config.get("priority") or "med")
        if priority not in ("low", "med", "high"):
            raise ActionError("Prioridade inválida (use low, med ou high).")
        task: dict[str, Any] = {"title": title, "status": "todo", "priority": priority}
        if config.get("description"):
            task["description"] = str(config["description"])
        days = config.get("due_in_days")
        if days is not None:
            try:
                task["due_date"] = (date.today() + timedelta(days=int(days))).isoformat()
            except (TypeError, ValueError) as exc:
                raise ActionError("due_in_days deve ser um número inteiro.") from exc
        if subject_type == "client" and subject_id:
            task["client_id"] = str(subject_id)
        TasksService(db, org_id=org).create_task(task)
