#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────
# Register EVERY custom git merge driver that .gitattributes maps.
#
# `.gitattributes` (committed) only NAMES a driver (`merge=kb-counts`); the
# driver BODY is per-repo git config, which is never committed. A checkout that
# has not run this script treats the attribute as an undefined driver → plain
# text merge → conflict on pure machine churn. Two callers need it:
#   * scripts/hooks/install-hooks.sh  (developer clones)
#   * .github/workflows/merge-queue.yml (the runner; before this existed, the
#     2026-11-05 incident ejected 4 queue entries on 02-LANDSCAPE.md conflicts)
# Idempotent. Usage: register-merge-drivers.sh [REPO_ROOT]   (default: cwd's toplevel)
# KB § PATTERNS/common/auto-generated-merge-drivers.md
# ──────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="${1:-$(git rev-parse --show-toplevel)}"
REPO_ROOT="$(cd "$REPO_ROOT" && pwd)"
HOOKS="$REPO_ROOT/scripts/hooks"

reg() { # name, description, script
    chmod +x "$HOOKS/$3"
    git -C "$REPO_ROOT" config "merge.$1.name" "$2"
    git -C "$REPO_ROOT" config "merge.$1.driver" "$HOOKS/$3 %O %A %B %P"
    echo "  merge driver: $1"
}

reg kb-counts "regenerate auto-derived kb-counts blocks; surface real prose conflicts" merge-kb-counts.sh
reg lgpd-warnings "entry-aware merge of LGPD-WARNINGS.md (keeps both sides' entries)" merge-lgpd-warnings.sh
reg gate-inventory "3-way merge of gate-alignment-inventory.json (gates union, decision ids renumbered on collision)" merge-gate-inventory.sh
