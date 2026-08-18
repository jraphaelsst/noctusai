# The dev fleet is DORMANT — prod-only, until we need it again

**Status: DORMANT since 2026-08-11. Reversible by design. Not deleted.**

This is a standing decision by the platform owner, not an agent's inference.
Read it before you reach for `./start.sh`, before you write a gate that
requires a dev container, and before you "helpfully" restore anything.

---

## The decision, in the owner's own framing

> "the platform has grown so much that the dev environment is requiring
> investment in storage that the prod environment (which is the public one,
> the one that i can actually profit from) is loose. let's work only on prod,
> widen the safety net for prod environment, so we dont need dev environment
> for now. […] Final decision. Prod only from now on. […] It was an
> overengineering setup by me at the end of our dev method development."

Two things follow from that, and only those two. **Do not generalize further.**

---

## 🔴 WHAT IS DORMANT — and what emphatically is NOT

| | status |
|---|---|
| the local Docker **dev fleet** — `dev-noctus-*` containers, their images, anonymous volumes, build cache | **DORMANT** |
| `./start.sh <slug>` as a routine step | **not used** |
| the **`dev` git branch** | 🔴 **FULLY ALIVE — unchanged** |
| self-branching: worktree off `origin/dev` → integrate to `dev` | 🔴 **unchanged** |
| `dev` → `main` (bless) → `prod` (promote) chain | 🔴 **unchanged** |
| the shared Supabase project, its schemas + RLS | 🔴 **unchanged** (never was "the dev environment") |

**The word "dev" means two different things in this repo and only one of them
is dormant.** The suspended thing is a set of *containers on a laptop*. The
`dev` *branch* costs zero storage, is the integration point the entire
branching methodology is built on, and is untouched. An agent that reads
"dev is deactivated" and starts committing to `main` has misread this page and
will be refused by `check_primary_checkout_commit` anyway.

Nothing was stopped, pruned, or deleted when this landed — explicitly:
*"dont do anything to dev environment right now."* The containers were left
running exactly as they were. They will age out naturally.

---

## What we LOSE, stated plainly

The old `noc-ship` §0 gate was: **the change must be RUNNING on the dev fleet
before it can be blessed** — functional smoke against real containers, on the
real image shape, before prod ever sees it. That gate is gone. Pretending
otherwise is the dangerous move here, so name the loss:

- no pre-prod **runtime** check that a container actually boots
- no pre-prod check of container-only wiring (bind-mounts, anon volumes,
  entrypoints, inter-container DNS)
- **prod is now first-contact for the running image**

That last line is the whole risk. Everything below exists to cover it.

---

## The widened prod safety net (the compensating controls)

Each of these already existed; what changes is that they are now **mandatory
and load-bearing** rather than belt-and-braces.

**1. `predeploy_check <slug>` — MANDATORY, per active product.**
Runs on the host, not in a container: framework-dep parity, a REAL `vite
build`, the backend pytest suite, the D3 gitignored-manifest assertion, and
prod-config value parity (catches present-but-localhost). This is now the
primary functional evidence.

**2. CI green on the exact sha — MANDATORY, no longer advisory.**
Previously a dev-fleet smoke could stand in for a red or pending CI. It
cannot now. If CI has not gone green on the commit being blessed, do not
bless. The one admissible exception is a commit whose entire diff is
`project-history/` or docs — prove it with `git diff --name-only` and say so
out loud.

**3. `deploy_image` — the real net.** Atomic GHCR pull + `up -d` + health
probe, with **automatic rollback to the `:previous` snapshot on a failed
probe**. This is what makes prod-first defensible at all: a broken image
never stays serving. It also carries the PROD-PIN ancestry guard, which
refuses a `:latest` whose baked revision is not an ancestor of `origin/prod`.
Since 2026-08-13 it also SWAP-VERIFIES: a healthy probe alone never proved
the recreate landed (a healthy *old* container satisfies it identically), so
after a healthy probe it re-inspects the RUNNING container's own image id +
revision label and refuses `status='deployed'` — reports `swap_unverified`
instead, no auto-rollback — unless both verifiably match. That self-check
still dies with the process if the tool times out, which is exactly why
point 3a exists.

**3a. `noctus.dev.deploy_verify` — the INDEPENDENT witness, MANDATORY.** The
2026-08-13 incident: `deploy_image` timed out and the MCP server
disconnected before reporting anything; every git-level signal (`prod`'s
tip, `deploy_pull`'s own success) stayed green throughout, and only a
manual `docker inspect` caught that the container was still on the
*previous* revision. `deploy_verify` closes that hole — it has **zero
dependency on `deploy_image` having run, succeeded, or even existed in this
process**: it re-derives the expected sha FRESH from `origin/prod` (never a
caller-supplied parameter — a wrong answer there would defeat the whole
point) and reads each ACTIVE product's running container's
`org.opencontainers.image.revision` label directly. `status='verified'`
(exit 0) is the only pass. **A `deploy_image` call that times out or whose
session drops is NOT success by default** — treat it as `status=unverified`
and run `deploy_verify` immediately for ground truth.

**3a-i. Two corrections from the first live run (2026-08-17).** The first
cut of `deploy_verify` compared every product in the compose file against
the prod tip by raw sha inequality — its FIRST real run against prod
reported 10/11 products drifted, and turned out to be almost entirely false
alarms. Two fixes, both load-bearing: (1) the roster is now CATALOG-DRIVEN
(`ativo=true AND deploy_scope='live'` + `core`), not compose-driven — an
`ativo=false` product can never reach the prod tip, so flagging it drifted
would make the gate permanently red and train people to ignore it (same
failure mode as a noisy keeper); the catalog-live+missing-from-the-fleet
case (a p-studio-shaped absence) is its own `missing` finding, which a
compose-driven loop could never even see. (2) the drift TEST is no longer
raw sha inequality — running an older revision is the expected steady state
here (images rebuild only when their build scope changes,
`KB § PATTERNS/devops/product-lockfile-and-slug-drift.md`); `deploy_verify`
now diffs the running revision against the prod tip through
`deploy_pull`'s build-scope oracle (`_rebuild_decision`, reused verbatim —
no second hand-rolled "what belongs to a product" mapping) and only flags
`drift` when that diff actually touches the product's own build inputs (or
a fleet-wide `seed/`/Dockerfile/compose change).

**3a-ii. Root-caused (2026-08-17) — the circuit-breaker cooldown was NOT it.**
The original 2026-08-13 hang (`deploy_image` timed out and the MCP server
disconnected) was investigated by reading every `_vps_ssh.run_remote` call
site. The leading suspect — the 600s circuit-breaker cooldown — turned out
to be a FAST FAIL by design: an OPEN circuit returns in microseconds without
ever calling the real runner, so it cannot itself be the source of a
multi-minute internal block. The real gap: EVERY production caller
(`deploy_image`, `deploy_pull`, `vps_exec`, `vps`, `tunnel_config`,
`vps_exec_sql`, `ensure_product_url_roster`) left `run_remote(timeout=...)`
unset, so `subprocess.run` got `timeout=None` — genuinely UNBOUNDED — and
could block forever if the SSH transport connected fine but the REMOTE
command hung (a wedged docker daemon, a stalled pull). That block happens
*inside* the cross-process `_state_lock`, so it also silently stalls every
OTHER VPS tool in every process/worktree — consistent with a two-day
ambiguous window. Fixed in `mcp/noctusai/tools/noctus/dev/_vps_ssh.py`:
`run_remote` now NEVER forwards `timeout=None` downstream — `None` resolves
to a finite default (`_DEFAULT_REMOTE_TIMEOUT` = 120s, env
`NOCTUS_SSH_TIMEOUT`), bounding every attempt (and, by construction, the
`_state_lock` hold) to a computable worst case (`min_interval + rate_window
+ 2×ceiling` ≈ 303s at defaults — always finite). A LOCAL wall-clock kill is
classified distinctly from a genuine transport failure (`_LOCAL_TIMEOUT_RC`,
not ssh's own 255) so a slow-but-connected remote command can never
misclassify as a connection failure and spuriously trip the fail2ban breaker.
`deploy_verify` remains the independent witness regardless — this fix makes
the specific 2026-08-13 hang mechanism structurally impossible, not
redundant with it.

**4. `prod-backup` — the code rollback pointer.** `promote` snapshots the
outgoing prod sha there before moving `prod`. Check it advanced.

**5. Post-deploy prod smoke — MANDATORY, was optional.**
After the swap: `noctus.vps.health` must read all-healthy, and each ACTIVE
product's `/api/health` must answer 200 — probed on the VPS via
`noctus.vps.exec --container` (internal) *and* through the public edge.
Programmatic edge callers need a browser User-Agent or Cloudflare WAF rule
1010 rejects them. A deploy is not "done" until BOTH this AND `deploy_verify`
(point 3a) pass; if either fails, roll back rather than debug forward.

**6. `startup_hook_error` on `/api/health`.** A product whose lifespan hook
failed still serves and now says so in that field. Read it during smoke —
`status: "ok"` alone is no longer the whole answer.
→ `KB § PATTERNS/backend/startup-hook-must-not-be-fatal.md`

**Order:** `predeploy_check` (all active) → CI green → `bless` → `promote` →
`deploy_pull` → `deploy_image` per product → `deploy_verify` → prod smoke →
(rollback on fail).

---

## Scope: which products this even applies to

Only **ativo** products, per `KB § PATTERNS/architect/product-working-scope.md`:

- `ativo` + `live` → work it, deploy it, smoke it in prod
- `ativo` + `dev` → **there is nowhere to deploy it right now.** With the
  fleet dormant this combination is a *parking* state, not a workflow. Land
  the code on `dev` and stop; do not invent a substitute environment.
- `inativo` → do not touch

---

## When the dev fleet comes back

It comes back **when we actually need it**, and the owner decides that — not
an agent, not a keeper, not a "this would be safer with" argument. Concrete
triggers that would justify raising it:

- a prod incident whose root cause could only have been caught by running the
  container beforehand (that is the honest cost of this trade — log it)
- work that is genuinely un-testable without a live container: container
  wiring, entrypoints, inter-container networking, a base-image change
- a paying customer on a product where first-contact-in-prod is no longer an
  acceptable risk
- the storage pressure that motivated this is gone

Everything needed to raise it is still in the repo — `start.sh`,
`docker-compose.yml` per product, the whole fleet definition. Nothing was
removed. Bringing it back is `./start.sh <slug>`; it is a *cost* decision,
never a capability we lost.

**Do not add a keeper that requires a dev container. Do not "restore" the
fleet as a side effect of another task. Do not re-add the §0 dev-validate
gate.** If you believe prod-only is unsafe for something specific, surface it
to the owner with the specific risk — that is the whole protocol.

→ `KB § GUIDES/production-deploy.md` · `KB § PATTERNS/architect/git-branch-model.md` · skill `noc-ship`
