-- Soft delete for leads and clients (owner decision 2026-10-21: deleting must never erase history).
--
-- Leads: DELETE /api/crm/leads/{id} now stamps deleted_at/deleted_by; the row, its
-- lead_activities and its automation_executions stay in the database for audit.
-- Clients: DELETE /api/clients/{id} stamps deleted_at/deleted_by (refused while the client has
-- a live contract or an open charge); tasks/content/reports keep their hard references.
--
-- FK decisions (history is never cascade-deleted):
--   lead_activities.lead_id          CASCADE -> RESTRICT   (history/audit; a stray hard DELETE must fail loudly)
--   automation_executions.lead_id    CASCADE -> RESTRICT   (execution history; same reason)
--   lead_scoring_results.lead_id     stays CASCADE         (derived, recomputable from custom_fields + rules)
--   automation_pending_actions       stays CASCADE via execution (executions are never deleted now)
-- Idempotent: safe to re-run.

SET search_path = orbity, public;

-- ---------------------------------------------------------------------------
-- leads
-- ---------------------------------------------------------------------------
ALTER TABLE orbity.leads ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE orbity.leads ADD COLUMN IF NOT EXISTS deleted_by UUID;

CREATE INDEX IF NOT EXISTS leads_org_live_idx ON orbity.leads (org_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS leads_org_phone_live_idx ON orbity.leads (org_id, phone) WHERE deleted_at IS NULL;

-- No authenticated hard delete any more: removal is an UPDATE (leads_update_own_org already covers it).
-- The SELECT policy is deliberately NOT narrowed to deleted_at IS NULL: an UPDATE ... RETURNING must
-- see its own new row, so the soft delete itself would fail. Every read path filters in the service.
DROP POLICY IF EXISTS "leads_delete_own_org" ON orbity.leads;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'lead_activities_lead_id_fkey'
             AND conrelid = 'orbity.lead_activities'::regclass) THEN
    ALTER TABLE orbity.lead_activities DROP CONSTRAINT lead_activities_lead_id_fkey;
  END IF;
  ALTER TABLE orbity.lead_activities
    ADD CONSTRAINT lead_activities_lead_id_fkey
    FOREIGN KEY (lead_id) REFERENCES orbity.leads(id) ON DELETE RESTRICT;

  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'automation_executions_lead_id_fkey'
             AND conrelid = 'orbity.automation_executions'::regclass) THEN
    ALTER TABLE orbity.automation_executions DROP CONSTRAINT automation_executions_lead_id_fkey;
  END IF;
  ALTER TABLE orbity.automation_executions
    ADD CONSTRAINT automation_executions_lead_id_fkey
    FOREIGN KEY (lead_id) REFERENCES orbity.leads(id) ON DELETE RESTRICT;
END
$$;

-- ---------------------------------------------------------------------------
-- clients
-- ---------------------------------------------------------------------------
ALTER TABLE orbity.clients ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE orbity.clients ADD COLUMN IF NOT EXISTS deleted_by UUID;

CREATE INDEX IF NOT EXISTS clients_org_live_idx ON orbity.clients (org_id) WHERE deleted_at IS NULL;

DROP POLICY IF EXISTS "clients_delete_own_org" ON orbity.clients;
