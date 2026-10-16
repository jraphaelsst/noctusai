"""Real-DB checks for migrations 019/021/023 (billing on the seed organs).

REQUIRES the three migrations applied; every test skips cleanly when `billing_charges` is absent or Supabase creds are
unset. The tech-lead applies the migrations at integration time. The SAME properties are proved on every merge on PGlite by
``mcp/noctusai/tests/test_orbity_billing_migration_on_replay.py``; this file proves them on the live project once applied.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

pytestmark = pytest.mark.realdb


@pytest.fixture(scope="module", autouse=True)
def _require_billing_migration(fin_db):
    try:
        fin_db.table("billing_charges").select("id").limit(1).execute()
        fin_db.table("fin_entries").select("id").limit(1).execute()
        fin_db.table("clients").select("legal_name").limit(1).execute()
    except Exception as exc:  # noqa: BLE001 -- PGRST205/42703 => not applied yet
        pytest.skip(f"billing migrations not applied: {type(exc).__name__}")


@pytest.fixture
def seeded(fin_db, test_org_a):
    org = test_org_a["id"]
    client = fin_db.table("clients").insert({"org_id": org, "name": "RT", "legal_name": "RT LTDA"}).execute().data[0]

    def entry(due):
        return fin_db.table("fin_entries").insert({
            "org_id": org, "direction": "receivable", "description": "RT", "competence_month": date.today().replace(day=1).isoformat(),
            "due_date": due, "amount_cents": 1000}).execute().data[0]

    e1, e2 = entry("2026-10-10"), entry("2026-10-20")
    for e in (e1, e2):
        fin_db.table("billing_charges").insert({
            "org_id": org, "entry_id": e["id"], "client_id": client["id"], "external_ref": f"orbity:{e['id']}",
            "generation_status": "skipped"}).execute()
    yield org, client, e1, e2
    for e in (e1, e2):
        fin_db.table("fin_entries").delete().eq("id", e["id"]).execute()  # cascades billing_charges
    fin_db.table("clients").delete().eq("id", client["id"]).execute()


def test_legal_name_is_required(fin_db, test_org_a):
    with pytest.raises(Exception) as exc:
        fin_db.table("clients").insert({"org_id": test_org_a["id"], "name": "sem razão"}).execute()
    assert "23502" in str(exc.value) or "null" in str(exc.value).lower()


def test_one_charge_row_per_receivable(fin_db, seeded):
    org, client, e1, _ = seeded
    with pytest.raises(Exception) as exc:
        fin_db.table("billing_charges").insert({"org_id": org, "entry_id": e1["id"], "external_ref": f"dup:{uuid.uuid4()}"}).execute()
    assert "23505" in str(exc.value) or "duplicate" in str(exc.value).lower()


def test_offboarding_is_all_or_nothing(fin_db, seeded):
    org, client, e1, e2 = seeded
    with pytest.raises(Exception):  # e2 undecided
        fin_db.rpc("offboard_client", {"p_org_id": org, "p_client_id": client["id"],
                                       "p_cancel_entry_ids": [e1["id"]], "p_preserve_entry_ids": []}).execute()
    assert fin_db.table("clients").select("active").eq("id", client["id"]).execute().data[0]["active"] is True
    assert fin_db.table("fin_entries").select("status").eq("id", e1["id"]).execute().data[0]["status"] == "open"

    out = fin_db.rpc("offboard_client", {"p_org_id": org, "p_client_id": client["id"],
                                         "p_cancel_entry_ids": [e1["id"]], "p_preserve_entry_ids": [e2["id"]]}).execute().data
    assert out["cancelled"] == 1 and out["preserved"] == 1
    assert fin_db.table("fin_entries").select("status").eq("id", e1["id"]).execute().data[0]["status"] == "cancelled"
    kept = fin_db.table("billing_charges").select("preserved_after_deactivation").eq("entry_id", e2["id"]).execute().data[0]
    assert kept["preserved_after_deactivation"] is True
    row = fin_db.table("clients").select("active,inactivated_at").eq("id", client["id"]).execute().data[0]
    assert row["active"] is False and row["inactivated_at"]


def test_the_compat_views_answer_the_old_shape(fin_db, seeded):
    org, _, e1, _ = seeded
    rows = fin_db.table("revenues").select("id,amount,status,client_id").eq("id", e1["id"]).execute().data
    assert rows and rows[0]["amount"] == 10.0 and rows[0]["status"] in ("pending", "overdue")


def test_org_a_charges_are_invisible_to_an_anon_client(anon_fin_db, seeded):
    org, *_ = seeded
    assert anon_fin_db.table("billing_charges").select("id").eq("org_id", org).execute().data == []
