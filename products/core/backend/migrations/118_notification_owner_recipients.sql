-- Migration: 118_notification_owner_recipients
-- Schema: public (core)
-- Project: noc-whatsapp-lines (Phase 2, owner line).
--
-- WHAT: who receives the owner-facing WhatsApp notices that the NoctusAI line (L3) sends.
--   * public.notification_owner_recipients — the numbers (E.164) the seed `notify_owner` sends to; `ativo` is the
--     per-recipient switch. Managed from the core admin "Notificações" page. Service role only.
--     The number is IMMUTABLE (remove and re-add instead), so "who receives" can only change through an event.
--   * public.notification_owner_recipient_events — append-only history (adicionado / ativado / desativado /
--     renomeado / removido): who (`ator`, NOT NULL) and when. Written ONLY by a SECURITY DEFINER trigger function
--     in the same transaction as the change; service_role can read it, never write it, never TRUNCATE it. A change
--     with no known actor is refused (the event insert fails NOT NULL), so no change goes unrecorded.
--   * The actor reaches the trigger through `alterado_por` (INSERT/UPDATE; every UPDATE must restamp
--     `alterado_em`, so an unchanged row never blames the previous admin) or, for DELETE only, the
--     transaction-local setting `noc.ator` set by `remover_destinatario_dono` (a plain DELETE is refused).
--   * A service-role writer can still name ANY actor (and the key holder can drive the RPC): an accepted residual
--     — the holder of the core service-role key is trusted at the DB layer; what the guards close is silent change
--     (number swap, wipe, forged or missing event), not a key holder lying about who acted.
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
    alterado_em  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT notification_owner_recipients_numero_key UNIQUE (numero)
);
-- Phone numbers that receive the owner-facing WhatsApp notices (owner line). Platform admins only, via service role.
COMMENT ON TABLE public.notification_owner_recipients IS 'tier:platform';

CREATE TABLE IF NOT EXISTS public.notification_owner_recipient_events (
    id            BIGSERIAL PRIMARY KEY,
    recipient_id  UUID NOT NULL,
    evento        TEXT NOT NULL CHECK (evento IN ('adicionado', 'ativado', 'desativado', 'renomeado', 'removido')),
    ator          UUID NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Append-only history of changes to the owner-notice recipients (ids only, no phone numbers). Platform admins only.
COMMENT ON TABLE public.notification_owner_recipient_events IS 'tier:platform';
CREATE INDEX IF NOT EXISTS ix_notification_owner_recipient_events_recipient
    ON public.notification_owner_recipient_events (recipient_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- Row guards on the recipients
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.notification_owner_recipients_touch()
RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = public
AS $$
BEGIN
    IF NEW.numero IS DISTINCT FROM OLD.numero THEN
        RAISE EXCEPTION 'notification_owner_recipients.numero is immutable (remove and re-add the recipient)';
    END IF;
    IF NEW.alterado_em IS NOT DISTINCT FROM OLD.alterado_em THEN
        RAISE EXCEPTION 'notification_owner_recipients: every update must restamp alterado_em and alterado_por';
    END IF;
    NEW.updated_at = now();
    RETURN NEW;
END; $$;
DROP TRIGGER IF EXISTS set_updated_at_notification_owner_recipients ON public.notification_owner_recipients;
CREATE TRIGGER set_updated_at_notification_owner_recipients
    BEFORE UPDATE ON public.notification_owner_recipients
    FOR EACH ROW EXECUTE FUNCTION public.notification_owner_recipients_touch();

-- The ONLY writer of the events table. SECURITY DEFINER so that service_role needs no INSERT grant on it.
CREATE OR REPLACE FUNCTION public.notification_owner_recipients_record_event()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
AS $$
DECLARE
    v_ator UUID;
BEGIN
    IF TG_OP = 'DELETE' THEN
        -- only the RPC deletes: it sets the actor transaction-locally; a session-level SET is never read elsewhere
        v_ator := NULLIF(pg_catalog.current_setting('noc.ator', true), '')::uuid;
        IF v_ator IS NULL THEN
            RAISE EXCEPTION 'notification_owner_recipients: delete is only allowed through remover_destinatario_dono';
        END IF;
    ELSE
        v_ator := NEW.alterado_por;
    END IF;
    IF TG_OP = 'INSERT' THEN
        INSERT INTO public.notification_owner_recipient_events (recipient_id, evento, ator)
        VALUES (NEW.id, 'adicionado', v_ator);
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        IF NEW.ativo IS DISTINCT FROM OLD.ativo THEN
            INSERT INTO public.notification_owner_recipient_events (recipient_id, evento, ator)
            VALUES (NEW.id, CASE WHEN NEW.ativo THEN 'ativado' ELSE 'desativado' END, v_ator);
        END IF;
        IF NEW.nome IS DISTINCT FROM OLD.nome THEN
            INSERT INTO public.notification_owner_recipient_events (recipient_id, evento, ator)
            VALUES (NEW.id, 'renomeado', v_ator);
        END IF;
        RETURN NEW;
    END IF;
    INSERT INTO public.notification_owner_recipient_events (recipient_id, evento, ator)
    VALUES (OLD.id, 'removido', v_ator);
    RETURN OLD;
END; $$;
REVOKE EXECUTE ON FUNCTION public.notification_owner_recipients_record_event()
    FROM PUBLIC, anon, authenticated, service_role;
DROP TRIGGER IF EXISTS notification_owner_recipients_event ON public.notification_owner_recipients;
CREATE TRIGGER notification_owner_recipients_event
    AFTER INSERT OR UPDATE OR DELETE ON public.notification_owner_recipients
    FOR EACH ROW EXECUTE FUNCTION public.notification_owner_recipients_record_event();

-- ---------------------------------------------------------------------------
-- Append-only guard on the events (row-level AND TRUNCATE — TRUNCATE skips row triggers)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.notification_owner_recipient_events_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = public
AS $$ BEGIN RAISE EXCEPTION 'notification_owner_recipient_events is append-only'; END; $$;
DROP TRIGGER IF EXISTS notification_owner_recipient_events_no_update_delete ON public.notification_owner_recipient_events;
CREATE TRIGGER notification_owner_recipient_events_no_update_delete
    BEFORE UPDATE OR DELETE ON public.notification_owner_recipient_events
    FOR EACH ROW EXECUTE FUNCTION public.notification_owner_recipient_events_append_only();
DROP TRIGGER IF EXISTS notification_owner_recipient_events_no_truncate ON public.notification_owner_recipient_events;
CREATE TRIGGER notification_owner_recipient_events_no_truncate
    BEFORE TRUNCATE ON public.notification_owner_recipient_events
    FOR EACH STATEMENT EXECUTE FUNCTION public.notification_owner_recipient_events_append_only();
-- Wiping the recipients would leave no `removido` events either.
DROP TRIGGER IF EXISTS notification_owner_recipients_no_truncate ON public.notification_owner_recipients;
CREATE TRIGGER notification_owner_recipients_no_truncate
    BEFORE TRUNCATE ON public.notification_owner_recipients
    FOR EACH STATEMENT EXECUTE FUNCTION public.notification_owner_recipient_events_append_only();

-- ---------------------------------------------------------------------------
-- Removal in ONE transaction, with the actor passed through (no stamp-then-delete race)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.remover_destinatario_dono(p_id UUID, p_ator UUID)
RETURNS UUID
LANGUAGE plpgsql SET search_path = public
AS $$
DECLARE
    v_id UUID;
BEGIN
    IF p_ator IS NULL THEN
        RAISE EXCEPTION 'remover_destinatario_dono requires the acting admin (p_ator)';
    END IF;
    PERFORM set_config('noc.ator', p_ator::text, true);
    DELETE FROM public.notification_owner_recipients WHERE id = p_id RETURNING id INTO v_id;
    RETURN v_id;
END; $$;
REVOKE EXECUTE ON FUNCTION public.remover_destinatario_dono(UUID, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.remover_destinatario_dono(UUID, UUID) TO service_role;

-- ---------------------------------------------------------------------------
-- Grants / RLS
-- ---------------------------------------------------------------------------
ALTER TABLE public.notification_owner_recipients ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notification_owner_recipient_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.notification_owner_recipients FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.notification_owner_recipient_events FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.notification_owner_recipients TO service_role;
-- The events are readable by service_role, writable by nobody but the definer trigger function.
REVOKE ALL ON public.notification_owner_recipient_events FROM service_role;
GRANT SELECT ON public.notification_owner_recipient_events TO service_role;
REVOKE ALL ON SEQUENCE public.notification_owner_recipient_events_id_seq FROM PUBLIC, anon, authenticated, service_role;

DROP POLICY IF EXISTS "service_role_bypass" ON public.notification_owner_recipients;
CREATE POLICY "service_role_bypass" ON public.notification_owner_recipients
    FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "service_role_bypass" ON public.notification_owner_recipient_events;
DROP POLICY IF EXISTS "service_role_read" ON public.notification_owner_recipient_events;
CREATE POLICY "service_role_read" ON public.notification_owner_recipient_events
    FOR SELECT TO service_role USING (true);
