"""Domain — reusable business primitives that aren't product-specific
but ARE feature-specific.

**Layer contract.** Anything in `domain/` MUST:
- Encode platform-wide business semantics (notifications, invitations,
  audit logs, page-status tracking, AI consent + outputs, gamification).
- Be product-agnostic — every product is a potential consumer. If a
  helper is single-product, it belongs in that product's `app/`, not
  here.
- May import from `primitives/`, `config/`, `integrations/`.
- MUST NOT import from `api/` — domain code is consumed BY API
  handlers, not the reverse.

**Why a layer.** Cross-product domain helpers used to live at the
seed-lib top level (`notifications.py`, `invitations.py`, `action_log.py`,
`page_status.py`, `ai/`). Each one is a feature surface that may grow
into a folder over time (notifications already has multiple shapes per
product). Putting them under `domain/` creates a clear "platform
business logic" namespace.

**Active occupants:**
- `notifications.py` — notification creation + dispatch
- `invitations.py` — invite-token lifecycle
- `action_log.py` — audit-log helpers
- `page_status.py` — per-page roll-up status
- `ai/` — clinical-text consent + output policies (consent.py + outputs.py)
- `digest/` — narrative + render + send orchestration shared across N=5
  product digest services (audit / metas / monthly-narrative / weekly-review /
  campaign-debrief). Sits *upstream* of `integrations/email/digest.py`
  (which owns the Resend transport).
- `sql_templates.py` — authoring-time helpers for canonical SQL DDL
  (set_search_path, updated_at_function, updated_at_trigger,
  rls_subquery_policy). Pure string emission; no IO. Used in new
  migration files + the scaffold tool so the SECURITY DEFINER /
  search_path / RLS subquery conventions can't drift across products.
- `metas/` — goals / targets / budgets domain (value-and-target tracking)
  shared across PF (financial goals + budgets), ERP (sales targets +
  proportional cascade) and Daily Life (habit check-ins). Pure-domain:
  value objects (`Goal`, `Target`, `Progress`, `Period`, `Contribution`),
  enums (`GoalStatus`, `PeriodKind`), pure-function helpers
  (`compute_progress`, `accumulate_contribution`, `period_bounds`,
  `proportional_target`, `next_status`), and a `GoalRepository` Protocol
  seam for product-side persistence. Lifted 2026-05-03 per N=3
  MUST-FORMALIZE. See `KB § PATTERNS/metas-seed.md`.
- `jobs/` — generic background-job primitive. `Job` frozen dataclass +
  `JobStatus` state machine + pure-function transitions + `RetryPolicy`
  exponential backoff + `JobRepository` Protocol+Fake+RealSupabase+factory
  + async `Worker` (polling loop + dispatch). Lifted 2026-05-04 from
  the chatbot-coupled `domain/chatbot/worker.py` shape into a
  domain-agnostic surface. Consumers: youtube-crawler uploads,
  scheduling tasks, AI batches, future long-running products. Per
  `projects/seed-hardening-from-youtube-crawler/` Phase 2.1 + 2.2.

**Future occupants:**
- `gamification/` (when ERP Metas patterns extract)

See `KB § PATTERNS/seed-lib-layout.md` for the full layer model.
"""
