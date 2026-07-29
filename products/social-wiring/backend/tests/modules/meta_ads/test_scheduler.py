"""meta_ads scheduler — org-scoping (safe-by-default) tests.

Pins the 2026-07-23 fix: the daily sync must target the ONE org named by
``settings.meta_ads_org_id`` and must NEVER fan out across every tenant
in ``noctus_users`` (that leaked the operator's private ad spend into
other orgs' RLS-scoped rows). Unset ⇒ skip, never sync.

Driven through the scheduler's DI seams (``cfg`` / ``admin_client_factory`` /
``service_factory`` / ``adapter_factory``) rather than by patching this
module's own ``settings`` and ``AdsSyncService``. These tests assert a SAFETY
property, so the resolution they exercise has to be the real one — patching it
out to force the gating would have left the fan-out guard untested
(``KB § PATTERNS/compliance/testing.md``).
"""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.modules.meta_ads import scheduler as sched

# `resolve_meta_ads_config` reads DB-first, so the ambient shared DB must not
# answer — otherwise the real stored config would override each test's `cfg`.
pytestmark = pytest.mark.usefixtures("isolate_meta_config_db")

_ORG = "6dd73140-74a4-41c6-aeff-bc94b5312b53"


class _Cfg:
    """Settings stand-in — only the three Meta-Ads keys are ever read."""

    def __init__(self, *, org: str = "", account: str = "", token: str = "") -> None:
        self.meta_ads_org_id = org
        self.meta_ad_account_id = account
        self.meta_system_user_token = token


def test_target_org_id_returns_configured_uuid():
    assert sched._target_org_id(cfg=_Cfg(org=_ORG)) == UUID(_ORG)


def test_target_org_id_unset_returns_none():
    assert sched._target_org_id(cfg=_Cfg(org="")) is None


def test_target_org_id_malformed_returns_none():
    assert sched._target_org_id(cfg=_Cfg(org="not-a-uuid")) is None


def test_sync_job_skips_when_org_unset_and_never_builds_service():
    # token + account configured, but org NOT set → must skip WITHOUT
    # constructing an AdsSyncService or touching any adapter (no fan-out).
    service_factory = MagicMock()
    sched._sync_job_sync(
        cfg=_Cfg(account="act_123", token="tok", org=""),
        admin_client_factory=lambda: MagicMock(),
        service_factory=service_factory,
        adapter_factory=lambda **_: MagicMock(),
    )
    service_factory.assert_not_called()


def test_sync_job_targets_exactly_the_one_configured_org():
    svc = MagicMock()
    svc.snapshot_campaign_insights.return_value = 0
    svc.ingest_activities.return_value = 0

    sched._sync_job_sync(
        cfg=_Cfg(account="act_123", token="tok", org=_ORG),
        admin_client_factory=lambda: MagicMock(),
        service_factory=lambda **_: svc,
        adapter_factory=lambda **_: MagicMock(),
    )

    # Exactly one org synced — the configured one.
    assert svc.sync_accounts.call_count == 1
    assert svc.sync_accounts.call_args.kwargs["org_id"] == UUID(_ORG)


def test_sync_job_skips_when_not_configured_at_all():
    # Neither token nor account → the operator-actionable "not wired yet"
    # state. Must return before ever asking for an admin client.
    admin_factory = MagicMock()
    sched._sync_job_sync(
        cfg=_Cfg(),
        admin_client_factory=admin_factory,
        service_factory=MagicMock(),
        adapter_factory=lambda **_: MagicMock(),
    )
    admin_factory.assert_not_called()


def test_sync_job_skips_when_admin_client_is_unavailable():
    service_factory = MagicMock()
    sched._sync_job_sync(
        cfg=_Cfg(account="act_123", token="tok", org=_ORG),
        admin_client_factory=lambda: None,
        service_factory=service_factory,
        adapter_factory=lambda **_: MagicMock(),
    )
    service_factory.assert_not_called()
