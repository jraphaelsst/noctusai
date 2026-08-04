"""Service-level tests for `LeadgenWebhookService` — the fan-out contract.

WHY THIS FILE EXISTS
────────────────────
Until 2026-08-04 the receiver had NO service-level tests. It was exercised
only through `test_leadgen_router.py`, which substitutes a fake service via the
`Depends` seam — so the route was well covered and the service was not covered
at all. That gap is exactly how the real defect shipped:

`process_event`'s docstring promised "Enrich → upsert → normalize → notify",
and the module docstring promised "a persisted lead, a unified-base row, and an
operator alert". The code did the enrich and the upsert and then stopped.
Slice 3 built `ingest_meta_lead` and Slice 4 built `notify_new_lead`, each with
their own green tests, and nothing ever called either from the webhook path —
so leads never reached `social_wiring.leads` and no alert ever fired. Both were
explicit product requirements. Two parallel engineers each shipped a correct
half; the seam between them belonged to neither file.

The tests below pin the seam itself. If someone deletes the `_ingest` call or
the `fan_out` scheduling, these fail — which the route tests, by construction,
cannot.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from app.modules.meta_ads.services.leadgen_webhook_service import (
    STATUS_ERROR,
    STATUS_PROCESSED,
    STATUS_UNRESOLVED,
    LeadgenWebhookService,
    ProcessResult,
)

ORG_ID = UUID("11111111-1111-1111-1111-111111111111")
LEAD_ID = "lead-abc-123"


def _event() -> Any:
    return SimpleNamespace(
        leadgen_id=LEAD_ID,
        page_id="page-1",
        form_id="form-1",
        ad_id=None,
        created_time=None,
        raw={},
    )


class _FakeAdmin:
    """Chainable Supabase double.

    `rows` is what the terminal `.execute()` yields — the form lookup in
    `resolve_form` reads it, and returning the form here keeps these tests on
    the WARM path (form already synced), so the cold-form Graph fallback is
    not silently exercised by every case.
    """

    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = rows if rows is not None else [
            {"id": "form-1", "org_id": str(ORG_ID), "page_id": "page-1",
             "name": "Form", "questions": []}
        ]

    def __getattr__(self, _name: str):
        # Every query-builder verb (schema/table/select/eq/limit/update/...)
        # is a no-op that returns self; only `execute` produces anything.
        return lambda *_a, **_k: self

    def execute(self) -> Any:
        return SimpleNamespace(data=self.rows)


class _FakeLeadsSync:
    """Stands in for `LeadsSyncService`. Returns the row it 'wrote', which is
    the contract the fan-out depends on (`upsert_lead` used to return None)."""

    def __init__(self, **_kw: Any) -> None:
        self.calls: list[dict] = []

    def upsert_lead(self, lead: Any, *, org_id: UUID, form: Any,
                    key_types: dict) -> dict:
        row = {"id": lead.id, "org_id": str(org_id), "full_name": "Fulana",
               "phone": "+5511999999999", "campaign_name": "Campanha X"}
        self.calls.append(row)
        return row


def _adapter_factory(**_kw: Any) -> Any:
    lead = SimpleNamespace(id=LEAD_ID, form_id="form-1", field_data=[])
    return SimpleNamespace(
        get_lead=lambda leadgen_id, page_id=None: lead,
        get_leadgen_form=lambda _fid, page_id=None: SimpleNamespace(
            id="form-1", name="Form", page_id="page-1", questions=[]
        ),
    )


def _service(**overrides: Any) -> LeadgenWebhookService:
    kwargs: dict[str, Any] = {
        "admin_supabase": _FakeAdmin(),
        "adapter_factory": _adapter_factory,
        "leads_sync_factory": lambda **_kw: _FakeLeadsSync(),
        "org_resolver": lambda _event: ORG_ID,
    }
    kwargs.update(overrides)
    return LeadgenWebhookService(**kwargs)


# ── the destination half: normalize into the unified `leads` base ──────────

def test_process_event_normalizes_into_the_unified_leads_base(monkeypatch):
    """🔴 THE REGRESSION GUARD for the shipped gap. `meta_ads_leads` is the
    raw ledger; `leads` is the canonical base the product actually reads.
    Writing only the former was the defect."""
    seen: list[tuple] = []

    def _ingest(client, org_id, meta_lead, **kw):
        seen.append((org_id, meta_lead["id"], kw.get("question_types")))
        return {"lead": {"id": "x"}, "created": True}

    svc = _service(ingest_fn=_ingest)
    result = svc.process_event(_event())

    assert result.status == STATUS_PROCESSED
    assert len(seen) == 1, "the lead never reached the unified base"
    assert seen[0][0] == ORG_ID
    assert seen[0][1] == LEAD_ID


def test_process_event_returns_the_row_the_fan_out_needs(monkeypatch):
    """The fan-out must work from the row just written, never re-read it."""
    svc = _service(ingest_fn=lambda *a, **k: {"lead": {}, "created": True})
    result = svc.process_event(_event())
    assert result.lead_row is not None
    assert result.lead_row["id"] == LEAD_ID
    assert result.org_id == ORG_ID
    assert result.announceable is True


def test_a_normalize_failure_marks_the_row_error_so_the_retry_redrives_it():
    """Deliberate: swallowing would leave the lead invisible in the base with
    nothing recording why. Every step is idempotent, so a re-drive is safe."""
    def _boom(*_a: Any, **_k: Any):
        raise RuntimeError("leads base unreachable")

    svc = _service(ingest_fn=_boom)
    result = svc.process_event(_event())
    assert result.status == STATUS_ERROR
    assert result.announceable is False, "a failed lead must not be announced"


def test_unresolved_org_is_parked_and_never_announced():
    svc = _service(org_resolver=lambda _e: None)
    result = svc.process_event(_event())
    assert result.status == STATUS_UNRESOLVED
    assert result.announceable is False


# ── the arrival half: operator alert + realtime push ───────────────────────

class _RecordingNotifier:
    def __init__(self, **_kw: Any) -> None:
        self.calls: list[tuple] = []

    async def notify_new_lead(self, *, org_id: UUID, lead: dict) -> Any:
        self.calls.append((org_id, lead.get("id")))
        return SimpleNamespace()


@pytest.mark.asyncio
async def test_fan_out_fires_both_the_alert_and_the_realtime_push():
    notifier = _RecordingNotifier()
    published: list[tuple] = []

    async def _publisher(*, org_id: UUID, lead: dict) -> str:
        published.append((org_id, lead.get("id")))
        return "1-0"

    svc = _service(notifier_factory=lambda **_kw: notifier, publisher=_publisher)
    outcome = await svc.fan_out(
        ProcessResult(STATUS_PROCESSED, org_id=ORG_ID, lead_row={"id": LEAD_ID})
    )

    assert outcome == {"notified": True, "published": True}
    assert notifier.calls == [(ORG_ID, LEAD_ID)]
    assert published == [(ORG_ID, LEAD_ID)]


@pytest.mark.asyncio
async def test_a_dead_notifier_does_not_take_the_realtime_push_with_it():
    """Both legs are announcements about a write that already succeeded. One
    channel degrading must never suppress the other — or a slow SMTP server
    silently costs every open client its live update."""
    published: list[str] = []

    class _Broken:
        async def notify_new_lead(self, **_kw: Any) -> Any:
            raise RuntimeError("smtp down")

    async def _publisher(*, org_id: UUID, lead: dict) -> str:
        published.append(lead["id"])
        return "1-0"

    svc = _service(notifier_factory=lambda **_kw: _Broken(), publisher=_publisher)
    outcome = await svc.fan_out(
        ProcessResult(STATUS_PROCESSED, org_id=ORG_ID, lead_row={"id": LEAD_ID})
    )

    assert outcome["notified"] is False
    assert outcome["published"] is True
    assert published == [LEAD_ID]


@pytest.mark.asyncio
async def test_a_dead_bus_does_not_suppress_the_operator_alert():
    notifier = _RecordingNotifier()

    async def _publisher(**_kw: Any) -> str:
        raise RuntimeError("redis down")

    svc = _service(notifier_factory=lambda **_kw: notifier, publisher=_publisher)
    outcome = await svc.fan_out(
        ProcessResult(STATUS_PROCESSED, org_id=ORG_ID, lead_row={"id": LEAD_ID})
    )

    assert outcome["notified"] is True
    assert outcome["published"] is False
    assert notifier.calls == [(ORG_ID, LEAD_ID)]


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [
    ProcessResult(STATUS_ERROR, org_id=ORG_ID),
    ProcessResult(STATUS_UNRESOLVED),
    ProcessResult(STATUS_PROCESSED, org_id=ORG_ID, lead_row=None),
    ProcessResult(STATUS_PROCESSED, org_id=None, lead_row={"id": LEAD_ID}),
])
async def test_nothing_is_announced_without_a_real_processed_lead(result):
    """A duplicate, a parked row, or a failure must reach neither the operator
    nor the wire — announcing a lead that does not exist is worse than silence."""
    notifier = _RecordingNotifier()
    published: list[str] = []

    async def _publisher(*, org_id: UUID, lead: dict) -> str:
        published.append(lead.get("id"))
        return "1-0"

    svc = _service(notifier_factory=lambda **_kw: notifier, publisher=_publisher)
    outcome = await svc.fan_out(result)

    assert outcome == {"notified": False, "published": False}
    assert notifier.calls == []
    assert published == []


# ── structural: the public surface actually exists on the class ────────────

def test_the_service_exposes_its_whole_public_surface():
    """🔴 A real defect this caught, 2026-08-04.

    A module-level helper was inserted into the middle of the class body
    during an edit. Python does not complain: everything after the dedent
    simply stopped being part of the class — `claim`, `drain_pending` and
    `purge_processed` became NESTED functions inside that helper and vanished
    from the service. The full 1671-test suite still passed, because the route
    tests substitute a fake service and nothing else constructed a real one.

    It surfaced only as a 500 on a live signed delivery
    (`AttributeError: 'LeadgenWebhookService' object has no attribute 'claim'`)
    — which, on the real webhook, is the failure mode that makes Meta retry and
    can disable the subscription outright.

    Asserting the surface is the cheap structural guard for that whole class of
    edit accident; it costs nothing and does not care WHY a method went missing.
    """
    expected = {
        "record_event", "resolve_org", "resolve_form", "process_event",
        "fan_out", "fan_out_sync", "claim", "drain_pending", "purge_processed",
    }
    missing = {n for n in expected if not callable(getattr(LeadgenWebhookService, n, None))}
    assert not missing, f"fell out of the class body: {sorted(missing)}"


def test_the_retry_drain_can_actually_be_called_on_a_real_service():
    """The drain is only ever invoked by the scheduler, so nothing else would
    notice it going missing until the */15 job started erroring in prod."""
    svc = _service(admin_supabase=_FakeAdmin(rows=[]))
    assert svc.drain_pending(limit=1) == {"scanned": 0, "processed": 0, "failed": 0}
