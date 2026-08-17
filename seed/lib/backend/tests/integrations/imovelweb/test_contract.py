"""The language-parameterized contract, its validator, and the diff.

The validator's error/warning split is the whole point: for this vendor the
only blocking condition is a body we cannot deduplicate. Everything else
still gets a 2xx, because a refusal costs 72 hours of retries against a
body that will never change.
"""

from __future__ import annotations

import pytest

from noctusai_lib.integrations.imovelweb.contract import (
    IMOVELWEB_FIELD_SPECS,
    IMOVELWEB_RESPONSE_SEMANTICS,
    IMOVELWEB_RETRY_POLICY,
    IMOVELWEB_SAMPLE_BODIES,
    LANGUAGE_FIELD_ALIASES,
    contract_summary,
    diff_observed,
    has_blocking_violation,
    imovelweb_json_schema,
    validate_imovelweb_payload,
)
from noctusai_lib.integrations.imovelweb.types import IMOVELWEB_CALLBACK_LANGUAGES


class TestContractStructure:
    def test_every_declared_language_has_a_field_table(self):
        assert set(IMOVELWEB_FIELD_SPECS) == set(IMOVELWEB_CALLBACK_LANGUAGES)

    def test_aliases_are_derived_from_the_specs(self):
        # Two hand-synced tables drift; this asserts the derivation holds.
        for language, specs in IMOVELWEB_FIELD_SPECS.items():
            assert LANGUAGE_FIELD_ALIASES[language] == {
                s.name: s.canonical for s in specs
            }

    def test_every_language_can_carry_an_event_id(self):
        for language, aliases in LANGUAGE_FIELD_ALIASES.items():
            assert "event_id" in aliases.values(), language

    def test_nothing_is_verified_yet(self):
        # The honesty invariant. Flipped only by an observation at Gate 1,
        # never by re-reading the vendor's docs.
        for specs in IMOVELWEB_FIELD_SPECS.values():
            assert all(s.verified is False for s in specs)
        assert contract_summary()["verified_against_live_traffic"] is False

    def test_response_semantics_record_3xx_as_success(self):
        # Diverges from Grupo OLX and is easy to "fix" wrongly.
        assert "3xx" in IMOVELWEB_RESPONSE_SEMANTICS["success_status_ranges"]

    def test_retry_policy_is_a_deadline_not_a_count(self):
        assert IMOVELWEB_RETRY_POLICY["retry_until_hours"] == 72
        assert IMOVELWEB_RETRY_POLICY["max_attempts"] is None
        assert IMOVELWEB_RETRY_POLICY["response_timeout_seconds"] == 1.5

    def test_the_language_tradeoff_is_real(self):
        # Documents the fact that drives the Gate-1 language decision: no
        # variant carries both the agency code and the portal name.
        def canon(language):
            return {s.canonical for s in IMOVELWEB_FIELD_SPECS[language]}

        assert "lead_origin" in canon("EN2")
        assert "codigo_imobiliaria" not in canon("EN2")
        for language in ("PT", "ES", "EN"):
            assert "codigo_imobiliaria" in canon(language), language
            assert "lead_origin" not in canon(language), language


class TestJsonSchema:
    @pytest.mark.parametrize("language", sorted(IMOVELWEB_FIELD_SPECS))
    def test_builds_for_every_language(self, language):
        schema = imovelweb_json_schema(language)
        assert schema["type"] == "object"
        assert schema["properties"]

    def test_allows_additional_properties(self):
        # The vendor adds fields without notice; refusing one would 4xx a
        # real lead into the retry queue.
        assert imovelweb_json_schema("EN2")["additionalProperties"] is True

    def test_rejects_an_unknown_language(self):
        with pytest.raises(ValueError, match="unknown language"):
            imovelweb_json_schema("KLINGON")


class TestValidator:
    def test_sample_bodies_have_no_blocking_errors(self):
        for language, body in IMOVELWEB_SAMPLE_BODIES.items():
            result = validate_imovelweb_payload(body, language=language)
            assert result["error"] == [], (language, result)
            assert has_blocking_violation(result) is False

    def test_missing_event_id_is_the_only_blocking_condition(self):
        result = validate_imovelweb_payload({"name": "x"}, language="EN2")
        assert has_blocking_violation(result) is True
        assert len(result["error"]) == 1
        assert "deduplicated" in result["error"][0]

    def test_non_object_payload_is_blocking(self):
        assert has_blocking_violation(
            validate_imovelweb_payload("not a body", language="EN2")
        )

    def test_unknown_language_is_blocking(self):
        assert has_blocking_violation(
            validate_imovelweb_payload({"eventId": "e"}, language="KLINGON")
        )

    @pytest.mark.parametrize(
        "body,fragment",
        [
            ({"eventId": "e", "eventType": "WAT"}, "unknown eventType"),
            ({"eventId": "e", "contactTypeId": 999}, "unknown contactTypeId"),
            ({"eventId": "e", "leadOrigin": "Nope"}, "unknown leadOrigin"),
            ({"eventId": "e"}, "no client listing code"),
            ({"eventId": "e"}, "no agency code"),
            ({"eventId": "e", "brandNewField": 1}, "undocumented field"),
        ],
    )
    def test_everything_else_is_only_a_warning(self, body, fragment):
        result = validate_imovelweb_payload(body, language="EN2")
        assert has_blocking_violation(result) is False
        assert any(fragment in w for w in result["warning"]), result["warning"]

    def test_missing_listing_code_warning_names_the_olx_divergence(self):
        result = validate_imovelweb_payload({"eventId": "e"}, language="EN2")
        listing = next(w for w in result["warning"] if "client listing" in w)
        assert "NOT a refusal" in listing


class TestDiffObserved:
    def test_reports_undocumented_and_never_observed(self):
        observed = [dict(IMOVELWEB_SAMPLE_BODIES["EN2"], surpriseField="!")]
        result = diff_observed(observed, language="EN2")
        assert "surpriseField" in result["undocumented_fields"]
        assert "eventId" in result["confirmed_fields"]
        assert "identificationId" in result["never_observed_fields"]

    def test_stays_unverified_until_a_human_acts(self):
        result = diff_observed([IMOVELWEB_SAMPLE_BODIES["EN2"]], language="EN2")
        assert result["verified_against_live_traffic"] is False
        assert "Never flip them from a document" in result["next_step"]

    def test_handles_an_empty_corpus(self):
        result = diff_observed([], language="EN2")
        assert result["bodies_examined"] == 0
        assert result["confirmed_fields"] == []

    def test_ignores_non_dict_entries(self):
        result = diff_observed([None, "junk", {"eventId": "e"}], language="EN2")
        assert result["confirmed_fields"] == ["eventId"]

    def test_rejects_an_unknown_language(self):
        with pytest.raises(ValueError, match="unknown language"):
            diff_observed([], language="KLINGON")


class TestContractSummary:
    def test_carries_the_caveat_about_the_spec(self):
        summary = contract_summary()
        assert "ZERO callback bodies" in summary["caveat"]

    def test_can_be_scoped_to_one_language(self):
        assert list(contract_summary("PT")["fields"]) == ["PT"]

    def test_unknown_language_yields_no_fields_rather_than_raising(self):
        # An agent asking about a language we do not model should get an
        # empty answer, not a stack trace.
        assert contract_summary("KLINGON")["fields"] == {}
