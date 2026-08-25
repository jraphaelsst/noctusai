# Roadmap — rename the product slugs: `erp-imobiliario` → `erp`, `social-wiring` → `social`

**Slug:** `product-slug-rename` · **Opened:** 2026-08-25 · **Owner:** tech-lead (Raphael)
**Status:** NOT STARTED — this is the deferred "heavy work" half of the 2026-08-25 session.

> 🔴 **HANDOFF NOTE — READ FIRST.** The owner's instruction at the close of the
> 2026-08-25 session: *"please dont deploy nothing to prod. Leave the work wrapped
> up with notes for another agent to deal with deployment. The last one remaining
> working will merge and deploy the platform."*
>
> So: **do the work, integrate to `dev`, and STOP.** Do not bless, do not promote,
> do not `deploy_image`. The final agent does the merge + deploy for the whole
> platform. See "State of prod at handoff" below for exactly what is already live,
> so you neither re-deploy it nor double-count it.

## Goal

The two products are publicly reachable at `erp.noctusai.com` and
`social.noctusai.com` (done — see below). Their INTERNAL slugs are still
`erp-imobiliario` and `social-wiring`. Rename those too, so the long names stop
recurring in code, containers, images, logs and every generated artifact.

## Why

The owner set the short public hostnames; a later change added them as aliases
"kept alongside, not replacing" the long ones, which inverted that. The hostnames
are now fixed. The slugs are the remaining source of the long names — every
generated artifact (catalog, compose, CI matrix, image tag) re-derives them from
the slug, so the long form keeps reappearing until the slug itself changes.

## Scope — measured, not estimated (2026-08-25)

```
erp-imobiliario -> 316 files
social-wiring   -> 509 files
                   ---
                   825 files total
```

(`--include=*.{py,ts,tsx,yml,yaml,json,md,sh,sql,Dockerfile*}`, excluding
`node_modules` and `.claude/worktrees`.)

This is a migration, not a rename. Surfaces that are NOT just text:

| Surface | Why it is not a sed |
|---|---|
| **GHCR image repos** | `ghcr.io/jraphaelsst/noctus-erp-imobiliario` → `noctus-erp`. New package repos must be created + built + pushed BEFORE any container references them. Old repos stay as rollback material; do not delete. |
| **Container names** | `noctus-erp-imobiliario` → `noctus-erp`. Prod containers get recreated under new names — the old ones must be stopped, and `deploy_image`'s snapshot/rollback pointer (`:previous`) does NOT carry across a rename. |
| **`noctus-net` service aliases** | `deploy/tunnel/ingress.yml` route targets are `http://erp-imobiliario:8001`. Those are in-network service names — they change with the compose service name and MUST move in the same change, or every hostname 502s. |
| **DB schema refs** | ERP's schema is already `erp` (confirmed: the app logs `"app": "erp"`). Verify social-wiring's before assuming; a schema rename is a migration with RLS implications across ~74 tables. **Check before touching.** |
| **CI test matrix + dependabot** | Both carry hand-maintained per-product lists, already gated by `check_ci_test_matrix_coverage` + `check_dependabot_product_coverage`. They will block a partial rename — that is the gate working, not an obstacle to route around. |
| **`deploy/fleet/build-scope.txt`, prod compose, `ALL_SLUGS`** | The prod-exposure-consent gate keys on a product's FIRST arrival in these. A renamed slug may read as a NEW product and demand a consent record — expect this and handle it deliberately (`noctus.dev.prod_consent`), never bypass it. |
| **Directory names** | `products/erp-imobiliario/` → `products/erp/`. Use `git mv` so history follows. |

## Slices

| # | Slice | Status | Notes |
|---|---|---|---|
| 0 | **Recon**: confirm social-wiring's DB schema name; enumerate generated-vs-authored surfaces | ⏳ todo | Do NOT sed a generated file — regenerate it. `mcp/noctusai/catalog.md` and the product composes are derived. |
| 1 | `erp-imobiliario` → `erp` end-to-end on `dev` (dirs, compose, ingress targets, CI, dependabot, catalog, KB, image name) | ⏳ todo | One product at a time; pilot-products-first cadence. |
| 2 | Same for `social-wiring` → `social` | ⏳ todo | Larger (509 files), more modules, has migrations. |
| 3 | Build + push the NEW GHCR repos at the dev tip; verify images exist and are pullable BEFORE any compose references them | ⏳ todo | Chicken-and-egg: compose must not point at a repo that does not exist yet. |
| 4 | Deploy — **NOT THIS AGENT** | ⏳ blocked-by-owner | Recreating containers under new names is the risky step. Rollback = `prod-backup` + the old GHCR repos + old container names. |

## Decision log

- **2026-08-25** — Owner: *"do the easy work first, the heavy work after. I want it in full and deployed to production whenever ready."* The easy half (hostnames) shipped that day; this roadmap is the heavy half.
- **2026-08-25** — Owner, later the same session: **no more prod deploys.** The final agent merges + deploys the platform.
- **2026-08-25** — Public hostnames are DECOUPLED from slugs. `ingress.yml` maps hostname → service explicitly, so the short URLs shipped without the rename. Keep it that way: a future hostname change must never require a slug migration.

## State of prod at handoff (2026-08-25) — already done, do not re-do

`origin/prod` = `eb648b2b`. `prod-backup` = `149fdbf4` (rollback pointer).
`deploy_verify` = **verified** — 7/7 actionable products on the prod tip, 0 drifted,
0 degraded, 0 missing. `noctus.vps.health` = 11 healthy / 0 unhealthy. All 7 SPAs
pass `spa_smoke` on their real hostnames.

Shipped and live:

1. **PDF scan-vs-text-layer classifier** (`media.classify_pdf_text_layer`) — a
   cartório scan's text layer is a signature stamp, not content. Four call sites now
   consume it. A CERTIDÃO DE MATRÍCULA had been transcribed as three copies of its
   own ONR validation URL.
2. **Whole-document transcription absorbed into the seed**
   (`documents.transcription` — Protocol + Fake + Real + factory), consumed by
   `matricula_service` (256 → 146 lines) and `certidoes_service`. **This is what
   social-wiring is meant to consume next** — see "Next up".
3. **Pure-ASGI seed middleware** — the `erp.noctusai.com` 502. `BaseHTTPMiddleware`
   was truncating responses under service-worker traffic (260 errors in 6h, while
   every health check passed). Verified fixed in prod: 20/20 full-body responses,
   5/5 clean 304s, 0 errors.
4. **Short hostnames only** — `erp-imobiliario.noctusai.com` and
   `social-wiring.noctusai.com` retired (now 404); `erp.` / `social.` are the only
   public names. `ingress.yml` gained a machine-readable `retired:` list so
   `tunnel_config action=apply` can drop a hostname deliberately without anyone
   bypassing its own outage guard.

## Next up — unrelated to the rename, queued, not started

- **social-wiring consumes the seed transcriber.** `media_service._extract_pdf_text`
  (~line 879) plus its tier-2 rasterize block collapses to one `transcribe()` call.
  This also closes the 6th instance of the scan-stamp bug: its `<200 chars` thin-text
  guard is cleared by the 411-char three-page ONR stamp.
- **`google_drive/reader_types.py:333`** (`DriveFileContent.text`) still returns the
  raw text layer — same bug, but it has NO vision rung to fall back on, so fixing it
  trades stamp junk for `""`. Needs a deliberate call.
- **`certidoes_service` vision cap.** Wired at `max_vision_pages=0` (text layer only)
  so a background scheduler on a per-org timer does not start billing vision calls.
  Raising it is a cost decision, not a technical one.

## Housekeeping only the owner can do — now LOSSLESS

The PRIMARY checkout (`/Users/rapha/Documents/repository/NoctusAI/noctusai`) is on a
diverged local `dev` and cannot fast-forward. `primary_write_guard` correctly refuses
to let an agent resolve this, so it needs the owner — but the hard part is already
done: **every stranded ledger entry is now on `origin/dev`** (commit `1f0ae93b`), so
the reset below loses nothing.

```
git -C <repo> reset --hard origin/dev
```

What was recovered first, so you know nothing is being discarded:

- The **6 unpushed `chore(salvage)` commits** that caused the divergence — their
  content (6 recovery pointers) is on `origin/dev`.
- **3 more pointers** appended by that session's own `task_branch action=cleanup`
  runs — same file, same fate, also landed.
- `project-history/vector-costs.ndjson` — the one extra ledger line, landed too.

Landed as a UNION over the three sources (dev's committed ledger, the preservation
branch `chore/salvage-ledger-20260825`, the primary's live working copy) rather than
a cherry-pick: these are append-only NDJSON ledgers of independent facts, so a union
cannot drop one, while rebasing six successive appends onto a moved base invites a
conflict resolution that silently can.

Still uncommitted and genuinely disposable in that tree: `mcp/noctusai/catalog.md`
(a generated catalog scan — regenerates on demand).

### 🔴 Tooling defect worth fixing

`task_branch action=cleanup` records its recovery pointer into the PRIMARY checkout's
working tree and returns `salvage_pushed: false` — it cannot commit there, because the
primary-write guard (correctly) forbids it. So **every teardown grows uncommitted
ledger drift by construction**, and the `false` is easy to read past in a large result
payload. That is how 9 pointers accumulated unlanded. Options: have cleanup write the
pointer via a short-lived worktree it can commit from, or make the ledger drift a
first-class surfaced warning rather than one field.

## Retrospective (fill on close)

- _pending_
