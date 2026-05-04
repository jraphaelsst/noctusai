# 01 — Engineering Philosophy

> This file is the **long-form elaboration** of the behavioral rules in `CLAUDE.md`.
> CLAUDE.md contains the terse, every-session version Claude reads every turn.
> When an agent needs deeper reasoning or historical context for a rule, it reads here.
> **Sync rule:** if you change a rule in one file, update the other.

---

## Vocabulary — methodology, not doctrine

Per user directive 2026-04-27: **we use "methodology" — not "doctrine".** The rules in this file (and across CLAUDE.md / KB) are the team's chosen *way of working* — collaborative, iterative, owned by the team. They are not commandments handed down from above.

When writing or revising rules, prefer: **methodology**, **rule**, **principle**, **convention**, **pattern**, **working agreement**, **practice**. Avoid **doctrine**, **doctrinal**, **doctrinally** — the framing is hierarchical and runs counter to how this team actually operates.

This is a small word-choice rule with a real cultural payload: agents reading these files inherit the framing. *Rule, not doctrine.*

---

## Seed first. Always.

Every product inherits its structural backbone from `seed/`. When creating a new product, import `create_product_app()` (backend) and `createProductApp()` / `createProductLayout()` (frontend) from the seed framework.

- Do NOT copy-paste structural code.
- Do NOT re-implement auth, routing, layout, database clients, health checks, team management, notifications, or page-status — they come from the seed.
- Do NOT ask whether to use the seed. Do NOT propose alternative approaches to product creation. The seed IS the approach.

This is the #1 engineering rule. It is not optional, not debatable, not a suggestion. The seed is the skeleton. Products are the organs. Read `seed/README.md` before building anything. The user's original framing: *"All future agents should not ask nor doubt, they should straight away use the seed."*

**Why:** Multiple products had duplicated auth, duplicated layouts, duplicated notification code. Every change meant editing N places. The seed centralizes structure; products carry only domain-specific code. Fixing a structural bug means editing the seed once and it propagates to every product — duplication defeats the whole architecture.

**Fix structural issues in the seed, never in individual products.** If three products all need the same tweak, the tweak belongs in `seed/lib/backend/` or `seed/framework/backend/` (or their frontend counterparts), not replicated three times. The "No quick fixes" rule and this rule reinforce each other: a symptom that appears in multiple products is a root-level signal.

### Compliance — what if a product isn't wired?

A product that doesn't call `create_product_app()` / `createProductApp()` is a **violation** of this rule, not a grandfathered exception. If an audit (see `CONTEXT/03-SEED-ARCHITECTURE.md § Compliance check`) finds a product that bypasses the framework — instantiates `FastAPI()` directly, reinvents layout, or reimplements any of the seed's capabilities — the remediation is a focused project:

- Slug: `<product>-seed-wiring` (subject=product, intent=`wiring` per `PATTERNS/project-execution.md §8`).
- Location: `products/<product>/projects/<product>-seed-wiring/`.
- Scope: rewrite `main.py` / `main.tsx` / `App.tsx` around the seed factories, thread existing routers through, verify the test baseline stays green, ship behind the product's existing deploy.

Do **not** paper over the gap by duplicating what the seed provides. Do **not** defer indefinitely. The directory tree under `products/` already implies "all of these are seed-inheriting products" — a non-compliant entry silently lies to every agent who reads it.

---

## MCP toolkit reviews after every change (observation-only)

After modifying code, run `python mcp/noctusai/cli.py --review` on the affected product. The review pass:
1. Detects seed-compliance issues deterministically (`check_seed_compliance`, `check_path_references`).
2. Asks an LLM (OpenAI, via `OPENAI_API_KEY`) to author one proposal per issue. Keeper-originated proposals land in `products/<product>/proposals/` (scoped to the product the detector flagged); project-scoped proposals land inside the project's own `proposals/` folder — at either `projects/<slug>/proposals/` or `products/<product>/projects/<slug>/proposals/` depending on where the project lives (see `PATTERNS/project-execution.md §1`). Callers pass `project=<slug>` or `product=<slug>` — the MCP tool resolves the location.
3. Falls back to a skeleton proposal (just the raw detector output) when the LLM is unavailable — so nothing is silently dropped.
4. Returns a report: `issues_found`, `proposals_created`, `llm_enriched` vs `llm_fallbacks`, and the `final_score`.

**It NEVER modifies code.** Every fix goes through a human who reads the proposal and applies it deliberately.

**Development loop:** change → `python mcp/noctusai/cli.py --review` → triage proposals in `products/<product>/proposals/` (accept / reject) → apply the accepted fixes manually → commit.

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

**The rule applies to test code too — caught + tightened 2026-04-27.** During `therapy-consent-guard-wiring` Phase 1, an autouse `monkeypatch.setattr(ai_pipeline, "require", _noop)` fixture was introduced to "make existing happy-path tests pass" alongside the new patient-consent guard. That is not a test of the guard — it's a deletion of the guard. Same pattern: per-test `monkeypatch.setattr(ai_pipeline, "_notify_therapist_ai_skipped", MagicMock())` to "verify the notification fired." User caught both. Both removed.

The correct shape for testing our own guards / write helpers:
- **Read paths (consent, RLS, role checks).** Seed the real underlying data (rows in `ai_consent`, role columns on `noctus_users`, etc.) so the real guard reads it and reaches its real verdict. Never patch the guard.
- **Write side-effects (notifications, audit rows, log lines).** Use proper dependency injection: an optional kwarg on the function (e.g. `core_db: Optional[Any] = None`) that defaults to `None` and lazily resolves to the real client at runtime when the function actually needs it. Tests pass the same mock as both `db` and `core_db`. Read what the helper actually inserted via `MockRequestBuilder.inserted_payloads` (seed-lib mock attribute, populated automatically on every `insert(payload)` call).
- **External boundaries (LLM APIs, transcription services, third-party HTTP).** `unittest.mock.patch.object(<external>, ...)` is the right tool — that's mocking THE BOUNDARY, not neutering our own logic. The litmus test: if removing the patch reveals real product behavior we want to verify, the patch is wrong. If removing the patch causes a network call to a service we don't own, the patch is right.

Reference: `products/therapy-platform/backend/tests/services/test_ai_pipeline_service.py` post-rewrite. Anti-pattern reference: the same file pre-rewrite (deleted) used `monkeypatch.setattr(ai_pipeline, "require", _noop)` — the rewrite seeds `ai_consent` rows via `_db_with_grants(...)` and uses `core_db=db` injection instead.

---

## No silent errors — always explicit fix opportunities

**Every failure mode surfaces loudly and concretely.** Exceptions, degraded states, missing data, failed builds, skipped steps, deferred items, unverifiable assumptions — all must appear in the user-facing output as explicit fix opportunities, not buried in logs or swallowed in `except: pass`.

The rule has three concrete shapes:

### Runtime / code

- **Never write `try/except:` with an empty body**, a bare `pass`, or a silent `return None` / `return default`. If a failure path is genuinely expected and benign, log-at-WARN with a clear reason string AND document why suppressing is correct. If it's not benign, raise, return a typed `Result`, or surface an HTTPException — but do not swallow.
- **Never catch broadly (`except Exception:`) without re-raising or explicitly surfacing.** `logger.exception(...)` + re-raise is acceptable; `logger.info("oops")` + continue is not.
- **Never suppress a test failure.** Skip-with-reason (`pytest.skip("reason")`) is fine; skip-without-reason or xfail-without-tracking is not.
- **When a dependency is unavailable**, fail to start with a clear error, not a background warning that the feature silently doesn't work (the "optional import degrades gracefully" anti-pattern — the product then runs in an undefined state).

### Agent execution / tooling

- **Never close a session or phase with a command that silently errored.** Build output, pytest summary, linter diff — read them; if anything is red, name it in the summary. "Verification: ✓ built" when the tail of the output showed an import error is a lie to the user.
- **Never finish a deliverable that has unverified claims.** If the agent said "the build is green," it ran the build. If it said "tests pass," it ran the tests. No inference from "it should work."
- **Never bury deferred items.** If an item was deferred, the end-of-work summary names it and names its new home (project folder, backlog entry, next phase). A deferred item without a live destination is a broken pointer.
- **When a tool fails** (MCP call, CLI invocation, curl), report the exact error and what the agent plans to do about it. Not "continuing..." without explanation.

### Communication

- **Ambiguity is a silent error.** If the user's instruction has two reasonable interpretations, ask. Picking one silently and proceeding is a deferred bug.
- **Assumptions are silent errors.** If the agent had to guess (schema, env var, file path), state the guess explicitly and offer the user a redirect path.
- **An absence of findings is a claim.** "No issues found" must mean the agent actually looked, not that the check wasn't run. Quote the command and the verified output.

**Why:** silent errors accumulate into mystery-failure debt. A year later someone asks "why does X not work?" and nobody can trace it because the original agent swallowed the signal. The rule is cheap at the moment of occurrence (one line in the summary, one `raise`) and expensive when violated (debugging with no audit trail). Prefer loud-and-fixable over quiet-and-working-most-of-the-time.

**Interaction with other rules:**

- `End-of-work summary (DEFAULT)` — silent errors break the summary's "verification" line. If verification actually had regressions, list them; don't pretend green.
- `Apply-inline-then-delete` — if a proposal item fails to apply (syntax error, lint rejection, behavior regression), the summary says so explicitly and the item is NOT moved to "applied" — it goes to "deferred: application failed, see <reason>".
- `Finish the session — verify, don't assume` — the verification commands catch many silent errors; read their output.
- `No workarounds` — a workaround often IS a silent error (the workaround makes the symptom go away but the root cause is still there, now invisible).

---

## Triage at decision time — formalize / refactor / accept-with-rationale

**The workflow evaluates itself as it runs. Decisions about ideals-vs-reality are made at the moment they're encountered, with full context — not as upfront ideological rulings that force unnecessary remediation or rigid uniformity.**

User directive (2026-04-22): *"The workflow should evaluate itself as it goes on and decide for the best moves to take at the time they were made."* This is the decision-making methodology sitting between **no silent errors** (surface what's diverging) and **apply inline then delete** (execute the decision).

### The pattern

When the work surfaces a divergence from an ideal (contract violation, architectural drift, pattern inconsistency, test-contract mismatch, whatever), the agent triages it at that moment into one of three outcomes:

1. **Formalize.** The divergence is worth making first-class. Extend the framework / library / seed to turn the ad-hoc pattern into a named, approved seam. Examples: "core needs custom auth — formalize as `authProvider` slot on `createProductApp`"; "three products had duplicate notification-mapping code — absorb into `noctusai_lib.notifications`."

2. **Refactor.** The divergence is forkable. Bring the product (or the call site) into compliance with the existing contract. Examples: "adconnect had its own NotificationBell import but opted out of `"notificacoes"` — fix the opt-in list"; "PF test mocked `app.dependencies.get_supabase_client` which was renamed — update the mock target."

3. **Accept-with-rationale.** The divergence is legitimate but project/product-unique; formalizing would bloat the framework, refactoring would destroy something the product actually needs. Document WHY in the appropriate living record (PROJECT.md §2 or §11 Change Log, or the product's MASTER-PROMPT.md) and move on.

**"Accept" is a real landing, not a failure mode.** Some divergences genuinely belong to the product. The paperwork ("why accepted") is what keeps drift from being silent — a future agent reading the record knows the divergence was intentional, not forgotten.

### The three outcomes are mutually exclusive + always explicit

Every surfaced divergence gets a single labelled outcome recorded in the project's §11 Change Log (or equivalent living record). Shape:

- `Divergence: core has custom app/dependencies.py not extending ProductDependencies.`
- `Outcome: accept-with-rationale. Reason: core is the identity-source product (not Supabase-consumer); the framework's ProductDependencies contract doesn't fit its JWT+refresh-token auth shape. Revisit if a second identity-source product surfaces — that's a strong signal to formalize as customDependencies slot.`

### Recurrence is a signal for formalize

A single product diverging = probably accept. The same divergence in 2 or 3 products = re-triage toward formalize. The pattern "we keep accepting the same thing" means the framework is under-serving a legitimate need; close the gap.

### Why this pattern (and not just "strict contract")

Strict contracts force every divergence into refactor, which:
- Bloats the framework with every product's edge case.
- Strangles legitimate product experimentation.
- Creates a remediation backlog that eventually gets ignored.
- Makes "approved exceptions" a political process instead of an evidence-based one.

Aspirational-only (no triage) makes divergences invisible over time. Drift accumulates silently. Same anti-pattern as "no silent errors" but at the architecture layer.

**Triage-at-decision-time** preserves both: the ideals are stated clearly (so drift is visible), and reality is accommodated explicitly (so divergences don't force bloat or produce remediation debt).

### How to apply

1. Divergence surfaces (keeper, audit, code review, user flag, agent observation).
2. At the point of encounter, the agent writes the divergence down explicitly + picks an outcome: formalize / refactor / accept.
3. For `formalize`: the work becomes the next phase / a new project (e.g., adding a seam to the framework).
4. For `refactor`: the work happens inline (or opens a small remediation project if scope demands).
5. For `accept`: the rationale goes in the living record. Nothing else blocks.
6. The §11 Change Log entry names the outcome. Future agents can audit the pattern's health by counting formalize / refactor / accept ratios over time — if accept dominates, the framework is probably under-serving.

### Interaction with other rules

- `No silent errors` — surfaces the divergence. This rule decides what to do with it.
- `Apply inline + delete` — is how the decision gets executed (formalize-by-seam or refactor ship inline as part of the work's phase).
- `Estimate off evidence` — reads the actual files before picking formalize vs refactor vs accept. Don't triage off inferred architecture.
- `Projects are living` — revisions to the outcome are legitimate as new evidence arrives; a prior "accept" can become "formalize" if a second occurrence surfaces.

### Worked examples

- `core-seed-wiring` Phase 4 — discovered core's frontend needs custom auth. Triaged: **formalize** → added `authProvider` slot to `createProductApp`. Divergence became an approved seam.
- `keeper-standard-routers-audit` Phase 0 — discovered adconnect frontend imports `NotificationBell` but `standard_routers` opted out of `notificacoes`. Triaged: **refactor** → fixed the opt-in list + restored deleted tests.
- `seed-inheritance-hardening` Phase 2 — discovered core's `app/dependencies.py` + `app/database.py` bypass framework factories. Triaged at Phase 4: user decides **formalize** (`customDependencies` seam) OR **accept-with-rationale** (core is identity-source, contract doesn't fit). Default posture: accept + document, re-triage if a second product surfaces the same divergence.

---

## Estimate off evidence, not structure

Before offering a scope estimate — options (A/B/C), session-size, time-box, "this should be quick" — **open the files the change would actually touch**. If the change would affect a shared library, framework, factory, or cross-cutting layer, read that code first. Don't estimate off inferred architecture.

**Why this matters:** when the user picks an option based on a shallow estimate, they're committing to the scope you described. Discovering the real scope mid-execution forces a course-correction, wastes the tokens already spent, and erodes trust in future estimates. The cost of reading a file before estimating is negligible; the cost of a mid-flight scope revision is not.

**Concrete failure mode (2026-04-20 — this rule was born from it):** an option-list was offered for migrating `products/core` to `create_product_app()` from the seed framework. The estimate assumed "just edit `core/main.py` and `App.tsx`." Only after the user chose Option 3 (do it this session) did the agent open `seed/framework/backend/noctusai_seed/app.py` and discover that `create_product_app()` auto-registers `/api/team`, `/api/notificacoes`, `/health`, `/api/llm/*` — routes that would collide with core's own control-plane routers — and scopes a `DatabaseModule` to a single product schema, incompatible with core's `public`-schema model. The real scope was a seed-framework refactor (a proper project), not a file edit. The option list itself was the defect.

**How to apply:**

- Before listing options, check: does this touch `seed/`, `noctusai_lib`, `noctusai_seed`, `@noctusai/lib`, `@noctusai/seed`, the seed framework factories, or any shared migration path? If yes → read the target file(s) before writing the option list.
- Before quoting a session-size or "this is quick" → actually trace the caller / the dependents. If the change would cascade into multiple files across products, the work is bigger than a session.
- If you catch yourself writing "this should be straightforward" or "I think this is small" — stop. Those are feelings, not estimates. Open the file.
- When a user asks "is this big?" — answer with what you have already confirmed by reading code, not what the file names suggest.
- If you have already offered a shallow estimate and then discover the real scope — stop, tell the user immediately, recommend re-scoping as a proper project (see `PATTERNS/project-execution.md §1`). Do not silently continue and course-correct inside the same execution.

**Interaction with other rules:**

- `CLAUDE.md "For exploratory questions, respond in 2-3 sentences with a recommendation..."` — that recommendation must be evidence-backed. The 2-3 sentences get shorter when you've read the code; they get *wrong* when you haven't.
- `Projects are living documents` — a revision mid-flight is always allowed, but the Change Log should record *why* the revision happened. "Shallow estimate; real scope discovered during execution" is a legitimate Change Log entry — but aim not to write it.

---

## Safety nets capture failures; failures become learnings; methodology evolves

**The principle.** Methodology is incomplete by design. Every methodology has gaps — cases it doesn't cover yet, edge conditions it didn't anticipate, environments it hasn't been stress-tested in. **Safety nets** are the mechanical layer underneath the methodology that keeps the system working when the methodology hits a gap. **Failures**, when caught by a safety net, are the methodology's evolution surface. Capture the learning, update the methodology, the gap closes. Future occurrences hit the updated methodology, not the gap.

**Why this is foundational:** treating methodology as fixed leads to two failure modes: (a) the methodology calcifies and people work around it (silent erosion), or (b) the methodology fails and people panic because the rule didn't anticipate the case (false sense that the rule should have been complete). Treating methodology as evolving — with safety nets that catch failures and a discipline that turns failures into learnings — keeps both pathologies at bay.

**The shape:**

1. **Methodology hits a gap.** Some case the rule didn't cover — a non-fast-forward push fails, a regex matches false-positive, a parallel agent's WIP blocks a switch.
2. **Safety net catches the work.** `git merge` for the merging gap. The drive-by-exception clause for hook false-positives. `git stash` for switch blockers. The mechanical layer keeps the system working while the methodology learns.
3. **Capture the learning.** Per `§ 2.11 Phase enrichment loop` — log to the SQLite tracker if the gap surfaced during a phase. Per `§ 2.7 Recurrence rule` — if N=2+ instances surface, formalize. The learning is durable, not narrative.
4. **Update the methodology.** Three-way sync: KB body, CLAUDE pointer, memory entry. The gap closes structurally, not in conversation memory.
5. **Future occurrences hit the updated methodology, not the gap.** The methodology covers a new case. The cycle is the platform learning to handle a class of failures it couldn't before.

**Examples** (each one a real instance):

- **Merging methodology gap (in-flight 2026-05-03).** `git merge` is the safety net for the cases our methodology hasn't codified yet (non-FF integration, multi-branch convergence, conflict resolution). The merging methodology project (`projects/merging-methodology/`) is the learning loop closing.
- **Detector regex precision (shipped 2026-05-03).** The `_shipped_phases_in_changelog` detector false-positive on cross-file references was a methodology gap. Workaround at the time was rephrasing prose; the structural fix (strip code spans) is the methodology evolving. Captured in `feedback_branching_methodology.md` companion + the regex fix itself.
- **Pre-commit hook drive-by-exception (codified 2026-05-03).** When a hook blocks your commit on another agent's incomplete state and the fix is small + non-destructive, apply it inline. The drive-by carve-out IS the methodology evolution from the original "never touch parallel-agent files" absolute.

**Companion rules:**

- `§ 2.7 Recurrence rule` — when learnings become formalize-triggers (N=2 → triage; N=3+ → must formalize).
- `§ 2.11 Phase enrichment loop` — where learnings get captured durably (SQLite tracker, log per phase, query before next).
- `Triage at decision time` — what to do with a learning (formalize / refactor / accept-with-rationale).
- `Three-way sync — KB ↔ CLAUDE ↔ memory move together` — how methodology updates land structurally, not just in agent memory.
- `No silent errors` — a failure that's silently absorbed isn't a learning; it's debt. The safety net catching the failure must be visible (commit message, change log, memory entry).

**Anti-patterns:**

- **Bypassing the safety net to avoid surfacing the gap.** "I'll just `--force` push so I don't have to deal with it" — defeats the entire mechanism. The methodology never learns; the same failure recurs.
- **Treating safety-net activations as failures of the rule.** Methodology gaps aren't bugs in the methodology; they're its evolution surface. The safety net activating IS the methodology working — it caught what the rule didn't yet cover.
- **Capturing the failure but skipping the methodology update.** A learning that lives in a §11 prose entry but never makes it to the methodology doc is conversation-memory at best, lost at worst. The capture must triple-sync (KB + CLAUDE + memory) for the methodology to actually evolve.
- **Repeating the same safety-net catch without ever formalizing.** N=2 should trigger triage; N=3 must formalize (per recurrence rule). If the same gap keeps catching the same fix, the methodology hasn't evolved — only the conversation has.

---

## Branching-first orchestration — parallelize by default; serial only when chunks collide

**The principle.** The dev methodology is **branching-first**. The orchestrator's default mental model on any incoming work: "can this be chunked into parallel branches?" If yes — dispatch subagents on separate branches in a single tool-use turn (true parallelism via `Task`). If no (chunks genuinely collide on files/lines OR have hard dependencies) — serial work, OR the master-tree-parallel-batches pattern for N≥2 same-shape children.

**Sequential is the carve-out, not the default.** Most non-trivial work has multiple chunks; most chunks touch disjoint file sets. Wall-clock leverage from parallelism is real and large; leaving it on the table by default is a structural waste.

**Why this is foundational, not just tactical:**

1. **Wall-clock leverage compounds.** N independent chunks dispatched in one `Task` tool-use turn finish in roughly 1×T (worst-case slowest chunk), not N×T. Across a session with many projects, the gap is hours, not minutes.
2. **Different vantage points are structural** (per `KB § PATTERNS/branching-and-merging.md § 12 Orchestrator role`). Each subagent has its own narrow context; the orchestrator collates at merge time. Parallelism multiplies this benefit — N subagents each contributing a fresh narrow vantage point converge at orchestrator-merge.
3. **Branches isolate failure.** One chunk failing doesn't poison sister chunks. Serial execution means a mid-stream failure blocks everything downstream; parallel means each chunk's failure is local.
4. **The merging methodology already handles convergence** (per `KB § PATTERNS/branching-and-merging.md § 10`). Branches queue at merge time per § 10.3 multi-branch convergence; same-line conflicts resolve per § 10.4. Parallelism doesn't introduce new failure modes — it reuses the merge methodology already shipped.

**Chunk identification (the orchestrator's first move):**

Before any work starts, the orchestrator asks:

- **File-overlap analysis:** what files would each chunk touch? Disjoint sets → safe parallel. Overlapping sets → potential collision.
- **Methodology-overlap analysis:** chunks editing the same KB doc / CLAUDE.md section collide on lines even if file sets differ at the directory level.
- **Dependency analysis:** does chunk A need chunk B's output? Hard yes → serial. Soft no / parallel-feasible-with-coordination → parallel via the master-tree-parallel-batches pattern.
- **Subagent vs orchestrator-direct:** is each chunk substantial enough to warrant a `Task` subagent? Tiny chunks may be cheaper to do directly (orchestrator-mode) sequentially.

The output of chunk identification is one of:

- **Parallel dispatch:** N independent chunks, branched + dispatched in a single `Task` tool-use turn.
- **Master-tree parallel batches:** N≥2 same-shape children sharing methodology; orchestrator runs the batches per `KB § PATTERNS/master-tree-parallel-batches.md`.
- **Serial:** dependencies make parallel infeasible; sequential is correct.
- **Orchestrator-direct:** chunks are too small for delegation overhead; do directly.

**The default is parallel; serial requires justification.** When the orchestrator chooses serial, the choice is logged (a learning to the SQLite tracker per `§ 2.11 Phase enrichment loop`) — "considered parallel; chose serial because <X>." This way the methodology sees the rejection rationale and the recurrence rule can fire if "chose serial because" repeats.

**Anti-patterns:**

- **Serial by default when parallel was feasible.** Leaves wall-clock leverage on the table without surfacing the choice. Always consider parallel first.
- **Dispatching subagents in separate messages.** Per `Task` tool: parallel only happens when multiple `Agent` tool uses are in a SINGLE message. Two messages = serial. The mechanism is clear; respect it.
- **Forcing parallelization when chunks genuinely depend.** If chunk B needs chunk A's output, parallelizing surfaces as merge conflicts or B-built-on-stale-A. Cheaper to serialize than to hand-merge later.
- **Skipping chunk identification.** Dispatching subagents on overlapping file sets pre-emptively guarantees merge conflicts. Spend the 30 seconds to map file sets first.
- **Treating multi-branch merge as a problem.** It's the methodology working. Per `§ 10.3`, branches queue at merge — auto-merge handles disjoint, manual resolution handles overlap. Both paths are documented.
- **Delegating the orchestration itself to a subagent.** Caught 2026-05-03 — the orchestrator dispatched a subagent to do the analysis + batching + planning for an in-flight portfolio, then waited passively. That collapses the head/worker distinction: the subagent only sees its brief, not the session-spanning conversation; the orchestrator's broad-context advantage IS the planning value. **Subagents are EXECUTORS of focused chunks; they are never PLANNERS of orchestration.** The head plans + dispatches; subagents execute the chunks the head defined. Hand-off rule: if you're tempted to dispatch ONE subagent to "figure out how to parallelize this," STOP — that's the orchestrator's job. Read the files yourself; compute the batches yourself; THEN dispatch N parallel executors with focused briefs.

**The orchestrator's responsibilities — full list:**
1. **Plan + chunk** the work (file-overlap analysis + dependency analysis).
2. **Set up worktrees** per `KB § PATTERNS/branching-and-merging.md § 16` for parallel dispatch (mandatory when 2+ subagents concurrent).
3. **Dispatch subagents** in single `Task` tool-use turn with focused briefs.
4. **Maintain findings.md** for the orchestration (per `Knowledge tracking — durable findings file` principle below + `KB § PATTERNS/branching-and-merging.md § 17`). Append slips / errors / lessons / surprises as subagent reports come in.
5. **Aggregate + merge** subagent branches at orchestrator-merge time (per § 12 of branching-and-merging).
6. **Close the orchestration** — synthesize findings.md into the durable knowledge artifact; archive the project per § 11.2.

**Companion rules:**

- `KB § PATTERNS/branching-and-merging.md § 11 Branch-per-project workflow` — the per-project branching mechanic this principle elevates.
- `KB § PATTERNS/branching-and-merging.md § 12 Orchestrator vs working-agent role split` — the orchestrator role this principle defines as default-parallel.
- `KB § PATTERNS/branching-and-merging.md § 13 Branch-creation triggers` — user-phrase triggers ("branch this") are explicit; this principle adds an implicit trigger (orchestrator's default mental model).
- `KB § PATTERNS/master-tree-parallel-batches.md` — when N≥2 same-shape children, this is the parallel-batches pattern.
- `KB § PATTERNS/branching-and-merging.md § 14 Pre-work fetch protocol` — collision detection BEFORE editing; what enables clean parallel chunks.
- `KB § PATTERNS/branching-and-merging.md § 16 Git worktree for true parallel agents` — single-worktree contention is the practical constraint; `git worktree add` is the resolution.
- `KB § PATTERNS/branching-and-merging.md § 17 Knowledge tracking during orchestration` — orchestrator maintains findings.md aggregating subagent slips / errors / lessons / surprises.

---

## Knowledge tracking — durable findings file for any non-trivial work

**The principle.** Any non-trivial work maintains a durable `findings.md` (or equivalent) file capturing **slips / errors / mistakes / lessons / interesting findings / discovered knowledge** as the work progresses. The file lives at the project / feature root during execution and travels with the project to archive at close.

**Why:** Without a durable durable surface, learnings live in conversation memory (lost between sessions), commit messages (durable but unstructured), or §11 prose (durable but optimized for "what we did," not "what we learned"). The findings.md is purpose-built for the latter — a curated knowledge artifact, not a transcript.

User directive 2026-05-04, verbatim:
> *"Please, as their orchestrator, i need you to keep track of their work and their findings, gather pieces of knowledge throught the process and give me a file with them. I want interesting findings annotations and piece of knowledge gathered from errors, mistakes, slips, lessons and stuff. ... We want that doc'd even if we're not branching."*

**Five categories** (all that the user specified, in standard headings):

```markdown
# <project-slug> — Findings

## Errors encountered
## Mistakes / slips
## Lessons learned (durable rules)
## Interesting findings (surprises, discoveries)
## Knowledge pieces (durable patterns)
```

**When to maintain findings.md:**

| Situation | findings.md? |
|---|---|
| Non-trivial project (multi-phase) | **Yes — default-on** |
| Multi-step feature | **Yes — default-on** |
| Master-tree orchestration | **Yes** (alongside existing live-patterns-log.md + absorption catalog) |
| Orchestrator dispatch of 2+ subagents | **Yes** (per `KB § PATTERNS/branching-and-merging.md § 17`) |
| Trivial direct fix (typo, broken link) | Skip |
| Solo orchestrator-direct work, fully predictable | Optional (skip if no surprises; log absence to `phase_learnings` so silence is explicit) |

**Append cadence:**

- **In-the-moment** for surprises / errors / slips — freshness matters; don't batch.
- **At each subagent report** (orchestration case) — extract findings from subagent's response, append.
- **At each phase close** — review the phase, capture lessons.
- **At project / feature close** — final synthesis pass: turn the log into a knowledge artifact (cross-reference KB amendments, group related lessons, mark which are durable vs. transient).

**Distinct from sibling tracking files:**

- **`phase_learnings.db`** (SQLite, per `§ 2.11 Phase enrichment loop`) — atomic per-phase learnings with structured kind tags. The findings.md is broader: orchestration-level meta-record, not just learnings.
- **`live-patterns-log.md`** (master-tree) — append-only batch findings table. The findings.md is curated; the patterns log is raw append-only.
- **`§11 Change log` of PROJECT.md** — narrative of WHAT was done. The findings.md captures WHAT WAS LEARNED.

**Anti-patterns:**

- **Skipping findings.md for non-trivial work.** Slips evaporate; methodology can't evolve from what wasn't captured.
- **findings.md as a raw transcript.** Only INTERESTING / NON-OBVIOUS / SURPRISING content belongs. "We did X" goes in §11 of PROJECT.md.
- **Skipping the close-time synthesis pass.** Without synthesis, the file is a list of timestamps; with synthesis, it's a curated knowledge artifact.
- **Capturing in conversation memory only.** Lost between sessions. The findings.md is the durable surface.

**Companion rules:**

- `Safety nets capture failures; failures become learnings; methodology evolves` — durable findings → recurrence rule firing → methodology amendment. The findings.md is the input to that loop.
- `§ 2.11 Phase enrichment loop` — atomic per-phase learnings; findings.md is the broader meta-record.
- `KB § PATTERNS/branching-and-merging.md § 17 Knowledge tracking during orchestration` — orchestration-specific specialization.

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

## AST-first — never regex code edits

Every code change goes through an **AST tool** — `libcst` for Python (parse → modify → render with formatting preserved), `ts-morph` for TypeScript, `tree-sitter` for cross-language analysis. **Regex / sed is for prose, search, and log inspection only — never for editing code.**

User direction (absorbed into NoctusAI on 2026-05-03 from the methodology lab): *"Any code change goes through an AST tool (libcst / ts-morph / tree-sitter); regex/sed only for prose, search, log inspection."*

**Why:** regex-driven code edits silently corrupt code. The same substring inside a string literal, a comment, a docstring, or an unrelated identifier gets rewritten alongside the target; multi-line constructs break under one-line patterns; whitespace and trailing-comma variants slip through. AST tools parse the structure, so every edit is scope-aware: rename-in-scope only renames the binding, find-callers only catches the callers, codemods preserve formatting.

**The rule:**

- **Code edits → AST tool.** `libcst` for `.py`; `ts-morph` for `.ts` / `.tsx` / `.js` / `.jsx`. Repo-level codemods live in `scripts/codemods/` or as MCP tools.
- **Markdown / config / log inspection → regex / sed / grep is fine.** Prose has no syntactic structure to violate.
- **Search-only → regex is the right tool.** `grep` / `rg` for finding occurrences. The discipline kicks in when you EDIT.
- **One-shot text replacement in a single non-code file** — fine.

**Boundary rule:** *if the file you're editing is parsed by a compiler / interpreter / type-checker, use the AST tool. If it's parsed by humans only, regex is fine.*

**Anti-patterns:**

- *"It's just a quick rename, I'll use sed."* — sed will rename the matching strings in comments / docstrings / unrelated identifiers. Use a libcst `RenameInScope` codemod.
- *"The regex matches only one place — I checked."* — *now*. The next agent rerunning the same regex on a refactored tree will hit a different set of matches.
- *"Hand-edit + find-and-replace in the editor for a multi-file change."* — same trap as sed; just slower. The editor's "find in scope" is only language-aware when it's running an LSP — and LSP renaming IS an AST operation, just exposed differently.

**Companion to** the seed-first rule (every code edit in this repo runs against framework code that products import — a regex slip-up cascades) and no-quick-fixes (a sed-driven "fix" that hits the wrong substring is the textbook quick-fix that creates future work).

**Toolchain reference + concrete recipes** (rename-in-scope, find-callers, find-pattern, apply-codemod): `PATTERNS/ast.md`.

The MCP toolkit at `mcp/noctusai/` already ships AST-based tools (`outline_python.py`, `outline_typescript.py`); future repo-wide rename / codemod tools land via `projects/mcp-server-expansion/`.

---

## MCP-first — agent-exposable capabilities default to MCP

When you want to expose a capability to **agents** (Claude Code, future Claude Desktop / VS Code MCP hosts, future bots, future product agents), the **default surface is the MCP server at `mcp/noctusai/`**. Dev tooling, business-logic primitives, vendor adapters all converge there as one growing wide-purpose toolkit. The 24-tool dev toolkit is **one branch among many**, not the whole identity.

User direction (established 2026-05-03 in the absorption-evaluation session): *"the idea is for us to really evolve our mcp server. I'm talking about literally growing it, the dev toolkit should be a branch of it, we should bring the other mcp inside so we have a broader and even better wide-purpose toolkit, for more tools rather than only deving."* Explicitly parallel to AST-first: *"we are doing the ast-first, so it makes sense to also adopt the mcp-first mentality and expand it for a broader use."*

**Why:** both rules establish a default surface for a class of work — AST for code edits, MCP for agent-exposable capabilities — so we stop re-deriving the answer per task. When the surface is consistent, the tooling around it (testing, observability, naming, registration) compounds.

**The rule:**

- **Agent-exposable capability → MCP tool first.** Scheduling helpers, calendar / maps lookups, message senders, codebase / log search, schema queries, audit-row writers, business-logic primitives all land as `mcp/noctusai/tools/<umbrella>/<service>/<action>.py`.
- **Naming convention.** 3-segment dotted (`<umbrella>.<service>.<action>`) per `projects/mcp-server-expansion/` Phase 3.
- **Pattern shape.** Pydantic in/out schemas with `Field(description=...)` for self-documenting MCP introspection. Hierarchical registration (umbrella → service → leaf, each `register(server)`). Lazy dependency container at `mcp/noctusai/context.py` for business-logic tools that need DB / adapters / clients.
- **Composition belongs to the consumer.** MCP tools are primitives; bot orchestrations / pipelines compose them. Don't bake bot-specific orchestration into the MCP itself.
- **Existing dev tools stay.** The 24 `noctusai_*` dev tools at `mcp/noctusai/tools/*.py` are the first branch (`platform.dev.*`); they migrate to dotted naming + Pydantic schemas opportunistically per the broaden project's phased plan.

**Boundary rule (MCP vs in-process import):** if a capability has only one consumer and that consumer always co-locates with it, a plain Python function is fine. The MCP-first rule fires when there's a plausible second consumer (another agent, another product, Claude Code) — that's when MCP becomes the default. Promotion is cheap (wrap an existing function with `register(server)`); demotion is rare.

**Companion to** AST-first (both establish a default surface for a class of work) and Seed-first (the MCP becomes the platform's agent-exposable surface, just as `seed/` is the platform's framework surface).

**Operational reference (forthcoming):** `KB § PATTERNS/mcp-tool-conventions.md` lands via `projects/mcp-server-expansion/` Phase 6.

---

## Flag MCP-first / AST-first opportunities proactively

Both default-surface rules above (`MCP-first`, `AST-first`) describe what to do when the surface is the **target** of your work. This rule fires when the surface is a **bystander** — you spot a missed opportunity *while doing something else* and the temptation is to silently move on.

User direction (established 2026-05-03 during the FastMCP-switch session): *"add to claude.md a point for specifically flagging mcp-first opportunities, as well as possible ast-first also … we actively search for improvements ops for our projects, why wouldn't we do the same for the great connector and tooler we have?"*

**Why this is its own rule (not a footnote on the others):** the existing project-execution methodology already encodes active opportunity-spotting (`KB § PATTERNS/project-execution.md § Active robustness review during execution` — eyes open while editing, capture in the live `**Improvements:**` block). The platform's two default surfaces — MCP for agent-exposable capabilities, AST for code edits — deserve the same active lens. Without an explicit rule, "I'll just write a quick helper" / "I'll just sed-edit the file" wins by default and the surface erodes one shortcut at a time.

**The rule:**

- **While working anywhere in the codebase, scan for two opportunity classes:**
  1. *MCP-first* — a capability you're authoring that has (or will plausibly have) a second consumer, but is being written as a private helper / per-product service.
  2. *AST-first* — a code edit you're about to do (or about to recommend) via regex / sed / find-replace where libcst / ts-morph would be safer.
- **When you spot one, surface it.** Two valid responses:
  1. **Apply now** — when the work is in scope and the cost is low (e.g., wrap the helper in `register(server)` instead of leaving it inline; reach for libcst instead of sed).
  2. **Defer with destination** — log the opportunity in the active project's `**Improvements:**` block, the accept-with-rationale catalog (if recurring), or as a follow-up project. Silent skipping is forbidden — it's the same anti-pattern as "absence of findings is a claim" (`§ No silent errors`).
- **The trigger is opportunity, not certainty.** If you're not sure whether the second consumer exists, surface the question; don't treat "I don't know" as a reason to proceed without flagging.

**Anti-patterns:**

- *"I'll add this MCP tool later."* — there is no later; either apply now or log the deferral with a destination.
- *"It's just one sed call, the regex is safe."* — same trap as "the regex matches only one place" (§ AST-first); flag it and reach for libcst, or document the regex carve-out in the improvements block.
- *"This helper is only for product X."* — fine until product Y needs it. The MCP-first boundary rule fires on plausible second consumers, not certain ones; flag the candidate so the recurrence rule can act when N=2 lands.

**Companion to** Active robustness review during execution (same active-search behavior, applied to a different opportunity class), No silent errors (silent skipping is the same shape of slip), the recurrence rule (flagged candidates feed N=2 triage and N=3 formalization).

**Operational reference:** `KB § PATTERNS/mcp-tool-conventions.md § 0. The MCP server is a living organism` + `KB § PATTERNS/ast.md`.

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
2. **End of phase, BEFORE flipping the header to `✅` — synthesize.** The in-session agent reads the entire accumulated block, considers the **whole project context** (not just this phase), and files **ONE proposal per phase** that bundles the improvements as independently-executable items. The proposal is filed via `noctus.dev.file_proposal(project="<project-slug>", ...)` and lands inside the project's own `proposals/` folder — at `projects/<slug>/proposals/` for root-level projects, or `products/<product>/projects/<slug>/proposals/` for product-scoped projects. The MCP tool resolves the slug automatically; callers pass only the slug. See `PATTERNS/project-execution.md §1` for the two-location rule.

**Not one proposal per improvement — ONE bundled proposal for the phase.** Each bundled improvement retains individual execution (the reviewer schedules them separately) but the proposal is a single coherent context-transfer vehicle: the agent who *lived the phase* captures situational awareness once, and all the bundled items inherit it.

Each phase proposal carries `Origin: project:<project-slug>:phase-<N>` with filled-in `Context`, `Situation`, `Proposed Solution` (with `§3.2 Application instructions` as the bundled-improvement list — each with its own linkage + steps + risks + independence note), `Effects`, and aggregated acceptance criteria.

`improvements.md` (next to the project file, regenerated by `noctus.dev.improvements`) remains the narrative retrospective. Proposals in the project's `proposals/` folder (at whichever of the two locations the project lives — see `PATTERNS/project-execution.md §1`) are the triage queue. The two systems cooperate — see `PATTERNS/proposals-and-improvements.md` for the full protocol, the promote boundary, and the bundling mechanics.

---

## Gamification is subtle

NoctusAI products embed gamification (ranks, points, progress) discretely — never confetti-on-every-click. Every metric shows a ⓘ info icon explaining its formula. Every point ties to real business activity, never "logged in today" arbitrariness.

See `07-GAMIFICATION.md` for full patterns + the shipped ERP metas service (code at `products/erp-imobiliario/backend/app/services/metas_*.py` + frontend at `products/erp-imobiliario/frontend/src/pages/MetasDashboard.tsx`) for the reference implementation. The `erp-metas` project that built it shipped 2026-04 + folder deleted per clean-folder rule.

---

## Docs stay in sync — three-way sync across KB, CLAUDE.md, and memory

Every commit that changes behavior updates the relevant docs:
- **`KB`** — `KNOWLEDGE-BASE/INDEX.md` (the catalog) + topical KB file (PHILOSOPHY, PATTERNS/*, GUIDES/*, CONTEXT/0x-*).
- **`CLAUDE.md`** — the map + behavioral rules + pointer.
- **`memory`** — the persistent feedback / project / reference file under `~/.claude/projects/.../memory/` + the `MEMORY.md` index entry.
- `mcp/noctusai/README.md` when tooling changes.

**Three-way sync is mandatory.** Any rule, methodology, or behavioral change lives in **all three layers simultaneously**: KB depth + CLAUDE.md pointer + memory entry. Updating one without the others creates drift the next agent can't see — KB has the long-form, CLAUDE.md has the rule-as-loaded-every-turn, memory has the persistent across-conversation framing. They are three views of the same rule, and they must agree.

**Triggering events:**
- A new `feedback_*.md` memory file is added → corresponding KB section + CLAUDE.md pointer must exist (or be created in the same session).
- A KB rule changes (added, extended, audit-trail updated) → memory entry filed (if user-preference-shaped) + CLAUDE.md pointer updated.
- A CLAUDE.md rule changes → KB depth + memory entry must back it.

**Ordering rules:**
- *When introducing a NEW rule:* KB-first (topical file + INDEX.md), then CLAUDE.md pointer, then memory entry citing both. Never the reverse — CLAUDE.md is the pointer layer and stranded pointers (pointing into nonexistent KB content) violate the contract.
- *When amending an existing rule* (extending, adding caught-instances, adjusting framing): all three layers in the same session. Partial updates lie about the rule's current state and the next agent reads a stale rule.

**Verification:**
- `bash scripts/verify-kb-sync.sh` — catches dangling KB ↔ CLAUDE.md pointers (pre-commit-hooked).
- Memory parity check (manual, agent's discipline): every memory entry in `MEMORY.md` should cite a `Doc-backed (CLAUDE.md + KB § ...)` line in its description; every CLAUDE.md rule with strong behavioral implications should have a memory entry. The `verify-kb-sync.sh` script does NOT verify this — it's the agent's discipline.

**Exempt:** tiny typo-only fixes (single layer, no rule change).

Project-scoped proposals live inside the project's own `proposals/` folder — either `projects/<slug>/proposals/` (root, for cross-product/platform work) or `products/<product>/projects/<slug>/proposals/` (product-scoped). See `PATTERNS/project-execution.md §1` for the rule. Keeper / LGPD / evaluation proposals live in `products/<product>/proposals/` (scoped to the product the detector flagged).

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

## Context budget discipline — `CLAUDE.md` is router, KB is depth, topical loads on-demand

> **Rule.** Auto-loaded surfaces (`CLAUDE.md`, `MEMORY.md` index) stay slim — every line costs per-turn tokens. Depth, examples, slip-history, and topical rules live in the on-demand layer (KB, individual `feedback_*.md` files, `CLAUDE/<topic>.md` sub-files). New rules go KB-first, then CLAUDE.md (or topical sub-file) gets a lean pointer. *Why this matters:* the auto-loaded budget compounds — a 10K bloat in CLAUDE.md costs 10K *every reply* across the entire session. The on-demand layer pays the cost only when the topic is actually relevant.

### The three layers

- **`CLAUDE.md`** (auto-loaded, always) — universal behavioral rules + pointers. Kept lean. Every §1 bullet ≤80 words (per § 2.8 in `KB § PATTERNS/project-execution.md`).
- **`CLAUDE/<topic>.md`** (auto-loaded NO — read by agent when working on the topic) — topical behavioral rules: `CLAUDE/backend.md`, `CLAUDE/frontend.md`, `CLAUDE/projects.md`, `CLAUDE/platform.md`. Each is a sibling-of-CLAUDE.md routing extension, NOT depth.
- **`KNOWLEDGE-BASE/`** (on-demand) — heavyweight depth, examples, slip-history, audit trails, principle-level reasoning. Pointed-to from CLAUDE.md and the topical files.

### Topical CLAUDE/<topic>.md loading discipline

The agent loads a topical sub-file when starting work on that topic. The §3 "When to read what" table in `CLAUDE.md` is the canonical routing manifest. Default loadings:

- **Backend code edit** → also read `CLAUDE/backend.md`.
- **Frontend code edit** → also read `CLAUDE/frontend.md`.
- **Starting a project / phase / scaffold** → also read `CLAUDE/projects.md`.
- **Touching cross-cutting platform** (LGPD, MCP toolkit, MCP-first decisions, clean-folder, KB depth itself) → also read `CLAUDE/platform.md`.

A topical file is NOT auto-loaded by the harness — the discipline is the agent's. If you skip the topical file when the topic applies, you're missing rules that exist. Treat the §3 table as a checklist, not a suggestion.

### MCP keep-list

Active MCP servers in this repo are restricted to a keep-list:

- **`noctusai`** — local project MCP (dev toolkit + business primitives + vendor adapters). Configured in `.mcp.json` + `.claude/settings.local.json`.
- **`supabase`** (claude.ai connector) — DB ops via `mcp__claude_ai_Supabase__*`.

**Anything else is off-list.** Notably, `claude-in-chrome` and the wide catalog of `mcp__claude_ai_*` connectors (Notion, Stripe, Gmail, etc.) are NOT on the keep-list — they exist as catalog entries but should not be invoked in this repo without explicit user OK.

Disable paths for non-keep-list MCPs:
- `claude-in-chrome` — Chrome extension toggle (Claude Desktop preferences → `chromeExtensionEnabled`) or Claude.ai connector settings; the CLI cannot directly disable a Chrome-extension-registered MCP server.
- `mcp__claude_ai_*` connectors — managed at claude.ai web settings → Connectors. Most appear in the deferred-tool catalog as unauthenticated stubs and are harmless until invoked.

Adding a new MCP requires explicit user approval (not "did the agent guess this would help?").

### Skills keep-list

Bundled Claude Code skills used in this repo:

- **`update-config`** — harness config edits (settings.json, hooks).
- **`loop`** — recurring tasks / polling.
- **`schedule`** — background routines (CronCreate-based).
- **`security-review`** — occasional security passes.

**Off-list (policy)**: `keybindings-help`, `simplify`, `fewer-permission-prompts`, `claude-api`, `init`, `review`. Bundled skills can't be CLI-disabled, but the policy reduces accidental invocation. (`init` and `review` overlap with repo-native tooling — `CLAUDE.md` already exists; the MCP keeper performs reviews.) `claude-api` is for building Anthropic SDK apps directly; this repo's LLM access goes through `noctusai_lib.llm` so the skill rarely applies.

### Why this rule earns its CLAUDE.md slot

The `CLAUDE.md`-vs-`KB` split was already a methodology rule. This expanded version codifies the *topical* layer that didn't previously exist (`CLAUDE/<topic>.md`), and codifies *which MCPs and skills are in-scope* — both directly bear on per-turn cost. Without an explicit keep-list, future agents add MCP servers casually, each one inflating the deferred-tool catalog and the system-reminder budget.

### How to apply

- New behavioral rule → land KB anchor first; pointer in CLAUDE.md OR the appropriate `CLAUDE/<topic>.md` sub-file (universal vs. topical decision); memory file added with three-way sync.
- New §1 bullet pushing >100 words → trim to ≤80; push the long-form into KB; pointer points to the new anchor.
- New MCP server proposed → check the keep-list. If not on it, file a project requesting addition with rationale.
- New bundled-skill use proposed → same drill.

### Cross-references

- `KB § PATTERNS/project-execution.md § 2.8 Multi-phase rule shipments — forward-stub + bullet-weight discipline` — the ≤80-word rule + measurement discipline.
- `KB § PATTERNS/agent-reading-discipline.md § Narrow-read first` — same per-turn-cost framing applied to file reads.
- This file § Docs stay in sync — three-way sync across KB, CLAUDE.md, and memory.

---

## `CLAUDE.md` vs `KNOWLEDGE-BASE/` (preserved — see § Context budget discipline above)

- **`CLAUDE.md`** = pointer/map + compact behavioral rules. Loaded every session. Kept lean on purpose.
- **`KNOWLEDGE-BASE/`** = deep context, technical specs, architectural reasoning. Loaded on-demand when Claude needs it.

The split exists to **save tokens every turn**. Heavy spec shouldn't be re-read every iteration. CLAUDE.md tells Claude where to look when the task requires depth.

---

## Every product has a `README.md` and `MASTER-PROMPT.md`

- `README.md` — what the product does, stack, ports, features. For humans browsing the repo.
- `MASTER-PROMPT.md` — authoritative development guide (purpose, architecture, domains, testing, dependencies). For agents or developers implementing features.

New products must include both from day one. See `GUIDES/new-product.md`.
