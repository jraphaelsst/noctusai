---
description: Evaluate whether a rule / request / methodology surface should be codified (discipline → mechanical gate), decide honestly, and apply where warranted. Drains the methodology-codification-pipeline proactively.
---

# /codify — discipline → mechanism, evaluated honestly

You are running the **codify** protocol. The user invoked `/codify $ARGUMENTS`.

**Premise (do not skip):** codifiable discipline → a mechanical gate is cheaper (a keeper costs ~0 agent tokens/turn + removes the "did the agent remember?" failure mode) and more reliable. This is **Stage 4** of `KB § PATTERNS/common/methodology-codification-pipeline.md`. But **code does not replace prose** (code = WHAT/HOW the gate; prose = WHY/history/exceptions/when-to-override — keep both) and **not all discipline is codifiable** (judgment rules stay Stage 3). Your job is to find the *real* opportunities and say **honestly whether to apply or not**.

**This command's own *detection* half is now mechanical.** `check_codification_debt` (a keeper in the compliance gate) reads every `NOC-REMEDIATE[codify]` marker each run, so a deferred codification can never go silent in prose. `/codify` is the **DECISION layer over that always-on detector**: the keeper *surfaces* the backlog; you *judge* it (apply / defer / stays-prose). When you defer, you feed the detector — you leave a `[codify]` marker (step 5), never bury the deferral in free prose.

## Target resolution
- `/codify <rule or request>` → evaluate THAT specific rule/request.
- `/codify` (no arg) or `/codify sweep` → **sweep `CLAUDE.md` §1 universal rules + the auto-memory `feedback_*`/`project_*` entries** for candidates. **Do NOT sweep KB by default** — KB is reference-depth, not behavioral discipline; only open a specific `KB § PATTERNS/<x>.md` when a candidate's rule lives there.

## The 3 codification criteria (ALL must hold — §3 of the pipeline)
1. **Deterministic** — reduces to a question a tree-walking script answers WITHOUT judgment (a file / AST / grep predicate). *Test:* would a junior + a script agree on whether it fires?
2. **Recurrence N≥3** — has bitten ≥3 times (cite evidence). N=1–2 ⇒ **defer** (record as a candidate, don't build the keeper). *Exception:* a pure **scan/query tool** (advisory, non-gating) doesn't need N≥3 — recurrence gates *enforcement*, not *querying*.
3. **Clear remediation** — an obvious "do X to fix" once flagged.

## Exclude (legitimately Stage-3-forever — §5 of the pipeline)
Judgment-dependent ("no quick fixes", "accept-vs-refactor", "right seam?", "real-regression-vs-fixture"), context-dependent ("parallelize vs serial"), aesthetic, or methodology-in-pilot (N<5 varied instances). For these the **honest answer is "do NOT codify — judgment is the rule"**. Say so; that IS a valid `/codify` outcome.

## Protocol
1. **Identify** the candidate rule(s) in the target.
2. **Read the standing backlog first** — run `noctus.dev.scan_remediation_markers` (or read the `check_codification_debt` findings from the last compliance run) to see the already-surfaced `NOC-REMEDIATE[codify]` deferrals; those are pre-vetted candidates that may now be ripe.
3. **Verify it isn't already codified** — grep the 50+ `check_*` in `mcp/noctusai/tools/noctus/dev/compliance.py` + the `noctus.dev.scan_*` tools. (Explore-audits over-report; always verify against the actual keeper corpus.)
4. **Classify each** against the criteria → ripeness **HIGH** (all 3, easy predicate) / **MED** (criteria met, predicate has edges) / **LOW/DEFER** (N<3, or judgment-edged) / **STAYS-PROSE** (judgment).
5. **Decide + state it** — for each: APPLY-NOW / DEFER (with the missing criterion) / STAYS-PROSE (with why). This explicit "whether we should or not" is the deliverable the user asked for.
6. **Apply the ripe ones** (s1→s4): build the `check_*` keeper (deterministic gate) OR a `noctus.dev.scan_*` tool (advisory query) — use `noctus.dev.scaffold_keeper` / `scaffold_mcp_tool`; add a **colocated regression test** (`check_detector_has_regression_test` requires it); add to the compliance baseline with cited triage if it surfaces pre-existing debt; **eight-way sync** (KB pattern + CLAUDE.md/topical pointer + memory). **Keep the prose** — trim it to rationale + a pointer to the gate, never delete it. **When a built keeper retires a `[codify]` marker, delete that marker** (it has graduated; the doc's codification footer flips to the keeper name).
7. **Defer the not-yet-ripe ones with a marker, NOT prose** — leave a structured `NOC-REMEDIATE[codify]: <rule> — <why deferred> — <YYYY-MM-DD>` in the rule's **durable** KB doc (never `projects/` — it gets archived) so `check_codification_debt` tracks it until it ripens. Burying the deferral in free prose is the gap this gate closes.
8. **Report** — the candidate table (rule · predicate · ripeness · decision), what you applied, what you deferred-with-a-marker, and what you deliberately left as prose (with reason). If nothing is ripe, say "pipeline is drained here — nothing to codify; here's why each stays prose / deferred." That's a healthy result, not a failure.

## Guardrails
- Never force a judgment rule into a keeper (false precision does harm).
- Never delete the rationale prose when codifying — the keeper enforces, the doc explains.
- A deferral is a `[codify]` **marker**, not a sentence — "we should codify X someday" written in prose is invisible to the gate and WILL be forgotten (the exact gap `check_codification_debt` closes).
- A keeper that would false-positive across the seed/products is NOT ripe — design the predicate carefully or defer.
- The compliance gate is **regression-semantics** (no NEW high/critical), not score==100 — a new keeper surfacing pre-existing debt goes in the baseline with cited triage, it doesn't break the gate. (`[codify]` markers are `warning`-severity — they surface without blocking.)

Reference: `KB § PATTERNS/common/methodology-codification-pipeline.md` · `projects/codification-backlog-drain/PROJECT.md` (the standing audit + waves).
