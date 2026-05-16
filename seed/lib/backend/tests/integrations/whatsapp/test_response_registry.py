"""WAHA response-shape registry — fingerprint + Fake + Real + factory.

Validates the promotion of `waha-response-registry` per the in-home
manifest: distinct WAHA shapes are recorded once; same-shape /
different-data responses fingerprint identically.
"""

from noctusai_lib.integrations.whatsapp import (
    FakeResponseRegistry,
    PersistentResponseRegistry,
    ResponseRegistry,
    ResponseSample,
    fingerprint_response,
    get_response_registry,
)


def test_fingerprint_is_shape_not_value() -> None:
    a = {"name": "default", "status": "WORKING"}
    b = {"name": "session-2", "status": "STOPPED"}
    c = {"name": "x", "status": "X", "extra": 1}

    assert fingerprint_response(a) == fingerprint_response(b)
    assert fingerprint_response(a) != fingerprint_response(c)


def test_fingerprint_distinguishes_list_vs_object() -> None:
    obj = {"name": "default", "status": "WORKING"}
    lst = [{"name": "default", "status": "WORKING"}]
    bare = "WORKING"

    fps = {
        fingerprint_response(obj),
        fingerprint_response(lst),
        fingerprint_response(bare),
    }
    assert len(fps) == 3


def test_fake_registry_records_new_shape_once() -> None:
    reg = FakeResponseRegistry()

    assert reg.record(
        {"name": "default", "status": "WORKING"},
        source="session_status",
        direction="inbound",
        handling_note="session object",
    ) is True
    # Same shape, different values → already known.
    assert reg.record(
        {"name": "other", "status": "STOPPED"},
        source="session_status",
        direction="inbound",
    ) is False
    assert len(reg.samples) == 1


def test_persistent_registry_dedupes_against_sink() -> None:
    stored: dict[str, ResponseSample] = {}

    class Sink:
        def upsert_sample(self, sample: ResponseSample) -> None:
            stored[sample.fingerprint] = sample

        def known_fingerprints(self) -> set[str]:
            return set(stored)

    reg = PersistentResponseRegistry(Sink())

    payload = {"_data": {"id": {"remote": "551199@c.us"}}}
    assert reg.record(payload, source="send_text", direction="outbound") is True
    assert reg.record(payload, source="send_text", direction="outbound") is False
    assert len(stored) == 1


def test_factory_returns_fake_without_sink() -> None:
    assert isinstance(get_response_registry(), FakeResponseRegistry)
    assert isinstance(FakeResponseRegistry(), ResponseRegistry)
