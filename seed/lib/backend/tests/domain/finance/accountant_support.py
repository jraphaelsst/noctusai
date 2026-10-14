"""Harness for the accountant suites (E16/E21): both finance routers with an `accountant_dependency` wired.

`Bearer accountant` is an ordinary (non-admin) org member holding the read grant -- the shape the mounted organ produces from
the permission repo. Nothing is monkeypatched: the dependency is a real FastAPI dependency pair, like the conftest's.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from noctusai_lib.domain.finance import make_finance_reconciliation_router, make_finance_router
from noctusai_lib.domain.finance._common import Scope
from noctusai_lib.integrations.payments.charges import FakeChargeOperations
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.primitives.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)

from .conftest import CFG, ORG_A, ORG_B, _admin, _auth, _resolve, make_db

P = "/api/finance"


def _accountant(authorization: Optional[str] = Header(None), auth: dict = Depends(_auth)) -> dict:
    if auth["admin"] or authorization == "Bearer accountant":
        return auth
    raise HTTPException(status_code=403, detail="Not an accountant")


@dataclass
class AccHarness:
    db: Any
    app: FastAPI
    client: TestClient

    @property
    def s(self) -> Scope:
        return Scope(self.db, CFG, ORG_A)

    @property
    def s_b(self) -> Scope:
        return Scope(self.db, CFG, ORG_B)

    @staticmethod
    def as_(role: str) -> dict:
        return {"Authorization": f"Bearer {role}"}

    admin = {"Authorization": "Bearer admin"}
    admin_b = {"Authorization": "Bearer org-b-admin"}
    accountant = {"Authorization": "Bearer accountant"}
    staff = {"Authorization": "Bearer user"}

    def get(self, path: str, headers: Optional[dict] = None, **kw: Any):
        return self.client.get(f"{P}{path}", headers=headers if headers is not None else self.admin, **kw)


def build_acc_harness(*, with_accountant: bool = True) -> AccHarness:
    db = make_db()
    kw: dict[str, Any] = dict(resolve_context=_resolve, get_db=lambda: db, get_storage=lambda: FakeStorageBackend())
    acc = {"accountant_dependency": _accountant} if with_accountant else {}
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.include_router(make_finance_router(CFG, _auth, _admin, **kw, **acc))
    app.include_router(make_finance_reconciliation_router(CFG, _auth, _admin, get_charge_operations=lambda: FakeChargeOperations(), **kw, **acc))
    return AccHarness(db, app, TestClient(app))


@pytest.fixture
def ah(finance_schema_cache) -> AccHarness:
    return build_acc_harness()


@pytest.fixture
def ah_plain(finance_schema_cache) -> AccHarness:
    """No accountant dependency wired: the reads stay admin-only (the behaviour before E16)."""
    return build_acc_harness(with_accountant=False)
