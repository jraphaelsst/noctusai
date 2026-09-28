-- ============================================================================
-- 034_card_hub_lembretes_titulo.sql — IGIG (igig)
--
-- Additive follow-up to 019_card_hub.sql: turns on
-- `CardHubConfig.lembretes_crud` for both card hubs (app/card_hub.py) so the
-- seed's ad-hoc reminder CRUD (`GET/POST .../lembretes`,
-- `PATCH/DELETE .../lembretes/{id}`) has somewhere to write a título and an
-- optional responsável — the columns a full "Lembretes" subpage needs, beyond
-- the single Datas-driven fire `lembrete_minutos_antes` materialises.
--
-- 019 already ran in every environment where `cliente_lembretes` /
-- `negocio_lembretes` exist (its `CREATE TABLE IF NOT EXISTS` is a no-op
-- there), so the new columns arrive here as a plain `ALTER TABLE`. 019 was
-- ALSO regenerated in this same change (`noctusai_lib.domain.card_hub.sql`
-- now emits these columns behind the flag) so a FRESH environment gets them
-- from the CREATE TABLE directly — this file's `IF NOT EXISTS` makes that
-- case a no-op, not a duplicate-column error.
--
-- No SQLite mirror, by design — like 019 itself (see its header): the card
-- hub is reached ONLY through PostgREST (`NOC-REMEDIATE[card-hub-recordstore]`
-- in the seed package), so this file is deliberately NOT named `034_igig_*`
-- (`test_schema_parity.py`'s `PG_FILES` glob only matches that pattern).
-- ============================================================================
SET search_path = igig, public;

ALTER TABLE igig.cliente_lembretes
    ADD COLUMN IF NOT EXISTS titulo         TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS responsavel_id UUID REFERENCES igig.profissional(id) ON DELETE SET NULL;

ALTER TABLE igig.negocio_lembretes
    ADD COLUMN IF NOT EXISTS titulo         TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS responsavel_id UUID REFERENCES igig.profissional(id) ON DELETE SET NULL;
