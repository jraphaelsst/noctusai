-- 004_ensure_notifications.sql
--
-- Ensures the public.notifications table exists with proper RLS policies.
-- This table is a PLATFORM-LEVEL resource used by all NoctusAI products.
-- Each product's backend proxies to it via get_core_client() targeting the
-- public schema.
--
-- Safe to run on any database — uses IF NOT EXISTS / IF NOT EXISTS guards.

-- ── Table ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    org_id UUID,
    type TEXT NOT NULL DEFAULT 'system',
    title TEXT NOT NULL,
    message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}',
    read BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Indexes ──────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_notifications_user
    ON notifications(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_notifications_unread
    ON notifications(user_id) WHERE read = false;

-- ── RLS ──────────────────────────────────────────────────────────────

ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

-- Users can read/update their own notifications
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'notifications' AND policyname = 'notifications_own'
    ) THEN
        CREATE POLICY "notifications_own" ON notifications
            FOR ALL USING (user_id = auth.uid());
    END IF;
END $$;

-- Service role has full access (for backend creating notifications)
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'notifications' AND policyname = 'notifications_service'
    ) THEN
        CREATE POLICY "notifications_service" ON notifications
            FOR ALL TO service_role
            USING (true)
            WITH CHECK (true);
    END IF;
END $$;

-- ── Grants ───────────────────────────────────────────────────────────

GRANT SELECT, INSERT, UPDATE, DELETE ON notifications TO authenticated;
GRANT ALL ON notifications TO service_role;
