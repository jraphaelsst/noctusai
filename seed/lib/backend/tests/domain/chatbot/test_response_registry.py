"""response_registry — vendor-neutral connector-shape registry.

Covers the pure shape/fingerprint helpers Engineer WHATSAPP (W1.E2)
reuses verbatim for the WAHA/SQLite sink, plus the FakeResponseRegistry
dedup behaviour and the factory's inject-or-Fake contract.
"""

from noctusai_lib.domain.chatbot.response_registry import (
    FakeResponseRegistry,
    ResponseRegistry,
    json_shape,
    make_response_registry,
    sample_key,
    shape_fingerprint,
)


def test_json_shape_collapses_scalars_to_type_tags() -> None:
    shape = json_shape({"b": 1, "a": "x", "c": True, "d": None, "e": 1.5})
    assert shape == {"a": "str", "b": "int", "c": "bool", "d": "null", "e": "float"}


def test_json_shape_dedups_list_element_shapes() -> None:
    shape = json_shape([{"x": 1}, {"x": 2}, {"x": 3}])
    assert shape == [{"x": "int"}]


def test_shape_fingerprint_is_stable_across_equivalent_payloads() -> None:
    a = shape_fingerprint(json_shape({"k": 1, "v": "a"}))
    b = shape_fingerprint(json_shape({"v": "b", "k": 999}))
    assert a == b  # same structure → same fingerprint
    assert len(a) == 16


def test_sample_key_composite() -> None:
    key = sample_key(
        source="waha",
        direction="inbound",
        fingerprint="abc123",
        event_type="message",
        http_status=200,
    )
    assert key == "waha|inbound|message|200|abc123"


def test_fake_records_one_sample_per_shape_and_counts_repeats() -> None:
    reg = FakeResponseRegistry()
    reg.record(source="waha", direction="inbound", payload={"k": 1})
    reg.record(source="waha", direction="inbound", payload={"k": 2})  # same shape
    reg.record(source="waha", direction="inbound", payload={"k": 3})
    assert len(reg.samples) == 1
    only = next(iter(reg.samples.values()))
    assert only["observed_count"] == 3
    assert only["source"] == "waha"


def test_fake_distinct_shapes_get_distinct_entries() -> None:
    reg = FakeResponseRegistry()
    reg.record(source="waha", direction="inbound", payload={"k": 1})
    reg.record(source="waha", direction="inbound", payload={"different": "x"})
    assert len(reg.samples) == 2


def test_fake_none_payload_is_noop() -> None:
    reg = FakeResponseRegistry()
    reg.record(source="waha", direction="inbound", payload=None)
    assert reg.samples == {}


def test_fake_satisfies_protocol() -> None:
    assert isinstance(FakeResponseRegistry(), ResponseRegistry)


def test_factory_returns_fake_when_no_sink() -> None:
    assert isinstance(make_response_registry(), FakeResponseRegistry)


def test_factory_returns_injected_sink() -> None:
    sink = FakeResponseRegistry()
    assert make_response_registry(sink=sink) is sink
