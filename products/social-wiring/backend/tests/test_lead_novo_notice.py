"""`lead_novo` OPERATIONAL notice: one seam (create_lead), admins only, never fails the lead."""
from unittest.mock import patch
from uuid import uuid4

from noctusai_lib.testing import MockSupabaseClient

from app.modules.leads.importer import import_service
from app.modules.leads.services import lead_notice, leads_service

ORG = uuid4()
CORE_PATCH = "noctusai_seed.database.DatabaseModule.get_core_client"


def _core():
    db = MockSupabaseClient(schema="public")
    db.set_table_data("noctus_users", [
        {"id": "adm", "org_id": str(ORG), "org_role": "admin"},
        {"id": "mem", "org_id": str(ORG), "org_role": "member"},
    ])
    db.set_table_data("org_memberships", [])
    db.set_table_data("notifications", [])
    return db


def _notifs(core):
    return core.table("notifications").select("*").execute().data


def _payload(**kw):
    return {"cliente_nome": "Ana Souza", "contato": "+5511999990000", "codigo_imovel": "AP1", "origem_raw": "Meta", **kw}


def test_create_lead_notifies_admins_only_once_with_pii_free_message():
    core, sw = _core(), MockSupabaseClient(schema="social_wiring")
    with patch(CORE_PATCH, return_value=core):
        lead = leads_service.create_lead(sw, ORG, _payload())
    rows = _notifs(core)
    assert [r["user_id"] for r in rows] == ["adm"]
    r = rows[0]
    assert r["title"] == "Novo lead: Ana Souza" and "AP1" in r["message"]
    assert "5511" not in r["message"] and "5511" not in r["title"]
    assert r["metadata"]["tipo"] == "lead_novo" and r["metadata"]["categoria"] == "operacional"
    assert r["metadata"]["entidade"] == {"tipo": "lead", "id": str(lead["id"])}


def test_notificar_false_is_silent():
    core = _core()
    with patch(CORE_PATCH, return_value=core):
        leads_service.create_lead(MockSupabaseClient(schema="social_wiring"), ORG, _payload(), notificar=False)
    assert _notifs(core) == []


def test_emission_failure_never_fails_lead_creation():
    class Boom:
        def table(self, *_):
            raise RuntimeError("core down")
    with patch(CORE_PATCH, return_value=Boom()):
        lead = leads_service.create_lead(MockSupabaseClient(schema="social_wiring"), ORG, _payload())
    assert lead["cliente_nome"] == "Ana Souza"


def test_no_admin_recipient_logs_warning_and_lead_still_created(caplog):
    core = _core()
    core.set_table_data("noctus_users", [])
    with patch(CORE_PATCH, return_value=core), caplog.at_level("WARNING"):
        lead = leads_service.create_lead(MockSupabaseClient(schema="social_wiring"), ORG, _payload())
    assert lead["id"] and _notifs(core) == []
    assert any("no owner/admin recipient" in r.message for r in caplog.records)


def test_import_summary_is_one_notice_and_silent_at_zero():
    core = _core()
    with patch(CORE_PATCH, return_value=core):
        assert lead_notice.avisar_importacao(ORG, 0) == 0
        assert lead_notice.avisar_importacao(ORG, 12) == 1
    rows = _notifs(core)
    assert len(rows) == 1 and rows[0]["title"] == "12 leads importados"
    assert rows[0]["metadata"]["tipo"] == "leads_importados"


def test_importer_does_not_route_rows_through_create_lead():
    # the bulk path inserts rows itself, so per-row notices cannot stack on its summary
    import inspect
    assert "create_lead(" not in inspect.getsource(import_service.commit)


def test_julia_source_lead_does_not_double_notify():
    # Julia's hand-off already notifies with richer routing; lead_novo would duplicate it
    core, sw = _core(), MockSupabaseClient(schema="social_wiring")
    src = str(uuid4())
    sw.set_table_data("lead_sources", [{"id": src, "org_id": str(ORG), "slug": "julia", "label": "Julia"}])
    with patch(CORE_PATCH, return_value=core):
        leads_service.create_lead(sw, ORG, _payload(origem_id=src, origem_raw="Julia"))
    assert _notifs(core) == []
