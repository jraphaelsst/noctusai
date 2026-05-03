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

**Future occupants:**
- `gamification/` (when ERP Metas patterns extract)

See `KB § PATTERNS/seed-lib-layout.md` for the full layer model.
"""
