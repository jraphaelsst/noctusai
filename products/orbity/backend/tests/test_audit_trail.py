"""Acting-staff writes leave an audit row (F8 of the 034 security review).

Once the tenant tables are service-only, platform staff acting in an agency org (the org picker) really read and write
its data. The seed stashes the ACTING actor (`acting_audit_actor`: target org, home org, selection id, role
`platform_support`) on `request.state.audit_actor`; the seed `AuditMiddleware` records every mutating request with it, but is
inert unless `audit_trail_enabled`. Orbity switches it on; the tagging itself is the seed's (tests/api/auth/test_org_selection.py).
"""
from noctusai_lib.testing import TEST_USER_ID

from app.config import settings
from app.dependencies import coerce_org_uuid

ORG = str(coerce_org_uuid("test-org-123"))


def test_the_audit_trail_is_switched_on_for_orbity():
    assert settings.audit_trail_enabled is True


def test_a_write_is_recorded_with_its_actor_and_org(client):
    from app.main import app

    client.mock_supabase.set_table_data(
        "noctus_users", [{"id": TEST_USER_ID, "org_id": ORG, "org_role": "owner", "role": "user"}])
    sink = app.state.audit_sink
    before = len(sink.entries)
    client.post("/api/tasks", json={"title": "audited"})
    new = sink.entries[before:]
    assert [(e.method, e.route_template) for e in new] == [("POST", "/api/tasks")]
    assert new[0].actor is not None and str(new[0].actor.user_id) == str(TEST_USER_ID)
    assert str(new[0].actor.org_id) == ORG
