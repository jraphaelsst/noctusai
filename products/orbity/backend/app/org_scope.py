"""Orbity's tenant-scoped data access: the 23 service-only tables behind one org-bound client.

Since migration 034 the browser roles hold NO grant on these tables; every router reads and writes them through
:func:`get_org_client` (service role, bound to the org of the authenticated request -- never a body or path value).
The seed wrapper (``noctusai_lib.api.org_scoped``) injects the org filter on every select/update/delete, stamps
``org_id`` on every insert, and checks the declared foreign keys below on every write (a request naming another
tenant's ``stage_id`` / ``client_id`` / ``post_id`` is refused 422). KB § PATTERNS/security/access-tiers.md.
"""
from __future__ import annotations

from typing import Any

from noctusai_lib.api.org_scoped import OrgScopedClient

#: The tables migration 034 makes service-only (with 031/032's: everything the browser used to reach).
SERVICE_ONLY_TABLES: frozenset[str] = frozenset({
    "ad_accounts", "agenda_events", "automation_executions", "automation_flows", "automation_pending_actions",
    "automation_steps", "campaign_metrics", "campaigns", "clients", "content_campaigns", "content_plan_items",
    "content_plans", "content_posts", "lead_activities", "lead_scoring_results", "lead_scoring_rules",
    "lead_stages", "leads", "post_approvals", "report_snapshots", "reports", "routines", "tasks",
})

#: table -> {column: parent table}; mirrors the FOREIGN KEYs of migrations 005-020 (a FK accepts any existing id,
#: whoever owns it -- this makes the parent prove it belongs to the caller's org).
FOREIGN_KEYS: dict[str, dict[str, str]] = {
    "leads": {"client_id": "clients", "stage_id": "lead_stages"},
    "lead_activities": {"lead_id": "leads"},
    "lead_scoring_results": {"lead_id": "leads"},
    "tasks": {"client_id": "clients"},
    "agenda_events": {"client_id": "clients"},
    "reports": {"client_id": "clients"},
    "report_snapshots": {"report_id": "reports"},
    "ad_accounts": {"client_id": "clients"},
    "campaigns": {"client_id": "clients", "ad_account_id": "ad_accounts"},
    "campaign_metrics": {"campaign_id": "campaigns"},
    "content_campaigns": {"client_id": "clients"},
    "content_posts": {"campaign_id": "content_campaigns", "client_id": "clients"},
    "post_approvals": {"post_id": "content_posts"},
    "automation_steps": {"flow_id": "automation_flows"},
    "automation_executions": {"flow_id": "automation_flows", "lead_id": "leads"},
    "automation_pending_actions": {"execution_id": "automation_executions", "step_id": "automation_steps"},
    "content_plans": {"client_id": "clients", "campaign_id": "content_campaigns"},
    "content_plan_items": {"plan_id": "content_plans", "task_id": "tasks", "post_id": "content_posts"},
}


def make_org_client(admin_client: Any, org_id: Any) -> OrgScopedClient:
    return OrgScopedClient(admin_client, org_id, foreign_keys=FOREIGN_KEYS)
