"""Shared harness for the slice-D (statement import / reconciliation / gateway sync / export) suites.

Builds BOTH finance routers on one app over the conftest's schema-validating mock db, with a real
`FakeChargeOperations` behind `get_charge_operations`. Nothing is monkeypatched.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from noctusai_lib.domain.finance import make_finance_reconciliation_router, make_finance_router
from noctusai_lib.domain.finance._common import Scope
from noctusai_lib.integrations.payments.charges import FakeChargeOperations
from noctusai_lib.integrations.payments.types import BalanceTransaction, Money
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.primitives.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)

from .conftest import CFG, ORG_A, ORG_B, _admin, _auth, _resolve, make_db

P = "/api/finance"


@dataclass
class ReconHarness:
    db: Any
    ops: FakeChargeOperations
    app: FastAPI
    client: TestClient

    @property
    def s(self) -> Scope:
        return Scope(self.db, CFG, ORG_A)

    @property
    def s_b(self) -> Scope:
        return Scope(self.db, CFG, ORG_B)

    def staff(self, role: str = "user") -> dict:
        return {"Authorization": f"Bearer {role}"}

    @property
    def admin(self) -> dict:
        return self.staff("admin")

    @property
    def admin_b(self) -> dict:
        return self.staff("org-b-admin")

    def upload(self, account_id: str, name: str, data: bytes, headers=None, **form) -> Any:
        return self.client.post(
            f"{P}/statements", headers=headers or self.admin,
            data={"account_id": account_id, **form}, files={"file": (name, data, "application/octet-stream")},
        )


def build_recon_harness(ops: Any = None) -> ReconHarness:
    db = make_db()
    ops = ops if ops is not None else FakeChargeOperations()
    kw = dict(resolve_context=_resolve, get_db=lambda: db, get_storage=lambda: FakeStorageBackend())
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.include_router(make_finance_router(CFG, _auth, _admin, **kw))
    app.include_router(make_finance_reconciliation_router(CFG, _auth, _admin, get_charge_operations=lambda: ops, **kw))
    return ReconHarness(db, ops, app, TestClient(app))


@pytest.fixture
def rh(finance_schema_cache) -> ReconHarness:
    return build_recon_harness()


# ── statement builders (real-bank-shaped) ───────────────────────────────────


def ofx1(*trns: tuple[str, str, str, str], start="20261001", end="20261031", charset="1252") -> bytes:
    """OFX 1.x SGML as Brazilian banks emit it: unclosed leaf tags, CRLF, cp1252.
    Each trn is `(DTPOSTED, TRNAMT, FITID, MEMO)`."""
    body = "".join(
        f"<STMTTRN>\r\n<TRNTYPE>OTHER\r\n<DTPOSTED>{d}120000[-3:BRT]\r\n<TRNAMT>{a}\r\n<FITID>{f}\r\n"
        f"<CHECKNUM>{f}\r\n<MEMO>{m}\r\n</STMTTRN>\r\n"
        for d, a, f, m in trns
    )
    text = (
        f"OFXHEADER:100\r\nDATA:OFXSGML\r\nVERSION:102\r\nSECURITY:NONE\r\nENCODING:USASCII\r\nCHARSET:{charset}\r\n"
        "COMPRESSION:NONE\r\nOLDFILEUID:NONE\r\nNEWFILEUID:NONE\r\n\r\n<OFX>\r\n<SIGNONMSGSRSV1><SONRS><STATUS><CODE>0<SEVERITY>INFO</STATUS>"
        "<DTSERVER>20261031120000[-3:BRT]<LANGUAGE>POR</SONRS></SIGNONMSGSRSV1>\r\n<BANKMSGSRSV1><STMTTRNRS><TRNUID>1"
        "<STATUS><CODE>0<SEVERITY>INFO</STATUS><STMTRS><CURDEF>BRL<BANKACCTFROM><BANKID>0341<BRANCHID>1234"
        "<ACCTID>56789-0<ACCTTYPE>CHECKING</BANKACCTFROM>\r\n"
        f"<BANKTRANLIST><DTSTART>{start}120000[-3:BRT]<DTEND>{end}120000[-3:BRT]\r\n{body}</BANKTRANLIST>\r\n"
        "<LEDGERBAL><BALAMT>1000.00<DTASOF>20261031120000[-3:BRT]</LEDGERBAL></STMTRS></STMTTRNRS></BANKMSGSRSV1>\r\n</OFX>\r\n"
    )
    return text.encode("cp1252" if charset == "1252" else "utf-8")


def ofx2(*trns: tuple[str, str, str, str], doctype: str = "", curdef: str = "BRL") -> bytes:
    body = "".join(
        f"<STMTTRN><TRNTYPE>CREDIT</TRNTYPE><DTPOSTED>{d}120000[-3:BRT]</DTPOSTED><TRNAMT>{a}</TRNAMT>"
        f"<FITID>{f}</FITID><MEMO>{m}</MEMO></STMTTRN>"
        for d, a, f, m in trns
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
        '<?OFX OFXHEADER="200" VERSION="211" SECURITY="NONE" OLDFILEUID="NONE" NEWFILEUID="NONE"?>\n'
        f"{doctype}<OFX><SIGNONMSGSRSV1><SONRS><STATUS><CODE>0</CODE><SEVERITY>INFO</SEVERITY></STATUS>"
        "<DTSERVER>20261031120000</DTSERVER><LANGUAGE>POR</LANGUAGE></SONRS></SIGNONMSGSRSV1>"
        f"<BANKMSGSRSV1><STMTTRNRS><TRNUID>1</TRNUID><STMTRS><CURDEF>{curdef}</CURDEF>"
        "<BANKACCTFROM><BANKID>0341</BANKID><ACCTID>56789-0</ACCTID><ACCTTYPE>CHECKING</ACCTTYPE></BANKACCTFROM>"
        f"<BANKTRANLIST><DTSTART>20261001120000</DTSTART><DTEND>20261031120000</DTEND>{body}</BANKTRANLIST>"
        "</STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"
    ).encode("utf-8")


def bt(id_: str, kind: str, cents: int, *, day: int = 3, charge: str | None = None, desc: str = "") -> BalanceTransaction:
    return BalanceTransaction(
        id_at_gateway=id_, occurred_at=dt.datetime(2026, 10, day, 15, 0, tzinfo=dt.timezone.utc),
        kind=kind, amount=Money(cents), charge_id_at_gateway=charge, description=desc,  # type: ignore[arg-type]
    )
