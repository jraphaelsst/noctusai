"""The portal splitter — a seam that must not be able to invent attribution.

Two properties carry this module, and both are about what it REFUSES:

  * with no rules (today's shipped state) every lead resolves to the
    `grupo-olx` umbrella, so nothing is split on a guess;
  * a rule cannot be constructed without evidence, or against a slug that
    has no `lead_sources` row — the two ways a plausible-looking guess
    would otherwise become permanent Portal ROI attribution.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.olx import (
    OLX_PORTAL_RULES,
    OLX_SOURCE_SLUG,
    PortalRule,
    parse_olx_lead_webhook,
    resolve_portal_source_slug,
)


def _lead(**extra):
    body = {
        "leadOrigin": "Grupo OLX",
        "originLeadId": "abc-1",
        "timestamp": "2026-08-17T10:00:00Z",
        "name": "Fulano",
        "email": "f@example.com",
        "ddd": "11",
        "phone": "981912534",
        **extra,
    }
    lead = parse_olx_lead_webhook(body)
    assert lead is not None
    return lead


class TestShippedState:
    def test_the_rule_table_is_empty_on_purpose(self):
        # If this ever fails, someone added a rule — check it carries a real
        # observation, not an inference from the vendor docs.
        assert OLX_PORTAL_RULES == ()

    def test_every_lead_defaults_to_the_umbrella_slug(self):
        result = resolve_portal_source_slug(_lead())

        assert result.slug == OLX_SOURCE_SLUG
        assert result.rule is None
        assert result.is_split is False

    def test_an_mcmv_lead_is_not_split_either(self):
        # MCMV is a PROGRAM (Minha Casa Minha Vida), not a portal — a
        # tempting thing to split on, and it would be wrong.
        assert resolve_portal_source_slug(
            _lead(leadOrigin="MCMV_OLX")
        ).slug == OLX_SOURCE_SLUG


class TestRuleValidation:
    def test_a_rule_without_evidence_is_refused(self):
        with pytest.raises(ValueError, match="evidence"):
            PortalRule(slug="zap", field="leadOrigin", equals="ZapImoveis", evidence="")

    def test_a_rule_for_an_unknown_slug_is_refused(self):
        # `lead_sources` has no such row, so the lead would vanish from
        # Portal ROI rather than be misfiled — worse, not better.
        with pytest.raises(ValueError, match="not a known Grupo OLX portal slug"):
            PortalRule(
                slug="zap-imoveis", field="leadOrigin", equals="x", evidence="obs"
            )

    @pytest.mark.parametrize(
        "kwargs",
        [
            {},                                        # neither
            {"equals": "a", "contains": "b"},           # both
        ],
    )
    def test_exactly_one_matcher_is_required(self, kwargs):
        with pytest.raises(ValueError, match="exactly one"):
            PortalRule(slug="zap", field="leadOrigin", evidence="obs", **kwargs)


class TestMatching:
    """Exercised with explicit rules so the mechanism is proven NOW, and
    Gate 1 only has to supply data."""

    def test_equals_matches_a_raw_body_field(self):
        rule = PortalRule(
            slug="zap", field="leadOrigin", equals="ZapImoveis",
            evidence="hypothetical — test-only, never shipped in OLX_PORTAL_RULES",
        )

        result = resolve_portal_source_slug(
            _lead(leadOrigin="ZapImoveis"), rules=(rule,)
        )

        assert result.slug == "zap"
        assert result.rule is rule
        assert result.is_split is True

    def test_matches_a_dotted_path_the_parser_does_not_model(self):
        # The likely Gate-1 shape: a key we have never seen before.
        rule = PortalRule(
            slug="viva-real", field="extraData.sourcePortal", equals="VIVAREAL",
            evidence="hypothetical — test-only",
        )

        result = resolve_portal_source_slug(
            _lead(extraData={"sourcePortal": "VIVAREAL"}), rules=(rule,)
        )

        assert result.slug == "viva-real"

    def test_contains_is_case_insensitive(self):
        rule = PortalRule(
            slug="imovel-web", field="leadOrigin", contains="imovelweb",
            evidence="hypothetical — test-only",
        )

        assert resolve_portal_source_slug(
            _lead(leadOrigin="Grupo OLX / ImovelWeb"), rules=(rule,)
        ).slug == "imovel-web"

    def test_first_matching_rule_wins(self):
        first = PortalRule(
            slug="zap", field="leadOrigin", contains="olx", evidence="test-only",
        )
        second = PortalRule(
            slug="olx", field="leadOrigin", contains="grupo", evidence="test-only",
        )

        assert resolve_portal_source_slug(
            _lead(), rules=(first, second)
        ).slug == "zap"

    def test_a_non_matching_rule_falls_back_to_the_umbrella(self):
        rule = PortalRule(
            slug="zap", field="extraData.sourcePortal", equals="ZAP",
            evidence="test-only",
        )

        assert resolve_portal_source_slug(
            _lead(), rules=(rule,)
        ).slug == OLX_SOURCE_SLUG

    def test_attribution_never_raises_on_a_weird_body(self):
        # Attribution must not be able to reject a real lead.
        rule = PortalRule(
            slug="zap", field="extraData.nested.deep", equals="x", evidence="test-only",
        )

        result = resolve_portal_source_slug(
            _lead(extraData={"nested": "not-a-dict"}), rules=(rule,)
        )

        assert result.slug == OLX_SOURCE_SLUG
