"""`TurnRequest.remetente`: the closed enum rides the wire only when set (an older agents build keeps accepting turns)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from noctusai_lib.integrations.agents_channel import REMETENTES, TurnMessage, TurnRequest


def _req(**kw):
    m = TurnMessage(texto="oi", provider_message_id="m1", at=datetime(2026, 11, 12, tzinfo=timezone.utc))
    return TurnRequest(agent_key="a", connection_id="c", chat_id="x", messages=(m,), **kw)


def test_absent_key_when_unknown():
    assert "remetente" not in _req().to_wire()


@pytest.mark.parametrize("v", REMETENTES)
def test_enum_values_ride_the_wire(v):
    assert _req(remetente=v).to_wire()["remetente"] == v


def test_a_non_enum_value_is_refused_client_side():
    with pytest.raises(ValueError):
        _req(remetente="admin").to_wire()
