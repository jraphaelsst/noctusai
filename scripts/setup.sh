#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# setup.sh — One-time setup after cloning the NoctusAI repo
#
# Run: bash scripts/setup.sh
#
# What it does:
#   1. Installs git hooks (seed auto-sync)
#   2. Creates Python venv + installs all backend deps
#   3. Installs seed packages (shared + framework) in dev mode
#   4. Installs frontend deps for all products
#   5. Verifies .env exists (warns if not)
#   6. Prints status summary
# ──────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${GREEN}[setup]${NC} $1"; }
warn() { echo -e "${YELLOW}[setup]${NC} $1"; }
step() { echo -e "\n${BLUE}── $1 ──${NC}"; }

echo ""
echo -e "${BLUE}╔══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     NoctusAI Platform Setup          ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════╝${NC}"
echo ""

# ── Step 1: Git hooks ────────────────────────────────────────
step "Step 1/5: Installing git hooks"

HOOKS_DIR="$REPO_ROOT/.git/hooks"

# post-commit: seed auto-sync
cat > "$HOOKS_DIR/post-commit" << 'HOOK'
#!/usr/bin/env bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
SEED_DIR="$REPO_ROOT/products/seed"
[ ! -d "$SEED_DIR" ] && exit 0
CHANGED_SEED=$(git diff-tree --no-commit-id --name-only -r HEAD -- products/seed/ 2>/dev/null | head -1)
[ -z "$CHANGED_SEED" ] && exit 0
[ -f "$REPO_ROOT/.seed-syncing" ] && rm -f "$REPO_ROOT/.seed-syncing" && exit 0
echo "[hook] Seed product changed — syncing template..."
touch "$REPO_ROOT/.seed-syncing"
bash "$REPO_ROOT/scripts/sync-seed-template.sh" 2>&1 | sed 's/^/[hook] /'
TEMPLATE_CHANGES=$(git status --porcelain -- templates/product-seed/ 2>/dev/null | head -1)
if [ -n "$TEMPLATE_CHANGES" ]; then
    git add templates/product-seed/
    git commit --amend --no-edit --no-verify 2>/dev/null
    echo "[hook] Template synced and included in commit"
else
    echo "[hook] Template already in sync"
fi
rm -f "$REPO_ROOT/.seed-syncing"
HOOK
chmod +x "$HOOKS_DIR/post-commit"
log "post-commit hook installed (seed → template auto-sync)"

# ── Step 2: Python venv ──────────────────────────────────────
step "Step 2/5: Python virtual environment"

if [ ! -d "$REPO_ROOT/venv" ]; then
    log "Creating venv..."
    python3.11 -m venv venv 2>/dev/null || python3 -m venv venv
    log "venv created"
else
    log "venv already exists"
fi

source "$REPO_ROOT/venv/bin/activate"

# ── Step 3: Backend deps ─────────────────────────────────────
step "Step 3/5: Backend dependencies"

pip install -q -r requirements.txt 2>/dev/null
log "Root requirements installed"

pip install -q -e seed/lib/backend 2>/dev/null
pip install -q -e seed/framework/backend 2>/dev/null
log "Seed packages installed (shared + framework, dev mode)"

# ── Step 4: Frontend deps ────────────────────────────────────
step "Step 4/5: Frontend dependencies"

FRONTENDS=(
    "core/frontend"
    "products/erp-imobiliario/frontend"
    "products/personal-finance/frontend"
    "products/therapy-platform/frontend"
)

for fe in "${FRONTENDS[@]}"; do
    if [ -d "$REPO_ROOT/$fe" ] && [ -f "$REPO_ROOT/$fe/package.json" ]; then
        (cd "$REPO_ROOT/$fe" && npm install --silent 2>/dev/null)
        log "$fe deps installed"
    fi
done

# Seed frontend (if exists)
if [ -d "$REPO_ROOT/products/seed/frontend" ] && [ -f "$REPO_ROOT/products/seed/frontend/package.json" ]; then
    (cd "$REPO_ROOT/products/seed/frontend" && npm install --silent 2>/dev/null)
    log "products/seed/frontend deps installed"
fi

# ── Step 5: Environment check ────────────────────────────────
step "Step 5/5: Environment verification"

if [ -f "$REPO_ROOT/.env" ]; then
    log ".env file found"
else
    warn ".env NOT found — create it from the template in CLAUDE.md"
    warn "The platform will not run without Supabase credentials."
fi

# ── Summary ──────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     Setup complete!                  ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""
echo "  Git hooks:  post-commit (seed auto-sync)"
echo "  Python:     venv/ with all deps"
echo "  Frontend:   node_modules/ in all products"
echo ""
echo "  Next: bash start.sh  (starts all services)"
echo ""
