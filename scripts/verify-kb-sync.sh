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

# ─── 1. CLAUDE.md pointers resolve to real KB files
echo "Checking CLAUDE.md pointers resolve to real KB files..."
while IFS= read -r path; do
  # Skip illustrative brace-alternation patterns
  if [[ "$path" == *"{"* ]]; then
    continue
  fi
  if [[ ! -f "$path" ]]; then
    red "  ✗ BROKEN: $path (referenced in CLAUDE.md, not on disk)"
    errors=$((errors + 1))
  fi
done < <(grep -oE '`KNOWLEDGE-BASE/[^`]+\.md`' "$CLAUDE_MD" 2>/dev/null | sed 's/`//g' | sort -u)

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

# ─── 3. Summary
echo ""
if [[ $errors -eq 0 && $warnings -eq 0 ]]; then
  green "✓ KB sync OK — all CLAUDE.md pointers resolve, all KB docs indexed."
  exit 0
elif [[ $errors -gt 0 ]]; then
  red "✗ $errors broken pointer(s) in CLAUDE.md. Fix before commit."
  exit 1
else
  yellow "⚠ $warnings KB doc(s) not indexed. Add to $KB_INDEX."
  exit 2
fi
