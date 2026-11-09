# Gate↔methodology sync — the build triad: construction, backstop gate, alignment telemetry

**The rule.** When you add a **gate** (a keeper that hard-blocks on a violation of a platform standard/rule), you MUST ship — in the **same change** — the **code-level mechanism that makes compliance automatic / by-construction**, so the gate rarely fires in normal flow. The gate names the standard; the mechanism *executes* the standard. **Never** ship a gate whose only "compliance path" is a human/agent remembering to do the right thing, and **never** satisfy a gate by working around it (monkeypatching the guard, `--no-verify`, loosening the assertion, deleting the row). Codified 2026-06-02 after the pattern recurred N≥3 times.

**Why.** A gate alone converts a silent drift into a *loud, recurring* drift — every agent that forgets the rule hits the wall, fixes it manually, and the next agent hits it again. That's strictly better than silent drift, but it's not the goal. The goal is **drift that cannot happen**: the standard is encoded in the code path that produces the artifact, so the normal way of doing the thing *is* the compliant way. The gate then becomes a **backstop** for out-of-band edits / legacy rows / foreign contexts — not the primary enforcement. Gate + mechanism are two halves of one contract; shipping the gate without the mechanism is an incomplete commit (`KB § 03-SEED-ARCHITECTURE.md` "no incomplete commits").

This is the same instinct as **fix-on-contact** ([[drift-fix-on-contact]]) and **safety-nets-capture-failures→methodology-evolves** (`KB § 01-PHILOSOPHY.md`), applied to the gate-authoring moment: the net firing IS the methodology working, but the *design target* is a system where the net almost never has to fire because the code already complies.

## The two halves (ship together, same commit)

| Half | What it is | Property |
|---|---|---|
| **Gate** (keeper) | A `compliance.py` detector (high/critical) that hard-blocks (pre-commit / pre-push / CI) when the standard is violated — scanning ALL relevant artifacts, incl. historical/terminal rows where the invariant is "always true". | Catches drift: out-of-band edits, legacy data, a context the mechanism didn't run in. |
| **Compliance mechanism** | The code path that **produces** the artifact does the compliant thing **automatically** (default-fills, derives, normalizes, writes-both, validates-then-refuses). The caller cannot easily produce a violating artifact. | Makes the normal path compliant by construction → the gate rarely fires. |

**No-silent-null corollary.** When the mechanism can't auto-derive a required value, it **refuses loudly** (returns an error / raises) rather than writing a placeholder/null — a null would just trip the gate later, one level removed (`KB § 01-PHILOSOPHY.md` "no silent errors").

## Worked examples (the N≥3 that triggered codification)

- **Branch-tree mirror** — gate `check_branch_tree_mirror` hard-blocks if ledger ≠ mirror; mechanism `branch_pointer._write_row` writes BOTH files on every append/update. An agent can't populate one without the other. (`KB § PATTERNS/architect/branch-tree-tracking.md` §2)
- **Branch-tree session** (2026-06-02) — gate: the same keeper flags any null/empty `session` across ALL rows; mechanism: `branch_pointer.append/update` auto-fill `session` from `CLAUDE_CODE_SESSION_ID` (→ newest-transcript fallback → refuse). A pointer can no longer be written session-null.
- **Detector-has-regression-test** — gate `check_detector_has_regression_test` flags any keeper lacking a test; mechanism: the authoring procedure ships the `Test<Detector>` class with the detector (and `scaffold_keeper` emits the test stub).
- **Cache freshness** — gate `check_*_cache_freshness`; mechanism: structural caches self-heal on contact (`settle_structural_caches`) + refresh pre-commit, so the gate is a backstop, not the refresh path. ([[cache-auto-freshness]])
- **SECURITY DEFINER EXECUTE** (2026-10-06) — gates `check_secdef_migration_revokes_execute` (static, commit) + `verify_db_guards` secdef probe (runtime, predeploy); mechanism: the migration itself carries the REVOKE (lockdown DO-block derives its keep-list from `pg_policy`, never a hand list). (`KB § PATTERNS/backend/migration-sql-security-gates.md`)
- **Seed Fake+Real+factory** — gate flags a half-shipped seed IO module; mechanism: the seed-adapter scaffold ships all three so a consumer can't fork. (`KB § PATTERNS/backend/seed-fake-real-adapter.md`)

## Anti-patterns (forbidden)

- **Gate-only** — ship the keeper, leave compliance to memory/discipline. (The drift recurs forever; agents burn cycles re-fixing.)
- **Workaround the gate** — `--no-verify`, monkeypatch the guard, weaken `==` to `in (...)`, delete the offending row to pass. (`KB § PATTERNS/common/bypass-rationalization-anti-patterns.md`)
- **Silent-null compliance** — auto-fill a placeholder/null just to clear the gate. Refuse loudly instead.
- **Mechanism-only** — ship the auto-fill but no gate. (Out-of-band edits + legacy rows + foreign contexts silently re-introduce the violation.)


## The build triad (2026-11-05): the pattern for anything enforceable

Owner, 2026-11-05: *"we shall build correctly by default, not by getting gated and fix. ... the idea is not not getting gated, but rather build correctly and gated catch only real drifts. please make sure those are always aligned"* and *"make sure future mechanisms are built correctly by default by methodology. so this isnt a 1-time fix, but rather a new build pattern."*

Anything an agent must remember (a rule, standard, keeper, guard, ledger, template) is authored as a **triad, in one change**:

| Leg | What | Property |
|---|---|---|
| **(a) Construction** | The scaffold, template, typed factory, write path or start-time injection that makes the correct thing the default. Eliminate the CLASS at the API: the safe path is the easy path, the raw primitive is restricted. | Compliance is what you get by doing the normal thing. |
| **(b) Backstop gate** | The gate that catches only real drift (out-of-band edits, legacy, foreign contexts). Placed by measured precision, not severity alone. | Fires ~never in normal flow. |
| **(c) Alignment telemetry** | Proof that (a) works: every refusal is an event (gate, actor, target, outcome); a refusal not followed by a pass of the same gate is an *effective false positive*. | A wall is ranked automatically, not found late. |

Authoring paths emit the triad pre-wired, not as a checklist: `noctus.dev.scaffold_keeper` **refuses** without `mechanism` (a construction pointer, or `none (reason)`), `owner` and `source`, and emits the inventory declaration plus a warn-first shadow block; `noctus.dev.scaffold_migration` returns the guard-probe stub and the by-name test reference; the cli exit wrapper logs every `--check-*` run (telemetry is automatic, nobody remembers it). The skills that author things (`skill-creator`, `noc-mcp-tool`, `noc-new-agent`, `noc-new-product`) and the tooling-engineer agent point here.

### The alignment loop (recurrent, not a one-time audit)

1. **Measure** firings: `python mcp/noctusai/cli.py --gate-alignment walls` (MCP `noctus.dev.gate_alignment`) ranks gates firing in normal flow (>= 10 firings across >= 4 sessions) and each gate's effective false-positive rate. It runs on its own from `noc-daily-ops` / `noc-hygiene` with `--file-walls`, which reconciles the `gate-walls` living findings ledger (`gate_wall_findings.py`; mechanism `findings_ledger`, exported as SARIF 2.1.0: ruleId, baselineState, suppressions). Its scanner is deterministic (committed inventory only), so `check_findings_ledgers` agrees on every machine.
2. **Classify**: real-drift catch · wall (fires in normal flow: construction leg missing or broken) · false positive · never-fires · unmeasured (runs outside the commit path, no per-run event yet). Unmeasurable is never "never-fires".
3. **Fix the mechanism** (the construction leg), not the agent. The gate stays a backstop.
4. **False alarms get researched, not just demoted.** Effective-FP above ~10% (tunable `MAX_EFFECTIVE_FP`, Tricorder's bar): (i) *containment*: demote to warn, with an inventory `demoted` block {since, expiry, destination} and an open ledger row; (ii) *research* how specialists detect that property precisely, from primary sources (vendor docs, OWASP, the tool or paper that solves it), **read and cited** in the detector docstring or KB entry; (iii) *fix the detector* to test the actual violation, with an FP regression test per false-alarm case and a TP test per true positive; (iv) *re-measure*; (v) *re-promote* once under threshold. `check_gate_triad` fails a demoted gate with no destination, and one past its expiry, so a gate cannot stay demoted forever.
5. **Re-measure** after the fix: the wall must drop out of the ranking. A gate succeeds when its class approaches zero in new code, not when it fires a lot.

### Admission & demotion by measured precision

A new blocking gate first runs warn-only in **shadow** (`placement: warn`, `shadow: {since, fires, fix_rate}`) for >= 7 days, and is promoted only when its effective-FP is under the threshold and its fix rate is above it. Zero-false-positive-by-construction gates (baseline-ratcheted, e.g. the meta-gate) may record that reason instead. Every refusal must be actionable: it names the construction path or an automatic fix; a refusal that only names the rule is itself a finding. Every gate has an **owner** (walls route there). Escape hatches are tracked, never silent: rationale + owner + expiry (accept-with-rationale, `NOC-REMEDIATE`); bypass stays forbidden.

### The meta-gate

`check_gate_triad` (`--check-gate-triad`, pre-commit when a gate surface changes) fails when: a wired gate is not in `gate-alignment-inventory.json`; a gate has no owner or a mechanism that is neither a construction pointer nor `none (reason >= 12 chars)`; a new gate cites no `source` or a new blocking gate has no shadow record; a decision-matrix row misses a leg or names no real gate; a new gate has no matrix row; a demoted gate has no destination or is past expiry. Legacy gates that predate the rule sit in `gate-triad-baseline.json`, a **shrink-only burn-down** (the keeper fails on a baseline row that has since declared a mechanism, so it only ever shrinks; it is never a grandfather). Order: mechanism first, then backfill, then the gate, so the meta-gate never went red on legacy state. Current burn-down: `python mcp/noctusai/cli.py --gate-alignment triad`.

### Measured comparison, not standard-by-default

Owner: *"we switch where we built ours and standard tools perform better, faster, cheaper, and so on and so forth on metrics."* When an in-repo mechanism and a standard tool cover the same job, compare them on stated metrics (coverage/recall, precision, speed, cost in money and tokens, maintenance, integration fit, security posture) and switch only when the standard wins on the metrics that matter; record a short decision record **with numbers**. Unmeasured means no switch. For a NEW capability with no in-repo mechanism, prefer an established tool when it measures adequately and record the same note. `check_new_dependency_justified` (warn-first shadow) checks that a new dependency carries its comparison record in `mcp/noctusai/dependency-additions.json`; it never checks "is it standard". SARIF 2.1.0 (findings ledger), the FastAPI dependency wrapper (`make_router(tier=)`), the Supabase advisor and promptfoo are **candidates to measure**, not decisions. Check the repo first for an existing mechanism (codebase is the source of truth for solutions).

### Sources & how they map

Read before codifying (step 0 of the checklist; each new gate cites its `source`):
- Google, *Building Secure and Reliable Systems*, ch. 12 "Frameworks to Enforce Security and Reliability": safety lives in common frameworks/libraries that only expose interfaces where the vulnerable class cannot be written; compiler errors give immediate actionable feedback while linters/review give it late; for legacy: restrict the unsafe API, keep a reviewed exemption list, block NEW uses with commit hooks. Maps to: construction leg = eliminate the class at the API; the shrink-only baseline.
- Sadowski et al., "Tricorder" (ICSE 2015) and "Lessons from Building Static Analysis Tools at Google" (CACM 2018; abstracts and secondary summaries read, primary PDFs not retrievable): effective false positive = no positive action taken; keep under ~10%; a not-useful signal per analyzer owned by its author; noisy analyzers demoted; new analyzers pass a precision threshold; fixes suggested. Maps to: `gate_stats.effective_fp`, shadow admission, demotion, owner.
- Google, "Secure by Design" (2024) / Safe Coding, and CISA Secure by Design: move responsibility from the individual to the framework (well-lit paths); eliminate classes, measure each class's frequency. Maps to: triad (a), "class approaches zero".
- Platform-engineering paved-road practice (secondary sources): guardrails not gates, tracked escape hatches, outcome-based checks, paved roads decay without an owner. Maps to: owner field, tracked exemptions, property-checking gates.
- SARIF 2.1.0 (OASIS) for ledger interchange; OWASP FastAPI guidance for framework-native auth dependencies (both candidates to measure under the comparison rule).

### Coverage matrix (decision -> legs -> owner)

A decision row with no gate, or a new gate with no row, fails `check_gate_triad`. `pending:<branch>` legs are not failures: they become `gate-walls` ledger rows (`matrix-pending`) so they cannot be forgotten. Only D8/D9 (Julia, `feat/julia-turn-redesign`) are pending after the access-tiers merge.

| # | Decision | Home | Construction | Backstop gate | Telemetry | Branch |
|---|---|---|---|---|---|---|
| D1 | Access tiers on every route and table, platform-wide, default deny. Route construction = `make_router(tier=)` over FastAPI APIRouter `dependencies=` (framework-native; to be MEASURED against alternatives) | KB § PATTERNS/security/access-tiers.md | api:noctusai_lib.api.access_tiers (DEP_TIERS, @access_tier, make_router(tier=)); seed example routers gated | keeper:check-access-tier-routes + guard:access-tier (write time) | gate events (cli wrapper, guard-events) + access-tier ledger | feat/access-tiers-gate |
| D2 | Closed public allowlist (landing+nav, login/signup/reset, pricing/checkout/thank-you w/o PII sans one-time token, legal/consent, lead forms); webhooks/OAuth callbacks/health in a service/signed tier | KB § PATTERNS/security/access-tiers.md | closed PUBLIC_CATEGORIES allowlist in noctusai_lib.api.access_tiers (landing, auth, pricing-checkout, legal-consent, lead-capture); webhooks/OAuth/health in the signed tier | keeper:check-access-tier-routes (admin-looking path behind org/public; unclear) | gate events + access-tier ledger | feat/access-tiers-gate |
| D3 | /docs and /openapi.json are not public in prod | KB § PATTERNS/security/access-tiers.md (API docs are public) | make_router(tier="platform") sets include_in_schema=False | keeper:check-access-tier-routes (class platform-in-public-schema) + assert_tier_contract | access-tier ledger (schema section) | feat/access-tiers-gate |
| D4 | DB defaults: RLS on, no browser grants on non-public tables, no anon/PUBLIC read on token/secret/PII, no inactive schema in pgrst.db_schemas; scaffold emits per-table role-matrix test | KB § PATTERNS/security/access-tiers.md · KB § PATTERNS/backend/database-rls.md | tool:scaffold_migration (tier comment + explicit REVOKE, no browser GRANT by default) | keeper:check-access-tier-tables + existing grant/RLS/bucket keepers | gate events + access-tier ledger | feat/access-tiers-gate |
| D5 | Effective-state production check = Supabase advisor (candidate, to be MEASURED) + our own SQL, scheduled and pre-deploy | KB § PATTERNS/security/access-tiers.md | tool:noctus.dev.access_tier_exposure (read-only effective-state queries diffed against declared tiers); Supabase advisor = candidate to MEASURE (decision record in the access-tiers pattern) | keeper:check-findings-ledgers (drift is a ledger row; unmeasured is never green); noc-daily-ops step 2b | access-tier ledger metrics snapshot | feat/access-tiers-gate |
| D6 | One shared living findings ledger exported as SARIF 2.1.0 (candidate standard format, to be MEASURED against the home-grown shape) uploaded to code scanning; baselineState reconcile; suppressions with justification+owner+expiry | KB § PATTERNS/common/living-findings-ledgers.md | tool:findings_ledger (single writer; export_sarif = SARIF 2.1.0) | keeper:check-findings-ledgers | ledger metrics; gate-walls ledger plugs in the same way | feat/access-tiers-gate |
| D7 | Ledger visibility injected at agent start and dispatch and in every template | KB § PATTERNS/common/living-findings-ledgers.md | injection: scripts/hooks/claude-inject-open-findings.py (SessionStart + SubagentStart) + ledger roster in templates | keeper:check-findings-ledger-visibility | gate events | feat/access-tiers-gate |
| D8 | Julia continuous evals on the real turn path (content-change, schedule, handoff triggers; every mistake becomes a permanent case; MODEL/STRUCTURAL/CONTENT attribution; same ledger) | KB agents-eval pattern | eval harness on the real turn path | pending:feat/julia-turn-redesign | pending:feat/julia-turn-redesign | feat/julia-turn-redesign |
| D9 | Red-team leg with promptfoo ONLY if it measures better than in-repo; else a recorded reason | KB agents-eval pattern | comparison record (decision 12) then harness | pending:feat/julia-turn-redesign | pending:feat/julia-turn-redesign | feat/julia-turn-redesign |
| D10 | The triad for every enforceable thing: construction + backstop gate + alignment telemetry; walls ranking; meta-gate | KB § PATTERNS/common/gate-methodology-sync.md (Build triad) · §1 Gate↔methodology line | tool:scaffold_keeper requires mechanism+owner and emits the inventory row; tool:gate_alignment declare | keeper:check-gate-triad | guard-events.ndjson + noctus.dev.gate_alignment walls | feat/gate-alignment |
| D11 | Gate admission/demotion by measured precision: warn-only shadow, effective-FP <= ~10%, owner, actionable refusals | KB § PATTERNS/common/gate-methodology-sync.md (Admission & demotion) | declare_gate defaults placement=warn; shadow record required for a new blocking gate | keeper:check-gate-triad | gate_alignment.gate_stats effective_fp; walls demote flag | feat/gate-alignment |
| D12 | Measured comparison, not standard-by-default: in-repo vs standard tool compared on stated metrics; switch only when the standard wins on the metrics that matter; unmeasured = no switch. SARIF, FastAPI dependency wrapper, Supabase advisor, promptfoo are CANDIDATES to measure | KB § PATTERNS/common/gate-methodology-sync.md (Measured comparison) · skill noc-dep-update gate 0 | comparison-record template in noc-dep-update; mcp/noctusai/dependency-additions.json | keeper:check-new-dependency-justified | warn-first shadow events via cli wrapper | feat/gate-alignment |
| D13 | Research-first is the default for EVERY request: specialists' reliable sources are read (not link-checked), cited in the deliverable, unverified items marked; tool choice follows the measured-switch rule | KB § PATTERNS/common/gate-methodology-sync.md (Sources & how they map; How to apply step 0) · product-engineer.md + advisor agents L1 line | standing line in .claude/agents/product-engineer.md and the 7 advisor agents; pattern-authoring checklist step 0; scaffold_keeper requires `source` | keeper:check-gate-triad (new gates carry `source`) + report-only `--gate-alignment sources` (KB deliverables without a sources section; never blocks code commits) | sources report output; gate-triad events | feat/gate-alignment |
| D14 | Public-API-docs readiness: every documented route gated and protected by old+new gates with no gap and no duplicate (each property one gate) | KB § PATTERNS/common/gate-methodology-sync.md (matrix) + access-tiers pattern | make_router(tier=) + assert_tier_contract (schema-driven) + old gates re-judged in `api_review` | old (re-judged at predicate level): auth-boundary-false-green (keep, shadow), auth-dep-anti-pattern + standard-routers-audit (functional, out of the exposure set), consent-routes-mounted, no-authenticated-grant (retire after alias), new-org-table-rls, schema-wide-anon-grant, storage-bucket-public, secdef-revokes-execute, no-metadata-authz · new: access-tier routes/tables/streams/fingerprint + guard:access-tier | gate events (cli wrapper) · `api_review` verdicts in the inventory | feat/gate-alignment (old-gate review) + feat/access-tiers-gate (new) |
| D15 | False-alarm gates are researched and fixed, not just demoted: containment by demotion -> research with read+cited primary sources -> detector fix with FP/TP regression tests -> re-measure -> re-promote; ledger row + expiry while demoted | KB § PATTERNS/common/gate-methodology-sync.md (Alignment loop, step 4) | declare_gate/inventory `demoted` block (since, expiry, destination) is the only way to hold a gate demoted | keeper:check-gate-triad (fails a demoted gate without destination, or past expiry) | gate_alignment walls: demote flag from measured effective-FP > 10% | feat/gate-alignment |
| D16 | Gate-wall misalignment is a finding by construction: walls, expired demotions and pending matrix legs live in the shared `gate-walls` findings ledger (deterministic scanner over the committed inventory) | KB § PATTERNS/common/gate-methodology-sync.md (Alignment loop) · KB § PATTERNS/common/living-findings-ledgers.md | tool:findings_ledger register_ledger (gate_wall_findings.py); noc-daily-ops / noc-hygiene run `--gate-alignment walls --file-walls` | keeper:check-findings-ledgers (covers the gate-walls ledger) | ledger rows + SARIF export | feat/gate-alignment |

Full inventory (every gate, class, mechanism, owner, firings; plus the route-auth/exposure re-judgement for a publicly documented API): `gate-alignment-inventory.md` (rendered) from `gate-alignment-inventory.json` (machine-readable, the source), `gate-triad-baseline.json` (burn-down).

## Walls: gates the normal flow keeps hitting (2026-09-23)

The owner's framing: *"gates only function as safety nets, not as part of the dev methodology flow. This is like driving a car and using walls to help you turn the wheel."* A gate that fires during ordinary work is a **wall**: its mechanism is missing or broken, and agents are steering by collision. The signal is measurable. Count the commits that exist only to satisfy a gate (baseline bumps, hand-closed pointers, renumbers, `fix(ci)` on the merged tip, ledger-only commits) and the auto-improvement rows naming a gate. A recurring count is a mechanism bug, not agent carelessness.

**This is a direction, not a new checklist.** The owner, same day: *"we dont want to be too strict in a sense that our deving loses criative potencial."* The goal is less friction, never more process in its name. Most work needs no gate at all. Spikes, prototypes and exploratory branches are free to be rough, and nothing here asks them to justify themselves. Reach for a gate only when an invariant's silent breakage is expensive: prod, data, consent, shared multi-agent state. When a gate starts firing on ordinary work, the fix is usually to remove the friction upstream, and sometimes to delete the gate.

Design rules, for the gates that earn their place:
- **Measure, don't predict.** A guard that parses intent (shell commands) turns into an arms race of fix commits. Where the exact target can't be known up front, allow the action and measure its effect (e.g. the primary-checkout dirt delta), then surface it.
- **Scope the block to the actor who can fix it.** In a shared multi-agent repo, a global-state gate blocks only the session that owns the violation. Peers get a warning (`check_stale_branch_pointers`).
- **Unmeasurable is not red.** A gate that can't run (no venv, no deps) says `SKIPPED — unmeasurable`. It never blocks on its own harness failure (`KB § PATTERNS/common/methodology-execution-discipline.md`, verdict-channel integrity).
- **Judge the change, not the file.** A pre-existing violation elsewhere in a file is the commit-time keeper's job. A write-time guard judges only what the write adds (`test_seam_guard`).
- **Mechanism first, then backfill, then the gate.** Otherwise the new gate goes red on legacy state and trains everyone to route around it.
- **Prefer removing a gate to adding one.** A gate that has never caught a real problem, or only guards ceremony (e.g. a baseline measured against live product code), is cost with no net.

The 2026-09-23 audit ranked the walls; the fixes landed as mechanisms:

| Wall | Mechanism now |
|---|---|
| branch-tree pointers left `on_going` for months | `task_branch` start/integrate/cleanup write the transitions; healer proves rebased branches via `Noc-Branch` trailers; net: `check_stale_branch_pointers` |
| engineer slices landing unmeasured; guard hooks never registered | `task_branch integrate` refuses `slice_unscored`; nets: `check_engineer_slice_scored`, `check_guard_hooks_registered` (`dispatch-token-log.md`) |
| follow-up branch read as an unapproved ship-consent project | `task_branch start project=` / inherited from `parent` |
| outline corpus baseline bumped by every UI change (a gate that guarded ceremony) | frozen vendored corpus; the baseline moves only when the outliner changes |
| `check_framework_deps` red after scaffold/absorb; its fix wrote `"*"` | `scaffold_product` runs the fix; ranges come from seed's own package.json |

In flight from that audit: the `primary_write_guard` Bash leg (predict only exact targets, measure primary dirt afterwards), `test_seam_guard` scoping (judge added lines; share the predicate with a Bash leg), and three integrate-time mechanisms in `task_branch` (migration renumber, a time-boxed merged-tip check that refuses only on a new measured red, KB counts regenerated at integrate). Proposal pending an owner decision: moving append-only ops ledgers off the `dev` code line (23% of dev commits are ledger-only).

## Measured walls (2026-11-05 alignment audit)

Measured over 943 session transcripts (tool results only, one count per tool call), not predicted. Inventory totals (156 gates, incl. the 7 gates landed by `feat/access-tiers-gate`): 12 wall · 35 real-drift catch · 41 never-fires in commit flow · 7 new (unmeasured) · 59 unmeasured (high/critical keepers that run in the validate/CI sweep and emit no per-run event yet, `NOC-REMEDIATE[gate-telemetry]`) · 2 new (shadow). No gate has a *measured* effective-FP rate yet: that telemetry starts now, so none was demoted on evidence and none removed (never-fires is expected for a backstop; removal needs a class-elimination measure, not silence). Route-auth gates were re-judged at the predicate level (inventory `api_review`): `check_auth_boundary_false_green` stays WARNING in shadow (2 findings, 2 true positives, 0 effective FP; promote after >=5 findings over >=7 days with 0 effective FP); `check_auth_dep_anti_pattern` and `check_standard_routers_audit` are functional-wiring gates, deliberately not tier-aware (one gate per property: `check_access_tier_routes` owns "declares a tier"); `check_no_authenticated_grant_on_content_tables` is superseded by `check_access_tier_tables` (retire after an alias period, `NOC-REMEDIATE[gate-retire]`).

| Wall (firings / sessions) | Status |
|---|---|
| `guard:primary-write` (134 / 43) | deferred: `NOC-REMEDIATE[gate-wall]` auto-isolation by injection at dispatch |
| `check_migration_guard_has_probe` (85 / 22) | **fixed**: `scaffold_migration` returns `guard_probe_stubs` |
| `guard:heavy-run` (72 / 22) | deferred: pre-filled admitted command in the start brief / test-engineer template |
| `check_migration_number_refs_in_tests` (48 / 21) | **fixed**: `scaffold_migration` returns `reference_in_tests` |
| `check_eight_way_sync` (46 / 24) | deferred: propagate-on-write across the 8 surfaces |
| `guard:executor-dispatch` (44 / 22) | deferred: dispatch template pre-fills `worktree_path` |
| `guard:test-seams` (18 / 9) | kept: write-time judge of added lines; no construction possible (`none (reason)`) |
| `verify_kb_sync` (15 / 14), `check_not_configured_carries_marker` (13), `check_mutation_invalidate_only` (12), `check_silent_refusal` (12), `check_upload_route_body_override` (10) | deferred, each with a destination in the inventory `remediation` field |

## How to apply (the authoring checklist)

When a rule/standard is worth enforcing:
0. **Research first, cite sources.** Read the primary/reliable sources on how specialists do it; check the repo for an existing mechanism; if a standard tool competes with an in-repo one, measure (comparison record). The gate's `source` field cites what you read.
1. Write the **gate** (keeper detector, `scaffold_keeper`) — scan ALL artifacts, hard-block, name the exact fix in the message.
2. Write the **mechanism** (construction leg, FIRST in practice) in the producing code path — auto-fill/derive/normalize/write-both; refuse (no silent-null) when it can't.
3. **Backfill** existing artifacts to comply (the gate gates legacy too).
4. Ship the **regression test** for the gate (the detector-has-test gate requires it).
5. Sync the rule across surfaces the SAME commit (`KB § PATTERNS/common/eight-way-sync.md`): CLAUDE.md §1 one-liner + this/the relevant KB pattern + memory.
6. Prove the loop: gate fires on the pre-fix state → mechanism+backfill → gate passes.
7. **Declare the triad**: `--gate-alignment declare` (mechanism, owner, source, placement `warn` = shadow) + a decision-matrix row; telemetry is automatic via the cli wrapper. Re-run `--gate-alignment walls` after a release to re-measure.

Composes with [[drift-fix-on-contact]] · [[methodology-execution-discipline]] · `KB § PATTERNS/common/bypass-rationalization-anti-patterns.md` · `KB § PATTERNS/common/eight-way-sync.md` · `KB § PATTERNS/architect/branch-tree-tracking.md`.

**Visibility layer (2026-10-06).** A gate's refusals are made visible — toast, pane, friction ledger — by the harness mod, which observes the `[noc-guard:<name>]` marker and never decides. A gate must never move INTO a mod: a mod can be toggled off per user. → `KB § PATTERNS/common/harness-mods.md`
