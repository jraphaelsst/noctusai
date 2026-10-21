-- ============================================================================
-- 045: Julia v2 guardrails B5/B6 -- abuse limits as DATA (agents).
--
-- Owner mandate (2026-10-21): rate limits and admission control that stop someone trying to break the
-- operation on purpose, WITHOUT cutting a legitimate long conversation. Every number lives in
-- agents.canal_limites (per agent instance, editable later in the Studio); the code carries none.
--
--   * per-lead rate:        max_turnos_hora (the per-window cap already exists: max_turnos_janela)
--   * new-lead admission:   max_novos_leads_hora / max_novos_leads_dia
--   * budget reservation:   reserva_leads_existentes_pct (new threads may spend only the rest of the day's cap)
--   * loop / flood breaker: loop_* (similar repeats, echo of the agent's own reply, bot-fast replies)
--   * tool hardening:       max_chamadas_ferramenta_turno, max_oferecer_turno, max_abrir_skill_turno,
--                           max_detalhes_turno, catalogo_* (caps of the untrusted catalogue text)
--
-- Idempotent (ADD COLUMN IF NOT EXISTS). The column DEFAULTs are the single source of the numbers;
-- app.stores.conformidade.LIMITES_PADRAO mirrors them for the Fake.
-- ============================================================================

SET search_path = agents, public;

ALTER TABLE agents.canal_limites
    ADD COLUMN IF NOT EXISTS max_turnos_hora INTEGER NOT NULL DEFAULT 60
        CHECK (max_turnos_hora BETWEEN 1 AND 100000),
    ADD COLUMN IF NOT EXISTS max_novos_leads_hora INTEGER NOT NULL DEFAULT 30
        CHECK (max_novos_leads_hora BETWEEN 1 AND 100000),
    ADD COLUMN IF NOT EXISTS max_novos_leads_dia INTEGER NOT NULL DEFAULT 200
        CHECK (max_novos_leads_dia BETWEEN 1 AND 1000000),
    ADD COLUMN IF NOT EXISTS reserva_leads_existentes_pct INTEGER NOT NULL DEFAULT 50
        CHECK (reserva_leads_existentes_pct BETWEEN 0 AND 95),
    ADD COLUMN IF NOT EXISTS loop_ativo BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS loop_repeticoes INTEGER NOT NULL DEFAULT 3
        CHECK (loop_repeticoes BETWEEN 2 AND 50),
    ADD COLUMN IF NOT EXISTS loop_similaridade NUMERIC(4, 3) NOT NULL DEFAULT 0.9
        CHECK (loop_similaridade > 0 AND loop_similaridade <= 1),
    ADD COLUMN IF NOT EXISTS loop_janela_segundos INTEGER NOT NULL DEFAULT 600
        CHECK (loop_janela_segundos BETWEEN 10 AND 86400),
    ADD COLUMN IF NOT EXISTS loop_min_chars INTEGER NOT NULL DEFAULT 8
        CHECK (loop_min_chars BETWEEN 1 AND 500),
    ADD COLUMN IF NOT EXISTS loop_eco_tokens INTEGER NOT NULL DEFAULT 12
        CHECK (loop_eco_tokens BETWEEN 4 AND 200),
    ADD COLUMN IF NOT EXISTS loop_latencia_mediana_s NUMERIC(6, 2) NOT NULL DEFAULT 3
        CHECK (loop_latencia_mediana_s >= 0 AND loop_latencia_mediana_s <= 600),
    ADD COLUMN IF NOT EXISTS loop_trocas INTEGER NOT NULL DEFAULT 5
        CHECK (loop_trocas BETWEEN 2 AND 50),
    ADD COLUMN IF NOT EXISTS max_chamadas_ferramenta_turno INTEGER NOT NULL DEFAULT 8
        CHECK (max_chamadas_ferramenta_turno BETWEEN 1 AND 100),
    ADD COLUMN IF NOT EXISTS max_oferecer_turno INTEGER NOT NULL DEFAULT 1
        CHECK (max_oferecer_turno BETWEEN 1 AND 20),
    ADD COLUMN IF NOT EXISTS max_abrir_skill_turno INTEGER NOT NULL DEFAULT 4
        CHECK (max_abrir_skill_turno BETWEEN 1 AND 50),
    ADD COLUMN IF NOT EXISTS max_detalhes_turno INTEGER NOT NULL DEFAULT 3
        CHECK (max_detalhes_turno BETWEEN 1 AND 50),
    ADD COLUMN IF NOT EXISTS catalogo_descricao_max INTEGER NOT NULL DEFAULT 600
        CHECK (catalogo_descricao_max BETWEEN 50 AND 20000),
    ADD COLUMN IF NOT EXISTS catalogo_titulo_max INTEGER NOT NULL DEFAULT 120
        CHECK (catalogo_titulo_max BETWEEN 20 AND 1000),
    ADD COLUMN IF NOT EXISTS catalogo_caracteristicas_max INTEGER NOT NULL DEFAULT 30
        CHECK (catalogo_caracteristicas_max BETWEEN 1 AND 500),
    ADD COLUMN IF NOT EXISTS catalogo_item_max INTEGER NOT NULL DEFAULT 60
        CHECK (catalogo_item_max BETWEEN 10 AND 1000);
