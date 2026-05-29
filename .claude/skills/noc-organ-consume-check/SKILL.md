---
name: noc-organ-consume-check
description: Check the canonical organ catalog before building any FE component; prevent silent re-forks of validated seed organs.
triggers:
  - "before scaffolding a product"
  - "is this component canonical"
  - "should I import this from seed"
  - "build a new component"
  - "create a new FE component"
  - "add a component to frontend"
---

# Skill: noc-organ-consume-check

> **Auto-trigger phrases:** "before scaffolding a product", "is this component canonical", "should I import this from seed", "build a new component", "create a new FE component", "add a component to frontend"

---

## Procedure

**Goal:** prevent silent re-forks of canonical organs by checking the catalog FIRST.

### Step 1 — Query the catalog

Run `noctus.dev.find_reusable_component "<intent>"` before writing any new FE component.

```
noctus.dev.find_reusable_component "credentials list with multi-account selector"
noctus.dev.find_reusable_component "login form with email and password"
noctus.dev.find_reusable_component "resource CRUD table with filters"
```

The tool embeds the query → cosine-top-K over `code-embeddings.sqlite WHERE chunk_kind='organ'` → returns matches with `validation_status`, `seed_path`, and `wiring_snippet`.

### Step 2 — Evaluate the match

| Outcome | Action |
|---|---|
| Match with `validation_status: validated` | **Consume it.** Import from the `seed_path`. If product-specific behavior needed, declare named-seam: `// @consumes-organ <Name>@<ver> +seam=<kind>`. |
| Match with `validation_status: emerging` | **Prefer consumption.** Emerging organs may have known gaps — check `known_facts` in the organ bundle. If the gap affects the use case, build local + register the gap. |
| Match with `validation_status: shelfware` | **Local build OK.** Shelfware organs are not production-hardened. Build local; if the local build validates, register it as a new organ via `noctus.dev.component_bundle`. |
| No match (zero results or low cosine) | **Build local** — but log the gap: surface `"no canonical organ found for <intent>"` in your delivery note so the tech-lead can decide whether to register the new component. |

### Step 3 — Declare the seam (if extending)

If consuming a canonical organ but adding product-specific behavior, add to the top of the wrapper file:

```tsx
// @consumes-organ LoginForm@1.0 +seam=data-binding
// Extends the canonical LoginForm with product-specific auth error handling.
import { LoginForm } from "@noctusai/lib/components/auth/LoginForm";
```

### Step 4 — Verify no silent fork exists

Before finishing, run the keeper:

```bash
python mcp/noctusai/cli.py --check-canonical-organ-consumption
```

A `high` finding means a local re-declaration without the declaration header was detected. Fix before committing.

---

## Why this exists

The platform reached 95% canonical organ consumption organically (architect Phase 2 scout, 2026-05-29). This skill LOCKS that discipline so the next scaffolded product doesn't restart the replication cycle.

→ `KB § PATTERNS/architect/products-consume-canonical-organs.md`
→ `KB § PATTERNS/architect/seed-organ-canonical-set.md`
