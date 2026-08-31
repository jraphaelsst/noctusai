# HANDOFF — 2026-08-31 (session 3, dangling-work drain) → next session

> **You are the tech-lead.** Contextualize first (`/contextualize`), then read this.
> Everything below is verified state, not expectation. Where something is unverified,
> it says so.
>
> **Nothing is in flight. `dev` is 42 commits ahead of `main`/`prod`, and the
> promotion decision is the owner's — see §0.**

---

## 0 · REF STATE — `dev` IS AHEAD, PROD IS NOT PROMOTED

| ref | sha | meaning |
|---|---|---|
| `origin/dev` | `fed11999` | 42 commits of this session's work |
| `origin/main` | `7765cbee` | ⬅ **not blessed** — unchanged since session 2 |
| `origin/prod` | `7765cbee` | ⬅ **not promoted** — unchanged since session 2 |
| `origin/prod-backup` | `0e13ea71` | rollback pointer |

**This is deliberate, not an oversight.** Prod-exposure registration is the owner's
decision, never an agent's (`KB § PATTERNS/devops/prod-exposure-consent.md`). Session 3
did the work; it did not promote it. The live fleet is healthy and running `34a0c4c4`
images — untouched all session except the two prod changes in §1.4.

**Before any promotion:** CI green on the tip, then `predeploy_check` per live product,
then `release stage=promote`, then `deploy_image` + `deploy_verify`. Skill `noc-ship`.

---

## 1 · WHAT SHIPPED (42 commits, 11 branches, all integrated + rebase-clean)

### 1.1 The lying-loading-state class — now gated, not just documented

The morning session fixed ~70 Mode-B sites by hand. This session closed the gate behind them.

- **`check_lying_loading_state` gained two AST shapes** (`ab37df8d`), implemented with
  ts-morph in `mcp/noctusai/node/lying_loading_scan.mjs`:
  - **Mode B** — `isFetching` reaching an early `return` / ternary / JSX-child gate, guard-aware.
  - **Shape 5** — a bare `.isLoading` reaching the same three gates. **This was the big one:**
    no `loading=` prop, no `isEmpty=`, no hand-rolled `.length === 0` guard, so all three
    original shapes missed it entirely while the fleet reported "clean."
  - Resolves through **one variable-alias hop** via the real TS binder, not name matching.
  - Found and fixed a genuine false positive mid-build: a `useState` array-destructured
    `isLoading` looks identical to query state. Excluded by requiring the identifier to
    resolve to an `ObjectBindingPattern`. Regression fixture added.
- **Fleet sweeps** cleared: orbity (21 Mode-A sites), therapy-platform (~110 conversions +
  1 real Mode-B in `Scheduling.tsx`), erp-imobiliario (18 consumer sites across 17 files),
  plus the Shape-5 wave (§3 for the residual).
- **Three blind tests fixed** — `pages/leads/{Corretores,Origens,Empreendimentos}.test.tsx`
  mocked `ChartCard` in a way that dropped the `loading` prop entirely, so they
  structurally could not catch the bug that shipped live on those very pages. The mock now
  reproduces the real `loading > error > isEmpty > children` priority, and each file gained
  a Mode-A and a Mode-B guard, **mutation-proved in both directions**: reintroducing
  `loading={q.isLoading}` fails only the Mode-A guard; reintroducing `isPending || isFetching`
  fails only the Mode-B guard.

**Severity is still `warning` (observe-first) — deliberately.** Do not promote it to `high`
until the fleet measures zero; see §3.

### 1.2 The primary/origin divergence loop — ROOT-CAUSED, this time for real

`d0170d92` (morning) fixed a real cause and the symptom **still recurred** hours later. It is
now genuinely closed (`8c0af23e`).

**Cause.** `_ledger_push`'s divergence guard requires every commit ahead of `origin/dev` to
touch only `ledger_set`. `task_branch` passes just `worktree-salvage.ndjson` — but the
pre-commit hook's step 10c `git add`s `project-history/vector-costs.ndjson` **into that very
commit**. The guard then rejected its own commit as contaminated.

**Why it was worse than what it replaced:** self-latching. The old rebase-refusal cleared
itself on the next rebase; this one refused *forever* until a human reconciled — which is
exactly the "regrows every teardown, cleared by hand once a session" history.

**Fix:** the guard now tolerates a rider iff `_benign_stash.is_benign(f)` — the **same
predicate** the stash pre-check already uses, so there is no second hand-maintained list to
drift. Real work still blocks loudly as `dirty_blocked`.

**Verified, not assumed:** reproduced in a throwaway repo with a real pre-commit hook;
`test_ledger_push_realgit.py` applies the *pre-fix* predicate to a real commit's real
`diff-tree` and asserts it would have blocked. 79 tests pass.

**Also corrected:** `git commit -- <paths>` (`--only` included) does **not** exclude a file a
hook adds mid-commit. That was tested explicitly — it is the obvious fix and it does not work.

**Reporting fixed too:** a failed salvage push now returns `salvage_push_reason` instead of a
bare `false`.

### 1.3 Everything else

- **Dependabot fully drained** — 20 PRs landed in 5 coherent commits, 2 already superseded,
  **zero deferred**. All four lockfile/slug keepers at 0 issues; **no `overrides` block
  touched** (the trap that froze this fleet three times).
- **`cli.py` exit-0 backstop** (`7ddda6ea`) — see §2.3 for the honest caveat.
- **Two silently-dead duplicate tool registrations resolved** (`23b0a5b1`). Both losers
  *differed* from the winners, so they were renamed rather than deleted:
  `noctus.dev.platform_bootstrap_context`, `noctus.dev.dispatch_completion_summary`.
  `build_server()` now logs **zero** collisions, enforced by a new uniqueness test.
- **Outline-corpus baseline** now relative-OR-absolute (±5% **or** ±1 symbol), with a test
  proving a genuine multi-symbol regression still fails.
- **MCP server loads the repo-root `.env`** (`80e37fff`, `override=False`) — catalog-backed
  tools stop falling back to the 2026-08-17 snapshot. The refreshed roster came back
  **byte-identical**; it was stale in timestamp only.
- **CI now provisions `mcp/noctusai/node`** (`09c77fc1`) — measured **6 passed/17 skipped →
  23 passed/0 skipped**. Node pinned to 20 (ts-morph 28's transitive deps require `20 || >=22`).
  Install is ~1.7s; caching deliberately declined as not worth the machinery.
- **Remediation markers: 142 → 70 real, 0 malformed.** The scanner now distinguishes a
  *declaration* from a *citation* (it was flagging docs that merely teach the syntax) and
  parses multi-line markers. 50 dates recovered via `git blame` at their **true introduction
  date**, not stamped with today's. `on_except` remains 0.
- **9 shipped-but-unclosed projects archived** (`cffea0a9`) — see §4.

### 1.4 PROD CHANGES — two, both verified

1. **p-studio migration `009` applied** (`20260831202859`). Verified after: 0 rows under the
   old org, 17 seed rows under `noctusai`, `p-studio` org row preserved as the file intends.
2. **`IGIG_COFRE_KEY` generated and set** in `/opt/noctus/noctusai/.env`; igig recreated and
   healthy. Proven by a real Fernet encrypt/decrypt roundtrip **inside the running container**
   (`len=44`, `roundtrip_ok=True`). Backup: `/root/.env.bak.20260831-igig-cofre`.
   Now declared in `required_prod_config` with a boot-refusal test.
3. **igig migration `013` applied** as a verified no-op — see §2.4, it is a cautionary tale.

---

## 2 · CORRECTIONS TO THE RECORD — things previously believed that are FALSE

Read this section before trusting any prior handoff.

### 2.1 `prod-fleet-swap-handoff` §7 was wrong about its own cause
It claimed `salvage_pushed:false` happens "because the primary-write guard forbids committing
there." It does not — `task_branch._push_salvage_ledger_from_primary` commits from the primary
**deliberately, and that commit succeeds**. Corrected in-place; real cause in §1.2.

### 2.2 `lying-loading-state.md` was actively lying, and it cost time twice
Lines 305–315 claimed the keeper's remediation strings still prescribed the superseded
`isPending || isFetching`, and instructed readers to *"trust this document over the finding
text."* `f4b4c625` had already fixed those strings. **Two independent engineers filed this as
a live finding.** A stale warning that manufactures false findings is worse than no warning.
Block deleted, replaced with a one-line historical note.

### 2.3 The `cli.py` rc=0 bug may never have existed
Unreproduced despite a real attempt. CPython already exits 1 on an escaping exception —
**3 of the 4 new tests pass on both pre- and post-fix code**, and the engineer said so rather
than staging a fake win. Two live hypotheses: a background-thread exception (which the new
backstop structurally *cannot* catch), or the original observation was itself a `cmd | tail`
exit-code misread — the exact anti-pattern in CLAUDE.md §1. The backstop still earns its
place: it stops a missing `SystemExit` passthrough corrupting a real `exit(2)` into `exit(1)`.

### 2.4 igig migration `013` nearly made prod LESS safe — check live before applying
The first draft added `SECURITY DEFINER` to `igig.set_updated_at()`. Migration `006` never had
it. A fix aimed at advisor 0011 would have converted an invoker-rights trigger into a
definer-rights one while its comment claimed "body unchanged from 006" — the body was, the
security context was not. Cause: copying the **shape** of `therapy_012`/`erp_028` rather than
their **reason** (those pin `search_path` on functions that genuinely *are* `SECURITY DEFINER`).
Both precedents were re-checked and are correct; the error was local to this draft.
**And prod already had the fix**, applied out-of-band — live was safer than the migration.
Corrected, then applied as a true no-op; all **18 triggers** still bound afterwards.

### 2.5 The migration ledger is NOT a reliable record of what is applied
Verified three times: p_studio `007`/`008` and social-wiring `060` are demonstrably applied but
**absent from `supabase_migration_list`**. So the ledger cannot answer "is N applied?", and a
replay from migrations alone would not reproduce prod. **Query the live schema before applying
anything.** Logged as broad drift; deliberately not auto-fixed, because a double-apply on a
non-idempotent migration is the worse failure.

### 2.6 A count I relayed was inflated by a stale base
The detector's "173 Shape-5 sites" was measured at `7765cbee`, **before** three concurrent
sweeps integrated. therapy went ~30 → 1, orbity ~20 → 0. But ~120 were genuinely real
(erp 61, social-wiring 27, personal-finance 14, p-studio 9, daily-life 5, adconnect 3, core 1).
Lesson: a fleet count is only valid at the sha it was measured on — `per-branch green ≠
integration green`, running in reverse.

---

## 3 · STILL OPEN

### Needs an owner decision (nobody else can answer these)
1. **Promote to prod?** `dev` is 42 commits ahead. Everything is CI-green and integrated.
2. **`deploy-config-pilot-consume`** — for **erp-imobiliario only** now (social-wiring and
   p-studio already declare; therapy is inactive): *which env keys must never fall back to a
   dev default in prod?*
3. **`imovelweb-portal-leads-ingestion`** — *send the drafted `gate-1-credential-request.md`
   to `integracao@imovelweb.com.br`, yes or no?* Everything buildable without credentials is
   built; this is the only real blocker.
4. **`therapy-scheduling-pilot-rollout`** — *reactivate therapy-platform, or park this?*
   Phase 3 needs live Google OAuth QA but the product is `ativo=false`.
5. **`prod-fleet-swap-handoff` §5** — *have you eyeballed the 5 social-wiring surfaces in
   prod?* (ROI, funil totals, duplicate queue, new panel, Negociação money field.) No agent
   can close this. The project is archived; this checklist outlived it deliberately.

### Real engineering work, filed not started
- **p-studio react-router CVE** (GHSA-wrjc-x8rr-h8h6, moderate). **No patched 6.x exists** —
  the only fix is a v6→v7 major migration off p-studio's deliberate v6 lag. Needs its own
  Gate-3 migration project; the skill's own history says v6→v7 was near-zero-source-edit
  fleet-wide, so this is likely small but must not be forced through a dependabot bump.
- **`check_lying_loading_state` severity promotion** to `high` — only once the fleet measures
  zero. Check first: it is a one-line change (`_LYING_LOADING_SEVERITY`) plus the cli.py help
  text and the "warnings — observe-first" output line, which must move together.
- **~49 body-only test assertions** across 7 igig router test files (no status-code pin).
  Logged s1. This is an authoring convention, not a fresh defect — a mass rewrite needs a
  decision, not a sweep.
- **The 9 "route-exists ≠ wired" findings** in therapy-platform from `noctus.dev.review`.

### Systemic, and getting worse — worth attention
- **The AST detector times out at 120s fleet-wide.** It is honest (emits one explicit
  bootstrap/timeout finding, `product: "*"`, never a silent zero) but **the gate does not
  actually run at fleet scale**. Per-product invocation takes ~10s and works — the recipe is
  in §5. Root fix: scope the scan per-product, or profile the `getSymbol()` resolution that
  took it from ~3s to ~90–100s.
- **noc-graph cache refresh timed out at 300s, twice.** It was ~12s this morning. Pre-commit
  hooks now take ~7 minutes on a product worktree. Something in the cache/gate layer got
  materially slower today; nobody has profiled it.
- **`02-LANDSCAPE.md`'s auto-derived counts drift on a clean checkout**
  (`cli.py --update-kb-counts --check` reports drift with nothing modified), and pre-commit
  can leave it in a staged+unstaged `MM` state non-deterministically. It blocked a primary
  `git pull` this session.
- **`noctus.dev.status`'s bucket classifier reports `blocked: 0`** while at least six projects
  self-describe as blocked — one literally opens `🔒 BLOCKED-EXTERNAL`. Teaching it to read
  `BLOCKED-USER`/`BLOCKED-EXTERNAL`/`🔒` moves 6–8 projects out of `executing`, and
  *"6 executing, 8 waiting"* is a portfolio someone can act on.
- **The highest-leverage fix in the whole audit:** `PROJECT.md` has no machine-checkable
  done-condition, so nothing could ever keep it fresh — three months of drift was the
  *expected* outcome, not a lapse. `auto_improvement_reconcile` already takes predicates
  (`path_exists:`, `grep_present:`, `keeper:`, `superseded_by:`). Add a
  `**Done when (machine):**` line to PROJECT.md and have `noctus.dev.status` evaluate it and
  override the prose icon. All 9 projects archived this session would have self-closed.

---

## 4 · PROJECT PORTFOLIO — now honest

**Archived (9)**, each verified against the tree rather than its status prose:
`vps-exec-sql-helper` · `dispatch-pattern-hardening` · `dispatch-with-project-notes` ·
`prod-deploy-compose-durable-relocate` · `prod-deploy-compose-vps-cutover` ·
`n8n-workflows-page` · `harness-agents-skills` · `container-first-codify-and-absorb-ke` ·
`seed-organs-cache`.

Two fought the gates, and the gates were right:
- `container-first…` had a `findings.md` → learn-before-archive. All six lessons were
  confirmed to have durable homes first. **Note:** the build-saga lessons live in
  `containerization-operations.md`, **not** `containerization.md` as its findings file implied.
- `seed-organs-cache` had 6 KB references calling it "the pilot project, the worked example."
  Rewritten as historical citations so `KB § GUIDES/product-body-caching.md` stands alone.
  A stale TODO naming a branch that was never created was resolved in passing.

**Superseded, safe to close:** `p-studio-absorption-rollout` (the roadmap won — two trackers,
the project doc rotted), `remaining-five-fleet-mount`, `finance-therapy-vps-deploy`,
`frontend-deps-base-consolidation` (Phases 2–4 target the dormant local fleet).

**Genuinely live, with collapsed scope:** `platform-auth-modernization` (fan-out is **4 live
products**, not 9) · `product-internal-wiring` (Wave 2 is **erp only**) ·
`meta-video-reels-publish` (correctly gated on a consumer that does not exist) ·
`seed-lift-ke-gap-seams` (correctly deferred at N=1) · `worktree-sensitivity-guard` (small) ·
`codification-backlog-drain` (low value).

**Marker classes at N≥3 — both already formalized, no new work:**
- The 30 orbity markers **are** M2/M3 of `roadmaps/orbity-2026-06.md`. Linked, not
  re-tracked — a second tracker would have repeated the p-studio mistake. They are deliberate
  Fake-adapter defaults, **not rot**; `reports-metrics-source` is *gated on* `meta-ads-live`.
- `rate-limit` needed nothing: `outbound-rate-limiting.md` already has an adoption table
  naming Vista/WAHA/YouTube as deferred with a trigger.

**The scanner's N≥3 list is a prompt to check, not a work queue.**

---

## 5 · KNOWN-GOOD COMMANDS + TRAPS

```bash
P=/Users/rapha/Documents/repository/NoctusAI/noctusai
V=$P/venv/bin/python3

$V mcp/noctusai/cli.py --verify-kb-sync --check-claude-md-router
$V mcp/noctusai/cli.py --predeploy-check <slug>          # value form, NOT --product
$V mcp/noctusai/cli.py --deploy-verify --spa-smoke
set -a && . ./.env && set +a    # gives catalog-backed tools their Supabase creds
```

**Per-product lying-loading scan (~10s — the fleet-wide call times out):**
```bash
find products/<SLUG>/frontend/src -name '*.tsx' ! -name '*.test.tsx' ! -name '*.spec.tsx' \
 | $V -c "import sys,json,os;print(json.dumps({'files':[os.path.abspath(l.strip()) for l in sys.stdin if l.strip()]}))" \
 | node $P/mcp/noctusai/node/lying_loading_scan.mjs
```
Returns `{results:{absPath:[finding,…]}, errors:{absPath:msg}}`. **`errors` must be empty** —
a non-empty entry is a real parse failure, not noise. Node resolves `ts-morph` from the
script's own directory, so run the PRIMARY's script pointed at any worktree's files; no
symlink needed.

**Traps that cost time THIS session:**
- **Verify by exit code captured as `rc=$?`.** `cmd | tail` returns *tail's* status. This may
  even be the origin of the phantom rc=0 bug (§2.3).
- **A heredoc does not survive a backgrounded shell** — `git commit -F -` read empty stdin and
  silently did nothing while reporting rc=0. Use a message file.
- **`task_branch action=start wire_env=True` returns ~1.2 MB** of per-file wiring detail and
  blows the tool-result budget. The worktree is still created; confirm with `git worktree list`.
- **The `primary_write_guard` will refuse a compound command containing any write to the
  primary on `dev`.** That is correct. Do not route around it — work in a worktree.
- **Never `pytest mcp/noctusai/tests` unbounded** — `TestSeedCompliance` /
  `TestAIFeatureCompleteness` take 25–50+ minutes.
- **Pre-commit now takes minutes**, sometimes >2, on product worktrees. Background the commit
  rather than assuming it hung.
- **The live MCP server does not hot-reload tool modules.** After editing one, a fresh-process
  CLI run reflects the change; the running server does not. **Restart it to pick up §1.2's
  divergence fix** — until then `task_branch cleanup` still uses the old code path.

**Owner action, one line** — the primary checkout is behind `origin/dev` with a dirty
auto-derived `02-LANDSCAPE.md` (self-branching mode correctly forbade an agent from fixing it):
```bash
cd $P && git checkout -- KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md && git pull --ff-only origin dev
```

---

## 6 · METHODOLOGY LESSONS WORTH MORE THAN THE FIXES

1. **A gate whose dependency is not provisioned is not a gate.** The AST keeper shipped and
   did nothing in CI because `node_modules` is gitignored and no job installed it — in a job
   whose own comment reads *"an unenforced quality gate is silent debt."*
2. **A fake that cannot express the failure passes forever.** `test_task_branch.py` asserts
   *both* `salvage_pushed` outcomes against a scripted runner whose `rebase` returns a canned
   code regardless of tree state. That is why the bug survived five closed ledger entries.
   Real-git tests are the only thing that closed it.
3. **Copy the reasoning, not the template.** §2.4's near-miss came from matching two
   precedents' *shape* instead of their *reason*.
4. **A stale doc that says "trust me over the tool" is worse than no doc** (§2.2).
5. **A count is only valid at the sha it was measured on** (§2.6).
6. **The scanner's N≥3 list is a prompt to check, not a work queue** — both classes were
   already formalized.
7. **A subagent refusing an out-of-band instruction is correct behaviour.** The dependabot
   engineer declined a mid-flight `SendMessage` asking it to edit CI — unrelated to its brief,
   unverifiable provenance — and said a real tech-lead should dispatch it normally. It was
   right; the task was re-dispatched properly. Use `SendMessage` to *extend* a brief; use a
   fresh dispatch for genuinely new scope.
