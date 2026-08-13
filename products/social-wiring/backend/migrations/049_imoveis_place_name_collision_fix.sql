-- 049_imoveis_place_name_collision_fix.sql — canonicalize the two
-- casing-only `cidade`/`empreendimento` spellings currently split across
-- `social_wiring.imoveis`.
--
-- Fires the same class `040_imoveis.sql`'s `Caracteristicas` collision fired
-- (roadmap `social-wiring-imoveis-vista-2026-08`, Q4): a tenant-side
-- data-entry inconsistency on `oneconsu-rest`, not a modelling choice — but
-- Q4 only covered the amenity schema. This is the same defect on
-- `Cidade`/`Empreendimento`, measured live 2026-08-13:
--
--   `cidade`         "Embu das Artes" (57 rows) vs "Embu Das Artes" (19
--                     rows) — filtering by the majority spelling silently
--                     hides a quarter of that city's inventory.
--   `empreendimento`  "Granja Viana II - Gleba 1 e 2 - Km 26" vs
--                     "...Ii..." (18 rows combined)
--                     "Paisagem Renoir II e III - Km 26" vs
--                     "...Ii e Iii..." (8 rows combined)
--
-- `bairro` is untouched here — zero collisions were measured on it, and
-- (see the code comment at `imovel_normalizer.py`) it has not been
-- word-by-word diffed against `normalize_place_name` the way `cidade`/
-- `empreendimento` were. NOC-REMEDIATE[bairro-place-name-census] tracks
-- that follow-up; this migration stays scoped to what was verified.
--
-- ── Why hand-written UPDATEs, not a generic SQL port of the normalizer ──
-- `noctusai_lib.domain.real_estate.imovel.normalize_place_name` (the code
-- fix, same commit) is a general per-word classifier — pt-BR connective
-- lowering + Roman-numeral uppercasing + accent-safe title-case — built to
-- be safe across the WHOLE live catalog, not just these 3 rows. Porting
-- that algorithm into SQL would be real engineering for a migration that
-- only ever needs to run once, against exactly 3 known collision pairs.
-- Instead, each canonical value below is the LITERAL output of
-- `normalize_place_name()` run against the corresponding raw variant
-- (verified interactively before authoring this file) — so the migration
-- and the code are provably consistent without duplicating the logic.
--
-- ── Row counts this migration touches ────────────────────────────────────
-- `cidade`: exactly 19 rows (`"Embu Das Artes"` → `"Embu das Artes"` — the
-- brief's live count for that spelling).
-- `empreendimento`: the brief gives the PAIR total per collision (18 and 8
-- imóveis respectively), not the per-spelling split, and this migration was
-- authored without live DB query access to split it further. Each UPDATE
-- below is scoped to `WHERE empreendimento = '<the Ii/Iii spelling>'` only
-- — it never touches a row that already holds the canonical `II`/`III`
-- spelling — so whichever way the 18/8 actually split, this affects only
-- the genuinely miscased rows. Upper bound across all three UPDATEs: 45
-- rows (19 + 18 + 8); the true count is likely lower since some rows in
-- each pair are presumably already canonical.
--
-- Idempotent: re-running finds zero matching rows the second time (every
-- WHERE clause targets the non-canonical spelling by exact match).
--
-- 🔴 MIGRATION FILE ONLY — NOT applied to any DB by this change. This is a
-- MIRROR table (`ImovelSyncService.sync()` overwrites it from Vista), so a
-- data-only fix without the code fix would be undone by the next sync, and
-- the code fix without this data-only fix leaves the current 45-or-fewer
-- rows wrong until the next full sync runs (~4-6 min, not immediate). Apply
-- via `noctus.dev.migrate_product` with explicit tech-lead consent — there
-- is no dev DB, so applying this goes straight to production.

SET search_path = social_wiring, public;

-- `cidade` — the one measured collision (76 imóveis total; 19 non-canonical).
UPDATE imoveis
SET cidade = 'Embu das Artes'
WHERE cidade = 'Embu Das Artes';

-- `empreendimento` — the two measured collisions (26 imóveis total across
-- both spellings combined; exact non-canonical split not measured).
UPDATE imoveis
SET empreendimento = 'Granja Viana II - Gleba 1 e 2 - Km 26'
WHERE empreendimento = 'Granja Viana Ii - Gleba 1 e 2 - Km 26';

UPDATE imoveis
SET empreendimento = 'Paisagem Renoir II e III - Km 26'
WHERE empreendimento = 'Paisagem Renoir Ii e Iii - Km 26';
