-- ============================================================================
-- Migration 253 — cs_roteiros.estrutura: neutral beat-order value names
-- (+ table comments scrubbed of the external app's name).
--
-- WHY (owner decision 2026-10-13, "no leftovers from Core"): migration 250 named
-- the two beat orders after the external app the module was rebuilt from
-- ('corestudio') and reused the methodology's own name ('metodo') for the
-- other, which is ambiguous with the Método itself. The values are renamed to
-- what they ARE:
--
--   corestudio -> cta_inicio   (CTA de salvar right after the capa; the default)
--   metodo     -> cta_final    (capa first, ONE merged CTA last)
--
-- Migration 250 is left untouched (never edit an applied migration); this one
-- rewrites the constraint + default + existing rows. Same named CHECK
-- (`cs_roteiros_estrutura_check`) so the verify_db_guards GuardProbe still
-- targets it. Idempotent: the constraint is dropped first (so the UPDATE is not
-- blocked by the old CHECK), UPDATEs are no-ops on a second run, the new CHECK
-- is DROP IF EXISTS + ADD, COMMENT ON is idempotent. Requires 217, 229, 250.
-- ============================================================================
SET search_path = social_wiring, public;

ALTER TABLE social_wiring.cs_roteiros
    DROP CONSTRAINT IF EXISTS cs_roteiros_estrutura_check;

UPDATE social_wiring.cs_roteiros SET estrutura = 'cta_inicio' WHERE estrutura = 'corestudio';
UPDATE social_wiring.cs_roteiros SET estrutura = 'cta_final'  WHERE estrutura = 'metodo';

ALTER TABLE social_wiring.cs_roteiros
    ALTER COLUMN estrutura SET DEFAULT 'cta_inicio';

ALTER TABLE social_wiring.cs_roteiros
    ADD CONSTRAINT cs_roteiros_estrutura_check
    CHECK (estrutura IN ('cta_inicio', 'cta_final'));

COMMENT ON COLUMN social_wiring.cs_roteiros.estrutura IS
    'Beat order of the roteiro (migrations 250 + 253): cta_inicio (CTA de salvar '
    'right after the capa) | cta_final (capa first, one merged CTA last). '
    'Reprocessar reuses it.';

-- Table comments of earlier migrations (217, 229) carried the external app's
-- name; those files stay as applied, the live comments are rewritten here.
COMMENT ON TABLE social_wiring.cs_research_variables IS
    'Migration 217 - Minha Pesquisa taxonomy: 29 reference-app variables + 4 globals + 7 classifier-only. '
    'Seeded from pesquisa_variables.py; read-only for authenticated users.';
COMMENT ON TABLE social_wiring.cs_nichos IS
    'Migration 229 - nichos (28 rows, reference-app ids). Seeded from geracao_taxonomias.py; read-only for authenticated users.';
COMMENT ON TABLE social_wiring.cs_profissoes IS
    'Migration 229 - profissoes (102 rows, reference-app ids). Seeded from geracao_taxonomias.py; read-only for authenticated users.';
COMMENT ON TABLE social_wiring.cs_treinamentos IS
    'Migration 229 - platform-wide training lessons (no org_id). Seeded with the 5 original lessons, video_url NULL; '
    'writes go through the backend only (platform admin).';
