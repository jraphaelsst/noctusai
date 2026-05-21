# Deploy-Hardening & Dev/Prod Isolation — Project Document

> Living document. Born 2026-05-21 from the production-deploy session: the user asked to (a) codify a safe VPS code-sync methodology, (b) add creative defense-in-depth so production code can never be damaged/reversed/half-deployed, (c) implement a pre-deploy verification gate that *learns* from failures, and (d) separate dev from prod data — currently local dev and the VPS share ONE Supabase project.

- **Created:** 2026-05-21
- **Last updated:** 2026-05-21
- **Status:** Phase 1 shipped (safety-net doc) → Phases 2–6 designed, **blocked on 2 user forks** (§7 Q1 DB approach, Q2 branch model) 🅿️
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

### Phase 2 — De-track deploy-local files (P4) 🅿️ (low-risk; can start independently)
- [ ] gitignore `config.yml`; add `config.yml.template`; render-on-deploy from `.env`
- [ ] migrate the live VPS copy (back up current `config.yml` → untrack → render → verify tunnel unaffected)
- [ ] D3 `deploy/STATE.json` manifest + drill diff

### Phase 3 — `prod` promote-branch (P3) 🅿️ (blocked on §7 Q2)
- [ ] create `prod` off `main`; GitHub branch protection on `prod`+`main`
- [ ] point the VPS at `origin/prod`; update §2a drill + memory to `prod`
- [ ] document the promote ritual (bless `main` sha → FF `prod` → deploy)

### Phase 4 — Pre-deploy verify + learning tool (P5 / D3 / C1 / C2)
- [ ] `noctus.dev.predeploy_check` (build slim runtime + FE build + import-check + pytest)
- [ ] failure classifier + known-class auto-fix + `predeploy-reports/` + `phase_learnings` log
- [ ] `backup-ref` (C1) + `atomic image rollback` (C2) as `noctus.dev.*` tools

### Phase 5 — DB dev/prod isolation 🅿️ (blocked on §7 Q1)
- [ ] `APP_ENV` Supabase-target seam in seed config (Fake unaffected)
- [ ] stand up the isolated dev datastore (approach per Q1)
- [ ] split `.env` (local → dev target; VPS → prod) + `.env.example` doc; verify local can't reach prod data

### Phase 6 — Self-owned Supabase MCP (`mcp/supabase`)
- [ ] connector composing `_kit`: project/db/migration/diagnostics tools; confirm-gated writes
- [ ] `mcp/supabase/.env` (token + project-ref); `KB § MCP-SERVERS/supabase.md` + memory; `.mcp.json` user-gated
- [ ] **commit + push** (the user's "last piece" gate)

---

## 7. Open questions (the two forks gating Phases 3 & 5)

1. **DB dev/prod isolation approach?** — needs answer before Phase 5; decided by user.
   - **(A) separate dev Supabase project** — same Postgres engine, isolated data, cloud, ~zero local setup. *Recommended for parity + simplicity.*
   - **(B) local Supabase stack (`supabase start`)** — real Postgres + PostgREST + Auth in Docker, fully offline. *Best parity, heavier local footprint.*
   - **(C) SQLite local** (user's initial idea) — ⚠️ **parity risk**: SQLite ≠ Postgres (RLS, PostgREST filters, JSON ops, `gen_random_uuid`) → re-introduces "works-locally-breaks-in-prod". *Not recommended; would need a real DB-abstraction layer the codebase doesn't have.*
2. **Branch model for the prod gate?** — needs answer before Phase 3; decided by user.
   - **(A) dedicated `prod` branch the VPS tracks**, FF from blessed `main` (user's idea). *Recommended — explicit human promote gate.*
   - **(B) keep VPS on `main` + add branch protection / required PR + CI.** Lighter, fewer steps.
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
| 2026-05-21 | Project drafted after the production-deploy session. Phase 1 (safety-net stack + safe-sync drill) shipped to `KB § GUIDES/production-deploy.md § 2a` + CLAUDE.md router row + memory. Two risks evidenced (tracked `config.yml`; local==prod Supabase `nyplttplcoyiiqjrvtiw`). Phases 2–6 designed; blocked on §7 Q1/Q2. | Claude |
