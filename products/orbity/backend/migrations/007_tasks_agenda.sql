-- ============================================================================
-- Migration 007 — Orbity Tasks + Agenda organ
--
-- Tables:
--   orbity.tasks          — work items with assignee, client, status, priority
--   orbity.agenda_events  — calendar events with GCal sync seam (gcal_event_id)
--   orbity.routines       — recurring task templates (spawn-a-task seam)
--
-- Tenancy: org_id (noc canonical). RLS on every table via
--   USING (org_id = public.current_org_id())
-- NEVER USING(true), NEVER JWT/user_metadata.
--
-- IDEMPOTENT: CREATE TABLE IF NOT EXISTS + DROP POLICY IF EXISTS.
--
-- SEARCH PATH: session-pinned to orbity, public.
-- ============================================================================

SET search_path = orbity, public;

-- set_updated_at() is defined in 005_crm_core.sql. The IF NOT EXISTS guard
-- on CREATE OR REPLACE means re-declaring it here is harmless if 005 ran
-- first; idempotent regardless of run order.
CREATE OR REPLACE FUNCTION orbity.set_updated_at()
  RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;


-- ============================================================================
-- 1. tasks — work items per org, optionally linked to a client
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    assignee_user_id UUID,               -- auth.users id (recorded, not FK-enforced)
    client_id       UUID REFERENCES orbity.clients(id) ON DELETE SET NULL,
    status          TEXT NOT NULL DEFAULT 'todo'
                        CHECK (status IN ('todo', 'doing', 'done', 'canceled')),
    priority        TEXT NOT NULL DEFAULT 'med'
                        CHECK (priority IN ('low', 'med', 'high')),
    due_date        DATE,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS tasks_org_id_idx
    ON orbity.tasks (org_id);
CREATE INDEX IF NOT EXISTS tasks_org_status_idx
    ON orbity.tasks (org_id, status);
CREATE INDEX IF NOT EXISTS tasks_org_assignee_idx
    ON orbity.tasks (org_id, assignee_user_id);
CREATE INDEX IF NOT EXISTS tasks_org_due_date_idx
    ON orbity.tasks (org_id, due_date);

DROP TRIGGER IF EXISTS trg_tasks_updated_at ON orbity.tasks;
CREATE TRIGGER trg_tasks_updated_at
  BEFORE UPDATE ON orbity.tasks
  FOR EACH ROW EXECUTE FUNCTION orbity.set_updated_at();

ALTER TABLE orbity.tasks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "tasks_select_own_org" ON orbity.tasks;
CREATE POLICY "tasks_select_own_org" ON orbity.tasks
  FOR SELECT TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "tasks_insert_own_org" ON orbity.tasks;
CREATE POLICY "tasks_insert_own_org" ON orbity.tasks
  FOR INSERT TO authenticated
  WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "tasks_update_own_org" ON orbity.tasks;
CREATE POLICY "tasks_update_own_org" ON orbity.tasks
  FOR UPDATE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "tasks_delete_own_org" ON orbity.tasks;
CREATE POLICY "tasks_delete_own_org" ON orbity.tasks
  FOR DELETE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "tasks_service_role_all" ON orbity.tasks;
CREATE POLICY "tasks_service_role_all" ON orbity.tasks
  FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ============================================================================
-- 2. agenda_events — calendar events with optional GCal sync seam
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.agenda_events (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL,
    title            TEXT NOT NULL,
    description      TEXT,
    event_type       TEXT NOT NULL DEFAULT 'other'
                         CHECK (event_type IN ('meeting', 'call', 'visit', 'other')),
    client_id        UUID REFERENCES orbity.clients(id) ON DELETE SET NULL,
    starts_at        TIMESTAMPTZ NOT NULL,
    ends_at          TIMESTAMPTZ NOT NULL,
    location         TEXT,
    -- GCal sync seam: populated by agenda_service.sync_to_gcal()
    -- when a real CalendarAdapter is wired via get_calendar_adapter().
    -- NULL = not synced / GCal not configured.
    gcal_event_id    TEXT,
    assignee_user_id UUID,               -- auth.users id (recorded, not FK-enforced)
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- ends_at must be after starts_at
    CONSTRAINT agenda_events_time_order CHECK (ends_at > starts_at)
);

CREATE INDEX IF NOT EXISTS agenda_events_org_id_idx
    ON orbity.agenda_events (org_id);
CREATE INDEX IF NOT EXISTS agenda_events_org_time_idx
    ON orbity.agenda_events (org_id, starts_at, ends_at);
CREATE INDEX IF NOT EXISTS agenda_events_org_client_idx
    ON orbity.agenda_events (org_id, client_id);
CREATE INDEX IF NOT EXISTS agenda_events_gcal_id_idx
    ON orbity.agenda_events (org_id, gcal_event_id)
    WHERE gcal_event_id IS NOT NULL;

DROP TRIGGER IF EXISTS trg_agenda_events_updated_at ON orbity.agenda_events;
CREATE TRIGGER trg_agenda_events_updated_at
  BEFORE UPDATE ON orbity.agenda_events
  FOR EACH ROW EXECUTE FUNCTION orbity.set_updated_at();

ALTER TABLE orbity.agenda_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "agenda_events_select_own_org" ON orbity.agenda_events;
CREATE POLICY "agenda_events_select_own_org" ON orbity.agenda_events
  FOR SELECT TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "agenda_events_insert_own_org" ON orbity.agenda_events;
CREATE POLICY "agenda_events_insert_own_org" ON orbity.agenda_events
  FOR INSERT TO authenticated
  WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "agenda_events_update_own_org" ON orbity.agenda_events;
CREATE POLICY "agenda_events_update_own_org" ON orbity.agenda_events
  FOR UPDATE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "agenda_events_delete_own_org" ON orbity.agenda_events;
CREATE POLICY "agenda_events_delete_own_org" ON orbity.agenda_events
  FOR DELETE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "agenda_events_service_role_all" ON orbity.agenda_events;
CREATE POLICY "agenda_events_service_role_all" ON orbity.agenda_events
  FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ============================================================================
-- 3. routines — recurring task templates; spawn-a-task seam
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.routines (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    title       TEXT NOT NULL,
    description TEXT,
    cadence     TEXT NOT NULL CHECK (cadence IN ('daily', 'weekly', 'monthly')),
    next_run    DATE NOT NULL,
    active      BOOLEAN NOT NULL DEFAULT true,
    -- Spawn-a-task seam: the routines service advances next_run
    -- and inserts a tasks row via TasksService when active=true.
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS routines_org_id_idx
    ON orbity.routines (org_id);
CREATE INDEX IF NOT EXISTS routines_org_active_next_run_idx
    ON orbity.routines (org_id, active, next_run)
    WHERE active = true;

DROP TRIGGER IF EXISTS trg_routines_updated_at ON orbity.routines;
CREATE TRIGGER trg_routines_updated_at
  BEFORE UPDATE ON orbity.routines
  FOR EACH ROW EXECUTE FUNCTION orbity.set_updated_at();

ALTER TABLE orbity.routines ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "routines_select_own_org" ON orbity.routines;
CREATE POLICY "routines_select_own_org" ON orbity.routines
  FOR SELECT TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "routines_insert_own_org" ON orbity.routines;
CREATE POLICY "routines_insert_own_org" ON orbity.routines
  FOR INSERT TO authenticated
  WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "routines_update_own_org" ON orbity.routines;
CREATE POLICY "routines_update_own_org" ON orbity.routines
  FOR UPDATE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "routines_delete_own_org" ON orbity.routines;
CREATE POLICY "routines_delete_own_org" ON orbity.routines
  FOR DELETE TO authenticated
  USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "routines_service_role_all" ON orbity.routines;
CREATE POLICY "routines_service_role_all" ON orbity.routines
  FOR ALL TO service_role USING (true) WITH CHECK (true);
