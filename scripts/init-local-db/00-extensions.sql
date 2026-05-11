-- ============================================================================
-- 00-extensions.sql — Postgres extensions required by product migrations.
--
-- This file runs FIRST (alphabetical order) inside the postgres container's
-- docker-entrypoint-initdb.d/ on a fresh postgres_data volume. Once the
-- volume has data, postgres does NOT re-run init scripts; tear the volume
-- (./stop.sh volumes) to re-init.
--
-- Extension set chosen by grepping every product's 001_<slug>.sql migration
-- for `CREATE EXTENSION` / `gen_random_uuid()` / `citext` / `uuid_generate_*`.
-- Keep this list MINIMAL — only what migrations actually reference.
--
-- pgcrypto    : provides `gen_random_uuid()` (used as PRIMARY KEY DEFAULT)
-- uuid-ossp   : provides `uuid_generate_v4()` (legacy; some product migrations
--               still reference it)
-- citext      : provides case-insensitive text type (some email columns)
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS citext;
