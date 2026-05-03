#!/usr/bin/env bash
# Template-workspace pre-commit hook.
#
# Installed at <workspace>/.githooks/pre-commit by bootstrap-template-workspace.sh.
# Activated via `git config core.hooksPath .githooks` (also set by bootstrap).
#
# Two enforcement rules — both run on every staged path. A single violation
# refuses the commit with a clear message citing the rule. Use `git commit
# --no-verify` only when you genuinely need to bypass (rare; the hook is
# the primary defense for "templates cannot modify noc").
#
#   Rule 1 — read-only re: noc.
#     Refuse any staged path that resolves through a symlinked surface
#     (CLAUDE.md, CLAUDE/, KNOWLEDGE-BASE/, .claude/, mcp/, seed/,
#     noctusai_lib/, templates/). Edits to these belong in noc itself,
#     not template.
#
#   Rule 2 — separated additions are explicit.
#     Refuse any newly added path under products/, projects/, or the
#     workspace root that doesn't have a matching .promotions/<slug>.md
#     entry staged in the same commit. Sandbox/ is the carve-out for
#     genuine throwaway.
#
# See KNOWLEDGE-BASE/CONTEXT/PATTERNS/template-workspace.md for the design.

set -euo pipefail

WORKSPACE_ROOT="$(git rev-parse --show-toplevel)"
MARKER="$WORKSPACE_ROOT/.noctusai-workspace"

# If the marker is missing, this hook isn't running in a noctusai template
# workspace. Skip silently — the hook may have been copied into the wrong
# repo by accident.
if [[ ! -f "$MARKER" ]]; then
  exit 0
fi

# Only enforce in template workspaces, not in primary noc.
WORKSPACE_KIND="$(grep -E '^workspace_kind=' "$MARKER" | cut -d= -f2- | tr -d '[:space:]' || true)"
if [[ "$WORKSPACE_KIND" != "template" ]]; then
  exit 0
fi

# Set of surface paths that are symlinks to noc — first-level only.
# Walking up parents catches nested writes (e.g. KNOWLEDGE-BASE/CONTEXT/...).
SYMLINKED_SURFACES=(
  "CLAUDE.md"
  "CLAUDE"
  "KNOWLEDGE-BASE"
  ".claude"
  "mcp"
  "seed"
  "noctusai_lib"
  "templates"
)

violations_symlink=()
violations_promotion=()

# Get the staged paths (added/modified/renamed) — ignore deletions for
# rule 1 (deleting a tracked symlink would be the user removing a surface
# from the workspace, not modifying noc) but enforce rule 2 on adds.
# Portable to bash 3.2 (macOS default — no mapfile builtin) via while-read loop.
STAGED_ALL=()
while IFS= read -r _line; do
  [[ -n "$_line" ]] && STAGED_ALL+=("$_line")
done < <(git diff --cached --name-only --diff-filter=ACMR)
STAGED_ADDED=()
while IFS= read -r _line; do
  [[ -n "$_line" ]] && STAGED_ADDED+=("$_line")
done < <(git diff --cached --name-only --diff-filter=A)

for path in "${STAGED_ALL[@]}"; do
  # Rule 1 — does the path resolve through a symlinked surface?
  for surface in "${SYMLINKED_SURFACES[@]}"; do
    if [[ "$path" == "$surface" || "$path" == "$surface/"* ]]; then
      violations_symlink+=("$path  (resolves through symlinked surface: $surface)")
      break
    fi
  done
done

# Rule 2 — every added file outside sandbox/ + .promotions/ + .noctusai-state/ + the
# workspace root metadata files needs a matching .promotions/<slug>.md
# entry. The slug match is loose: if any .promotions/*.md is staged in this
# commit, we accept it as covering any addition. (A stricter shape would
# parse the manifest's `origin` field; deferred to Phase 4 of project.)
PROMOTION_STAGED=false
for path in "${STAGED_ALL[@]}"; do
  if [[ "$path" == .promotions/*.md ]]; then
    PROMOTION_STAGED=true
    break
  fi
done

# Workspace-root metadata files exempt from rule 2.
ROOT_METADATA=(
  ".gitignore"
  "README.md"
  "PROMOTIONS.md"
  ".env"
)

for path in "${STAGED_ADDED[@]}"; do
  # Skip files exempt from rule 2.
  is_metadata=false
  for meta in "${ROOT_METADATA[@]}"; do
    if [[ "$path" == "$meta" ]]; then
      is_metadata=true
      break
    fi
  done
  $is_metadata && continue

  # Skip sandbox additions — explicit carve-out.
  [[ "$path" == sandbox/* ]] && continue
  # Skip .promotions/ entries themselves.
  [[ "$path" == .promotions/* ]] && continue
  # Skip .noctusai-state/ — gitignored anyway, but defensive.
  [[ "$path" == .noctusai-state/* ]] && continue
  # Skip rule-1 violators — they get a clearer error from rule 1.
  is_symlink_violation=false
  for surface in "${SYMLINKED_SURFACES[@]}"; do
    if [[ "$path" == "$surface" || "$path" == "$surface/"* ]]; then
      is_symlink_violation=true
      break
    fi
  done
  $is_symlink_violation && continue

  # The remaining additions need a .promotions/ entry.
  if ! $PROMOTION_STAGED; then
    violations_promotion+=("$path  (no .promotions/ entry staged in this commit)")
  fi
done

# Report + refuse.
if [[ ${#violations_symlink[@]} -gt 0 || ${#violations_promotion[@]} -gt 0 ]]; then
  echo ""
  echo "REFUSED: template-workspace pre-commit hook"
  echo ""
  if [[ ${#violations_symlink[@]} -gt 0 ]]; then
    echo "Rule 1 — read-only re: noc — VIOLATED:"
    for v in "${violations_symlink[@]}"; do
      echo "  - $v"
    done
    echo ""
    echo "  Edits to these surfaces belong in noc itself, not template."
    echo "  Templates strictly cannot modify noc — see"
    echo "  KNOWLEDGE-BASE/CONTEXT/PATTERNS/template-workspace.md."
    echo ""
  fi
  if [[ ${#violations_promotion[@]} -gt 0 ]]; then
    echo "Rule 2 — separated additions are explicit — VIOLATED:"
    for v in "${violations_promotion[@]}"; do
      echo "  - $v"
    done
    echo ""
    echo "  Every non-sandbox addition needs a matching .promotions/<slug>.md"
    echo "  entry staged in the same commit, OR the file should live under"
    echo "  sandbox/ (the throwaway carve-out)."
    echo "  See KNOWLEDGE-BASE/CONTEXT/PATTERNS/template-workspace.md § Promotion manifest."
    echo ""
  fi
  echo "  Bypass with 'git commit --no-verify' only when genuinely necessary."
  echo ""
  exit 1
fi

exit 0
