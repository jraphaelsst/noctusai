#!/usr/bin/env bash
# Bootstrap a seed workspace as a sibling of this noc repo.
#
# A seed workspace is a sibling folder that consumes noc strictly
# read-only via symlinks (CLAUDE.md, KB, .claude/, mcp/, seed/,
# noctusai_lib/, templates/). Templates serve three use cases:
# sandbox / new-product staging / parallel-agent isolation.
#
# Design source of truth: KNOWLEDGE-BASE/CONTEXT/PATTERNS/seed-workspace.md
# Project: projects/seed-workspace/PROJECT.md
#
# Usage:
#   bash scripts/bootstrap-seed-workspace.sh --target <abs-path> [opts]
#
# Idempotent: re-runs refresh symlinks + chmod + marker without touching
# local content (projects/, sandbox/, products/, .promotions/, git history).

set -euo pipefail

# ----- arg parsing -----
TARGET=""
NAME=""
NOC_HOME=""
FORCE=false

usage() {
  cat >&2 <<EOF
Usage: $0 --target <abs-path> [--name <workspace-name>] [--noc-home <path>] [--force]

Required:
  --target <path>     Absolute path where the workspace will be created.

Optional:
  --name <name>       Workspace label written to .noctusai-workspace marker
                      (default: basename of --target).
  --noc-home <path>   Absolute path to noc repo (default: detected from script
                      location — script lives in noc/scripts/).
  --force             Overwrite a non-empty target dir that lacks the marker.
                      Use only when you've verified the dir is safe to clobber.
  -h, --help          Show this help.

Examples:
  bash scripts/bootstrap-seed-workspace.sh \\
       --target ~/Documents/repository/NoctusAI/noctusai-template

  # Re-run on existing workspace to refresh symlinks (idempotent):
  bash scripts/bootstrap-seed-workspace.sh \\
       --target ~/Documents/repository/NoctusAI/noctusai-template

See projects/seed-workspace/PROJECT.md for the design.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)    TARGET="$2"; shift 2 ;;
    --name)      NAME="$2"; shift 2 ;;
    --noc-home)  NOC_HOME="$2"; shift 2 ;;
    --force)     FORCE=true; shift ;;
    -h|--help)   usage; exit 0 ;;
    *) echo "ERROR: unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$TARGET" ]]; then
  echo "ERROR: --target is required" >&2
  usage
  exit 2
fi

# ----- resolve noc home -----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "$NOC_HOME" ]]; then
  # script lives in noc/scripts/, so noc root is one level up
  NOC_HOME="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

# Verify noc looks legitimate.
for required in "CLAUDE.md" "KNOWLEDGE-BASE" "mcp" "seed"; do
  if [[ ! -e "$NOC_HOME/$required" ]]; then
    echo "ERROR: $NOC_HOME doesn't look like noc — missing $required" >&2
    exit 2
  fi
done

# Resolve target to absolute path (handles ~, relative).
TARGET="$(cd "$(dirname "$TARGET")" 2>/dev/null && pwd)/$(basename "$TARGET")" || TARGET="$TARGET"

# Default name = basename of target.
[[ -z "$NAME" ]] && NAME="$(basename "$TARGET")"

# Sanity: refuse to bootstrap INSIDE noc (would create a confused symlink loop).
case "$TARGET/" in
  "$NOC_HOME"/*)
    echo "ERROR: refusing to create workspace inside noc ($NOC_HOME)" >&2
    echo "       Pick a sibling path instead." >&2
    exit 2
    ;;
esac

# ----- target dir state -----
EXISTING_WORKSPACE=false
if [[ -e "$TARGET" ]]; then
  if [[ ! -d "$TARGET" ]]; then
    echo "ERROR: $TARGET exists but is not a directory" >&2
    exit 2
  fi
  if [[ -f "$TARGET/.noctusai-workspace" ]]; then
    echo "INFO: $TARGET already a noctusai workspace; refreshing symlinks + chmod + marker"
    EXISTING_WORKSPACE=true
  elif [[ -n "$(ls -A "$TARGET" 2>/dev/null)" ]]; then
    if ! $FORCE; then
      echo "ERROR: $TARGET exists, is non-empty, and is not a noctusai workspace." >&2
      echo "       Use --force to bootstrap into it anyway (you've been warned)." >&2
      exit 2
    fi
    echo "WARN: --force given; bootstrapping into non-empty non-workspace dir"
  fi
fi

mkdir -p "$TARGET"

# ----- the 7 surfaces consumed from noc -----
# Note: `noctusai_lib` is NOT a top-level surface in noc — it lives at
# `seed/lib/backend/noctusai_lib/` and is editable-installed by mcp's
# requirements.txt. Symlinking `seed/` already exposes it; the MCP toolkit
# in template (symlinked from noc) inherits the same editable install.
SURFACES=(
  "CLAUDE.md"
  "CLAUDE"
  "KNOWLEDGE-BASE"
  ".claude"
  "mcp"
  "seed"
  "templates"
)

# ----- symlink + chmod each surface -----
echo "==> Symlinking $((${#SURFACES[@]})) noc surfaces into $TARGET"
for surface in "${SURFACES[@]}"; do
  src="$NOC_HOME/$surface"
  dst="$TARGET/$surface"

  if [[ ! -e "$src" ]]; then
    echo "    WARN: $src missing in noc; skipping symlink for $surface"
    continue
  fi

  # Refresh: remove stale entry (file, dir, symlink) at workspace path.
  if [[ -L "$dst" || -e "$dst" ]]; then
    rm -rf "$dst"
  fi

  ln -s "$src" "$dst"

  # chmod a-w on the SYMLINK (not the target — symlink targets affect noc).
  # macOS: -h applies to the symlink itself; symlinks ignore mode bits at the
  # kernel level so this is symbolic. Linux: mode bits on symlinks are also
  # mostly ignored. The pre-commit hook is the actual write defense.
  chmod -h a-w "$dst" 2>/dev/null || true

  echo "    OK   $surface  ->  $src"
done

# ----- local dirs -----
echo "==> Creating local workspace dirs"
mkdir -p "$TARGET/projects"
mkdir -p "$TARGET/sandbox"
mkdir -p "$TARGET/products"
mkdir -p "$TARGET/.promotions"
mkdir -p "$TARGET/.noctusai-state"
mkdir -p "$TARGET/.githooks"
echo "    OK   projects/ sandbox/ products/ .promotions/ .noctusai-state/ .githooks/"

# ----- marker file (the source of workspace identity) -----
echo "==> Planting .noctusai-workspace marker"
cat > "$TARGET/.noctusai-workspace" <<EOF
# NoctusAI workspace marker — DO NOT EDIT.
# Identifies this directory as a workspace for the MCP toolkit's
# workspace-aware tools (status, file_proposal, scaffold_product).
# See KNOWLEDGE-BASE/CONTEXT/PATTERNS/seed-workspace.md.
workspace_kind=seed
workspace_name=$NAME
noctusai_home=$NOC_HOME
bootstrap_version=1
created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

# ----- .env (local; gitignored) -----
if [[ ! -f "$TARGET/.env" ]]; then
  echo "==> Creating .env (NOCTUSAI_HOME pointer)"
  cat > "$TARGET/.env" <<EOF
# Seed workspace .env — local; gitignored.
# Pointer to the noc repo this workspace consumes.
NOCTUSAI_HOME=$NOC_HOME
EOF
else
  echo "==> .env already exists; not touching"
fi

# ----- .gitignore -----
if [[ ! -f "$TARGET/.gitignore" ]]; then
  echo "==> Creating .gitignore"
  cat > "$TARGET/.gitignore" <<'EOF'
# Workspace-local state — never tracked.
.noctusai-state/
.env

# Standard exclusions.
__pycache__/
*.pyc
.pytest_cache/
.venv/
node_modules/
.DS_Store
EOF
else
  echo "==> .gitignore already exists; not touching"
fi

# ----- .promotions/ manifest template -----
# Authors drop one copy per promotable capability. Shipped by default so
# the absorption map is a convention, not tribal knowledge.
MANIFEST_TPL_SRC="$NOC_HOME/templates/seed-workspace-promotions-MANIFEST-TEMPLATE.md"
MANIFEST_TPL_DST="$TARGET/.promotions/MANIFEST-TEMPLATE.md"
if [[ -f "$MANIFEST_TPL_SRC" ]]; then
  echo "==> Installing .promotions/MANIFEST-TEMPLATE.md"
  cp "$MANIFEST_TPL_SRC" "$MANIFEST_TPL_DST"
else
  echo "    WARN: $MANIFEST_TPL_SRC missing — manifest template NOT installed"
fi

# ----- .promotions/gen-index.py (self-contained generator copy) -----
# scripts/ is NOT a symlinked surface, so the workspace pre-commit needs a
# local copy to run `--check`. The generator imports its manifest parser
# from the symlinked mcp/ surface, so a copy stays DRY against noc.
GEN_SRC="$NOC_HOME/scripts/gen-promotions-index.py"
GEN_DST="$TARGET/.promotions/gen-index.py"
if [[ -f "$GEN_SRC" ]]; then
  echo "==> Installing .promotions/gen-index.py (PROMOTIONS.md generator)"
  cp "$GEN_SRC" "$GEN_DST"
  chmod +x "$GEN_DST"
else
  echo "    WARN: $GEN_SRC missing — promotions generator NOT installed"
fi

# ----- PROMOTIONS.md index (DERIVED — never hand-maintained) -----
# Generated from .promotions/*.md so the index can never drift from the
# manifest dir (the social-wiring-absorption W0.2 stale-index slip class).
echo "==> Generating PROMOTIONS.md (derived from .promotions/)"
if [[ -f "$GEN_SRC" ]]; then
  python3 "$GEN_SRC" --workspace "$TARGET" \
    || echo "    WARN: PROMOTIONS.md generation failed (non-fatal at bootstrap)"
fi

# ----- pre-commit hook -----
HOOK_SRC="$NOC_HOME/templates/seed-workspace-pre-commit.sh"
HOOK_DST="$TARGET/.githooks/pre-commit"
if [[ -f "$HOOK_SRC" ]]; then
  echo "==> Installing pre-commit hook"
  cp "$HOOK_SRC" "$HOOK_DST"
  chmod +x "$HOOK_DST"
else
  echo "    WARN: $HOOK_SRC missing — pre-commit hook NOT installed"
fi

# ----- docker artifacts -----
# Containers live at the workspace root so the user can boot the product
# online (`docker compose up`) right after `noctus.dev.scaffold_product`.
# These templates carry {{PRODUCT_SLUG}}/{{PRODUCT_NAME}}/{{BACKEND_PORT}}/
# {{FRONTEND_PORT}} placeholders; scaffold_product substitutes them in
# place after creating the product. Source of truth: KB §
# PATTERNS/seed-workspace.md § "Docker scaffolding".
DOCKER_SRC="$NOC_HOME/templates/seed-workspace-docker"
if [[ -d "$DOCKER_SRC" ]]; then
  echo "==> Installing docker templates (Dockerfile, Dockerfile.frontend,"
  echo "    docker-compose.yml, .dockerignore, .env.example, start.sh, stop.sh)"
  for f in Dockerfile Dockerfile.frontend docker-compose.yml .dockerignore .env.example start.sh stop.sh; do
    if [[ -f "$DOCKER_SRC/$f" && ! -f "$TARGET/$f" ]]; then
      cp "$DOCKER_SRC/$f" "$TARGET/$f"
      # start.sh + stop.sh need executable bit; cp does not preserve mode
      # reliably across filesystems.
      if [[ "$f" == "start.sh" || "$f" == "stop.sh" ]]; then
        chmod +x "$TARGET/$f"
      fi
    elif [[ -f "$TARGET/$f" ]]; then
      echo "    skip: $f already exists"
    fi
  done
else
  echo "    WARN: $DOCKER_SRC missing — docker templates NOT installed"
fi

# ----- README -----
README_SRC="$NOC_HOME/templates/seed-workspace-README.md"
README_DST="$TARGET/README.md"
if [[ -f "$README_SRC" && ! -f "$README_DST" ]]; then
  echo "==> Installing README (workspace conventions)"
  # Substitute placeholders.
  sed -e "s|{{WORKSPACE_NAME}}|$NAME|g" \
      -e "s|{{NOCTUSAI_HOME}}|$NOC_HOME|g" \
      -e "s|{{CREATED_AT}}|$(date -u +%Y-%m-%dT%H:%M:%SZ)|g" \
      "$README_SRC" > "$README_DST"
elif [[ -f "$README_DST" ]]; then
  echo "==> README.md already exists; not touching"
fi

# ----- git init + hook path -----
if [[ ! -d "$TARGET/.git" ]]; then
  echo "==> git init"
  (cd "$TARGET" && git init -q)
fi
echo "==> git config core.hooksPath .githooks"
(cd "$TARGET" && git config core.hooksPath .githooks)

# ----- summary -----
echo ""
echo "Bootstrap complete."
echo ""
echo "  Workspace:       $TARGET"
echo "  Name:            $NAME"
echo "  NoctusAI home:   $NOC_HOME"
echo "  Symlinked:       ${#SURFACES[@]} surfaces (CLAUDE.md, CLAUDE/, KNOWLEDGE-BASE/, .claude/, mcp/, seed/, templates/)"
echo "  Local:           projects/ sandbox/ products/ .promotions/ .noctusai-state/"
echo "  Pre-commit hook: $HOOK_DST  (Rule 1 + Rule 2 — see file header)"
echo "  Marker:          $TARGET/.noctusai-workspace"
echo ""
echo "READ-ONLY DEFENSE:"
echo "  Layer 1 (PRIMARY): pre-commit hook — refuses commits touching symlinked surfaces"
echo "  Layer 2 (AGENT):   KB § PATTERNS/seed-workspace.md + CLAUDE.md + agent memory"
echo "  Layer 3 (SYMBOLIC): chmod -h a-w on symlinks — works partially on Linux, no-op on macOS"
echo ""
echo "  See $TARGET/README.md for full conventions."
echo ""
