-- Migration: 118_notification_owner_recipients
-- Schema: public (core)
-- Project: noc-whatsapp-lines (Phase 2, owner line).
--
-- WHAT: who receives the owner-facing WhatsApp notices that the NoctusAI line (L3) sends.
--   * public.notification_owner_recipients — the numbers (E.164) the seed `notify_owner` sends to; `ativo` is the
--     per-recipient switch. Managed from the core admin "Notificações" page. Service role only.
--   * public.notification_owner_recipient_events — append-only history (adicionado / ativado / desativado /
--     removido): who and when (`created_at`). Written by a trigger, so the event lands in the SAME transaction as the change
--     (event-oriented). Carries the recipient id only — never the phone number (a removed number is gone for good).
-- The writer sets `alterado_por` (the admin's user id) on every write; for a removal it first updates that column,
-- then deletes, so the trigger can name the actor on the `removido` event.
-- Additive only; previous images never read these tables.
-- Re-runnable: IF NOT EXISTS / CREATE OR REPLACE / DROP-then-CREATE.
SET search_path = public, public;
SET lock_timeout = '5s';

CREATE TABLE IF NOT EXISTS public.notification_owner_recipients (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    numero       TEXT NOT NULL CHECK (numero ~ '^\+[1-9][0-9]{7,14}$'),
    nome         TEXT CHECK (nome IS NULL OR length(nome) BETWEEN 1 AND 120),
    ativo        BOOLEAN NOT NULL DEFAULT true,
    alterado_por UUID,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT notification_owner_recipients_numero_key UNIQUE (numero)
);
-- Phone numbers that receive the owner-facing WhatsApp notices (owner line). Platform admins only, via service role.
COMMENT ON TABLE public.notification_owner_recipients IS 'tier:platform';

CREATE TABLE IF NOT EXISTS public.notification_owner_recipient_events (
    id            BIGSERIAL PRIMARY KEY,
    recipient_id  UUID NOT NULL,
    evento        TEXT NOT NULL CHECK (evento IN ('adicionado', 'ativado', 'desativado', 'removido')),
    ator          UUID,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Append-only history of changes to the owner-notice recipients (ids only, no phone numbers). Platform admins only.
COMMENT ON TABLE public.notification_owner_recipient_events IS 'tier:platform';
CREATE INDEX IF NOT EXISTS ix_notification_owner_recipient_events_recipient
    ON public.notification_owner_recipient_events (recipient_id, created_at DESC);

CREATE OR REPLACE FUNCTION public.notification_owner_recipients_touch()
RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = public
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;
DROP TRIGGER IF EXISTS set_updated_at_notification_owner_recipients ON public.notification_owner_recipients;
CREATE TRIGGER set_updated_at_notification_owner_recipients
    BEFORE UPDATE ON public.notification_owner_recipients
    FOR EACH ROW EXECUTE FUNCTION public.notification_owner_recipients_touch();

CREATE OR REPLACE FUNCTION public.notification_owner_recipients_record_event()
RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = public
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO public.notification_owner_recipient_events (recipient_id, evento, ator)
        VALUES (NEW.id, 'adicionado', NEW.alterado_por);
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        IF NEW.ativo IS DISTINCT FROM OLD.ativo THEN
            INSERT INTO public.notification_owner_recipient_events (recipient_id, evento, ator)
            VALUES (NEW.id, CASE WHEN NEW.ativo THEN 'ativado' ELSE 'desativado' END, NEW.alterado_por);
        END IF;
        RETURN NEW;
    END IF;
    INSERT INTO public.notification_owner_recipient_events (recipient_id, evento, ator)
    VALUES (OLD.id, 'removido', OLD.alterado_por);
    RETURN OLD;
END; $$;
DROP TRIGGER IF EXISTS notification_owner_recipients_event ON public.notification_owner_recipients;
CREATE TRIGGER notification_owner_recipients_event
    AFTER INSERT OR UPDATE OR DELETE ON public.notification_owner_recipients
    FOR EACH ROW EXECUTE FUNCTION public.notification_owner_recipients_record_event();

CREATE OR REPLACE FUNCTION public.notification_owner_recipient_events_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = public
AS $$ BEGIN RAISE EXCEPTION 'notification_owner_recipient_events is append-only'; END; $$;
DROP TRIGGER IF EXISTS notification_owner_recipient_events_no_update_delete ON public.notification_owner_recipient_events;
CREATE TRIGGER notification_owner_recipient_events_no_update_delete
    BEFORE UPDATE OR DELETE ON public.notification_owner_recipient_events
    FOR EACH ROW EXECUTE FUNCTION public.notification_owner_recipient_events_append_only();

ALTER TABLE public.notification_owner_recipients ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notification_owner_recipient_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.notification_owner_recipients FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.notification_owner_recipient_events FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.notification_owner_recipients TO service_role;
GRANT ALL ON public.notification_owner_recipient_events TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.notification_owner_recipient_events_id_seq TO service_role;

DROP POLICY IF EXISTS "service_role_bypass" ON public.notification_owner_recipients;
CREATE POLICY "service_role_bypass" ON public.notification_owner_recipients
    FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "service_role_bypass" ON public.notification_owner_recipient_events;
CREATE POLICY "service_role_bypass" ON public.notification_owner_recipient_events
    FOR ALL TO service_role USING (true) WITH CHECK (true);
