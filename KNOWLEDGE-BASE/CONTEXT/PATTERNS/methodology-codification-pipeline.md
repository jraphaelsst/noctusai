# Methodology Codification Pipeline

> **How rules move from human conversation into deterministic, automatically-enforced code.**
>
> This document explains the pipeline that turns "we agreed not to ship X without Y" into a `check_*` function in the keeper. It names the four stages, defines the criteria a rule must meet to reach the codified stage, and walks through real examples of rules that made the journey — plus the rules that legitimately couldn't.
>
> **Why this doc exists.** The pipeline already runs implicitly across the project. Naming it makes the implicit decision explicit: when a new rule emerges, the architect can deliberately route it through the right stages instead of letting it stall at the memory entry. The keeper-housekeeping-upgrade (2026-05-11) is the most recent example of a rule traversing the full pipeline; the pattern was already there for LGPD, webhook 5-pin, status-code assertions, and slowapi-pep563.

---

## 1. The four stages

A methodology rule has a natural life-cycle in this workspace. It starts as a conversation and, if it earns the journey, ends as a function that runs without anyone remembering to invoke it.

### Stage 1 — Emerges (conversation)

The rule appears in a back-and-forth between user and agent. Usually triggered by a slip ("don't mock the database that way" / "you shouldn't have force-pushed there") or a moment of synthesis ("if N=2 we should triage, N=3 we MUST formalize"). At this stage the rule is **pre-textual** — it lives in the moment, with all its nuance and exceptions intact.

### Stage 2 — Documented (memory)

The agent saves a memory entry capturing:
- The rule itself (one sentence).
- The **why** — the past incident, the rationale, the constraint that drove it.
- The **how to apply** — when this rule fires; what shape the work looks like under it.

Stage 2 is the *minimum viable persistence*. Without it the rule survives only as long as the conversation does. The memory entry is private to the agent — it shapes future behavior but isn't visible to other contributors yet.

### Stage 3 — Indexed (KB / CLAUDE.md)

The rule earns a KB pattern document (rich-prose canonical) and a `CLAUDE.md` pointer (terse universal rule). It becomes visible to every agent that opens the repo. The three-way-sync rule (see `KB § 01-PHILOSOPHY.md § Docs stay in sync`) fires here: memory + KB + CLAUDE.md move together.

At Stage 3 the rule is **descriptive**. It tells humans and agents what to do, but enforcement still depends on someone reading the doc and applying judgment in the right moment.

### Stage 4 — Codified (keeper detector)

The rule becomes a `check_*` function in `mcp/noctusai/tools/noctus/dev/compliance.py` (or its successor module). A keeper run (`noctus.dev.review`) fires the check across the relevant scope and emits a `KeeperFinding` with severity, category, and a remediation proposal. The detector ships with a colocated `Test<CamelCase>` regression test that proves the detector catches its target shape (see `KB § PATTERNS/testing.md § Regression-test-the-detector`).

Stage 4 is **active enforcement** — the rule fires whether or not anyone remembered to invoke it. The agent's role shifts from "remember the rule" to "triage the keeper's proposals".

---

## 2. The keeper's role in the pipeline

The keeper is the **Stage 4 layer**. It does one job: deterministic detection + LLM-authored proposals, observation-only. The trio is:

| Module | Stage in the pipeline | What it owns |
|---|---|---|
| Memory entries | Stage 2 | Private persistence of rules + the WHY |
| KB pattern docs + CLAUDE.md | Stage 3 | Public, indexed, prose-rich rule library |
| **Keeper detectors** | **Stage 4** | **Mechanical enforcement of rules that meet the codification criteria** |

The keeper has never been "a separate kind of intelligence". It is the **codification layer of the very same methodology** that lives in memory and KB. A keeper detector is a *rule-with-a-mechanical-predicate*, no more and no less.

This is why the keeper-housekeeping-upgrade (2026-05-11) didn't need a new module: workspace hygiene rules ("archive ≤2 days", "merged branches deleted", "transient files gitignored") meet the codification criteria, so they land in the keeper alongside LGPD and webhook 5-pin. The keeper's domain is not "regulatory compliance" — it is "compliance with any rule the methodology has codified".

### The trio, properly oriented

The trio of `keeper` / `hound` / `mole` is sometimes described as regulatory / curatorial / custodial. That is correct, but a more pipeline-accurate framing is:

- **Keeper** = Stage 4 codification for *any* rule with a mechanical predicate.
- **Hound** = Stage 4 codification for a *specific class of rules* — code-hygiene rules (cross-product duplication, tool-surface fusion, intra-file optimization). Hound could be thought of as a specialized sibling of the keeper, optimized for code-shape detection.
- **Mole** = **execution layer** — when a Stage 4 rule emits a proposal that touches the filesystem (sweep stale worktrees, clear cache), mole is the surgeon that runs the sweep with safety gates. Mole is downstream of the keeper, not parallel to it.

This framing also clarifies why a "fourth identity" is wrong: housekeeping non-compliance is just another rule-class the keeper codifies. The trio isn't a partition by *concern* — it's a partition by *what stage the module operates in*.

---

## 3. Codification criteria — when a rule earns Stage 4

Not every Stage 3 rule belongs in Stage 4. Three criteria must all hold:

### 3.1 Deterministic predicate

The rule must reduce to a question a computer can answer **without judgment**:

| Good (deterministic) | Bad (judgment-dependent) |
|---|---|
| "Every webhook route MUST verify signature before any side-effect" | "Webhook routes should feel idiomatic" |
| "Every test asserting on response body MUST also assert on status_code" | "Tests should be readable" |
| "Archive folders ≤2 days old should remain; anything older should be cleaned" | "The archive shouldn't get too cluttered" |

If a junior engineer + a tree-walking script can't agree on whether the rule fires, it isn't ready for Stage 4. The rule stays at Stage 3 (KB doc + CLAUDE.md), serving as guidance for human judgment.

### 3.2 Recurring

The rule must fire often enough that "just remember it" is unreliable. The recurrence rule (`KB § PATTERNS/project-execution.md § 2.7`) gives a number: **N=3+ instances → MUST formalize**. The same threshold applies to detectors. A rule that has fired exactly once might be a one-off; a rule that has fired three times is a pattern and earns codification.

Counterexample: the `feedback_TEMP_*` memory entries are explicitly held at Stage 2/3 because the methodology hasn't yet been validated across multiple instances. Premature codification would lock in a calibration mistake. Codification is the *latest* possible stage, not the earliest.

### 3.3 Has a clear remediation

The keeper proposes; something else executes. If the rule fires and the only honest proposal is "think hard about this", codification adds noise. Useful codified rules always pair with concrete remediation:

- `check_webhook_pin` → proposal: "Add `verify_signature(...)` before the database write at <file>:<line>"
- `check_status_assertion_rule` → proposal: "Add `assert response.status_code == <expected>` before the body assertion at <file>:<line>"
- `check_archive_staleness` → proposal: "Run `bash scripts/archive-clean.sh --force`"
- `check_branch_orphan` → proposal: "Delete merged branches: `git branch -d <name1> <name2>`"

The remediation makes the keeper's output actionable. Without it the detector is a complaint, not a tool.

---

## 4. Examples — rules that made the journey

The pipeline isn't theoretical. Several rules have already traversed all four stages. Walking through them shows the path concretely.

### 4.1 LGPD-first

- **Stage 1 (emerges):** user flagged early that anything touching personal data needs an LGPD lens before being merged.
- **Stage 2 (memory):** `feedback_lgpd_first.md` — "every data-touching change goes through LGPD lens first; doubt → `noctusai_lgpd_flag(...)`".
- **Stage 3 (KB + CLAUDE.md):** `KB § PATTERNS/lgpd.md` + CLAUDE.md routing entry pointing at the pattern doc.
- **Stage 4 (codified):** LGPD detectors in `compliance.py` — they scan for unredacted PII in logs, missing `noctusai_lgpd_flag` annotations on data-touching routes, and other deterministic shapes.

The journey took multiple sessions; the rule was used as judgment guidance for a long time before the detector existed. The detector exists *because* the rule had matured enough to admit a mechanical predicate.

### 4.2 Webhook 5-pin compliance

- **Stage 1:** the team established that webhook receivers MUST verify signature, scope side-effects, rate-limit, status-pin, and bypass-when-unset.
- **Stage 2:** `feedback_webhook_verify_before_side_effect.md` — five named pins with rationale.
- **Stage 3:** `KB § PATTERNS/webhook-signatures.md` + seed reference implementation at `products/seed/backend/app/routers/webhook_router.py`.
- **Stage 4:** detector that walks every router file, identifies webhook handlers (decorator + name heuristics), and checks each of the five pins. A Stripe SDK carve-out applies to pins 1–3 only; pins 4 + 5 still apply.

The Stripe carve-out is interesting: it shows the codified detector can be **calibrated** through Stage 3 amendments. The rule didn't get weaker — it got more precise.

### 4.3 Status-code-assertion rule

- **Stage 1:** the YouTube Crawler Phase 1 false-green incident — tests asserted on response body but not on `.status_code`, masking a real bug.
- **Stage 2:** `feedback_status_code_assertion_rule.md` capturing the rule + its origin incident.
- **Stage 3:** added as a §1 universal CLAUDE.md mention via the testing pattern doc.
- **Stage 4:** `check_test_status_assertion` in `compliance.py`. Severity *warning* (calibration: the response-variable gating drops false positives on tests that assert on domain-object attributes rather than HTTP body).

This one moved quickly through the stages because the incident gave it both the rationale (Stage 1) and the mechanical predicate (Stage 4) in one shot.

### 4.4 slowapi-pep563 gotcha

- **Stage 1:** the team hit it in three separate products — `from __future__ import annotations` combined with slowapi decorators silently broke rate-limiting.
- **Stage 2:** memory entries captured across the three incidents.
- **Stage 3:** documented as a known-gotcha in the rate-limit KB pattern.
- **Stage 4:** the `SLOWAPI-PEP563-DETECTOR` engineer added a keeper check that flags files importing `from __future__ import annotations` alongside any `@limiter.limit(...)` usage.

This is the **N=3 → MUST formalize** rule firing directly. Codification became non-optional after the third instance.

### 4.5 Hygiene-compliance (in flight)

- **Stage 1:** operator tick 2 surfaced four hygiene gaps (archive staleness, dispatcher inbox/outbox aging, branch orphans, gitignore drift).
- **Stage 2:** memory entries for the operator tick 2 calibration items.
- **Stage 3:** this doc + the project doc at `projects/keeper-housekeeping-upgrade/PROJECT.md`.
- **Stage 4:** Engineer K is implementing the four `check_*` functions and colocated tests as we speak.

Stage 4 is in flight, not yet landed. When it does, the housekeeping rules become indistinguishable from the LGPD rules: same module, same detector shape, same proposal pipeline.

### 4.6 Seed export-surface membership

- **Stage 1:** social-wiring-absorption W1.E2 found `lid_auth.py` lifted into `noctusai_lib.integrations.whatsapp` with code present but ZERO `__all__` membership + no colocated tests — a "reconciled-but-invisible" half-ship (the deep import worked, the seam was unpublished). W2.4/DEP-B found `createWhatsApp{Connection,Intake}Hooks` + 6 types consumed by validated product hooks but absent from `seed/lib/frontend/src/index.ts`. N=2, same shape, both surfaces.
- **Stage 2:** memory `feedback_seed_export_membership_keeper`.
- **Stage 3:** this entry + the verify-the-seed-ships-it rule it extends (`feedback_verify_seed_ships_it` — file-presence → public-export-surface membership).
- **Stage 4:** `check_seed_export_membership` in `compliance.py`. For each symbol a product imports from a seed *package* path (`from noctusai_lib.x.y import sym` where `x/y/` is a package with a literal `__all__`, or a `@noctusai/lib` / `@noctusai/seed` frontend import), assert membership in that package's `__all__` (backend) / `index.ts` re-export surface (frontend, per-specifier — `@noctusai/lib` and `@noctusai/seed` resolve to *different* index.ts files). Severity `warning`. **Calibration that mattered:** the predicate must (a) resolve to the *exact imported package*, not the lean lazy root `__all__`; (b) exempt `from <pkg> import <submodule>` (a module import — `__all__` does not govern submodule importability; this was a real N=4 FP class — therapy/PF/mailing/social-wiring all `from noctusai_lib.api import scheduler`); (c) skip `export *` / computed-`__all__` (non-enumerable → false-negatives over noise). Without all three the detector emitted 685 false positives; with them, 0 on the reconciled tree (it fires only on a genuine future regression).

### 4.7 Hardcoded product-slug set in seed tests

- **Stage 1:** social-wiring-absorption W3.5 — `test_cors_registry` + `test_per_product_cors_sentinel` both froze literal product-slug tuples/sets that went stale when `media-scheduling` was consolidated, surfacing as CORS assertion failures *misattributed twice* to the wrong commit before `git log -S` settled it. N=2.
- **Stage 2:** memory `feedback_hardcoded_product_slug_set_keeper`.
- **Stage 3:** this entry.
- **Stage 4:** `check_hardcoded_product_slug_set` in `compliance.py`. Flags any `seed/lib/backend/tests/` literal list/tuple/set containing ≥3 live product slugs (the recognizer corpus is derived from the live `products/` tree at scan time — the detector itself must not freeze a slug literal, or it would violate its own rule). Remediation: derive from `parse_products_registry()` (`noctusai_lib.config.cors_registry`). Opt-out: a `slug-literal-ok` / `registry-exempt` / `not-a-product-set` rationale keyword (mirrors the `check_mock_schema_validation` guardrail) for the rare legitimate slug→x fixture. Severity `warning`. W3.5 already root-fixed `test_cors_registry` (registry-derived assertion, `c9e1abb`); the detector still fires correctly on the remaining `test_per_product_cors_sentinel` frozen literal until the W4 teardown re-homes it.

---

## 5. What CAN'T be codified — and why that's fine

Some rules legitimately stay at Stage 3 (KB + CLAUDE.md), and trying to drag them into Stage 4 would do harm.

### 5.1 Judgment-dependent rules

- **"Estimate off evidence, not structure"** — depends on the agent's reading of the change scope. No mechanical predicate.
- **"No quick fixes — solve root causes"** — requires understanding *why* a fix is at the wrong layer; that's a synthesis judgment, not a pattern match.
- **"Don't extend scope mid-session"** — requires knowing what the original scope was.

These rules shape the agent's behavior at decision points the keeper can't see. They live as memory entries + KB prose precisely because *judgment is the rule*.

### 5.2 Context-dependent rules

- **"Branching-first orchestration — parallelize by default; serial requires justification"** — whether a chunk is parallelizable depends on the chunk. A keeper detector would have no way to read the brief and decide if parallelism was the right call.
- **"Triage at decision time — formalize / refactor / accept-with-rationale"** — fires at the moment of decision; the decision itself is the rule.

### 5.3 Methodology-in-pilot

Rules that are still being validated stay at Stage 3 deliberately. Promoting them prematurely codifies a calibration mistake. The pattern: a TEMPORARY memory entry (e.g. `feedback_TEMP_methodology_validation_in_progress.md`) explicitly forbids Stage 4 promotion until N≥5 varied instances confirm the rule. Erase the TEMP entry when the rule proves out.

### 5.4 Aesthetic / craft rules

- **"Default to writing no comments"** — code-style guidance that depends on the reader's mental model. A detector here would tend to be either too noisy (every comment flagged) or too quiet (only literal docstrings) and would fail to capture the spirit of the rule.

These are stage 3 forever. That's healthy. The codification layer should hold the mechanical rules; the prose layer should hold the judgmental ones; neither layer should try to absorb the other.

---

## 6. How to promote a rule through the pipeline

When you encounter a new rule (or a memory entry that has accumulated multiple instances), decide its next stage with this checklist:

### From Stage 1 → Stage 2 (always)
Always save the memory entry. Stage 1 → Stage 2 is the default — the cost is one small file, the benefit is durable retention.

### From Stage 2 → Stage 3 (when the rule generalizes)
Promote when:
- The rule applies beyond a single conversation or product.
- Other agents would benefit from seeing it without your memory.
- The KB-first / CLAUDE.md-pointer / three-way-sync routine is justified.

### From Stage 3 → Stage 4 (when codification criteria are met)
Promote when:
- The rule has a deterministic predicate (§3.1).
- It has recurred ≥3 times OR is unambiguously the right design for new code (§3.2).
- A clear remediation exists (§3.3).

The promotion itself is a small project — file `projects/<rule-slug>-codification/PROJECT.md` from template, scope §6 to "add `check_*` function + colocated test + KB amendment", dispatch one engineer. The keeper-housekeeping-upgrade is the reference shape.

### From Stage 4 → back to Stage 3 (rarely, but possible)
A codified detector that produces consistent false positives should drop back to Stage 3 with a memory entry capturing why. Better to lose mechanical enforcement than to train agents to ignore the keeper. The `noctus.dev.review` workflow already supports retiring detectors by removing them from the global-checks list.

---

## 7. Why naming this pipeline matters

For most of this workspace's history, the pipeline ran without a name. New rules entered conversation, got memory entries, sometimes earned KB docs, and occasionally graduated to keeper detectors — but the path was implicit and the criteria were intuitive. Naming the pipeline gives the architect a deliberate tool:

- **When a slip surfaces**, the architect can ask: "is this Stage 1 → 2 (just save memory), or have we hit Stage 2 → 3 (now it earns a KB doc)?"
- **When a memory entry recurs**, the architect can ask: "is this ready for Stage 3 → 4?"
- **When a keeper detector misfires**, the architect can ask: "should this drop back to Stage 3?"

The pipeline isn't bureaucracy. It is the **shape of how methodology actually evolves in this workspace**, made visible so the next move is obvious instead of guessed.

---

## 8. Situation → tool map (greppable)

Future agents land in a situation ("the archive looks bloated", "tests are silently passing", "the dispatcher inbox is growing"). They need to know **which tool or script handles this** without re-deriving the pipeline. The table below is intentionally **greppable** — search by symptom-phrase, by tool name, or by stage; every row contains the actual invocation.

If a row references a keeper detector by name (`check_*`), confirm it currently exists via the AST-based discovery method in §10 — the catalog rotates as detectors are added or retired, and this table can lag.

### Workspace hygiene (Stage 4 — keeper hygiene detectors + execution scripts)

| Symptom you see | Tool / script | Invocation | Stage |
|---|---|---|---|
| Stale archive folders (older than today + yesterday) | `check_archive_staleness` + `archive-clean.sh` | `noctus.dev.review` (detect) → `bash scripts/archive-clean.sh --force` (execute) | Stage 4 detect → script execute |
| Stale agent worktrees on disk | `mole.sh` worktree scope (now aligned scan↔sweep enumeration) | `bash scripts/mole.sh scan --worktrees` reports STALE / STALE_LOCKED / STALE_DIRTY / ACTIVE / ORPHAN / PHANTOM categories; `bash scripts/mole.sh sweep --worktrees --force` removes STALE + ORPHAN + PHANTOM only | Stage 4-equivalent custodial |
| Disk artifacts (caches, builds) bloating repo | `mole.sh` artifact scope | `bash scripts/mole.sh scan --artifacts` / `... sweep --artifacts --force` | Stage 4-equivalent custodial |
| Dispatcher inbox/outbox entries piling up | `check_dispatcher_staleness` | `noctus.dev.review` (detect); manual prune of `dispatcher-inbox.md` `## Completed` section; consider archiving to `dispatcher-archive/<date>.md` | Stage 4 detect → manual execute |
| Merged branches still hanging around | `check_branch_orphan` | `noctus.dev.review` (detect); `git branch -d <name>` (local) / `git push origin --delete <name>` (remote) | Stage 4 detect → git execute |
| Transient log/coordination files not gitignored | `check_gitignore_drift` | `noctus.dev.review` (detect); `.gitignore` patch + `git rm --cached <file>` if tracked | Stage 4 detect → gitignore patch |
| Disk usage approaching capacity | `disk-usage-monitor.sh` | `bash scripts/disk-usage-monitor.sh` (exit code 0-3 by severity) | preventative monitor |

### Code hygiene (Stage 4 — hound + seed scans)

| Symptom you see | Tool / script | Invocation | Stage |
|---|---|---|---|
| "Which file should I absorb next?" | `noctus.seed.report` (P0-P5 triage) | `mcp__noctusai__noctus_seed_report` | Stage 4 hound (absorption) |
| Code duplicated across N products | `noctus.seed.scan_repetition` | `mcp__noctusai__noctus_seed_scan_repetition` | Stage 4 hound (absorption) |
| Tool surface bloat (too many similar MCP tools) | `noctus.seed.scan_fusions` | `mcp__noctusai__noctus_seed_scan_fusions` | Stage 4 hound (fusion) |
| Intra-file dead code / single-call helpers | `noctus.seed.scan_optimizations` | `mcp__noctusai__noctus_seed_scan_optimizations` | Stage 4 hound (optimization) |
| "What cleanup is most urgent?" (covers all 3 hound scopes) | `noctus.hound.scan` | `mcp__noctusai__noctus_hound_scan` | Stage 4 hound (orchestrator) |
| Helper duplicated within one product (N≥3) | `noctus.dev.scan_within_product_helpers` | `mcp__noctusai__noctus_dev_scan_within_product_helpers` | Stage 4 hound (within-product) |
| Helper duplicated across products | `noctus.dev.scan_cross_product_helpers` | `mcp__noctusai__noctus_dev_scan_cross_product_helpers` | Stage 4 hound (cross-product) |

### Compliance + security (Stage 4 — keeper regulatory detectors)

| Symptom you see | Tool / script | Invocation | Stage |
|---|---|---|---|
| Webhook receiver — is the 5-pin compliance contract honored? | `check_webhook_pin` family in `compliance.py` | `noctus.dev.review` (runs full keeper) | Stage 4 keeper |
| Test asserts on response body — does it also assert status code? | `check_test_status_assertion` | `noctus.dev.review` | Stage 4 keeper |
| File imports `from __future__ import annotations` + uses `@limiter.limit` (slowapi gotcha) | `check_slowapi_pep563` | `noctus.dev.review` | Stage 4 keeper |
| LGPD risk — unredacted PII in logs / missing flag annotations | `check_lgpd_*` family | `noctus.dev.review` + `noctus.dev.lgpd_flag` for manual flagging | Stage 4 keeper |
| Auth router not using `make_get_current_user_org` factory | `check_auth_factory_pattern` (or equiv) | `noctus.dev.review` | Stage 4 keeper |
| Pydantic schema silently dropping unknown fields | `check_pydantic_strict_http` | `noctus.dev.review` (post StrictHttpModel rollout) | Stage 4 keeper |
| Per-phase learnings not logged | `phase_state_consistency` global check | `noctus.dev.review` (global mode) | Stage 4 keeper (global) |
| Seed version stamps stale | `seed_version_propagation` global check | `noctus.dev.review` | Stage 4 keeper (global) |
| Detector regression test missing for a `check_*` | `meta_detector_regression_test_presence` | `noctus.dev.review` | Stage 4 keeper (meta) |
| Literal `# silent-ok` annotation present in production code (escape hatch retired 2026-04-28) | `check_no_silent_ok_comment` | `noctus.dev.review` (global mode) → replace with `logger.<level>(...)` / `raise` / surface via return value | Stage 4 keeper (global) |
| Router uses `Depends(ProductDependencies.{get_org_id,get_user_role,get_user_client})` (422-trap shape) | `check_auth_dep_anti_pattern` | `noctus.dev.review` → migrate to `Depends(get_current_user_org)` via the `make_get_current_user_org` factory | Stage 4 keeper (per-product routers) |
| MCP tool computes root via `Path(__file__).parents[N]` instead of `from settings import REPO_ROOT` | `check_mcp_path_via_settings` | `noctus.dev.review` → import `REPO_ROOT` / `PRODUCTS_DIR` from `settings` | Stage 4 keeper (MCP scope) |
| MCP write-side tool def lacks `worktree_path: str` arg (engineer can't route side-effect into worktree) | `check_mcp_write_tool_worktree_arg` | `noctus.dev.review` → add `worktree_path: str \| None = None` + resolve writes relative to it | Stage 4 keeper (MCP scope) |
| Shell script has `cmd \| grep -q ...` under `set -o pipefail` (SIGPIPE-141 footgun, Engineer M discovery 2026-05-11) | `check_pipefail_grep_q` | `noctus.dev.review` → split pipeline, consume full stream, or drop `-q` | Stage 4 keeper (scripts scope) |
| KB doc references `bash scripts/<name>.sh <mode>` but `<mode>` no longer exists in the script (doc-code coherence drift) | `check_doc_tool_reference_drift` | `noctus.dev.review` → update either the doc or the script in the same change | Stage 4 keeper (KB doc scope) |

### Project / dispatch operations

| Symptom you see | Tool / script | Invocation | Stage |
|---|---|---|---|
| Starting a new project | `templates/PROJECT-TEMPLATE.md` | `cp templates/PROJECT-TEMPLATE.md projects/<slug>/PROJECT.md` | methodology |
| New product scaffold | `noctus.dev.scaffold_product` | `mcp__noctusai__noctus_dev_scaffold_product` | seed-first contract |
| Testing-ground / sandbox workspace | `noctus.dev.create_testing_ground` | `mcp__noctusai__noctus_dev_create_testing_ground` | sibling workspace |
| Project close / archive | `noctus.dev.archive` | `mcp__noctusai__noctus_dev_archive(project-path)` | project lifecycle |
| Inbox-drain for autonomous operator | `orchestrator-operator` subagent | `Agent(subagent_type="orchestrator-operator", ...)` after writing tasks to `dispatcher-inbox.md` | Option D (in-pilot) |
| Clean archive (D-2+ folders) | `archive-clean.sh` | `bash scripts/archive-clean.sh --force` after dry-run | housekeeping |
| Disk audit + cleanup | `mole.sh` orchestrator | `bash scripts/mole.sh scan` (all scopes, read-only) → `... sweep <scope> --force` | custodial |

### When a symptom doesn't appear in this table

If the symptom matches no row, the rule may be at Stage 1-3 (not codified) or genuinely new. Three actions:

1. `grep -ri "<symptom-keyword>" KNOWLEDGE-BASE/` — Stage 3 prose may cover it.
2. `grep -ri "<symptom-keyword>" $HOME/.claude/projects/<workspace>/memory/` — Stage 2 memory entries may cover it.
3. If neither hits, the rule is at Stage 1 (still in conversation) — surface to the user. Don't invent a tool.

---

## 9. Discovering current detectors at runtime (AST-based)

The §9 table is hand-curated; the source of truth for *currently active detectors* is the keeper's compliance module. To get a live, never-stale list, use **AST outline tools** rather than re-reading this doc:

### Quick canonical detector inventory

```bash
# All detector functions (Stage 4 codified rules) in the keeper:
mcp__noctusai__noctus_dev_outline_python \
  --file mcp/noctusai/tools/noctus/dev/compliance.py
```

The outline returns every top-level function with name + line + signature. Detectors follow the `check_*` naming convention — filter by prefix to get just the detector list. Read the docstring for each to learn its trigger + proposal shape.

### Why this matters

The §9 table will lag — new detectors land continuously, retired detectors leave gaps. The KB pattern doc is a **navigation aid**, not a manifest. The AST outline is the manifest. Future agents that need authoritative answers should run the outline command, not trust the static table.

This is the same reason the agent reading discipline (`KB § PATTERNS/agent-reading-discipline.md`) prefers `noctus.dev.outline_python` over wide-net grep for symbol discovery in Python files — AST-based queries don't drift with formatting/whitespace and surface the exact function set the runtime knows about.

### Companion AST queries for the trio

```bash
# Hound code-hygiene scans — what scopes exist now?
mcp__noctusai__noctus_dev_outline_python \
  --file mcp/noctusai/tools/noctus/hound/scan.py

# Seed absorption tooling — full surface area
mcp__noctusai__noctus_dev_outline_python \
  --file mcp/noctusai/tools/noctus/seed/report.py
mcp__noctusai__noctus_dev_outline_python \
  --file mcp/noctusai/tools/noctus/seed/scan_repetition.py
# (etc — grep the mcp/noctusai/tools/noctus/seed/ directory for the full set)
```

### Caveat — scripts are NOT AST-discoverable

The mole + archive-clean + cleanup-stale-worktrees scripts live in `scripts/` as bash. They have no AST outline tool that lists their modes. For shell scripts, the discovery pattern is:

```bash
# Show every script's purpose header + usage comments:
grep -lE '^#! ?/.*sh' scripts/ | xargs -I {} head -30 {}
```

Every script in this repo follows the convention of putting a `# Usage:` block at the top. Reading the first 30 lines of each `.sh` file gives the situation → mode mapping for shell-side tools.

### Updating §9 when a detector lands

When a new `check_*` function is added to `compliance.py` (or `hound/scan.py`, or a new tool registers in `mcp/noctusai/tools/`), the engineer SHOULD add a row to §9. The pre-commit hook does **not** enforce this (intentional — false positives in this scope are noisy); it's a discipline rule documented here. If §9 drifts, the AST outline is the safety net.

---

## 10. Related patterns

- `KB § 01-PHILOSOPHY.md § Docs stay in sync` — the three-way-sync rule that powers Stage 2 ↔ Stage 3.
- `KB § PATTERNS/project-execution.md § 2.7 The recurrence rule` — the N=2/N=3 gate that drives Stage 3 → Stage 4 promotion.
- `KB § PATTERNS/testing.md § Regression-test-the-detector` — every Stage 4 detector ships a colocated test, by rule.
- `KB § PATTERNS/seed-absorption.md § noctus.hound.scan` — the curatorial sibling of the keeper; the same pipeline, optimized for code-shape rules.
- `KB § PATTERNS/storage-hygiene.md` — the trio doc; mole is the execution layer downstream of the codified keeper rules.
- `KB § PATTERNS/accept-with-rationale.md` — the catalog for rules deliberately not promoted (Stage 3 with justification, durable across project folder deletion).
