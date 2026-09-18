-- ============================================================================
-- Migration 138 -- social_wiring: admin-adjudicated conflicts for a
-- CAMPOS-driven extracted value
--
-- WHAT THIS IS
-- ------------
-- Owner directive, 2026-09-18, superseding part of 097/110's original
-- `sobrescreve=False` design: when an extracted value (any `CAMPOS` /
-- `CAMPOS_QUALIFICACAO` field — cpf/rg/estado_civil/genero/nacionalidade/
-- profissao/...) DISAGREES with a value already on `clientes`, this is no
-- longer a silent skip. An admin is notified and decides: ACCEPT overwrites
-- with the extracted (official-document) value; REJECT leaves the existing
-- value in place. Quoted verbatim from the directive:
--
--   "let admins decide on suggestions AI gives us. Upon acceptance, fields
--   should be overwritten with data extracted from official doc files. On
--   rejection, prevails the human input. if the inputed data was made by
--   human and corrected by ai and accepted by a human admin, then ai input
--   prevails"
--
-- 🔴 WHAT DID NOT CHANGE: THE REASON `sobrescreve=False` EXISTED
-- --------------------------------------------------------------------------
-- 110's header: overwriting a human's entry "would destroy it with no way
-- back." That reason has not gone away -- the owner's directive explicitly
-- requires it stay satisfiable ("on rejection, prevails the human input" is
-- only honourable if that input still exists to prevail; an admin can
-- accept wrongly and needs a way back). So `valor_anterior` /
-- `origem_anterior` below are a PERMANENT snapshot, taken at the moment the
-- conflict is detected, never overwritten, never deleted by an accept. The
-- accept still changes what is ON `clientes` -- it does not delete the
-- record of what was there before.
--
-- WHAT THIS FILE DOES NOT BUILD
-- ------------------------------
-- A one-click "undo an accepted conflict" endpoint. The data this needs
-- (`valor_anterior`, who decided, when) is captured here and is therefore
-- POSSIBLE to build on; wiring an undo action is a separate, bounded
-- follow-up, not invented in this pass.
-- NOC-REMEDIATE[cliente-conflito-undo]: an explicit "restore valor_anterior"
-- action reading this table — 2026-09-18.
--
-- 🔴 NOTIFICATION REUSES `notification_recipients` / `NotificationService`,
-- NOT A NEW CHANNEL
-- --------------------------------------------------------------------------
-- Per the owner's own instruction. `NotificationService.notify_field_conflict`
-- (code, not this migration) composes a message and fans it out through the
-- SAME `_dispatch` core `notify_upload` / `notify_new_lead` already use, to
-- the org-wide recipient tier -- a field conflict on a `clientes` row has no
-- natural `social_wiring.clients` (the org's OWN sub-tenant, a DIFFERENT
-- table from `clientes`) to scope to the way a lead does, so it always uses
-- the fallback tier. `notificado_em` records whether that dispatch actually
-- ran; NULL is an honest "detected, not yet (or not successfully) announced"
-- state, mirroring every other best-effort log in this schema.
--
-- ONE OPEN CONFLICT PER (cliente, campo) AT A TIME
-- --------------------------------------------------------------------------
-- The partial unique index below stops a re-extraction from piling up a
-- second, third, ... pending conflict row (and notification) for the same
-- field while an earlier one is still awaiting a decision. A resolved
-- (aceito/rejeitado) row does not block a NEW conflict from opening later --
-- only 'pendente' rows are covered by the index.
--
-- `fonte_tabela` / `fonte_id` (NOT a hard FK) -- SAME reasoning
-- `imovel_documentos` gave for not FK'ing a polymorphic pointer: a conflict
-- can be raised by `cliente_documentos` (rg/cpf/estado_civil/... readings)
-- OR by `matricula_qualificacoes` (migration 137) -- two different tables,
-- so a single-target FK cannot express it. `fonte_tabela` names which.
--
-- FORWARD-ONLY, IDEMPOTENT (safe to re-run; every step is existence-guarded).
-- 🔴 MIGRATION FILE ONLY -- applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.cliente_campo_conflitos (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            UUID NOT NULL,
    cliente_id        UUID NOT NULL
        REFERENCES social_wiring.clientes(id) ON DELETE CASCADE,

    -- The `CampoExtraido.item_key` in conflict -- 'estado_civil', 'rg', ...
    campo             TEXT NOT NULL,

    -- The permanent snapshot -- see the header. Taken once, at detection,
    -- from whatever was on `clientes` at that moment (an operator's typed
    -- value, an earlier accepted extraction, or an earlier document's
    -- unattended write -- the directive is explicit that ALL of these
    -- "prevail" identically until an admin says otherwise).
    valor_anterior    TEXT,
    origem_anterior   TEXT,

    -- What the new extraction proposes.
    valor_proposto    TEXT NOT NULL,
    origem_proposto   TEXT NOT NULL,
    confianca_proposta TEXT,

    -- Polymorphic pointer to the suggestion row that raised this conflict --
    -- see the header. Both nullable: the unattended `identidade_extracao
    -- _service.extrair_identidade` path names `cliente_documentos`/
    -- `documento_id`; `qualificacao_service.confirmar` names
    -- `matricula_qualificacoes`/`qualificacao_id`.
    fonte_tabela      TEXT,
    fonte_id          UUID,

    status            TEXT NOT NULL DEFAULT 'pendente'
        CHECK (status IN ('pendente', 'aceito', 'rejeitado')),
    notificado_em     TIMESTAMPTZ,
    decidido_por      UUID,
    decidido_em       TIMESTAMPTZ,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.cliente_campo_conflitos IS
    'One row per CAMPOS field where an extracted value disagreed with what '
    'was already on clientes (migration 138). Never auto-resolved: an admin '
    'accepts (extraction overwrites, valor_anterior stays as the way back) '
    'or rejects (clientes untouched). See this migration''s header.';
COMMENT ON COLUMN social_wiring.cliente_campo_conflitos.valor_anterior IS
    'PERMANENT snapshot of clientes.<campo> at detection time -- the '
    'reversibility 110''s sobrescreve=False used to provide by simply never '
    'overwriting. Never updated after insert, never cleared by an accept.';
COMMENT ON COLUMN social_wiring.cliente_campo_conflitos.origem_proposto IS
    'Where the PROPOSED value came from -- a tipo_documento (''rg'', ''cpf'', '
    '...) or ''matricula'' (migration 137). Written onto clientes.<campo>'
    '_origem verbatim if accepted.';

CREATE INDEX IF NOT EXISTS idx_sw_cliente_campo_conflitos_cliente
    ON social_wiring.cliente_campo_conflitos (org_id, cliente_id);

-- The admin's queue.
CREATE INDEX IF NOT EXISTS idx_sw_cliente_campo_conflitos_pendentes
    ON social_wiring.cliente_campo_conflitos (org_id, created_at DESC)
    WHERE status = 'pendente';

-- One open conflict per (cliente, campo) -- see the header.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_cliente_campo_conflitos_aberto
    ON social_wiring.cliente_campo_conflitos (cliente_id, campo)
    WHERE status = 'pendente';

ALTER TABLE social_wiring.cliente_campo_conflitos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cliente_campo_conflitos_select_own_org"
    ON social_wiring.cliente_campo_conflitos;
CREATE POLICY "cliente_campo_conflitos_select_own_org"
    ON social_wiring.cliente_campo_conflitos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "cliente_campo_conflitos_service_role"
    ON social_wiring.cliente_campo_conflitos;
CREATE POLICY "cliente_campo_conflitos_service_role"
    ON social_wiring.cliente_campo_conflitos
    FOR ALL TO service_role USING (true) WITH CHECK (true);
