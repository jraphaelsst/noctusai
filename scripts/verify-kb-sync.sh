#!/usr/bin/env bash
#
# verify-kb-sync.sh
# Validates that CLAUDE.md pointers resolve to real files in KNOWLEDGE-BASE/
# and that KNOWLEDGE-BASE/INDEX.md lists every top-level KB doc file.
#
# Illustrative pointers using brace-alternation syntax `{a,b,c}.md` are skipped
# (they're meant for humans, not as literal paths).
#
# Directories excluded from the "must be indexed" check:
#   - SKILLS/     — skill definition artifacts, indexed collectively
#   - WORKFLOWS/  — workflow exports, indexed collectively
#   - MCP-SERVERS/ — MCP server defs, indexed collectively
#   - EVALS/      — eval cases, indexed collectively
#
# Exit codes:
#   0 — synced
#   1 — broken pointer in CLAUDE.md
#   2 — KB doc exists but is not referenced by INDEX.md
#
# Usage:
#   bash scripts/verify-kb-sync.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

CLAUDE_MD="CLAUDE.md"
KB_INDEX="KNOWLEDGE-BASE/INDEX.md"
KB_DIR="KNOWLEDGE-BASE"

red()    { printf '\033[31m%s\033[0m\n' "$*" >&2; }
yellow() { printf '\033[33m%s\033[0m\n' "$*" >&2; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }

errors=0
warnings=0

# ─── 1. CLAUDE.md + topical CLAUDE/*.md pointers resolve to real KB files
echo "Checking CLAUDE.md + CLAUDE/*.md pointers resolve to real KB files..."
# Build the list of router files to scan: CLAUDE.md + any CLAUDE/*.md sibling routers
# (introduced 2026-05-03 by `context-budget-overhaul` — topical CLAUDE/<topic>.md
# files load on-demand and reference KB anchors; their pointers must also resolve.)
router_files=("$CLAUDE_MD")
if [[ -d "CLAUDE" ]]; then
  while IFS= read -r f; do
    router_files+=("$f")
  done < <(find CLAUDE -maxdepth 2 -type f -name '*.md' | sort -u)
fi

while IFS= read -r path; do
  # Skip illustrative brace-alternation patterns
  if [[ "$path" == *"{"* ]]; then
    continue
  fi
  if [[ ! -f "$path" ]]; then
    red "  ✗ BROKEN: $path (referenced by a CLAUDE.md / CLAUDE/*.md router, not on disk)"
    errors=$((errors + 1))
  fi
done < <(grep -hoE '`KNOWLEDGE-BASE/[^`]+\.md`' "${router_files[@]}" 2>/dev/null | sed 's/`//g' | sort -u)

# ─── 2. Top-level KB docs are indexed in INDEX.md
echo "Checking all KB docs are indexed in $KB_INDEX..."
while IFS= read -r file; do
  if [[ "$file" == "$KB_INDEX" ]]; then continue; fi
  if [[ "$file" == "$KB_DIR/AGENT-CONTEXT.md" ]]; then continue; fi  # explicitly noted as prose
  # Skip collective subtrees
  case "$file" in
    "$KB_DIR/SKILLS/"*|"$KB_DIR/WORKFLOWS/"*|"$KB_DIR/MCP-SERVERS/"*|"$KB_DIR/EVALS/"*)
      continue ;;
  esac
  base="$(basename "$file")"
  if ! grep -q "$base" "$KB_INDEX" 2>/dev/null; then
    yellow "  ⚠ NOT INDEXED: $file"
    warnings=$((warnings + 1))
  fi
done < <(find "$KB_DIR" -type f -name '*.md' ! -path '*/.*' | sort -u)

# ─── 3. INDEX.md Layout tree reflects the filesystem
# Caught 2026-05-02 in methodology-extraction Phase 1: `logging.md` and
# `seed-lib-layout.md` were in the By-topic table but missing from the
# Layout tree (lines 13-66 of INDEX.md). The existing check #2 only
# requires the basename appear *somewhere* in INDEX.md, so the Layout-
# tree drift slipped through. This check is advisory (warnings only) —
# the Layout tree is human-readable scaffolding, not a hard index.
echo "Checking $KB_INDEX Layout tree reflects KB filesystem..."
layout_files=$(sed -n '/^## Layout/,/^---/p' "$KB_INDEX" | grep -oE '[A-Za-z0-9_-]+\.md' | sort -u)
while IFS= read -r file; do
  if [[ "$file" == "$KB_INDEX" ]]; then continue; fi
  case "$file" in
    "$KB_DIR/SKILLS/"*|"$KB_DIR/WORKFLOWS/"*|"$KB_DIR/MCP-SERVERS/"*|"$KB_DIR/EVALS/"*)
      continue ;;
  esac
  base="$(basename "$file")"
  if ! printf '%s\n' "$layout_files" | grep -qx "$base"; then
    yellow "  ⚠ NOT IN LAYOUT TREE: $file (visible in INDEX.md tables but missing from the Layout sketch)"
    warnings=$((warnings + 1))
  fi
done < <(find "$KB_DIR" -type f -name '*.md' ! -path '*/.*' | sort -u)

# ─── 4. Summary
echo ""
if [[ $errors -eq 0 && $warnings -eq 0 ]]; then
  green "✓ KB sync OK — all CLAUDE.md pointers resolve, all KB docs indexed, Layout tree current."
  exit 0
elif [[ $errors -gt 0 ]]; then
  red "✗ $errors broken pointer(s) in CLAUDE.md. Fix before commit."
  exit 1
else
  yellow "⚠ $warnings drift warning(s). Add to $KB_INDEX (Layout tree or topic tables as applicable)."
  exit 2
fi
