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
        self.client_ids: list = []

    async def notify_new_lead(
        self, *, org_id: UUID, lead: dict, marca_id: Any = None
    ) -> Any:
        # `client_id` mirrors the real signature (migration 045): the receiver
        # resolves which client a lead belongs to and the notifier routes on it.
        self.calls.append((org_id, lead.get("id")))
        self.client_ids.append(marca_id)
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


# ── unhandled-delivery visibility ──────────────────────────────────────────

class _CapturingAdmin(_FakeAdmin):
    """Captures what was upserted, so the recorded ROW SHAPE is assertable —
    not just that some write happened."""

    def __init__(self) -> None:
        super().__init__()
        self.upserted: list[dict] = []

    def upsert(self, rows, **_kw):
        self.upserted.extend(rows if isinstance(rows, list) else [rows])
        return self

    def __getattr__(self, name: str):
        if name == "upsert":
            raise AttributeError(name)
        return lambda *_a, **_k: self


def _page_payload(field: str, value: dict | None = None, *, entry_time: int = 1754300000):
    return {"object": "page", "entry": [{
        "id": "page-1", "time": entry_time,
        "changes": [{"field": field, "value": value or {"foo": "bar"}}]}]}


def test_an_unknown_field_delivery_is_recorded_not_dropped():
    """🔴 The gap this closes: before, a non-leadgen Page event was parsed to
    nothing and dropped, so 'Meta called us and we ignored it' looked exactly
    like 'Meta never called us' — opposite problems, identical evidence.

    Uses `feed` rather than `leadgen_update`: the latter graduated to a real
    processor on 2026-08-04 and is no longer an example of an unknown field."""
    admin = _CapturingAdmin()
    svc = _service(admin_supabase=admin)
    n = svc.record_unhandled(_page_payload("feed"))

    assert n == 1
    row = admin.upserted[0]
    assert row["field"] == "feed"
    assert row["object_type"] == "page"
    assert row["status"] == "ignored"
    assert row["page_id"] == "page-1"
    # The raw value must survive intact — the whole point is to LEARN what
    # an undocumented field actually sends.
    assert row["payload"]["value"] == {"foo": "bar"}


def test_the_synthetic_id_is_content_derived_so_retries_dedup():
    """Meta retries. A random id would make one delivery look like six, which
    defeats the question the inbox exists to answer."""
    admin = _CapturingAdmin()
    svc = _service(admin_supabase=admin)
    svc.record_unhandled(_page_payload("feed"))
    svc.record_unhandled(_page_payload("feed"))
    assert admin.upserted[0]["id"] == admin.upserted[1]["id"]


def test_a_different_delivery_gets_a_different_id():
    admin = _CapturingAdmin()
    svc = _service(admin_supabase=admin)
    svc.record_unhandled(_page_payload("feed", {"a": 1}))
    svc.record_unhandled(_page_payload("feed", {"a": 2}))
    assert admin.upserted[0]["id"] != admin.upserted[1]["id"]


def test_the_synthetic_id_can_never_collide_with_a_real_leadgen_id():
    """Real leadgen_ids are numeric; ours is namespaced."""
    admin = _CapturingAdmin()
    svc = _service(admin_supabase=admin)
    svc.record_unhandled(_page_payload("feed"))
    rid = admin.upserted[0]["id"]
    assert rid.startswith("evt:")
    assert not rid.isdigit()


def test_leadgen_itself_is_never_double_recorded_here():
    """The real path already owns `leadgen`. Recording it again would put two
    rows in the inbox for one lead and corrupt the delivery counts."""
    admin = _CapturingAdmin()
    svc = _service(admin_supabase=admin)
    assert svc.record_unhandled(_page_payload("leadgen")) == 0
    assert admin.upserted == []


def test_every_change_in_a_batch_is_recorded():
    """Meta batches. Recording only the first would under-count deliveries."""
    admin = _CapturingAdmin()
    svc = _service(admin_supabase=admin)
    payload = {"object": "page", "entry": [
        {"id": "p1", "time": 1, "changes": [
            {"field": "feed", "value": {"n": 1}},
            {"field": "mention", "value": {"n": 2}}]},
        {"id": "p2", "time": 2, "changes": [{"field": "messages", "value": {"n": 3}}]},
    ]}
    assert svc.record_unhandled(payload) == 3
    assert {r["field"] for r in admin.upserted} == {"feed", "mention", "messages"}


def test_a_write_failure_is_logged_and_never_raised():
    """Observability must never cost us the 200 — a non-2xx makes Meta retry
    and can disable the subscription."""
    class _Exploding(_FakeAdmin):
        def upsert(self, *_a, **_k):
            raise RuntimeError("db down")
        def __getattr__(self, name):
            if name == "upsert":
                raise AttributeError(name)
            return lambda *_a, **_k: self

    svc = _service(admin_supabase=_Exploding())
    assert svc.record_unhandled(_page_payload("feed")) == 0


def test_malformed_entries_do_not_raise():
    admin = _CapturingAdmin()
    svc = _service(admin_supabase=admin)
    assert svc.record_unhandled({"object": "page", "entry": "not-a-list"}) == 0
    assert svc.record_unhandled({"object": "page", "entry": ["str", 42]}) == 0
    assert svc.record_unhandled({}) == 0


# ── leadgen_update — the qualification-sync shell ──────────────────────────

from noctusai_lib.integrations.meta.leadgen_webhook import (  # noqa: E402
    parse_leadgen_update_webhook,
)


def _update_event(leadgen_id="987654321", **over):
    payload = {"object": "page", "entry": [{"id": "page-1", "time": 1, "changes": [{
        "field": "leadgen_update", "value": {
            "leadgen_id": leadgen_id, "page_id": "page-1", "form_id": "form-1",
            "updated_time": "1704067200", "area": "ai_agent_updates",
            "event": "qualification_status_change",
            "updated_fields": ["qualification_details", "qualification_status"],
            **over}}]}]}
    return parse_leadgen_update_webhook(payload)[0]


class _LeadPresentAdmin(_CapturingAdmin):
    """Fake where the referenced lead EXISTS in meta_ads_leads."""
    def execute(self):
        return SimpleNamespace(data=[{"id": "987654321"}])


class _LeadMissingAdmin(_CapturingAdmin):
    def execute(self):
        return SimpleNamespace(data=[])


def test_a_qualification_update_for_a_KNOWN_lead_is_recorded_as_received():
    admin = _LeadPresentAdmin()
    svc = _service(admin_supabase=admin, org_resolver=lambda _e: ORG_ID)
    assert svc.process_qualification_event(_update_event()) == "received"
    row = admin.upserted[0]
    assert row["field"] == "leadgen_update"
    assert row["payload"]["area"] == "ai_agent_updates"
    assert row["payload"]["event"] == "qualification_status_change"
    assert row["payload"]["updated_fields"] == [
        "qualification_details", "qualification_status"]
    assert row["payload"]["matched_lead"] is True


def test_an_update_for_an_UNKNOWN_lead_is_parked_unresolved_not_errored():
    """A miss is information — the lead predates the receiver or belongs to a
    page we do not sync. Recording it as an ERROR would put it in the retry
    queue forever for something no retry can fix."""
    admin = _LeadMissingAdmin()
    svc = _service(admin_supabase=admin, org_resolver=lambda _e: ORG_ID)
    assert svc.process_qualification_event(_update_event()) == "unresolved"
    assert admin.upserted[0]["payload"]["matched_lead"] is False


def test_successive_DIFFERENT_changes_to_one_lead_are_separate_rows():
    """🔴 Unlike `leadgen`, this fires repeatedly per lead as the AI agent
    revises its assessment. Keying on leadgen_id alone would collapse a
    qualification HISTORY into a single overwritten row."""
    admin = _LeadPresentAdmin()
    svc = _service(admin_supabase=admin, org_resolver=lambda _e: ORG_ID)
    svc.process_qualification_event(_update_event(updated_time="1704067200"))
    svc.process_qualification_event(_update_event(updated_time="1704070000"))
    assert admin.upserted[0]["id"] != admin.upserted[1]["id"]


def test_a_RETRY_of_the_same_change_is_idempotent():
    admin = _LeadPresentAdmin()
    svc = _service(admin_supabase=admin, org_resolver=lambda _e: ORG_ID)
    e = _update_event()
    svc.process_qualification_event(e)
    svc.process_qualification_event(e)
    assert admin.upserted[0]["id"] == admin.upserted[1]["id"]


def test_the_row_id_is_namespaced_away_from_leads_and_unknown_events():
    admin = _LeadPresentAdmin()
    svc = _service(admin_supabase=admin, org_resolver=lambda _e: ORG_ID)
    svc.process_qualification_event(_update_event())
    rid = admin.upserted[0]["id"]
    assert rid.startswith("upd:987654321:")
    assert not rid.isdigit()          # never a real leadgen_id
    assert not rid.startswith("evt:")  # never an unhandled-field row


def test_an_unrecognised_area_or_event_is_still_recorded():
    """Meta owns this vocabulary. Refusing an unknown value would make us
    blind to whatever it ships next."""
    admin = _LeadPresentAdmin()
    svc = _service(admin_supabase=admin, org_resolver=lambda _e: ORG_ID)
    ev = _update_event(area="future_area", event="future_event")
    assert svc.process_qualification_event(ev) == "received"
    assert admin.upserted[0]["payload"]["area"] == "future_area"


def test_a_write_failure_returns_error_and_never_raises():
    class _Exploding(_LeadPresentAdmin):
        def upsert(self, *_a, **_k):
            raise RuntimeError("db down")
        def __getattr__(self, name):
            if name == "upsert":
                raise AttributeError(name)
            return lambda *_a, **_k: self

    svc = _service(admin_supabase=_Exploding(), org_resolver=lambda _e: ORG_ID)
    assert svc.process_qualification_event(_update_event()) == "error"


def test_the_raw_payload_is_kept_so_a_future_build_has_the_real_shape():
    """The shell exists to CAPTURE, so the eventual processor is written
    against a real payload rather than a guess."""
    admin = _LeadPresentAdmin()
    svc = _service(admin_supabase=admin, org_resolver=lambda _e: ORG_ID)
    svc.process_qualification_event(_update_event(some_unknown_key="surprise"))
    assert admin.upserted[0]["payload"]["raw"]["some_unknown_key"] == "surprise"


def test_leadgen_update_is_not_double_recorded_by_the_unhandled_recorder():
    """It now has a real processor, so `record_unhandled` must skip it or the
    inbox gets two rows for one delivery and the health counts lie."""
    admin = _CapturingAdmin()
    svc = _service(admin_supabase=admin)
    payload = {"object": "page", "entry": [{"id": "p", "time": 1, "changes": [
        {"field": "leadgen_update", "value": {"leadgen_id": 1}},
        {"field": "feed", "value": {"n": 1}}]}]}
    assert svc.record_unhandled(payload) == 1
    assert admin.upserted[0]["field"] == "feed"


def test_a_leadgen_change_on_a_NON_page_object_is_still_recorded():
    """🔴 Neither parser accepts a non-`page` object, so such a delivery is
    processed by nobody. Skipping it by field NAME would make the one field
    we most need to see invisible — 'Meta called us on the wrong object'
    would look identical to 'Meta never called us'."""
    admin = _CapturingAdmin()
    svc = _service(admin_supabase=admin)
    payload = {"object": "user", "entry": [{"id": "u1", "time": 1, "changes": [
        {"field": "leadgen", "value": {"leadgen_id": "1"}}]}]}
    assert svc.record_unhandled(payload) == 1
    assert admin.upserted[0]["object_type"] == "user"
    assert admin.upserted[0]["field"] == "leadgen"
