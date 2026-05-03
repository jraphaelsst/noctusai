# Project Execution Conventions

> How agents write, tick, and advance `*-PROJECT.md` / `task.md` files.
> The user reads `improvements.md` as the project's **retrospective knowledge base** — what was learned building each phase, captured inline, aggregated by tool. Keep those learnings fresh; future reworkers of a phase read them before touching anything.

---

## 0. The execution workflow — the rigorous loop, top-to-bottom

This is the canonical workflow every project follows. Each numbered step fires a specific named rule below — the rule is authoritative; this section is the **index** that names the right rule at the right step. Do not skim this; **the discipline at each step is non-negotiable** and the user will re-establish it if the agent slips.

**Code-quality bias (user directive 2026-04-28).** *"Please opt for the optimized version best-related to code-quality for future implementations."* When choosing between a quick path and a thorough path at any step, pick thorough. The 5-30 min Phase 0 audit prevents 2-8 hr of mis-scope; the 30 sec absorption-scan rerun prevents the 4th `_safe_float`; the 60 sec phase-end verification prevents the green-now-red-on-merge surprise. Speed is downstream of correctness.

```
SCAFFOLD
  └─ §1   Copy templates/PROJECT-TEMPLATE.md → §1-§11 sections in order.
  └─ §3a  Run the seed-first checklist (KB § GUIDES/seed-first-design.md). Six questions + per-product code-count litmus.
          Required for EVERY project, not just cross-product. Single-product projects whose answers point at "product-specific"
          still fill §3a (explicit confirmation). PROJECT.md without §3a = bug.

PRE-PHASE — Phase 0 audit + absorption scan (BEFORE any code lands)
  └─ §2.5 Phase 0 audit FIRST — read actual files / run actual commands. When findings invalidate §6, *expand loudly* — revise §6 to match reality, log in §11, continue. STOP only for hard-to-reverse / shared-system / security-class discoveries.
          Phase 0 takes 5-30 min; mis-scope discoveries it prevents take 2-8 hr.
  └─ ABSORPTION SCAN — run BEFORE writing new code, scoped to what the phase will touch (KB § 06-AGENTS.md § Absorption-search sextet):
          • `--scan-helpers`              always (function/class names recurring across products)
          • `--scan-service-lines`        when touching `app/services/` or `app/routers/`
          • `--scan-blocks`               when refactoring control-flow (try/except shapes)
          • `--scan-test-fixtures`        when touching `tests/`
          • `--scan-migrations`           when touching `migrations/*.sql`
          • `--scan-within-product`       when refactoring within one product
          New N≥2 hit on a name/shape this phase plans to introduce → decide formalize/refactor/accept BEFORE proceeding.
          Absorption work usually changes the §6 plan; expand loudly per Phase-0 expand-loudly rule.

EXECUTE — one phase at a time
  └─ §2.6 Active robustness review WHILE editing — eyes open: silent error swallows, stale TODOs, magic numbers,
          async races, mock-vs-real divergence, `any`/`unknown` leaks. Capture findings LIVE in the phase's
          **Improvements:** block (not deferred). Apply low-risk fixes inline; defer out-of-scope to follow-up
          projects (scaffold the folder immediately — broken pointers forbidden).
  └─ §2   Live tick — `- [ ]` → `- [x]` IMMEDIATELY when a sub-task completes; flip phase header to `⏳`/`✅`
          as state changes. Never batch.
  └─ MID-PHASE absorption-scan checkpoint — every 5-10 file edits, re-run the scan most relevant to what was
          touched. Did your edits create a new N=2 pattern? Triage live in the Improvements block; do NOT defer.
  └─ Self-check before claiming a phase done — §6 ↔ §11 consistency rule. Five-point check:
      (1) phase header ✅; (2) all sub-tasks `- [x]`; (3) **Improvements:** filled or `none identified.`;
      (4) §11 entry exists; (5) `improvements.md` regenerated. Missing any → not closed.

PHASE-END VERIFICATION CHECKLIST — runs at every phase boundary (NEW 2026-04-28)
  └─ 1. Tests green for the touched product:
          cd products/<X>/backend && pytest tests/<scope> -q                         (backend)
          cd products/<X>/frontend && npx vite build                                 (frontend, if touched)
  └─ 2. Keeper validate — score unchanged or improved:
          python mcp/noctusai/cli.py --validate
  └─ 3. RE-RUN ABSORPTION SCANS — did this phase introduce a new N=2 pattern?
          --scan-helpers + the scan(s) relevant to what was edited.
          New N=2+ → triage NOW (Improvements block + decision: formalize / refactor / accept-with-rationale).
  └─ 4. KB sync (if any KB doc was edited): bash scripts/verify-kb-sync.sh
  └─ 5. §6 ↔ §11 self-check passes (the five-point rule above).

CLOSE — at every phase end
  └─ Synthesize captured improvements → ONE bundled proposal per phase via `noctusai_file_proposal(...)`.
  └─ Apply each bundled improvement INLINE during the same session.
  └─ Delete the proposal file (apply-inline-then-delete protocol).
  └─ Run `python mcp/noctusai/cli.py --improvements <PROJECT.md path>` to regenerate `improvements.md`.
  └─ **Phase commit (NEW 2026-05-03).** Stage the phase's diff with explicit file paths and commit it locally
          with a phase-scoped subject (e.g. `feat(<area>): <project-slug> phase <N> — <one-line summary>`).
          DO NOT push. Per-phase commits keep the history bisectable and let the user review state before the
          project-close push. `git status` first; never `git add .` / `-A`.

PROJECT CLOSE — at the last phase

PROJECT-END VERIFICATION CHECKLIST — runs once before folder deletion (NEW 2026-04-28)
  └─ 1. Cross-product frontend builds — green for every touched product:
          python mcp/noctusai/cli.py --build --changed                              (parallel; --changed scopes to git-changed products only)
  └─ 2. Backend pytest — green for every touched product:
          cd products/<X>/backend && pytest                                          (per touched product)
  └─ 3. MCP toolkit tests — green:
          mcp/noctusai/.venv/bin/python -m pytest mcp/noctusai/tests/ -q
  └─ 4. Keeper full validate — score 100/100, zero new critical/high:
          python mcp/noctusai/cli.py --validate
  └─ 5. KB sync — both verifiers clean:
          bash scripts/verify-kb-sync.sh
          python mcp/noctusai/cli.py --check-three-way-sync
  └─ 6. FINAL ABSORPTION SCAN sweep — capture what was absorbed vs what's deferred. Document in §11 close
          entry. Any new N=2+ patterns surfaced by THIS project's edits get a triage decision (formalize /
          refactor / accept-with-rationale) recorded in the close entry — not silently shipped.
  └─ 7. Three-way sync: KB depth + CLAUDE.md pointer + memory entry — all in the same session.
  └─ 8. End-of-work summary in the user-facing reply: applied items + deferred destinations + verification line.

CLOSE PROJECT (only after the verification checklist is fully green)
  └─ Folder deletion — clean-folder rule. Empty `proposals/` ok (delete with the project).
  └─ **Final commit + push (NEW 2026-05-03).** Stage everything still uncommitted (per-phase commits already
          captured each phase; the close commit captures the methodology amendments + folder deletion + any
          end-of-project polish). Subject: `feat(<area>): close <project-slug> — <one-line outcome>`. Then
          `git push`. Pushing is the literal last step of the project — it makes the work visible to other
          agents and pinned in remote history. Never push partway through; never push without an explicit
          project-close gate. If the user explicitly delegated the close (e.g. "commit and push the project"),
          this step runs without a re-confirmation prompt; absent that delegation, ask before pushing.
```

**Cross-cutting language trigger that fires at every step.** If you see or write any of these phrasings — in your own response, in the project doc, in a user prompt — STOP and challenge the framing: *"per-product X"*, *"mount across N products"*, *"for each product Y"*, *"mount on each ___"*. The right per-product code count for cross-product concerns is **zero**. See the language-trigger rule (§ The replication-to-seed symmetry rule).

**No-shortcut rules in scope of every project:**
- No monkey-patching of our own symbols (production OR tests). Use real APIs / dependency injection / row-seeding.
- No silent errors — every failure mode surfaces loudly.
- No replication framing — the seed is every product's skeleton.
- Three-way doc sync — KB + CLAUDE.md + memory move together.

**Anti-patterns the agent has slipped on (caught + documented audit trail in this file):**
- Closing a phase without ticking §6 checkboxes (§ Self-check before claiming a phase is done).
- Documenting a slip pattern as a "variant" instead of removing it (§ The replication-to-seed symmetry rule, instance #2).
- Walking through products one-by-one instead of absorbing into seed (§ The replication-to-seed symmetry rule, instances #1, #3, #4).
- Closing phase ✅ with `**Improvements:** none identified.` after a non-trivial multi-file phase (§ 2.6 Active robustness review).

This workflow is not optional. The named rules are not optional. Future agents are expected to operate this loop end-to-end.

---

## 1. Plan file anatomy

Every project document is created by copying `templates/PROJECT-TEMPLATE.md` — **do not re-invent the shape**. The template has 11 sections; keep them in order. Two mechanical features make projects machine-readable:

1. **Phase header checkboxes** — `### Phase N - [ ] Title`
2. **Improvements blocks** — appended inside each completed phase

Both are consumed by the `noctusai_improvements` tool to generate the retrospective.

### Where projects live — scope-scoped, not centralized

Projects live next to the code they touch. There are **two valid locations** and every slug is globally unique across them:

| Location | Use when | Examples |
|---|---|---|
| `projects/<slug>/` (repo root) | Project spans **multiple products**, touches the **seed/platform** itself, or migrates **something not yet a product** into the platform. | `adconnect-migration`, `repo-state-consolidation`, `strict-mode-migration` |
| `products/<product>/projects/<slug>/` | Project is scoped to **a single product** — including `products/core/` (auth, SSO, billing, orgs — the platform control plane, which is one product among many). | `products/personal-finance/projects/pf-org-scoping-migration`, `products/therapy-platform/projects/therapy-platform-wiring`, `products/erp-imobiliario/projects/vista-crm-wiring` |

**Every product has its own `projects/` folder**, including `products/core/` — even when empty. The folder signals "this is where single-scope project documents live" and is created the same moment a product is scaffolded. Empty folders are pinned with `.gitkeep` so git tracks the convention across the whole repo.

**Why scope-scoped?** An agent working inside `products/therapy-platform/` should discover the product's own projects without sifting through unrelated work from other products. Scoping projects to their parent folder makes the repo feel organized from any entry point and caps the per-product cognitive load. Root `projects/` stays reserved for the cross-cutting work that genuinely does not belong to one product.

**Why core is under `products/`:** core is structurally a peer to the other products — it has the same shape (`backend/` + `frontend/` + `MASTER-PROMPT.md` + `README.md`), imports from `seed/` the same way, and deploys independently. It is *also* the runtime entry point (users authenticate through core before entering any other product), but that's a user-journey relationship, not a code-structure one. Putting core under `products/` makes the code hierarchy honest: one product among many, importing from a shared `seed/`.

**Mechanical invariants** (enforced by the MCP tool — `mcp/noctusai/tools/proposals.py::_find_project_dir`):

- Slugs are **unique across both locations**. `therapy-platform-wiring` lives under `products/therapy-platform/projects/`, nowhere else. The resolver walks both locations and returns the single match.
- When a new slug is passed to `noctusai_file_proposal(project="<slug>")` and no folder yet exists in either location, the proposal lands at `projects/<slug>/proposals/` (root-default). If the project is product-scoped, **create the folder under `products/<product>/projects/<slug>/` first**, then file — the resolver will route correctly.
- A project folder contains exactly: `PROJECT.md`, `improvements.md` (generated), `proposals/` (grows as phases complete).

**Scope migrations:** a project that grows or shrinks in scope moves folders via `git mv`. Update every reference to the old path — the pre-commit `verify-kb-sync.sh` hook catches dangling KB pointers but not stale prose.

Each project folder contains exactly:

```
<project-root>/<slug>/
├── PROJECT.md        # the living document, written from templates/PROJECT-TEMPLATE.md
├── improvements.md   # auto-regenerated by `noctusai_improvements` after every phase tick
└── proposals/        # one bundled proposal per completed phase
```

### Phase status icon

Every phase header ends with a status icon (or none, for pending). The convention originated with the `erp-metas` project (shipped 2026-04, folder deleted per clean-folder rule); recent reference adopters include `consent-guard-rollout` and `consent-ui-rollout` (both shipped 2026-04-28). Sub-tasks still use `- [ ]` / `- [x]`.

| Icon | Meaning |
|---|---|
| _(none)_ | Pending — not started |
| ⏳ | In progress or partially complete (some sub-tasks deferred/blocked) |
| ✅ | Complete — every sub-task is ticked |
| ❌ | Blocked or failed — explain in Change Log + Open questions |

```markdown
### Phase 1 — Foundation: protocol + config + models

- [ ] create module X
- [ ] create module Y
- [ ] write tests
```

Once every sub-task is ticked, the header becomes:

```markdown
### Phase 1 — Foundation: protocol + config + models ✅
```

If a phase has real work done but is blocked on a sub-task, use `⏳` with a parenthetical:

```markdown
### Phase 2 — Teams & membership ⏳ (UI deferred pending UX confirmation)
```

Flip to `✅` **only when every sub-task is ticked.** The icon is the at-a-glance truth signal — don't lie.

### Improvements block

Immediately after ticking a phase header, append this *inside* that phase section:

```markdown
### Phase 1 — Foundation ✅

- [x] create module X
- [x] create module Y
- [x] write tests

**Improvements:**
- The X cache is a flat dict — switch to LRU when Y grows past 100 entries.
- Missing coverage: no test for the "provider swapped mid-request" edge case.
- We silently swallow Supabase errors on Tier 1/2 — log at WARN on next rework.
- `_reset_for_testing` is publicly exposed; move to a `testing/` submodule.
```

**What goes in:**
- Refactor candidates you saw but didn't take
- Edge cases discovered but not covered
- Tech debt deliberately taken on (with rationale)
- Performance / memory concerns
- Shortcuts the implementation made
- Missing tests / coverage gaps
- Specific observations about the code you just wrote

**What stays out:**
- Tasks for future phases — they're already in §6 of the project
- Generic "do more tests" — only specific, actionable observations
- Narration / praise ("this went well")

If you genuinely found nothing worth flagging: `**Improvements:** none identified.` That distinguishes "considered, none found" from "forgot to write".

The block is about the *just-completed phase's own implementation*. It is **not** a preview of what the next phase does. Upcoming work lives in §6 of the project itself.

---

## 2. Live ticking — tasks and headers

**Tick the moment a task is done. Save the file. Don't batch.**

The user treats the project as a live artifact. A phase that appears half-done in the file when it's really 90% done breaks the contract.

Workflow:

1. Finish a sub-task → flip `- [ ]` → `- [x]` on that line → save.
2. All sub-tasks in a phase are ticked → flip the phase header `- [ ]` → `- [x]` → save.
3. **Immediately** append the `**Improvements:**` block capturing what you learned → save.
4. **Immediately** run `noctusai_improvements` (see §4).
5. Log the phase completion in §11 Change Log → save.
6. Pause. Wait for the user's instruction to advance.

No step in this workflow is optional.

### Self-check before claiming a phase is done — the §6 ↔ §11 consistency rule (2026-04-27)

**Observed slip pattern (recurring):** writing rich §11 Change-Log entries that say "Phase N ✅ shipped" while §6 still shows `- [ ]` checkboxes and a header without the `✅` icon. The §11 narrative is rich; §6 is the live state. Mismatch lies to the user's dashboard.

**Mandatory self-check before any reply that claims a phase is closed:**

1. **§6 phase header** — does it carry the `✅` icon? (Or `⏳` if partial; never blank-after-shipped.)
2. **§6 sub-tasks** — are all `- [ ]` flipped to `- [x]`? (Verify ALL of them — a single un-ticked checkbox lies.)
3. **§6 `**Improvements:**` block** — is it filled in (or `none identified.`)? Empty placeholder text means the synthesis step was skipped.
4. **§11 entry** — does it exist + name what shipped + what verification ran?
5. **`improvements.md` regenerated** — did `noctusai_improvements` run after the tick?

**If ANY of 1-5 is missing, the phase is NOT closed — fix the live state first, then claim done.**

**Anti-pattern (the slip):** "I'll update §11 first because that's where the rich narrative lives, then I'll come back and flip the checkboxes" — and forgetting the second half. **Do it in order: tick first, narrate second.** The narrative is allowed to be terser than the live state; the live state is NEVER allowed to lag the narrative.

**Enforcement (live since 2026-04-28):**
- `check_phase_state_consistency` ships in `mcp/noctusai/tools/compliance.py` — walks every `PROJECT.md` across `projects/`, `products/*/projects/`, `core/projects/`. Flags four drift classes: (1) §11 says shipped but §6 header lacks `✅`, (2) header has `✅` but sub-tasks remain `- [ ]`, (3) header has `✅` but no `**Improvements:**` block, (4) §11 says shipped but §6 has both unflipped header AND unticked sub-tasks (the dashboard-lying case). Severity `high`. `⏳`/`❌`/`🅿️` icons recognized as legitimate non-shipped states; not flagged.
- Wired into `check_all_products()` so every `python mcp/noctusai/cli.py --validate` run picks it up automatically.
- Exposed as `python mcp/noctusai/cli.py --check-phase-state` for direct invocation; exits `1` on any high-severity issue.
- Pre-commit hook `scripts/pre-commit § 5` runs the detector ONLY when `**/PROJECT.md` is in the staged set (perf — zero overhead on commits that don't touch project docs). Blocks the commit on drift.
- Inaugural catch (2026-04-28): `repo-state-consolidation` Phase 0 was flipped to `✅` but lacked the `**Improvements:**` block. Caught by the detector on its own first run; fixed inline. Validates the four-trigger detection design.
- Shipped by the `keeper-phase-state-consistency-detector` project (closed + folder deleted per clean-folder rule). `mcp/noctusai/tests/test_compliance.py::TestPhaseStateConsistency` covers all four detection rules + happy paths + edge cases (`⏳`/`❌`/`🅿️` icons, bare phase mentions in §11, product-scoped projects).
- Until the detector ships, this rule is enforced by reader (user) audit + agent self-discipline. The slip pattern observed 2026-04-27 (multiple times in one session) is the trigger for formalizing the detector.

### Audit trail of the slip pattern (so future agents recognize it)

Caught instances 2026-04-27:
- `consent-guard-rollout` Phase 0 + Phase 1 — §11 entries claimed shipped, §6 still showed `- [ ]` everywhere. User: *"did you skip phase 1, or did you not tick checkboxes?"*
- Multiple earlier phases in the session followed the same pattern.

The slip is mechanical, not conceptual — the agent KNOWS the rule. The fix is the self-check above.

---

### The replication-to-seed symmetry rule — fires at LANGUAGE time, not action time (2026-04-28)

**The slip is recursive.** Caught 4× in 24 hours including ONE inside the very reply that documented the rule the first 3 times. Lesson learned: the rule scoped to "before edit #2" fires too late. By the time you're about to write edit #2, you've already mentally accepted the per-product framing. The rule has to fire at READ/PLAN/DESCRIBE time — when you first encounter the framing, in any context.

**The trigger is LANGUAGE.** The moment any of these phrasings appears — in your own response, in a project doc you're reading (even one written by another agent), in a user prompt, in a Phase plan — STOP and challenge it:

- "per-product X"
- "mount across N products"
- "for each product Y"
- "per-product mount table"
- "mount on each settings page" / "mount on each layout"
- "every product gets its own ___"
- any phrasing that implies the same thing happens N times

**These phrasings ARE the slip.** They describe a design that's wrong, even when the design is enshrined in an existing `PROJECT.md`. The right move on encountering replication framing in a doc you're reading: **challenge it in Phase 0**, do not parrot it back, do not propose phases that walk through products. The rule that matters: *if every product needs the identical thing, it lives ONCE in seed, products consume it via a kwarg or auto-on convention.*

**Where "once in seed" lives:**
- Backend cross-cutting infra → `seed/backend/framework/noctusai_seed/` (factories, app construction)
- Backend reusable code → `seed/backend/lib/noctusai_lib/` (helpers, factories, dependencies)
- Frontend components/pages/layouts → `seed/frontend/lib/src/design-system/` + `seed/frontend/framework/createProductApp(...)`
- Test scaffolding → `seed/backend/lib/noctusai_lib/testing/` (including `pytest11` entry-point plugins)
- Scaffold templates → `templates/product-seed/`

**The right per-product code count for a cross-product concern is ZERO.** Products opt in via:
- A kwarg in `create_product_app(...)` / `createProductApp(...)`
- Auto-on by convention (e.g. `consent_features=...` triggers consent-related backend AND frontend behavior; product writes nothing)
- A scaffold-template inheritance that's invisible at runtime

**If the right count isn't zero, prove it.** Legitimate per-product code: domain logic, routes, business rules, content. Anything else (settings page hosting a uniform component, layout slot mount, route registration, fixture line, kwarg flag, scaffold line) → seed.

**Mandatory self-check (at edit-time, kept as the secondary trigger):**

When you are about to make the same change to a SECOND product in a single session — the same line, the same kwarg, the same import, the same fixture, the same conftest helper, the same router registration, the same component mount — STOP and answer:

1. **Is this row in the framework or in the products?** If the change is mechanical-inheritance shape (every product needs it identically), the answer is the framework.
2. **Did I JUST land a sibling change at the framework level in this session?** If yes, I'm about to do the symmetric absorption the wrong way. Land it in the framework too.
3. **Is the per-product change pure scaffolding (a conftest line, a kwarg flag, an import, a setup fixture)?** Pure scaffolding for a cross-product concern almost always belongs in seed. Only product-specific *content* (domain routers, business logic) stays per-product.
4. **What's the seed-side mechanism that would absorb this?** Pytest entry-point plugins, `create_*_app` kwargs, factory functions in `noctusai_lib`, helper imports, scaffold templates. If the answer is "no clean mechanism," sometimes per-product is correct — but bias is "absorb until proven otherwise."

**The rule:** *if you're typing the same boilerplate into product #2, you're typing it into the wrong layer.*

**Anti-pattern (the slip):** "I'll add this one line to each conftest — it's just test scaffolding." It is NOT just test scaffolding when N products need the identical line. That's the seed-absorption signal firing in real time. The same N-fold-edit shape applies to: production code (caught by `Audit seed completeness proactively`), test scaffolding (this rule), config files (vitest absorption 2026-04-27), KB documentation patterns (caught when `monkeypatch` was about to be documented as a "Service-layer variant").

### Audit trail of the slip pattern (so future agents recognize it)

Caught instances 2026-04-27 → 2026-04-28 (4× in two days):

- **Vitest config replication (2026-04-27).** Almost stamped `vitest.config.ts` into 7 products; user: *"shouldn't this be seed-scoped? Is it being replicated or propagated?"* → absorbed into `seed/frontend/framework/vitest.config.factory.ts`.
- **Monkeypatch as a documented pattern (2026-04-27).** Almost wrote a "Service-layer variant" subsection in KB testing.md showing `monkeypatch.setattr(ai_pipeline, "require", _noop)` as how-to; user: *"NO MONKEYPATCHING. Fix all monkey-patch bullshit you've done"* → row-seeding pattern + `inserted_payloads` capture absorbed into seed-lib mock.
- **Conftest test-bootstrap line replication (2026-04-28).** Almost added `from app.main import app as _app` to 6 product conftests; user: *"this sounded like a seed-level issue, aint it?"* → absorbed into `noctusai_lib/testing/pytest_plugin.py` registered via `pytest11` entry point in seed-lib's `pyproject.toml`.
- **`consent-ui-rollout` mount-per-product framing (2026-04-28, INSIDE the reply that documented the first 3).** Described the next step as `<AIConsentToggles/>` + `<PendingConsentBadge/>` + `LayoutEnrichment.aiBadge` "mount across 6 products," parroting the existing `consent-ui-rollout/PROJECT.md` Phase 2/3 framing. User: *"This also looks like a seedable feature. Are we joking here?"* The whole UI is seedable — components, settings page hosting them, route, layout mount — products write zero consent-UI code. Lesson: the rule scoped to "before edit #2" fires too late; by then the per-product framing is already accepted. **The rule has to fire at LANGUAGE time** — the moment any "per-product"/"mount across N"/"for each product" phrasing appears. → `consent-ui-rollout/PROJECT.md` to be reframed Phase 0.

**Common shape of all 4 slips:** the agent had the seed-vs-replication frame for *something* in scope (a related change just landed; an existing rule was salient) but lost it when shifting to a symmetric sub-task — or, in case #4, when *describing* the sub-task. The slip is at the SHIFT moment (action #1 → action #2; or seed-frame → replication-frame in the same response). Self-check fires the moment you encounter ANY language implying replication, not just the moment you're about to open product #2's file.

**Why the at-edit-time check failed for case #4:** action #1 was "document the rule." Action #2 was "describe the next step." The shift happened mid-reply, the language was generated unconsciously, and "before edit #2" didn't trigger because no edit was happening yet. The fix is the LANGUAGE trigger added above.

**Difference vs. `Audit seed completeness proactively`** (existing memory rule): that rule is *retroactive* (sweep the codebase periodically and absorb duplicates you find). This rule is *proactive* (catch it at edit-time, before the duplication exists). Both rules cite the same principle — DRY across products → seed — but the trigger windows are different.

---

## 2.5 Phase 0 audits — the highest-leverage work in any project (2026-04-27)

Every project's **first phase is an audit** — read the actual files, run the actual commands, query the actual DB — before any code lands. Phase 0 frequently surfaces that the project itself is mis-scoped: too small (real scope is bigger), too large (real scope is smaller), or wrong direction.

**Rule (updated 2026-04-28 — *expand loudly*, don't stop).** When Phase 0 invalidates the §6 phase plan, **expand loudly** — revise the plan to match reality, surface every change explicitly, log it in §11, then continue execution. Do NOT silently absorb the discovery (that hides the drift); do NOT halt indefinitely waiting for re-approval (that gates progress on small re-scoping moments).

User directive 2026-04-28, verbatim:

> *"Let's change this rule [...] to expand loudly. self-improve, then let me know what you did."*

What "expand loudly" means in practice:

1. **Surface the audit findings explicitly** in §11 Change Log + at the top of the affected phase block. Quote the divergence (expected vs. actual file counts, missing dependencies, scope creep, etc.).
2. **Revise the §6 phase plan in the same session** — add tasks for the new scope, drop tasks for the no-longer-needed scope, renumber phases if needed. Keep the document the source of truth.
3. **Note the expand-loudly event in §11** — "Phase 0 audit found X; §6 expanded to absorb Y; original plan superseded by revision Z." Future readers see the trail.
4. **Continue executing** the revised plan unless the discovery is a hard-stop class (see "When stopping IS still required" below).

**When stopping IS still required (regardless of expand-loudly):**

- The discovery affects shared systems beyond the local repo (production deploys, shared databases, public APIs) — confirm with user before proceeding.
- The discovery reveals a security / LGPD concern that needs design discussion (e.g. "we'd be persisting un-anonymized clinical data") — STOP, surface, design with user.
- The discovery is hard-to-reverse + multi-agent-shared (force pushes, branch deletions, prod migrations, force-merging upstream) — STOP, confirm.
- The user explicitly asked to be confirmed before scope changes — honor that gate.

For everything else (small re-scopes, new tasks, dropped tasks, renumbered phases, expanded commit plans, etc.) → expand loudly + continue.

Per `01-PHILOSOPHY.md § Estimate off evidence` — the option list itself was the defect; the audit is the answer; the plan now matches the answer.

**Worked example (2026-04-28, this very rule's inaugural use):** `repo-state-consolidation` Phase 0 audit found the working tree had drifted from ~430 entries (drafted 2026-04-27) to 470 entries (today's session added ~40 new files + modifications). Under the old "STOP and re-scope" rule the agent reported and waited. Under the new "expand loudly" rule, the agent revises §5/§6 to allocate today's files into the right commits, logs the audit findings in §11, then continues — UNLESS the action is hard-to-reverse (here, the final `git push origin main` IS hard-to-reverse, so confirm before that one step; intermediate commits expand loudly without a gate).

**What a good Phase 0 looks like:**
- Read the actual files the project would touch (not the docs, not the file names).
- Run the actual commands the project would run (test suites, build commands, DB queries via Supabase MCP).
- Surface findings explicitly in §11 Change Log — even if (especially if) they invalidate a §6 phase.

**Worked examples (2026-04-27):**
- **`frontend-test-harness` Phase 0** caught that ERP's "configured" vitest was actually red for 9 of 10 files. Rescoped the canonicalization step from "copy ERP's config" to "fix ERP first then copy" — saved propagating broken config to 6 products.
- **`pf-schema-drift-reconciliation` Phase 0** caught that the project's "small reconciliation" assumption was wrong: live DB and migration 001 disagreed on the entire scope model (~13 tables, structural divergence). Project parked + rescoped as `pf-org-scoping-migration` (multi-day product evolution).

**Sized rule of thumb.** Phase 0 takes 5-30 minutes for a typical project. Mis-scope discoveries it prevents take 2-8 hours of wrong-direction work. The ratio is asymmetric enough that **no project should skip Phase 0** unless it's truly trivial (one-line fixes, doc-only changes).

**Anti-pattern: skipping Phase 0 in favor of "real work."** Some projects scope Phase 1 as the first "real" phase, with Phase 0 framed as preamble. This is exactly the trap. The audit IS real work — often the most valuable kind.

---

## 2.6 Active robustness review during execution — every phase doubles as an inspection pass (2026-04-28)

**The rule.** Phase execution is not "ram through the §6 sub-tasks until they all tick." It is *also* a proactive inspection pass on the code being touched, the surrounding code it integrates with, and the contract it implements. Every phase is supposed to surface improvements, fixes, and robustness gaps you find as you read the code — captured live in the phase's `**Improvements:**` block, not deferred to "later."

User directive (verbatim, 2026-04-28):

> *"i need you to be as strict and proactive as you were phase by phase finding improvement/fixing opportunities. This is meant to find code robustness along the implementation, rather than just ramming through tasks to finish your work earlier."*

**What this means in practice — your eyes are open, not closed, while editing:**

1. **Read with critical attention, not just for orientation.** When you open a file to make a change, read the surrounding code. Look for: silent error swallows (`except: pass`, `try { ... } catch { return null }`), TODO comments stale for months, hardcoded magic numbers that should be config, missing input validation at trust boundaries, race conditions in async chains, fields that are populated in one place and never read, error paths that drop information, mock-vs-real divergence in test scaffolding, untyped `any`/`unknown` that should be narrowed.
2. **Surface findings live, in the moment, into `**Improvements:**`.** Do not save them for a "later cleanup phase." Do not file them as separate projects unless they clearly need scope. The right grain is: one bullet per finding, in-the-act phrasing ("noticed X — would benefit from Y because Z"), filed during the phase that's looking at the code.
3. **Apply when fitting in scope; defer with destination otherwise.** If the fix is one line and obviously safe, apply inline (per the apply-inline-then-delete rule). If it needs a separate project, file the project from `templates/PROJECT-TEMPLATE.md` immediately and link from the improvement bullet — prose references to nonexistent projects are broken pointers (per the clean-folder + apply-inline-then-delete rules).
4. **At phase close, synthesize.** The bundled phase proposal includes the captured improvements as independently-executable items (per `Project phases produce ONE proposal per phase`). Don't filter the captures aggressively at synthesis — every concrete bullet earns a line in the proposal.

**Anti-pattern: rushing to close.** Symptoms: phase header flips to ✅ with `**Improvements:** none identified.` after a non-trivial phase touched many files. That outcome is rare in practice — non-trivial code changes almost always surface SOMETHING worth noting. An empty improvements block after a non-trivial phase is a signal that the inspection pass was skipped, not that the code was perfect.

**Counter-pattern (also wrong): scope creep.** The active-review rule is NOT permission to refactor adjacent code, rewrite unrelated modules, or expand the phase's scope mid-flight. The rule is to **notice** broadly and **act** narrowly: capture in `**Improvements:**`, apply in-scope ones inline, defer out-of-scope ones to follow-up projects with a real folder + a real link.

**Sized expectations.** A typical implementation phase that touches 3-10 files should produce 1-5 improvement bullets. Less than 1 = inspection pass was skipped. More than 5-7 = scope creep risk; promote half of them to a dedicated cleanup project.

**Reference cadence (the right shape):**
- Open file → read context.
- Make the in-scope edit.
- BEFORE saving, scan the surrounding 50 lines for robustness gaps.
- Note any found in `**Improvements:**` immediately.
- Move to the next file.
- At phase close, synthesize the captured bullets into the bundled proposal.
- Apply low-risk improvements inline, file deferrals as project folders, delete the proposal.

This rule is the active-execution companion to Phase 0 audits. Phase 0 reads BEFORE any code lands; this rule reads WHILE code lands. Both fire in the same project. Both produce findings that change the work.

---

## 2.7 The recurrence rule — formalize the pattern at N instances (2026-04-28)

The active-robustness-review rule (§2.6) catches improvements while editing. The replication-to-seed-symmetry rule catches duplication at language time (before edit #2). The **recurrence rule** is the third pattern-detection trigger, fired at OBSERVATION time when an agent notices that the same pattern / boilerplate / code shape ALREADY exists in N independent places.

User directive (verbatim, 2026-04-28):

> *"can we implement this recurrence rule? i got what you meant and it was exactly what i was expecting and was trying to build on that seed-feature"*

The thresholds are not negotiable:

| N instances | Outcome (mandatory) |
|---|---|
| **N = 2** | **TRIAGE TIME.** Explicit decision per `01-PHILOSOPHY.md § Triage at decision time`: formalize / refactor / accept-with-rationale. "Coincidence" is the only legitimate `accept` outcome at this threshold. The decision is recorded — silently moving on is forbidden. |
| **N = 3+** | **MUST FORMALIZE.** The pattern lives in seed-lib / seed-framework / a shared library. The minimum acceptable response is filing a follow-up project from `templates/PROJECT-TEMPLATE.md` for the extraction. Silently shipping the 4th instance is forbidden. |

**When the rule fires (every check should run all three):**

- **Phase 0 audit** — when reading the actual files: *"is this pattern already in seed under a different name? does it appear in N+ products?"*
- **Active robustness review (§2.6)** — when editing: *"does my edit echo something elsewhere? did I just write boilerplate that exists somewhere I forgot?"*
- **KB pass / proposal synthesis** — when writing or revising a doc: *"is this section becoming a catch-all? is this rule mentioned in N other places already?"*
- **Cross-product code audits** — when running `grep -r` / spot-checking across products: *"how many places match this pattern?"*

**Action when triggered (in order):**

1. STOP the foreground task. Don't keep typing.
2. **Name the pattern** explicitly. Pull together what's the same vs. what differs across instances. Phrase it as a concrete extraction (e.g. "every product reads `org_id` from `user_metadata` then resolves admin via `resolveSSORoles` — extract `useCurrentOrgContext` hook").
3. **Decide the destination.** Where in seed does it live? `seed/backend/lib/noctusai_lib/`, `seed/frontend/lib/src/`, `seed/backend/framework/noctusai_seed/`, `seed/frontend/framework/src/`, `templates/PROJECT-TEMPLATE.md` (for repeated project structure), `pytest11` entry-point plugin (for test bootstrap), etc.
4. **File the project** (or apply inline if low-risk and in-scope): scaffold from `templates/PROJECT-TEMPLATE.md` with §3a confirming it's truly seed-bound. Folder must exist; broken pointers (prose references to nonexistent projects) are forbidden.
5. **Resume the foreground task** — but the slip is now captured as a real follow-up, not an offhand "Not yet" note.

**Anti-patterns:**

- *"Not yet — the recurrence rule hasn't tripped"* without naming a threshold or logging a trip-counter for the pattern. Vague — it lets future drift accumulate undetected.
- *"We can extract this if it surfaces again"* without filing the trigger condition. The next agent has to re-discover the recurrence from scratch.
- Silent shipping of the Nth instance because "it's just one more line." Lines compound.

**Audit trail of formalizations driven by this rule (this session, 2026-04-27 → 2026-04-28):**

- **Vitest config** caught at 7 instances → `createProductVitestConfig` factory in `seed/frontend/framework/`.
- **Conftest bind-consent-mock helper** caught at 3 instances (mailing, ERP, daily-life) → `bind_consent_module_to_mock` in `seed/backend/lib/noctusai_lib/testing/consent.py`.
- **`from app.services import ai_consent_features  # noqa: F401`** in main.py — caught at 6 product instances → `consent_features=` kwarg in `create_product_app(...)` (backend framework).
- **`from app.main import app as _app`** in conftest.py — almost stamped into 6 conftests → `pytest11` entry-point plugin auto-registered via seed-lib's `pyproject.toml`.
- **Per-product Settings page mounts for consent UI** — would have been 6 mounts → seed-mounted `/settings/ai` route + framework default `aiBadge` fill.
- **Per-product Spend Badge mounts** — would have been 6+1 mounts → `DEFAULT_AI_BADGES = [<PendingConsentBadge/>, <LLMSpendBadge/>]` exported from `seed/frontend/framework/src/layout.tsx`; products that need product-specific badges spread `DEFAULT_AI_BADGES` (legitimate per-product touch — Daily Life is the sole adopter).

**Companion rules (sister triggers in the same family):**

- `Audit seed completeness proactively` (memory rule) — the retroactive sweep counterpart; runs periodically across the codebase looking for duplication that pre-existed without being caught.
- `Replication-to-seed symmetry` (§ 2 above) — the at-language-time trigger; fires when about to write the duplication.
- `Triage at decision time` — the decision framework (`01-PHILOSOPHY.md`).

The three triggers + this rule form a complete fence around the DRY-into-seed concern: language-time, observation-time (this rule), execution-time (active review), retroactive-time (audit completeness).

---

## 2.8 Multi-phase rule shipments — forward-stub + bullet-weight discipline (2026-05-02)

When a project ships a *new behavioral rule* (or a small family of related rules) across multiple phases — Phase 1 lands rule A, Phase 2 lands rule B in the same KB anchor — two practices keep the work clean and the auto-load surface lean.

### The forward-stub pattern

When Phase 1 authors a KB anchor that Phase 2 will extend, **leave a labeled placeholder section in the anchor for the future content**. Phase 2's three-way sync becomes a single edit (extend the stub) instead of authoring a separate file.

Worked example: `methodology-extraction` Phase 1 created `KNOWLEDGE-BASE/CONTEXT/PATTERNS/agent-reading-discipline.md` with a populated `## Narrow-read first` section and a stub `## Explore-agent delegation` section pointing forward to Phase 2. Phase 2 replaced the stub body with the full rule — INDEX.md was already pointing at the file, no new entry required, three-way sync cost halved.

### CLAUDE.md §1 bullet-weight discipline

CLAUDE.md is loaded every turn — every bullet costs per-turn tokens. When adding a new rule bullet, the soft target is **≤80 words**; **>100 words → consider trimming** (move long-form content to the KB anchor and shorten the bullet to rule + key why + pointer). When a project legitimately needs to add 3+ bullets of similar length, that's the **recurrence rule firing on §1 itself** — triage time:

- **Formalize**: extract the bullets into a single dedicated KB pattern with one §1 pointer.
- **Refactor**: condense / merge / cite shared pointers across the bullets.
- **Accept-with-rationale**: rule needs the load-bearing nuance to be in CLAUDE.md per-turn (rare).

Default reading: 3+ heavy bullets = formalize unless rationale says otherwise.

#### Auto-loaded vs. topical CLAUDE/<topic>.md (added 2026-05-03 by `context-budget-overhaul`)

The ≤80-word soft cap applies to **CLAUDE.md §1 bullets only** — those are auto-loaded every turn. Topical `CLAUDE/<topic>.md` files (e.g. `CLAUDE/backend.md`, `CLAUDE/projects.md`) are **siblings of CLAUDE.md, NOT auto-loaded**: they're read on-demand by the agent when starting work on the matching topic, per the §3 "When to read what" routing table in CLAUDE.md. Because they're not paid every turn, their per-bullet word budget is intentionally relaxed (50-100 words is fine; the platform-rules bullets in `CLAUDE/projects.md` average ~115 words and that's correct). The discipline that **does** apply to topical files: each rule still ends with a KB pointer; the rule body is rule + why + how-to-apply + pointer, never expanded into deep examples (those live in KB).

Full layered model: see `KB § 01-PHILOSOPHY.md § Context budget discipline § The three layers`.

### Measurement discipline

Use `noctusai_count_tokens` (the offline MCP tool) to measure CLAUDE.md / KB / project-doc sizes during phase work. Eyeballing word counts with `wc` produces approximate numbers that miss tokenizer-aware drift; the dedicated tool reports the same number Phase 5's measurement will use, so phase-block metrics across a project's history stay comparable.

> **2026-05-03 status:** the `noctusai_count_tokens` MCP tool referenced above does not yet exist; cataloged as accept-with-rationale at `KB § PATTERNS/accept-with-rationale.md § noctusai_count_tokens MCP tool referenced by KB § 2.8 does not yet exist`. Until shipped (deferred to `projects/mcp-server-expansion/`), measurement falls back to `wc -w` — sufficient for directional-reduction signals (50%+) but not for tokenizer-aware comparison across history.

---

## 3. Phase-by-phase cadence

Default cadence: **execute exactly one phase, then stop.** Wait for the user to say "continue" / "next phase" / "do phase N" before advancing.

The user overrides with explicit throughput instructions:

- "ram through phases 1-3"
- "run all backend phases"
- "do phases 2 and 4" (skipping 3)

Absent an override, stop after one phase — even if the next phase looks trivial. The cost of a false auto-advance (shipping something the user didn't authorize) beats the cost of one extra round trip.

---

## 4. The `noctusai_improvements` tool

Full reference in `mcp/noctusai/README.md`. Short version:

- **What it does**: reads a project file; extracts each completed phase's `**Improvements:**` block, the list of completed phases missing a block, items from §4 Out of scope, and open questions from §7; writes `improvements.md` in the project's folder.
- **What it does NOT do**: preview future phases. Those stay in §6 of the project.
- **When to call**: every time a phase header flips from `- [ ]` to `- [x]`.
- **How to call**:
  - CLI: `python mcp/noctusai/cli.py --improvements <project>.md`
  - MCP: `noctusai_improvements(project_path="<project>.md")`
- **Output**: overwrites `<project-folder>/improvements.md`. Idempotent — safe to re-run.

Not calling it after a phase tick is a rule violation. Without regeneration, the retrospective file goes stale and the next iteration of a phase starts blind.

### Why a retrospective file at all?

A project describes *what the agent is going to build*. The implementation always teaches the agent things the project didn't anticipate — gotchas, nicer designs seen after the fact, tests that would have helped catch a subtle bug. Those learnings vanish the moment the session ends unless they're captured in the project file itself.

`improvements.md` is the aggregated view. When the phase comes back for rework, a refactor, or a v2, the person picking it up (which may well be another agent) reads the improvements first — the friction and discoveries of the original build, laid out per phase. That's the feedback loop.

---

## 5. Project revision (scope changes mid-flight)

Projects are living documents. If you learn something that invalidates the original structure — a phase collapses into half the tasks, two phases merge, a new phase appears — **rewrite the project, don't force-fit the new reality into the old shape.**

When you revise:

1. Rewrite the affected phases in §6.
2. Update §7 Open questions if the revision answered (or raised) any.
3. Log the revision in §11 Change Log with a one-line reason.
4. Run `noctusai_improvements` to regenerate the retrospective (it tracks the new shape automatically).
5. Tell the user **before** executing the revised project — don't silently rewrite and execute.

Do not:
- Delete phases (even completed ones). Strike through or move to the Change Log.
- Pad a project to hide that a phase was trivial. Shrink it.
- Add a new phase to §6 without a corresponding Change Log entry.

---

## 6. Change Log (§11) discipline

Every project revision and every phase completion gets a row:

```markdown
| 2026-04-18 | **Phase 1 complete.** Credentials module + LLM foundation shipped. 23/23 tests pass. | Claude |
| 2026-04-18 | Rewrote Phase 3 to reflect seed-injector model — products no longer wire LLM manually. | Claude |
```

Keep entries terse: what changed, in one sentence. The "why" for revisions goes in §2 Confirmed constraints (when a constraint flips) or the affected phase's Improvements block (when an in-flight learning shifts direction).

---

## 7. Common failure modes

- **Phase header ticked before all sub-tasks** — Don't. The state is a lie.
- **Tasks ticked in one batch at end of phase** — Don't. Live-tick means immediately.
- **Missing `**Improvements:**` on a completed phase** — The tool flags it. Back-fill.
- **Improvements block used to preview future phases** — Don't. Upcoming tasks live in §6. Improvements are about the just-completed phase's own implementation.
- **Forgetting to run `noctusai_improvements`** — The retrospective goes stale. Future reworkers start blind. Re-run immediately.
- **Auto-advancing to the next phase without user permission** — Stop. Wait.
- **Revising phases without a Change Log entry** — Future-you can't trace what happened. Always log.

---

## 8. Project slug naming convention

The project slug is the folder name (under `projects/<slug>/` **or** `products/<product>/projects/<slug>/` — see §1) and the value passed to `noctusai_file_proposal(project="<slug>", ...)`. **Pick the slug — and the location — before writing the project file.** Renaming churns proposal paths; moving folders mid-project requires finding every reference.

**Format:** `<subject>-<intent>` — two or three dash-separated tokens, lowercase, ASCII only.

- `<subject>` — the domain being worked on. For a single-product project: `<product-name>` (e.g. `therapy`, `erp`, `adconnect`, `seed`). For cross-cutting work: the capability or area (`llm`, `ai`, `strict-mode`).
- `<intent>` — what the project delivers. Pick from the vocabulary below; invent a new one only when none fits, and log the addition in the Change Log of the first project that uses it.

| Intent | Use when |
|---|---|
| `-migration` | Moving an existing system to a new shape (schema, framework, runtime). |
| `-expansion` | Adding new capability to an existing system. |
| `-wiring` | Closing end-to-end gaps where one layer is scaffolded and another is missing (frontend exists, backend doesn't; feature flag exists, implementation doesn't). |
| `-gap` | Narrower than `-wiring`: one or two concrete holes, not a sweep. |
| `-refactor` | Structural change with no new user-visible behavior. |
| `-hardening` | Security, RLS, LGPD, or robustness uplifts. |
| `-rollout` | Bringing an already-built feature to more products, tenants, or users. |
| `-consolidation` | Folding two or more implementations into one. |
| `-baseline` | Establishing a new minimum (test baseline, LGPD baseline, docs baseline). |

**Scope → location (see §1):**
- Single-product scope (including `products/core/`) → `products/<product>/projects/<slug>/`.
- Cross-product, seed/platform-infra, or not-yet-a-product migrations → `projects/<slug>/` (root).
- The slug itself does not encode location — the folder path does. But the subject of a single-product slug generally matches the product name, which makes location self-evident.

**Examples that exist in the repo:**
- `therapy-platform-wiring` — product + intent. Lives at `products/therapy-platform/projects/therapy-platform-wiring/`.
- `pf-org-scoping-migration` — product + intent. Lives at `products/personal-finance/projects/pf-org-scoping-migration/`.
- `vista-crm-wiring` — product + intent. Lives at `products/erp-imobiliario/projects/vista-crm-wiring/`.
- `adconnect-migration` — subject + intent (adconnect is not yet a product). Root `projects/adconnect-migration/`.
- `strict-mode-migration` — area + intent. All 5 frontends → root `projects/strict-mode-migration/`.
- `repo-state-consolidation` — subject + intent. Cross-product / platform-infra → root `projects/repo-state-consolidation/`.

**Examples shipped + folder deleted (closed audit history; cited as past adopters):**
- `erp-metas` (product-area) — shipped 2026-04; ERP metas service code at `products/erp-imobiliario/backend/app/services/metas_*.py`.
- `ai-expansion` (cross-product) — shipped 2026-04 (all 19 phases); the AI primitives + cross-cutting infra it built live in `seed/` + per-product AI services.
- `consent-guard-rollout` + `consent-ui-rollout` + `llm-spend-badge-mount` + `digest-ui-pages` (cross-product) — all shipped 2026-04-28.
- `core-seed-wiring`, `core-scheduler-for-retention`, `webhook-event-classification` (core-platform) — all shipped 2026-04.
- `keeper-config-inheritance-audit`, `keeper-frontend-config-paths-audit`, `seed-pydantic-v2-migration` (cross-product) — all shipped 2026-04-25; detector code at `mcp/noctusai/tools/compliance.py`.

**Rules of thumb:**
- **Descriptive over clever.** The slug is read by future agents skimming `projects/` and `products/*/projects/`; `therapy-platform-wiring` beats `therapy-v2`.
- **Scope-honest.** If the scope widens mid-project, revise the slug *only* at the project-design stage (before proposals are filed). Once proposals exist under `projects/<old-slug>/proposals/`, rename requires moving the folder and updating every proposal's `Origin:` header — not worth it.
- **No dates in the slug.** Dates belong in the Change Log and the proposal filenames (which the MCP tool already timestamps).
- **No agent names** (`claude-...`, `opus-...`) — proposal filenames carry the author; the project slug is about the work, not the worker.

---

## 9. Tests land with the implementation

The "three-layer discipline" in `KNOWLEDGE-BASE/CONTEXT/PATTERNS/testing.md` is the default for every phase — **not a project-level choice.** When a phase writes a new router, a new service function, or a new migration, the same phase writes the router tests, service unit tests, and any integration paths required. Skipping tests to "backfill later" violates the methodology; a phase that shipped without its tests is not `✅`, it's `⏳ (tests deferred)`.

Agents shouldn't need to ask about test coverage in the interrogation phase — assume tests land with code. A user asking for no tests has to say so explicitly.

---

## 10. Write for a zero-context reader

**Every project file is drafted on the assumption that the next person to read it has not seen the conversation that produced it.** This is non-negotiable — it is the single invariant that makes `*-PROJECT.md` files usable across sessions, agents, and models.

### Why the invariant is non-negotiable

- The drafting agent may `/clear` or be archived before execution begins. The user explicitly does this between design and implementation.
- Conversation-context auto-compaction happens without warning mid-session.
- The implementing agent is often a different session, a different day, or a different model.
- Even the same agent, days later, has no conversational memory — only the file.
- A project that reads "as discussed above" or "per the conversation" is a project that only one past agent could execute.

**Cost of violating it:** the implementing agent either re-interrogates the user for context that is no longer retrievable, makes silent assumptions that drift from intent, or stalls. All three erode the methodology's value.

### How to make a project self-contained

1. **Inline the context in §1.** Don't just link to KB docs — include the 2-4 sentences of *why this project exists* inside §1. A future reader's first pass should be §1 alone, with no tab-jumping to reconstruct motivation.
2. **Quote the user in §2 Confirmed constraints** when a decision came from their words. Direct quotes preserve tone and rule out paraphrase drift (`*"I don't want every product to have standard-routes access, only authorized/scoped ones."*` is a quote that survives handoff; "user prefers scoped access" is a paraphrase that won't).
3. **§5 Architecture names files with paths.** Every referenced file carries its full path. When you quote code shapes, date-stamp them (`verified 2026-04-XX`) so the next agent knows whether to re-verify. Line numbers drift; the date-stamp tells the reader when the snapshot was taken.
4. **§7 Open Questions is the interrogation gate, and each Q ships with a recommendation.** Every open question is paired with a 2-3 sentence evidence-backed recommendation (per `§9` — "Estimate off evidence, not structure" is also a project-authoring rule, not just an execution rule). The implementing agent asks the user each Q *before* starting Phase 1; answers land in §2.
5. **§10 verification commands are copy-paste ready.** Absolute paths where appropriate, explicit venv invocation, no "just run the tests" hand-waves. A reader should be able to verify any phase without reconstructing tribal knowledge.
6. **Add an "If something surprises you" or equivalent escape-hatch note.** Anticipate drift between drafting and execution — line numbers may move, tests may already be red, an adjacent piece of the system may be in an unexpected state. Tell the next agent how to react: note the drift, keep going, escalate a new project when needed.
7. **Note whether the drafting agent is still reachable.** If the user says they will `/clear`, the conversation is ending, or the drafting agent is otherwise departing, write that in the project header. The implementing agent reads the header first and knows they have no one to ping for follow-up questions — the file is all they have.

### Self-contained ≠ long

A 300-line project can be self-contained. A 900-line one can fail. The test is not "how thorough is it" but "can a cold reader execute Phase 0 without asking the user anything beyond §7 Open questions?"

**Symptoms of under-inlining** (to catch during review):
- "See the conversation for context" / "as we discussed" / "per the chat above" — all failures.
- A design decision in §3 with no source — failure (§2 should carry it with a quote or inferred-from-context note).
- §7 questions without recommendations — the implementing agent has to re-derive the tradeoffs.
- §10 commands with placeholder paths (`<product>`, `<schema>`) — the reader has to guess.

**Symptoms of over-inlining** (to prune during review):
- Re-stating KB content verbatim when a pointer suffices. Pointer + one-line summary is enough for stable KB content; only inline if the KB section is unstable or if the pointer would make the reader's first pass incoherent.
- Narrating the conversation ("the user asked X, then the agent did Y, then the user said Z"). The outcome belongs in §2; the narrative does not.
- Duplicating §6 phases in §5 Architecture. Phases describe *work*; §5 describes *target shape*.

---

## 11. Clean-folder principle

**Every artifact has a home. Nothing lives loose at repo root.** The repo root holds platform-wide files (CLAUDE.md, README.md, docker-compose.yml, package.json if any, license, .gitignore, scripts folder pointer) and nothing else. Work-in-progress docs, audit handoffs, half-drafted plans, stray `NOTES.md` files — all belong inside a project folder.

### Concrete rules

1. **A delivered artifact that isn't a root-platform file → move it into a project folder.** If an audit, review, proposal-draft, or design doc was created at repo root by any agent (human or AI), its first-class home is `projects/<slug>/` (cross-product) or `products/<product>/projects/<slug>/` (single-product) or `core/projects/<slug>/` (control-plane). Create the project folder from `templates/PROJECT-TEMPLATE.md`, move the original file into it as a reference artifact (e.g., `CODEX-AUDIT-REFERENCE.md`, `DESIGN-NOTES.md`), and delete the root copy.
2. **Reference artifacts inside project folders are first-class.** A project folder can hold PROJECT.md + improvements.md + proposals/ AND any number of `.md` (or other) reference files that support the work. Those references are quoted by §1 Context or §5 Architecture. They travel with the project — not at root.
3. **`proposals/` folders stay clean (`.gitkeep` only) per § 4b of `proposals-and-improvements.md`** — the apply-inline-then-delete methodology; this is the same principle applied to proposal queues.
4. **A completed project's folder is not auto-deleted.** The PROJECT.md + improvements.md are the durable record. The folder lives on; only ephemeral intermediates (proposals, scratch files that have been superseded) get cleaned up.
5. **Consolidate before scattering.** When multiple findings derive from a single source (e.g., one audit spawning multiple derivative work-streams), prefer a single umbrella project with phases grouping related findings over N separate project folders. Separate folders are justified only when the scopes are genuinely independent (different owners, different cadences, different risk profiles).

### Why

A `projects/` folder with 30 half-started one-finding projects is noisier than one `compliance-audit-reconciliation/` project with 5 phases covering the same findings. Future agents scanning `projects/` read a handful of focused projects, not an inventory of every scratch thought. The clean-folder principle is an inventory discipline — the same one behind "apply inline + delete proposals" and "don't leave stray docs at repo root."

### What to do when you find a stray root file

1. Read it enough to understand the scope (audit, proposal, design notes).
2. Decide: is this project-scale or a single-commit cleanup? If single-commit → apply the changes, delete the stray file, summarize in the end-of-work summary. If project-scale → scaffold the project folder, move the file in as a reference artifact, inline the relevant bits into PROJECT.md §1/§2/§5.
3. Never leave the stray file "for later." It violates the principle and silently misleads the next agent who greps the repo.

Doc-backed by `CLAUDE.md` rule "Apply proposals inline, then delete — every deliverable ends with a short summary" (the proposals case) and `KB § 01-PHILOSOPHY.md § No silent errors` (a stray file IS a silent signal that rot is accumulating).

---

## 12. Cross-references

- `templates/PROJECT-TEMPLATE.md` — the canonical project shape.
- `CLAUDE.md` § Engineering Philosophy → "Projects are living documents" — the behavioral rule, loaded every session.
- `mcp/noctusai/README.md` — full tool reference including `noctusai_improvements`.
- `mcp/noctusai/tools/improvements.py` — the implementation.
- `KNOWLEDGE-BASE/CONTEXT/PATTERNS/testing.md` — three-layer test discipline referenced by §9.
- `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md § Estimate off evidence, not structure` — the sibling rule for §9 and §10.
- Memory: `feedback_living_projects.md` — cross-session project discipline.
