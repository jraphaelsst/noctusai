-- ============================================================================
-- Migration 313 -- social_wiring: Julia v3 reports -- destination, report ledger, offered listings (CONTRACT julia-v2 §12.5/§12.6)
-- ============================================================================
-- WHY
-- ---
-- Owner brief 2026-11-03: at every hand-off / conclusion Julia produces a REPORT (conversation summary + lead profile +
-- offered / recommended properties) that goes by WhatsApp to a swappable number and is saved on the lead card; an
-- unhappy lead / own mistake / drift raises an ALERT to the same destination. Julia sends the lead up to 3 properties per
-- run and never repeats one, so SW also mirrors which codes were offered (the lead card shows them as chips).
--
-- WHAT
--   1. julia_relatorio_destino : ONE row per org -- WHO receives the reports/alerts. modo `usuario` -> usuario_id (a member of the org);
--      modo `responsavel` -> the lead responsavel, usuario_id as the fallback. The WhatsApp number is NOT stored here: it is the
--      own phone in noc (core noctus_users.telefone), resolved at send time. No phone -> the report is saved, the send is
--      skipped and the user is told in-app (status `sem_destino`), never silent.
--   2. julia_relatorios        : the report/alert ledger per contato (handoff | conclusao | alerta): the text that was sent, the
--      structured data, the destination number, the delivery status. `chave` is the idempotency key of the producing
--      action (a replayed turn writes the row once).
--   3. leads.imoveis_oferecidos / julia_contatos.imoveis_oferecidos : the codes Julia offered, ordered (agents sends the
--      full list every turn; SW overwrites).
-- Both new tables are backend-only like every julia_* table (migration 289): service_role only.
--
-- FORWARD-ONLY, IDEMPOTENT. NO SECURITY DEFINER function. Apply with noctus.dev.migrate_product.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.julia_contatos') IS NULL OR to_regclass('social_wiring.leads') IS NULL
     OR to_regclass('social_wiring.cliente_documentos') IS NULL THEN
    RAISE EXCEPTION 'this migration requires social_wiring.julia_contatos + leads + cliente_documentos -- apply the earlier migrations first';
  END IF;
END
$guard$;

-- 1. destination ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.julia_relatorio_destino (
    org_id       uuid        PRIMARY KEY,
    modo         text        NOT NULL DEFAULT 'usuario' CHECK (modo IN ('usuario', 'responsavel')),
    -- a USER of the org (public.noctus_users.id), never a typed number: the phone is read from the profile of that user in noc at send time
    usuario_id   uuid,
    updated_by   uuid,
    updated_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT julia_relatorio_destino_usuario CHECK (modo <> 'usuario' OR usuario_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS social_wiring.julia_relatorio_destino_auditoria (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     uuid        NOT NULL,
    user_id    uuid,
    evento     text        NOT NULL CHECK (evento IN ('alterado')),
    antes      jsonb       NOT NULL DEFAULT '{}'::jsonb,
    depois     jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS julia_relatorio_destino_auditoria_org_idx
    ON social_wiring.julia_relatorio_destino_auditoria (org_id, created_at DESC);

COMMENT ON TABLE social_wiring.julia_relatorio_destino IS
    'Who receives Julia''s reports and alerts (migration 313, one row per org): a USER (usuario_id) or the lead''s responsavel. The phone is '
    'the user''s own in noc (core noctus_users.telefone), read at send time, never typed here. Backend-only.';

-- 2. report / alert ledger ------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.julia_relatorios (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid        NOT NULL,
    contato_id    uuid        NOT NULL REFERENCES social_wiring.julia_contatos (id) ON DELETE CASCADE,
    lead_id       uuid,
    thread_id     text,
    tipo          text        NOT NULL CHECK (tipo IN ('handoff', 'conclusao', 'alerta')),
    texto         text        NOT NULL CHECK (char_length(texto) BETWEEN 1 AND 4000),
    dados         jsonb       NOT NULL DEFAULT '{}'::jsonb,
    destino_e164  text,
    envio_status  text        NOT NULL DEFAULT 'pendente' CHECK (envio_status IN ('pendente', 'enviado', 'falhou', 'sem_destino', 'limitado')),
    envio_erro    text        CHECK (envio_erro IS NULL OR char_length(envio_erro) <= 300),
    chave         text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS julia_relatorios_org_chave_uk
    ON social_wiring.julia_relatorios (org_id, chave) WHERE chave IS NOT NULL;
CREATE INDEX IF NOT EXISTS julia_relatorios_contato_idx
    ON social_wiring.julia_relatorios (org_id, contato_id, created_at DESC);

COMMENT ON TABLE social_wiring.julia_relatorios IS
    'Julia reports + alerts per contato (migration 313): the text sent to the destination, the structured data, the delivery status. '
    'chave = idempotency key of the producing action. Holds lead PII (profile, summary) -> backend-only, erased with the contato.';

-- RLS: service role only (the julia_* lockdown, migration 289)
ALTER TABLE social_wiring.julia_relatorio_destino ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS julia_relatorio_destino_service_role ON social_wiring.julia_relatorio_destino;
CREATE POLICY julia_relatorio_destino_service_role ON social_wiring.julia_relatorio_destino FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON social_wiring.julia_relatorio_destino FROM PUBLIC, anon, authenticated;

ALTER TABLE social_wiring.julia_relatorio_destino_auditoria ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS julia_relatorio_destino_auditoria_service_role ON social_wiring.julia_relatorio_destino_auditoria;
CREATE POLICY julia_relatorio_destino_auditoria_service_role ON social_wiring.julia_relatorio_destino_auditoria FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON social_wiring.julia_relatorio_destino_auditoria FROM PUBLIC, anon, authenticated;

ALTER TABLE social_wiring.julia_relatorios ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS julia_relatorios_service_role ON social_wiring.julia_relatorios;
CREATE POLICY julia_relatorios_service_role ON social_wiring.julia_relatorios FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON social_wiring.julia_relatorios FROM PUBLIC, anon, authenticated;

-- 3. offered listings -----------------------------------------------------------
ALTER TABLE social_wiring.leads
    ADD COLUMN IF NOT EXISTS imoveis_oferecidos text[] NOT NULL DEFAULT '{}';
ALTER TABLE social_wiring.julia_contatos
    ADD COLUMN IF NOT EXISTS imoveis_oferecidos text[] NOT NULL DEFAULT '{}';

COMMENT ON COLUMN social_wiring.leads.imoveis_oferecidos IS
    'Listing codes Julia offered this lead, in order (migration 313; mirrored from agents'' qualificacao every turn).';
COMMENT ON COLUMN social_wiring.julia_contatos.imoveis_oferecidos IS
    'Listing codes Julia offered this contato, in order (migration 313; overwritten from agents'' qualificacao every turn).';

-- 4. WhatsApp-origin identity documents are NOT verified until a human confirms the extraction ------------------
-- A document the lead sends over WhatsApp is read by a model; its values are suggestions, never facts. `verificado` is false for
-- origem_entrada='whatsapp' (set by the intake) and true for everything else (default); the "confirmar extração" action sets it.
ALTER TABLE social_wiring.cliente_documentos
    ADD COLUMN IF NOT EXISTS verificado boolean NOT NULL DEFAULT true;

COMMENT ON COLUMN social_wiring.cliente_documentos.verificado IS
    'false = read by a model from a WhatsApp-origin file and not yet confirmed by a person (migration 313). Contracts must not use it unverified.';
