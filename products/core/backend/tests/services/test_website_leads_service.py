"""Tests for `app.services.website_leads_service` (contract §1, §3, dedupe)."""
import pytest
from unittest.mock import patch

from app.schemas.website import WebsiteLeadCreate
from app.services import website_leads_service
from tests.conftest import MockSupabaseClient


@pytest.fixture
def mock_sb():
    return MockSupabaseClient()


def _patched(mock_sb):
    return patch("app.services.website_leads_service.get_admin_client", return_value=mock_sb)


def _lead_body(**overrides) -> WebsiteLeadCreate:
    defaults = dict(
        source="waitlist", name="Ana Silva", email="ana@example.com", phone=None,
        company=None, profile=None, product_interest=None, message=None,
        locale="pt-BR", consent_marketing=True, consent_text_version="v1",
        utm=None, landing_path="/", referrer=None, turnstile_token=None,
    )
    defaults.update(overrides)
    return WebsiteLeadCreate(**defaults)


class TestCreateOrMergeLead:
    def test_neither_email_nor_valid_phone_raises(self, mock_sb):
        body = _lead_body(email=None, phone="not-a-phone")
        with _patched(mock_sb):
            with pytest.raises(website_leads_service.WebsiteLeadContactMissing):
                website_leads_service.create_or_merge_lead(body, ip_hash="h")

    def test_creates_new_lead_with_created_activity(self, mock_sb):
        mock_sb.set_table_data("website_leads", [])
        mock_sb.set_table_data("website_lead_activities", [])
        with _patched(mock_sb):
            lead, created = website_leads_service.create_or_merge_lead(_lead_body(), ip_hash="h")
        assert created is True
        assert lead["email"] == "ana@example.com"
        assert lead["dedupe_key"] == "email:ana@example.com"

    def test_phone_normalized_to_e164_default_br(self, mock_sb):
        mock_sb.set_table_data("website_leads", [])
        mock_sb.set_table_data("website_lead_activities", [])
        body = _lead_body(email=None, phone="11 98765-4321")
        with _patched(mock_sb):
            lead, _created = website_leads_service.create_or_merge_lead(body, ip_hash="h")
        assert lead["phone_e164"] == "+5511987654321"

    def test_resubmission_merges_into_existing_lead(self, mock_sb):
        existing = {
            "id": "lead-1", "email": "ana@example.com", "dedupe_key": "email:ana@example.com",
            "source": "waitlist", "stage": "novo", "company": None,
        }
        mock_sb.set_table_data("website_leads", [existing])
        mock_sb.set_table_data("website_lead_activities", [])
        with _patched(mock_sb):
            lead, created = website_leads_service.create_or_merge_lead(
                _lead_body(company="Acme"), ip_hash="h"
            )
        assert created is False
        assert lead["id"] == "lead-1"

    def test_email_wins_dedupe_key_over_phone(self, mock_sb):
        mock_sb.set_table_data("website_leads", [])
        mock_sb.set_table_data("website_lead_activities", [])
        body = _lead_body(email="ana@example.com", phone="11987654321")
        with _patched(mock_sb):
            lead, _created = website_leads_service.create_or_merge_lead(body, ip_hash="h")
        assert lead["dedupe_key"] == "email:ana@example.com"


class TestHashIp:
    def test_none_ip_returns_marker(self):
        assert website_leads_service.hash_ip(None) == "unknown"

    def test_same_ip_hashes_deterministically(self):
        a = website_leads_service.hash_ip("1.2.3.4")
        b = website_leads_service.hash_ip("1.2.3.4")
        assert a == b
        assert a != website_leads_service.hash_ip("5.6.7.8")


class TestPatchLead:
    def test_stage_change_appends_activity(self, mock_sb):
        mock_sb.set_table_data("website_leads", [{"id": "lead-1", "stage": "novo"}])
        mock_sb.set_table_data("website_lead_activities", [])
        with _patched(mock_sb):
            updated = website_leads_service.patch_lead("lead-1", {"stage": "contatado"}, actor="user:u1")
        assert updated["stage"] == "contatado"

    def test_missing_lead_returns_none(self, mock_sb):
        mock_sb.set_table_data("website_leads", [])
        with _patched(mock_sb):
            result = website_leads_service.patch_lead("missing", {"stage": "contatado"}, actor="user:u1")
        assert result is None


class TestAddActivity:
    def test_missing_lead_returns_none(self, mock_sb):
        mock_sb.set_table_data("website_leads", [])
        with _patched(mock_sb):
            result = website_leads_service.add_activity("missing", "note", "hi", actor="user:u1")
        assert result is None
