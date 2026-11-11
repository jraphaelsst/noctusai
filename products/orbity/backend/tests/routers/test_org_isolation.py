"""Tenant isolation of the nine routers that moved from the user's JWT (RLS) to the org-bound service-role client.

Since migration 034 RLS no longer protects these tables from the app: the scope is enforced in code
(``app/org_scope.py`` over the seed ``OrgScopedClient``). Every case below seeds a row of ANOTHER org and proves that the
caller (org A) cannot read it, change it, delete it, or point one of its own rows at it. A customer-role caller (``membro``)
gets nothing from any route. Strict statuses (404 / 422 / 403): never ``in (...)``.
"""
import pytest
from noctusai_lib.testing import TEST_USER_ID

from app.dependencies import coerce_org_uuid

ORG_A = str(coerce_org_uuid("test-org-123"))
ORG_B = "00000000-0000-4000-8000-0000000000bb"
FOREIGN = "b0000000-0000-4000-8000-000000000001"  # id of a row owned by org B
LEAK = "LEAK-FROM-ORG-B"

# (table, extra columns of the org-B row)
ROWS = {
    "tasks": {"title": LEAK, "status": "todo", "priority": "med"},
    "routines": {"title": LEAK, "cadence": "daily", "next_run": "2026-12-01", "active": True},
    "agenda_events": {"title": LEAK, "event_type": "other", "starts_at": "2026-12-01T10:00:00+00:00", "ends_at": "2026-12-01T11:00:00+00:00"},
    "clients": {"name": LEAK, "legal_name": LEAK, "active": True},
    "leads": {"name": LEAK},
    "lead_stages": {"name": LEAK, "position": 1},
    "lead_scoring_rules": {"name": LEAK},
    "content_campaigns": {"name": LEAK, "month": "2026-12", "status": "active"},
    "content_posts": {"platform": "instagram", "caption": LEAK, "status": "draft"},
    "content_plans": {"title": LEAK, "month": "2026-12", "status": "active"},
    "ad_accounts": {"name": LEAK, "external_account_id": "x", "status": "active"},
    "campaigns": {"name": LEAK, "external_campaign_id": "x", "ad_account_id": FOREIGN, "status": "active"},
    "reports": {"name": LEAK, "status": "draft", "period_start": "2026-11-01", "period_end": "2026-11-30"},
    "automation_flows": {"name": LEAK, "trigger_type": "lead_created", "active": True},
    "automation_steps": {"flow_id": FOREIGN, "ord": 0, "step_type": "end"},
    "automation_executions": {"flow_id": FOREIGN, "lead_id": FOREIGN, "status": "running"},
}

# (table, method, path, body): an id-addressed route -- the foreign row must be invisible (404) and untouched.
BY_ID = [
    ("tasks", "GET", f"/api/tasks/{FOREIGN}", None),
    ("tasks", "PATCH", f"/api/tasks/{FOREIGN}", {"title": "hijacked"}),
    ("tasks", "PATCH", f"/api/tasks/{FOREIGN}/status", {"status": "done"}),
    ("tasks", "DELETE", f"/api/tasks/{FOREIGN}", None),
    ("routines", "GET", f"/api/routines/{FOREIGN}", None),
    ("routines", "PATCH", f"/api/routines/{FOREIGN}", {"title": "hijacked"}),
    ("routines", "DELETE", f"/api/routines/{FOREIGN}", None),
    ("agenda_events", "GET", f"/api/agenda/events/{FOREIGN}", None),
    ("agenda_events", "PATCH", f"/api/agenda/events/{FOREIGN}", {"title": "hijacked"}),
    ("agenda_events", "DELETE", f"/api/agenda/events/{FOREIGN}", None),
    ("clients", "GET", f"/api/clients/{FOREIGN}", None),
    ("clients", "PATCH", f"/api/clients/{FOREIGN}", {"name": "hijacked"}),
    ("clients", "DELETE", f"/api/clients/{FOREIGN}", None),
    ("leads", "GET", f"/api/crm/leads/{FOREIGN}", None),
    ("leads", "PATCH", f"/api/crm/leads/{FOREIGN}", {"name": "hijacked"}),
    ("leads", "DELETE", f"/api/crm/leads/{FOREIGN}", None),
    ("leads", "GET", f"/api/crm/leads/{FOREIGN}/activities", None),
    ("lead_scoring_rules", "DELETE", f"/api/crm/scoring-rules/{FOREIGN}", None),
    ("content_campaigns", "GET", f"/api/content/campaigns/{FOREIGN}", None),
    ("content_campaigns", "PATCH", f"/api/content/campaigns/{FOREIGN}", {"name": "hijacked"}),
    ("content_campaigns", "DELETE", f"/api/content/campaigns/{FOREIGN}", None),
    ("content_posts", "GET", f"/api/content/posts/{FOREIGN}", None),
    ("content_posts", "PATCH", f"/api/content/posts/{FOREIGN}", {"caption": "hijacked"}),
    ("content_posts", "DELETE", f"/api/content/posts/{FOREIGN}", None),
    ("content_posts", "POST", f"/api/content/posts/{FOREIGN}/approvals", {"expires_in_days": 7}),
    ("content_posts", "GET", f"/api/content/posts/{FOREIGN}/approvals", None),
    ("content_plans", "GET", f"/api/content/plans/{FOREIGN}", None),
    ("content_plans", "PATCH", f"/api/content/plans/{FOREIGN}", {"title": "hijacked"}),
    ("content_plans", "DELETE", f"/api/content/plans/{FOREIGN}", None),
    ("ad_accounts", "GET", f"/api/meta-ads/ad-accounts/{FOREIGN}", None),
    ("ad_accounts", "PATCH", f"/api/meta-ads/ad-accounts/{FOREIGN}", {"name": "hijacked"}),
    ("ad_accounts", "DELETE", f"/api/meta-ads/ad-accounts/{FOREIGN}", None),
    ("campaigns", "GET", f"/api/meta-ads/campaigns/{FOREIGN}", None),
    ("campaigns", "PATCH", f"/api/meta-ads/campaigns/{FOREIGN}", {"name": "hijacked"}),
    ("campaigns", "DELETE", f"/api/meta-ads/campaigns/{FOREIGN}", None),
    ("campaigns", "GET", f"/api/meta-ads/campaigns/{FOREIGN}/metrics", None),
    ("reports", "GET", f"/api/reports/{FOREIGN}", None),
    ("reports", "PATCH", f"/api/reports/{FOREIGN}", {"name": "hijacked"}),
    ("reports", "DELETE", f"/api/reports/{FOREIGN}", None),
    ("reports", "GET", f"/api/reports/{FOREIGN}/snapshots", None),
    ("reports", "POST", f"/api/reports/{FOREIGN}/generate", None),
    ("automation_flows", "GET", f"/api/automation/flows/{FOREIGN}", None),
    ("automation_flows", "PATCH", f"/api/automation/flows/{FOREIGN}", {"name": "hijacked"}),
    ("automation_flows", "DELETE", f"/api/automation/flows/{FOREIGN}", None),
    ("automation_flows", "GET", f"/api/automation/flows/{FOREIGN}/steps", None),
    ("automation_flows", "POST", f"/api/automation/flows/{FOREIGN}/steps", {"ord": 0, "step_type": "end", "config": {}}),
    ("automation_steps", "PATCH", f"/api/automation/steps/{FOREIGN}", {"config": {"x": 1}}),
    ("automation_steps", "DELETE", f"/api/automation/steps/{FOREIGN}", None),
    ("automation_executions", "DELETE", f"/api/automation/executions/{FOREIGN}", None),
    ("content_plans", "POST", f"/api/content/plans/{FOREIGN}/items", {"items": [{"title": "x"}]}),
]

#: What "invisible" looks like per route shape: an id-addressed read/write is a 404; a child LIST of a foreign parent is an empty
#: list (it never leaked, nothing to find); creating a child row under a foreign parent is the 422 foreign-reference refusal.
_EMPTY_LISTS = ("/steps", "/approvals", "/metrics", "/snapshots")


def _expected(method, path):
    if method == "GET" and path.endswith(_EMPTY_LISTS):
        return 200
    if method == "POST" and path.endswith(("/steps", "/approvals")):
        return 422
    return 404


def _seed(client, table):
    client.mock_supabase.set_table_data(table, [{"id": FOREIGN, "org_id": ORG_B, **ROWS[table]}])


def _make_staff(client):
    client.mock_supabase.set_table_data(
        "noctus_users", [{"id": TEST_USER_ID, "org_id": "test-org-123", "org_role": "owner", "role": "user"}])


@pytest.mark.parametrize("table,method,path,body", BY_ID, ids=[f"{m} {p.split('/api/')[1][:40]}" for _t, m, p, _b in BY_ID])
def test_another_orgs_row_is_invisible_and_untouched(client, table, method, path, body):
    _make_staff(client)
    _seed(client, table)
    resp = client.mock_supabase and getattr(client, method.lower())(path, **({"json": body} if body is not None else {}))
    assert resp.status_code == _expected(method, path), f"{method} {path} -> {resp.status_code} {resp.text[:200]}"
    assert LEAK not in resp.text
    if _expected(method, path) == 200:
        assert resp.json() in ([], {"items": []}) or resp.json().get("items") == []
    rows = client.mock_supabase.table(table).select("*").execute().data
    assert rows == [{"id": FOREIGN, "org_id": ORG_B, **ROWS[table]}], "the other org's row was changed or removed"


@pytest.mark.parametrize("path,key", [
    ("/api/tasks", "items"), ("/api/routines", "items"), ("/api/agenda/events", "items"), ("/api/clients", "items"),
    ("/api/crm/leads", "items"), ("/api/content/campaigns", "items"), ("/api/content/posts", "items"),
    ("/api/content/plans", "items"), ("/api/meta-ads/ad-accounts", "items"), ("/api/meta-ads/campaigns", "items"),
    ("/api/reports", "items"), ("/api/automation/flows", "items"), ("/api/automation/executions", "items"),
])
def test_lists_never_contain_another_orgs_rows(client, path, key):
    _make_staff(client)
    for table in ROWS:
        _seed(client, table)
    resp = client.get(path)
    assert resp.status_code == 200, resp.text[:200]
    assert LEAK not in resp.text and FOREIGN not in resp.text


# (path, body-with-a-foreign-id, table of the foreign id)
FOREIGN_REFERENCES = [
    ("/api/crm/leads", {"name": "n", "stage_id": FOREIGN}, "lead_stages"),
    ("/api/crm/leads", {"name": "n", "client_id": FOREIGN}, "clients"),
    ("/api/tasks", {"title": "t", "client_id": FOREIGN}, "clients"),
    ("/api/agenda/events", {"title": "e", "client_id": FOREIGN, "starts_at": "2026-12-01T10:00:00+00:00", "ends_at": "2026-12-01T11:00:00+00:00"}, "clients"),
    ("/api/content/campaigns", {"name": "c", "month": "2026-12", "client_id": FOREIGN}, "clients"),
    ("/api/content/posts", {"platform": "instagram", "campaign_id": FOREIGN}, "content_campaigns"),
    ("/api/content/posts", {"platform": "instagram", "client_id": FOREIGN}, "clients"),
    ("/api/content/plans", {"title": "p", "month": "2026-12", "campaign_id": FOREIGN}, "content_campaigns"),
    ("/api/content/plans", {"title": "p", "month": "2026-12", "client_id": FOREIGN}, "clients"),
    ("/api/meta-ads/ad-accounts", {"external_account_id": "x", "name": "n", "client_id": FOREIGN}, "clients"),
    ("/api/meta-ads/campaigns", {"ad_account_id": FOREIGN, "external_campaign_id": "x", "name": "n"}, "ad_accounts"),
    ("/api/reports", {"name": "r", "period_start": "2026-11-01", "period_end": "2026-11-30", "client_id": FOREIGN}, "clients"),
]


@pytest.mark.parametrize("path,body,table", FOREIGN_REFERENCES, ids=[f"{p} {next(iter(set(b) & {'stage_id','client_id','campaign_id','ad_account_id'}))}" for p, b, _t in FOREIGN_REFERENCES])
def test_a_foreign_id_named_in_the_body_is_refused_422(client, path, body, table):
    _make_staff(client)
    _seed(client, table)
    resp = client.post(path, json=body)
    assert resp.status_code == 422, f"POST {path} -> {resp.status_code} {resp.text[:200]}"
    assert LEAK not in resp.text


def test_updating_a_lead_to_another_orgs_stage_is_422(client):
    _make_staff(client)
    own = "a0000000-0000-4000-8000-000000000001"
    client.mock_supabase.set_table_data("leads", [{"id": own, "org_id": ORG_A, "name": "mine"}])
    client.mock_supabase.set_table_data("lead_stages", [{"id": FOREIGN, "org_id": ORG_B, "name": LEAK, "position": 1}])
    resp = client.patch(f"/api/crm/leads/{own}", json={"stage_id": FOREIGN})
    assert resp.status_code == 422, resp.text[:200]


def test_a_body_cannot_name_an_org(client):
    """org_id comes ONLY from the authenticated context: the strict request models reject the field."""
    _make_staff(client)
    assert client.post("/api/tasks", json={"title": "t", "org_id": ORG_B}).status_code == 422
    assert client.patch(f"/api/tasks/{FOREIGN}", json={"org_id": ORG_B}).status_code == 422


@pytest.mark.parametrize("table,method,path,body", BY_ID[::6], ids=[f"{m} {p.split('/api/')[1][:30]}" for _t, m, p, _b in BY_ID[::6]])
def test_a_customer_role_gets_nothing(client, table, method, path, body):
    client.mock_supabase.set_table_data(
        "noctus_users", [{"id": TEST_USER_ID, "org_id": "test-org-123", "org_role": "membro", "role": "user"}])
    client.mock_supabase.set_table_data(table, [{"id": FOREIGN, "org_id": ORG_A, **ROWS[table]}])
    resp = getattr(client, method.lower())(path, **({"json": body} if body is not None else {}))
    assert resp.status_code == 403, f"{method} {path} -> {resp.status_code}"
    assert LEAK not in resp.text


@pytest.mark.parametrize("path", ["/api/tasks", "/api/crm/leads", "/api/clients", "/api/content/posts", "/api/reports", "/api/automation/flows"])
def test_a_customer_role_cannot_list(client, path):
    client.mock_supabase.set_table_data(
        "noctus_users", [{"id": TEST_USER_ID, "org_id": "test-org-123", "org_role": "membro", "role": "user"}])
    assert client.get(path).status_code == 403
