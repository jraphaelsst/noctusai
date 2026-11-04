"""Operational-notice helpers: recipients = org owners + admins, never raises."""
import logging

from noctusai_lib.domain.notifications import notify_org_admins, resolve_org_admin_user_ids
from noctusai_lib.testing import MockSupabaseClient

ORG, OTHER = "org-1", "org-2"


def _db():
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data("noctus_users", [
        {"id": "owner", "org_id": ORG, "org_role": "owner"},
        {"id": "adm", "org_id": ORG, "org_role": "admin"},
        {"id": "mem", "org_id": ORG, "org_role": "member"},
        {"id": "foreign", "org_id": OTHER, "org_role": "admin"},
    ])
    db.set_table_data("org_memberships", [
        {"id": "m1", "user_id": "multi", "org_id": ORG, "org_role": "admin", "status": "active"},
        {"id": "m2", "user_id": "gone", "org_id": ORG, "org_role": "admin", "status": "inactive"},
    ])
    db.set_table_data("notifications", [])
    return db


def test_recipients_are_owners_and_admins_of_that_org_only():
    assert resolve_org_admin_user_ids(_db(), ORG) == ["adm", "multi", "owner"]


def test_notify_writes_neutral_operational_row_per_admin():
    db = _db()
    n = notify_org_admins(db, org_id=ORG, kind="lead_novo", title="Novo lead: Ana", message="Meta",
                          produto="social-wiring", link="/leads", entidade={"tipo": "lead", "id": "l1"})
    assert n == 3
    rows = db.table("notifications").select("*").execute().data
    assert {r["user_id"] for r in rows} == {"adm", "multi", "owner"}
    r = rows[0]
    assert r["type"] == "system" and r["org_id"] == ORG
    assert r["metadata"] == {"categoria": "operacional", "link": "/leads", "produto": "social-wiring",
                             "entidade": {"tipo": "lead", "id": "l1"}, "tipo": "lead_novo"}


def test_title_and_message_are_capped():
    db = _db()
    notify_org_admins(db, org_id=ORG, kind="k", title="t" * 99, message="m" * 300, produto="p")
    r = db.table("notifications").select("*").execute().data[0]
    assert len(r["title"]) == 60 and len(r["message"]) == 160


def test_empty_recipient_set_warns_and_returns_zero(caplog):
    with caplog.at_level(logging.WARNING):
        assert notify_org_admins(_db(), org_id="nobody", kind="lead_novo", title="t", message="m", produto="p") == 0
    assert any("no owner/admin recipient" in r.message for r in caplog.records)


def test_failure_never_raises(caplog):
    class Boom:
        def table(self, *_):
            raise RuntimeError("db down")
    assert notify_org_admins(Boom(), org_id=ORG, kind="k", title="t", message="m", produto="p") == 0
    assert any(r.levelno == logging.ERROR for r in caplog.records)
