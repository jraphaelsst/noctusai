"""In-memory deterministic n8n client for dev + tests.

Satisfies the ``N8nClient`` Protocol structurally. Seeds three
workflows on construction, deliberately covering the three
run-eligibility outcomes measured live 2026-07-16
(``can_run = has_webhook_node AND active AND NOT archived``):

- ``"fake-wf-1"`` — webhook trigger, active, not archived → **can_run**.
- ``"fake-wf-2"`` — ``manualTrigger`` node only (no webhook) → not runnable.
- ``"fake-wf-3"`` — webhook trigger but archived → not runnable.

One tag (``"fake-tag-1"`` / ``"prod"``) and one execution
(``id=1``, on ``"fake-wf-1"``) are also seeded. All ids are
deterministic so tests can assert exact values.

Lifecycle semantics that mirror the real API:
- ``activate``/``deactivate``: flip ``active``, bump ``updatedAt``.
- ``rename``: routes through the same
  ``mappers.sanitize_workflow_put_body`` the real adapter's ``PUT``
  uses — so the fake exercises the identical sanitize path.
- ``delete_workflow``: removes the entry entirely (real API is not
  API-undoable either).
- ``run_via_webhook``: raises ``N8nWorkflowNotRunnableError`` for
  ``"fake-wf-2"``/``"fake-wf-3"`` — never a faked dispatch — and
  records dispatched ids on ``self.webhook_calls`` for assertions.

Use ``client._raw_workflows["fake-wf-1"]`` etc. to inspect or seed
state in tests. Same shape as ``FakeMailchimpClient`` per
``KB § PATTERNS/seed-fake-real-adapter.md``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from noctusai_lib.integrations.n8n.mappers import (
    raw_to_execution,
    raw_to_workflow,
    sanitize_workflow_put_body,
)
from noctusai_lib.integrations.n8n.types import (
    Credential,
    Execution,
    N8nNotFoundError,
    N8nWorkflowNotRunnableError,
    RunResult,
    Tag,
    Workflow,
)

# Canned schemas for the credential types actually exercised by this
# platform's n8n workflows — the Fake's answer to
# `get_credential_schema`. Unknown types fall back to a generic empty
# object shape rather than a fabricated guess at required fields.
_CREDENTIAL_SCHEMAS: dict[str, dict[str, Any]] = {
    "httpHeaderAuth": {
        "type": "object",
        "required": ["name", "value"],
        "properties": {"name": {"type": "string"}, "value": {"type": "string"}},
    },
    "httpBasicAuth": {
        "type": "object",
        "required": ["user", "password"],
        "properties": {"user": {"type": "string"}, "password": {"type": "string"}},
    },
}


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _webhook_node(path: str, method: str = "GET") -> dict[str, Any]:
    return {
        "id": f"node-webhook-{path}",
        "name": "Webhook",
        "type": "n8n-nodes-base.webhook",
        "parameters": {"httpMethod": method, "path": path, "options": {}},
        "webhookId": f"wh-{path}",
    }


def _manual_trigger_node() -> dict[str, Any]:
    return {
        "id": "node-manual",
        "name": "Manual Trigger",
        "type": "n8n-nodes-base.manualTrigger",
        "parameters": {},
    }


class FakeN8nClient:
    """In-memory n8n stand-in. Records state as raw n8n-shaped dicts
    (the same shape ``HttpxN8nClient`` parses) so ``get_workflow``
    returns realistic full fidelity and every mapper gets exercised.

    Test pattern::

        client = FakeN8nClient()
        workflows = await client.list_workflows()
        runnable = [w for w in workflows if w.can_run]
        assert len(runnable) == 1
    """

    def __init__(self) -> None:
        now = _now_iso()
        self._raw_workflows: dict[str, dict[str, Any]] = {
            "fake-wf-1": {
                "id": "fake-wf-1",
                "name": "Fake Runnable Webhook Flow",
                "active": True,
                "isArchived": False,
                "tags": [{"id": "fake-tag-1", "name": "prod"}],
                "nodes": [_webhook_node("fake-runnable")],
                "connections": {},
                "settings": {},
                "createdAt": now,
                "updatedAt": now,
            },
            "fake-wf-2": {
                "id": "fake-wf-2",
                "name": "Fake Manual-Trigger Flow",
                "active": True,
                "isArchived": False,
                "tags": [],
                "nodes": [_manual_trigger_node()],
                "connections": {},
                "settings": {},
                "createdAt": now,
                "updatedAt": now,
            },
            "fake-wf-3": {
                "id": "fake-wf-3",
                "name": "Fake Archived Webhook Flow",
                "active": True,
                "isArchived": True,
                "tags": [{"id": "fake-tag-1", "name": "prod"}],
                "nodes": [_webhook_node("fake-archived")],
                "connections": {},
                "settings": {},
                "createdAt": now,
                "updatedAt": now,
            },
        }
        self.tags: dict[str, Tag] = {"fake-tag-1": Tag(id="fake-tag-1", name="prod")}
        self.executions: dict[int, dict[str, Any]] = {
            1: {
                "id": 1,
                "workflowId": "fake-wf-1",
                "status": "success",
                "mode": "webhook",
                "finished": True,
                "startedAt": now,
                "stoppedAt": now,
                "data": {"resultData": {}},
            }
        }
        self._next_tag_serial = 2
        self._next_workflow_serial = 1
        self._credentials: dict[str, Credential] = {}
        self._next_credential_serial = 1
        # Test introspection — ids of workflows successfully dispatched via
        # run_via_webhook, in call order.
        self.webhook_calls: list[str] = []

    # ------------------------------------------------------------------
    # Workflows
    # ------------------------------------------------------------------

    async def list_workflows(
        self, *, tag: str | None = None, include_archived: bool = False
    ) -> list[Workflow]:
        workflows = [raw_to_workflow(w) for w in self._raw_workflows.values()]
        if not include_archived:
            workflows = [w for w in workflows if not w.archived]
        if tag:
            workflows = [
                w for w in workflows
                if any(t.id == tag or t.name == tag for t in w.tags)
            ]
        return workflows

    async def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        return dict(self._require_workflow(workflow_id))

    async def create_workflow(self, workflow: dict[str, Any]) -> Workflow:
        body = sanitize_workflow_put_body(workflow)
        wid = f"fake-wf-created-{self._next_workflow_serial}"
        self._next_workflow_serial += 1
        now = _now_iso()
        raw: dict[str, Any] = {
            "id": wid,
            "name": body.get("name", ""),
            "active": False,
            "isArchived": False,
            "tags": [],
            "nodes": body.get("nodes", []),
            "connections": body.get("connections", {}),
            "settings": body.get("settings", {}),
            "createdAt": now,
            "updatedAt": now,
        }
        self._raw_workflows[wid] = raw
        return raw_to_workflow(raw)

    async def update_workflow(
        self, workflow_id: str, workflow: dict[str, Any]
    ) -> Workflow:
        raw = self._require_workflow(workflow_id)
        # Route through the same sanitize path the real adapter's PUT body
        # goes through, so the fake exercises the identical allowlist logic.
        sanitized = sanitize_workflow_put_body(workflow)
        raw.update(sanitized)
        raw["updatedAt"] = _now_iso()
        return raw_to_workflow(raw)

    async def activate(self, workflow_id: str) -> Workflow:
        raw = self._require_workflow(workflow_id)
        raw["active"] = True
        raw["updatedAt"] = _now_iso()
        return raw_to_workflow(raw)

    async def deactivate(self, workflow_id: str) -> Workflow:
        raw = self._require_workflow(workflow_id)
        raw["active"] = False
        raw["updatedAt"] = _now_iso()
        return raw_to_workflow(raw)

    async def rename(self, workflow_id: str, name: str) -> Workflow:
        raw = self._require_workflow(workflow_id)
        return await self.update_workflow(workflow_id, {**raw, "name": name})

    async def delete_workflow(self, workflow_id: str) -> None:
        self._require_workflow(workflow_id)
        del self._raw_workflows[workflow_id]

    async def set_workflow_tags(
        self, workflow_id: str, tag_ids: list[str]
    ) -> list[Tag]:
        raw = self._require_workflow(workflow_id)
        resolved: list[Tag] = []
        for tid in tag_ids:
            tag = self.tags.get(tid)
            if tag is None:
                raise N8nNotFoundError(f"Tag {tid!r} not found", status=404)
            resolved.append(tag)
        raw["tags"] = [{"id": t.id, "name": t.name} for t in resolved]
        raw["updatedAt"] = _now_iso()
        return resolved

    # ------------------------------------------------------------------
    # Executions
    # ------------------------------------------------------------------

    async def list_executions(
        self,
        *,
        workflow_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[Execution]:
        items = list(self.executions.values())
        if workflow_id:
            items = [e for e in items if str(e.get("workflowId")) == str(workflow_id)]
        if status:
            items = [e for e in items if e.get("status") == status]
        items = items[:limit]
        return [raw_to_execution(e) for e in items]

    async def get_execution(
        self, execution_id: int, *, include_data: bool = True
    ) -> dict[str, Any]:
        raw = self.executions.get(execution_id)
        if raw is None:
            raise N8nNotFoundError(f"Execution {execution_id} not found", status=404)
        if not include_data:
            return {k: v for k, v in raw.items() if k != "data"}
        return dict(raw)

    async def delete_execution(self, execution_id: int) -> None:
        if execution_id not in self.executions:
            raise N8nNotFoundError(f"Execution {execution_id} not found", status=404)
        del self.executions[execution_id]

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    async def list_tags(self) -> list[Tag]:
        return list(self.tags.values())

    async def create_tag(self, name: str) -> Tag:
        tid = f"fake-tag-{self._next_tag_serial}"
        self._next_tag_serial += 1
        tag = Tag(id=tid, name=name)
        self.tags[tid] = tag
        return tag

    # ------------------------------------------------------------------
    # Credentials (write-only)
    # ------------------------------------------------------------------

    async def create_credential(
        self, *, name: str, type: str, data: dict[str, Any]
    ) -> Credential:
        cid = f"fake-cred-{self._next_credential_serial}"
        self._next_credential_serial += 1
        cred = Credential(id=cid, name=name, type=type)
        self._credentials[cid] = cred
        return cred

    async def delete_credential(self, credential_id: str) -> None:
        if credential_id not in self._credentials:
            raise N8nNotFoundError(
                f"Credential {credential_id!r} not found", status=404
            )
        del self._credentials[credential_id]

    async def get_credential_schema(self, credential_type_name: str) -> dict[str, Any]:
        return dict(
            _CREDENTIAL_SCHEMAS.get(
                credential_type_name,
                {"type": "object", "properties": {}, "required": []},
            )
        )

    # ------------------------------------------------------------------
    # Run (webhook-only)
    # ------------------------------------------------------------------

    async def run_via_webhook(self, workflow: Workflow) -> RunResult:
        if not workflow.can_run:
            reason = (
                "no webhook trigger node" if not workflow.has_webhook_node
                else "workflow is inactive" if not workflow.active
                else "workflow is archived"
            )
            raise N8nWorkflowNotRunnableError(
                f"Workflow {workflow.id!r} ({workflow.name!r}) is not "
                f"webhook-runnable: {reason}",
                status=409,
            )
        self.webhook_calls.append(workflow.id)
        return RunResult(
            workflow_id=workflow.id, dispatched=True, http_status=200, raw={"ok": True}
        )

    # ------------------------------------------------------------------
    # Connectivity
    # ------------------------------------------------------------------

    async def ping(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_workflow(self, workflow_id: str) -> dict[str, Any]:
        raw = self._raw_workflows.get(workflow_id)
        if raw is None:
            raise N8nNotFoundError(f"Workflow {workflow_id!r} not found", status=404)
        return raw


__all__ = ["FakeN8nClient"]
