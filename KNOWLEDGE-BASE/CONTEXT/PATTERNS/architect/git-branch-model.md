# Git branch model — current phase + the methodology/prod-code separation roadmap

**What this is.** The mental model for *what each branch MEANS* and *when/how* to move code across them — and the deliberate PHASING of that model while the development methodology itself is still maturing. The mechanical "how to branch/merge/FF" lives in [[branching]] + [[branching-and-merging]]; THIS doc is the *why each ref exists* + the *roadmap* for separating methodology from prod code. User-ratified 2026-06-01.

## The refs
| Ref | Today's meaning | Mindset |
|---|---|---|
| `dev` (+ under-dev `feat/*` worktrees) | **Development isolation.** ALL work happens here; isolate each task in a worktree off `origin/dev`, integrate clean. | Never develop on a shared HEAD; never on `main`/`prod`. The only branch you push routine work to. |
| `main` | **The blessed GLOBAL-repo-scope line** — EVERYTHING that's validated: methodology (hooks/keepers/KB/skills/CI) **AND** prod code, as ONE coherent blessed state. | Bless `dev`→`main` means "this whole repo state is dev-validated." Methodology-only changes get blessed here too (see below). |
| `prod` (+ `prod-backup`) | **Production refs + rollback snapshot.** TODAY they carry the *same* blessed content as `main` (methodology + code) — as EXTRA safety-net layers while the dev methodology is still being hardened. `prod-backup` = the pre-promote snapshot for instant rollback. | Advanced ONLY by the promote ritual ([[branching-and-merging]] §2b). Never develop on them. They are nets, not workspaces. |

## Why methodology changes get blessed to `main` even though they never run in prod containers
The prod containers run the product apps — NOT the pre-commit hooks, keepers, KB, skills, or CI workflows. So a methodology change has **no prod-runtime effect** and needs **no container redeploy**. But it MUST still be blessed `dev`→`main` (→`prod`): the point of the phase we're in is to **preserve methodology + prod code together as one blessed, recoverable state**, with `prod` + `prod-backup` as extra safety layers *while the development methodology itself is still being made safe*. Blessing-without-redeploy is normal and correct: a methodology-only promote moves the git refs; only a **prod-code** change triggers the `deploy_pull`→`deploy_image` runtime rollout (gated by the [[fe-be-contract-first-dispatch]] / dev-deploy validation gate — `KB § GUIDES/production-deploy.md § 0.1`).

## The roadmap — current phase → target phase
- **NOW (unified):** `main` = global repo scope (methodology + prod code); `prod`/`prod-backup` = the same content as extra safety nets. We are NOT separating methodology from prod code yet — the methodology is still under active development and the extra net is worth more than the separation.
- **TARGET (once the methodology is "round"):** separate the concerns — `main` stays the global-repo-scope line; **`prod` carries PROD CODE ONLY** (+ its backup) — the dev-tooling/methodology surfaces drop out of `prod`; `dev` (+ under-dev branches) stays development isolation. The trigger to flip is "the development methodology is stable enough that the extra prod safety-net layer is no longer earning its keep."
- **Until that flip:** treat `prod` as "blessed-everything + rollback," not "prod-code-only." Do not hand-separate codes; just keep the chain `dev → main → prod` moving as one.

## The flow (per-change mindset)
1. Develop on a `feat/*` worktree off `origin/dev` → integrate to `dev`.
2. **Dev-validate** (the gate): deploy on the dev fleet + smoke + keepers green (`KB § GUIDES/production-deploy.md § 0.1`).
3. **Bless** `dev`→`main` (validated global-repo state).
4. **Promote** `main`→`prod` (snapshots `prod-backup` first).
5. **Deploy** `prod`→VPS — `deploy_pull`(+`deploy_image`) — ONLY when prod CODE changed; a methodology-only promote stops at step 4 (refs current, no rollout).

## Composes with
[[branching]] (the unified primitive) · [[branching-and-merging]] (§0 sacred-main + §2b promote ritual) · [[fe-be-contract-first-dispatch]] + `KB § GUIDES/production-deploy.md § 0.1` (the dev-validation gate) · [[self-branching-mode]] (never on `dev`).
