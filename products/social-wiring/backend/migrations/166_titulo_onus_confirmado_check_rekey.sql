-- ============================================================================
-- Migration 166 · social_wiring: re-key `imovel_dados`'s título/ônus CHECKs
-- off `_origem` instead of `_confirmado_em` — a live prod bug (165's finding
-- d), not bad test data
-- ============================================================================
-- Roadmap: project-history/roadmaps/sw-extraction-contract-gate-2026-09.md
--
-- WHAT BROKE (verified live in prod, 2026-09-23, during the 165 backfill)
-- --------------------------------------------------------------------------
-- `preenchimento_service.preencher_sincrono` (migration 154, owner decision
-- D1) writes `imovel_dados.titulo_aquisitivo_texto` / `onus_credor` through
-- the SAME generic `campos_extraidos_service.aplicar` every other
-- contract-feeding field goes through: a fresh field is filled machine-
-- pending — value set, `<campo>_origem` set to `'matricula'`,
-- `<campo>_confirmado_por/_em` left NULL (D2 — a human validates later).
-- The roadmap's own D1 write-policy table (line 49) says this in as many
-- words: 154 added `titulo_aquisitivo_texto_origem` / `onus_credor_origem`
-- to these two fields FOR this reason.
--
-- But 115's own CHECKs —
--   `imovel_dados_titulo_aquisitivo_texto_confirmado`
--     CHECK ((titulo_aquisitivo_texto IS NULL) = (titulo_aquisitivo_texto_confirmado_em IS NULL))
--   `imovel_dados_onus_credor_confirmado`
--     CHECK ((onus_credor IS NULL) = (onus_credor_confirmado_em IS NULL))
-- — predate 154 and still enforce the OLDER, narrower invariant `titulo_
-- service.py` describes ("what IS stored is the operator's confirmation"):
-- text and CONFIRMATION travel together. Nobody relaxed them when 154 added
-- the machine-pending write path, so EVERY imóvel whose título act has a
-- readable instrumento (any real matrícula whose `estrutura_service.sugerir`
-- finds a título act with typed detail) fails this CHECK on its very first
-- `preencher_sincrono` call — reproducible, not a fixture artifact; the E2E
-- test imóvel E2E-IMV-LIVRE hit it, and any future prod imóvel with a
-- computable título phrase hits it too.
--
-- THE FIX
-- -------
-- Re-key both CHECKs off `_origem` (which travels WITH the value in BOTH
-- the machine-pending write, `aplicar`'s empty-field branch, AND the
-- confirmed write, `titulo_service._patch_confirmacao` — `origem` is never
-- left NULL while the value is set, on either path) instead of
-- `_confirmado_em` (which is legitimately NULL while machine-pending).
-- 115's narrower invariant — a CONFIRMATION timestamp must never appear on
-- a field with no value — still holds, folded into the SAME CHECK as a
-- second, one-directional clause: `confirmado_em IS NULL OR texto IS NOT
-- NULL`. Every ROW state either CHECK can produce today (see the pre-flight
-- counts below) already satisfies both clauses — a machine-pending row
-- (value + origem, no confirmado_em) is a NEW state this CHECK now
-- explicitly allows; nothing that was previously legal becomes illegal.
--
-- PRE-FLIGHT (read-only, counts only, verified live against prod via the
-- same `noctus.dev.migrate_product` SqlExecutor DI seam `verify_db_guards`
-- uses — 2026-09-23):
--   social_wiring.imovel_dados total rows ................................ 2
--   rows with titulo_aquisitivo_texto NOT NULL ............................ 1 (EUROVILLE-535, already `origem='manual'`, confirmado_em set — a human-confirmed row)
--   rows with onus_credor NOT NULL ......................................... 0
--   rows violating the NEW combined titulo_aquisitivo_texto CHECK ......... 0
--   rows violating the NEW combined onus_credor CHECK ...................... 0
-- Zero violators on both fields — `NOT VALID` + `VALIDATE CONSTRAINT` (the
-- house lock-light pattern, `027_erp_org_scoping_completion.sql`) applies
-- cleanly; no historical backfill needed.
--
-- FORWARD-ONLY, IDEMPOTENT (`DROP CONSTRAINT IF EXISTS` + re-`ADD`; safe to
-- re-run).
-- 🔴 MIGRATION FILE ONLY — applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. titulo_aquisitivo_texto — value<->origem pairing, confirmado_em never
--    without a value.
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_titulo_aquisitivo_texto_confirmado;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_titulo_aquisitivo_texto_pareado
    CHECK (
        (titulo_aquisitivo_texto IS NULL) = (titulo_aquisitivo_texto_origem IS NULL)
        AND (titulo_aquisitivo_texto_confirmado_em IS NULL OR titulo_aquisitivo_texto IS NOT NULL)
    ) NOT VALID;
ALTER TABLE social_wiring.imovel_dados
    VALIDATE CONSTRAINT imovel_dados_titulo_aquisitivo_texto_pareado;

-- ----------------------------------------------------------------------------
-- 2. onus_credor — the same two rules.
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_onus_credor_confirmado;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_onus_credor_pareado
    CHECK (
        (onus_credor IS NULL) = (onus_credor_origem IS NULL)
        AND (onus_credor_confirmado_em IS NULL OR onus_credor IS NOT NULL)
    ) NOT VALID;
ALTER TABLE social_wiring.imovel_dados
    VALIDATE CONSTRAINT imovel_dados_onus_credor_pareado;

COMMENT ON CONSTRAINT imovel_dados_titulo_aquisitivo_texto_pareado ON social_wiring.imovel_dados IS
    'Migration 166 (replaces 115''s imovel_dados_titulo_aquisitivo_texto_confirmado, '
    'which paired the value with confirmado_em and so refused the D1 machine-'
    'pending write 154 added). Two rules: the value and its _origem always '
    'travel together (machine-pending OR confirmed, never one without the '
    'other); a confirmation timestamp never appears without a value.';

COMMENT ON CONSTRAINT imovel_dados_onus_credor_pareado ON social_wiring.imovel_dados IS
    'Migration 166 (replaces 115''s imovel_dados_onus_credor_confirmado) — same '
    'two rules as imovel_dados_titulo_aquisitivo_texto_pareado, for onus_credor.';

NOTIFY pgrst, 'reload schema';
