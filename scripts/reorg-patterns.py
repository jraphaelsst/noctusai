#!/usr/bin/env python3
"""One-shot reorg script: relocate KB/PATTERNS/*.md into per-owner subfolders +
bulk-update every `PATTERNS/<basename>.md` reference across the tree.

Per the design in `KB § PATTERNS/agent-context-architecture.md` and the user's
mandate: organize the patterns folder by agents and common-ground separately.

Mirrors `KB § PATTERNS/lossless-doc-refactor.md`:
  - Pointer-set: every `PATTERNS/<old>` → `PATTERNS/<owner>/<old>` (no loss).
  - Rule/section: file contents untouched (only PATHS change).
  - Line-structure: only the path-substring inside lines changes.
  - Hook-grade diff: `noctus.dev.kb_sync` is the post-condition gate.

This script is intentionally one-shot — it runs once for the reorg, then the
keeper `check_agent_kb_alignment` enforces alignment from then on. After the
commit lands, this script can be removed in a follow-up (it's not a recurring
tool, so it doesn't belong as a `noctus.dev.*` MCP tool per
KB § PATTERNS/mcp-first-scripts.md §3 — one-shot migration carve-out).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PATTERNS_DIR = REPO_ROOT / "KNOWLEDGE-BASE" / "CONTEXT" / "PATTERNS"

# Mapping: basename → subfolder. Mirrors the owns_kb declarations in the agent
# files + the unowned-allowlist in compliance.py.
MAPPING: dict[str, str] = {
    # ── common/ — universal patterns (every agent uses; no single owner) ───
    "absorption-ships-consume-docs.md":      "common",
    "accept-with-rationale.md":              "common",
    "agent-context-architecture.md":         "common",
    "agent-reading-discipline.md":           "common",
    "ast.md":                                "common",
    "branching.md":                          "common",
    "claude-md-router-discipline.md":        "common",
    "defer-is-not-resolve.md":               "common",
    "doc-symbology.md":                      "common",
    "drift-fix-on-contact.md":               "common",
    "harness-overlay-worktree-divergence.md":"common",
    "keeper-check-before-docing.md":         "common",
    "keeper-pattern-cache.md":               "common",
    "lossless-doc-refactor.md":              "common",
    "methodology-codification-pipeline.md":  "common",
    "minimum-viable-rebuild.md":             "common",
    "persistent-files-absorption.md":        "common",
    "phased-push-policy.md":                 "common",
    "proposals-and-improvements.md":         "common",
    "remediation-markers.md":                "common",
    "scoped-auto-improvement.md":            "common",
    "self-branching-mode.md":                "common",
    "storage-hygiene.md":                    "common",
    "verify-seed-on-fork-base.md":           "common",
    # ── architect/ — methodology meta + orchestration ───────────────────────
    "absorbed-product-seed-shape-seam.md":   "architect",
    "autonomous-operator-via-subagent.md":   "architect",
    "branching-and-merging.md":              "architect",
    "branching-dispatch.md":                 "architect",
    "dev-team.md":                           "architect",
    "dev-toolkit-scaffolders.md":            "architect",
    "dispatch-engineer-tuning.md":           "architect",
    "master-tree-parallel-batches.md":       "architect",
    "mcp-first-scripts.md":                  "architect",
    "mcp-tool-conventions.md":               "architect",
    "noc-graph.md":                          "architect",
    "parallelization-first-orchestration.md":"architect",
    "project-execution.md":                  "architect",
    "seed-absorption.md":                    "architect",
    "seed-canonical-defaults.md":            "architect",
    "seed-lib-layout.md":                    "architect",
    "seed-workspace.md":                     "architect",
    "shared-library-conventions.md":         "architect",
    "two-session-architect-operator.md":     "architect",
    # ── backend/ — backend-engineer ─────────────────────────────────────────
    "backend.md":                            "backend",
    "boundary-contract-tests.md":            "backend",
    "chatbot-operational-readiness.md":      "backend",
    "database-rls.md":                       "backend",
    "di-test-seam.md":                       "backend",
    "digest-seed.md":                        "backend",
    "llm-tool-audit.md":                     "backend",
    "llm-usage.md":                          "backend",
    "logging-at-except.md":                  "backend",
    "logging.md":                            "backend",
    "metas-seed.md":                         "backend",
    "notifications.md":                      "backend",
    "pydantic-strict-http.md":               "backend",
    "scheduling-seed.md":                    "backend",
    "seed-fake-real-adapter.md":             "backend",
    "whatsapp-chatbot-seed.md":              "backend",
    # ── frontend/ — frontend-engineer ───────────────────────────────────────
    "core-url-routing.md":                   "frontend",
    "frontend.md":                           "frontend",
    "product-icon-registry.md":              "frontend",
    "product-internal-wiring.md":            "frontend",
    "svg-render-mode.md":                    "frontend",
    # ── devops/ — devops-engineer ───────────────────────────────────────────
    "base-image-dep-freshness.md":           "devops",
    "ci-security-gates.md":                  "devops",
    "container-sanitization.md":             "devops",
    "containerization-operations.md":        "devops",
    "containerization.md":                   "devops",
    "deploy-config-contract.md":             "devops",
    "dev-prod-parity.md":                    "devops",
    "environment.md":                        "devops",
    # ── security/ — security advisor ────────────────────────────────────────
    "lgpd.md":                               "security",
    "llm-bot-security.md":                   "security",
    "webhook-signatures.md":                 "security",
    # ── compliance/ — compliance-reviewer ───────────────────────────────────
    "compliance-regression-baseline.md":     "compliance",
    "testing.md":                            "compliance",
}


def main() -> int:
    # 1. Verify mapping covers every file in PATTERNS/.
    actual = {p.name for p in PATTERNS_DIR.iterdir() if p.is_file() and p.suffix == ".md"}
    mapped = set(MAPPING.keys())
    missing = actual - mapped
    extra = mapped - actual
    if missing or extra:
        print(f"❌ Mapping mismatch — missing: {missing}, extra: {extra}", file=sys.stderr)
        return 1
    print(f"✓ Mapping covers all {len(actual)} files in PATTERNS/")

    # 2. Create subfolders + git mv.
    for basename, sub in MAPPING.items():
        target_dir = PATTERNS_DIR / sub
        target_dir.mkdir(parents=True, exist_ok=True)
        src = PATTERNS_DIR / basename
        dst = target_dir / basename
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "mv", str(src.relative_to(REPO_ROOT)), str(dst.relative_to(REPO_ROOT))],
            check=True,
        )
    print(f"✓ Moved {len(MAPPING)} files into subfolders")

    # 3. Bulk-update every reference. Scan every committed text file + key
    # roots. We use a precise substring match: `PATTERNS/<basename>` →
    # `PATTERNS/<sub>/<basename>`. This works for both `KB § PATTERNS/<x>`
    # and `CONTEXT/PATTERNS/<x>` forms (both contain `PATTERNS/<x>` as
    # substring).
    scan_roots = [
        REPO_ROOT / "CLAUDE.md",
        REPO_ROOT / "CONTEXTUALIZE.md",
        REPO_ROOT / "CLAUDE",
        REPO_ROOT / "KNOWLEDGE-BASE",
        REPO_ROOT / ".claude" / "agents",
        REPO_ROOT / ".claude" / "skills",
        REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "compliance.py",
        REPO_ROOT / "mcp" / "noctusai" / "tests",
    ]
    target_files: list[Path] = []
    for root in scan_roots:
        if root.is_file():
            target_files.append(root)
        elif root.is_dir():
            target_files.extend(p for p in root.rglob("*") if p.is_file() and p.suffix in {".md", ".py", ".json", ".yml", ".yaml"})

    total_updates = 0
    files_changed = 0
    for path in target_files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        original = text
        for basename, sub in MAPPING.items():
            # Only match the bare `PATTERNS/<basename>` (not already-relocated
            # `PATTERNS/<sub>/<basename>`).
            old = f"PATTERNS/{basename}"
            new = f"PATTERNS/{sub}/{basename}"
            # Guard: skip if the substring is ALREADY in its new form (so we
            # don't re-prepend).
            if new in text:
                # Already-updated occurrence won't be re-mangled — the regex
                # below uses negative-lookbehind to skip them.
                pass
            # Negative-lookbehind: don't match if already prefixed with one
            # of our known subfolders. Build the pattern once per basename.
            pattern = re.compile(
                rf"(?<![/\w-])PATTERNS/{re.escape(basename)}"
            )
            matches = pattern.findall(text)
            if matches:
                text = pattern.sub(new, text)
                total_updates += len(matches)
        if text != original:
            path.write_text(text, encoding="utf-8")
            files_changed += 1
    print(f"✓ Bulk-updated {total_updates} pointer occurrence(s) across {files_changed} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
