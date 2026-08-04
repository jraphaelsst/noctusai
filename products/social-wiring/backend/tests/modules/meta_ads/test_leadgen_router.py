"""Meta Lead-Ads webhook receiver — status-code-pinned tests.

Pin 5 of `KB § PATTERNS/security/webhook-signatures.md`: assert
``resp.status_code == N`` exactly, never a body substring and never
``in (401, 404)``. A receiver is a security boundary, and "it returned
something 4xx-ish" is not a boundary assertion.

The controlling facts these tests encode:
  • Meta signs with the **App Secret**, and the verify token is a DIFFERENT
    secret used only on the GET handshake. Conflating them is a live defect
    in erp-imobiliario; several tests below exist purely to keep it from
    being reintroduced here.
  • ``bypass_when_unset=False`` — an unset secret must 401, NOT silently
    accept. A forged POST writes lead PII and spawns a CRM funnel card.
  • Everything past signature verification returns **200**, because Meta
    retries non-2xx and can disable the subscription outright.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from types import SimpleNamespace
from typing import Any

import pytest

from uuid import UUID

from app.modules.meta_ads.services.leadgen_webhook_service import ProcessResult

APP_SECRET = "test-app-secret"
VERIFY_TOKEN = "test-verify-token"
ORG_ID = UUID("11111111-1111-1111-1111-111111111111")

WEBHOOK = "/api/meta/leadgen/webhook"


def _sign(body: bytes, secret: str = APP_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _delivery(*, leadgen_id: str = "lead-1", field: str = "leadgen",
              obj: str = "page", entries: int = 1, changes: int = 1) -> dict:
    return {
        "object": obj,
        "entry": [
            {
                "id": "page-1",
                "changes": [
                    {
                        "field": field,
                        "value": {
                            "leadgen_id": f"{leadgen_id}-{e}-{c}",
                            "page_id": "page-1",
                            "form_id": "form-1",
                            "created_time": 1754000000,
                        },
                    }
                    for c in range(changes)
                ],
            }
            for e in range(entries)
        ],
    }


class _FakeService:
    """Records what the route asked of it. Substituted through the real
    ``Depends`` seam, so the ROUTE under test (signature check, parse,
    status code) is fully exercised."""

    def __init__(self, *, new: bool = True, claim: bool = True,
                 status: str = "processed") -> None:
        self._new, self._claim, self._status = new, claim, status
        self.recorded: list[str] = []
        self.processed: list[str] = []
        #: Leads whose announcement half actually ran. The route schedules
        #: `fan_out` on the RESPONSE, so this only fills in once the 200 has
        #: been sent — which is exactly the ordering guarantee under test.
        self.fanned_out: list[str] = []
        self.unhandled: list[Any] = []

    def record_event(self, event: Any) -> bool:
        self.recorded.append(event.leadgen_id)
        return self._new

    def claim(self, leadgen_id: str) -> bool:
        return self._claim

    def process_event(self, event: Any) -> ProcessResult:
        self.processed.append(event.leadgen_id)
        return ProcessResult(
            self._status,
            org_id=ORG_ID,
            # Only a genuinely-processed lead carries a row; a parked or
            # failed one must not look announceable.
            lead_row=(
                {"id": event.leadgen_id, "full_name": "Fulano"}
                if self._status == "processed" else None
            ),
        )

    async def fan_out(self, result: ProcessResult) -> dict[str, bool]:
        self.fanned_out.append((result.lead_row or {}).get("id"))
        return {"notified": True, "published": True}

    def record_unhandled(self, payload: Any) -> int:
        #: Deliveries the route recognised as non-leadgen and handed here.
        #: Asserted below — a route that stopped calling this would silently
        #: reopen the "arrived vs never arrived" blind spot.
        self.unhandled.append(payload)
        return 1


@pytest.fixture
def wired(client, monkeypatch):
    """Real app + real routes, with the two secrets resolved to knowns and
    the service swapped through its dependency."""
    from app.main import app
    from app.modules.meta_ads.routers.leadgen_router import get_leadgen_service
    import app.services.app_config_store as store

    monkeypatch.setattr(store, "resolve_meta_app_creds",
                        lambda **_kw: ("app-id", APP_SECRET), raising=False)
    monkeypatch.setattr(store, "resolve_meta_webhook_verify_token",
                        lambda **_kw: VERIFY_TOKEN, raising=False)

    svc = _FakeService()
    app.dependency_overrides[get_leadgen_service] = lambda: svc
    yield SimpleNamespace(raw=client.raw(), svc=svc, app=app,
                          set_service=lambda s: app.dependency_overrides.__setitem__(
                              get_leadgen_service, lambda: s))
    app.dependency_overrides.pop(get_leadgen_service, None)


# ─── GET handshake ────────────────────────────────────────────────────────


def test_handshake_matching_token_returns_200_and_echoes_challenge(wired):
    resp = wired.raw.get(WEBHOOK, params={
        "hub.mode": "subscribe",
        "hub.verify_token": VERIFY_TOKEN,
        "hub.challenge": "abc123",
    })
    assert resp.status_code == 200
    assert resp.text == "abc123"


def test_handshake_echoes_a_NON_NUMERIC_challenge_verbatim(wired):
    """🔴 The erp-imobiliario regression: it returns ``int(hub_challenge)``,
    which raises on anything non-numeric. Meta does not promise digits."""
    resp = wired.raw.get(WEBHOOK, params={
        "hub.mode": "subscribe",
        "hub.verify_token": VERIFY_TOKEN,
        "hub.challenge": "not-a-number-xyz",
    })
    assert resp.status_code == 200
    assert resp.text == "not-a-number-xyz"


def test_handshake_wrong_token_returns_403(wired):
    resp = wired.raw.get(WEBHOOK, params={
        "hub.mode": "subscribe",
        "hub.verify_token": "wrong",
        "hub.challenge": "abc123",
    })
    assert resp.status_code == 403


def test_handshake_wrong_mode_returns_403(wired):
    resp = wired.raw.get(WEBHOOK, params={
        "hub.mode": "unsubscribe",
        "hub.verify_token": VERIFY_TOKEN,
        "hub.challenge": "abc123",
    })
    assert resp.status_code == 403


def test_handshake_with_unset_verify_token_returns_403(client, monkeypatch):
    """Unset must REFUSE, not accept. An empty configured token compared
    against an empty supplied token would let anyone register our endpoint."""
    import app.services.app_config_store as store

    monkeypatch.setattr(store, "resolve_meta_webhook_verify_token",
                        lambda **_kw: None, raising=False)
    resp = client.raw().get(WEBHOOK, params={
        "hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "x",
    })
    assert resp.status_code == 403


# ─── POST signature boundary ─────────────────────────────────────────────


def test_valid_signature_returns_200(wired):
    body = json.dumps(_delivery()).encode()
    resp = wired.raw.post(WEBHOOK, content=body,
                          headers={"X-Hub-Signature-256": _sign(body),
                                   "Content-Type": "application/json"})
    assert resp.status_code == 200


def test_tampered_body_returns_401(wired):
    body = json.dumps(_delivery()).encode()
    sig = _sign(body)
    resp = wired.raw.post(WEBHOOK, content=body + b" ",
                          headers={"X-Hub-Signature-256": sig,
                                   "Content-Type": "application/json"})
    assert resp.status_code == 401


def test_missing_signature_header_returns_401(wired):
    body = json.dumps(_delivery()).encode()
    resp = wired.raw.post(WEBHOOK, content=body,
                          headers={"Content-Type": "application/json"})
    assert resp.status_code == 401


def test_signature_computed_with_the_VERIFY_TOKEN_returns_401(wired):
    """🔴 THE anti-regression for the erp defect. If someone ever wires the
    verify token in as the HMAC secret, a payload signed with the App Secret
    stops validating — and a payload signed with the verify token starts
    validating. This asserts the latter is rejected."""
    body = json.dumps(_delivery()).encode()
    resp = wired.raw.post(WEBHOOK, content=body,
                          headers={"X-Hub-Signature-256": _sign(body, VERIFY_TOKEN),
                                   "Content-Type": "application/json"})
    assert resp.status_code == 401


def test_unset_app_secret_returns_401_not_bypass(client, monkeypatch):
    """``bypass_when_unset=False`` is a deliberate deviation from the seed
    skeleton. An unset secret must fail LOUDLY — the alternative is
    unauthenticated write-through to lead PII and the CRM funnel board."""
    import app.services.app_config_store as store

    monkeypatch.setattr(store, "resolve_meta_app_creds",
                        lambda **_kw: ("app-id", None), raising=False)
    body = json.dumps(_delivery()).encode()
    resp = client.raw().post(WEBHOOK, content=body,
                             headers={"X-Hub-Signature-256": _sign(body),
                                      "Content-Type": "application/json"})
    assert resp.status_code == 401


# ─── POST behaviour past the boundary (always 200) ───────────────────────


def test_non_page_object_returns_200_ignored(wired):
    body = json.dumps(_delivery(obj="user")).encode()
    resp = wired.raw.post(WEBHOOK, content=body,
                          headers={"X-Hub-Signature-256": _sign(body),
                                   "Content-Type": "application/json"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    assert wired.svc.processed == []
    # Ignored, but RECORDED — "we ignored it" must stay distinguishable from
    # "it never arrived", which is the whole reason the inbox exists.
    assert len(wired.svc.unhandled) == 1
    assert resp.json()["recorded"] == 1


def test_non_leadgen_field_returns_200_ignored(wired):
    body = json.dumps(_delivery(field="feed")).encode()
    resp = wired.raw.post(WEBHOOK, content=body,
                          headers={"X-Hub-Signature-256": _sign(body),
                                   "Content-Type": "application/json"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    assert wired.svc.processed == []
    assert len(wired.svc.unhandled) == 1


def test_an_unknown_field_like_leadgen_update_is_handed_to_the_recorder(wired):
    """The concrete motivation: `leadgen_update` is undocumented by Meta and
    has no public discussion, so the only way to learn its payload is to
    capture one. This is the seam that makes that possible."""
    body = json.dumps(_delivery(field="leadgen_update")).encode()
    resp = wired.raw.post(WEBHOOK, content=body,
                          headers={"X-Hub-Signature-256": _sign(body),
                                   "Content-Type": "application/json"})
    assert resp.status_code == 200
    assert resp.json()["recorded"] == 1
    assert wired.svc.unhandled[0]["entry"][0]["changes"][0]["field"] == "leadgen_update"


def test_a_json_body_that_is_not_an_object_returns_200_and_records_nothing(wired):
    """Valid JSON, wrong shape. Must not reach `.get()` on a list."""
    body = json.dumps([1, 2, 3]).encode()
    resp = wired.raw.post(WEBHOOK, content=body,
                          headers={"X-Hub-Signature-256": _sign(body),
                                   "Content-Type": "application/json"})
    assert resp.status_code == 200
    assert resp.json()["reason"] == "not-an-object"
    assert wired.svc.unhandled == []


def test_malformed_json_from_a_VERIFIED_sender_returns_200(wired):
    """A verified sender sending garbage is not retryable — 200 so Meta
    stops, with the reason recorded."""
    body = b"{not json"
    resp = wired.raw.post(WEBHOOK, content=body,
                          headers={"X-Hub-Signature-256": _sign(body),
                                   "Content-Type": "application/json"})
    assert resp.status_code == 200
    assert resp.json()["reason"] == "malformed-json"


def test_batched_delivery_processes_every_entry_and_change(wired):
    """🔴 Meta BATCHES. The erp parser reads entry[0].changes[0] only and
    silently drops the rest — 2×2 must yield 4 processed leads, not 1."""
    body = json.dumps(_delivery(entries=2, changes=2)).encode()
    resp = wired.raw.post(WEBHOOK, content=body,
                          headers={"X-Hub-Signature-256": _sign(body),
                                   "Content-Type": "application/json"})
    assert resp.status_code == 200
    assert resp.json()["events"] == 4
    assert len(wired.svc.processed) == 4


def test_duplicate_delivery_returns_200_and_does_not_reprocess(wired):
    """Meta retry: the inbox PK says 'seen', so we must NOT re-hit Graph."""
    dup = _FakeService(new=False)
    wired.set_service(dup)
    body = json.dumps(_delivery()).encode()
    resp = wired.raw.post(WEBHOOK, content=body,
                          headers={"X-Hub-Signature-256": _sign(body),
                                   "Content-Type": "application/json"})
    assert resp.status_code == 200
    assert resp.json()["results"][0]["status"] == "duplicate"
    assert dup.processed == []


def test_dedup_claim_lost_returns_200_and_does_not_reprocess(wired):
    """Redis says another worker owns it — same outcome, different layer."""
    lost = _FakeService(new=True, claim=False)
    wired.set_service(lost)
    body = json.dumps(_delivery()).encode()
    resp = wired.raw.post(WEBHOOK, content=body,
                          headers={"X-Hub-Signature-256": _sign(body),
                                   "Content-Type": "application/json"})
    assert resp.status_code == 200
    assert lost.processed == []


def test_processing_error_still_returns_200(wired):
    """The whole point of the inbox: a Graph failure is a recorded row, not
    a non-2xx. A 500 here risks Meta disabling the subscription."""
    failing = _FakeService(status="error")
    wired.set_service(failing)
    body = json.dumps(_delivery()).encode()
    resp = wired.raw.post(WEBHOOK, content=body,
                          headers={"X-Hub-Signature-256": _sign(body),
                                   "Content-Type": "application/json"})
    assert resp.status_code == 200
    assert resp.json()["results"][0]["status"] == "error"


def test_unresolved_org_still_returns_200(wired):
    unresolved = _FakeService(status="unresolved")
    wired.set_service(unresolved)
    body = json.dumps(_delivery()).encode()
    resp = wired.raw.post(WEBHOOK, content=body,
                          headers={"X-Hub-Signature-256": _sign(body),
                                   "Content-Type": "application/json"})
    assert resp.status_code == 200
    assert resp.json()["results"][0]["status"] == "unresolved"
