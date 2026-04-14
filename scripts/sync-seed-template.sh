#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# sync-seed-template.sh
#
# Syncs the live seed product (products/seed/) to the template
# (templates/product-seed/) by copying files and replacing
# product-specific values with {{PLACEHOLDERS}}.
#
# Flow:
#   1. Backup current seed → products/seed/.backup/
#   2. Backup current template → templates/product-seed/.backup/
#   3. Copy seed → template (excluding build artifacts)
#   4. Replace product values with placeholders
#   5. Validate all expected placeholders exist
#
# Usage:
#   bash scripts/sync-seed-template.sh          # normal run
#   bash scripts/sync-seed-template.sh --dry    # show what would change
# ──────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SEED="$REPO_ROOT/products/seed"
TEMPLATE="$REPO_ROOT/templates/product-seed"
DRY_RUN="${1:-}"

# ── Colors ────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[sync]${NC} $1"; }
warn() { echo -e "${YELLOW}[warn]${NC} $1"; }
err()  { echo -e "${RED}[error]${NC} $1" >&2; }

# ── Pre-checks ───────────────────────────────────────────────
if [ ! -d "$SEED" ]; then
    err "Seed product not found at $SEED"
    err "Build the seed product first (see TODO-SEED-PRODUCT.md)"
    exit 1
fi

if [ "$DRY_RUN" = "--dry" ]; then
    log "DRY RUN — no files will be modified"
fi

# ── Step 1: Backup seed ──────────────────────────────────────
backup_dir() {
    local src="$1"
    local backup="$src/.backup"

    if [ "$DRY_RUN" = "--dry" ]; then
        log "Would backup $src → $backup"
        return
    fi

    # Remove old backup, create fresh
    rm -rf "$backup"
    mkdir -p "$backup"

    # Copy everything except .backup itself, node_modules, __pycache__, .env, venv
    rsync -a \
        --exclude='.backup' \
        --exclude='node_modules' \
        --exclude='__pycache__' \
        --exclude='.env' \
        --exclude='venv' \
        --exclude='dist' \
        --exclude='.pytest_cache' \
        --exclude='*.egg-info' \
        "$src/" "$backup/"

    log "Backed up $(basename "$src") → .backup/"
}

log "Step 1: Backing up current state..."
backup_dir "$SEED"
if [ -d "$TEMPLATE" ]; then
    backup_dir "$TEMPLATE"
fi

# ── Step 2: Copy seed → template ─────────────────────────────
log "Step 2: Copying seed → template..."

if [ "$DRY_RUN" = "--dry" ]; then
    log "Would copy $SEED → $TEMPLATE"
else
    # Preserve .backup in template if it exists
    if [ -d "$TEMPLATE/.backup" ]; then
        mv "$TEMPLATE/.backup" "/tmp/_noctus_template_backup_$$"
    fi

    # Clean template and copy fresh
    rm -rf "$TEMPLATE"
    mkdir -p "$TEMPLATE"

    rsync -a \
        --exclude='.backup' \
        --exclude='node_modules' \
        --exclude='__pycache__' \
        --exclude='.env' \
        --exclude='venv' \
        --exclude='dist' \
        --exclude='.pytest_cache' \
        --exclude='*.egg-info' \
        --exclude='package-lock.json' \
        "$SEED/" "$TEMPLATE/"

    # Restore template backup
    if [ -d "/tmp/_noctus_template_backup_$$" ]; then
        mv "/tmp/_noctus_template_backup_$$" "$TEMPLATE/.backup"
    fi

    log "Copied seed → template"
fi

# ── Step 3: Replace values with placeholders ─────────────────
log "Step 3: Replacing product values with placeholders..."

# Mapping: seed value → placeholder
declare -A REPLACEMENTS=(
    ["Seed Product"]="{{PRODUCT_NAME}}"
    ["Seed"]="{{PRODUCT_NAME}}"
    ["seed-product"]="{{PRODUCT_SLUG}}"
    ["\"seed\""]="\"{{SCHEMA_NAME}}\""
    ["'seed'"]="'{{SCHEMA_NAME}}'"
    ["8004"]="{{BACKEND_PORT}}"
    ["8100"]="{{FRONTEND_PORT}}"
    ["Sprout"]="{{PRODUCT_ICON}}"
)

if [ "$DRY_RUN" != "--dry" ]; then
    # Process all text files in template
    find "$TEMPLATE" -type f \( \
        -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" \
        -o -name "*.json" -o -name "*.md" -o -name "*.sql" \
        -o -name "*.css" -o -name "*.html" -o -name "*.yml" \
        -o -name "*.yaml" -o -name "*.toml" -o -name "*.cfg" \
        -o -name "*.txt" -o -name "*.env.example" \
    \) | while read -r file; do
        for key in "${!REPLACEMENTS[@]}"; do
            placeholder="${REPLACEMENTS[$key]}"
            # Use perl for reliable find-and-replace (handles special chars)
            perl -pi -e "s/\Q${key}\E/${placeholder}/g" "$file" 2>/dev/null || true
        done
    done

    log "Replaced product values with placeholders"
else
    log "Would replace: Seed→{{PRODUCT_NAME}}, seed→{{SCHEMA_NAME}}, 8004→{{BACKEND_PORT}}, 8100→{{FRONTEND_PORT}}, Sprout→{{PRODUCT_ICON}}"
fi

# ── Step 4: Validate ─────────────────────────────────────────
log "Step 4: Validating template..."

EXPECTED_PLACEHOLDERS=(
    "{{PRODUCT_NAME}}"
    "{{SCHEMA_NAME}}"
    "{{BACKEND_PORT}}"
    "{{FRONTEND_PORT}}"
)

errors=0
for placeholder in "${EXPECTED_PLACEHOLDERS[@]}"; do
    count=$(grep -r "$placeholder" "$TEMPLATE" --include="*.py" --include="*.ts" --include="*.tsx" --include="*.json" --include="*.sql" 2>/dev/null | wc -l)
    if [ "$count" -eq 0 ] && [ "$DRY_RUN" != "--dry" ]; then
        warn "Placeholder $placeholder not found in template"
        errors=$((errors + 1))
    else
        log "  $placeholder: $count occurrences"
    fi
done

if [ "$errors" -gt 0 ]; then
    warn "$errors placeholder(s) missing — template may be incomplete"
else
    log "All expected placeholders found"
fi

# ── Done ─────────────────────────────────────────────────────
log ""
log "Sync complete!"
log "  Seed:     $SEED"
log "  Template: $TEMPLATE"
log "  Backups:  .backup/ in each directory"
