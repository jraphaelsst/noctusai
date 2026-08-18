# HANDOFF — `feat/olx-portal-leads-mcp`

> For whoever merges and deploys this. Rewritten 2026-08-17 after the branch
> was rebased onto `origin/dev`. **Nothing is deployed and nothing is pushed.**
> The branch lives in the worktree `.claude/worktrees/olx-portal-leads-mcp`.

## What this is

Grupo OLX portal-lead ingestion — ZAP · VivaReal · OLX · ImovelWeb · Casa
Mineira, which share one webhook. Plan: `PROJECT.md` beside this file.

## The commits (oldest first, over `origin/dev` @ `7d132be2`)

| SHA | What |
|---|---|
| `e8a3e7ea` | `docs(olx)` — MCP-first sequencing + Gate 1 in the plan |
| `47ca53a6` | `feat(seed)` — `basic_shared_secret` webhook scheme |
| `ee8e0c79` | `feat(seed)` — `noctusai_lib.integrations.olx` |
| `a4af62ff` | `feat(mcp)` — `mcp/olx` + KB docs + agent `owns_kb` |
| `f20ed2c8` | `feat(social-wiring)` — receiver, migration 051, module, config |
| `aff17af2` | `feat(social-wiring)` — OLX health card on the Leads config tab |
| `7d8b71be` | `feat(seed)` — `iter_paged_rows`, the one offset pager |
| `30092cb9` | `docs(olx)` — MCP registered (pre-merge form), repoint at merge |
| `37ae8fc0` | `docs(olx)` — the FE flake, recorded instead of a clean-596 claim |
| `0d95a725` | `fix(kb-sync)` — the kb-counts merge driver, made side-effect-free |
| `128b6c72` | `feat(seed)` — the portal splitter seam (rules empty until Gate 1) |
| `56cc392a` | `fix(social-wiring)` — OLX config DI seam; stop patching our own module |
| `3365a7ef` | `docs(olx)` — what the full toolkit suite caught, and the rc=0 trap |

(plus five `chore(branch-pointer)` commits — `d117a9b7`, `e48bdc98`, `bd8c5e0d`,
`c50f2044`, `ed85f033` — which carry no code.)

**Already rebased onto `origin/dev`.** It was 28 commits behind, and that
mattered — see "What the rebase changed" below. Re-fetch and re-check before
integrating; more may have landed since.

## Verification actually run, on the rebased tip

| Suite | Result |
|---|---|
| `seed/lib/backend` full | **2968 passed**, 1 skipped, **rc=0** |
| `products/social-wiring/backend` full | **1948 passed**, 3 skipped, **rc=0** |
| `mcp/olx/tests` + `mcp/_kit/tests` | **64 passed**, rc=0 |
| `mcp/noctusai` cli + kb_sync + task_branch | **112 passed**, rc=0 |
| `mcp/noctusai` the two compliance detectors | **2 passed** (98s), rc=0 |
| `mcp/noctusai` FULL suite | ran (70 min) — **see "what the full suite caught"** |
| `products/social-wiring/frontend` vitest | 596 tests / 56 files — **see the flake note** |
| `tsc --noEmit` (social-wiring FE) | **rc=0**, zero errors |
| `cli.py --help` | **rc=0** (it was broken mid-branch — see below) |
| `mcp/olx/server.py` over stdio | initialize → 9 tools → live call → 412 gate |
| pre-commit gates | green on every commit |

Exit codes captured with `pipefail`, never read off a piped `tail`.

> The p-studio CORS sentinel failure noted in the previous revision of this file
> is **gone** — it was fixed on `dev` and the rebase picked the fix up.

### 🟡 The FE suite times out under parallel load, on `dev` as well

**First, an env correction that invalidated the earlier numbers.** This
worktree was created with a bare `git worktree add`, so it had no
`node_modules`. Those were originally hand-symlinked, including a whole-dir
symlink at `products/social-wiring/frontend/node_modules` → the primary's real
directory. That is the exact shape `task_branch`'s env-wiring fixed as a
primary-contamination bug on 2026-07-20, and it had a second consequence here:
`@noctusai/{lib,seed}` resolved through it to the **primary's** seed, so FE
runs were building against `dev`'s seed frontend, not this branch's.

Re-wired using the toolkit's own planner/applier rather than by hand
(`_plan_env_wiring` / `_apply_env_wiring`), which converts the stale symlink to
a real worktree directory, overlays one symlink per primary package, and
re-points `@noctusai` at the **worktree's** seed. 3,740 links, 0 failures. The
primary was checked and is uncontaminated — its `@noctusai` links are relative
and predate this work (nothing was ever `npm install`ed through the symlink).

**With the wiring correct**, the full suite is stable at **591 passed / 5
failed**, twice running. The failures are `Test timed out in 5000ms` —
resource starvation under parallel load, not assertion failures — and they
move between runs (`ClientesBoard` ×2 and `RevisaoFila` ×2 are constant;
the fifth alternates between `Configuracao` and `CampanhaManagerDialog`).
**The same suite fails on `origin/dev` in the primary checkout** (8 failures
across `MarcaModal`, `CampanhaManagerDialog`, `ClientesBoard`, `RevisaoFila`),
so it is pre-existing and not from this branch.

What is actually established:

- every failing file passes **in isolation**, rc=0, in both trees;
- the three files this branch adds or touches (`useOlxLeads.test.ts`,
  `OlxWebhookCard.test.tsx`, `Configuracao.test.tsx`) pass **30/30 across
  three consecutive runs**;
- `tsc --noEmit` is **rc=0**, zero errors, with the corrected wiring.

Worth a real fix by whoever owns the FE suite — raising `testTimeout` or
capping `maxThreads` would likely do it. Not touched here: dev-owned files.

> The FE also needs `VITE_SUPABASE_URL` / `VITE_SUPABASE_PUBLISHABLE_KEY`
> exported from the primary's untracked `.env` — `wire_env` does not wire
> `.env`. Without them 7 files fail at import with a build-time-var error that
> reads nothing like a flake. Prefer `task_branch action=start wire_env=true`
> for a new worktree so none of this is manual.

## What the rebase changed, and why it was not optional

`dev` shipped three things on 2026-08-17, hours before this branch tried to
ship its own answer to the same problem:

1. `KB § PATTERNS/backend/postgrest-row-cap.md` — the pattern doc for the
   silent-1000-row-cap bug class (SEVEN prod instances in one session).
2. An **honest `MockSupabaseClient`** — `range()`/`limit()`/`offset()` now
   model PostgREST's real window and cap, and `.in_()` raises the real
   `APIError` over the URL budget.
3. Keeper `check_postgrest_unbounded_query`.

This branch had authored `postgrest-paging.md` for the same class. Two docs for
one bug class is the fork the methodology forbids, so the rebase **deleted**
`postgrest-paging.md` and folded the helper into `postgrest-row-cap.md`'s
Layer 2 — which had been a four-line recipe copied into four services. One
INDEX row, one `backend-engineer` rule, both `dev`'s, extended.

The framing changed with it: "the mock hangs offset loops" is now history, not
a live symptom. It is *how the hang was found*, not why it matters — a client
or proxy dropping the `Range` header still hangs production, on the path
touching the most rows, with no test watching. The docstrings say that.

**Rebase mechanics — the wall is gone, and the fix ships in this branch.**
Replaying over `dev` used to stall forever: `.gitattributes` gives
`02-LANDSCAPE.md` a `merge=kb-counts` driver, and that driver regenerated the
counts by writing to the **real working-tree path**, so the tree was dirty
again between picks and every `--continue` aborted (stalled at pick 7/10,
indefinitely, with the todo list growing on each attempt).

A merge driver's contract is to write `%A` and nothing else. The driver now
keeps it, via a new pure CLI mode:

```
python mcp/noctusai/cli.py --render-kb-counts <repo-rel-path> --source <file> --out <file>
```

`git rebase origin/dev` now needs **no flags, no env, no overrides** — proven
on an isolated repro worktree at the pre-fix tip: 7/10 stall → all 10 picks
applied, stopping only on the two genuine doc conflicts, with `02-LANDSCAPE.md`
auto-merging exactly as the driver intends. Detail:
`KB § PATTERNS/common/auto-generated-merge-drivers.md`.

> ⚠️ The driver git actually executes is the **primary checkout's** copy
> (`git config merge.kb-counts.driver` holds an absolute path), so the fix only
> takes effect locally once this branch lands on `dev`. Until then a rebase
> still stalls. That is an argument for merging this sooner, not for reviving
> the workaround.

**Do not merge instead of rebasing**: a merge commit stages `dev`'s
`deploy/consent/p-studio.prod.yml` alongside 64 other paths and
`check_prod_exposure_consent` refuses it — correctly, that gate exists to stop
consent slipping through inside an unrelated diff.

## Merge

Collision zones (published on the branch-tree pointer):
`seed/.../integrations/olx`, `seed/.../security/webhook_signatures.py`,
`seed/.../integrations/persistence/`, `mcp/olx`,
`products/social-wiring/{backend,frontend}`,
`KNOWLEDGE-BASE/{INDEX.md,MCP-SERVERS,CONTEXT/PATTERNS/backend/postgrest-row-cap.md,CONTEXT/INTEGRATIONS/olx.md}`,
`.claude/agents/backend-engineer.md`, `projects/olx-portal-leads-ingestion`.

**New collision surface since the last revision:** this branch now edits
`modules/leads/services/query.py` and `meta_ingest_service.py`, and
`postgrest-row-cap.md`. Check those against live peers specifically.

```
git -C .claude/worktrees/olx-portal-leads-mcp fetch origin
git -C .claude/worktrees/olx-portal-leads-mcp rebase origin/dev   # env above if it stalls
git -C .claude/worktrees/olx-portal-leads-mcp push origin HEAD:dev
```

Re-run the gates on the **merged tip**, not per branch.

## After the merge, before anything else

1. **Repoint the MCP row.** `.mcp.json` is gitignored, so it is a local edit —
   and it is **already registered**, pointing at the *worktree* server path so
   the connector is usable before the merge (the user asked for it live this
   session). Once merged, and **before** `task_branch action=cleanup` removes
   the worktree, change `args` back to the durable relative form
   `["mcp/olx/server.py"]`. The exact before/after is in
   `KB § MCP-SERVERS/olx.md § Registration`. Cleaning the worktree without
   repointing leaves a server row whose file is gone.
2. **Migration 051 is NOT applied.** File only, per the house rule. Needs
   `noctus.dev.migrate_product` with explicit consent. Additive: two new
   tables, two new nullable columns, one widened CHECK, plus a backfill of the
   existing Meta rows into the new generic external-lead key.

## Gate 1 blocks deploy, and needs the user

The receiver is **inert until configured** — no secret ⇒ every delivery gets a
401, by design. Merging is therefore safe; calling it live is not, until:

- the real `SECRET_KEY` arrives (`integracaoleads@grupozap.com`) and is set as
  `olx_webhook_secret` (app config) / `OLX_WEBHOOK_SECRET`;
- `olx.diagnostics.probe` runs live and every `unverified` baseline row is
  filled in **from what was observed**, never guessed;
- a real delivery is captured with `olx.webhook.record_delivery` and
  `olx.contract.diff_observed` reports no unexplained divergence;
- the KB change log (`INTEGRATIONS/olx.md` §8) records the date + evidence.

**Everything in the contract is transcription, not measurement.** The connector
says so itself: `olx.webhook.describe_contract` returns
`verified_against_live_traffic: false` and all 14 fields `verified: false`,
and every `OLX_ENDPOINT_BASELINE` row carries `expected_http_status: null`
with `probe_status: "unverified"`. Nothing was guessed into a green-looking
number. `PROJECT.md § Gate 1` has the checklist and the four open questions.

## What the FULL mcp/noctusai suite caught (and the fast suites could not)

Running it takes ~70 minutes, so it is easy to skip. It came back `rc=1`
with three defects that were **mine**, none visible to the per-module runs:

1. **`cli.py --help` was broken outright.** argparse `%`-expands help strings,
   and the new `--render-kb-counts` help contained a literal `%A` (describing
   git's merge result) → `ValueError: unsupported format character 'A'`. `%%A`
   renders correctly. Caught by `test_cli_worktree_path`, which asserts
   `--help` runs at all — a test worth knowing exists before touching argparse.
2. **Two NEW high-severity compliance regressions vs the committed baseline**,
   both *monkeypatching our own code in tests*
   (`patch(...resolve_olx_config)`, `monkeypatch(resolve_portal_source_slug)`).
   Fixed with real seams — `app/modules/portal_leads/deps.py` (module-level
   config provider) and an `ingest_olx_lead(..., portal_rules=…)` parameter —
   **not** by adding fingerprints to the baseline.

> ⚠️ **The task notification for that background run said "exit code 0".**
> That is the shell wrapper's status; pytest itself returned `rc=1`
> (5 failed / 3596 passed). Same trap as `cmd | tail`, one layer out — read
> the summary line, not the wrapper.

Pre-existing and **not** from this branch (verified by reproducing on
unmodified `dev` in the primary checkout):
`test_graph_extractor_correctness.py::TestEdgeFloors::test_cache_edge_floor[semantic_neighbor-100]`.

## Findings worth keeping

1. **`iter_paged_rows` is new seed surface on a hot path.** Three social-wiring
   loops now route through it. It cannot truncate silently — it raises — so a
   regression shows up as a visible failure, not a wrong total. Un-migrated
   loops (`portal_roi_service`, `clientes_service`, `imoveis_service`,
   `email_marketing/contact_service`) are named in the KB doc for a sweep;
   deliberately not touched here, they landed on `dev` hours ago.
2. **`iter_leads_rows` now forces `id` into the projection.** Its callers ask
   for `origem_raw` / `corretor_raw` / `source_sheet` — non-unique columns they
   are *counting*, so the pager's dedup key had to be `id` or rows would
   collapse. Behavioural change worth a look in review.
3. **The `migration_parser` multi-`ADD COLUMN` fix** (in `f20ed2c8`) still
   stands: it registered only the FIRST `ADD COLUMN` of a multi-clause
   `ALTER TABLE`, so ~20 fleet migrations had columns invisible to the mock
   schema registry. 5 regression tests. Seed-testing change touching every
   product — worth attention in review, though it can only make the registry
   more complete, never stricter.
4. **Pre-existing, untouched:** `check_hardcoded_product_slug_set` warns on
   `seed/.../tests/domain/fleet_control/test_fleet_control.py:31` on every
   commit that stages a seed test. Not from this branch.

## What is deliberately NOT done

- Not pushed, not merged, not deployed. Migration not applied.
- **The portal splitter is BUILT and wired, with an empty rule table.**
  `noctusai_lib.integrations.olx.portal_split` sits on the ingest path and
  returns the `grupo-olx` umbrella for every lead, because the payload names no
  portal and inventing one would write a guess into Portal ROI. Gate 1 turns
  the split into a `PortalRule(...)` entry — a data change, no migration (every
  portal slug already ships in `CANONICAL_SOURCES`). A rule cannot be
  constructed without an OBSERVATION in `evidence`, nor against a slug with no
  `lead_sources` row.
- **No ImovelWeb work here — a peer owns it.** `feat/imovelweb-portal-leads` is
  building `noctusai_lib.integrations.imovelweb` (seed IO quartet) right now.
  This branch deliberately stops at the Grupo OLX pipe; do not let the two
  overlap at merge.
- Un-migrated paging loops (finding 1) — named, not swept.
