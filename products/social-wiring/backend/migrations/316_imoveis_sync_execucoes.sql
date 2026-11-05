-- ============================================================================
-- Migration 316 -- social_wiring: one row per Vista imóveis refresh run (julia-v3, owner 2026-11-03)
-- ============================================================================
-- WHY
-- ---
-- `/imoveis/listar` went silent on Vista's side (2026-10-23+), so the mirror is now refreshed per code
-- (`/imoveis/detalhes`) on a 2-hour schedule, with listar tried first on every run. Every run must leave an honest,
-- queryable record: WHEN it ran, WHICH path ran (listar | detalhes), the counts (new / updated / unchanged / removed /
-- failed, and the HTTP calls spent), and how it ended. `sincronizado_em` alone cannot say any of that.
--
-- WHAT
--   imoveis_sync_execucoes: one row per run per org. `relatorio` is the SyncReport (counts, failures, call counts).
--   The in-flight row (`status='em_andamento'`) is also what the manual "Atualizar agora" button polls, and what makes
--   a second click return the running one instead of starting another. Backend-only like every internal table: RLS
--   on, service role only.
--
-- FORWARD-ONLY, IDEMPOTENT. NO SECURITY DEFINER function.
-- ============================================================================

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.imoveis_sync_execucoes (
    id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                uuid        NOT NULL,
    origem                text        NOT NULL DEFAULT 'agendado' CHECK (origem IN ('agendado', 'manual')),
    modo                  text        NOT NULL DEFAULT 'auto' CHECK (modo IN ('auto', 'listar', 'detalhes')),
    escopo                text        CHECK (escopo IS NULL OR escopo IN ('vitrine', 'resto', 'todos')),
    caminho               text        CHECK (caminho IS NULL OR caminho IN ('listar', 'detalhes')),
    status                text        NOT NULL DEFAULT 'em_andamento'
                                      CHECK (status IN ('em_andamento', 'ok', 'incompleto', 'listar_vazio', 'removidos_excessivos',
                                                        'sem_credencial', 'falhou', 'ignorada')),
    iniciado_por          uuid,
    iniciado_em           timestamptz NOT NULL DEFAULT now(),
    finalizado_em         timestamptz,
    relatorio             jsonb       NOT NULL DEFAULT '{}'::jsonb,
    aviso_listar_vazio    boolean     NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS imoveis_sync_execucoes_org_idx
    ON social_wiring.imoveis_sync_execucoes (org_id, iniciado_em DESC);

COMMENT ON TABLE social_wiring.imoveis_sync_execucoes IS
    'One row per Vista imóveis refresh run (migration 315): path (listar|detalhes), status, counts and call counts in '
    'relatorio. status=em_andamento is the single-flight marker the manual button polls. aviso_listar_vazio marks the run '
    'that raised the once-a-day in-app notice. Backend-only.';

ALTER TABLE social_wiring.imoveis_sync_execucoes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS imoveis_sync_execucoes_service_role ON social_wiring.imoveis_sync_execucoes;
CREATE POLICY imoveis_sync_execucoes_service_role ON social_wiring.imoveis_sync_execucoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON social_wiring.imoveis_sync_execucoes FROM PUBLIC, anon, authenticated;
