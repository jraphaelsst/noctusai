-- Migration 013: rejection audit columns
--
-- Project:   products/therapy-platform/projects/therapy-platform-wiring/
-- Phase:     5 — Reject flow wiring
-- Surfaced:  2026-04-20 (admin-therapists fix); §5.4.5 column gap; §5.2 spec.
--
-- Background:
--   admin_service.reject_entity() writes {is_approved=False, rejection_reason=...}
--   to therapy.therapist_profiles / therapy.clinics. The column never existed
--   in any prior migration — clicking "Rejeitar" in the admin UI 500s with
--   undefined_column. The empty-Rejected-tab early return at admin_service.py
--   masked the throw on the clinic-side and on the rejeitado list filter.
--
--   §3 "Reject flow primer" + Open Question Q1/Q5 decisions: audit trail lives
--   on the live row while rejected; re-approval clears the three columns.
--
-- This migration:
--   1. Adds `rejection_reason TEXT`, `rejected_at TIMESTAMPTZ`,
--      `rejected_by UUID REFERENCES auth.users(id)` to therapy.therapist_profiles
--      and therapy.clinics.
--   2. Idempotent — uses ADD COLUMN IF NOT EXISTS so re-applying is a no-op.
--   3. No RLS changes — the existing platform_admin select policies cover
--      these columns, and service_role_bypass covers writes from reject_entity.
--
-- Per `feedback_mcp_migrations_mirror_file`: this file is committed BEFORE
-- being applied via mcp__claude_ai_Supabase__apply_migration.

ALTER TABLE therapy.therapist_profiles
  ADD COLUMN IF NOT EXISTS rejection_reason TEXT,
  ADD COLUMN IF NOT EXISTS rejected_at      TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS rejected_by      UUID REFERENCES auth.users(id);

ALTER TABLE therapy.clinics
  ADD COLUMN IF NOT EXISTS rejection_reason TEXT,
  ADD COLUMN IF NOT EXISTS rejected_at      TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS rejected_by      UUID REFERENCES auth.users(id);

COMMENT ON COLUMN therapy.therapist_profiles.rejection_reason IS
  'Free-text reason captured at reject time. LGPD: 90-day retention after rejection (Q5, 2026-05-03), then null-out via scheduled job.';
COMMENT ON COLUMN therapy.clinics.rejection_reason IS
  'Free-text reason captured at reject time. LGPD: 90-day retention after rejection (Q5, 2026-05-03), then null-out via scheduled job.';
