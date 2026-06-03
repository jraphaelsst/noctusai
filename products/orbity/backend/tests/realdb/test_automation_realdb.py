"""
Real-DB integration tests for migration 010 — automation tables.

Requires: migration 010_automation.sql applied to the target Supabase project.
Pending migration apply: these tests are intentionally skipped until the
tech-lead applies the migration (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY
must be set AND the migration must have been applied).

Run: pytest products/orbity/backend/tests/realdb/test_automation_realdb.py -v

Tables exercised:
  - automation_flows, automation_steps, automation_executions,
    automation_pending_actions
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.realdb


class TestAutomationFlowsRoundTrip:
    """Service-role round-trip: insert → fetch → update → delete."""

    def test_create_and_fetch_flow(self, orbity_db, test_org_a):
        org_id = test_org_a["id"]
        flow_id = str(uuid.uuid4())
        payload = {
            "id": flow_id,
            "org_id": org_id,
            "name": "Real-DB test flow",
            "trigger_type": "lead_created",
            "trigger_config": {},
            "active": True,
            "schedule_window": {},
            "stop_rules": {},
        }
        try:
            inserted = orbity_db.table("automation_flows").insert(payload).execute().data
            assert len(inserted) == 1
            assert inserted[0]["id"] == flow_id

            fetched = (
                orbity_db.table("automation_flows").select("*").eq("id", flow_id).execute().data
            )
            assert len(fetched) == 1
            assert fetched[0]["name"] == "Real-DB test flow"
            assert fetched[0]["org_id"] == org_id
            assert fetched[0]["active"] is True
        finally:
            orbity_db.table("automation_flows").delete().eq("id", flow_id).execute()

    def test_update_flow_active_flag(self, orbity_db, test_org_a):
        org_id = test_org_a["id"]
        flow_id = str(uuid.uuid4())
        orbity_db.table("automation_flows").insert({
            "id": flow_id,
            "org_id": org_id,
            "name": "Update test",
            "trigger_type": "manual",
            "trigger_config": {},
            "active": True,
            "schedule_window": {},
            "stop_rules": {},
        }).execute()
        try:
            orbity_db.table("automation_flows").update({"active": False}).eq("id", flow_id).execute()
            row = orbity_db.table("automation_flows").select("active").eq("id", flow_id).execute().data
            assert row[0]["active"] is False
        finally:
            orbity_db.table("automation_flows").delete().eq("id", flow_id).execute()

    def test_invalid_trigger_type_rejected(self, orbity_db, test_org_a):
        """DB-level CHECK constraint rejects invalid trigger_type values."""
        from postgrest.exceptions import APIError
        with pytest.raises((APIError, Exception)):
            orbity_db.table("automation_flows").insert({
                "org_id": test_org_a["id"],
                "name": "bad",
                "trigger_type": "not_a_real_trigger",
                "trigger_config": {},
                "active": True,
                "schedule_window": {},
                "stop_rules": {},
            }).execute()


class TestAutomationStepsRoundTrip:
    """Round-trip for automation_steps with FK to automation_flows."""

    def _create_flow(self, orbity_db, org_id: str) -> str:
        flow_id = str(uuid.uuid4())
        orbity_db.table("automation_flows").insert({
            "id": flow_id,
            "org_id": org_id,
            "name": "Step test parent",
            "trigger_type": "manual",
            "trigger_config": {},
            "active": True,
            "schedule_window": {},
            "stop_rules": {},
        }).execute()
        return flow_id

    def test_create_and_fetch_step(self, orbity_db, test_org_a):
        org_id = test_org_a["id"]
        flow_id = self._create_flow(orbity_db, org_id)
        step_id = str(uuid.uuid4())
        try:
            inserted = orbity_db.table("automation_steps").insert({
                "id": step_id,
                "org_id": org_id,
                "flow_id": flow_id,
                "ord": 0,
                "step_type": "send_message",
                "config": {"template": "Olá {nome}!"},
            }).execute().data
            assert len(inserted) == 1

            fetched = (
                orbity_db.table("automation_steps").select("*").eq("id", step_id).execute().data
            )
            assert fetched[0]["step_type"] == "send_message"
            assert fetched[0]["config"]["template"] == "Olá {nome}!"
        finally:
            orbity_db.table("automation_steps").delete().eq("id", step_id).execute()
            orbity_db.table("automation_flows").delete().eq("id", flow_id).execute()

    def test_duplicate_ord_in_same_flow_rejected(self, orbity_db, test_org_a):
        """UNIQUE(flow_id, ord) constraint prevents duplicate ord values."""
        from postgrest.exceptions import APIError
        org_id = test_org_a["id"]
        flow_id = self._create_flow(orbity_db, org_id)
        step1_id = str(uuid.uuid4())
        step2_id = str(uuid.uuid4())
        try:
            orbity_db.table("automation_steps").insert({
                "id": step1_id,
                "org_id": org_id,
                "flow_id": flow_id,
                "ord": 0,
                "step_type": "end",
                "config": {},
            }).execute()
            with pytest.raises((APIError, Exception)):
                orbity_db.table("automation_steps").insert({
                    "id": step2_id,
                    "org_id": org_id,
                    "flow_id": flow_id,
                    "ord": 0,  # duplicate!
                    "step_type": "end",
                    "config": {},
                }).execute()
        finally:
            orbity_db.table("automation_steps").delete().eq("flow_id", flow_id).execute()
            orbity_db.table("automation_flows").delete().eq("id", flow_id).execute()


class TestAutomationExecutionsRoundTrip:
    """Round-trip for automation_executions — requires flows + leads."""

    def _create_flow(self, orbity_db, org_id: str) -> str:
        flow_id = str(uuid.uuid4())
        orbity_db.table("automation_flows").insert({
            "id": flow_id,
            "org_id": org_id,
            "name": "Exec parent flow",
            "trigger_type": "manual",
            "trigger_config": {},
            "active": True,
            "schedule_window": {},
            "stop_rules": {},
        }).execute()
        return flow_id

    def _create_lead(self, orbity_db, org_id: str) -> str:
        lead_id = str(uuid.uuid4())
        orbity_db.table("leads").insert({
            "id": lead_id,
            "org_id": org_id,
            "name": "Automation Test Lead",
            "custom_fields": {},
            "tags": [],
        }).execute()
        return lead_id

    def test_create_and_fetch_execution(self, orbity_db, test_org_a):
        org_id = test_org_a["id"]
        flow_id = self._create_flow(orbity_db, org_id)
        lead_id = self._create_lead(orbity_db, org_id)
        exec_id = str(uuid.uuid4())
        try:
            inserted = orbity_db.table("automation_executions").insert({
                "id": exec_id,
                "org_id": org_id,
                "flow_id": flow_id,
                "lead_id": lead_id,
                "status": "running",
                "current_step_ord": 0,
                "context": {},
            }).execute().data
            assert len(inserted) == 1
            assert inserted[0]["status"] == "running"

            fetched = (
                orbity_db.table("automation_executions")
                .select("*")
                .eq("id", exec_id)
                .execute()
                .data
            )
            assert fetched[0]["current_step_ord"] == 0
            assert fetched[0]["org_id"] == org_id
        finally:
            orbity_db.table("automation_executions").delete().eq("id", exec_id).execute()
            orbity_db.table("leads").delete().eq("id", lead_id).execute()
            orbity_db.table("automation_flows").delete().eq("id", flow_id).execute()

    def test_invalid_status_rejected(self, orbity_db, test_org_a):
        """CHECK constraint blocks invalid status values."""
        from postgrest.exceptions import APIError
        org_id = test_org_a["id"]
        flow_id = self._create_flow(orbity_db, org_id)
        lead_id = self._create_lead(orbity_db, org_id)
        try:
            with pytest.raises((APIError, Exception)):
                orbity_db.table("automation_executions").insert({
                    "org_id": org_id,
                    "flow_id": flow_id,
                    "lead_id": lead_id,
                    "status": "invalid_status",  # must be running/done/canceled/failed
                    "current_step_ord": 0,
                    "context": {},
                }).execute()
        finally:
            orbity_db.table("leads").delete().eq("id", lead_id).execute()
            orbity_db.table("automation_flows").delete().eq("id", flow_id).execute()


class TestAutomationPendingActionsRoundTrip:
    """Round-trip for automation_pending_actions."""

    def _setup_flow_exec_step(self, orbity_db, org_id: str):
        """Create a flow + lead + execution + step for pending_action FK deps."""
        flow_id = str(uuid.uuid4())
        lead_id = str(uuid.uuid4())
        exec_id = str(uuid.uuid4())
        step_id = str(uuid.uuid4())

        orbity_db.table("automation_flows").insert({
            "id": flow_id,
            "org_id": org_id,
            "name": "PA parent flow",
            "trigger_type": "manual",
            "trigger_config": {},
            "active": True,
            "schedule_window": {},
            "stop_rules": {},
        }).execute()
        orbity_db.table("leads").insert({
            "id": lead_id,
            "org_id": org_id,
            "name": "PA Test Lead",
            "custom_fields": {},
            "tags": [],
        }).execute()
        orbity_db.table("automation_steps").insert({
            "id": step_id,
            "org_id": org_id,
            "flow_id": flow_id,
            "ord": 0,
            "step_type": "send_message",
            "config": {},
        }).execute()
        orbity_db.table("automation_executions").insert({
            "id": exec_id,
            "org_id": org_id,
            "flow_id": flow_id,
            "lead_id": lead_id,
            "status": "running",
            "current_step_ord": 0,
            "context": {},
        }).execute()
        return flow_id, lead_id, exec_id, step_id

    def _cleanup(self, orbity_db, flow_id, lead_id, exec_id, step_id, pa_ids=None):
        if pa_ids:
            for pa_id in pa_ids:
                orbity_db.table("automation_pending_actions").delete().eq("id", pa_id).execute()
        orbity_db.table("automation_executions").delete().eq("id", exec_id).execute()
        orbity_db.table("automation_steps").delete().eq("id", step_id).execute()
        orbity_db.table("leads").delete().eq("id", lead_id).execute()
        orbity_db.table("automation_flows").delete().eq("id", flow_id).execute()

    def test_create_and_fetch_pending_action(self, orbity_db, test_org_a):
        org_id = test_org_a["id"]
        flow_id, lead_id, exec_id, step_id = self._setup_flow_exec_step(orbity_db, org_id)
        pa_id = str(uuid.uuid4())
        try:
            inserted = orbity_db.table("automation_pending_actions").insert({
                "id": pa_id,
                "org_id": org_id,
                "execution_id": exec_id,
                "step_id": step_id,
                "scheduled_for": datetime.now(timezone.utc).isoformat(),
                "status": "pending",
                "payload": {"step_type": "send_message", "phone": "5511999990000"},
            }).execute().data
            assert len(inserted) == 1
            assert inserted[0]["status"] == "pending"

            fetched = (
                orbity_db.table("automation_pending_actions")
                .select("*")
                .eq("id", pa_id)
                .execute()
                .data
            )
            assert fetched[0]["payload"]["step_type"] == "send_message"
        finally:
            self._cleanup(orbity_db, flow_id, lead_id, exec_id, step_id, [pa_id])

    def test_update_pending_action_to_sent(self, orbity_db, test_org_a):
        org_id = test_org_a["id"]
        flow_id, lead_id, exec_id, step_id = self._setup_flow_exec_step(orbity_db, org_id)
        pa_id = str(uuid.uuid4())
        try:
            orbity_db.table("automation_pending_actions").insert({
                "id": pa_id,
                "org_id": org_id,
                "execution_id": exec_id,
                "step_id": step_id,
                "scheduled_for": datetime.now(timezone.utc).isoformat(),
                "status": "pending",
                "payload": {},
            }).execute()
            orbity_db.table("automation_pending_actions").update({
                "status": "sent",
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", pa_id).execute()
            row = (
                orbity_db.table("automation_pending_actions")
                .select("status")
                .eq("id", pa_id)
                .execute()
                .data
            )
            assert row[0]["status"] == "sent"
        finally:
            self._cleanup(orbity_db, flow_id, lead_id, exec_id, step_id, [pa_id])

    def test_invalid_pending_action_status_rejected(self, orbity_db, test_org_a):
        """CHECK constraint blocks invalid status values."""
        from postgrest.exceptions import APIError
        org_id = test_org_a["id"]
        flow_id, lead_id, exec_id, step_id = self._setup_flow_exec_step(orbity_db, org_id)
        try:
            with pytest.raises((APIError, Exception)):
                orbity_db.table("automation_pending_actions").insert({
                    "org_id": org_id,
                    "execution_id": exec_id,
                    "step_id": step_id,
                    "scheduled_for": datetime.now(timezone.utc).isoformat(),
                    "status": "bogus_status",
                    "payload": {},
                }).execute()
        finally:
            self._cleanup(orbity_db, flow_id, lead_id, exec_id, step_id)


class TestAutomationRLSIsolation:
    """RLS isolation: org A's automation rows are invisible to org B queries.

    Uses service-role client with explicit org_id filter — demonstrates the
    data-layer org scoping that RLS enforces for authenticated JWT clients.
    """

    def test_automation_flows_scoped_by_org_id(self, orbity_db, test_org_a, test_org_b):
        flow_a_id = str(uuid.uuid4())
        flow_b_id = str(uuid.uuid4())
        try:
            orbity_db.table("automation_flows").insert({
                "id": flow_a_id,
                "org_id": test_org_a["id"],
                "name": "Org A flow",
                "trigger_type": "manual",
                "trigger_config": {},
                "active": True,
                "schedule_window": {},
                "stop_rules": {},
            }).execute()
            orbity_db.table("automation_flows").insert({
                "id": flow_b_id,
                "org_id": test_org_b["id"],
                "name": "Org B flow",
                "trigger_type": "manual",
                "trigger_config": {},
                "active": True,
                "schedule_window": {},
                "stop_rules": {},
            }).execute()

            rows_a = (
                orbity_db.table("automation_flows")
                .select("id")
                .eq("org_id", test_org_a["id"])
                .execute()
                .data
            )
            rows_b = (
                orbity_db.table("automation_flows")
                .select("id")
                .eq("org_id", test_org_b["id"])
                .execute()
                .data
            )
            ids_a = {r["id"] for r in rows_a}
            ids_b = {r["id"] for r in rows_b}

            assert flow_a_id in ids_a
            assert flow_a_id not in ids_b
            assert flow_b_id in ids_b
            assert flow_b_id not in ids_a
        finally:
            orbity_db.table("automation_flows").delete().eq("id", flow_a_id).execute()
            orbity_db.table("automation_flows").delete().eq("id", flow_b_id).execute()
