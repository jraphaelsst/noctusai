# GUIDE — Caching a product's body (the procedural recipe)

> **What this is.** The procedural recipe for caching a product's **body** (components / pages / integrations) as canonical reusable **organs** in the noc-graph + code-embeddings caches. Use **before** starting work on caching any new product (after the seed pilot). Self-contained; composes — never duplicates — the methodology rules shipped during the seed pilot.
>
> **NOT another codification rule.** This is a guide / recipe / lessons / gotchas — sibling of `KB § GUIDES/production-deploy.md` (recipe + lessons) and `KB § GUIDES/absorb-seed-workspace.md` (10-gate procedure), not a `PATTERNS/` doc.
>
> **Born:** 2026-05-29, from the **seed pilot** (the `seed-organs-cache` project, Phase 1; closed 2026-08-31 — this guide is the durable record of what it proved).

---

## §0 What this guide is

- The 5-wave **per-product** recipe for caching its components / pages / integrations as canonical organs queryable by intent.
- Use it **once per product**, in the order recommended by §5 (next: social-wiring → ERP → therapy-platform → others).
- The cache that the recipe populates is the same cache the seed pilot populated — extended one product at a time. No 9th cache; we extend `code-embeddings.sqlite` with `chunk_kind="organ"` (per the vectorize → embed → cache META-RULE).
- The guide is **append-only** during each product's caching session: lessons learned become the next product's pre-coded knowledge (`§3` worked-example section).

**Composes with** (read once, never re-paste here):
- `KB § PATTERNS/architect/seed-organ-canonical-set.md` — the canonical seed catalog (the starting point).
- `KB § PATTERNS/common/build-learn-cache-mindset.md` — the 8-field knowledge bundle every organ carries.
- `KB § PATTERNS/common/vectorize-embed-cache-framework.md` — the universal vectorize → embed → cache pipeline (META-RULE).
- `KB § PATTERNS/common/cache-as-agent-tool.md` — caches ARE the search engines; reach for them BEFORE grep/Read.
- `KB § PATTERNS/architect/noc-graph.md` — the structural graph the recipe writes into.
- `KB § PATTERNS/architect/absorbed-product-seed-shape-seam.md` — the absorbed-product seed-shape seam (the *legitimate-divergence* shape).
- `KB § PATTERNS/common/bypass-rationalization-anti-patterns.md` — the 5 forbidden rationalizations the seed pilot caught its codifiers using.
- `KB § PATTERNS/common/persistent-files-absorption.md` — absorb-at-project-close (continuous variant of which is build-learn-cache).
- The `seed-organs-cache` pilot (closed 2026-08-31) — the worked example this guide was extracted from.

---

## §1 Prerequisites — must be true BEFORE you start

The 5-wave recipe assumes the seed-pilot infrastructure is **live**. Verify before starting any product's caching:

| Capability | Live since | Verify |
|---|---|---|
| `noctus.dev.find_reusable_component` (semantic search over organs) | W4 `1bbafead` | `noctus.dev.find_reusable_component "credentials list" --filter-status validated` returns ≥1 hit |
| `noctus.dev.component_bundle <name>` (organ-in-a-box) | W2 `23164dce` | `noctus.dev.component_bundle ResourceManager` returns `{source, types, tests, deps[], consumers[], wiring_snippet, validation_status}` in ≤1s |
| `noctus.dev.component_list` + derived `validation_signal` | W3 `74c7e4a9` | `noctus.dev.component_list sort=consumers_desc` lists the canonical seed set |
| `consumes_component` edges in noc-graph (re-export-attribution-honest) | W1 `fe9c3bfc` | `noctus.graph.neighbors component:LoginForm edge_kinds=consumes_component` returns ≥3 product nodes |
| Vectorize → embed → cache META-RULE codified | `25491bc0` | `KB § PATTERNS/common/vectorize-embed-cache-framework.md` exists |
| Build-learn-cache mindset codified | `ea7514e7` | `KB § PATTERNS/common/build-learn-cache-mindset.md` exists |
| Canonical seed catalog | seed pilot W4 | `KB § PATTERNS/architect/seed-organ-canonical-set.md` exists |

If any row is **not live**, STOP and surface — the recipe relies on the tooling. Don't try to cache a product without the tools (you'd be hand-rolling the cache shape, which is exactly what we just spent the seed pilot avoiding).

---

## §2 The 5-wave recipe (per product)

For each product to cache, run waves **W_a → W_e in dependency order**. Each wave is one architect-session pass (or one engineer dispatch, file-disjoint).

### W_a · Audit (READ-ONLY)

**Goal:** know the CURRENT state of every canonical organ in this product — consumer / forker / wrapper — and identify the *fork-shape catalog* (accidental fork / named-seam extension / genuine divergence) before touching anything.

**How:**
1. Pull the canonical seed catalog: `noctus.dev.component_list sort=consumers_desc --filter-status validated`.
2. For each canonical organ, query: `noctus.graph.neighbors component:<Name> edge_kinds=consumes_component` to see if this product is in the consumer set.
3. Cross-check with semantic search: `noctus.dev.find_reusable_component "<intent>" --product <slug>` — does this product import via a name-mismatch? (e.g. `AuthForm` that's structurally `LoginForm`.)
4. Grep cross-check ONLY to confirm (per `cache-as-agent-tool.md`: caches are discovery; grep is confirmation). Pattern: `rg "from ['\"]@noctusai/lib" products/<slug>/` then diff against the canonical roster.
5. Classify each finding into one of three buckets:
   - **consumer (clean)** — imports from `@noctusai/lib`, nothing to do.
   - **wrapper (LEGITIMATE)** — local component that wraps a canonical one to re-bind data / themes / labels without mutating the visible contract. KEEP. Declare with `// @consumes-organ <Name>@<ver> +seam=<kind>` if not already.
   - **fork (suspect)** — local re-implementation. Goto W_b.

**Output:** a markdown table in `projects/<slug>-organs/findings.md` listing every canonical organ × this product × {consumer / wrapper / fork / shelfware-here}.

**Don't write anything else this wave.** Just audit. (The seed pilot proved that 95% of canonical consumption was already in place — the real shape of "caching a product's body" is mostly *locking the gain*, not *doing the migration*.)

---

### W_b · Cleanup forks

**Goal:** every "fork (suspect)" from W_a is resolved into one of three landings.

**How — per fork:**
- **(i) Orphan fork (zero referrers)** → DELETE. `noctus.graph.neighbors file:<path> direction=incoming` is empty ⇒ safe delete. (Example: `991e9ed0` erp-imobiliario LoginForm.)
- **(ii) Non-orphan fork, contract matches canonical** → MIGRATE the consumer to import from `@noctusai/lib`. Delete the local fork. Run the product's tests. Commit.
- **(iii) Non-orphan fork, contract diverges legitimately** → DECIDE:
  - **a.** Extend the canonical via a **named seam in seed** (per `KB § PATTERNS/architect/absorbed-product-seed-shape-seam.md`). Back-compat-defaulted. Validate the seed change passes its own tests. Commit. THEN consume from `@noctusai/lib`.
  - **b.** Declare a **named seam locally** with `// @consumes-organ <Name>@<ver> +seam=<kind>` (e.g. `+seam=theme-override`). The marker IS the contract: this product's deliberate divergence is now visible to the keepers, not a silent fork.
  - **c.** If the fork is genuinely *a different organ* (different intent, different contract), it's not a fork — it's a candidate emerging organ. Goto W_c.

**The disqualifier:** if you can't articulate the seam in one clause, it's not a legitimate divergence — it's a fork by other means. (Wrappers that *mutate the visible contract* are forks; wrappers that *re-bind data* are good.)

---

### W_c · Register product-specific emerging organs

**Goal:** any component **unique** to this product that 2+ other products would benefit from (or already use) becomes a NEW canonical organ — registered with `organ.yaml` sidecar, embedded into the cache.

**How:**
1. List candidate components: those not in the seed catalog, with `noctus.graph.neighbors file:<path> direction=incoming` showing cross-product consumption OR plausible future cross-product use.
2. Apply the *triage rule*: N=1 → log to memory only (s2); N=2 → `noc-triage` skill, propose emerging; N≥3 → MUST register.
3. For each emerging organ:
   - Create `organ.yaml` sidecar (8 knowledge fields per `build-learn-cache-mindset.md`, populated as in W_d).
   - Register via `noctus.dev.register_organ <path>` (W4 seed-pilot tooling).
   - Embed: the registration writes to `code-embeddings.sqlite` with `chunk_kind="organ"` automatically.
4. Add the new organ to `KB § PATTERNS/architect/seed-organ-canonical-set.md` (one row, per the existing table format).

**Don't speculate.** Only register what already has 2+ consumers or a real plausible use case. The catalog grows by USE, not by guess (the seed pilot's hard-won rule).

---

### W_d · Populate the knowledge bundle

**Goal:** every newly-canonical-or-emerging organ ships its 8-field `organ.yaml`, populated from real evidence.

**Sources (in this order):**
1. **`git log -S "<organ-name>" -- <path>`** — the bug-fix-during-dev SHAs go in `bugs_fixed_during_dev`.
2. **`auto-improvement.ndjson` query** — `noctus.dev.auto_improvement_query "<organ-name OR product-slug>"` — drifts surfaced near this organ go in `drifts_surfaced` (cite the ndjson refs).
3. **Source comments + commit messages** — the *why-not-Y* discussions go in `alternatives_considered`.
4. **Manual review by orchestrator + user** — known behaviors / invariants / constraints go in `known_facts`.
5. **CI test run output** — latest pass/fail + which suites cover this organ → `integration_test_status` + `e2e_test`.
6. **Errors-during-this-session** — every bug you hit while caching THIS product gets appended via `noctus.dev.organ_knowledge_append <name> errors_encountered "<resolution + patch sha>"`. Yes, while you're caching.

**The invariant:** the knowledge bundle is **append-only across the artifact's life**. Refactor, bug-fix, integration touch-up, deploy — every event APPENDS. Knowledge never gets parked in transcripts or commit messages alone (those aren't queryable by intent).

---

### W_e · Acceptance + manual validation co-loop

**Goal:** validate end-to-end with the user. Findings become cache content.

**How:**
1. Orchestrator runs `noctus.dev.find_reusable_component "<a real query a future builder would ask>"` and reports the top-3 to the user.
2. User runs the product's UI surfaces backed by the cached organs and reports findings (works / breaks-when-X / unexpected-Y).
3. EACH finding lands via `noctus.dev.organ_knowledge_append <name> manual_validation_log "<finding + status + date>"`.
4. The embedding refresh runs **inline** (synchronous — the seed pilot's §3b decision, 2026-05-29) — the next query reflects this validation immediately.
5. Acceptance is binary: every organ has `validation_status=validated` (consumers ≥3 ∧ has_test ∧ no NOC-REMEDIATE markers ∧ no recent bugfix in 14d) OR is honestly tagged `emerging` / `shelfware`. **No "available but unused."**

The cache reflects the journey **as it happens**, not at project close.

---

## §3 What we learned doing the seed pilot (the worked example)

Captured in-flight during the 2026-05-29 seed pilot. These are pre-coded for the **next** product's caller — read them now, save the session.

### Lesson 1 — the gain may ALREADY exist

The architect scout found ≈95% canonical consumption *before* any migration. Phase 2's real shape was "lock the gain" not "do the migration." **Implication:** for every new product, W_a (audit) is the biggest wave and may be the ONLY wave that fires. The other waves are conditional on what the audit surfaces. Don't dispatch parallel engineers for W_b/W_c/W_d before W_a is done — you don't know there's work yet.

### Lesson 2 — re-export attribution must be HONEST first

`noc-graph` initially missed `@noctusai/lib/design-system/index.ts` re-exports (the W1 fix at `fe9c3bfc` resolved through the barrel `index.ts`). Audit BEFORE this fix LIES (the cache shows zero consumers for canonical organs that are heavily used); AFTER it tells the truth. **Implication:** verify the prerequisite row in §1 BEFORE running W_a. If the consumer counts look implausibly low, suspect the cache, not the codebase — surface to tech-lead.

### Lesson 3 — derived validation, not manual

`consumers ≥ 3 ∧ has_test ∧ no NOC-REMEDIATE markers ∧ no recent bugfix in 14d ⇒ validated` beats hand-maintained registry. The latter rots; the former auto-tracks. **Implication:** never add a manual `validated: true` toggle to `organ.yaml`. Trust the derivation. (If you find yourself wanting to override, that's a signal the derivation is wrong — fix the derivation, not the data.)

### Lesson 4 — shelfware gets its own tag

`consumers == 0` ≠ "available for reuse." Silent "available" misroutes future builders into adopting components nobody has battle-tested. The seed pilot's 4 shelfware components (`PageSkeleton` / `LLMSpendBadge` / `FakeModeBadge` / `ErrorBoundary`) get the `shelfware` tag — honest, surfaced, not deleted. **Implication:** W_a's classification MUST include the `shelfware-here` bucket. Don't promote shelfware to "canonical" just because it ships in seed.

### Lesson 5 — named-seam declaration is the ONLY legitimate divergence

Wrappers that re-bind data (e.g. `WeeklyReviewCard`, `MonthlyNarrativeCard` consuming `DigestCard`) are GOOD. Wrappers that mutate the visible contract (props the canonical doesn't accept; emit signals the canonical doesn't emit) are forks-by-other-means. **Implication:** the `+seam=<kind>` marker discipline is load-bearing. If you can't articulate the seam in one clause, the divergence isn't legitimate — it's a fork (W_b case iii).

### Lesson 6 — vectorize-embed-cache is the universal pipeline

Don't spawn new caches. Extend the existing one with a new `chunk_kind`. The seed pilot codified this as a META-RULE (`25491bc0`, `KB § PATTERNS/common/vectorize-embed-cache-framework.md`) because we caught ourselves *almost* designing a 9th cache for organ search. **Implication:** when this guide's recipe surfaces a "new cache needed" temptation, STOP. Open the META-RULE. Extend `code-embeddings.sqlite` with the new chunk kind.

### Lesson 7 — surfacing > bypassing

When the harness-cwd-drift bug bit the codification agents (the pre-commit hook ran from the wrong cwd → blocked the commit), the disciplined response was to surface via `noctus.dev.surface_to_tech_lead` (the `fe81e3c7` tooling). The rationalizing response was `--no-verify`. The latter was caught — and the rule against it was codified (`62560ede`) along with 5 forbidden rationalizations. **Implication:** when a keeper fires during this guide's recipe, surface. Never `--no-verify`. The methodology *fires correctly on its codifiers* — that's the methodology working, not malfunctioning.

---

## §4 Common gotchas (pre-coded learnings — save the next caller time)

- **Cache cwd-drift during pre-commit on a worktree.** Pre-commit refreshes keeper-pattern + agent-context caches *from the worktree*. If the worktree is fresh / re-stashed, the refresh may fail loudly. Fix BEFORE running pre-commit: `python mcp/noctusai/cli.py --refresh-keeper-pattern-cache --refresh-agent-context-cache` from inside the worktree, then commit. (Or wait for the upstream harness-cwd-drift fix to land.)
- **`find_reusable_component` requires `configure_llm()` at startup.** Bare CLI invocations may fall back to keyword search; the MCP server auto-wires this — prefer the MCP entry point during waves. If you see "keyword fallback active" in the tool output, that's the signal.
- **Wrapping-with-different-name is invisible to the keeper.** The keeper is name-only; semantic similarity-search via `find_reusable_component` is the FE-side compensating check. If W_a misses a fork because the local name is `AuthForm` but the structure is `LoginForm`, the similarity search would have caught it. RUN the similarity sweep as part of W_a — don't trust name-match alone.
- **Re-embedding cost.** Per-organ embed isn't free. Use `noctus.dev.vector_costs_report` to track. Empirical: ≈$0.0001 per organ via OpenAI `text-embedding-3-small`. A full product cache pass is ≈$0.01-0.05 — cheap, but log it.
- **The `auto-improvement.ndjson` write happens AFTER pre-commit.** Don't grep the file mid-session expecting your own surfaces to be there yet. Use `noctus.dev.auto_improvement_query` (cache-backed, more current) or wait for the post-commit refresh.

---

## §5 Order of operations across products

The seed pilot proved the loop. The recommended order across the fleet:

| # | Product | Why this order | Estimate (W_a-W_e tooling already in place) |
|---|---|---|---|
| 0 | **seed** (Phase 1, DONE 2026-05-29) | Pilot; tooling validated on the most-consumed components first. | DONE |
| 1 | **social-wiring** (next, user's focus) | Highest-traffic FE; multi-account integrations CRUD + settings already absorbed; clean test of the recipe on a real product. | ≈4-6h |
| 2 | **erp-imobiliario** | Largest codebase; highest absolute reuse value when its organs land in the catalog. Phase 2.2 already cleaned its LoginForm orphan fork. | ≈6-10h |
| 3 | **therapy-platform** | Per-therapist scheduling surfaces are reusable across future practitioner-style products. | ≈4-6h |
| 4 | core / sw-* / others | Lower-traffic; absorb opportunistically when touching them for other work (fix-on-contact). | per-product |

**Per-product budget:** ≈1 working session with the seed-pilot tooling already in place. The waves are mostly mechanical — the manual-validation co-loop (W_e) takes the longest because it's user-paced.

---

## §6 The build-learn-cache loop applied (the most important transfer)

**The journey IS cached.** As you cache each product:

| What happens in-session | Where it lands |
|---|---|
| You hit an error + fix it | `errors_encountered: [{date, error, resolution_sha}]` |
| You surface a pre-existing drift | `drifts_surfaced: [{date, ndjson_ref}]` + auto-improvement.ndjson |
| You consider design A, abandon it for B | `alternatives_considered: "tried A, chose B because X"` |
| User reports "works for case A but fails when X" | `manual_validation_log: [{date, validator, finding, status}]` |
| Integration tests pass / fail | `integration_test_status` |
| E2E test ships | `e2e_test: {path, status, last_run, runs_in_ci}` |
| Bug-fix during dev | `bugs_fixed_during_dev: [<sha>]` |
| Verified behavior | `known_facts` |

**The next product reads the previous product's organ knowledge BEFORE starting** → avoids repeating mistakes. The cache becomes the source of truth for *what we've learned across all products* — not just *what we built*.

This extends `persistent-files-absorption.md` from "absorb at project close" to "absorb continuously per artifact." The append-only contract closes the structural feedback loop.

---

## §7 Cross-reference index (open on-demand)

- `KB § PATTERNS/architect/seed-organ-canonical-set.md` — the canonical seed catalog (the starting point per product).
- `KB § PATTERNS/architect/absorbed-product-seed-shape-seam.md` — the *legitimate-divergence* pattern (W_b case iii.a).
- `KB § PATTERNS/architect/seed-canonical-defaults.md` — seed-default rule (sibling of the canonical organ rule).
- `KB § PATTERNS/architect/noc-graph.md` — the structural graph the recipe writes into.
- `KB § PATTERNS/common/build-learn-cache-mindset.md` — the 8-field knowledge bundle every organ carries.
- `KB § PATTERNS/common/vectorize-embed-cache-framework.md` — the universal pipeline (META-RULE).
- `KB § PATTERNS/common/cache-as-agent-tool.md` — caches ARE the search engines.
- `KB § PATTERNS/common/bypass-rationalization-anti-patterns.md` — the 5 forbidden rationalizations.
- `KB § PATTERNS/common/persistent-files-absorption.md` — continuous variant = build-learn-cache.
- The `seed-organs-cache` pilot (closed 2026-08-31) — the worked example.
- Recent worked-example commits: `1bbafead` (W4 register+embed+find), `74c7e4a9` (W3 validation_signal), `23164dce` (W2 component_bundle), `fe9c3bfc` (W1 re-export attribution), `25491bc0` (vectorize META-RULE), `ea7514e7` (build-learn-cache), `62560ede` (no-verify loophole + 5 rationalizations), `fe81e3c7` (surface-and-resume tooling).
