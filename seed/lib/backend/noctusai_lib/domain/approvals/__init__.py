"""Approvals -- a versioned approve / reject gate over any subject. An L0 seed organ (no UI, no router: the host exposes endpoints).

A subject is `(subject_kind, subject_id)` -- a roteiro, a media, a quote -- and the host numbers its versions. `submit(versao)`
puts a versao up for approval; `approve` / `reject` decide the CURRENT one (reject needs a motivo); a stale versao is refused; a
newer `submit` makes the earlier decision history, so editing after approval invalidates it. Approval is always required:
`is_approved` is False for a subject nobody submitted. Every change is an immutable intent-named event in `apr_events`
(`submitted` / `approved` / `rejected`, who/when/why) written atomically by the `apr_record` RPC -- no state table to drift.

    cfg = ApprovalsConfig(schema="social_wiring")
    sql = approvals_migration(cfg, "social_wiring")                 # -> migrations/0NN_approvals.sql (noctus.dev.render_organ_migration)
    svc = ApprovalService(build_approvals_store(cfg, supabase_client=admin_client), cfg)
    svc.submit(org, "roteiro", roteiro_id, 3, actor_id=user)       # the host calls this when it saves a new versao
    svc.approve(org, "roteiro", roteiro_id, 3, actor_id=user)      # any org member (the host authorizes the call)
    svc.is_approved(org, "roteiro", roteiro_id)                    # the gate the host's workflow checks
"""
from .config import ApprovalsConfig
from .errors import AlreadyDecided, ApprovalError, NotSubmitted, StaleVersion
from .guards import approvals_guard_probes
from .service import ApprovalService, ApprovalState
from .sql import APPEND_ONLY_TABLES, APPROVALS_MIGRATION_HEADER, APPROVALS_TABLES, approvals_migration
from .store import (
    ApprovalLedger,
    ApprovalStore,
    FakeApprovalLedger,
    SupabaseApprovalLedger,
    build_approvals_store,
    table_specs,
)
from .types import DECISION_EVENTS, EVENT_KINDS, STATUSES

__all__ = [
    "APPEND_ONLY_TABLES", "APPROVALS_MIGRATION_HEADER", "APPROVALS_TABLES", "AlreadyDecided", "ApprovalError", "ApprovalLedger",
    "ApprovalService", "ApprovalState", "ApprovalStore", "ApprovalsConfig", "DECISION_EVENTS", "EVENT_KINDS",
    "FakeApprovalLedger", "NotSubmitted", "STATUSES", "StaleVersion", "SupabaseApprovalLedger", "approvals_guard_probes",
    "approvals_migration", "build_approvals_store", "table_specs",
]
