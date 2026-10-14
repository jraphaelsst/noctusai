"""Recurrences: next-date rule for the 8 frequencies, generation idempotency, catch-up, end date."""
from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.domain.finance import Frequency, calcular_proxima_data, generate_due_recurrences, recurrences
from noctusai_lib.domain.finance.errors import FinanceError

from .conftest import CFG, ORG_B, mk_account


@pytest.mark.parametrize("freq, start, expected", [
    ("daily", date(2026, 2, 28), date(2026, 3, 1)),
    ("weekly", date(2026, 12, 28), date(2027, 1, 4)),
    ("biweekly", date(2026, 1, 1), date(2026, 1, 15)),
    ("monthly", date(2026, 1, 15), date(2026, 2, 15)),
    ("bimonthly", date(2026, 11, 10), date(2027, 1, 10)),
    ("quarterly", date(2026, 1, 31), date(2026, 4, 30)),
    ("semiannual", date(2026, 8, 31), date(2027, 2, 28)),
    ("annual", date(2024, 2, 29), date(2025, 2, 28)),
])
def test_next_date_for_each_frequency(freq, start, expected):
    assert calcular_proxima_data(start, freq) == expected


def test_every_frequency_is_covered():
    for f in Frequency:
        assert calcular_proxima_data(date(2026, 1, 10), f) > date(2026, 1, 10)


def test_monthly_series_keeps_its_anchor_day():
    cur, seen = date(2026, 1, 31), []
    for _ in range(4):
        cur = calcular_proxima_data(cur, "monthly", anchor_day=31)
        seen.append(cur)
    assert seen == [date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30), date(2026, 5, 31)]


def test_unknown_frequency_is_refused():
    with pytest.raises(ValueError):
        calcular_proxima_data(date(2026, 1, 1), "fortnightly")


def make(s, **over):
    body = {
        "template": {"direction": "payable", "description": "Aluguel", "amount_cents": 250000},
        "frequency": "monthly",
        "next_date": "2026-01-31",
    }
    body.update(over)
    return recurrences.create_recurrence(s, body)


def test_create_validates_template_and_stamps_the_anchor(s):
    rec = make(s)
    assert rec["template"]["anchor_day"] == 31 and rec["active"] is True
    with pytest.raises(FinanceError):
        make(s, template={"direction": "payable", "description": "x", "amount_cents": 0})
    with pytest.raises(FinanceError):
        make(s, end_date="2026-01-01")
    with pytest.raises(FinanceError):
        make(s, frequency="never")


def test_template_references_must_belong_to_the_org(s, s_b):
    foreign = mk_account(s_b)
    with pytest.raises(FinanceError) as err:
        make(s, template={"direction": "payable", "description": "x", "amount_cents": 1, "expected_account_id": foreign["id"]})
    assert err.value.details["field"] == "expected_account_id"


def entries_of(s, rec):
    rows = s.rows("entries", eq={"recurrence_id": rec["id"]})
    return sorted(rows, key=lambda r: r["due_date"])


def test_generation_is_idempotent_and_advances_next_date(s):
    rec = make(s)
    result = generate_due_recurrences(s.db, CFG, on=date(2026, 1, 31))
    assert result == {"recurrences": 1, "created": 1, "failed": 0}
    again = generate_due_recurrences(s.db, CFG, on=date(2026, 1, 31))
    assert again["created"] == 0 and again["recurrences"] == 0  # next_date moved past today
    assert len(entries_of(s, rec)) == 1
    e = entries_of(s, rec)[0]
    assert (e["source"], e["source_ref"], e["status"]) == ("recurrence", f"{rec['id']}:2026-01-31", "open")
    assert (e["due_date"], e["competence_month"], e["amount_cents"]) == ("2026-01-31", "2026-01-01", 250000)
    assert s.find("recurrences", rec["id"])["next_date"] == "2026-02-28"


def test_rerun_after_a_crash_before_next_date_moved_does_not_duplicate(s):
    rec = make(s)
    generate_due_recurrences(s.db, CFG, on=date(2026, 1, 31))
    # Crash simulation: the entry exists but next_date was never advanced.
    s.tbl("recurrences").update({"next_date": "2026-01-31"}).eq("id", rec["id"]).execute()
    out = generate_due_recurrences(s.db, CFG, on=date(2026, 1, 31))
    assert out["created"] == 0 and len(entries_of(s, rec)) == 1
    assert s.find("recurrences", rec["id"])["next_date"] == "2026-02-28"


def test_catch_up_generates_every_missed_occurrence_once(s):
    rec = make(s, next_date="2026-01-31")
    out = generate_due_recurrences(s.db, CFG, on=date(2026, 4, 30))
    assert out["created"] == 4
    assert [e["due_date"] for e in entries_of(s, rec)] == ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"]


def test_catch_up_is_capped_per_run(s):
    make(s, frequency="daily", next_date="2020-01-01")
    out = generate_due_recurrences(s.db, CFG, on=date(2026, 1, 1))
    assert out["created"] == recurrences.MAX_CATCHUP_PER_RUN


def test_end_date_stops_and_deactivates(s):
    rec = make(s, next_date="2026-01-10", end_date="2026-02-20")
    generate_due_recurrences(s.db, CFG, on=date(2026, 6, 1))
    assert [e["due_date"] for e in entries_of(s, rec)] == ["2026-01-10", "2026-02-10"]
    assert s.find("recurrences", rec["id"])["active"] is False


def test_inactive_and_future_recurrences_are_ignored(s):
    off = make(s)
    recurrences.update_recurrence(s, off["id"], {"active": False})
    make(s, next_date="2027-01-01")
    out = generate_due_recurrences(s.db, CFG, on=date(2026, 6, 1))
    assert out["recurrences"] == 0 and s.rows("entries") == []


def test_job_spans_orgs_and_keeps_them_apart(s, s_b):
    a, b = make(s), make(s_b)
    generate_due_recurrences(s.db, CFG, on=date(2026, 1, 31))
    assert {e["org_id"] for e in entries_of(s, a)} == {s.org_id}
    assert {e["org_id"] for e in entries_of(s_b, b)} == {ORG_B}


def test_one_bad_recurrence_does_not_starve_the_rest(s):
    good = make(s)
    bad = make(s)
    s.tbl("recurrences").update({"template": {"direction": "payable"}}).eq("id", bad["id"]).execute()  # corrupt template
    out = generate_due_recurrences(s.db, CFG, on=date(2026, 1, 31))
    assert out["failed"] == 1 and out["created"] == 1
    assert len(entries_of(s, good)) == 1


def test_update_template_merges_and_revalidates(s):
    rec = make(s)
    out = recurrences.update_recurrence(s, rec["id"], {"template": {"amount_cents": 300000}})
    assert out["template"]["amount_cents"] == 300000 and out["template"]["description"] == "Aluguel"
    with pytest.raises(FinanceError):
        recurrences.update_recurrence(s, rec["id"], {"frequency": "bogus"})
