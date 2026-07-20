# Prod-exposure consent — registering a product on the fleet IS the promotion decision

**What it is.** A pre-commit gate (`check_prod_exposure_consent`) + a status/authoring-assist tool (`noctus.dev.prod_consent`) that make it structurally impossible for a product's *first arrival* on a prod-exposure surface to land without an explicit, user-authored consent record.

**Why.** Codified 2026-07-20 after the **orbity incident**: the product went prod-serving on 2026-06-03 — the same day it was scaffolded, six weeks before validation, every roadmap phase still ⬜, no consent decision anywhere. The architect traced the causal chain: commit `679d0838` "feat(deploy): onboard orbity to the prod fleet" registered orbity on THREE surfaces simultaneously:

- `deploy/fleet/docker-compose.prod.yml` (runs on the VPS fleet)
- `deploy/tunnel/ingress.yml` (public edge — `<slug>.noctusai.com`)
- `ALL_SLUGS` in `scripts/infra/build-and-push.sh` (GHCR artifact + `:latest`)

**Editing those three surfaces *IS* the production-promotion decision.** Everything downstream (bless → main-push CI build → `:latest` → fleet pull) is faithful automation of a declaration already made. There is **no later gate** — the fleet runs `:latest` built from `main` on every push (`.github/workflows/build-and-push.yml`), so a `prod`-branch FF governs the deploy-config **checkout**, never the product **images** that actually execute (`KB § GUIDES/production-deploy.md § 2b` correction). By the time a product shows up on `docker-compose.prod.yml`, it is publicly reachable the moment the next `docker compose pull` happens — no human ever reviews "should this be public" again.

## The fire boundary — a SET-DIFFERENCE on slugs, not a content diff

```
declared = slugs(WORKING TREE: compose.prod ∪ ingress ∪ ALL_SLUGS)
baseline = slugs(HEAD:         compose.prod ∪ ingress ∪ ALL_SLUGS)
new      = declared − baseline
if not new: return []          ← the universal, silent case
```

This is what keeps the gate from becoming noise. It fires **only** on a product's **first** arrival on any of the three surfaces:

| Case | Fires? |
|---|---|
| A product's slug appears for the first time on compose/ingress/ALL_SLUGS | ✅ yes |
| Any `products/<slug>/**` commit for an already-registered product | ❌ silent (surfaces unchanged) |
| Routine redeploy / bless / promote | ❌ silent (no edit to the three files) |
| Editing *inside* an existing service block (port / env / healthcheck / anchors) | ❌ silent (the slug *set* is unchanged) |
| Removing a slug (de-registration) | ❌ silent (never appears in `new`) |
| No `deploy/` directory (non-noc tree) | ❌ silent-skip |

## The consent record

For each slug in `new`, the gate requires `deploy/consent/<slug>.prod.yml` **present in `HEAD`** — i.e. committed in a **prior, isolated commit**, never the registration commit itself:

```yaml
consented_by: <the user's git-config user.email>
consented_on: <YYYY-MM-DD>
consent_ref: <path/to/roadmap.md>#<milestone text, ALSO marked ✅ on that same line>
dev_validated: true
```

All four legs are validated (`_validate_prod_consent_record` in `compliance.py`):

1. **Non-empty** `consented_by` / `consented_on` / `consent_ref`.
2. `dev_validated: true` (literal boolean — the dev-first validation gate, `KB § GUIDES/production-deploy.md § 0.1`, must have already run).
3. `consent_ref` **resolves** to a `roadmap-tracking.md`-shaped milestone: `<relpath>#<anchor>` — the roadmap file must exist AND contain a line with BOTH the anchor substring AND a ✅ marker (`_resolve_roadmap_milestone`). E.g. a Milestones bullet gets annotated once reached: `- **M4: prod promote** — ... ✅ 2026-07-20`.
4. `consented_by` **matches** the current commit author's `git config user.email` (`_git_author_email`) — a mismatch means someone other than the person about to commit is claiming the consent, which is refused.

Any failure → **severity `high`**, hard-block at pre-commit, with a self-explanatory message (see below).

## Consent commits must be isolated

`_check_consent_commit_isolated` refuses a `deploy/consent/*.prod.yml` staged alongside **any other path** — independent of the set-difference, so it fires even when `new` is empty. This closes the "slip consent past review inside an unrelated diff" hole: the consent record must be its own commit, reviewable on its own, before the registration commit can even be attempted.

## Failure message contract

The message an agent sees is deliberately self-explanatory, not just a violation name — it states which three surfaces are affected, that registration **is** the promotion decision, that there is **no later gate**, exactly what the **USER** (not an agent) must do, and ends with:

> An agent MUST NOT create the consent record on the user's behalf.

`noctus.dev.prod_consent action=request slug=<slug>` prints the exact same template + instructions on demand — and **refuses to write the file** (refuse-not-null, `KB § PATTERNS/common/gate-methodology-sync.md`). An agent calling this tool can only ever hand back instructions; it can never produce a consent record.

## `noctus.dev.prod_consent` — status + refuse-not-null template

| action | Behavior |
|---|---|
| `status` | Honest per-product dashboard for every slug currently declared on the three surfaces. `consent_status` ∈ `valid` / `invalid` / `missing_pregate`. |
| `request` | `ok: false` always — never writes. Returns `target_path`, `already_exists`, `template_yaml`, `instructions`. |

## Scope decision — no backfill for grandfathered products

The 9 products (+ n8n/waha/legacy infra rows) already on the three surfaces at gate-introduction time are **NOT** retroactively required to carry a consent record — the set-difference means they never appear in `new` going forward, so correctness never depends on a backfill. `prod_consent action=status` reports them honestly as `missing_pregate` ("no consent record on file (pre-gate)") — never silently hidden, never auto-authored. **An agent must not author a `deploy/consent/*.prod.yml` on the user's behalf, including as a backfill** — doing so on day one would defeat the mechanism it exists to gate.

## What this does NOT touch (deliberately deferred)

- `.github/workflows/build-and-push.yml` — the CI-job backstop (should CI itself refuse to build/push a newly-registered slug without consent?) is a separate wave pending user decision.
- `release.py` / `deploy_image.py` — the PROD-PIN HOLE (the fact that `:latest` floats independent of the `prod`-branch promote gate, see the `KB § GUIDES/production-deploy.md § 2b` correction) is a structural gap this doc names but does not fix — fixing it changes what runs in prod and needs its own consent.

## Mechanism half — `scaffold_product` never touches these surfaces

`noctus.dev.scaffold_product` (product creation) does not, and must never, write to any of the three surfaces — locked in by `TestScaffoldProductNeverTouchesProdExposureSurfaces` (AST-scans `scaffold.py`'s code for the three surfaces' literal names; the module's own explanatory comment is exempt since comments aren't AST nodes). Its `next_steps` always carries a breadcrumb: prod exposure is a separate, consent-gated step the scaffold never performs.

## Composes with

- [`gate-methodology-sync`](../common/gate-methodology-sync.md) — the gate/mechanism pairing this pattern instantiates (refuse-not-null on `prod_consent action=request`).
- [`prod-deploy-safety-gates`](prod-deploy-safety-gates.md) — the sibling pre-deploy gate cluster (cache reachability / drift-shield / slip-shield); this gate answers a *different* question ("should this product be public at all") than theirs ("is this deploy safe to ship").
- [`git-branch-model`](../architect/git-branch-model.md) — bless/promote are **branch-granular**, not per-product; this consent gate is the missing **per-product** promotion decision bless/promote never made.
- [`roadmap-tracking`](../common/roadmap-tracking.md) — the `consent_ref` milestone-resolution convention.
- `KB § GUIDES/production-deploy.md § 2b` — the corrected "prod branch gate" claim this pattern's incident analysis forced.

## CLI

```bash
python mcp/noctusai/cli.py --check-prod-exposure-consent
```

## MCP tools

- `noctus.dev.prod_consent(action='status'|'request', slug=None, worktree_path=None)`.

## History

- **2026-07-20** — Shipped closing the orbity incident (prod-serving six weeks before validation, zero consent decision on record). Keeper + mechanism (`scaffold_product` invariant + `prod_consent` tool) + regression test proving fire/pass/silent + 8-way sync, same commit.
