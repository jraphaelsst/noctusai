# WAVE-4 TEARDOWN MANIFEST — verified, ordered, scripted-apply-ready

> Produced by Engineer **W4-RECON** (read-only critical-path accelerator), 2026-05-16, on branch `feat/social-wiring-absorption` @ `7c746a5`.
> **Wave 4 is GATED (hard) on Wave-2-full-green via TEST-ISO.** This manifest makes the post-gate deletion a scripted apply+verify, NOT a discovery exercise. Re-grep the dynamic-confirmation block at apply time (the tree moves under W2.2/W2.3/W2.5b/TEST-ISO merges before Wave 4 opens).
> Convention basis: single-`001`-per-product + **lock-step additive core migration** (`KB § PATTERNS/database-rls.md`, memory `feedback_single_001_migration` + `feedback_mcp_migrations_mirror_file`); ledger append-only (`feedback_durable_docs_self_contained`); KB↔CLAUDE↔INDEX pre-commit sync (`scripts/verify-kb-sync.sh`); `check_hardcoded_product_slug_set` keeper (`feedback_hardcoded_product_slug_set_keeper`).

---

## 0. Top-line facts (verified)

- **`media-scheduling` is ALREADY logically gone.** `git ls-files products/media-scheduling` = **0 tracked files**; the 229 MB on disk is pure untracked debris (`.DS_Store`, `.pytest_cache/`) left by `b91043f` (ms-merge, pre-branch). Its `backend/app/config.py` is absent. NO `git rm`, NO commit needed for the directory — a plain `rm -rf` of untracked dirt. **Only its REFERENCES survive** and must be scrubbed.
- **No surviving-code import blocker (BLOCKER = NO).** Zero `import`/`from` of `media_scheduling`/`youtube_crawler`/`imobi_scheduling`/`products.mailing` anywhere in surviving `products/`, `seed/`, `mcp/`, `noctusai_lib`. `products/social-wiring/` references the doomed slugs **only in docstring provenance lines** ("absorbed from imobi-scheduling, Wave 2.3") — not imports. Deletion does not break any Python import graph.
- **`mailing` + `youtube-crawler` have NO core product-registration migration.** Only `media-scheduling` (`013`) and `imobi-scheduling` (`028`) have dedicated `INSERT INTO public.products` migrations. `mailing`/`youtube-crawler` were never given a core seed-row migration (registered live-only or never dashboard-listed). So the new teardown migration DELETEs **only 3 slugs' rows** (`media-scheduling`, `imobi-scheduling`, and `youtube-crawler`/`mailing` defensively via `slug IN (...)` — harmless no-op if absent).
- **Port-collision context:** `start.sh` line 54 `imobi-scheduling:…:8011:8160` and line 56 `social-wiring:…:8011:8160` both claim 8011/8160. Deleting the `imobi-scheduling` line frees the collision (W0.3 carried this transient; build paused).
- **`scripts/update-kb-counts.py` line 49-50** still lists `("YouTube Crawler", "products/youtube-crawler")` + `("Imobi Scheduling", "products/imobi-scheduling")` + `("Mailing","products/mailing")` (line 46). `media-scheduling` already removed from that list. Auto-derived KB count blocks regenerate via the pre-commit hook → those count cells in `02-LANDSCAPE.md` self-update; the list entries themselves are the manual scrub.

---

## 1. Per-product deletion paths

| Slug | Path | git rm needed? | Sub-dirs of note |
|---|---|---|---|
| `media-scheduling` | `products/media-scheduling/` | **NO** (0 tracked files; `rm -rf` untracked debris) | none tracked |
| `youtube-crawler` | `products/youtube-crawler/` | YES (`git rm -r`) | `products/youtube-crawler/projects/youtube-crawler-domain-implementation/` ⚠ unique history (see §3 RISK-A) |
| `mailing` | `products/mailing/` | YES (`git rm -r`) | `products/mailing/projects/mailing-wiring/` ⚠ unique history (RISK-A); `products/mailing/proposals/evaluations/20260419-014952-mailing/` (5 files, 32 KB — eval set) |
| `imobi-scheduling` | `products/imobi-scheduling/` | YES (`git rm -r`) | `products/imobi-scheduling/projects/` = `.gitkeep` only (no unique content) |

---

## 2. Every reference site (file:line) + sanitization action

### 2.1 Compose / ops scripts

| Site | Slug(s) | Action |
|---|---|---|
| `docker-compose.yml:40` `- products/mailing/docker-compose.yml` | mailing | `delete-line` |
| `docker-compose.yml:43` `- products/imobi-scheduling/docker-compose.yml` | imobi | `delete-line` |
| `docker-compose.yml:44` `- products/youtube-crawler/docker-compose.yml` | youtube | `delete-line` |
| `start.sh:51` `"mailing:Mailing:8006:8120"` | mailing | `delete-line` |
| `start.sh:54` `"imobi-scheduling:Imobi Scheduling:8011:8160"` | imobi | `delete-line` (frees 8011/8160 for social-wiring) |
| `start.sh:55` `"youtube-crawler:YouTube Crawler:8008:8150"` | youtube | `delete-line` |
| `stop.sh` | — | none (no slug refs; iterates start.sh array) |
| `docker-compose.infra.yml` | — | none (no slug refs) |
| media-scheduling | — | **already absent** from compose/start.sh/stop.sh (b91043f) — no action |

### 2.2 Ports registry source — `mcp/noctusai/tools/noctus/dev/scaffold.py`

| Line | Content | Action |
|---|---|---|
| `431` `(8006, "mailing"),` | `delete-line` |
| `434` `(8010, "youtube-crawler"),` | `delete-line` |
| `435` `(8096, "media-scheduling"),` | `delete-line` |
| `443` `(8120, "mailing"), # Mailing frontend` | `delete-line` |
| `446` `(8140, "media-scheduling"), # Media Scheduling frontend` | `delete-line` |
| `447` `(8150, "youtube-crawler"), # YouTube Crawler frontend` | `delete-line` |
| (imobi 8011/8160) | NOT present in scaffold.py registry (collision was start.sh-only) — no action; but **add `social-wiring` registry rows** if not yet present (W0.3 added start.sh only — confirm at apply time) |

AST note: this is a Python literal list (`PORT_REGISTRY` tuples). Per AST-first this is a `libcst` list-element removal, not sed. At Wave-4 apply, run `cd mcp/noctusai && pytest tests/test_scaffold.py` as the oracle (`available_ports` derives from this list).

### 2.3 Scripts

| Site | Action |
|---|---|
| `scripts/propagate-dockerfiles.sh:28` `("mailing", "8006"),` | `delete-line` (and `:30` `("imobi-scheduling","8011"), ("youtube-crawler","8008"),`) |
| `scripts/propagate-composes.sh:20` `("mailing","8006"),` + `:22` `("imobi-scheduling","8011"), ("youtube-crawler","8008"),` | `delete-line` (each tuple) |
| `scripts/update-kb-counts.py:46` `("Mailing","products/mailing"),` | `delete-line` |
| `scripts/update-kb-counts.py:49` `("YouTube Crawler","products/youtube-crawler"),` | `delete-line` |
| `scripts/update-kb-counts.py:50` `("Imobi Scheduling","products/imobi-scheduling"),` | `delete-line` |
| `scripts/update-kb-counts.py:157` schema-list `"mailing"` literal | `delete-token` from the schema tuple (verify exact tuple at apply) |
| `scripts/bootstrap-worktree.sh:118` comment naming `imobi-scheduling, youtube-crawler` as lockfile examples | `mark-retired-with-dated-fact` (swap example slugs to surviving products; comment-only, non-functional) |
| `scripts/init-local-db/01-schemas.sql:23-24,26-27,38-39` (imobi/mailing/youtube `CREATE SCHEMA`) + `scripts/init-local-db/02-migrations.sql:4650-5856,7909-7989` (full imobi+mailing+youtube schema bodies) | **`regenerate-artifact`** — these are GENERATED by concatenating `products/*/backend/migrations/*`; do NOT hand-edit. Re-run the local-db generator (the script that produces `scripts/init-local-db/`) AFTER the product dirs are deleted so they drop out naturally. Confirm generator name/path at apply time. |

### 2.4 Core product-registration migration (NEW additive migration — NOT a historical edit)

- **Mechanism (verified against convention):** historical migrations `013_seed_media_scheduling_product.sql` + `028_seed_imobi_scheduling_product.sql` are **immutable history** (single-001 + lock-step-additive: phases edit `001` in-place, live-DB deltas are NEW numbered files — `feedback_single_001_migration` / `feedback_mcp_migrations_mirror_file`). The dashboard reads `public.products` dynamically; a deleted product must be UN-registered by a **new forward migration**, not by deleting `013`/`028`.
- **Action: `new-migration-to-DELETE-rows`** — create `products/core/backend/migrations/033_retire_consolidated_products.sql`:
  ```sql
  -- 033 — Retire products consolidated into social-wiring (Wave 4, social-wiring-absorption)
  DELETE FROM public.products
  WHERE slug IN ('media-scheduling','imobi-scheduling','youtube-crawler','mailing');
  ```
  (`youtube-crawler`/`mailing` rows likely never existed — `DELETE … WHERE slug IN` is an idempotent no-op for absent slugs; included defensively + documents intent.)
- **Mirror to live DB** via Supabase MCP `apply_migration` (the "MCP migrations mirror the file" rule) — operator step, same change-set.
- Leave `013`/`028`/`032` files **untouched** (history).

### 2.5 KB docs (`KNOWLEDGE-BASE/CONTEXT/...`)

| File:line | What | Action |
|---|---|---|
| `02-LANDSCAPE.md:16` Mailing product-table row | `delete-line` (row) |
| `02-LANDSCAPE.md:19` YouTube Crawler row | `delete-line` (row) |
| `02-LANDSCAPE.md:20` Imobi Scheduling row | `delete-line` (row) |
| `02-LANDSCAPE.md:50` `Schemas (11): … mailing … youtube_crawler … imobi_scheduling` | `update-derived-count` — drop the 3 schema tokens; recompute count (11→8 unless social-wiring schema added; verify) + **add `social_wiring`** row/schema if Wave 2 hasn't |
| `chatbot-operational-readiness.md` (11 lines: §9 "First adopter — imobi-scheduling", lines 17-18,55,95,253-265) | `re-home-content` — imobi-scheduling is the *first adopter / canonical reference*; its files are absorbed into `products/social-wiring/app/modules/scheduling/`. Rewrite §9 + the `products/imobi-scheduling/backend/app/services/retry.py` etc. file-paths to the social-wiring `scheduling` module paths; preserve the pattern, re-anchor the dated fact ("first adopter imobi-scheduling, absorbed into social-wiring 2026-05-16"). NOT a delete — the pattern is durable. |
| `digest-seed.md:27,34` `mailing/campaign_debrief_service.py → CampaignDebriefService`; `extra` carries `campaign_id` for mailing | `re-home-content` — mailing's digest is absorbed into `social-wiring/app/modules/email_marketing/`; update the adopter path; keep the 4-adopter cluster narrative with the dated re-home fact |
| `scheduling-seed.md:229` "Future: `projects/imobi-scheduling-bot-creation/` Phase 7 — first consumer wiring" | `mark-retired-with-dated-fact` — anchor to a dated fact ("first consumer was imobi-scheduling, absorbed into social-wiring/scheduling 2026-05-16"); do NOT leave a dangling project-path pointer (durable-docs-self-contained) |
| `seed-fake-real-adapter.md` (6), `llm-bot-security.md` (6), `webhook-signatures.md` (2), `database-rls.md` (3), `containerization.md` (3), `branching-and-merging.md` (3), `methodology-codification-pipeline.md` (2), `ast.md` (1), `lgpd.md` (1), `mcp-tool-conventions.md` (1), `project-execution.md` (1), `seed-workspace.md` (1), `whatsapp-chatbot-seed.md` (1), `04-SHARED-LIBRARY.md` (5), `03-SEED-ARCHITECTURE.md` (4), `06-AGENTS.md` (2), `backend/04-DATABASE.md` (1), `backend/05-AI-FEATURES.md` (5), `AGENT-CONTEXT.md` (1), `GUIDES/deploy-workspace-online.md` (1), `GUIDES/new-product.md` (1) | **TRIAGE-AT-APPLY** — most are *generic-example* mentions ("e.g. mailing's webhook", "products like imobi") that are durable as illustrations; `mark-retired-with-dated-fact` ONLY where the slug names a now-deleted path as a *live pointer*. Each must be eyeballed at apply (a slug-as-illustration is fine; a slug-as-path-to-deleted-file is a dangling ref). Counts are upper bounds, not all actionable. |
| `INDEX.md` (3) | verify no doomed-product KB file is indexed (none exist) — likely a generic mention; `mark-retired-with-dated-fact` only if a stale pointer |

### 2.6 CLAUDE.md + CLAUDE/*.md

| File:line | Action |
|---|---|
| `CLAUDE.md:107` digest-seed pointer "4-adopter cluster — core/audit, daily-life/weekly-review, **mailing/debrief**, PF/narrative" | `re-home-content` — update "mailing/debrief" → "social-wiring/email-marketing-debrief"; same-commit with `digest-seed.md` (doc-code coherence) |
| `CLAUDE.md:112` chatbot-operational-readiness pointer "first adopter imobi-scheduling; therapy/mailing/PF inherit" | `re-home-content` — re-anchor to social-wiring/scheduling; same-commit with `chatbot-operational-readiness.md` |
| `CLAUDE/platform.md:12` slip example "Slip surfaced 2026-05-05 by `media-scheduling` (on disk, missing from dashboard)" | `mark-retired-with-dated-fact` — keep the methodology, the slip is a durable dated fact ("surfaced 2026-05-05 by media-scheduling, since consolidated"); harmless historical reference, NOT a dangling pointer — **lowest priority / optional** |

### 2.7 Seed test fixtures (the W3.5 / W5.9a slug-literal sites — HIGHEST HAZARD)

| File:line | Content | Action |
|---|---|---|
| `seed/lib/backend/tests/config/test_per_product_cors_sentinel.py:60-69` **frozen `PRODUCT_SLUGS` tuple** containing `imobi-scheduling`, `mailing`, `youtube-crawler` | **`scrub-slug-literal`** — this is the **W5.9a-identified live true-positive** of `check_hardcoded_product_slug_set`. The test `exec_module`s each `products/<slug>/backend/app/config.py` → **`FileNotFoundError` the instant the dirs are deleted**. Root fix (already prescribed by the file's own comment + the keeper): derive `PRODUCT_SLUGS` from `parse_products_registry()` (already imported line 38) instead of the frozen tuple. MUST land in the SAME commit as the product-dir deletion + start.sh scrub. |
| `seed/lib/backend/tests/test_product_urls.py:21-77` (~9 sites: all use `"media-scheduling"` + `8140` as the test slug) | `scrub-slug-literal` — these are *unit* tests of `resolve_product_url()` using `media-scheduling` purely as an arbitrary slug fixture (no filesystem read). They will NOT fail on deletion (pure-string logic), but the literal is stale. Action: swap fixture slug to a surviving product (e.g. `erp-imobiliario`) OR a synthetic `"test-product"`. **Low hazard (won't break), medium hygiene.** |
| `seed/lib/backend/tests/config/test_cors_registry.py:280-281` comment about `media-scheduling`/`b91043f` | `mark-retired-with-dated-fact` — comment-only; harmless; optional |
| `seed/lib/backend/tests/test_oauth.py:189` comment "parity with `products/media-scheduling/.../oauth.py`" | `mark-retired-with-dated-fact` — comment-only; the parity is now with seed `security/oauth`; optional |
| `seed/lib/backend/tests/test_email_digest.py:149` comment (youtube-crawler provenance) | `mark-retired-with-dated-fact` — comment-only; optional |
| Seed **lib SOURCE** docstring mentions — `noctusai_lib/api/product_urls.py:13-22`, `testing/fixtures.py:5`, `testing/framework_test_suites.py:41-149`, `integrations/email/digest.py:30`, `noctusai_seed/dev_auth.py:9`, + the ~25 other `grep -l` hits under `seed/lib/backend/noctusai_lib/` | **NO ACTION REQUIRED for correctness** — all verified docstring/provenance/example-only ("Lifted verbatim from seed/adconnect/media-scheduling/youtube-crawler shape"), zero functional refs, zero imports, zero assertions. Optional `mark-retired-with-dated-fact` for provenance hygiene; NOT on the critical path; do NOT let these expand Wave-4 scope. |

### 2.8 `seed/framework/frontend/vite.config.factory.ts` PRODUCT_MAP

| Line | Content | Action |
|---|---|---|
| `82` `8120: { backend: 8006, schema: "mailing" }, // mailing` | `delete-line` (TS object entry → `ts-morph`, not sed; AST-first). No imobi/youtube/media entries present (only mailing). Add `social-wiring` entry if Wave 2/6 hasn't. |
| `13` docstring example `port: 8120, backendPort: 8006` (mailing's ports) | `mark-retired-with-dated-fact` — swap to a surviving product's ports in the doc example; comment-only |

### 2.9 accept-with-rationale.md (`KNOWLEDGE-BASE/CONTEXT/PATTERNS/accept-with-rationale.md`)

Durable register — **survives project folder deletion by design; do NOT bulk-delete.** 28 doomed-slug lines across 3 section headers + scattered scope lines.

| Site | Action |
|---|---|
| `:429` `## Entries from \`media-scheduling-port-resume\` (closed 2026-05-04)` section | `mark-retired-with-dated-fact` — these are CLOSED-project rationale entries; the *decisions* are durable. Re-anchor any `products/media-scheduling/...` path to the absorbed social-wiring path OR mark "(product consolidated into social-wiring 2026-05-16; rationale retained as dated record)". Do NOT delete the entries. |
| `:471` `## Entries from \`seed-hardening-from-youtube-crawler\`` section | `mark-retired-with-dated-fact` — same: dated record, re-anchor paths |
| `:532` `## Entries from \`mailing-wiring\` Phase 2 (filed 2026-05-11)` section | `mark-retired-with-dated-fact` — **these 5 entries are the durable substance of the incomplete `mailing-wiring` project (RISK-A mitigation)** — they MUST survive; re-anchor `products/mailing/...` paths to `products/social-wiring/app/modules/email_marketing/...` |
| scattered scope lines `:105,:196,:257,:276,:324,:327` naming `products/mailing/...` or `mailing` in multi-product scope tuples | `re-home-content` — replace the `products/mailing/...` path token with the absorbed `social-wiring/app/modules/email_marketing/...` path; keep the entry (digest cluster, tsconfig, scheduler-consolidation, webhook-signature scope all still valid, just re-pathed) |

### 2.10 LGPD-WARNINGS.md

| Site | Action |
|---|---|
| `LGPD-WARNINGS.md:18` `[ ] imobi-scheduling.oauth_credentials stores plaintext Google OAuth refresh+access tokens … at products/imobi-scheduling/backend/app/services/calendar.py:SupabaseCalendarCredentialResolver` | **`re-home-content` (NOT delete) — SECURITY/LGPD, do NOT silently drop.** The plaintext-credential risk MIGRATES with the absorbed scheduling module. Verify whether `products/social-wiring/app/modules/scheduling/` (or the W2.5-decision product-local `services/credential_store.py`) still stores plaintext OAuth tokens; if yes → rewrite the entry to the new path (`products/social-wiring/backend/app/...`) and keep it OPEN; if the absorption resolved encryption → flip to resolved with the dated fact. **Route through `noctus.dev.lgpd_flag` if state is ambiguous (LGPD-first).** This is a Wave-4 hard sub-gate: an unresolved LGPD warning may NOT be lost to a path-delete. |

### 2.11 Append-only history (NO rewrite)

| Site | Action |
|---|---|
| `project-history/ledger.ndjson` (34 lines; slug fields `media-scheduling-port`, `seed-hardening-from-youtube-crawler`) | **`append-ledger-entry`** — append ONE new line recording the Wave-4 retirement of the 4 products (consolidated into social-wiring, social-wiring-absorption project). Do NOT rewrite/delete existing lines (append-only sanctioned durable index). |
| `dispatcher-inbox.md` | none (verified clean — no doomed-slug refs) |
| `.promotions/` at root | none (no root `.promotions/`; only `projects/social-wiring-absorption/reference/.promotions/` (in-home reference, stays) + `templates/seed-workspace-promotions-MANIFEST-TEMPLATE.md` (generic template, no slug)) |
| `seed/framework/backend/noctusai_seed.egg-info/SOURCES.txt` (currently `M` in git status) | none (verified no doomed-slug refs; regenerated artifact) |

---

## 3. Ordering + hazards

**RISK-A — unabsorbed in-noc project history at risk (FLAG, not a blocker, but requires an explicit pre-deletion action):**
Deleting `products/{mailing,youtube-crawler}/` destroys two **noc-internal closed/abandoned project records** that the W0.2 audit did NOT cover (W0.2 audited the *originating sibling workspace*, not in-noc product subtrees):
- `products/mailing/projects/mailing-wiring/PROJECT.md` (468 lines) — **Phases 0-2 ✅, Phases 3-5 PENDING (incomplete project)**. Substance partially durable: its 5 accept-with-rationale entries (§2.9 `:532`) survive in KB. The PROJECT.md itself is unique and **NOT in `project-history/ledger.ndjson`** (0 matches). **Action before W4.1 delete:** `noctus.dev.archive` it (git-mv to `archive/projects/<today>/`) OR append a ledger retirement entry capturing its disposition (Phases 3-5 superseded by absorption into `social-wiring/email_marketing`). Do NOT silently `rm`.
- `products/youtube-crawler/projects/youtube-crawler-domain-implementation/PROJECT.md` (361 lines) — **"Design draft — needs user interrogation before Phase 1"** (never executed; fully superseded by social-wiring). Lower value; minimum action = ledger retirement entry noting "design-draft, superseded, never executed."
- `products/mailing/proposals/evaluations/20260419-014952-mailing/` (5 files, 32 KB) — closed proposal-evaluation set; low value; bundle into the same archive/ledger action.

**HAZARD-1 — same-commit atomicity (KB-sync + keeper + collection):** The following MUST land in ONE commit (the pre-commit hook + test collection will otherwise red):
1. `products/{youtube-crawler,mailing,imobi-scheduling}/` `git rm -r` **+** `seed/lib/backend/tests/config/test_per_product_cors_sentinel.py` registry-derive fix (§2.7) — else `FileNotFoundError` on `exec_module` (this is the live `check_hardcoded_product_slug_set` true-positive; W5.9a flagged it).
2. KB doc re-homes (`02-LANDSCAPE.md`, `chatbot-operational-readiness.md`, `digest-seed.md`, `scheduling-seed.md`) **+** their CLAUDE.md pointer twins (`CLAUDE.md:107,:112`) — doc-code-coherence; verify-kb-sync.sh blocks dangling `KB §` pointers.
3. `start.sh` + `docker-compose.yml` line-deletes + `scaffold.py` port-registry libcst removal + `update-kb-counts.py` list-trim — the auto-count regeneration (`update-kb-counts.py` runs in pre-commit) must see a consistent product set.

**HAZARD-2 — core-migration BEFORE dir-delete (live-DB ordering):** Author + `apply_migration` `033_retire_consolidated_products.sql` (§2.4) and mirror to the live DB **before or with** the dir deletion, so the dashboard never points at a 404'd product. File-and-live must move together ("MCP migrations mirror the file").

**HAZARD-3 — generated artifacts re-generate, NOT hand-edit:** `scripts/init-local-db/{01-schemas,02-migrations}.sql` (§2.3) are concatenations of `products/*/backend/migrations/*`. Delete the product dirs FIRST, then re-run the local-db generator so imobi/mailing/youtube schema blocks drop out naturally. Hand-editing 1200+ generated SQL lines = error-prone + drifts on next regen.

**HAZARD-4 — LGPD warning must not be path-deleted (security sub-gate):** §2.10 — the imobi `oauth_credentials` plaintext-token LGPD entry migrates with the absorbed scheduling code. It must be re-homed (path-rewritten, status re-verified), not lost. Route through `noctus.dev.lgpd_flag` if ambiguous.

**HAZARD-5 — `media-scheduling` dir is untracked debris:** `rm -rf products/media-scheduling` (no `git rm`, not in any commit). Its references (scaffold.py `:435,:446`, `013` migration via the new `033`, `accept-with-rationale :429`, comment sites) are the only Wave-4 work for it.

**Surviving-code import blocker: NO** (verified §0). Nothing surviving imports a doomed product package.

**`social-wiring` registration sanity:** confirm at apply time that `social-wiring` is in `start.sh` (yes, line 56), has core migration `032` (yes), and is added to `scaffold.py` PORT_REGISTRY + `vite.config.factory.ts` PRODUCT_MAP + `update-kb-counts.py` + `02-LANDSCAPE.md` (W0.3 added start.sh only — the others are Wave-4/Wave-6 adds, NOT scrubs; track but out of pure-teardown scope).

---

## 4. Ordered copy-paste teardown checklist (Wave-4 executes post-gate)

> Re-run §0 dynamic confirmations first (tree moved under W2/TEST-ISO merges). All from repo root `/Users/rapha/Documents/repository/NoctusAI/noctusai`. Engineers stage; architect commits (zero engineer git ops).

```
# 0. Pre-flight
git fetch origin && git rev-parse HEAD                       # confirm Wave-2-full-green merged
bash scripts/disk-usage-monitor.sh                            # pre-dispatch gate

# 1. Preserve at-risk in-noc history (RISK-A) — BEFORE any rm
#    archive OR ledger-record mailing-wiring + youtube-crawler-domain + mailing eval set
#    (use noctus.dev.archive on the two PROJECT.md trees, or append ledger lines)

# 2. Author core un-registration migration (HAZARD-2) — file + live together
#    create products/core/backend/migrations/033_retire_consolidated_products.sql  (§2.4 SQL)
#    Supabase MCP apply_migration  (mirror to live DB)

# 3. Code/config scrubs (single coherent commit — HAZARD-1)
#    - libcst: remove scaffold.py PORT_REGISTRY lines 431,434,435,443,446,447
#    - ts-morph: remove vite.config.factory.ts:82 mailing entry
#    - line-delete: docker-compose.yml 40,43,44 ; start.sh 51,54,55
#    - line-delete: propagate-dockerfiles.sh 28/30 ; propagate-composes.sh 20/22
#    - line-trim: update-kb-counts.py 46,49,50 + schema literal :157
#    - registry-derive fix: test_per_product_cors_sentinel.py PRODUCT_SLUGS -> parse_products_registry()
#    - swap stale fixture slug: test_product_urls.py (media-scheduling -> surviving/synthetic)

# 4. Delete product trees
rm -rf products/media-scheduling                              # untracked debris, no git
git rm -r products/youtube-crawler products/mailing products/imobi-scheduling

# 5. Doc re-homes (same commit as 3 where KB<->CLAUDE paired — HAZARD-1.2)
#    - 02-LANDSCAPE.md rows :16,:19,:20 + schema count :50
#    - chatbot-operational-readiness.md §9 + paths ; CLAUDE.md:112
#    - digest-seed.md :27,:34 ; CLAUDE.md:107
#    - scheduling-seed.md:229 dated-fact ; CLAUDE/platform.md:12 (optional)
#    - accept-with-rationale.md §429/§471/§532 + scope lines (re-home, NOT delete)
#    - LGPD-WARNINGS.md:18 re-home + re-verify (HAZARD-4; lgpd_flag if ambiguous)

# 6. Regenerate generated artifacts (HAZARD-3) — AFTER step 4
#    re-run the scripts/init-local-db generator

# 7. Append ledger retirement entry
#    project-history/ledger.ndjson  += one line (4-product retirement, append-only)
```

## 5. Post-teardown verification command set

```bash
cd /Users/rapha/Documents/repository/NoctusAI/noctusai

# A. Zero dangling slug refs in functional surfaces (expect: empty)
grep -rn -E "media-scheduling|youtube-crawler|imobi-scheduling|\bmailing\b" \
  docker-compose.yml start.sh stop.sh \
  mcp/noctusai/tools/noctus/dev/scaffold.py \
  scripts/propagate-dockerfiles.sh scripts/propagate-composes.sh scripts/update-kb-counts.py \
  seed/framework/frontend/vite.config.factory.ts \
  | grep -v "social-wiring-absorption/reference/"        # reference/ legit-retains copies

# B. No surviving Python import of a doomed product (expect: empty)
grep -rn -E "from (products\.)?(media_scheduling|youtube_crawler|imobi_scheduling)|products\.mailing" \
  --include="*.py" products/ seed/ mcp/ | grep -v "social-wiring-absorption/reference/"

# C. KB <-> CLAUDE <-> INDEX sync (expect: exit 0)
bash scripts/verify-kb-sync.sh
python scripts/update-kb-counts.py --check

# D. Keeper: hardcoded-slug-set true-positive resolved (expect: 0 findings on the sentinel)
#    via noctus.dev.review / compliance.check_hardcoded_product_slug_set

# E. Test oracle (the segmented-construction blind-spot — pytest is the oracle, not grep)
cd mcp/noctusai && pytest tests/test_scaffold.py -q          # available_ports registry
cd /Users/rapha/Documents/repository/NoctusAI/noctusai
( cd seed/lib/backend && pytest tests/config/test_per_product_cors_sentinel.py tests/config/test_cors_registry.py tests/test_product_urls.py -q )
( cd products/core/backend && pytest -q )                    # control-plane green post-033
( cd products/social-wiring/backend && pytest -q )           # absorber green

# F. Frontend build (surviving + absorber)
( cd products/core/frontend && npx vite build )
( cd products/social-wiring/frontend && npx vite build )

# G. Compose still valid (4 includes removed)
docker compose -f docker-compose.yml config -q
docker compose -f docker-compose.infra.yml config -q

# H. Ledger append-only intact (expect: only +1 line vs pre-teardown)
git diff --stat -- project-history/ledger.ndjson
```

---

## 6. Reference-site count summary (per product, actionable vs. cosmetic)

| Slug | Functional/actionable sites | Cosmetic (comment/docstring/example) | Notes |
|---|---|---|---|
| `media-scheduling` | ~9 (scaffold.py ×2, new `033`, test_product_urls fixtures, accept-wr §429) | ~6 (test comments, CLAUDE/platform.md, seed-lib docstrings) | dir = untracked debris (no git rm) |
| `youtube-crawler` | ~10 (compose, start.sh, scaffold.py ×2, propagate ×2, update-kb-counts, 01/02 generated SQL, accept-wr §471) | ~8 (seed-lib docstrings, test comments) | RISK-A: in-noc design-draft project |
| `mailing` | ~16 (compose, start.sh, scaffold.py ×2, propagate ×2, update-kb-counts ×2, vite-map, generated SQL, digest-seed, CLAUDE:107, accept-wr §532 + scope ×6) | ~10 (generic-example KB mentions) | RISK-A: incomplete `mailing-wiring` (Ph 3-5 pending) + eval set; substance partly durable in accept-wr |
| `imobi-scheduling` | ~14 (compose, start.sh, propagate ×2, generated SQL block ~big, `033`, chatbot-op-readiness §9, scheduling-seed:229, CLAUDE:112, cors-sentinel literal, **LGPD-WARNINGS:18**) | ~5 (mcp/workspace.py comment, test comments) | LGPD security sub-gate (HAZARD-4); frees 8011/8160 collision |

**Manifest path:** `projects/social-wiring-absorption/.integration-holding/WAVE4-TEARDOWN-MANIFEST.md`
