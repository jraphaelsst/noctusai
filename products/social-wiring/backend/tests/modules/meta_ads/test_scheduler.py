"""meta_ads scheduler — org-scoping (safe-by-default) tests.

Pins the 2026-07-23 fix: the daily sync must target the ONE org named by
``settings.meta_ads_org_id`` and must NEVER fan out across every tenant
in ``noctus_users`` (that leaked the operator's private ad spend into
other orgs' RLS-scoped rows). Unset ⇒ skip, never sync.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from app.modules.meta_ads import scheduler as sched

# _target_org_id / _sync_job_sync resolve the org DB-first
# (resolve_meta_ads_config); these tests drive the gating via a patched
# `settings.meta_ads_org_id`, so isolate them from the ambient shared DB.
pytestmark = pytest.mark.usefixtures("isolate_meta_config_db")

_ORG = "6dd73140-74a4-41c6-aeff-bc94b5312b53"


def test_target_org_id_returns_configured_uuid():
    with patch.object(sched.settings, "meta_ads_org_id", _ORG):
        assert sched._target_org_id() == UUID(_ORG)


def test_target_org_id_unset_returns_none():
    with patch.object(sched.settings, "meta_ads_org_id", ""):
        assert sched._target_org_id() is None


def test_target_org_id_malformed_returns_none():
    with patch.object(sched.settings, "meta_ads_org_id", "not-a-uuid"):
        assert sched._target_org_id() is None


def test_sync_job_skips_when_org_unset_and_never_builds_service():
    # token + account configured, but org NOT set → must skip WITHOUT
    # constructing an AdsSyncService or touching any adapter (no fan-out).
    with patch.object(sched.settings, "meta_ad_account_id", "act_123"), \
         patch.object(sched.settings, "meta_system_user_token", "tok"), \
         patch.object(sched.settings, "meta_ads_org_id", ""), \
         patch.object(sched, "get_admin_client", return_value=MagicMock()), \
         patch(
             "app.modules.meta_ads.services.ads_sync_service.AdsSyncService"
         ) as svc_cls:
        sched._sync_job_sync()
    svc_cls.assert_not_called()


def test_sync_job_targets_exactly_the_one_configured_org():
    svc = MagicMock()
    svc.snapshot_campaign_insights.return_value = 0
    svc.ingest_activities.return_value = 0
    with patch.object(sched.settings, "meta_ad_account_id", "act_123"), \
         patch.object(sched.settings, "meta_system_user_token", "tok"), \
         patch.object(sched.settings, "meta_ads_org_id", _ORG), \
         patch.object(sched, "get_admin_client", return_value=MagicMock()), \
         patch(
             "app.modules.meta_ads.services.ads_sync_service.AdsSyncService",
             return_value=svc,
         ), \
         patch("app.services.meta.get_meta_adapter", return_value=MagicMock()):
        sched._sync_job_sync()
    # Exactly one org synced — the configured one.
    assert svc.sync_accounts.call_count == 1
    assert svc.sync_accounts.call_args.kwargs["org_id"] == UUID(_ORG)
