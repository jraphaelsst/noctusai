---
name: noc-ship
description: Use for the in-repo release/deploy gates — triggers "ship to main", "bless this", "merge to main", "promote to prod", "release", "deploy these changes", "deploy the latest", "redeploy", "pull the code to the VPS". `main` is production; everyday work lands on `dev`.
version: 1.0.0
---

# noc-ship — release · bless · promote · deploy

`main` = the blessed/shippable release line; production is the further `main → prod` promote the VPS tracks. NEVER push/merge to `main`/`prod` without explicit per-action consent. `dev` = integration branch (push your own work freely).

## Workflow

1. **Status first** — `noctus.dev.release stage=status` (read-only chain view: dev → main → prod).
2. **Bless** — `noctus.dev.release stage=bless` FFs `main` → `dev` tip. DRY-RUN by default; `confirm=true` to push. FF-only by construction; it is the ONLY sanctioned setter of `NOCTUS_ALLOW_MAIN_PUSH`.
3. **Promote** — `noctus.dev.release stage=promote` snapshots `prod` → `prod-backup` (rollback pointer) then FFs `prod` → a blessed `main` sha. `confirm=true` to push.
4. **Deliver to VPS** — code: `noctus.dev.deploy_pull` (§2a safe pull: inspect → ff-only → verify; never reset/checkout/clean on the VPS). Image model: `noctus.dev.deploy_image` (atomic GHCR pull + health-probe + auto-rollback).
5. **Pre-deploy gate** — `noctus.dev.predeploy_check` (D3 manifest + prod-config parity: catches present-but-localhost values the boot guard can't).

## Guardrails
- R4 human-gated: PRESENT {push cmd + range + evidence} → explicit user go → execute. Never auto-push `main`/`prod`.
- The slim prod image is structurally different (no start.sh/registry/node, baked dist, env-only config) — verify in the PRODUCTION SHAPE, not just dev-green (`noc` highest-recurrence drift class).
- Prod services sit behind the CF tunnel ⇒ any programmatic caller needs a browser User-Agent (1010 WAF). SSO verify: `noctus.dev.sso_smoke`.

## Depth
`KB § PATTERNS/architect/branching-and-merging.md §0.2` · `KB § GUIDES/production-deploy.md` (+ §2a safe pull) · `KB § PATTERNS/devops/dev-prod-parity.md`.
