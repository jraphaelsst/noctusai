-- ============================================================================
-- 047_audit_acao_check_restore.sql -- the audit CHECK accepts every action the code writes again.
--
--   031 extended `agent_audit_log_acao_check` with the Julia v2 contract §5.1 list. 034 dropped and re-added it
--   to admit 'modo_alterado' but re-listed the actions from an older copy, silently losing 'specs_org_editadas'
--   and 'definicao_lida'. Every Studio draft read audits 'definicao_lida', so GET .../draft failed with a CHECK
--   violation (HTTP 500) in prod -- and so did the per-org specs write.
--
--   The list below is the union and matches `app.stores.studio_definitions.AUDIT_ACOES` exactly;
--   tests/test_migration_audit_acao_check.py pins the LATEST definition across all migrations to that tuple,
--   so a later redefinition cannot drop an action again.
--
-- Forward-only + idempotent (drops whatever acao CHECK exists, re-adds the full one). No data change: rows
-- written under 031/034 are all members of the union.
-- ============================================================================

SET search_path = agents, public;

DO $$
DECLARE
    v_con TEXT;
BEGIN
    FOR v_con IN
        SELECT conname FROM pg_constraint
         WHERE conrelid = 'agents.agent_audit_log'::regclass
           AND contype = 'c'
           AND pg_get_constraintdef(oid) ILIKE '%acao%'
    LOOP
        EXECUTE format('ALTER TABLE agents.agent_audit_log DROP CONSTRAINT %I', v_con);
    END LOOP;
END
$$;

ALTER TABLE agents.agent_audit_log
    ADD CONSTRAINT agent_audit_log_acao_check
        CHECK (acao IN (
            'limiar_alterado', 'publicado', 'publicado_override', 'rascunho_descartado',
            'conteudo_editado_mcp', 'specs_org_editadas', 'definicao_lida',
            'modo_alterado', 'conversa_pausada', 'conversa_retomada', 'padrao_publicado'
        ));
