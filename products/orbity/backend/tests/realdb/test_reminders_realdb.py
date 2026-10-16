"""Real-DB checks for migration 024 (billing reminders / dunning organ).

REQUIRES 019/021/023/024 applied; every test skips cleanly when ``fin_reminder_rules`` is absent or Supabase creds are
unset. The tech-lead applies the migration at integration time. The SAME properties run on every merge on PGlite in
``mcp/noctusai/tests/test_orbity_finance_reminders_on_replay.py``; this file proves them on the live project once applied.
"""
from __future__ import annotations

from datetime import date

import pytest

pytestmark = pytest.mark.realdb


@pytest.fixture(scope="module", autouse=True)
def _require_reminders_migration(fin_db):
    try:
        fin_db.table("fin_reminder_rules").select("id").limit(1).execute()
        fin_db.table("fin_entries").select("reminders_opt_out").limit(1).execute()
    except Exception as exc:  # noqa: BLE001 -- PGRST205/42703 => not applied yet
        pytest.skip(f"reminders migration not applied: {type(exc).__name__}")


@pytest.fixture
def seeded(fin_db, test_org_a):
    org = test_org_a["id"]
    entry = fin_db.table("fin_entries").insert({
        "org_id": org, "direction": "receivable", "description": "RT lembrete", "competence_month": date.today().replace(day=1).isoformat(),
        "due_date": "2026-10-20", "amount_cents": 1000}).execute().data[0]
    rule = fin_db.table("fin_reminder_rules").insert({"org_id": org, "channel": "whatsapp", "offset_days": 0, "template": "Oi {nome}"}).execute().data[0]
    yield org, entry, rule
    fin_db.table("fin_reminder_log").delete().eq("rule_id", rule["id"]).execute()
    fin_db.table("fin_reminder_rules").delete().eq("id", rule["id"]).execute()
    fin_db.table("fin_entries").delete().eq("id", entry["id"]).execute()


def _log(org, entry, rule, **over):
    return {"org_id": org, "entry_id": entry["id"], "rule_id": rule["id"], "channel": "whatsapp", "offset_days": 0,
            "cycle_date": "2026-10-20", "status": "pending", "recipient": "5511999998888", "message": "x", **over}


def test_new_receivables_are_not_opted_out(seeded):
    _, entry, _ = seeded
    assert entry["reminders_opt_out"] is False


def test_the_dedup_ledger_rejects_a_second_row_for_the_same_slot(fin_db, seeded):
    org, entry, rule = seeded
    fin_db.table("fin_reminder_log").insert(_log(org, entry, rule)).execute()
    with pytest.raises(Exception) as exc:
        fin_db.table("fin_reminder_log").insert(_log(org, entry, rule)).execute()
    assert "23505" in str(exc.value) or "duplicate" in str(exc.value).lower()


def test_a_rule_with_history_cannot_be_deleted(fin_db, seeded):
    org, entry, rule = seeded
    fin_db.table("fin_reminder_log").insert(_log(org, entry, rule)).execute()
    with pytest.raises(Exception) as exc:
        fin_db.table("fin_reminder_rules").delete().eq("id", rule["id"]).execute()
    assert "23503" in str(exc.value) or "foreign key" in str(exc.value).lower()


def test_org_a_reminder_rules_are_invisible_to_an_anon_client(anon_fin_db, seeded):
    org, *_ = seeded
    assert anon_fin_db.table("fin_reminder_rules").select("id").eq("org_id", org).execute().data == []
