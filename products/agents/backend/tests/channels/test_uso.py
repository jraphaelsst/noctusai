"""``GET /api/channels/uso?mes=YYYY-MM`` — the org's channel usage for a month
(Lais w9 Painel): turns + cost vs the org daily cap. Month edges are taken in
America/Sao_Paulo; org comes from the token."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.config import settings
from app.dependencies import SCOPE_CHANNEL_STATUS, SCOPE_CHANNEL_TURN
from tests.channels.conftest import OTHER_ORG


def _put(chan, org_id: UUID, role: str, cost: float | None, at: datetime) -> None:
    store = chan.rt.stores.messages
    conv = uuid4()
    rec = store.add(org_id, conv, role, "x")
    store._rows[(org_id, conv)][-1]["created_at"] = at
    if cost is not None:
        store.set_turn_cost(org_id, conv, rec.id, custo_usd=cost, tokens_entrada=1, tokens_saida=1)


def _uso(chan, mes="2026-10", **kw):
    with chan.as_token(SCOPE_CHANNEL_TURN, **kw):
        return chan.request("GET", f"/api/channels/uso?mes={mes}")


def test_no_credential_is_401(chan):
    chan.seed_agent()
    assert chan.request("GET", "/api/channels/uso?mes=2026-10").status_code == 401


def test_status_scope_does_not_open_uso(chan):
    chan.seed_agent()
    with chan.as_token(SCOPE_CHANNEL_STATUS):
        resp = chan.request("GET", "/api/channels/uso?mes=2026-10")
    assert resp.status_code == 403 and resp.json()["code"] == "scope_missing"


def test_sums_assistant_turns_and_cost_for_the_month(chan):
    chan.seed_agent()
    utc = timezone.utc
    _put(chan, chan.org_id, "assistant", 0.25, datetime(2026, 10, 5, 12, tzinfo=utc))
    _put(chan, chan.org_id, "assistant", 0.5, datetime(2026, 10, 20, 12, tzinfo=utc))
    _put(chan, chan.org_id, "user", None, datetime(2026, 10, 20, 12, tzinfo=utc))  # not a turn
    _put(chan, chan.org_id, "assistant", 9.0, datetime(2026, 9, 5, 12, tzinfo=utc))  # other month
    body = _uso(chan).json()
    assert body == {"turnos": 2, "custo_usd": 0.75, "limite_diario_usd": float(settings.channel_daily_budget_usd)}


def test_month_edges_are_sao_paulo_not_utc(chan):
    chan.seed_agent()
    utc = timezone.utc
    # 2026-11-01 01:00 UTC = 2026-10-31 22:00 SP  -> October
    _put(chan, chan.org_id, "assistant", 1.0, datetime(2026, 11, 1, 1, tzinfo=utc))
    # 2026-10-01 02:00 UTC = 2026-09-30 23:00 SP  -> September
    _put(chan, chan.org_id, "assistant", 2.0, datetime(2026, 10, 1, 2, tzinfo=utc))
    # 2026-11-01 04:00 UTC = 2026-11-01 01:00 SP  -> November
    _put(chan, chan.org_id, "assistant", 4.0, datetime(2026, 11, 1, 4, tzinfo=utc))
    assert _uso(chan, "2026-10").json()["custo_usd"] == 1.0
    assert _uso(chan, "2026-09").json()["custo_usd"] == 2.0
    assert _uso(chan, "2026-11").json()["custo_usd"] == 4.0


def test_org_isolation(chan):
    chan.seed_agent()
    at = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
    _put(chan, OTHER_ORG, "assistant", 7.0, at)
    body = _uso(chan).json()
    assert body["turnos"] == 0 and body["custo_usd"] == 0.0
    other = _uso(chan, org_id=OTHER_ORG).json()
    assert other["turnos"] == 1 and other["custo_usd"] == 7.0


def test_bad_mes_is_422(chan):
    chan.seed_agent()
    for bad in ("2026-13", "202610", "x"):
        resp = _uso(chan, bad)
        assert resp.status_code == 422, bad
