"""Unit tests for `noctusai_lib.integrations.meta.leadgen_webhook` — pure
functions, zero IO, zero FastAPI. Table-tests the parser against the
shapes Meta's Lead-Ads webhook actually sends (batched `entry[]` ×
`changes[]`) plus the `GET /webhooks` verification handshake.

The anti-shape this module exists to avoid is
`products/erp-imobiliario/backend/app/services/meta_api_service.py:139`
(`parse_lead_webhook`), which reads `entry[0].changes[0]` only and
silently drops the rest of a batched delivery — several tests below
lock that batching behaviour directly.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from noctusai_lib.integrations.meta import (
    LeadgenEvent,
    leadgen_challenge_response,
    parse_leadgen_webhook,
)


def _delivery(*entries: dict) -> dict:
    return {"object": "page", "entry": list(entries)}


def _leadgen_change(value: dict) -> dict:
    return {"field": "leadgen", "value": value}


# ─── parse_leadgen_webhook ──────────────────────────────────────────────


class TestParseLeadgenWebhookHappyPath:
    def test_single_entry_single_change(self):
        payload = _delivery({
            "id": "PAGE1",
            "time": 1700000000,
            "changes": [
                _leadgen_change({
                    "leadgen_id": "LEAD1",
                    "page_id": "PAGE1",
                    "form_id": "FORM1",
                    "ad_id": "AD1",
                    "adgroup_id": "ADSET1",
                    "created_time": 1700000000,
                })
            ],
        })

        events = parse_leadgen_webhook(payload)

        assert events == [
            LeadgenEvent(
                leadgen_id="LEAD1",
                page_id="PAGE1",
                form_id="FORM1",
                ad_id="AD1",
                adgroup_id="ADSET1",
                created_time=datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc),
                raw={
                    "leadgen_id": "LEAD1",
                    "page_id": "PAGE1",
                    "form_id": "FORM1",
                    "ad_id": "AD1",
                    "adgroup_id": "ADSET1",
                    "created_time": 1700000000,
                },
            )
        ]

    def test_optional_fields_default_none_when_absent(self):
        payload = _delivery({
            "id": "PAGE1",
            "changes": [_leadgen_change({"leadgen_id": "LEAD1"})],
        })

        [event] = parse_leadgen_webhook(payload)

        assert event.leadgen_id == "LEAD1"
        assert event.page_id is None
        assert event.form_id is None
        assert event.ad_id is None
        assert event.adgroup_id is None
        assert event.created_time is None


class TestParseLeadgenWebhookBatching:
    """Meta batches — the anti-shape drops everything past index 0."""

    def test_multi_entry_batch_all_parsed(self):
        payload = _delivery(
            {
                "id": "PAGE1",
                "changes": [_leadgen_change({"leadgen_id": "LEAD1"})],
            },
            {
                "id": "PAGE2",
                "changes": [_leadgen_change({"leadgen_id": "LEAD2"})],
            },
        )

        events = parse_leadgen_webhook(payload)

        assert [e.leadgen_id for e in events] == ["LEAD1", "LEAD2"]

    def test_multi_changes_batch_all_parsed(self):
        payload = _delivery({
            "id": "PAGE1",
            "changes": [
                _leadgen_change({"leadgen_id": "LEAD1"}),
                _leadgen_change({"leadgen_id": "LEAD2"}),
                _leadgen_change({"leadgen_id": "LEAD3"}),
            ],
        })

        events = parse_leadgen_webhook(payload)

        assert [e.leadgen_id for e in events] == ["LEAD1", "LEAD2", "LEAD3"]

    def test_multi_entry_and_multi_changes_combined(self):
        payload = _delivery(
            {
                "id": "PAGE1",
                "changes": [
                    _leadgen_change({"leadgen_id": "LEAD1"}),
                    _leadgen_change({"leadgen_id": "LEAD2"}),
                ],
            },
            {
                "id": "PAGE2",
                "changes": [_leadgen_change({"leadgen_id": "LEAD3"})],
            },
        )

        events = parse_leadgen_webhook(payload)

        assert [e.leadgen_id for e in events] == ["LEAD1", "LEAD2", "LEAD3"]


class TestParseLeadgenWebhookFiltering:
    def test_object_not_page_returns_empty_never_raises(self):
        payload = {"object": "user", "entry": [{"changes": []}]}

        assert parse_leadgen_webhook(payload) == []

    def test_missing_object_returns_empty(self):
        assert parse_leadgen_webhook({"entry": []}) == []

    def test_field_not_leadgen_is_skipped(self):
        payload = _delivery({
            "id": "PAGE1",
            "changes": [
                {"field": "feed", "value": {"leadgen_id": "LEAD1"}},
                _leadgen_change({"leadgen_id": "LEAD2"}),
            ],
        })

        events = parse_leadgen_webhook(payload)

        assert [e.leadgen_id for e in events] == ["LEAD2"]

    def test_missing_leadgen_id_is_skipped(self):
        payload = _delivery({
            "id": "PAGE1",
            "changes": [
                _leadgen_change({"page_id": "PAGE1"}),  # no leadgen_id
                _leadgen_change({"leadgen_id": "LEAD2"}),
            ],
        })

        events = parse_leadgen_webhook(payload)

        assert [e.leadgen_id for e in events] == ["LEAD2"]

    def test_falsy_leadgen_id_is_skipped(self):
        payload = _delivery({
            "id": "PAGE1",
            "changes": [_leadgen_change({"leadgen_id": ""})],
        })

        assert parse_leadgen_webhook(payload) == []


class TestParseLeadgenWebhookMalformedShapes:
    """A malformed-but-signature-verified body must degrade to `[]` /
    skip the bad entry — never raise."""

    def test_malformed_created_time_is_none_never_guessed(self):
        payload = _delivery({
            "id": "PAGE1",
            "changes": [
                _leadgen_change({
                    "leadgen_id": "LEAD1",
                    "created_time": "not-a-timestamp",
                })
            ],
        })

        [event] = parse_leadgen_webhook(payload)

        assert event.created_time is None

    def test_missing_entry_key_returns_empty(self):
        assert parse_leadgen_webhook({"object": "page"}) == []

    def test_entry_not_a_list_returns_empty(self):
        assert parse_leadgen_webhook({"object": "page", "entry": {"id": "x"}}) == []

    def test_entry_row_not_a_dict_is_skipped(self):
        payload = {
            "object": "page",
            "entry": [
                "not-a-dict",
                {"id": "PAGE1", "changes": [_leadgen_change({"leadgen_id": "LEAD1"})]},
            ],
        }

        events = parse_leadgen_webhook(payload)

        assert [e.leadgen_id for e in events] == ["LEAD1"]

    def test_changes_missing_or_not_a_list_is_skipped(self):
        payload = {
            "object": "page",
            "entry": [
                {"id": "PAGE1"},  # no "changes" key at all
                {"id": "PAGE2", "changes": "not-a-list"},
                {"id": "PAGE3", "changes": [_leadgen_change({"leadgen_id": "LEAD1"})]},
            ],
        }

        events = parse_leadgen_webhook(payload)

        assert [e.leadgen_id for e in events] == ["LEAD1"]

    def test_change_row_not_a_dict_is_skipped(self):
        payload = _delivery({
            "id": "PAGE1",
            "changes": ["not-a-dict", _leadgen_change({"leadgen_id": "LEAD1"})],
        })

        events = parse_leadgen_webhook(payload)

        assert [e.leadgen_id for e in events] == ["LEAD1"]

    def test_value_not_a_dict_is_skipped(self):
        payload = _delivery({
            "id": "PAGE1",
            "changes": [{"field": "leadgen", "value": "not-a-dict"}],
        })

        assert parse_leadgen_webhook(payload) == []

    def test_payload_not_a_dict_returns_empty(self):
        assert parse_leadgen_webhook(None) == []  # type: ignore[arg-type]


class TestParseLeadgenWebhookRawLossless:
    def test_raw_is_the_value_object_verbatim(self):
        value = {
            "leadgen_id": "LEAD1",
            "page_id": "PAGE1",
            "unexpected_future_field": "meta-added-this-later",
        }
        payload = _delivery({"id": "PAGE1", "changes": [_leadgen_change(value)]})

        [event] = parse_leadgen_webhook(payload)

        assert event.raw == value
        assert event.raw is not value  # defensive copy, not aliased


# ─── leadgen_challenge_response ─────────────────────────────────────────


class TestLeadgenChallengeResponse:
    def test_matching_token_echoes_challenge(self):
        result = leadgen_challenge_response(
            mode="subscribe",
            verify_token="secret",
            challenge="CHALLENGE123",
            expected_token="secret",
        )
        assert result == "CHALLENGE123"

    def test_mismatched_token_returns_none(self):
        result = leadgen_challenge_response(
            mode="subscribe",
            verify_token="wrong",
            challenge="CHALLENGE123",
            expected_token="secret",
        )
        assert result is None

    def test_mode_not_subscribe_returns_none(self):
        result = leadgen_challenge_response(
            mode="unsubscribe",
            verify_token="secret",
            challenge="CHALLENGE123",
            expected_token="secret",
        )
        assert result is None

    def test_missing_mode_returns_none(self):
        result = leadgen_challenge_response(
            mode=None,
            verify_token="secret",
            challenge="CHALLENGE123",
            expected_token="secret",
        )
        assert result is None

    def test_empty_expected_token_returns_none(self):
        """An unconfigured verify token must never accidentally match —
        a falsy `expected_token` is always a refusal, even if
        `verify_token` also happens to be falsy."""
        result = leadgen_challenge_response(
            mode="subscribe",
            verify_token="anything",
            challenge="CHALLENGE123",
            expected_token="",
        )
        assert result is None

    def test_missing_verify_token_returns_none(self):
        result = leadgen_challenge_response(
            mode="subscribe",
            verify_token=None,
            challenge="CHALLENGE123",
            expected_token="secret",
        )
        assert result is None

    @pytest.mark.parametrize(
        ("mode", "verify_token", "expected_token"),
        [
            ("subscribe", "secret", "secret"),
            ("subscribe", "SECRET", "secret"),  # case-sensitive mismatch
        ],
    )
    def test_case_sensitive_compare(self, mode, verify_token, expected_token):
        result = leadgen_challenge_response(
            mode=mode,
            verify_token=verify_token,
            challenge="X",
            expected_token=expected_token,
        )
        if verify_token == expected_token:
            assert result == "X"
        else:
            assert result is None


# ── leadgen_update — Meta's AI-agent qualification feed ────────────────────
#
# Every fixture below is Meta's OWN "Teste" sample, captured verbatim from the
# App Dashboard on 2026-08-04. Meta does not document this field anywhere, so
# the wire is the only specification that exists — a paraphrase here would be
# inventing a contract rather than pinning one.

from noctusai_lib.integrations.meta.leadgen_webhook import (  # noqa: E402
    LeadgenUpdateEvent,
    parse_leadgen_update_webhook,
)

#: Verbatim from the dashboard's "Exemplo do campo leadgen_update" (v26.0).
#: NOTE the ids are INTEGERS here while the `leadgen` sample uses STRINGS.
_META_SAMPLE = {
    "object": "page",
    "entry": [{
        "id": 0,                      # Meta's test harness sends 0, not a page
        "time": 1785879142,
        "changes": [{
            "field": "leadgen_update",
            "value": {
                "adgroup_id": 123456789,
                "ad_id": 123456789,
                "leadgen_id": 987654321,
                "page_id": 111111111,
                "form_id": 222222222,
                "updated_time": "1704067200",
                "area": "ai_agent_updates",
                "event": "qualification_status_change",
                "updated_fields": ["qualification_details", "qualification_status"],
            },
        }],
    }],
}


def test_parses_metas_own_leadgen_update_sample():
    events = parse_leadgen_update_webhook(_META_SAMPLE)
    assert len(events) == 1
    e = events[0]
    assert isinstance(e, LeadgenUpdateEvent)
    assert e.leadgen_id == "987654321"
    assert e.area == "ai_agent_updates"
    assert e.event == "qualification_status_change"
    assert e.updated_fields == ("qualification_details", "qualification_status")


def test_INTEGER_ids_are_coerced_to_strings():
    """🔴 Meta is inconsistent with ITSELF: the `leadgen` sample sends ids as
    strings, the `leadgen_update` sample sends the same ids as integers. A
    parser that assumed either would break on the other, and the failure would
    be a silent type mismatch downstream (a str PK compared against an int)."""
    e = parse_leadgen_update_webhook(_META_SAMPLE)[0]
    for got in (e.leadgen_id, e.page_id, e.form_id, e.ad_id, e.adgroup_id):
        assert isinstance(got, str), f"{got!r} should have been coerced to str"
    assert e.page_id == "111111111"
    assert e.adgroup_id == "123456789"


def test_leadgen_parser_also_survives_integer_ids():
    """The same inconsistency could appear on the `leadgen` field. It already
    coerces — this pins that so a refactor cannot quietly remove it."""
    payload = {"object": "page", "entry": [{"id": 111, "changes": [{
        "field": "leadgen", "value": {
            "leadgen_id": 987654321, "page_id": 111111111,
            "form_id": 222222222, "created_time": 1704067200}}]}]}
    e = parse_leadgen_webhook(payload)[0]
    assert e.leadgen_id == "987654321"
    assert isinstance(e.page_id, str)


def test_updated_time_is_parsed_from_a_STRING_unix_timestamp():
    """Meta sends `updated_time` as a quoted string here, unlike `leadgen`'s
    numeric `created_time`."""
    e = parse_leadgen_update_webhook(_META_SAMPLE)[0]
    assert e.updated_time is not None
    assert e.updated_time.year == 2024
    assert e.updated_time.tzinfo is not None


def test_the_two_parsers_never_see_each_others_events():
    """🔴 The load-bearing separation. `leadgen` is 'a new lead exists';
    `leadgen_update` is 'an existing lead changed'. If the leadgen parser
    picked up an update, one qualification change would create a duplicate
    lead — and if the update parser picked up a leadgen, a brand-new lead
    would be processed as a qualification change to a lead we do not have."""
    assert parse_leadgen_webhook(_META_SAMPLE) == []
    leadgen_payload = {"object": "page", "entry": [{"id": "p", "changes": [{
        "field": "leadgen", "value": {"leadgen_id": "1", "page_id": "p"}}]}]}
    assert parse_leadgen_update_webhook(leadgen_payload) == []


def test_raw_value_is_preserved_losslessly():
    """The vocabulary is Meta's to extend. An unrecognised key must survive
    to the inbox so we can SEE it, rather than being silently narrowed away."""
    payload = {"object": "page", "entry": [{"id": "p", "changes": [{
        "field": "leadgen_update", "value": {
            "leadgen_id": 5, "area": "some_future_area",
            "event": "some_future_event", "a_key_we_have_never_seen": 42}}]}]}
    e = parse_leadgen_update_webhook(payload)[0]
    assert e.raw["a_key_we_have_never_seen"] == 42
    assert e.area == "some_future_area"


def test_an_unknown_area_or_event_is_kept_not_dropped():
    """`ai_agent_updates` is one area; treating it as an enum would make us
    blind to the next one Meta ships."""
    payload = {"object": "page", "entry": [{"id": "p", "changes": [{
        "field": "leadgen_update", "value": {
            "leadgen_id": 5, "area": "brand_new", "event": "brand_new_event"}}]}]}
    e = parse_leadgen_update_webhook(payload)[0]
    assert (e.area, e.event) == ("brand_new", "brand_new_event")


def test_an_update_without_a_leadgen_id_is_dropped():
    """Without it we cannot say WHICH lead changed — the event is unusable."""
    payload = {"object": "page", "entry": [{"id": "p", "changes": [{
        "field": "leadgen_update", "value": {"area": "ai_agent_updates"}}]}]}
    assert parse_leadgen_update_webhook(payload) == []


def test_batched_updates_are_all_parsed():
    payload = {"object": "page", "entry": [
        {"id": "p1", "changes": [
            {"field": "leadgen_update", "value": {"leadgen_id": 1}},
            {"field": "leadgen_update", "value": {"leadgen_id": 2}}]},
        {"id": "p2", "changes": [
            {"field": "leadgen_update", "value": {"leadgen_id": 3}}]}]}
    assert [e.leadgen_id for e in parse_leadgen_update_webhook(payload)] == ["1", "2", "3"]


def test_malformed_shapes_degrade_to_no_events_never_raise():
    for bad in ({}, {"object": "user", "entry": []},
                {"object": "page", "entry": "nope"},
                {"object": "page", "entry": [None, 5]},
                {"object": "page", "entry": [{"changes": "nope"}]},
                {"object": "page", "entry": [{"changes": [{"field": "leadgen_update",
                                                           "value": "not-a-dict"}]}]}):
        assert parse_leadgen_update_webhook(bad) == []


def test_updated_fields_tolerates_a_non_list():
    payload = {"object": "page", "entry": [{"id": "p", "changes": [{
        "field": "leadgen_update",
        "value": {"leadgen_id": 5, "updated_fields": "not-a-list"}}]}]}
    assert parse_leadgen_update_webhook(payload)[0].updated_fields == ()
