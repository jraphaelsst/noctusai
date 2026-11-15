-- ============================================================================
-- Migration 349 -- social_wiring: imovel_historico (append-only) + the Vista-edit switch (owner 2026-11-04; re-cut v3 2026-11-15)
-- ============================================================================
-- WHY
-- ---
-- Owner, 2026-11-04: "no one receives the alert, we update our database to the Vista data and history gets an action
-- register [...] every change to them is supposed to be stored in its history [...] in-app notification only. no whatsapp,
-- no email." and "if julia is certain on a owner-confirmation, we edit vista [...] i need a switch to vista editing on and
-- off default off". 2026-11-15 (owner, option 1): the switchable WhatsApp digest of migration 317 is KEPT, so
-- `vista_divergencias_config.destino_user_id` stays (this migration does NOT drop it):
--   * `vista_divergencias_config.vista_escrita_ativa` is the owner's switch to EDIT Vista (default OFF).
--   * `imovel_historico` is the action register of an imóvel: every change the Vista sync applied, every "Vista wins",
--     every value we sent to Vista (or failed to), every approval opened and decided. Append-only.
--
-- `conflito_id` points at the `imovel_campo_conflitos` row of an approval (aprovacao_pendente / aprovacao_decidida), so the
-- timeline can say whether it is still pending and the screen can resolve it.
--
-- `imovel_preco_historico` (262) keeps recording the asking-price series by trigger; `imovel_notas` (315) are the notes.
-- The imóvel "Histórico" card merges the three through the seed card_hub timeline engine.
--
-- FORWARD-ONLY, IDEMPOTENT. The only SECURITY DEFINER function is the seed-rendered append-only guard (trigger body).
--
-- APPEND-ONLY, two layers: the grants below (UPDATE/DELETE revoked even from service_role) AND a seed GUC carve-out
-- guard trigger, so even the table owner cannot rewrite history. No FK to imoveis/orgs => no ON DELETE CASCADE can ever
-- erase it silently. LGPD erasure is the ONE allowed mutation: DELETE inside a transaction that set
-- `social_wiring.imovel_historico_expurgo` = 'on' (transaction-local). No function sets it yet; the erasure path
-- (NOC-REMEDIATE[imovel-historico-expurgo-lgpd]) must be a SECURITY DEFINER function using guc_carveout_set_config_sql.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.vista_divergencias_config
    ADD COLUMN IF NOT EXISTS vista_escrita_ativa boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN social_wiring.vista_divergencias_config.vista_escrita_ativa IS
    'Owner switch (migration 349, default OFF): when ON, an owner-confirmed price/availability that Julia is certain of is '
    'PUT to Vista (/imoveis/detalhes). OFF = Vista wins and an approval opens.';

-- transition-log-ok: imovel_historico cross-system action register (Vista sync, sends to Vista, approvals) with no single state column to compare-and-set
-- WHY THE SEED transition_log (E1) DOES NOT FIT: E1 is a state row + a transition appended in the SAME row-locked transaction. This register
-- records ACTIONS across four stores that have no common state column and are not written through one RPC: the Vista-owned mirror columns
-- (written by the sync upsert), our overlay (captacao / imovel_dados / owner confirmation), Vista itself (the PUT) and the approval row in
-- imovel_campo_conflitos (which carries its own status + decision trail). There is nothing for `<agg>_transition` to lock or compare.
-- It still has the E1 guarantees that matter: intent-named events, append-only through the seed GUC carve-out guard below, no FK/CASCADE,
-- and a gated LGPD erasure path (NOC-REMEDIATE[imovel-historico-expurgo-lgpd]). Re-evaluate when the mirror gets a lifecycle state.
CREATE TABLE IF NOT EXISTS social_wiring.imovel_historico (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           uuid        NOT NULL,
    codigo_canonical text        NOT NULL,
    ocorrido_em      timestamptz NOT NULL DEFAULT now(),
    origem           text        NOT NULL CHECK (origem IN ('vista_sync', 'usuario', 'julia', 'sistema')),
    acao             text        NOT NULL CHECK (acao IN (
                         'campo_atualizado', 'vista_prevaleceu', 'enviado_ao_vista', 'envio_vista_falhou',
                         'aprovacao_pendente', 'aprovacao_decidida')),
    campo            text,
    valor_anterior   jsonb,
    valor_novo       jsonb,
    ator_user_id     uuid,
    conversa         jsonb,
    detalhe          text,
    conflito_id      uuid,
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sw_imovel_historico_org_codigo_ocorrido
    ON social_wiring.imovel_historico (org_id, codigo_canonical, ocorrido_em DESC);

-- Append-only action register of an imóvel (Vista sync changes, Vista-wins, sends to Vista, approvals); `conversa` = {id, url} of the
-- conversation that triggered it. Written by the backend only; UPDATE/DELETE revoked.
COMMENT ON TABLE social_wiring.imovel_historico IS 'tier:org';

ALTER TABLE social_wiring.imovel_historico ENABLE ROW LEVEL SECURITY;

-- No browser-role policy/grant (access tier: the app reads it through GET /api/imoveis/{codigo}/historico, a backend-mediated read;
-- a direct PostgREST grant would be a browser-grant finding for no benefit).
DROP POLICY IF EXISTS "imovel_historico_service_role" ON social_wiring.imovel_historico;
CREATE POLICY "imovel_historico_service_role"
    ON social_wiring.imovel_historico
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Append-only: browser roles get nothing; the service role may only INSERT/SELECT.
REVOKE ALL ON social_wiring.imovel_historico FROM PUBLIC, anon, authenticated;
REVOKE UPDATE, DELETE, TRUNCATE ON social_wiring.imovel_historico FROM service_role;
GRANT SELECT, INSERT ON social_wiring.imovel_historico TO service_role;

-- guc-carveout-guard: rendered by noctusai_lib.domain.sql_templates.guc_carveout_guard_sql
CREATE OR REPLACE FUNCTION social_wiring.guard_imovel_historico_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = social_wiring, public
AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('social_wiring.imovel_historico_expurgo', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'imovel_historico is append-only' USING ERRCODE = 'P0001';
END;
$$;

REVOKE ALL ON FUNCTION social_wiring.guard_imovel_historico_append_only() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.guard_imovel_historico_append_only() TO service_role;

DROP TRIGGER IF EXISTS guard_imovel_historico_append_only ON social_wiring.imovel_historico;
CREATE TRIGGER guard_imovel_historico_append_only
    BEFORE UPDATE OR DELETE ON social_wiring.imovel_historico
    FOR EACH ROW EXECUTE FUNCTION social_wiring.guard_imovel_historico_append_only();
