#!/usr/bin/env bash
# build-init-local-db.sh — regenerate scripts/init-local-db/01-schemas.sql
# and 02-migrations.sql from each product's `001_<slug>.sql` migration.
#
# The output is the input scripts the postgres container runs on a fresh
# volume to bootstrap a usable schema set for offline dev. See
# scripts/init-local-db/00a-supabase-shims.sql header for the why.
#
# Run this whenever a product's `001_*.sql` migration changes, and commit
# the regenerated 01/02 outputs. The committed-output discipline means
# the postgres profile is reproducible without re-running this script
# (no live filesystem dependency at container start).
#
# Usage:
#   bash scripts/bootstrap/build-init-local-db.sh
#
# Idempotent. Fails fast (`set -e`) if any 001 migration is missing.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
INIT_DIR="$ROOT_DIR/scripts/init-local-db"
SCHEMAS_OUT="$INIT_DIR/01-schemas.sql"
MIGRATIONS_OUT="$INIT_DIR/02-migrations.sql"

mkdir -p "$INIT_DIR"

# ─── Discover the FIRST migration per product ──────────────────────────────
# Most products use `001_<slug>.sql`; dev-team uses `0001_<name>.sql` (4-digit
# zero-padded). Per the project convention, the FIRST migration carries the
# full initial schema (see CLAUDE.md memory entry `single 001 migration per
# product`); later migrations are additive patches that may depend on
# Supabase-only features. For offline-dev we apply ONLY the first migration
# so the local DB has a known good baseline.
#
# Strategy: per product directory, find every `[0-9]*_*.sql` and pick the
# lexicographically-first (`001_*` vs `0001_*` both sort as "earliest").
# Skip data-seed files (e.g., `mock_*.sql`).
#
# Portable across bash 3.2 (macOS default) — no `mapfile`.

MIGRATION_FILES=()

PRODUCT_DIRS=()
# `core` first (other products FK to `public.organizations` etc.), then the
# rest alphabetically. The sort prelude pushes `products/core` to position 0
# and falls back to lexical order for the rest.
while IFS= read -r d; do
  PRODUCT_DIRS+=("$d")
done < <(
  find "$ROOT_DIR/products" -mindepth 1 -maxdepth 1 -type d \
    | awk -v core="$ROOT_DIR/products/core" '{ if ($0 == core) print "0\t"$0; else print "1\t"$0 }' \
    | sort \
    | cut -f2-
)

for product_dir in "${PRODUCT_DIRS[@]}"; do
  mig_dir="$product_dir/backend/migrations"
  [[ -d "$mig_dir" ]] || continue
  # First numeric-prefixed migration (lexically earliest).
  first_mig=$(find "$mig_dir" -maxdepth 1 -name "[0-9]*_*.sql" -type f | sort | head -1)
  [[ -n "$first_mig" ]] || continue
  MIGRATION_FILES+=("$first_mig")
done

if [[ ${#MIGRATION_FILES[@]} -eq 0 ]]; then
  echo "ERROR: no numeric-prefixed *.sql migrations found under products/*/backend/migrations/" >&2
  exit 1
fi

echo "Found ${#MIGRATION_FILES[@]} product migrations:"
for f in "${MIGRATION_FILES[@]}"; do
  echo "  $(realpath --relative-to="$ROOT_DIR" "$f" 2>/dev/null || echo "$f")"
done
echo ""

# ─── Generate 01-schemas.sql ────────────────────────────────────────────────
# Extract `CREATE SCHEMA IF NOT EXISTS <name>;` lines from each migration so
# every product schema exists BEFORE the bulk migrations run. This handles
# the (rare) case where a product migration has cross-schema dependencies.

{
  cat <<'HEADER'
-- ============================================================================
-- 01-schemas.sql — CREATE SCHEMA IF NOT EXISTS for every product.
--
-- GENERATED FILE. Regenerate via: bash scripts/bootstrap/build-init-local-db.sh
--
-- Extracted from each product's 001_<slug>.sql migration. Running this
-- BEFORE 02-migrations.sql ensures cross-schema references in product
-- migrations always resolve to a pre-existing target schema.
-- ============================================================================

HEADER

  for f in "${MIGRATION_FILES[@]}"; do
    rel=$(python3 -c "import os,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))" "$f" "$ROOT_DIR")
    schema_lines=$(grep -E '^CREATE SCHEMA IF NOT EXISTS' "$f" || true)
    if [[ -n "$schema_lines" ]]; then
      echo "-- from: $rel"
      echo "$schema_lines"
      echo ""
    fi
  done
} > "$SCHEMAS_OUT"

echo "Wrote $SCHEMAS_OUT ($(wc -l < "$SCHEMAS_OUT" | tr -d ' ') lines)"

# ─── Generate 02-migrations.sql ─────────────────────────────────────────────
# Concatenate every 001_<slug>.sql verbatim, separated by clear banners.
# Wrap each block in `BEGIN; ... COMMIT;` so a single product's failure
# rolls back THAT product's schema only — the rest still applies (best-effort
# offline-dev posture).

{
  cat <<'HEADER'
-- ============================================================================
-- 02-migrations.sql — concatenated product migrations.
--
-- GENERATED FILE. Regenerate via: bash scripts/bootstrap/build-init-local-db.sh
--
-- Each product's first migration is wrapped in BEGIN/COMMIT so one product's
-- failure (e.g., a Supabase-only feature this offline profile doesn't
-- support — `cron.schedule()`, `CREATE EXTENSION vector`, `pg_net`)
-- doesn't poison the others.
--
-- `ON_ERROR_STOP off` overrides the docker-entrypoint default of `=1` so a
-- single failing statement aborts its enclosing transaction (BEGIN/COMMIT
-- block rolls back) but psql CONTINUES to the next product's block. With
-- the default ON_ERROR_STOP=1 the entrypoint would abort the whole file on
-- the first cross-product incompatibility and the rest of the fleet's
-- schemas would be lost — empirically observed during T4 verification.
-- ============================================================================

\set ON_ERROR_STOP off

HEADER

  for f in "${MIGRATION_FILES[@]}"; do
    rel=$(python3 -c "import os,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))" "$f" "$ROOT_DIR")
    cat <<BANNER
-- ────────────────────────────────────────────────────────────────────────────
-- $rel
-- ────────────────────────────────────────────────────────────────────────────
BEGIN;

BANNER
    cat "$f"
    cat <<'BANNER'

COMMIT;

BANNER
  done
} > "$MIGRATIONS_OUT"

echo "Wrote $MIGRATIONS_OUT ($(wc -l < "$MIGRATIONS_OUT" | tr -d ' ') lines)"
echo ""
echo "Done. Commit scripts/init-local-db/0[12]-*.sql alongside this generator."
