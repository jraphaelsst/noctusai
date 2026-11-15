"""Harness for the approvals suite. ONE contract, two ledgers: the Fake, and the Real one driven through an RPC-shaped client.

The Real ledger only talks `client.rpc(name, params).execute().data`; `RpcClient` is that surface backed by the Fake's
logic and raising the SAME error text the SQL RPC raises, so the Real adapter's translation is exercised without Postgres
(the SQL itself is replayed on a real Postgres in `test_sql.py`). No monkeypatching: every seam is the organ's own DI.
"""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from noctusai_lib.domain.approvals import (
    ApprovalsConfig,
    ApprovalService,
    FakeApprovalLedger,
    SupabaseApprovalLedger,
    build_approvals_store,
)
from noctusai_lib.domain.approvals.errors import AlreadyDecided, NotSubmitted, StaleVersion
from noctusai_lib.domain.approvals.sql import ERR_ALREADY_DECIDED, ERR_NOT_SUBMITTED, ERR_STALE

ORG_A = "5b0e8f7a-1c2d-4e3f-9a8b-7c6d5e4f3a2b"
ORG_B = "9c8d7e6f-5a4b-4c3d-8e2f-1a0b9c8d7e6f"
U1 = "11111111-1111-4111-8111-111111111111"
U2 = "22222222-2222-4222-8222-222222222222"
ROT = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
MID = "c2c2c2c2-c2c2-4c2c-8c2c-c2c2c2c2c2c2"
SCHEMA = "aprx"

_TEXT = {StaleVersion: ERR_STALE, NotSubmitted: ERR_NOT_SUBMITTED, AlreadyDecided: ERR_ALREADY_DECIDED}


class RpcClient:
    """`client.rpc("apr_record", {...}).execute().data`, answered by the Fake ledger; refusals surface as the RPC's error text."""

    def __init__(self, fake: FakeApprovalLedger) -> None:
        self._fake = fake

    def rpc(self, name: str, params: dict):
        assert name.endswith("apr_record"), name
        try:
            data = self._fake.record(params["p_org"], params["p_row"])
        except (StaleVersion, NotSubmitted, AlreadyDecided) as exc:
            raise RuntimeError('{"message":"%s"}' % _TEXT[type(exc)]) from exc
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=data))


@pytest.fixture(params=["fake", "real"])
def service(request) -> ApprovalService:
    cfg = ApprovalsConfig(schema=SCHEMA)
    store = build_approvals_store(cfg, use_fake=True)
    if request.param == "real":
        store = replace(store, ledger=SupabaseApprovalLedger(RpcClient(store.ledger), cfg))
    return ApprovalService(store, cfg)
