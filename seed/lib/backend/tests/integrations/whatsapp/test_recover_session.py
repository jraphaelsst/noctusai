"""WahaClient.recover_session — the start→restart→logout+start escalation
ladder used to unstick a session outside {SCAN_QR_CODE, WORKING}.

Root-cause proof (live fleet, 2026-08): the `default` session carries stored
credentials (`me` populated) but is FAILED; `POST /restart` retries those
dead credentials and hangs in STARTING for ~5 minutes before WAHA force-stops
it back to FAILED — only `logout` clears the stored credentials so NOWEB can
re-enter SCAN_QR_CODE. These tests isolate the LADDER'S ORCHESTRATION via
method-level mocks (each rung's own HTTP wire shape is covered elsewhere:
`_session_config` tests in test_client.py, identity/session tests in
test_client_identity.py).

Every call passes ``settle_seconds=0``: `_poll_until_ready`'s deadline is
then `time.monotonic()` at entry (no budget), so after its single
``await get_session()`` real time has already advanced past the deadline —
the retry-loop condition (`elapsed < deadline`) is always false on the first
check, so the loop body (with its real `asyncio.sleep(0.5)`) never runs. That
makes each rung consume EXACTLY one `get_session()` read via
`_poll_until_ready`, so the mocked ``get_session`` `side_effect` lists below
can be read as one literal call-by-call trace of the ladder — no timing
flakiness, no real sleeping.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from unittest.mock import AsyncMock

from noctusai_lib.integrations.whatsapp.client import WahaClient


def _conflict(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://waha.test/x")
    return httpx.HTTPStatusError(
        f"{status_code} conflict",
        request=request,
        response=httpx.Response(status_code, request=request),
    )


# ---- rung 1: already WORKING -------------------------------------------------


def test_recover_session_returns_immediately_when_already_working() -> None:
    client = WahaClient(base_url="https://waha.test", api_key="k")
    client.get_session = AsyncMock(  # type: ignore[method-assign]
        return_value={"status": "WORKING", "me": {"id": "5511999999999@c.us"}}
    )
    client.start_session = AsyncMock()  # type: ignore[method-assign]

    result = asyncio.run(client.recover_session())

    assert result == {
        "status": "WORKING",
        "stage": "already_working",
        "paired": True,
        "me": {"id": "5511999999999@c.us"},
    }
    client.start_session.assert_not_called()


def test_recover_session_does_not_short_circuit_on_initial_scan_qr_code() -> None:
    """Rung 1 only short-circuits on WORKING (per the documented ladder) —
    an initial SCAN_QR_CODE still proceeds through start_session, it does
    not count as "already recovered" on its own."""
    client = WahaClient(base_url="https://waha.test", api_key="k")
    client.get_session = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            {"status": "SCAN_QR_CODE", "me": None},  # initial read
            {"status": "SCAN_QR_CODE", "me": None},  # poll after start_session
        ]
    )
    client.start_session = AsyncMock(return_value={"status": "SCAN_QR_CODE"})  # type: ignore[method-assign]

    result = asyncio.run(client.recover_session(settle_seconds=0))

    assert result["stage"] == "start"
    client.start_session.assert_awaited_once()


# ---- rung 2: start_session converges -----------------------------------------


def test_recover_session_converges_at_start_for_never_paired_session() -> None:
    client = WahaClient(base_url="https://waha.test", api_key="k")
    client.get_session = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            {"status": "STOPPED", "me": None},
            {"status": "SCAN_QR_CODE", "me": None},
        ]
    )
    client.start_session = AsyncMock(return_value={"status": "SCAN_QR_CODE"})  # type: ignore[method-assign]
    client.restart_session = AsyncMock()  # type: ignore[method-assign]
    client.logout_session = AsyncMock()  # type: ignore[method-assign]

    result = asyncio.run(client.recover_session(settle_seconds=0))

    assert result == {
        "status": "SCAN_QR_CODE",
        "stage": "start",
        "paired": False,
        "me": None,
    }
    client.restart_session.assert_not_called()
    client.logout_session.assert_not_called()


# ---- rung 3: restart_session converges ---------------------------------------


def test_recover_session_escalates_to_restart_when_start_does_not_settle() -> None:
    client = WahaClient(base_url="https://waha.test", api_key="k")
    client.get_session = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            {"status": "STARTING", "me": None},
            {"status": "STARTING", "me": None},
            {"status": "WORKING", "me": {"id": "5511999999999@c.us"}},
        ]
    )
    client.start_session = AsyncMock(return_value={"status": "STARTING"})  # type: ignore[method-assign]
    client.restart_session = AsyncMock(return_value={"status": "WORKING"})  # type: ignore[method-assign]
    client.logout_session = AsyncMock()  # type: ignore[method-assign]

    result = asyncio.run(client.recover_session(settle_seconds=0))

    assert result["stage"] == "restart"
    assert result["status"] == "WORKING"
    assert result["paired"] is True
    client.logout_session.assert_not_called()


def test_recover_session_tolerates_expected_409_on_restart() -> None:
    """restart_session raising WAHA's documented 409 'already restarting'
    must NOT propagate — recover_session polls get_session for the truth
    instead of trusting the admin call's own response."""
    client = WahaClient(base_url="https://waha.test", api_key="k")
    client.get_session = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            {"status": "STARTING", "me": None},
            {"status": "STARTING", "me": None},
            {"status": "SCAN_QR_CODE", "me": None},
        ]
    )
    client.start_session = AsyncMock(return_value={"status": "STARTING"})  # type: ignore[method-assign]
    client.restart_session = AsyncMock(side_effect=_conflict(409))  # type: ignore[method-assign]
    client.logout_session = AsyncMock()  # type: ignore[method-assign]

    result = asyncio.run(client.recover_session(settle_seconds=0))

    assert result["stage"] == "restart"
    assert result["status"] == "SCAN_QR_CODE"
    client.logout_session.assert_not_called()


# ---- rung 4: logout+start converges (the live-fleet FAILED-with-dead-creds bug) --


def test_recover_session_escalates_to_logout_start_when_restart_does_not_settle() -> None:
    """The exact live-fleet bug this ladder was built for: a session with
    stored (dead) credentials stays FAILED through both start AND
    restart; only logout+start clears it."""
    client = WahaClient(base_url="https://waha.test", api_key="k")
    client.get_session = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            {"status": "FAILED", "me": {"id": "5511992694172@c.us"}},  # initial
            {"status": "FAILED", "me": {"id": "5511992694172@c.us"}},  # after start
            {"status": "FAILED", "me": {"id": "5511992694172@c.us"}},  # after restart
            {"status": "SCAN_QR_CODE", "me": None},  # after logout+start
        ]
    )
    client.start_session = AsyncMock(return_value={"status": "FAILED"})  # type: ignore[method-assign]
    client.restart_session = AsyncMock(return_value={"status": "FAILED"})  # type: ignore[method-assign]
    client.logout_session = AsyncMock(return_value={"status": "SCAN_QR_CODE"})  # type: ignore[method-assign]

    result = asyncio.run(client.recover_session(settle_seconds=0))

    assert result == {
        "status": "SCAN_QR_CODE",
        "stage": "logout_start",
        "paired": False,
        "me": None,
    }
    client.logout_session.assert_awaited_once()
    assert client.start_session.await_count == 2  # rung 2, then rung 4 post-logout


def test_recover_session_tolerates_expected_422_on_logout() -> None:
    client = WahaClient(base_url="https://waha.test", api_key="k")
    client.get_session = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            {"status": "FAILED", "me": {"id": "5511992694172@c.us"}},
            {"status": "FAILED", "me": {"id": "5511992694172@c.us"}},
            {"status": "FAILED", "me": {"id": "5511992694172@c.us"}},
            {"status": "SCAN_QR_CODE", "me": None},
        ]
    )
    client.start_session = AsyncMock(return_value={"status": "FAILED"})  # type: ignore[method-assign]
    client.restart_session = AsyncMock(return_value={"status": "FAILED"})  # type: ignore[method-assign]
    client.logout_session = AsyncMock(side_effect=_conflict(422))  # type: ignore[method-assign]

    result = asyncio.run(client.recover_session(settle_seconds=0))

    assert result["stage"] == "logout_start"
    assert result["status"] == "SCAN_QR_CODE"


# ---- no silent excepts: genuinely unexpected errors propagate ---------------


def test_recover_session_propagates_unexpected_5xx_on_restart() -> None:
    client = WahaClient(base_url="https://waha.test", api_key="k")
    client.get_session = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            {"status": "STARTING", "me": None},
            {"status": "STARTING", "me": None},
        ]
    )
    client.start_session = AsyncMock(return_value={"status": "STARTING"})  # type: ignore[method-assign]
    client.restart_session = AsyncMock(side_effect=_conflict(503))  # type: ignore[method-assign]

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(client.recover_session(settle_seconds=0))


def test_recover_session_propagates_unexpected_5xx_on_logout() -> None:
    client = WahaClient(base_url="https://waha.test", api_key="k")
    client.get_session = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            {"status": "FAILED", "me": {"id": "x@c.us"}},
            {"status": "FAILED", "me": {"id": "x@c.us"}},
            {"status": "FAILED", "me": {"id": "x@c.us"}},
        ]
    )
    client.start_session = AsyncMock(return_value={"status": "FAILED"})  # type: ignore[method-assign]
    client.restart_session = AsyncMock(return_value={"status": "FAILED"})  # type: ignore[method-assign]
    client.logout_session = AsyncMock(side_effect=_conflict(500))  # type: ignore[method-assign]

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(client.recover_session(settle_seconds=0))
