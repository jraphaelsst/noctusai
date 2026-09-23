"""Tests for `app.services.website_settings_service` (contract §2)."""
import pytest
from unittest.mock import patch

from app.services import website_settings_service
from tests.conftest import MockSupabaseClient, website_defaults_dict


@pytest.fixture
def mock_sb():
    return MockSupabaseClient()


def _patched(mock_sb):
    return patch("app.services.website_settings_service.get_admin_client", return_value=mock_sb)


class TestGetCurrent:
    def test_no_rows_falls_back_to_defaults_file_as_version_0(self, mock_sb, website_site):
        mock_sb.set_table_data("website_settings", [])
        with _patched(mock_sb):
            version, data = website_settings_service.get_current(use_cache=False)
        assert version == 0
        assert data == website_defaults_dict()

    def test_missing_defaults_file_raises_loudly(self, mock_sb, tmp_path):
        from app.services import website_paths

        mock_sb.set_table_data("website_settings", [])
        website_paths.configure_site_dir(tmp_path / "nowhere")
        try:
            with _patched(mock_sb):
                with pytest.raises(website_settings_service.WebsiteDefaultsMissing):
                    website_settings_service.get_current(use_cache=False)
        finally:
            website_paths.reset_site_dir()

    def test_returns_current_row_when_present(self, mock_sb, website_site):
        row = {"version": 3, "data": {**website_defaults_dict(), "site_enabled": False}}
        mock_sb.set_table_data("website_settings", [row])
        with _patched(mock_sb):
            version, data = website_settings_service.get_current(use_cache=False)
        assert version == 3
        assert data["site_enabled"] is False

    def test_cache_is_honored_within_ttl(self, mock_sb, website_site):
        mock_sb.set_table_data("website_settings", [{"version": 1, "data": website_defaults_dict()}])
        with _patched(mock_sb):
            version_a, _ = website_settings_service.get_current()
            # Mutate the underlying data — a cached read must NOT see it.
            mock_sb.set_table_data("website_settings", [{"version": 2, "data": website_defaults_dict()}])
            version_b, _ = website_settings_service.get_current()
        assert version_a == version_b == 1


class TestPublicSubset:
    def test_filters_unverified_trust_items_and_strips_verified_by(self):
        data = website_defaults_dict()
        out = website_settings_service.public_subset(data)
        assert len(out["trust_items"]) == 1
        assert out["trust_items"][0]["key"] == "iso"
        assert "verified_by" not in out["trust_items"][0]

    def test_empties_social_proof_when_section_off(self):
        data = website_defaults_dict()
        data["sections"]["social_proof"] = False
        data["social_proof_items"] = [{"kind": "logo", "name": "x", "consent_ref": "ref-1"}]
        out = website_settings_service.public_subset(data)
        assert out["social_proof_items"] == []

    def test_strips_consent_ref_when_section_on(self):
        data = website_defaults_dict()
        data["sections"]["social_proof"] = True
        data["social_proof_items"] = [{"kind": "logo", "name": "x", "consent_ref": "ref-1"}]
        out = website_settings_service.public_subset(data)
        assert out["social_proof_items"] == [{"kind": "logo", "name": "x"}]

    def test_filters_products_to_visible(self):
        data = website_defaults_dict()
        out = website_settings_service.public_subset(data)
        slugs = {p["slug"] for p in out["products"]}
        assert slugs == {"erp-imobiliario"}


class TestUpdate:
    def test_version_conflict(self, mock_sb, website_site):
        mock_sb.set_table_data("website_settings", [{"version": 5, "data": website_defaults_dict()}])
        with _patched(mock_sb):
            with pytest.raises(website_settings_service.WebsiteVersionConflict):
                website_settings_service.update(website_defaults_dict(), expected_version=4, created_by=None)

    def test_social_proof_on_with_zero_items_rejected(self, mock_sb, website_site):
        mock_sb.set_table_data("website_settings", [])
        bad = website_defaults_dict()
        bad["sections"]["social_proof"] = True
        bad["social_proof_items"] = []
        with _patched(mock_sb):
            with pytest.raises(website_settings_service.WebsiteSocialProofEmpty):
                website_settings_service.update(bad, expected_version=0, created_by=None)

    def test_success_inserts_next_version_and_invalidates_cache(self, mock_sb, website_site):
        mock_sb.set_table_data("website_settings", [])
        new_data = website_defaults_dict()
        new_data["site_enabled"] = False
        with _patched(mock_sb):
            row = website_settings_service.update(new_data, expected_version=0, created_by="user-1")
        assert row["version"] == 1
        assert row["data"]["site_enabled"] is False


class TestRollback:
    def test_missing_version_raises_lookup_error(self, mock_sb, website_site):
        mock_sb.set_table_data("website_settings", [])
        with _patched(mock_sb):
            with pytest.raises(LookupError):
                website_settings_service.rollback(99, created_by=None)
