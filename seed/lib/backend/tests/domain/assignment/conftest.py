"""Shared harness for the assignment organ suite: Fake store + Fake directory + a controllable clock -- no monkeypatching.

Every seam is the organ's own DI: `build_assignment_store(use_fake=True, card_writer=...)`, `FakeUserDirectory`, the service `clock`
kwarg and the `hooks` mapping.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from noctusai_lib.domain.assignment import (
    AssignmentConfig,
    AssignmentService,
    FakeUserDirectory,
    build_assignment_store,
)

ORG_A = "5b0e8f7a-1c2d-4e3f-9a8b-7c6d5e4f3a2b"
ORG_B = "9c8d7e6f-5a4b-4c3d-8e2f-1a0b9c8d7e6f"
ADMIN = "0f1e2d3c-4b5a-4978-8a9b-0c1d2e3f4a5b"
U1 = "11111111-1111-4111-8111-111111111111"
U2 = "22222222-2222-4222-8222-222222222222"
U3 = "33333333-3333-4333-8333-333333333333"
U4 = "44444444-4444-4444-8444-444444444444"
OUTSIDER = "99999999-9999-4999-8999-999999999999"
CARD1 = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1"
CARD2 = "c2c2c2c2-c2c2-4c2c-8c2c-c2c2c2c2c2c2"
CARD3 = "c3c3c3c3-c3c3-4c3c-8c3c-c3c3c3c3c3c3"
CARD4 = "c4c4c4c4-c4c4-4c4c-8c4c-c4c4c4c4c4c4"
SCHEMA = "asgx"
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: int) -> None:
        self.now += timedelta(**kw)


class Env:
    """A service over Fake everything + the recorded card writes."""

    def __init__(self, *, cfg: AssignmentConfig | None = None, hooks=None) -> None:
        self.cfg = cfg or AssignmentConfig(schema=SCHEMA, card_table="cards")
        self.clock = Clock()
        self.card_writes: list[tuple[str, str | None]] = []
        self.directory = FakeUserDirectory()
        for org in (ORG_A, ORG_B):
            for uid, name in ((U1, "Ana"), (U2, "Bruno"), (U3, "Carla"), (U4, "Davi"), (ADMIN, "Gestora")):
                self.directory.add(org, uid, name)
        self.store = build_assignment_store(
            self.cfg, use_fake=True, card_writer=lambda subject, user: self.card_writes.append((subject, user))
        )
        self.svc = AssignmentService(self.store, self.directory, self.cfg, hooks=hooks, clock=self.clock)

    def team(self, name: str, users: list[str], *, org: str = ORG_A, **kw) -> dict:
        team = self.svc.create_team(org, name=name, **kw)
        for u in users:
            self.svc.add_member(org, team["id"], u)
        return team


@pytest.fixture
def env() -> Env:
    return Env()
