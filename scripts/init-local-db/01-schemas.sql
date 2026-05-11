-- ============================================================================
-- 01-schemas.sql — CREATE SCHEMA IF NOT EXISTS for every product.
--
-- GENERATED FILE. Regenerate via: bash scripts/build-init-local-db.sh
--
-- Extracted from each product's 001_<slug>.sql migration. Running this
-- BEFORE 02-migrations.sql ensures cross-schema references in product
-- migrations always resolve to a pre-existing target schema.
-- ============================================================================

-- from: products/adconnect/backend/migrations/001_adconnect.sql
CREATE SCHEMA IF NOT EXISTS adconnect;

-- from: products/daily-life/backend/migrations/001_daily_life.sql
CREATE SCHEMA IF NOT EXISTS daily_life;

-- from: products/dev-team/backend/migrations/0001_init_telemetry_events.sql
CREATE SCHEMA IF NOT EXISTS dev_team;

-- from: products/erp-imobiliario/backend/migrations/001_erp_imobiliario.sql
CREATE SCHEMA IF NOT EXISTS erp;

-- from: products/mailing/backend/migrations/001_mailing.sql
CREATE SCHEMA IF NOT EXISTS mailing;

-- from: products/media-scheduling/backend/migrations/001_seed.sql
CREATE SCHEMA IF NOT EXISTS media_scheduling;

-- from: products/personal-finance/backend/migrations/001_personal_finance.sql
CREATE SCHEMA IF NOT EXISTS "personal-finance";

-- from: products/seed/backend/migrations/001_seed.sql
CREATE SCHEMA IF NOT EXISTS seed;

-- from: products/therapy-platform/backend/migrations/001_therapy_platform.sql
CREATE SCHEMA IF NOT EXISTS therapy;

-- from: products/youtube-crawler/backend/migrations/001_seed.sql
CREATE SCHEMA IF NOT EXISTS youtube_crawler;

