# 01 — Engineering Philosophy

> This file is the **long-form elaboration** of the behavioral rules in `CLAUDE.md`.
> CLAUDE.md contains the terse, every-session version Claude reads every turn.
> When an agent needs deeper reasoning or historical context for a rule, it reads here.
> **Sync rule:** if you change a rule in one file, update the other.

---

## Seed first. Always.

Every product inherits its structural backbone from `seed/`. When creating a new product, import `create_product_app()` (backend) and `createProductApp()` / `createProductLayout()` (frontend) from the seed framework.

- Do NOT copy-paste structural code.
- Do NOT re-implement auth, routing, layout, database clients, health checks, team management, or notifications — they come from the seed.

This is not optional, not debatable, not a suggestion. The seed is the skeleton. Products are the organs. Read `seed/README.md` before building anything.

**Why:** Multiple products had duplicated auth, duplicated layouts, duplicated notification code. Every change meant editing N places. The seed centralizes structure; products carry only domain-specific code.

---

## MCP toolkit reviews after every change (observation-only)

After modifying code, run `python mcp/noctusai/cli.py --review` on the affected product. The review pass:
1. Detects seed-compliance issues deterministically (`check_seed_compliance`, `check_path_references`).
2. Asks an LLM (OpenAI, via `OPENAI_API_KEY`) to author one proposal per issue in `mcp/noctusai/proposals/` — with a problem analysis, a concrete proposed solution that references seed APIs, and an effort estimate.
3. Falls back to a skeleton proposal (just the raw detector output) when the LLM is unavailable — so nothing is silently dropped.
4. Returns a report: `issues_found`, `proposals_created`, `llm_enriched` vs `llm_fallbacks`, and the `final_score`.

**It NEVER modifies code.** Every fix goes through a human who reads the proposal and applies it deliberately.

**Development loop:** change → `python mcp/noctusai/cli.py --review` → triage proposals in `mcp/noctusai/proposals/` (accept / reject) → apply the accepted fixes manually → commit.

### Why no auto-fix?

The earlier `--heal` flow auto-rewrote code (`str.replace`, router-file deletion) for issues the detector classified as "deterministic." It was retired because:
- Text-level rewrites cannot distinguish a real violation from the same substring inside a comment, docstring, or unrelated path — a false positive corrupts code.
- Deleting boilerplate files without diffing against the current seed silently erases legitimate product customizations.
- The detectors themselves are **string-match snapshots** of the seed at the time they were written. When the seed adds or renames a factory, the checks rot and begin flagging the wrong thing. An LLM reading the actual seed can reason about the current contract; a `"create_product_app" not in content` check cannot.

No code ships with unreviewed violations — but the review is human-in-the-loop, not automated rewriting.

---

## No incomplete commits

Never commit a product with mismatched maturity between backend and frontend. If the backend has working endpoints, the frontend must have real pages wired to those endpoints — not placeholders.

"Scaffolded" is not "complete." Both sides must be at the same level before committing. If one side is incomplete, flag it to the user before committing.

---

## No quick fixes

Never patch symptoms. If your fix requires touching multiple products for the same reason, you're fixing a symptom, not the root cause. Step back. The fix belongs in one place (seed, lib, or a shared config) and propagates automatically.

Spend 30 minutes on a proper solution over 5 minutes on a hack that creates future work. Infrastructure before features, root cause before symptoms.

**Signal of a symptom patch:** the same change is needed in 2+ products. Stop, find the root.

---

## No workarounds

Always use the real API/SDK/framework. No monkeypatches, shims, or hacks. If the framework lacks a feature, extend the framework — don't bolt a workaround onto a product.

---

## DRY

Single authoritative source for every piece of logic. Three similar blocks → extract to shared.

Applies to:
- Code — extract to `noctusai_lib` or `noctusai_seed`.
- Configuration — one `.env`, one vite factory, one tsconfig base.
- Docs — one PHILOSOPHY, one INDEX, cross-refs not duplications.
- Schema patterns — one RLS template, one trigger helper.

---

## Componentize everything

When you build something a product needs, ask: "will another product need this?" If yes (or maybe), build it as a shared component from the start.

**Check `04-SHARED-LIBRARY.md` before writing anything** — it might already exist.

The shared library is the platform's validated, reusable code. Every extraction reduces maintenance burden as the platform grows. Duplicate code is tech debt; shared components are assets.

---

## Module-scope imports

All Python imports go at the top of the file (module scope). Never defer imports to inside functions or after object creation unless solving a documented circular dependency.

**Why:** Module-scope imports fail fast at startup, making bugs visible immediately. Deferred imports mask problems until a specific code path runs.

---

## Projects are living documents — and planners interrogate before designing

Two halves of the same rule. Every `*-PROJECT.md` is a guideline that evolves with execution, and every revision begins with questions to the user — not assumptions.

**Terminology (2026-04-19):** NoctusAI uses *project* for the focused design-and-execution document driving a piece of work (what other teams call a "plan"). The template is `templates/PROJECT-TEMPLATE.md`. Legacy `*-PLAN.md` files may still exist until renamed; treat them as projects regardless.

### Living

A project document that survives execution unchanged means either the work was trivial or you ignored new information. Expect to revise.

- Check off completed items.
- Rewrite phases that no longer reflect current understanding.
- Look for optimizations and fold them back into the project file.
- Commit project changes alongside code changes — they evolve together.

### Interrogate first

Before drafting or revising any project:
- Ask the user clarifying questions.
- Understand business context.
- Confirm constraints.
- Surface edge cases.

Never assume. Only after context is clear should you propose structure.

### Leave a paper trail

Document the question that prompted each revision alongside the change in the project's Change Log. Future agents inherit the reasoning, not just the outcome — they need to know *why* the project evolved, not just *what* changed.

### Start from the template — don't re-invent

Every new `*-PROJECT.md` begins by copying `templates/PROJECT-TEMPLATE.md`. The template exists so agents don't waste tokens rebuilding the same structural skeleton (header, change log, phases, open questions, success criteria, "how to use") every time. Fill in the placeholders, delete sections that don't apply (§5 Architecture is optional; §8 Dependencies can be omitted if none), and start working. If you find a consistent improvement opportunity while using it, update the template itself — it's living too.

### Improvements captured during steps, synthesized into ONE phase proposal

The flow is **capture-then-synthesize**, not capture-per-step:

1. **During step implementation — capture.** As each sub-task is built, drop short specific bullets into the phase's `**Improvements:**` block — free-form, frictionless, no ceremony. These are step-individual-related observations, captured while the context is fresh.
2. **End of phase, BEFORE flipping the header to `✅` — synthesize.** The in-session agent reads the entire accumulated block, considers the **whole project context** (not just this phase), and files **ONE proposal per phase** that bundles the improvements as independently-executable items. The proposal is filed via `noctusai_file_proposal(project="<project-slug>", ...)` and lands in `mcp/noctusai/proposals/<project-slug>/`.

**Not one proposal per improvement — ONE bundled proposal for the phase.** Each bundled improvement retains individual execution (the reviewer schedules them separately) but the proposal is a single coherent context-transfer vehicle: the agent who *lived the phase* captures situational awareness once, and all the bundled items inherit it.

Each phase proposal carries `Origin: project:<project-slug>:phase-<N>` with filled-in `Context`, `Situation`, `Proposed Solution` (with `§3.2 Application instructions` as the bundled-improvement list — each with its own linkage + steps + risks + independence note), `Effects`, and aggregated acceptance criteria.

`improvements.md` (next to the project file, regenerated by `noctusai_improvements`) remains the narrative retrospective. Proposals in `mcp/noctusai/proposals/<project-slug>/` are the triage queue. The two systems cooperate — see `PATTERNS/proposals-and-improvements.md` for the full protocol, the promote boundary, and the bundling mechanics.

---

## Gamification is subtle

NoctusAI products embed gamification (ranks, points, progress) discretely — never confetti-on-every-click. Every metric shows a ⓘ info icon explaining its formula. Every point ties to real business activity, never "logged in today" arbitrariness.

See `07-GAMIFICATION.md` for full patterns and `products/erp-imobiliario/METAS-PLAN.md` for the reference implementation.

---

## Docs stay in sync — and land KB-first, CLAUDE.md second

Every commit that changes behavior updates the relevant docs:
- `CLAUDE.md` (the map + behavioral rules)
- `KNOWLEDGE-BASE/INDEX.md` (the catalog)
- Topical KB file (PHILOSOPHY, PATTERNS/*, GUIDES/*, CONTEXT/0x-*)
- `mcp/noctusai/README.md` when tooling changes

Proposals live in `mcp/noctusai/proposals/`.

### The KB-first ordering rule

When any rule changes, **KB lands first, CLAUDE.md second**. Never the reverse, never both in parallel without KB having settled.

- **KB holds the authoritative long-form content.** CLAUDE.md is the slim pointer layer. If CLAUDE.md gains a new pointer before the KB target exists, the pointer strands (or worse, CLAUDE.md carries content that should have lived in the KB — violating the token-budget split).
- **Order for a new rule:**
  1. Write or update the KB file (`CONTEXT/01-PHILOSOPHY.md`, the relevant `CONTEXT/PATTERNS/*.md`, etc.).
  2. If you created a new file, add it to `KNOWLEDGE-BASE/INDEX.md` in the *same* change.
  3. Only then touch `CLAUDE.md` with the short behavioral rule + pointer.
- **Exception:** tiny CLAUDE.md-only corrections (typos, reordering, comma fixes) that introduce no new concept can land CLAUDE.md-only.
- **Announce the order** when presenting a multi-file doc plan: `KB → CLAUDE.md`. Visibility helps the user verify.

**Enforcement:**
- `scripts/verify-kb-sync.sh` validates that every pointer in `CLAUDE.md` resolves and that `KNOWLEDGE-BASE/INDEX.md` lists every file in the KB. Run pre-commit.
- The KB-first ordering rule is **procedural** — the verifier catches dangling pointers but cannot catch "wrote CLAUDE.md first then backfilled the KB." That discipline is the agent's.

---

## MCP migrations mirror the file

When you apply DDL via the Supabase MCP (`apply_migration` or `execute_sql`), the **exact same SQL** must exist as a numbered migration file in `products/<name>/backend/migrations/NNN_<name>.sql`. Commit the file in the same change set that applied the MCP call.

**Why:** the database is mutable state; the migration files are the authoritative replay log. If the file drifts from what was applied, a fresh clone (or a staging / production deploy) cannot reproduce the current schema. The hosted DB is a consequence, not the source of truth.

**How to apply:**
- **Write the migration file first**, run the parse tests, then apply via MCP. Not the other way around.
- Use `apply_migration` for all DDL (schema changes, policy creation, enum edits) so Supabase's internal migrations table records the version.
- `execute_sql` is for ad-hoc reads only. If you catch yourself running DDL via `execute_sql`, stop and convert it to `apply_migration` + a new file.
- **If you iterated directly on the DB** during debugging, back-port every delta into a new migration file before committing. Never leave DB state that isn't reproducible from the repo.
- Keep the file name deterministic: next unused number in the product's `migrations/` directory + snake_case slug (`016_metas_domain.sql`).
- The MCP migration record gets its own timestamp-based version (`20260418...`); the file number is your sequence; both coexist without conflict.
- For RLS policy churn during development, prefer dropping and recreating the entire policy set in a new migration over surgical `ALTER POLICY` — clarity over incrementalism.

**Red flags:**
- An `execute_sql` call containing `CREATE TABLE`, `CREATE POLICY`, `ALTER TABLE`, `CREATE TYPE`, `ALTER TYPE`, `CREATE INDEX`, `DROP ...`.
- A commit that modifies the DB schema but doesn't touch `migrations/`.
- A migration file whose content doesn't match what's running on the DB (drift).

See `PATTERNS/database-rls.md → MCP + file sync` for the operational recipe.

---

## Supabase MCP is the agent's tool — use it proactively

When a task needs Supabase access — apply a migration, audit a schema, verify an RLS policy, seed data, inspect rows — the agent executes it directly through the `mcp__claude_ai_Supabase__*` tool family. There is **blanket standing approval** for Supa MCP on this repo; no per-task confirmation needed.

**Why:** The user already accepted this cost once and doesn't want to be asked again. Pausing to request "please run this SQL in your Supabase editor" wastes a roundtrip and slows the work. The agent has the capability; the user expects it to be used.

**How to apply:**
- **Default-on:** when the next step needs DB state, go straight to `apply_migration` / `execute_sql` — don't ask.
- **Still follow the MCP↔file sync rule above:** `apply_migration` for DDL (mirrored in `migrations/NNN_*.sql`); `execute_sql` for read-only inspection.
- **Pre-flight checks are fine:** querying `information_schema`, `pg_catalog`, etc. via `execute_sql` before an `apply_migration` is encouraged.
- **Don't silently commit schema changes the user didn't ask for.** "Proactive use of the tool" ≠ "proactive DDL". If you need to change schema to finish a task, the schema change itself is part of what you're shipping — normal plan + review flow applies.
- **Errors:** if a Supa call fails (auth, quota, network), surface the error with a short explanation rather than asking the user to retry manually.

---

## `CLAUDE.md` vs `KNOWLEDGE-BASE/`

- **`CLAUDE.md`** = pointer/map + compact behavioral rules. Loaded every session. Kept lean on purpose.
- **`KNOWLEDGE-BASE/`** = deep context, technical specs, architectural reasoning. Loaded on-demand when Claude needs it.

The split exists to **save tokens every turn**. Heavy spec shouldn't be re-read every iteration. CLAUDE.md tells Claude where to look when the task requires depth.

---

## Every product has a `README.md` and `MASTER-PROMPT.md`

- `README.md` — what the product does, stack, ports, features. For humans browsing the repo.
- `MASTER-PROMPT.md` — authoritative development guide (purpose, architecture, domains, testing, dependencies). For agents or developers implementing features.

New products must include both from day one. See `GUIDES/new-product.md`.
