"""license_service — grants/revokes by source; legacy licenses are untouchable."""
from __future__ import annotations

import pytest

from noctusai_lib.testing import MockSupabaseClient

from app.services import license_service
from tests.billing_fakes import NOW, ORG_ID, PRODUCT_ID, Clock

SUB_ID = "66666666-6666-6666-6666-666666666666"


@pytest.fixture
def db() -> MockSupabaseClient:
    return MockSupabaseClient()


def test_manual_grant_inserts_a_manual_license(db):
    db.set_table_data("licenses", [])
    result = license_service.grant_license(db, org_id=ORG_ID, product_id=PRODUCT_ID)
    assert result.created and result.reason == "created"
    assert db.table("licenses").inserted_payloads == [
        {"org_id": ORG_ID, "product_id": PRODUCT_ID, "status": "active", "source": "manual"}
    ]


def test_manual_grant_over_an_active_license_conflicts(db):
    db.set_table_data("licenses", [
        {"id": "lic-1", "org_id": ORG_ID, "product_id": PRODUCT_ID, "status": "active", "source": "legacy"},
    ])
    with pytest.raises(license_service.LicenseConflict):
        license_service.grant_license(db, org_id=ORG_ID, product_id=PRODUCT_ID)


def test_subscription_grant_never_adopts_or_duplicates_a_legacy_license(db):
    db.set_table_data("licenses", [
        {"id": "lic-legacy", "org_id": ORG_ID, "product_id": PRODUCT_ID, "status": "active",
         "source": "legacy", "subscription_id": None},
    ])
    result = license_service.grant_license(
        db, org_id=ORG_ID, product_id=PRODUCT_ID, source="subscription", subscription_id=SUB_ID
    )
    assert result.created is False
    assert result.reason == "covered_by_existing"
    assert db.table("licenses").inserted_payloads == []
    assert db.table("licenses").updated_payloads == []


def test_subscription_grant_is_idempotent(db):
    db.set_table_data("licenses", [
        {"id": "lic-sub", "org_id": ORG_ID, "product_id": PRODUCT_ID, "status": "active",
         "source": "subscription", "subscription_id": SUB_ID},
    ])
    result = license_service.grant_license(
        db, org_id=ORG_ID, product_id=PRODUCT_ID, source="subscription", subscription_id=SUB_ID
    )
    assert (result.created, result.reason) == (False, "already_granted")


@pytest.mark.parametrize("source", ["legacy", "bogus"])
def test_grant_refuses_legacy_or_unknown_source(db, source):
    with pytest.raises(ValueError):
        license_service.grant_license(db, org_id=ORG_ID, product_id=PRODUCT_ID, source=source)


def test_subscription_grant_requires_subscription_id(db):
    with pytest.raises(ValueError):
        license_service.grant_license(db, org_id=ORG_ID, product_id=PRODUCT_ID, source="subscription")


def test_revoke_subscription_licenses_touches_only_that_subscriptions_grant(db):
    db.set_table_data("licenses", [
        {"id": "lic-legacy", "org_id": ORG_ID, "product_id": PRODUCT_ID, "status": "active",
         "source": "legacy", "subscription_id": None, "fim": None},
        # Mislinked on purpose: a legacy row carrying the subscription id must
        # STILL be untouched — the source filter is the guarantee.
        {"id": "lic-mislinked", "org_id": ORG_ID, "product_id": "p2", "status": "active",
         "source": "legacy", "subscription_id": SUB_ID, "fim": None},
        {"id": "lic-manual", "org_id": ORG_ID, "product_id": "p3", "status": "active",
         "source": "manual", "subscription_id": None, "fim": None},
        {"id": "lic-sub", "org_id": ORG_ID, "product_id": "p4", "status": "active",
         "source": "subscription", "subscription_id": SUB_ID, "fim": None},
        {"id": "lic-other-sub", "org_id": ORG_ID, "product_id": "p5", "status": "active",
         "source": "subscription", "subscription_id": "other", "fim": None},
    ])
    revoked = license_service.revoke_subscription_licenses(db, SUB_ID, clock=Clock())
    assert [r["id"] for r in revoked] == ["lic-sub"]
    rows = {r["id"]: r for r in db.table("licenses").select("*").execute().data}
    assert rows["lic-sub"]["status"] == "revoked"
    assert rows["lic-sub"]["fim"] == NOW.isoformat()
    for untouched in ("lic-legacy", "lic-mislinked", "lic-manual", "lic-other-sub"):
        assert rows[untouched]["status"] == "active"
        assert rows[untouched]["fim"] is None


def test_revoke_subscription_licenses_is_idempotent(db):
    db.set_table_data("licenses", [
        {"id": "lic-sub", "org_id": ORG_ID, "product_id": "p4", "status": "revoked",
         "source": "subscription", "subscription_id": SUB_ID},
    ])
    assert license_service.revoke_subscription_licenses(db, SUB_ID) == []


def test_admin_revoke_returns_none_for_unknown_license(db):
    db.set_table_data("licenses", [])
    assert license_service.revoke_license(db, "nope") is None
