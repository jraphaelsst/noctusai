-- 218_campanha_intake.sql — sw-lead-to-contract S1: the imóvel comes from the campaign
--
-- CONTRACT: products/social-wiring/projects/sw-lead-to-contract/CONTRACT.md §1.
-- Reuses mig 065's (empty) campanhas / campanha_imoveis / campanha_veiculacoes — no new
-- tables. Adds only what the contract needs and 065 lacks:
--
--   * campanha_veiculacoes.nivel — WHICH Meta object `ref_codigo` names. Intake resolves
--     ad → adset → campaign → form (§1.2); without the level an id could match the wrong
--     row. Required for canal='meta_ads', NULL for every other canal (they have no levels).
--   * campanhas.deleted_at — DELETE /api/campanhas/{id} is a soft delete (§1.1); a deleted
--     campanha never resolves a lead.
--   * meta_ads_leads.simulado — rows created by POST /api/meta/leadgen/simular (§1.4) are
--     marked, never mistaken for a real Meta lead.
--   * status_pagina 'campanhas' — the new /campanhas page under Leads.
--
-- RLS: every column lands on a table that already carries the org-picker policies (211)
-- and the acting-audit trigger (214 attaches per table, so new columns are covered).
-- Additive + idempotent.

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.campanha_veiculacoes
    ADD COLUMN IF NOT EXISTS nivel TEXT;

DO $c$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conname = 'campanha_veiculacoes_nivel_valido'
                    AND conrelid = 'social_wiring.campanha_veiculacoes'::regclass) THEN
    ALTER TABLE social_wiring.campanha_veiculacoes
      ADD CONSTRAINT campanha_veiculacoes_nivel_valido CHECK (
        (canal = 'meta_ads' AND nivel IN ('campaign', 'adset', 'ad', 'form'))
        OR (canal <> 'meta_ads' AND nivel IS NULL)
      );
  END IF;
END
$c$;

-- One Meta object resolves to ONE campanha per org — a second row would make intake guess.
CREATE UNIQUE INDEX IF NOT EXISTS campanha_veiculacoes_meta_ref_unico
    ON social_wiring.campanha_veiculacoes (org_id, nivel, ref_codigo)
    WHERE canal = 'meta_ads';

ALTER TABLE social_wiring.campanhas
    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

ALTER TABLE social_wiring.meta_ads_leads
    ADD COLUMN IF NOT EXISTS simulado BOOLEAN NOT NULL DEFAULT false;

INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES
    ('campanhas', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
