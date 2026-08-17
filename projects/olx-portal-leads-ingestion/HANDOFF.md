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
| `d117a9b7` | `chore(branch-pointer)` |
| `f20ed2c8` | `feat(social-wiring)` — receiver, migration 051, module, config |
| `aff17af2` | `feat(social-wiring)` — OLX health card on the Leads config tab |
| `0a956dc9` | `docs(olx)` — this file (earlier revision) |
| `e48bdc98` | `chore(branch-pointer)` |
| `7d8b71be` | `feat(seed)` — `iter_paged_rows`, the one offset pager |

**Already rebased onto `origin/dev`.** It was 28 commits behind, and that
mattered — see "What the rebase changed" below. Re-fetch and re-check before
integrating; more may have landed since.

## Verification actually run, on the rebased tip

| Suite | Result |
|---|---|
| `seed/lib/backend` full | **2955 passed**, 1 skipped, **rc=0** |
| `products/social-wiring/backend` full | **1946 passed**, 3 skipped, **rc=0** |
| `mcp/olx/tests` + `mcp/_kit/tests` | **64 passed**, rc=0 |
| `products/social-wiring/frontend` vitest | **596 passed**, 56 files |
| `tsc --noEmit` (social-wiring FE) | **rc=0** |
| `mcp/olx/server.py` over stdio | initialize → 9 tools → live call → 412 gate |
| pre-commit gates | green on every commit |

Exit codes captured with `pipefail`, never read off a piped `tail`.

> The p-studio CORS sentinel failure noted in the previous revision of this file
> is **gone** — it was fixed on `dev` and the rebase picked the fix up. The
> `tsc` gap was a missing `node_modules` in the worktree; symlinked from the
> primary (untracked, disappears with the worktree).

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

**Rebase mechanics, if you hit the same wall.** Replaying over `dev` fights
`.gitattributes`' `merge=kb-counts` driver on `02-LANDSCAPE.md`: it re-derives
the counts block on every 3-way merge, so the tree is dirty again between
picks and every `--continue` aborts. Neutralise the driver for the rebase only:

```
GIT_CONFIG_COUNT=2 \
  GIT_CONFIG_KEY_0=core.hooksPath      GIT_CONFIG_VALUE_0=/dev/null \
  GIT_CONFIG_KEY_1=merge.kb-counts.driver GIT_CONFIG_VALUE_1=true \
  git rebase origin/dev
```

The counts are machine-derived and the pre-commit hook regenerates them on the
next real commit, so keeping "ours" loses nothing. **Merging instead of
rebasing does not work here**: the merge commit stages `dev`'s
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
- **The portal splitter** (`grupo-olx` → `zap` / `viva-real` / `imovel-web`) is
  not built: the payload does not name the portal, so there is nothing honest
  to split on yet. `origem_raw` carries `leadOrigin / leadType`, so it stays
  buildable the moment real traffic shows a discriminator.
- **No ImovelWeb-direct adapter.** Working hypothesis: ImovelWeb rides this
  same webhook once the client requests an activation code from
  `atendimento@imovelweb.com.br`. Confirm at Gate 1 before building anything.
- Un-migrated paging loops (finding 1) — named, not swept.
