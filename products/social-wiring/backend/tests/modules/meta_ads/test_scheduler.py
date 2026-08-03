"""meta_ads scheduler — org-scoping (safe-by-default) + lead-sync tests.

Pins the 2026-07-23 fix: the daily sync must target the ONE org named by
``settings.meta_ads_org_id`` and must NEVER fan out across every tenant
in ``noctus_users`` (that leaked the operator's private ad spend into
other orgs' RLS-scoped rows). Unset ⇒ skip, never sync.

Also pins the 2026-08-03 fix: the daily job must call ``LeadsSyncService``.
Before it did, the ONLY consumer of that service was the manual
``POST /leads/sync`` button, so campaign leads silently stopped arriving
while every ads table kept updating — a stall that reads as "the Meta
integration is broken" rather than "nobody pressed the button."

Driven through the scheduler's DI seams (``cfg`` / ``admin_client_factory`` /
``service_factory`` / ``adapter_factory`` / ``leads_service_factory``) rather
than by patching this module's own ``settings`` and ``AdsSyncService``. These
tests assert SAFETY properties, so the resolution they exercise has to be the
real one — patching it out to force the gating would have left the fan-out
guard untested (``KB § PATTERNS/compliance/testing.md``).
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


# ─── lead sync on the daily job (2026-08-03) ──────────────────────────────


def _leads_result(forms: int = 0, leads: int = 0, gated: bool = False) -> dict:
    return {
        "forms_upserted": forms,
        "leads_upserted": leads,
        "records_gated": gated,
    }


def _ads_svc() -> MagicMock:
    svc = MagicMock()
    svc.snapshot_campaign_insights.return_value = 0
    svc.ingest_activities.return_value = 0
    return svc


def test_daily_sync_calls_leads_sync_all():
    """🔴 THE regression guard. If this fails, campaign leads have silently
    stopped syncing on a schedule again — the exact 2026-07-29 → 2026-08-03
    stall this test exists to prevent."""
    leads_svc = MagicMock()
    leads_svc.sync_all.return_value = _leads_result(forms=298, leads=958)
    adapter = MagicMock()

    sched._sync_job_sync(
        cfg=_Cfg(account="act_123", token="tok", org=_ORG),
        admin_client_factory=lambda: MagicMock(),
        service_factory=lambda **_: _ads_svc(),
        adapter_factory=lambda **_: adapter,
        leads_service_factory=lambda **_: leads_svc,
    )

    assert leads_svc.sync_all.call_count == 1
    kwargs = leads_svc.sync_all.call_args.kwargs
    # Same org the ads half targets — never a fan-out, never a different org.
    assert kwargs["org_id"] == UUID(_ORG)
    # Same adapter instance: one resolved token per run, not a second build.
    assert kwargs["adapter"] is adapter


def test_lead_sync_runs_after_the_ads_calls():
    """Ordering is a real property, not incidental: the ads writes must be
    committed before lead ingest runs, so a Graph failure on the lead leg
    cannot cost us the ads results already fetched."""
    order: list[str] = []
    ads = MagicMock()
    ads.sync_accounts.side_effect = lambda **_: order.append("accounts")
    ads.sync_hierarchy.side_effect = lambda **_: order.append("hierarchy")
    ads.snapshot_campaign_insights.side_effect = (
        lambda **_: (order.append("insights"), 0)[1]
    )
    ads.ingest_activities.side_effect = (
        lambda **_: (order.append("activities"), 0)[1]
    )
    leads = MagicMock()
    leads.sync_all.side_effect = (
        lambda **_: (order.append("leads"), _leads_result())[1]
    )

    sched._sync_job_sync(
        cfg=_Cfg(account="act_123", token="tok", org=_ORG),
        admin_client_factory=lambda: MagicMock(),
        service_factory=lambda **_: ads,
        adapter_factory=lambda **_: MagicMock(),
        leads_service_factory=lambda **_: leads,
    )

    assert order == ["accounts", "hierarchy", "insights", "activities", "leads"]


def test_lead_sync_not_attempted_when_org_unset():
    """The fan-out guard covers the lead leg too — an unset org must not
    reach LeadsSyncService any more than it reaches AdsSyncService."""
    leads_factory = MagicMock()
    sched._sync_job_sync(
        cfg=_Cfg(account="act_123", token="tok", org=""),
        admin_client_factory=lambda: MagicMock(),
        service_factory=MagicMock(),
        adapter_factory=lambda **_: MagicMock(),
        leads_service_factory=leads_factory,
    )
    leads_factory.assert_not_called()


def test_records_gated_is_surfaced_in_the_summary_log(caplog):
    """A missing ``leads_retrieval`` scope must be VISIBLE in the run summary.
    Silently logging `leads=0` would be indistinguishable from "no new leads"
    — the no-silent-errors contract applies to log lines too."""
    leads_svc = MagicMock()
    leads_svc.sync_all.return_value = _leads_result(forms=12, leads=0, gated=True)

    with caplog.at_level("INFO", logger=sched.logger.name):
        sched._sync_job_sync(
            cfg=_Cfg(account="act_123", token="tok", org=_ORG),
            admin_client_factory=lambda: MagicMock(),
            service_factory=lambda **_: _ads_svc(),
            adapter_factory=lambda **_: MagicMock(),
            leads_service_factory=lambda **_: leads_svc,
        )

    summary = [r.getMessage() for r in caplog.records if "done —" in r.getMessage()]
    assert summary, "no run-summary line was logged"
    assert "leads_retrieval" in summary[-1]
    assert "forms=12" in summary[-1]


def test_summary_log_reports_lead_counts_when_not_gated():
    """The counts have to reach the log — that line is the only way an
    operator (or `noctus_vps_logs`) can tell a healthy run from a stalled one."""
    leads_svc = MagicMock()
    leads_svc.sync_all.return_value = _leads_result(forms=298, leads=17)

    import logging

    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[method-assign]
    sched.logger.addHandler(handler)
    sched.logger.setLevel(logging.INFO)
    try:
        sched._sync_job_sync(
            cfg=_Cfg(account="act_123", token="tok", org=_ORG),
            admin_client_factory=lambda: MagicMock(),
            service_factory=lambda **_: _ads_svc(),
            adapter_factory=lambda **_: MagicMock(),
            leads_service_factory=lambda **_: leads_svc,
        )
    finally:
        sched.logger.removeHandler(handler)

    summary = [r.getMessage() for r in records if "done —" in r.getMessage()]
    assert summary, "no run-summary line was logged"
    assert "forms=298" in summary[-1] and "leads=17" in summary[-1]
    assert "leads_retrieval" not in summary[-1]
