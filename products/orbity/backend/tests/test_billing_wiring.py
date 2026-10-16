"""Billing on the seed organs, wired into Orbity.

Pins: (a) the organ migrations are the generators' output and numbered in dependency order; (b) every organ + billing
route is mounted and strictly 401 without auth; (c) the jobs are on the scheduler; (d) the seed contracts billing run, fed
through ``OrbityContractsBilling``, books the monthly receivable ONCE per contract + cycle and records the gateway state;
(e) the body-limit overrides the organs need are covered. Collaborators swap through DI / Fakes -- nothing is patched.
"""
import json
from datetime import date
from pathlib import Path

import pytest
from noctusai_lib.domain.commerce.gateway import FakeCheckoutGateway
from noctusai_lib.domain.contracts import contracts_generate_billing, contracts_migration
from noctusai_lib.testing import MockSupabaseClient
from noctusai_lib.testing.migrations import migrations_dir
from noctusai_lib.testing.organs import assert_organ_migration_current, find_organ_migration

from app.billing import CONTRACTS_CFG, FINANCE_CFG, SCHEMA
from app.services.billing_charges import OrbityContractsBilling

PRODUCT_DIR = Path(__file__).resolve().parents[1]
UUID0 = "00000000-0000-0000-0000-000000000000"
ORG = "00000000-0000-0000-0000-000000000abc"
CLIENT = "c1000000-0000-4000-8000-000000000001"
CONTRACT = "d1000000-0000-4000-8000-000000000001"


def test_finance_migration_is_the_generators_output():
    assert_organ_migration_current(PRODUCT_DIR, "finance", schema=SCHEMA)


def test_contracts_migration_is_the_generators_output_for_this_hosts_config():
    # Orbity mounts no parties/items organ, so the registry's LINKED rendering does not apply: pin the host's own config.
    from noctusai_seed.organs import ORGAN_REGISTRY

    (path,) = find_organ_migration(PRODUCT_DIR, ORGAN_REGISTRY["contracts"].migration_header)
    assert path.read_text(encoding="utf-8") == contracts_migration(CONTRACTS_CFG, SCHEMA)
    assert "party_id                UUID," in path.read_text(encoding="utf-8"), "party_id is a plain UUID here (clients.id)"
    assert "REFERENCES orbity.pty_parties" not in path.read_text(encoding="utf-8")


def test_migrations_are_numbered_in_dependency_order():
    from noctusai_seed.organs import ORGAN_REGISTRY

    num = lambda p: int(p.name.split("_", 1)[0])  # noqa: E731
    (fin,) = find_organ_migration(PRODUCT_DIR, ORGAN_REGISTRY["finance"].migration_header)
    (ctr,) = find_organ_migration(PRODUCT_DIR, ORGAN_REGISTRY["contracts"].migration_header)
    (delta,) = [p for p in migrations_dir(PRODUCT_DIR).glob("*.sql") if "billing_on_seed_organs" in p.name]
    assert num(fin) < num(ctr) < num(delta)  # contracts widens fin_entries.source; the data move needs both organs


def test_applied_migrations_were_not_rewritten():
    import hashlib

    applied = json.loads((PRODUCT_DIR / "migrations-applied.json").read_text(encoding="utf-8"))["applied"]
    for name, digest in applied.items():
        assert hashlib.sha256((migrations_dir(PRODUCT_DIR) / name).read_bytes()).hexdigest() == digest, name
    numbers = [int(p.name.split("_", 1)[0]) for p in migrations_dir(PRODUCT_DIR).glob("*.sql")]
    assert len(numbers) == len(set(numbers)), "two migrations share a number"


def _routes(app) -> set[tuple[str, str]]:
    return {(m, r.path) for r in app.routes if hasattr(r, "methods") for m in r.methods}


ORGAN_ROUTES = [
    ("GET", "/api/finance/entries"), ("POST", "/api/finance/entries"), ("GET", "/api/finance/reports/dre"),
    ("GET", "/api/contracts"), ("POST", "/api/contracts"), ("POST", "/api/contracts/{contract_id}/activate"),
    ("POST", "/api/contracts/{contract_id}/suspend"), ("POST", "/api/contracts/{contract_id}/terminate"),
    ("GET", "/api/contracts/{contract_id}/billing-preview"), ("POST", "/api/contracts/billing/run"),
]
BILLING_ROUTES = [
    ("GET", "/api/financial/charges"), ("POST", "/api/financial/charges"), ("POST", "/api/financial/charges/{entry_id}/generate"),
    ("GET", "/api/financial/cash-flow/{month}"), ("GET", "/api/financial/gateway"),
    ("POST", "/api/clients/{client_id}/archive"), ("GET", "/api/clients/{client_id}/offboarding-preview"),
    ("GET", "/api/clients/cnpj/{cnpj}"), ("POST", "/api/billing/webhook/asaas/{org_id}"),
]


@pytest.mark.parametrize("method,path", ORGAN_ROUTES + BILLING_ROUTES)
def test_route_is_mounted(client, method, path):
    from app.main import app

    assert (method, path) in _routes(app), f"{method} {path} is not mounted"


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/finance/entries"), ("POST", "/api/finance/entries"), ("GET", "/api/finance/reports/dre"),
    ("GET", "/api/contracts"), ("POST", "/api/contracts"), ("GET", f"/api/contracts/{UUID0}"),
    ("POST", f"/api/contracts/{UUID0}/activate"), ("POST", f"/api/contracts/{UUID0}/terminate"),
    ("POST", "/api/contracts/billing/run"),
])
def test_organ_routes_are_strictly_401_without_auth(client, method, path):
    assert client.raw().request(method, path).status_code == 401


def test_contract_writes_need_an_org_admin(client):
    assert client.post("/api/contracts", json={}).status_code == 403
    assert client.post(f"/api/contracts/{UUID0}/terminate", json={}).status_code == 403
    assert client.post("/api/contracts/billing/run").status_code == 403
    assert client.get("/api/contracts").status_code == 200


def test_the_billing_jobs_ride_on_the_seed_scheduler():
    from noctusai_lib.api import scheduler as seed_scheduler

    from app.scheduler import configure

    configure()
    ids = {j.id for j in seed_scheduler.scheduler.get_jobs()}
    assert {"contracts_generate_billing", "orbity_billing_process", "finance_generate_recurrences",
            "orbity_automacao_run_due", "orbity_rotinas_run_due"} <= ids


def test_the_upload_surface_of_the_organs_is_covered_by_a_body_override():
    from app.main import app  # noqa: F401  (boot refuses an UploadFile route without a covering override)
    from noctusai_lib.domain.contracts import ATTACHMENT_UPLOAD_PATH_PATTERN
    from noctusai_lib.domain.finance import ATTACHMENT_UPLOAD_PATH_PATTERN as FIN_ATTACHMENT

    from app.routers.organs import contracts_organ, finance_organ

    assert ATTACHMENT_UPLOAD_PATH_PATTERN in contracts_organ.max_body_path_overrides
    assert FIN_ATTACHMENT in finance_organ.max_body_path_overrides


# ── the seed billing run, through Orbity's billing seam ─────────────────────────────────────────────────────


def _db(client_over=None):
    db = MockSupabaseClient(schema=SCHEMA)
    db.set_table_data("clients", [{"id": CLIENT, "org_id": ORG, "name": "Acme", "legal_name": "Acme LTDA", "document": "11222333000181",
                                   "email": "fin@acme.com", "active": True, "default_billing_type": "pix",
                                   "billing_automation_enabled": True, **(client_over or {})}])
    db.set_table_data("ctr_contracts", [{
        "id": CONTRACT, "org_id": ORG, "title": "Gestão de tráfego", "party_id": CLIENT, "party_name": "Acme LTDA", "party_doc": "11222333000181",
        "status": "active", "billing_model": "recurring", "amount_cents": 150_000, "frequency": "monthly", "due_day": 20,
        "first_due_date": "2026-10-20", "next_period_on": "2026-10-20", "start_date": "2026-10-01", "end_date": None,
        "auto_renew": False, "version_n": 1}])
    for t in ("ctr_contract_billings", "fin_entries", "fin_categories", "billing_charges"):
        db.set_table_data(t, [])
    return db


class TestTheBillingRunBooksOncePerContractAndCycle:
    def _run(self, db, *, configured=True, on=date(2026, 10, 16)):
        billing = OrbityContractsBilling(db, gateway=FakeCheckoutGateway(configured=configured))
        return contracts_generate_billing(db, CONTRACTS_CFG, billing, on=on)

    def test_the_monthly_receivable_is_booked_with_its_gateway_state(self):
        db = _db()
        summary = self._run(db)
        assert summary["failed"] == 0 and summary["created"] >= 1
        entries = db.table("fin_entries")._data
        assert entries and all(e["source"] == "contracts" and e["direction"] == "receivable" for e in entries)
        assert entries[0]["source_ref"] == f"{CONTRACT}:2026-10-20" and entries[0]["amount_cents"] == 150_000
        charges = db.table("billing_charges")._data
        assert len(charges) == len(entries)
        first = next(c for c in charges if c["entry_id"] == entries[0]["id"])
        assert first["client_id"] == CLIENT and first["contract_id"] == CONTRACT
        assert first["generation_status"] == "queued" and first["billing_method"] == "pix"
        assert first["external_ref"] == f"orbity:{entries[0]['id']}"

    def test_a_second_run_creates_nothing_new(self):
        db = _db()
        self._run(db)
        n_entries, n_charges = len(db.table("fin_entries")._data), len(db.table("billing_charges")._data)
        again = self._run(db)
        assert again["created"] == 0
        assert (len(db.table("fin_entries")._data), len(db.table("billing_charges")._data)) == (n_entries, n_charges)

    def test_with_no_gateway_the_receivable_is_plain_and_honest(self):
        db = _db()
        self._run(db, configured=False)
        (first, *_) = db.table("billing_charges")._data
        assert first["generation_status"] == "skipped" and "não configurado" in first["last_error"]

    def test_a_client_who_opted_out_of_automation_is_skipped_with_the_reason(self):
        db = _db({"billing_automation_enabled": False})
        self._run(db)
        (first, *_) = db.table("billing_charges")._data
        assert first["generation_status"] == "skipped" and "desligada" in first["last_error"]
