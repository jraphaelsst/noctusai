"""Parser + contract-validator tests for `noctusai_lib.integrations.olx`.

Pure functions, no DB, no client, no FastAPI — the whole point of
`webhook.py` / `contract.py` being zero-IO.

The theme running through these: **a doubt must never cost us a lead.**
OLX retries a non-2xx three times and then discards it after 14 days
with no replay API, so every "reject it to be safe" instinct is actually
"throw a real customer away". The parser therefore accepts unknown
values, and the validator downgrades them to warnings.
"""

from __future__ import annotations

import copy

import pytest

from noctusai_lib.integrations.olx import (
    OLX_LEAD_ORIGIN_MCMV,
    OLX_SAMPLE_LEAD,
    diff_observed,
    has_blocking_violation,
    missing_client_listing_id,
    olx_lead_json_schema,
    parse_olx_lead_webhook,
    validate_olx_lead_payload,
)


def _sample(**overrides):
    body = copy.deepcopy(OLX_SAMPLE_LEAD)
    body.update(overrides)
    return body


# -- parsing ---------------------------------------------------------------


def test_parses_the_vendor_documentation_sample():
    lead = parse_olx_lead_webhook(_sample())

    assert lead is not None
    assert lead.origin_lead_id == "59ee0fc6e4b043e1b2a6d863"
    assert lead.client_listing_id == "a40171"
    assert lead.name == "Nome Consumidor"
    assert lead.lead_type == "CONTACT_CHAT"
    assert lead.temperature == "Alta"
    assert lead.raw == OLX_SAMPLE_LEAD


def test_raw_is_carried_verbatim_including_unmodelled_fields():
    body = _sample(someFutureField={"nested": 1})
    lead = parse_olx_lead_webhook(body)

    assert lead is not None
    assert lead.raw["someFutureField"] == {"nested": 1}


def test_returns_none_without_an_origin_lead_id():
    """No dedup key ⇒ the lead cannot be stored idempotently, so there is
    nothing honest to do but refuse and let OLX retry."""
    assert parse_olx_lead_webhook(_sample(originLeadId="")) is None
    assert parse_olx_lead_webhook(_sample(originLeadId=None)) is None
    body = _sample()
    del body["originLeadId"]
    assert parse_olx_lead_webhook(body) is None


def test_returns_none_never_raises_for_non_dict_bodies():
    for body in (None, [], "a string", 42):
        assert parse_olx_lead_webhook(body) is None


def test_accepts_an_unknown_lead_type_rather_than_rejecting_it():
    """A channel the vendor adds next week must not 4xx a real lead into
    a retry queue that discards it."""
    body = _sample()
    body["extraData"]["leadType"] = "CLICK_TELEPATHY"

    lead = parse_olx_lead_webhook(body)

    assert lead is not None
    assert lead.lead_type == "CLICK_TELEPATHY"


def test_tolerates_a_missing_or_non_dict_extra_data():
    for value in (None, "nope", 7, []):
        lead = parse_olx_lead_webhook(_sample(extraData=value))
        assert lead is not None
        assert lead.extra_data == {}
        assert lead.lead_type is None


def test_coerces_numeric_ids_rather_than_dropping_them():
    lead = parse_olx_lead_webhook(_sample(originListingId=87027856))

    assert lead is not None
    assert lead.origin_listing_id == "87027856"


def test_full_phone_prefers_phone_number_then_falls_back_to_ddd_plus_phone():
    assert parse_olx_lead_webhook(_sample()).full_phone == "11999999999"

    body = _sample()
    del body["phoneNumber"]
    assert parse_olx_lead_webhook(body).full_phone == "11999999999"

    body = _sample(phoneNumber=None, ddd=None)
    assert parse_olx_lead_webhook(body).full_phone == "999999999"

    body = _sample(phoneNumber=None, ddd=None, phone=None)
    assert parse_olx_lead_webhook(body).full_phone is None


def test_mcmv_leads_are_flagged():
    lead = parse_olx_lead_webhook(_sample(leadOrigin=OLX_LEAD_ORIGIN_MCMV))

    assert lead is not None
    assert lead.is_mcmv is True
    assert parse_olx_lead_webhook(_sample()).is_mcmv is False


# -- contract validation ---------------------------------------------------


def test_the_documentation_sample_satisfies_its_own_contract():
    """If this ever fails, our transcription and the vendor's example
    disagree — and the transcription is the thing to fix."""
    assert validate_olx_lead_payload(OLX_SAMPLE_LEAD) == []


def test_missing_required_field_is_an_error():
    body = _sample()
    del body["name"]

    violations = validate_olx_lead_payload(body)

    assert has_blocking_violation(violations)
    assert any(v.field == "name" and v.severity == "error" for v in violations)


def test_listing_lead_without_client_listing_id_is_the_documented_4xx_case():
    violations = validate_olx_lead_payload(_sample(clientListingId=None))

    assert missing_client_listing_id(violations) is True


def test_mcmv_lead_without_listing_ids_is_valid():
    """MCMV leads are not tied to a listing, so 4xx-ing one would requeue
    a lead the vendor will never enrich."""
    body = _sample(leadOrigin=OLX_LEAD_ORIGIN_MCMV, clientListingId=None,
                   originListingId=None)

    violations = validate_olx_lead_payload(body)

    assert missing_client_listing_id(violations) is False
    assert not has_blocking_violation(violations)


def test_unknown_enum_value_is_a_warning_not_an_error():
    violations = validate_olx_lead_payload(_sample(temperature="Escaldante"))

    assert not has_blocking_violation(violations)
    assert any(v.field == "temperature" and v.severity == "warning" for v in violations)


def test_undocumented_field_is_a_warning_not_an_error():
    violations = validate_olx_lead_payload(_sample(brandNewField="x"))

    assert not has_blocking_violation(violations)
    assert any(v.field == "brandNewField" and v.severity == "warning"
               for v in violations)


def test_wrong_type_is_an_error():
    violations = validate_olx_lead_payload(_sample(extraData="not-an-object"))

    assert has_blocking_violation(violations)


def test_non_dict_payload_is_reported_not_raised():
    violations = validate_olx_lead_payload(["nope"])

    assert has_blocking_violation(violations)
    assert violations[0].field == "<root>"


def test_errors_sort_before_warnings():
    body = _sample(temperature="Escaldante")
    del body["email"]

    violations = validate_olx_lead_payload(body)

    severities = [v.severity for v in violations]
    assert severities == sorted(severities, key=lambda s: 0 if s == "error" else 1)


def test_json_schema_is_derived_from_the_field_table():
    schema = olx_lead_json_schema()

    assert "originLeadId" in schema["properties"]
    assert "originLeadId" in schema["required"]
    # Optional-on-MCMV fields must not be schema-required, or the schema
    # would contradict the conditional rule the validator implements.
    assert "clientListingId" not in schema["required"]
    assert schema["additionalProperties"] is True


# -- the doc-vs-reality loop -----------------------------------------------


def test_diff_observed_is_clean_for_a_corpus_matching_the_contract():
    report = diff_observed([OLX_SAMPLE_LEAD])

    assert report["clean"] is True
    assert report["bodies_examined"] == 1


def test_diff_observed_surfaces_undocumented_fields_and_novel_enums():
    body = _sample(newVendorField="surprise", temperature="Escaldante")

    report = diff_observed([body, body])

    assert report["clean"] is False
    assert report["undocumented_fields"]["newVendorField"] == 2
    assert report["novel_enum_values"]["temperature"] == ["Escaldante"]


def test_diff_observed_reports_documented_fields_that_never_arrive():
    body = _sample()
    del body["phoneNumber"]

    report = diff_observed([body])

    assert "phoneNumber" in report["documented_never_seen"]


def test_diff_observed_reports_required_fields_that_arrive_null():
    """Present-but-null is the divergence a schema check misses and a
    receiver trips over — worth its own line in the report."""
    report = diff_observed([_sample(message=None)])

    assert "message" in report["required_but_arrived_null"]


def test_diff_observed_survives_a_non_dict_entry():
    report = diff_observed(["garbage", OLX_SAMPLE_LEAD])

    assert report["bodies_examined"] == 2
    assert any(entry.get("error") for entry in report["bodies_with_violations"])


@pytest.mark.parametrize("lead_type", [
    "CLICK_SCHEDULE", "CLICK_WHATSAPP", "CONTACT_CHAT",
    "CONTACT_FORM", "PHONE_VIEW", "VISIT_REQUEST",
])
def test_every_documented_lead_type_validates(lead_type):
    body = _sample()
    body["extraData"]["leadType"] = lead_type

    assert validate_olx_lead_payload(body) == []
