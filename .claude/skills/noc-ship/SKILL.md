---
name: noc-ship
description: Use for the in-repo release/deploy gates — triggers "ship to main", "bless this", "merge to main", "promote to prod", "release", "deploy these changes", "deploy the latest", "redeploy", "pull the code to the VPS". `main` is production; everyday work lands on `dev`.
version: 1.1.0
---

# noc-ship — release · bless · promote · deploy

`main` = the blessed/shippable release line; production is the further `main → prod` promote the VPS tracks. NEVER push/merge to `main`/`prod` without explicit per-action consent. `dev` = integration branch (push your own work freely).

## Workflow

0. **🔴 Dev-validate FIRST (the gate — prod-deploy is a PROMOTION of a dev-validated build, never first-contact).** Before any bless: (a) the change must be RUNNING on the dev fleet — `./start.sh <slug>` (add `build` only when deps/Dockerfile changed; else a `docker restart dev-noctus-<slug>` lets its bind-mounted `vite --watch` + `uvicorn --reload` pick up the synced source); (b) **functional smoke** — `noctus.dev.smoke_fleet` + hit the actually-changed route/endpoint on `localhost:<port>`; (c) keepers green — `noctus.dev.predeploy_check <slug>`. Only a GREEN dev fleet (functional ∧ keepers) earns the bless. We work mainly on `dev`; deploying to `dev` ≠ deploying to prod, but deploying to prod REQUIRES a validated dev first. **Hygiene:** after worktree integrates, FF the PRIMARY checkout to `origin/dev` (`git merge --ff-only origin/dev`) so its bind-mount + active hooks reflect dev — else the dev fleet serves STALE code (the 2026-06-01 trap: deployed straight to prod off a dev fleet running old source). → `KB § GUIDES/production-deploy.md § 0.1`.
1. **Status first** — `noctus.dev.release stage=status` (read-only chain view: dev → main → prod).
2. **Bless** — `noctus.dev.release stage=bless` FFs `main` → `dev` tip. DRY-RUN by default; `confirm=true` to push. FF-only by construction; it is the ONLY sanctioned setter of `NOCTUS_ALLOW_MAIN_PUSH`.
3. **Promote** — `noctus.dev.release stage=promote` snapshots `prod` → `prod-backup` (rollback pointer) then FFs `prod` → a blessed `main` sha. `confirm=true` to push.
4. **Deliver to VPS** — code: `noctus.dev.deploy_pull` (§2a safe pull: inspect → ff-only → verify; never reset/checkout/clean on the VPS). Image model: `noctus.dev.deploy_image` (atomic GHCR pull + health-probe + auto-rollback).
5. **Pre-deploy gate** — `noctus.dev.predeploy_check` (D3 manifest + prod-config parity: catches present-but-localhost values the boot guard can't).

## Guardrails
- R4 human-gated: PRESENT {push cmd + range + evidence} → explicit user go → execute. Never auto-push `main`/`prod`.
- The slim prod image is structurally different (no start.sh/registry/node, baked dist, env-only config) — verify in the PRODUCTION SHAPE, not just dev-green (`noc` highest-recurrence drift class).
- Prod services sit behind the CF tunnel ⇒ any programmatic caller needs a browser User-Agent (1010 WAF). SSO verify: `noctus.dev.sso_smoke`.
- **Prod-exposure precheck** — before promote, `python mcp/noctusai/cli.py --check-prod-exposure-consent` (should already be clean; the pre-commit gate refuses an un-consented product registration at commit time). Bless/promote is a whole-repo-state decision — it is NEVER a per-product "should this be public" decision, and an agent MUST NOT author `deploy/consent/*.prod.yml` on the user's behalf. → `KB § PATTERNS/devops/prod-exposure-consent.md`.

## Depth
`KB § PATTERNS/architect/branching-and-merging.md §0.2` · `KB § GUIDES/production-deploy.md` (+ §2a safe pull) · `KB § PATTERNS/devops/dev-prod-parity.md` · `KB § PATTERNS/devops/prod-exposure-consent.md`.
