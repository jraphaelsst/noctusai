# Disposition — 20260419-014952-mailing eval folder

**Triaged:** 2026-05-11 by Engineer MAI-P2 during `mailing-wiring` Phase 2 stale-proposal review.
**Originating context:** induced compliance evaluation 2026-04-19; see `comparison.md` §4 ("keep both files as eval artifact").

## Triage table

| File | Proposal | Current state in main | Disposition |
|---|---|---|---|
| `openai-gpt-4o-mini-20260419-015001-remove-custom-health-endpoint-in-mailing-product.md` | Remove custom `app/routers/health.py` | No such file exists; `app/main.py:41` mounts `standard_routers=["health", "notificacoes", "team", "ai_outputs", "ai_feedback"]` via `create_product_app()` | **APPLIED-elsewhere** (seed framework solution) |
| `claude-opus-4-7-20260419-015135-remove-product-level-health.py-in-mailing-—-delega.md` | Same as above, with full diff-before-delete + risk-categorization rigor | Same — `app/main.py:41` framework mount | **APPLIED-elsewhere** (seed framework solution) |
| `comparison.md` | Authoring-path evaluation reference | N/A — methodology artifact | **KEEP** as worked-example reference (per comparison.md §4 + cross-reference value for future authoring decisions) |
| `issues.json` | Induced compliance issue input | N/A — eval scaffold | **KEEP** as eval-scaffold artifact |

## Verification commands

```bash
# Confirm no product-level health.py
ls products/mailing/backend/app/routers/health.py 2>&1   # → "No such file or directory"

# Confirm seed framework health mount
grep -n 'standard_routers' products/mailing/backend/app/main.py
# → standard_routers=["health", "notificacoes", "team", "ai_outputs", "ai_feedback"]
```

## Rationale

The recommended action in both proposals ("remove `health.py`, rely on framework router") was already the resolved state — the file never existed in this main-branch slice. The proposals predate the `create_product_app(..., standard_routers=[...])` pattern's canonical adoption (which mounts the seed health router declaratively). Per the `KB § PATTERNS/accept-with-rationale.md` triage convention, the right disposition is "FORMALIZED-elsewhere" (the seed pattern absorbed the fix at the platform level).

The eval folder remains intact as a methodology reference for the agent-vs-headless authoring comparison documented in `comparison.md` — exactly as that file's §4 recommends.

**Status flips:** both proposals → APPLIED-elsewhere (resolved by seed pattern; no action required).
