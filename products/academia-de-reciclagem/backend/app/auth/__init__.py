"""Academia de Reciclagem — auth composition (SEED-1, contract §B.0/§D).

- `roles`: the READ/WRITE/ADMIN org-role sets `require_scopes` binds to.
- `assertion`: `X-Approval-Assertion` (§D) verification — the 8 ordered
  checks + the tool→route map (§C).
- `provenance`: `Provenance` construction per caller kind (§B.0's
  human / agent / human_personal split). Deliberately NOT re-exported
  here — `provenance.py` imports `app.dependencies` (for
  `get_core_client`), and `app.dependencies` imports `app.auth.roles`;
  re-exporting `provenance` from THIS `__init__` would make that a
  circular import the instant anything imports `app.auth` before
  `app.dependencies` finishes loading. Routers import it directly:
  `from app.auth.provenance import build_write_provenance`.
"""
from __future__ import annotations

from app.auth.assertion import (
    ApproverNotAllowedError,
    AssertionInvalidError,
    VerifiedAssertion,
    verify_assertion,
)
from app.auth.roles import ADMIN, READ, WRITE

__all__ = [
    "ADMIN",
    "READ",
    "WRITE",
    "ApproverNotAllowedError",
    "AssertionInvalidError",
    "VerifiedAssertion",
    "verify_assertion",
]
