"""F77 — a lead's DATE `data_entrada` must reach the timeline as a date.

The touch row stores it as timestamptz at midnight UTC; a UTC-3 client then
rendered the PREVIOUS day at 21:00. The gatherer serialises it back as a date.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.modules.card_hub.timeline_service import _touch_ocorrido_em


def _row(origem: str, ocorreu_em: str) -> dict:
    return {"origem_tabela": origem, "ocorreu_em": ocorreu_em}


def test_lead_touch_is_serialised_as_bare_date():
    assert _touch_ocorrido_em(_row("leads", "2026-10-24T00:00:00+00:00")) == "2026-10-24"
    assert _touch_ocorrido_em(_row("leads", "2026-10-24T00:00:00Z")) == "2026-10-24"


def test_date_never_shifts_in_utc_minus_3():
    out = _touch_ocorrido_em(_row("leads", "2026-10-24T00:00:00+00:00"))
    # Interpreting the value as a calendar date in UTC-3 keeps the same day.
    assert datetime.strptime(out, "%Y-%m-%d").date().isoformat() == "2026-10-24"
    shifted = datetime(2026, 10, 24, tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=-3)))
    assert shifted.day == 23  # the bug the bare date avoids


def test_real_timestamp_sources_are_untouched():
    ts = "2026-10-24T14:41:00+00:00"
    assert _touch_ocorrido_em(_row("meta_ads_leads", ts)) == ts


def test_lead_touch_with_real_time_keeps_it():
    ts = "2026-08-01T10:00:00+00:00"
    assert _touch_ocorrido_em(_row("leads", ts)) == ts
