# HANDOFF — `feat/olx-portal-leads-mcp`

> For whoever merges and deploys this. Written 2026-08-17 by the session that
> built it. **Nothing is deployed and nothing is pushed.** The branch exists
> locally, in the worktree `.claude/worktrees/olx-portal-leads-mcp`.

## What this is

Grupo OLX portal-lead ingestion — ZAP · VivaReal · OLX · ImovelWeb · Casa
Mineira, which share one webhook. Plan: `PROJECT.md` beside this file.

## The commits (in order — each is self-contained and green)

| SHA | What |
|---|---|
| `6e455d62` | `docs(olx)` — MCP-first sequencing + Gate 1 in the plan |
| `cbe33f97` | `feat(seed)` — `basic_shared_secret` webhook scheme |
| `8d2d043a` | `feat(seed)` — `noctusai_lib.integrations.olx` |
| `af74d5f6` | `feat(mcp)` — `mcp/olx` + KB docs + agent `owns_kb` |
| `57d25c4f` | `chore(branch-pointer)` |
| `5c84ee69` | `feat(social-wiring)` — receiver, migration 051, module, config |
| `ed835117` | `feat(social-wiring)` — OLX health card on the Leads config tab |

Fork base is `origin/dev` as of 2026-08-17 (`4e54e832`).

## Verification actually run (not inferred)

| Suite | Result |
|---|---|
| `seed/lib/backend` full | **2939 passed**, 1 skipped |
| `products/social-wiring/backend` full | **1942 passed**, 3 skipped |
| `products/social-wiring/frontend` vitest full | **596 passed**, 56 files |
| `mcp/olx/tests` | **33 passed** |
| `mcp/_kit/tests` | passed |
| `tsc --noEmit` (social-wiring FE) | **rc=0**, zero errors |
| `mcp/olx/server.py` over stdio | initialize → 9 tools → live call → 412 gate |
| pre-commit gates | green on every commit |

Two failures encountered while running these turned out to be **worktree
environment gaps, not regressions** — both verified by reproducing green
elsewhere:

- `seed .../test_per_product_cors_sentinel[p-studio]` needs `P_STUDIO_ORG_ID`,
  which lives in the primary checkout's untracked `.env`. Passes in the
  primary; passes in the worktree when the var is supplied.
- `tsc` reported 156 errors, **all** in `seed/lib/frontend/src`, because the
  worktree had no `node_modules` there. `rc=0` in the primary. After
  symlinking, `rc=0` in the worktree too.

> The worktree was created with a bare `git worktree add`, so it is env-less.
> I symlinked `node_modules` for `products/social-wiring/frontend`,
> `seed/lib/frontend` and `seed/framework/frontend` to the primary's. Those
> symlinks are untracked and disposable — they vanish with the worktree.

## Merge

Collision zones (published on the branch-tree pointer): `seed/.../integrations/olx`,
`seed/.../security/webhook_signatures.py`, `mcp/olx`, `products/social-wiring/{backend,frontend}`,
`KNOWLEDGE-BASE/{INDEX.md,MCP-SERVERS,CONTEXT/INTEGRATIONS/olx.md}`,
`.claude/agents/backend-engineer.md`, `projects/olx-portal-leads-ingestion`.

Live peers to check before integrating — several touch social-wiring:
`feat/fix-portal-roi-lead-count-cap`, `feat/fix-revisao-in-filter-overflow`,
`feat/fix-revisao-page-envelope`, `integration/session-gates`. **No file
overlap that I can see** (they are in `services/`/`routers/`, this adds
`modules/portal_leads/`), but `KNOWLEDGE-BASE/INDEX.md` is high-traffic and is
the likely conflict. Re-run the gates on the **merged tip**, not per branch.

Integrate worktree-explicitly while peers are live:

```
git -C .claude/worktrees/olx-portal-leads-mcp fetch origin
git -C .claude/worktrees/olx-portal-leads-mcp rebase origin/dev
git -C .claude/worktrees/olx-portal-leads-mcp push origin HEAD:dev
```

## After the merge, before anything else

1. **Register the MCP** — `.mcp.json` is gitignored, so it is a local edit.
   The row is in `KB § MCP-SERVERS/olx.md`. **Do not add it before the merge**:
   `cwd` points at the primary checkout, whose editable `noctusai_lib` has no
   `integrations.olx` until then, so the server would ImportError at every
   session start. Keep-list membership is the user's call.
2. **Migration 051 is NOT applied.** File only, per the house rule. It needs
   `noctus.dev.migrate_product` with explicit consent. It is additive
   (two new tables, two new nullable columns, one widened CHECK) and it
   backfills the Meta rows into the new generic key.

## Gate 1 blocks deploy, and needs the user

The receiver is **inert until configured** — no secret ⇒ every delivery gets a
401, by design. So merging is safe, but shipping it as "working" is not, until:

- the real `SECRET_KEY` is obtained (`integracaoleads@grupozap.com`) and set
  as `olx_webhook_secret` (app config) / `OLX_WEBHOOK_SECRET`;
- `olx.diagnostics.probe` is run live and every `unverified` baseline row is
  filled in **from what was observed**, never guessed;
- a real delivery is captured with `olx.webhook.record_delivery` and
  `olx.contract.diff_observed` reports no unexplained divergence;
- the KB change log (`INTEGRATIONS/olx.md` §8) records the date + evidence.

`PROJECT.md` § Gate 1 has the full checklist including the four open questions
(does `leadOrigin` ever name the portal · is the Basic username still
`vivareal` · which `extraData` keys really arrive · do ImovelWeb leads land on
this pipe).

## Findings worth keeping (surfaced, not swallowed)

1. **`noctusai_lib.testing.migration_parser` only registered the FIRST
   `ADD COLUMN` of a multi-clause `ALTER TABLE`.** ~20 fleet migrations use
   that form (erp `006` adds 3 columns, erp `016` adds 4), so those columns
   were invisible to the mock schema registry and any test touching one failed
   naming a column the migration plainly adds. **Fixed in this branch**
   (`5c84ee69`) with 5 regression tests. The change can only make the registry
   more complete, never stricter — but it is a seed-testing change touching
   every product, so it deserves attention in review.
2. **An offset-paged loop hangs when the backend ignores `range()`.**
   `MockSupabaseClient.range()` is a documented no-op, so the backfill spun
   forever on its first run. Fixed by making progress-over-unseen-ids the
   termination condition. The same shape exists elsewhere in the fleet
   (`meta_ingest_service.backfill_meta_ads_leads`, `query.py`) — those loops
   are correct against real PostgREST but share the hang-if-ignored property.
   Not touched here; worth a sweep.
3. **`.mcp.json` is gitignored.** The plan assumed it was committable. Any
   future "register the connector" step is a local action plus a KB doc, never
   a commit.
4. **Pre-existing, untouched:** `check_hardcoded_product_slug_set` warns on
   `seed/.../tests/domain/fleet_control/test_fleet_control.py:31` on every
   commit that stages a seed test. Not mine, not fixed here.

## What is deliberately NOT done

- Not pushed, not merged, not deployed.
- Migration not applied.
- MCP not registered.
- The portal splitter (`grupo-olx` → `zap` / `viva-real` / `imovel-web`) is
  **not** built: the payload does not name the portal, so there is nothing
  honest to split on yet. `origem_raw` carries `leadOrigin / leadType` so it
  stays buildable.
- No ImovelWeb-direct adapter — the working hypothesis is that ImovelWeb rides
  this same webhook once the client requests an activation code from
  `atendimento@imovelweb.com.br`. Confirm at Gate 1 before building anything.
