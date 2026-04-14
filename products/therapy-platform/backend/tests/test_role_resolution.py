"""
Tests for SSO + therapy-native role resolution in dependencies.py.

Verifies the priority chain:
1. org_role (owner/admin) → platform_admin
2. noctus_role (admin) → platform_admin
3. Therapy-native role → as-is
4. Default → patient
"""
from types import SimpleNamespace

from app.dependencies import get_user_role


def _user(metadata=None):
    """Create a mock user with given user_metadata."""
    return SimpleNamespace(user_metadata=metadata or {})


# ── SSO-derived roles ─────────────────────────────────────────


class TestSSOOrgRole:
    def test_org_owner_is_platform_admin(self):
        assert get_user_role(_user({"org_role": "owner"})) == "platform_admin"

    def test_org_admin_is_platform_admin(self):
        assert get_user_role(_user({"org_role": "admin"})) == "platform_admin"

    def test_org_member_is_not_admin(self):
        assert get_user_role(_user({"org_role": "member"})) == "patient"

    def test_org_viewer_is_not_admin(self):
        assert get_user_role(_user({"org_role": "viewer"})) == "patient"


class TestSSONoctusRole:
    def test_noctus_admin_is_platform_admin(self):
        assert get_user_role(_user({"noctus_role": "admin"})) == "platform_admin"

    def test_noctus_user_is_not_admin(self):
        assert get_user_role(_user({"noctus_role": "user"})) == "patient"

    def test_noctus_manager_is_not_admin(self):
        assert get_user_role(_user({"noctus_role": "manager"})) == "patient"


class TestSSOPriority:
    def test_org_role_takes_precedence_over_noctus_role(self):
        """org_role=owner wins even if noctus_role is just 'user'."""
        assert get_user_role(_user({
            "org_role": "owner",
            "noctus_role": "user",
        })) == "platform_admin"

    def test_noctus_admin_overrides_member_org_role(self):
        """noctus_role=admin wins even if org_role is 'member'."""
        assert get_user_role(_user({
            "org_role": "member",
            "noctus_role": "admin",
        })) == "platform_admin"


# ── Therapy-native roles ─────────────────────────────────────


class TestTherapyNativeRoles:
    def test_platform_admin_native(self):
        assert get_user_role(_user({"role": "platform_admin"})) == "platform_admin"

    def test_clinic_admin(self):
        assert get_user_role(_user({"role": "clinic_admin"})) == "clinic_admin"

    def test_therapist(self):
        assert get_user_role(_user({"role": "therapist"})) == "therapist"

    def test_patient(self):
        assert get_user_role(_user({"role": "patient"})) == "patient"

    def test_unknown_role_defaults_to_patient(self):
        assert get_user_role(_user({"role": "unknown"})) == "patient"


# ── Edge cases ───────────────────────────────────────────────


class TestEdgeCases:
    def test_no_metadata(self):
        assert get_user_role(_user(None)) == "patient"

    def test_empty_metadata(self):
        assert get_user_role(_user({})) == "patient"

    def test_sso_overrides_native_role(self):
        """SSO org_role=owner wins even if native role is 'patient'."""
        assert get_user_role(_user({
            "org_role": "owner",
            "role": "patient",
        })) == "platform_admin"

    def test_native_role_used_when_no_sso(self):
        """Without SSO fields, native role is used."""
        assert get_user_role(_user({"role": "therapist"})) == "therapist"
