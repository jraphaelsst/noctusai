# Deploy-Hardening & Dev/Prod Isolation — Project Document

> Living document. Born 2026-05-21 from the production-deploy session: the user asked to (a) codify a safe VPS code-sync methodology, (b) add creative defense-in-depth so production code can never be damaged/reversed/half-deployed, (c) implement a pre-deploy verification gate that *learns* from failures, and (d) separate dev from prod data — currently local dev and the VPS share ONE Supabase project.

- **Created:** 2026-05-21
- **Last updated:** 2026-05-22
- **Status:** **ALL 6 phases ✅ + close-out deploy live (2026-05-22).** 1 (safety-net doc) · 2 (de-track — **VPS migration DONE**) · 3 (prod branch — VPS on `origin/prod`) · 4 (predeploy_check — **P5 interpreter false-block FIXED**) · 5 (DB decision + One Permutas RLS FIXED) · 6 (Supabase MCP, live). `prod`/VPS at `9f80d550`; `main` at `182e7e59` (a test-only catalog fix ahead, rides the next promotion). **Close-out deploy:** promoted `9f80d550` → `prod` → VPS via the §2a drill (C1 backup ref+tar; config.yml+creds migrated → working tree now clean; fleet healthy, no rebuild). **Safety matrix asserted P1–P5 / D1–D4 / C1 / C2 / C3 all live** (C2 = `noctus.dev.deploy_image`, the atomic-rollback redeploy tool, shipped 2026-05-22). **Edge audit (corrected):** all DEPLOYED products are live under the user's short public slugs — `noctusai.com`/`core.`/`erp.`/`social.`/`n8n.`/`waha.`/`legacy.` all serving (an earlier "DNS gap" was a probe of the wrong long hostnames). Remaining = user-dependent: PAT rotation (pasted in chat) · `.mcp.json` supabase registration **DONE** (effective next session) · local `supabase/` cleanup (explained; awaiting go) · **personal-finance + therapy-platform not deployed** (no container/vhost — a full build+run+edge deploy, not a DNS add).
- **Owner / stakeholders:** Rapha (devops learner — teach-while-doing) · Claude
- **Related docs:** `KB § GUIDES/production-deploy.md` (§2a drill + safety-net stack — the authority) · `KB § PATTERNS/containerization.md § 12b` · `[[reference_production_deploy_runbook]]` · `CLAUDE/platform.md` (MCP-first)
- **Project slug:** `deploy-hardening-and-dev-isolation` (root `projects/` — cross-cutting: deploy methodology + seed DB layer + new MCP connector + dev toolkit)

---

## 1. Context & Purpose

The fleet is live on `noctusai.com` (Hostinger VPS, Caddy interim edge, CF tunnel pre-staged). The VPS checkout is **production**, reached only by `git pull`. The §2a drill (inspect → decide → `ff-only` → verify) was just codified. The user wants this hardened past "proven moves" into structural defense-in-depth so the production code is treated as a diamond — and wants the dev workflow made genuinely safe.

Two active risks surfaced this session, both evidence-backed:
1. **`deploy/tunnel/config.yml` is git-tracked AND edited-in-place on the VPS** (`git ls-files` confirms tracked; `git status` shows it `M` every deploy) → every pull has to "dance around" a tracked deploy-local file. One wrong `reset --hard`/`checkout --` wipes the live tunnel config.
2. **Local `.env` and the VPS `.env` both point at Supabase project `nyplttplcoyiiqjrvtiw`** (verified, masked) with no env marker → **local dev currently reads/writes production data.** git isolates *code*, not the *database*.

Win = a deploy pipeline where no single mistake can damage prod, only-functional code can go online, and dev work is provably isolated from prod data.

---

## 2. Confirmed constraints

- **The VPS code is "a diamond"** — *(treat code-preservation as paramount; be creative for edge cases/drift, not only proven nets. User: "always-only have production functional code online and preserve the repo from getting damaged or reversed or anything destructive.")*
- **Dislikes "git = the only wall" between dev/prod** — *(wants an extra structural layer. User idea: a `prod` branch the VPS alone pulls; code promoted to `prod` only when 100% ready. Rules out main-tracked-VPS as the only gate.)*
- **Pre-deploy gate must LEARN** — *(auto-fix known classes in-process; where not code-fixable, emit reports a human/future agent can act on. Same always-hardening mindset.)*
- **DB: separate dev/prod; never lose control of Supabase** — *(user proposed SQLite-local / Supabase-prod; ALSO wants a self-owned Supabase MCP to manipulate the project from home on-demand, "without actually calling supa's real mcp." "aproveitar" → EN: take advantage of / make the most of / seize the opportunity.)*
- **Own Supabase MCP, not the managed one** — *(consistency with the every-connector-owns-its-auth-store pattern: github/n8n/waha/hostinger/cloudflare. `.mcp.json` registration is user-gated per the MCP keep-list.)*
- **Commit + push after the last piece (the Supabase MCP).** *(Doc/methodology phases may commit incrementally; the build phases land their own commit.)*

---

## 3. Design principles

1. **Defense in depth, not a single gate** — preventive ∧ detective ∧ corrective nets, so the failure of any one is caught by another.
2. **Nothing-to-clobber beats careful-clobbering** — gitignore deploy-local files so a pull *cannot* touch them by construction (root fix > procedural care).
3. **Only-functional-code-online** — a verification gate is a precondition of promotion, not an afterthought.
4. **dev/prod parity for the DB engine** — local dev should run the *same engine* (Postgres) as prod with *isolated data*; a different engine (SQLite) re-introduces the "works-locally-breaks-in-prod" class the boundary-contract methodology already fights (see §7 Q1).
5. **Every new mechanism is MCP-first** (`noctus.dev.*` / a `mcp/supabase` connector composing `mcp/_kit`), never a bare `scripts/` one-off — per `KB § PATTERNS/mcp-first-scripts.md`.

---

## 3a. Seed-first analysis

1. **Contract identical for every product?** YES — every product reaches Supabase through `noctusai_lib` + `create_product_app`; DB-env selection + the deploy pipeline are uniform. **Per-product code = 0.**
2. **Data source product-specific?** NO — the DB connection config is platform-uniform (env-driven).
3. **Placement product-specific?** NO — deploy methodology = KB GUIDE; DB config = seed; pre-deploy + Supabase ops = MCP toolkit.
4. **Visibility/permission rule same?** YES — uniform (deploy = root; MCP auth = connector `.env`).
5. **Seam already in seed?** PARTIAL — `resolve_credential` / env config exist; a clean **`APP_ENV`-driven Supabase-target selector** is the new seam. `mcp/_kit` exists for the connector. The pre-deploy tool extends `noctus.dev.*`.
6. **Default-on or opt-in?** DEFAULT-ON (safety nets + env separation are universally beneficial).

**Litmus:** 0 per-product lines — all changes land in the deploy GUIDE, seed config, `mcp/supabase`, and `noctus.dev.*`. §6 phases work in seed/platform layers, never product-by-product. ✅ correctly seed-bounded.

---

## 4. Scope

**In scope:**
- §2a safety-net stack (P1–P5 / D1–D4 / C1–C3) — codify (done) + implement the ⏳ items.
- De-track deploy-local files (`config.yml` → gitignored + `.template` + render-on-deploy).
- `prod` promote-branch + GitHub branch protection + VPS tracks `origin/prod`.
- Pre-deploy verification + learning tool (`noctus.dev.predeploy_check`).
- DB dev/prod isolation (chosen approach in §7 Q1) + `APP_ENV` seam + `.env` separation.
- Self-owned Supabase MCP (`mcp/supabase` composing `_kit`) + KB doc + memory.

**Out of scope (for now):**
- Full CI/CD runner (GitHub Actions) — phased later; pre-deploy gate runs locally/on-VPS first.
- Migrating the managed `mcp__claude_ai_Supabase__*` off — keep as fallback; our connector is additive.
- Blue-green multi-host — single-VPS atomic image swap (C2) is enough at this fleet size.

---

## 5. Architecture / Data Model

- **Deploy GUIDE** `KB § GUIDES/production-deploy.md § 2a` — drill + safety-net stack (authority). ✅
- **De-track:** `.gitignore` += `**/tunnel/config.yml`; add `deploy/tunnel/config.yml.template`; `start.sh`/deploy renders `config.yml` from template + `.env` (tunnel id + creds path).
- **`prod` branch:** `git branch prod origin/main` → push; VPS `git config` tracks `origin/prod`; drill pulls `origin/prod`. GitHub branch protection (PR + checks, no force-push/delete) on `prod`+`main`.
- **`noctus.dev.predeploy_check`** (new MCP tool): for changed product(s) → build `--target runtime` + FE `vite build` + backend import-check + `pytest`; classify failures against known patterns (npm root-hoist, pip framework-implicit, VITE-baked-localhost — `KB § PATTERNS/boundary-contract-tests.md`); known class → suggest/auto-apply fix; unknown → write `predeploy-reports/<utc>.md` + log `phase_learnings.db` (s1 of the codification pipeline). Colocated `Test*`.
- **Seed DB seam:** `APP_ENV` (`dev`|`prod`) selects the Supabase target (URL/keys) — dev → the isolated dev datastore (§7 Q1), prod → `nyplttplcoyiiqjrvtiw`. Implemented in the seed config layer; Fake unaffected.
- **`mcp/supabase`** (composes `mcp/_kit`): `supabase.project.*` (get/list), `supabase.db.{query,list_tables,...}` (Management API SQL), `supabase.migration.*`, `supabase.diagnostics.connection_status`; writes confirm-gated; token + project-ref in `mcp/supabase/.env` (gitignored). `.mcp.json` user-gated.

---

## 6. Implementation phases

### Phase 1 — Safety-net stack + safe-sync drill (doc) ✅ (2026-05-21)
- [x] §2a safe-pull drill (inspect → decide → `ff-only` → verify) in the deploy GUIDE
- [x] Safety-net stack P1–P5 / D1–D4 / C1–C3 + destructive-command ban
- [x] CLAUDE.md router row + `[[reference_production_deploy_runbook]]` memory (three-way sync)

**Improvements:**
- The safety-net stack interleaves ✅-live and ⏳-planned nets; the per-item icons carry the status, but a one-line legend at the top of the stack would stop a skim-reader assuming every net is already live.
- The destructive-command ban is a **deterministic predicate** (scan deploy GUIDEs/runbooks/scripts for `reset --hard origin` ∨ `checkout -- <deploy-local>` framed as a sync step) → Stage-4 keeper codification candidate once a 2nd deploy target exists (`s1→s4`, `KB § PATTERNS/methodology-codification-pipeline.md`).
- §2a now lives canonically in the GUIDE while `[[reference_production_deploy_runbook]]` carries a compressed mirror → a known three-way-sync drift touchpoint; future §2a edits must update both (or trim the memory to a pure pointer).

### Phase 2 — De-track deploy-local files (P4) ✅ (2026-05-22; repo-side + VPS migration DONE)
- [x] gitignore the rendered `config.yml` (`**/tunnel/config.yml`); rename tracked `config.yml` → `config.yml.template` (placeholders, no secrets); render-on-deploy documented (`cp`/`envsubst`)
- [x] document the safe one-time VPS migration (back-up → move-aside → `ff-only` pull → restore → verify ignored → reload tunnel) in `deploy/tunnel/README.md` — *execution is a VPS deploy action (§8); the rendered `config.yml` is now structurally un-clobberable*
- [x] D3 `deploy/STATE.json` manifest (deploy-local paths + `must_be_gitignored` + the destructive-command-ban invariant) — consumed by the §2a drill + `predeploy_check` (Phase 4)

**Improvements:**
- The fix is **structural, not procedural** — gitignoring the rendered file means even a wrong `reset --hard`/`checkout --` can't touch it (design principle 2 realized). The remaining residual risk is the *one-time* migration pull on the VPS (the file is still tracked there until that pull) — bounded by the documented back-up-first step; after it, the risk is gone forever.
- `STATE.json`'s invariants are **deterministic predicates** (`git check-ignore` HIT for each path; no `reset --hard origin`/`checkout -- <deploy-local>` framed as a sync step in deploy docs) → the same Stage-4 keeper candidate flagged in Phase 1's Improvements; `predeploy_check` (Phase 4) is the first consumer, a standalone keeper follows once a 2nd deploy target exists.
- `envsubst` render is offered as an *option* but the manual `cp`+fill is the documented default (the tunnel isn't live yet — Caddy is the current edge — so an automated renderer is premature; revisit at the Caddy→tunnel cutover).

### Phase 3 — `prod` promote-branch (P3) ✅ (2026-05-22; repo-side + docs; remote/UI/VPS handed off) — §7 Q2 = (A) `prod` branch
- [x] document the promote ritual + one-time cutover (`KB § GUIDES/production-deploy.md § 2b` — main=integration, prod=promotion gate, VPS pulls `origin/prod`; FF-only both hops; the user's "vps only accepts pulls from prod branch")
- [x] create the local `prod` branch off the live tip (`origin/main` = `6b23f4af`) — *push is the user-gated cutover step (phased-push), presented at handoff*
- [x] update §2a drill (notes the target flips to `origin/prod` post-cutover; deliberately stays `origin/main` until then — no lying about live state) + memory `[[reference_production_deploy_runbook]]`
- [x] **(1) push `prod`** → ✅ `origin/prod` = `6b23f4af` (the live sha; `prod` now tracks `origin/prod`)
- [x] **(2) branch protection** → server-side BLOCKED (GitHub branch-protection *and* rulesets need Pro on a private repo; free-private = 403). Shipped the **free client-side equivalent**: `scripts/hooks/pre-push` refuses force-push + deletion of `main`/`prod` (installed + tested: FF passes, rewind/delete/force blocked, non-protected branches untouched; `--no-verify` = deliberate bypass). Wired into `scripts/install-hooks.sh`.
- [x] **(3) SSH made a one-liner** → `~/.ssh/config` `Host noctus-vps` (`root@72.61.28.36`, the `noctusai-deploy` key) created; the repoint is now a single command. *The actual repoint is a production action gated on the user's "connect to the VPS" go (the auto-classifier correctly blocked an uninvited prod SSH); not a no-op unless the VPS HEAD already == `origin/prod`.*

- [x] **VPS repoint ✅ DONE 2026-05-22** (user: "repoint the vps") — `ssh noctus-vps`, ran the §2a inspect→decide→act→verify drill: VPS was on `main`@`26a7cedd` (clean-FF ancestor of `origin/prod`@`6b23f4af`); incoming diff = docs + mcp/supabase connector only (NO runtime code) → no rebuild. Backed up `config.yml` + tagged `backup/predeploy-20260522-103242`, switched to branch `prod` tracking `origin/prod`, deploy-local `config.yml`+creds preserved, fleet verified healthy (core 200; erp/social-wiring Docker-healthy; tunnel+caddy+services up).

**Improvements:**
- The two-hop FF invariant (`main`→`prod` FF-only ∧ VPS→`origin/prod` FF-only) means production can *only* advance along promoted history — the "extra layer beyond git=the-wall" the user wanted, realized structurally (a `main` push alone never reaches prod; a human must promote).
- **Learning (2026-05-22): server-side branch protection is paywalled on free-private.** GitHub branch-protection AND rulesets both return 403 "Upgrade to GitHub Pro or make this repository public" on a private free-tier repo. Since the user won't pay (consistent with the Supabase-no-Pro decision) and won't make the fleet repo public, server-side enforcement is unavailable. Resolved with a **client-side `pre-push` hook** (free, prevents accidents; `--no-verify` bypass for the rare deliberate case). Trade-off vs server-side: a determined local actor can bypass — acceptable for a solo-dev accident-guard; the read-only deploy key (P2) still makes the *VPS* incapable of any push. A `github.repo.protect_branch` MCP tool is moot until the repo is Pro/public.
- `prod` currently tracks `origin/main` locally (artifact of `git branch prod origin/main`); the push step re-tracks it to `origin/prod` (`git push -u origin prod`) — noted so the tracking isn't mistaken for a bug.

### Phase 4 — Pre-deploy verify + learning tool (P5) ✅ (2026-05-22)
- [x] `noctus.dev.predeploy_check <product>` (CLI `--predeploy-check`): composes framework-dep parity + frontend `vite build` + backend `pytest`; `status='ready'|'blocked'`, exit 0/1; injectable IO (`run_check`/`write_report`/`log_fn`/`fix_framework_deps`/`now`) → 10 colocated tests green, zero real builds
- [x] failure **classifier** (OPEN taxonomy — 4 known boundary-contract classes: npm-root-hoist / pip-framework-implicit / vite-baked-localhost / framework-dep-drift; non-match ⇒ `unknown`) + **auto-fix** the framework-dep class via `--fix` (composes the existing `check_framework_deps._fix`) + `predeploy-reports/<utc>-<product>.md` (gitignored) + `phase_learnings` s1 log for unknowns
- [x] **C1 (backup-ref) ✅ IMPLEMENTED + exercised at the 2026-05-22 close-out deploy** — `git tag -f backup/predeploy-<utc> HEAD` + `tar` the deploy-local files to `/opt/noctus/backups/<utc>.tgz` (refinement: outside the repo tree, not `deploy/backups/`, so a stray `git add` can't commit a backup). Plus an ERR-trap in the deploy script that auto-restores `config.yml` if any step fails mid-flight. **C2 (atomic image rollback) stays ⏳** — it only fires on a product-code/image-rebuild deploy; the close-out was docs/tooling-only (no image to swap). Named destination = the first product-code VPS deploy. *(Defer-with-destination, not silent skip — C2 is genuinely N/A until an image rebuilds.)* **→ ✅ DONE 2026-05-22: `noctus.dev.deploy_image` (the deploy-time corrective net), see change-log.**

**Improvements:**
- The classifier taxonomy is **OPEN by construction** (a non-matching failure → `unknown` → report + s1 log, never force-fit) — this is the codification on-ramp: a recurring `unknown` class graduates to a 5th `_KNOWN` entry, then to a keeper. First real consumer of the boundary-contract "if this contract drifts, what fails?" discipline as a runtime gate (vs authoring-time).
- Only the framework-dep class is *auto-fixable* today (it composes an existing safe fixer); source-mutating fixes (TS2307 → edit package.json, Pillow → edit requirements.txt) are SUGGESTED not applied — they need AST edits + per-class apply logic. Candidate `noctus.dev.*` extension once a class recurs enough to justify the AST-apply path (DRY N≥3).
- `predeploy_check` reads `deploy/STATE.json` conceptually (D3) but does NOT yet assert the deploy-local-gitignored invariants — wiring that assertion in is a cheap next add (the manifest + the `git check-ignore` predicate both already exist); deferred to the C1/C2 deploy-time batch to keep this phase's surface tight.

### Phase 5 — DB dev/prod isolation → RESOLVED-BY-DECISION ✅ (2026-05-21; separate dev DB descoped, 2-project architecture locked)
> **Decision (user; no pay, no 3rd project):** a free cloud dev project is impossible (Supabase 2-active-free cap; both slots are live apps) and the local stack rolls back under Docker 29.4.3 — so **dev runs against the `noctusai` project** (no separate dev DB). The 2-project architecture is the answer and was MCP-verified to ALREADY be correctly wired (no reshape needed): **noc fleet → `noctusai`** (`nyplttplcoyiiqjrvtiw`; control-plane tables `organizations`/`products`/`licenses`/…, RLS on) · **legacy → `One Permutas`** (`eourhjahxxkhozxmpyno`; Django `proprietario_*`/`imovel_*`/`permuta_*`; legacy container anon-key `ref` = `eourhjahxxkhozxmpyno`). User: *"we must use the noctusai project to build ours, no additional projects for now ... just reshape them"* — already in the desired shape.
- [x] Verify + lock the 2-project wiring (managed Supabase MCP `list_tables` on both + legacy container anon-key ref).
- [x] Descope the separate-dev-DB goal (no 3rd project, no Pro). **Accepted tradeoff:** running the live app locally hits `noctusai` prod data; the pytest loop stays isolated via the seed Fake (`MockSupabaseClient`).
- [x] Document free isolation escape-hatches, available on-demand (NOT blocking): (a) raw local Postgres+PostgREST via plain docker-compose — sidesteps the supabase-CLI/Docker-29 health-gate; (b) schema-separation within `noctusai`; (c) Pro cloud dev project.

> **🔴→✅ SECURITY (One Permutas) — FIXED 2026-05-22** (user: "apply the rls fix"). Was: RLS DISABLED on all 27 tables ∧ the anon key in the public React bundle ⇒ anyone with `legacy.noctusai.com` could read/write all property-owner data (LGPD). **Investigation proved it app-safe to enable:** the frontend's `supabase.ts` client is dead code (never imported) — all data flows via the Django `/api` (axios); Django connects direct-psycopg as `postgres` (`rolbypassrls=true`, owns all tables) ⇒ RLS does not affect it; `anon`/`authenticated` (PostgREST) do NOT bypass. **Applied** `ENABLE ROW LEVEL SECURITY` on all 27 tables (via our own `mcp/supabase` connector seam) → post-state RLS ON 27 / OFF 0; the `rls_disabled` ERROR advisory cleared (remaining `rls_enabled_no_policy` is INFO and INTENTIONAL — default-deny for the public roles; adding policies would re-open access). Reversible via `DISABLE ROW LEVEL SECURITY`. The noc fleet project (`noctusai`) was already clean.

**Improvements:**
- The "develop against prod" risk is bounded by the seed Fake for the *test* loop but NOT for *running the live app locally* — a `USE_FAKE_SUPABASE`/`APP_ENV=dev`→Fake seed seam would give a zero-cost, zero-infra local-run isolation (no DB at all locally). Candidate if the running-app-locally risk ever bites; cheaper than any of the 3 escape-hatches.
- The One Permutas RLS exposure is a recurring absorbed-product class (external app brought onto our infra with Supabase RLS off) — worth a deploy-time check (scan absorbed products' Supabase projects for `rls_disabled` advisories) if a 2nd external app is ever absorbed (N=1 today).

### Phase 6 — Self-owned Supabase MCP (`mcp/supabase`) ✅ (2026-05-21, commit `31fc8178`)
- [x] connector composing `_kit`: project/db/migration/diagnostics tools (8); confirm-gated writes
- [x] `mcp/supabase/.env.example` (PAT + project-ref); `KB § MCP-SERVERS/supabase.md` + memory; `.mcp.json` user-gated
- [x] **commit + push** (31fc8178; 23 tests green; salvaged from the engineer worktree via patch + verified on disk)

**Improvements:**
- `db.query`'s read/write gate is a best-effort leading-keyword heuristic (documented as NOT a security boundary); if a real safety boundary is ever needed, parse the SQL (sqlglot) instead of keyword-sniffing — deferred until a use-case demands it.
- The connector-MCP cluster is now N=7 (vista/github/n8n/waha/hostinger/cloudflare/supabase) all composing `_kit` identically — the `_kit` formalization is paying off (supabase added zero `_kit` changes); a `scaffold_connector` generator (mirroring `scaffold_mcp_tool`) would make connector #8 a one-command emit. Candidate for `noctus.dev.*`.
- ~~Live validation deferred~~ → ✅ **LIVE-validated 2026-05-22**: PAT pasted, wired to `mcp/supabase/.env` (gitignored; default ref `noctusai`), `request_json` seam authed OK (5 projects) + `project.get` + `db.query` read (`count(*) organizations` → 15) all returned live data through the connector's own code path. `.mcp.json` registration remains user-gated (the auto-classifier correctly blocked it as self-modification) — offered, takes effect next session restart. ⚠️ The PAT was pasted in chat → rotate once home-ops stable.

---

## 7. Open questions (the two forks gating Phases 3 & 5)

1. ✅ **RESOLVED 2026-05-21 → (B) local Supabase stack.** User initially asked for SQLite-local; on surfacing that the whole data layer speaks **PostgREST via `supabase-py create_client`** (`seed/lib/backend/noctusai_lib/integrations/database.py` — no SQL/ORM layer, so SQLite has no compatible driver path and would re-introduce the works-locally-breaks-in-prod class), the user chose the parity-preserving option. Options were:
   - **(A) separate dev Supabase project** — cloud, isolated, same engine, ~zero local setup.
   - **(B) local Supabase stack (`supabase start`)** ⭐ CHOSEN — real Postgres + PostgREST + Auth in Docker on localhost; offline, free, isolated, **same engine** ⇒ no parity surprises. Gives what "SQLite local" reached for, compatibly.
   - **(C) SQLite local** — ❌ rejected: ⚠️ parity risk (RLS, PostgREST filters, JSON ops, `gen_random_uuid`) + needs a full PostgREST-shaped adapter the codebase doesn't have.
2. ✅ **RESOLVED 2026-05-22 → (A) dedicated `prod` branch.** User: *"when any branch is 100% to go for main it goes to prod branch and the vps only accepts pulls from prod branch."* Implemented in `KB § GUIDES/production-deploy.md § 2b` (promote ritual + cutover). Options were:
   - **(A) dedicated `prod` branch the VPS tracks**, FF from blessed `main` ⭐ CHOSEN — explicit human promote gate; the extra layer beyond git=the-wall.
   - **(B) keep VPS on `main` + add branch protection / required PR + CI.** Lighter, fewer steps. *(Branch protection is folded into (A) anyway.)*
   - **(C) tag-based releases** (`deploy-vN` tags) the VPS checks out. Immutable, but no moving branch.

---

## 8. Dependencies & blockers
- **GitHub branch protection** (Phase 3) needs repo-admin in the GitHub UI (user) — the read-only deploy key can't set it.
- **Dev datastore** (Phase 5) needs the user to create the dev Supabase project (A) or run `supabase` CLI (B).
- **Supabase access token + project-ref** (Phase 6) in `mcp/supabase/.env` (user-provided; rotate-after per the secrets policy).

---

## 9. Success criteria
- A pull on the VPS can never damage deploy-local state or rewind prod, even with a wrong command (P4 makes it structural; C1/C2 make it reversible).
- Only code that passes `predeploy_check` reaches prod; failures auto-fix (known) or report (unknown).
- Local dev provably cannot read/write prod data (`APP_ENV` separation; `.env` split verified).
- Supabase is fully operable from home via `mcp/supabase` without the managed connector.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-21 | Project drafted after the production-deploy session. Phase 1 (safety-net stack + safe-sync drill) shipped to `KB § GUIDES/production-deploy.md § 2a` + CLAUDE.md router row + memory (commit `06828bf9`). Two risks evidenced (tracked `config.yml`; local==prod Supabase `nyplttplcoyiiqjrvtiw`). Phases 2–6 designed. | Claude |
| 2026-05-21 | §7 Q1 RESOLVED → local Supabase stack (user chose B after the PostgREST-vs-SQLite architecture finding). Phase 5 detailed. Starting build: Phase 6 (self-owned Supabase MCP) dispatched. | Claude |
| 2026-05-21 | **Phase 6 ✅ shipped** (`mcp/supabase`, commit `31fc8178`; 23 tests green). **Phase 5 🅿️ DEFERRED:** local stack rolls back under Docker 29.4.3 health-gates; free cloud dev project blocked by the 2-active-free-project cap (both slots are live apps — `create_project` failed with the limit error). User chose to keep developing on the NoctusAI project for now ("we're on the right direction"). Resume via Pro (~$25/mo cloud dev project) OR Docker-28 OR a Supabase-CLI fix for Docker 29. Caveat carried: local dev still shares prod DB until resumed. Also shipped this session: explanation-as-signal listener (commit `5ff6bd1a`). | Claude |
| 2026-05-21 | **Phase 5 → RESOLVED-BY-DECISION ✅** (user: no pay, no 3rd project, "just reshape them"). MCP-verified the 2-project architecture is ALREADY correctly wired — noc fleet → `noctusai` (control-plane tables, RLS on); legacy → `One Permutas` (Django tables; container anon-key ref confirmed). Nothing to reshape; separate-dev-DB descoped; dev runs on `noctusai`; isolation escape-hatches documented (not blocking). **🔴 SECURITY surfaced (not auto-fixed):** One Permutas has RLS disabled on all 27 tables + anon key in the public React bundle → legacy property-owner data (LGPD) publicly read/writable; remediation presented, named destination = user's one-permutas project. Used managed Supabase MCP for inspection; our own `mcp/supabase` awaits a PAT for live use. | Claude |
| 2026-05-22 | **Credential-class correction (verified vs tree):** root `.env` holds `SUPABASE_{ANON,SERVICE_ROLE}_KEY` = `eyJhbG…` JWTs (data-API keys for PostgREST), NOT a Management PAT (`sbp_…`); no `sbp_` token in any `.env`. Our `mcp/supabase` connector (Management API) can't use the existing key → stays Fake/awaiting-PAT; the managed Supabase MCP (account-OAuth, no `.env` key) is the working door, used for all DB ops this session. Also noted: org has 5 projects, 2 ACTIVE (`NoctusAI`, `One Permutas`), 3 paused — consistent w/ the Phase-5 cap finding. | Claude |
| 2026-05-22 | **Phase 2 ✅ (repo-side).** De-tracked the rendered tunnel `config.yml` → gitignored `**/tunnel/config.yml`; tracked artifact is now `config.yml.template` (placeholders only). Added `deploy/STATE.json` (D3 deploy-local manifest + invariants) + the safe one-time VPS migration runbook in `deploy/tunnel/README.md`. "Nothing-to-clobber" is now structural; VPS migration execution handed off (§8). GUIDE nets P4 + D3 → ✅. | Claude |
| 2026-05-22 | **Phase 3 ✅ (repo-side + docs).** §7 Q2 RESOLVED → (A) dedicated `prod` promote-branch. Added `KB § GUIDES/production-deploy.md § 2b` (promote ritual + one-time cutover; main=integration → prod=promotion gate → VPS pulls `origin/prod`; FF-only both hops). Created local `prod` branch off `origin/main` (`6b23f4af`). | Claude |
| 2026-05-22 | **One Permutas RLS FIXED + main pushed + VPS repointed** (user: "apply the rls fix, push main, then repoint the vps"). (1) Verified app-safe (frontend supabase client dead; Django=postgres bypasses RLS) → `ENABLE ROW LEVEL SECURITY` on all 27 tables via our `mcp/supabase` seam; RLS ON 27/0, `rls_disabled` ERROR advisory cleared. (2) Pushed `main` `6b23f4af..dfaf6dd4` (pre-push hook passed clean FF). (3) Repointed the VPS to `origin/prod` via `ssh noctus-vps` + the §2a drill (clean docs/connector-only FF 26a7cedd→6b23f4af, deploy-local preserved, `backup/predeploy-*` tag, fleet healthy). Docs synced: GUIDE §2a/§2b/P3 + memory. | Claude |
| 2026-05-22 | **Phase 4 ✅** — `noctus.dev.predeploy_check <product>` (CLI `--predeploy-check [--fix]`): composes framework-dep + `vite build` + `pytest`; OPEN-taxonomy classifier (4 boundary-contract classes); auto-fix the framework-dep class; report+`phase_learnings` s1 for unknowns. 10 colocated tests green; registry + cli wired; `predeploy-reports/` gitignored. GUIDE net P5 → ✅. C1/C2 scoped out (VPS-runtime corrective nets, deferred-with-destination to deploy-time). | Claude |
| 2026-05-22 | **Phase 3 handoff RESOLVED** (user: "resolve this for me"). (1) `prod` pushed → `origin/prod`=`6b23f4af`. (2) Server-side branch protection BLOCKED (GitHub protection+rulesets need Pro on private; 403) → shipped `scripts/hooks/pre-push` (free client-side: blocks force-push+deletion of main/prod; installed+tested) + wired `install-hooks.sh`. (3) Created `~/.ssh/config` `noctus-vps` alias (root@72.61.28.36, deploy key) so VPS ops are one-liners; the actual VPS repoint is gated on the user's explicit "connect to prod" go (auto-classifier blocked an uninvited prod SSH — correct). | Claude |
| 2026-05-22 | **Phase 6 live-validation ✅** — user pasted a real Management PAT; wired to `mcp/supabase/.env` (gitignored, default ref `noctusai`). Validated our connector end-to-end through its own `request_json` seam (auth OK / 5 projects / `project.get` / `db.query` read `count(*) organizations`→15). `.mcp.json` registration attempted but **correctly auto-blocked as user-gated self-modification** → offered, needs session restart; usable now via direct Python import. ⚠️ PAT pasted in chat → rotate once home-ops stable. 3-way synced (KB MCP-SERVERS/supabase.md + 2 memory files). | Claude |
| 2026-05-22 | **CLOSE-OUT DEPLOY + safety-matrix assertion** (user: "finish the remaining work, then deploy to vps and assert the safety patterns work"). (1) **Fix-on-contact, gitignore creds gap** (`b385e6a6`): `**/tunnel/*.json` was declared in STATE.json D3 but missing from `.gitignore` → the secret creds file was one `git add .` from being committed; closed. (2) **Fix-on-contact, P5 false-block** (`79f19ccb`): `predeploy_check` (P5 gate) + `noctus.dev.pytest` both shelled bare `python` (no pytest) → false BLOCK + false GREEN; added shared `settings.resolve_test_python()` + returncode-gated success + regression test; P5 re-run on core → `ready`. (3) **Promoted `79f19ccb` main→prod** (pre-push hook passed FF). (4) **VPS §2a deploy:** C1 backup ref + tar (`/opt/noctus/backups/`), Phase-2 `config.yml`+creds migration (move-aside→ff-only→restore, ERR-trap guard) → working tree now CLEAN; docs/tooling-only, no rebuild; fleet healthy. (5) **Asserted P1–P5/D1–D4/C1/C3 all live** (P2 read-only key denied a push; D3 invariant holds; pre-push blocks force/delete; C2 N/A until an image rebuilds). **Edge audit + correction:** an initial probe of the LONG hostnames (`social-wiring.noctusai.com`) returned NXDOMAIN and was wrongly reported as a "DNS gap"; the Caddyfile uses the user's SHORT public slugs — re-probe confirmed `erp.`/`social.`/`core.`/apex/`n8n.`/`waha.`/`legacy.` ALL serve (erp + social-wiring already live). Genuinely offline = `personal-finance` + `therapy-platform`, which are **not deployed** (no container/vhost) → a full build+run+edge deploy, not a DNS add. 3-way synced (GUIDE P4/C1 + this doc + memory). | Claude |
| 2026-05-22 | **Post-close-out hardening — drill codified + D3 enforced** (user: "cover all those gaps, resolve them in this go"; ran a §2a-drill evaluation, found 4 gaps — the other agent had already closed 2 of them in parallel, `9f80d550`). Closed the two genuinely-remaining: **(Gap 3) `noctus.dev.deploy_pull`** (CLI `--deploy-pull`/`--deploy-confirm`) — the §2a drill as a tool over SSH: deterministic overlap-check + derived rebuild decision; DRY-RUN default, confirm-gated act; **by construction limited to a safe git allowlist + tar backup → can never emit reset/checkout/clean/push** (asserted by a colocated test); backs up via `git tag`+tar to `/opt/noctus/backups`. **(Gap 4)** `predeploy_check` now **asserts the D3 manifest** — new `deploy_local_gitignored` check + `deploy_local_tracked` known-class fails on any tracked/un-ignored deploy-local file in `STATE.json` (was previously "read conceptually"). 18 predeploy + 12 deploy_pull tests green; registry + cli wired; GUIDE §2a/P5/D3 + memory synced. **Worked in-tree after the user confirmed the parallel agent had stopped** (re-grounded each turn; touched only own files). Not fired against prod (no pending deploy; prod runs stay user-gated). C2 still the lone ⏳ net (first image-rebuild deploy). | Claude |
| 2026-05-22 | **Hardening shipped to prod + D3 manifest graduated to a code constant** (user: "push and deploy to prod"; then "graduate STATE.json durably"). (1) **Deployed** `ef986f74` (the deploy_pull + D3 work) main→prod→VPS **via `deploy_pull` itself** (its first real run, dogfooded): dry-run → confirm; clean FF `9f80d550→ef986f74`, C1 backup `backup/predeploy-20260522-144915` + `/opt/noctus/backups/20260522-144915.tgz`, no rebuild (docs/tooling-only), deploy-local preserved; fleet verified healthy (apex/core/erp/social 200, VPS HEAD confirmed). (2) **Graduated the D3 manifest** from the transient `projects/.../deploy/STATE.json` (archival → silent-skip risk) to a durable code constant `mcp/noctusai/deploy_state.py` `DEPLOY_LOCAL_FILES` (gitignore-style location-independent patterns). Both tools import it; `audit_deploy_local` + `deploy_pull`'s C1 resolution refactored (find-based remote glob resolution, no globstar dependency); STATE.json deleted; GUIDE D3/P4/P5 + .gitignore + memory synced. Chosen over a new root `deploy/` folder (over-build for one file) per the user's reasoning. 32 tests green. The gate now ALWAYS runs (manifest is code, never a missing file). | Claude |
| 2026-05-22 | **C2 (atomic image rollback) shipped — the last ⏳ net** (user: "implement C2 next then deploy"). Grounded against the live box first: the fleet runs the **GHCR-pull** model (`ghcr.io/jraphaelsst/noctus-<slug>:latest`, project `noctusai-products-prod`; "the VPS never builds") — so C2 is a retag/pull swap, not a rebuild. Shipped **`noctus.dev.deploy_image`** (CLI `--deploy-image [--deploy-image-confirm]`): snapshot running image id as `:previous` → `compose pull` + `up -d` → health-probe (`docker inspect` Health.Status, fallback State.Status) → **roll back** (retag snapshot → `:<tag>` + `up -d` + re-probe) on a health failure ⇒ prod never left on a broken image. DRY-RUN default, confirm-gated; **by construction limited to a safe docker allowlist (inspect/image/tag/ps + compose pull/up) — never rmi/prune/down/rm** (asserted by a colocated test, so it can't delete the rollback image or tear the fleet down). 11 colocated tests (planned/up_to_date/deployed/rolled_back/error/pull-fail + allowlist guards), zero real SSH/waiting. `deploy_pull`'s rebuild-decision now points here. **Fix-on-contact (surfaced):** GUIDE §2 "build on the VPS" is stale vs the live GHCR-pull model — added a corrective §2 note + flagged the full reconciliation as follow-up. Safety matrix now P1–P5 / D1–D4 / **C1 / C2 / C3** all live. Not fired against a real image swap (would disrupt a healthy product; fires naturally at the first product-code deploy). | Claude |
| 2026-05-22 | **C2 LIVE-VALIDATED + hardened from a real outage + §2 reality-corrected** (user: "rebuild a product image so we can assert C2 is functional and fix/improve while we validate"). **(1) Found GHCR is EMPTY** — `jraphaelsst` has 0 container packages; `docker compose pull` 404s. The fleet actually runs **build-on-VPS** (images built on the box, tagged `ghcr.io/...` locally, never pushed) — the earlier "GHCR-pull is live" was wrong (trusted compose/README over the registry). **Corrected GUIDE §2** (build-on-VPS = live ①; GHCR-pull = designed/not-active ②) + memory. **(2) Real outage + fix** — the first `deploy_image` falsely reported `rolled_back` while social-wiring stayed on a broken image (~2min down). Root cause: tagging the container's `.Image` id is unreliable on the **containerd manifest-list store** (snapshot resolved to a stale digest) AND there was no snapshot-/rollback-verify. Restored prod via rebuild-from-source. **Fixes:** `docker commit` snapshot (reliable) + **verify-snapshot-or-REFUSE** (fail-safe: no rollback target ⇒ don't deploy) + **verify-restored-or-loud-`rollback_failed`** (+ manual-recovery cmd) + `up -d --force-recreate` + **active `/api/health` probe** (port from healthcheck; startup-grace → faster detection). **(3) Improvement:** `--source local|pull` mode (deploy a VPS-built image, not just a GHCR pull). **(4) Re-validated LIVE on social-wiring:** happy path `deployed` (~22s, no downtime); fail-safe correctly REFUSED a stale-snapshot deploy (zero downtime); commit-based rollback `rolled_back` + restored (200). 18 deploy_image tests (50 deploy-tool total) green. ⚠️ GHCR token was pasted in chat → user to rotate; VPS GHCR login removed. | Claude |
| 2026-05-22 | **CI build-and-push workflow added (GHCR delivery layer §2 ②)** (user: "set up the GitHub Actions build-and-push workflow"). `.github/workflows/build-and-push.yml` — on push to `main` (path-filtered `products/**`/`seed/**`/build-script) + `workflow_dispatch`; runs `build-and-push.sh`, pushes `ghcr.io/jraphaelsst/noctus-<slug>:<sha>` (immutable) **+ `:latest`**. GHCR auth = built-in `GITHUB_TOKEN` (no PAT). **Fail-closed** on missing `VITE_SUPABASE_*` repo secrets (never pushes a broken-FE image). Enhanced `build-and-push.sh` to push `:sha`+`:latest` in one run. **Layering (answered): CI does NOT supersede `deploy_image`/C2** — CI = BUILD/DELIVER (off-box immutable artifact), `deploy_image --source pull` = DEPLOY/ROLLBACK-SAFETY (snapshot/health/rollback on the VPS); they compose, and GHCR's persistent `:sha` makes rollback/DR more durable. The `prod` promote-gate is unchanged (main-push builds, does NOT auto-deploy). To activate: add the 2 secrets → run → give the VPS a `read:packages` token → flip C2 to `--source pull`. Workflow YAML + `build-and-push.sh` syntax validated; first run is user-gated (secrets). | Claude |
| 2026-05-22 | **`noctus.vps.*` MCP fleet-ops surface + the build/deploy/operate methodology** (user: "enrich the methodology + MCP server to manage the VPS and containers"; "are we still using SSH?"). Answered: yes, SSH — but from the **local** MCP runtime, **never CI** (rejected the root-key-in-CI deploy job; set VITE secrets for the build layer only). Shipped **10 `noctus.vps.*` tools** (`mcp/.../dev/vps.py`): read-free `ps`/`health`/`logs`/`inspect`/`images`/`disk`/`stats`; confirm-gated `restart`/`recreate`/`prune` (dangling-only — never `-a`/tagged/running). Safe docker allowlist; no `rm`/`rmi -a`/`kill`/`down`/`exec` (test-asserted); injectable IO. 14 colocated tests + **live-validated read ops** against the box (health 5/0; disk 20%; ps/images/stats real data). Codified the **3-layer methodology** (build/deliver = GitHub Actions → GHCR, no key in cloud; deploy = deploy_pull/deploy_image; operate = noctus.vps.*; 🔒 prod SSH key never in CI) in `KB § PATTERNS/containerization-operations.md § 2a` + CLAUDE.md §3 router row + memory. Tool count 106→116. | Claude |
