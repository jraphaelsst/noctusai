"""Registry hygiene for the core owner-recipient guard probes (migration 118): a probe fixture that violates a
NOT NULL on the events table reports `ambiguous` and never tests the refusal."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.verify_db_guards import DEFAULT_REGISTRY  # noqa: E402

EVENTS = "public.notification_owner_recipient_events"
IDS = {
    "notification_owner_recipient_events.update_refused",
    "notification_owner_recipient_events.delete_refused",
    "notification_owner_recipient_events.truncate_refused",
    "notification_owner_recipient_events.direct_insert_refused",
    "notification_owner_recipients.numero_update_refused",
    "notification_owner_recipients.truncate_refused",
}


def test_owner_recipient_probes_are_registered():
    assert IDS <= {p.id for p in DEFAULT_REGISTRY}


def test_every_events_fixture_insert_names_ator():
    inserts = 0
    for p in DEFAULT_REGISTRY:
        for m in re.finditer(rf"INSERT INTO {re.escape(EVENTS)}\s*\(([^)]*)\)", p.sql):
            inserts += 1
            assert "ator" in [c.strip() for c in m.group(1).split(",")], f"{p.id}: events fixture insert omits ator (NOT NULL)"
    assert inserts >= 3
