-- ============================================================================
-- Migration 093 · social_wiring: the 29 Vista fields the calibrator found
--
-- Contract: projects/imoveis-vista-field-surface-CONTRACT.md §1 (authored by
-- the tech-lead 2026-09-04, BEFORE this dispatch). Every column below is
-- **measured live** against tenant `oneconsu-rest`: 107 candidate field
-- names probed on `/imoveis/detalhes` (Vista answers `400 "Campo X não está
-- disponível"` for a field this tenant doesn't expose), 32 fields accepted
-- and re-probed across 20 imóveis spanning all 20 categorias, then narrowed
-- to 29 — see the CORRECTION note below. Nothing here is guessed — the
-- per-column "Measured" note mirrors the contract table.
--
-- 🔴 CORRECTION 2026-09-04 — `Lavabo`/`Copa`/`Escritorio` DROPPED
-- ---------------------------------------------------------------------------
-- The contract originally listed 32 fields; 3 were removed after a live
-- re-check found Vista SHADOWS them. All three are also keys inside
-- `Caracteristicas`, and when `Caracteristicas` rides in the same
-- `/imoveis/detalhes` `fields` request (our sync always includes it),
-- Vista returns `null` for the top-level `Escritorio`/`Lavabo`/`Copa`
-- fields — even though the identical value is present, correctly, inside
-- `Caracteristicas` itself. Shipping those 3 columns would mean permanently
-- NULL columns in production while the true value sits one JSONB key away
-- in `caracteristicas_raw`. `Elevador` and `Portaria` were checked against
-- the same collision and are NOT shadowed — they keep their columns.
--
-- WHY STORE ALL 29 EVEN WHERE THE 20-IMÓVEL SAMPLE READS MOSTLY EMPTY
-- ---------------------------------------------------------------------------
-- n=20 of 2057 is weak evidence for DROPPING a field — `Ocupacao` populates
-- on only 9/20 sampled rows yet is a real, tenant-populated fact on the
-- rest of the catalog. Columns are cheap; `vista_raw` already retains
-- everything Vista sends either way. The UI renders every section
-- conditionally, so an always-empty column costs nothing on screen and
-- loses nothing if the tenant starts populating it.
--
-- 🔴 `matricula_vista`, NOT `matricula`
-- ---------------------------------------------------------------------------
-- `social_wiring.imovel_dados` (migration 075) already owns a
-- cartório-authored `matricula` — a column WE write, sourced from a document
-- upload, not from Vista. Naming this one `matricula` would put two
-- different `matricula`s in one schema with no way to tell which is which
-- from the column name alone: exactly the `origem` collision the 2026-08
-- roadmap called out for a different pair of columns. Keeping them
-- `matricula_vista` (mirror, read-only) vs `matricula` (ours, cartório-
-- sourced) makes the provenance part of the name instead of tribal
-- knowledge.
--
-- SAME ASYMMETRIC CHECK CONVENTION AS 040_imoveis.sql — DO NOT "HARMONIZE"
-- ---------------------------------------------------------------------------
-- Money/measure columns reject a stored 0 (`"0"` on the wire means "not
-- applicable", matching `valor_venda > 0` / `area_construida > 0`):
-- `valor_condominio`, `valor_iptu`, `ano_construcao`, `area_terreno`,
-- `frente`, `fundos`. Count columns ACCEPT 0 (a real zero is a fact, NULL is
-- unknown), matching `dormitorios >= 0`: `pavimentos`, `closet`. This is the
-- same deliberate asymmetry 040 pins with its own tests — do not collapse
-- the two conventions into one CHECK shape.
--
-- 🔴 NO RLS CHANGES — CONSIDERED, NOT NEEDED
-- ---------------------------------------------------------------------------
-- These are plain columns added to the existing `social_wiring.imoveis`
-- table. RLS is table-scoped in Postgres — a policy has no column list to
-- update — so the existing `imoveis_select_own_org` (org-scoped SELECT) and
-- `imoveis_service_role` (service_role ALL) policies from 040 cover every
-- new column automatically. Nothing to add, nothing to touch.
--
-- FORWARD-ONLY, IDEMPOTENT (`ADD COLUMN IF NOT EXISTS` /
-- `DROP CONSTRAINT IF EXISTS` + `ADD CONSTRAINT`).
-- 🔴 MIGRATION FILE ONLY — not applied to any database by this change. The
-- tech-lead applies it via the documented path.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.imoveis
    -- Descrição — n=20: descricao_web 20/20 (463–1648 chars), observacoes 0/20.
    ADD COLUMN IF NOT EXISTS descricao_web         TEXT,
    ADD COLUMN IF NOT EXISTS observacoes           TEXT,

    -- Custos além do valor de venda/locação. n=20: condomínio 11/20, IPTU 18/20.
    ADD COLUMN IF NOT EXISTS valor_condominio       NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS valor_iptu             NUMERIC(14, 2),

    -- Construção e estado. n=20: ano_construcao 16/20, situacao 7/20
    -- ("Usado"), ocupacao 9/20 ("Proprietário"/"Desocupado"), pavimentos
    -- 0-valued on every sampled row, posicao 1/20 ("Frente").
    ADD COLUMN IF NOT EXISTS ano_construcao         INTEGER,
    ADD COLUMN IF NOT EXISTS situacao               TEXT,
    ADD COLUMN IF NOT EXISTS ocupacao               TEXT,
    ADD COLUMN IF NOT EXISTS pavimentos             INTEGER,
    ADD COLUMN IF NOT EXISTS posicao                TEXT,

    -- Comodidades estruturais (BOOLEAN — "Sim"/"Nao" flags, not counts).
    ADD COLUMN IF NOT EXISTS elevador               BOOLEAN,
    ADD COLUMN IF NOT EXISTS portaria               BOOLEAN,

    -- Condições comerciais. n=20: exclusivo 1/20, permuta 7/20,
    -- financiamento 4/20, destaque/super-destaque vary (both Sim on
    -- ONE10107), exibir_no_site 20/20 Sim.
    ADD COLUMN IF NOT EXISTS exclusivo              BOOLEAN,
    ADD COLUMN IF NOT EXISTS aceita_permuta          BOOLEAN,
    ADD COLUMN IF NOT EXISTS aceita_financiamento    BOOLEAN,
    ADD COLUMN IF NOT EXISTS destaque_web            BOOLEAN,
    ADD COLUMN IF NOT EXISTS super_destaque_web      BOOLEAN,
    ADD COLUMN IF NOT EXISTS exibir_no_site          BOOLEAN,
    ADD COLUMN IF NOT EXISTS chave                  TEXT,

    -- Localização, além do que 040 already stores. n=20: zona 5/20
    -- (upstream-truncated to ~10 chars — stored verbatim, not our bug to
    -- fix), regiao 0/20.
    ADD COLUMN IF NOT EXISTS zona                   TEXT,
    ADD COLUMN IF NOT EXISTS regiao                 TEXT,

    -- Áreas e dimensões extras. n=20: area_terreno 3/20, frente and fundos
    -- both 0-valued on every sampled row.
    ADD COLUMN IF NOT EXISTS area_terreno           NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS frente                 NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS fundos                 NUMERIC(12, 2),

    -- Cômodos extras, beyond 040's dormitorios/suites/vagas/banheiro_social.
    -- n=20: closet 0-valued on every sampled row. `lavabo`/`copa`/
    -- `escritorio` are DELIBERATELY absent — see the 2026-09-04 CORRECTION
    -- above: Vista shadows all three whenever `Caracteristicas` rides in
    -- the same request (our sync always includes it), so a column would be
    -- permanently NULL while the true value already lives in
    -- `caracteristicas_raw`/`caracteristicas`. Source them from there.
    ADD COLUMN IF NOT EXISTS closet                 INTEGER,

    -- Identificação / registro. n=20: referencia 20/20 (always == codigo —
    -- kept as its own column anyway since Vista sends it as a distinct
    -- field and a future tenant could diverge), matricula_vista 7/20,
    -- inscricao_municipal 1/20 (holds a CITY name on this tenant — data-
    -- entry noise upstream, stored verbatim, not normalized here).
    ADD COLUMN IF NOT EXISTS referencia             TEXT,
    ADD COLUMN IF NOT EXISTS matricula_vista        TEXT,
    ADD COLUMN IF NOT EXISTS inscricao_municipal    TEXT,

    -- Mídia extra, beyond 040's foto_destaque/fotos. n=20: video_destaque
    -- 0/20, tour_360 3/20 (real 360° tour URLs).
    ADD COLUMN IF NOT EXISTS video_destaque         TEXT,
    ADD COLUMN IF NOT EXISTS tour_360               TEXT;

COMMENT ON COLUMN social_wiring.imoveis.matricula_vista IS
    'Vista''s own `Matricula` field, Vista-sourced and read-only (this table '
    'is a mirror). Deliberately NOT named `matricula` — that name is already '
    'taken by `social_wiring.imovel_dados.matricula` (migration 075), a '
    'cartório-authored column WE write from an uploaded document. Two '
    'different `matricula`s in one schema, one Vista-sourced and one ours, '
    'is the exact `origem` collision the 2026-08 roadmap flagged for a '
    'different pair of columns — keep them namespaced and distinct.';

COMMENT ON COLUMN social_wiring.imoveis.inscricao_municipal IS
    'On tenant `oneconsu-rest`, the one populated sample value holds a CITY '
    'name, not an inscrição municipal number — a tenant data-entry defect, '
    'not a parsing bug on our side. Stored verbatim; do not "fix" the value.';

COMMENT ON COLUMN social_wiring.imoveis.zona IS
    'Populated on 5/20 sampled rows, upstream-truncated to ~10 characters on '
    'this tenant. Stored verbatim — the truncation happens before Vista '
    'sends it, there is nothing left here to recover.';

-- ── CHECK constraints — same asymmetric convention as 040_imoveis.sql ──
-- Money/measure: "0" on the wire means "not applicable", so a stored 0 is a
-- bug. Counts: 0 is a real, meaningful value and must survive.
ALTER TABLE social_wiring.imoveis
    DROP CONSTRAINT IF EXISTS imoveis_valor_condominio_not_zero;
ALTER TABLE social_wiring.imoveis
    ADD CONSTRAINT imoveis_valor_condominio_not_zero
    CHECK (valor_condominio IS NULL OR valor_condominio > 0);

ALTER TABLE social_wiring.imoveis
    DROP CONSTRAINT IF EXISTS imoveis_valor_iptu_not_zero;
ALTER TABLE social_wiring.imoveis
    ADD CONSTRAINT imoveis_valor_iptu_not_zero
    CHECK (valor_iptu IS NULL OR valor_iptu > 0);

ALTER TABLE social_wiring.imoveis
    DROP CONSTRAINT IF EXISTS imoveis_ano_construcao_not_zero;
ALTER TABLE social_wiring.imoveis
    ADD CONSTRAINT imoveis_ano_construcao_not_zero
    CHECK (ano_construcao IS NULL OR ano_construcao > 0);

ALTER TABLE social_wiring.imoveis
    DROP CONSTRAINT IF EXISTS imoveis_area_terreno_not_zero;
ALTER TABLE social_wiring.imoveis
    ADD CONSTRAINT imoveis_area_terreno_not_zero
    CHECK (area_terreno IS NULL OR area_terreno > 0);

ALTER TABLE social_wiring.imoveis
    DROP CONSTRAINT IF EXISTS imoveis_frente_not_zero;
ALTER TABLE social_wiring.imoveis
    ADD CONSTRAINT imoveis_frente_not_zero
    CHECK (frente IS NULL OR frente > 0);

ALTER TABLE social_wiring.imoveis
    DROP CONSTRAINT IF EXISTS imoveis_fundos_not_zero;
ALTER TABLE social_wiring.imoveis
    ADD CONSTRAINT imoveis_fundos_not_zero
    CHECK (fundos IS NULL OR fundos > 0);

-- Counts — deliberately `>= 0`, NOT `> 0`. Do not harmonize with the block
-- above: a real zero (e.g. zero pavimentos on a térreo-only building) is
-- data, not absence.
ALTER TABLE social_wiring.imoveis
    DROP CONSTRAINT IF EXISTS imoveis_pavimentos_non_negative;
ALTER TABLE social_wiring.imoveis
    ADD CONSTRAINT imoveis_pavimentos_non_negative
    CHECK (pavimentos IS NULL OR pavimentos >= 0);

ALTER TABLE social_wiring.imoveis
    DROP CONSTRAINT IF EXISTS imoveis_closet_non_negative;
ALTER TABLE social_wiring.imoveis
    ADD CONSTRAINT imoveis_closet_non_negative
    CHECK (closet IS NULL OR closet >= 0);
