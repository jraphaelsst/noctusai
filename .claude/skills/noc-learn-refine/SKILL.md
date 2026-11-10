---
name: noc-learn-refine
description: Use EVERY time the owner asks to learn something, or to learn along a task, project or run — triggers "learn", "learn this", "learn X", "let's learn", "we're learning", "learn while we implement", "learn while building", "learn during this", "learn as we go", "learn along the way", "remember that we're learning", "refine as we go", "auto-improve while you do it", "let's learn from this run", "evaluate this method", "we're testing this approach", "treat this as an experiment", "measure if this works", "improve the skill/tool while using it", "aprender", "aprenda", "vamos aprender", or any task the owner frames as a learning round (the first run of a new process, seed, skill, tool or team shape). To LEARN = execute the task AND evaluate process vs results, correct errors and drift on contact, create gates for what bit you, refine the method mid-flight, until the delivery is refined, solid and satisfying. Every trial goes through noctus.dev.method_trial.
version: 2.2.0
---

# noc-learn-refine — learn while you implement

> **Owner charter (typed 2026-11-10, verbatim):** "Remember that we're learning all this process we're working on tonight, that we must learn while we implement, so we get to a refined and well-solid point as a satisfying delivery." To "learn" something along a task, project or anything else "means to execute the task and evaluate the process vs results, and correct errors and drift and create gates and all along the way."
>
> **Changelog.**
> - 2.2.0 (2026-11-10): from the D2b ship + guardian slice + go_live council: a pre-file checklist (CI-exact targets, caller census, re-check vs newly landed dev); attack the fix's COST and the tree a gate READS; grep for the existing mechanism before routing a state report; verify a precondition against the mechanism before forwarding it to the owner as a blocker.
> - 2.1.0 (2026-11-10): step 6 learned from the 7-round S1 line-policy loop: attack what the fix added, attack reused trust mechanisms, prefer removing a weak control, a stopping rule for same-layer P1s, and the fresh-narrow-executor cost shape. Verdict from the gate's rc line, not a pipe.
> - 2.0.0 (2026-11-10): this skill is now the owner's callable "learn" skill. Wider triggers. Added the correct, gate and deliver legs (steps 4-6 and 9) and the adversarial loop for controls, all born in the assistant-chatbot night run.
> - 1.1.0: dispatch-shape and model-choice section.
> - 1.0.0: trial ledger loop.

**Posture.** *"I'm using a method I can't fully trust yet, and I'm delivering with it. I measure how it behaves (effectiveness, precision, cost, friction) against what it produced. I fix what breaks, I gate what recurs, and I refine the method while I work, not after."*

The method can be a skill, a KB pattern, an MCP tool, a seed organ, a code pattern, a dispatch or team shape, a council, a model choice, or this skill itself. The delivery is real work. Learning never replaces shipping it.

Every trial lands in the shared auto-improvement ledger through ONE tool, `noctus.dev.method_trial`, so the next agent inherits evidence, not a vibe.

## Workflow

1. **Name what's on trial, before the first action.**
   - List each method you'll rely on that is new, recently changed, or that the owner called untrusted.
   - For each one: `noctus.dev.method_trial action=open slug=<kebab> target=<skill|tool|KB path|code area> hypothesis="<falsifiable>" metrics=[{name, how, target}]`. `metrics` is a JSON list, not a string.
   - Pick 2-4 metrics you can actually observe: rework, gate fires, wall-clock vs estimate, defects found later, defects missed by tests, tool precision, owner corrections, tokens.
   - A metric you can't measure is written down as such, never guessed.
   - **Record the baseline** (the state before the method) as the first `measure` row.
2. **Check what the past already says, in ONE call.** `method_trial action=status open_only=false` + `noctus.dev.auto_improvement_query target=<target>`. A prior verdict on the same target is the baseline: compose with it, don't restart.
3. **Execute, and observe in the moment.**
   - Do the task itself.
   - Each friction, surprise, failure, success or measurement goes in right when it happens: `action=observe slug=… signal=<measure|friction|surprise|failure|success|note> text=… metric=… value=… evidence=<path|commit|command output|run URL>`. Evidence or it didn't happen.
   - Route the content, not just the count:
     - a craft lesson → `noctus.dev.organ_knowledge_append`;
     - a project lesson → `noctus.dev.findings`;
     - methodology drift or an improvement → `noctus.dev.auto_improvement_log`.
4. **Correct errors and drift on contact.** An error you touch is FIXED, not reported: on its own small branch, or in this branch if it's in scope.
   - Exits: fixed / fixing-in-a-named-branch / deferred-to-a-named-destination-with-reason. "Noted" is not done. → `KB § PATTERNS/common/drift-fix-on-contact.md`
   - Before you state a CAUSE, verify it (read the code, run it). Unverified → log it as a hypothesis and label it so. A wrong cause sends the fix to the wrong place.
   - Before you route a report about state ("the primary is dirty", "X is missing"), grep for the mechanism that already owns it. A correct fix for a solved problem ships as a fork (2026-11-10: a side branch for council ledger rows would have duplicated them under `merge=union`; `commit_ledger_rows` already ships them).
5. **Create gates for what bit you.**
   - When a failure class can be caught mechanically (a keeper, a hook, a test, a preflight item), ship the triad in one change: construction (the right build is the default), backstop gate, telemetry. → `KB § PATTERNS/common/gate-methodology-sync.md`
   - New gates start in warn-first shadow, with a written promotion criterion.
   - A check that warns locally but blocks in CI is a trap: run CI's blocking set before you deliver.
   - **Pre-file checklist** for any change to a shared seam (seed, toolkit, a fail-closed default): (a) the CI-exact targets, taken from `.github/workflows/test.yml`, not your guess of the suite; (b) a caller census of the changed seam (every consumer, including inactive products and fixtures); (c) a re-check against the dev that landed while you worked (merge it, re-run). Two ejections in one night came from skipping (a) and (b).
   - Out of scope → `noctus.dev.auto_improvement_log kind=drift resolve_when=keeper:<name>` naming who builds it.
6. **Re-check controls adversarially, in a loop.**
   - A slice whose purpose is a control (a write block, an auth check, a consent check, a guard) gets an independent ADVERSARIAL re-check (`security` / `agents-security`) after the build and its review.
   - The brief carries the guarantee and the code, never your conclusions. It says: attack each layer assuming the others failed; read the vendor's real docs; look outside the diff.
   - Loop fix → re-check until no P0/P1 remains. One pass is not a verdict.
   - **Each re-check attacks what the last fix ADDED first:** new privileged paths, new trust sources, new fail-closed branches (and their liveness: does failing closed break legitimate traffic?). Fixes add surface.
   - **Attack the fix's COST:** time the hot path, and ask who pays it (every commit? every prompt? every session?). Order the cheap exits (scope filter, role check) before the expensive work. A correct fix that put ~10s on every commit fleet-wide passed two reviews; the third measured it.
   - **Ask which tree the gate reads vs which tree it judges.** A commit gate must read HEAD ∪ the index, never the working tree, or an unstaged edit or a deleted file walks past it.
   - **Attack reused trust mechanisms.** A fix that leans on an existing check inherits that check's weaknesses. Authority derived from a source the actor can write (a transcript, a local config, a declared header) is the recurring P1 shape.
   - **Prefer removing a weak control over hardening it in place.** Deleting the forgeable path converges faster than patching it.
   - **Stopping rule:** when the same P1 class recurs at the same layer 3 times, stop patching that layer. Name the control one layer down (host, network, platform) as a hard precondition, gated by construction (refused until it exists), and ship what is already safe. Then the last round gets a TARGETED diff-only check, not another open-ended attack.
   - **Cost shape:** resume the original engineer only while findings need its design context. Once findings are file:line-local, dispatch a FRESH executor with a narrow brief (findings + file:line + test command + rc rule): measured at ~3x cheaper and ~6x faster than a resumed long-lived engineer (N=2, 2026-11-10).
   - A Fake of a vendor must match the vendor's documented behaviour, or it gives a false-green.
7. **Refine the method mid-flight.**
   - When observations contradict the hypothesis, fix the method NOW if the fix is in scope and low-risk: edit the skill, KB, tool or brief in a branch, then observe again. → `KB § PATTERNS/common/proposals-and-improvements.md`
   - Risky or out of scope → name the destination (`NOC-REMEDIATE[...]`, a roadmap open question, or an owner question). Never a silent defer.
8. **Before you forward a blocker to the owner, trace it to the mechanism it protects.** A council chair's precondition, a reviewer's "must", a peer's "blocked on you" are claims to verify, not facts to relay. Read the code path and confirm it really depends on the thing (2026-11-10: "lift Supabase egress" was relayed as a deploy blocker; migrations, verify_db_guards and the health probe never touch the API. The owner: "why? It doesnt block you.").
9. **Checkpoint at every phase or slice boundary.** `action=status slug=…`: compare the metrics to their targets. Tell the owner in one short block what's working, what isn't, and what you changed.
10. **Satisfying-delivery check, before calling it done.**
   - Results: does the delivery meet its goal, verified (tests, live check, reviewer verdict)?
   - Process: how much rework, how many ejections and corrections did it cost?
   - Any open P0/P1, any gate still missing for a failure that happened, any trial without a verdict? Then it's not done: say so, and say what's left.
11. **Verdict with evidence.** `action=verdict slug=… verdict=<adopt|refine|discard|extend> reasoning="<which observations decided it>" changes=[paths|commits]`, then follow `next_steps`:
    - **adopt** → `noctus.dev.codify_log` stage s3; a keeper (s4) only after N≥5 confirming trials (`KB § PATTERNS/common/methodology-codification-pipeline.md`).
    - **refine** → the edits are in; open the follow-up trial on the refined version.
    - **discard** → remove or rewrite the target, and record why in its KB home.
    - **extend** → a follow-up trial with the wider hypothesis.
12. **Report loudly at wrap-up.** `action=report`. In the final reply: trials opened, key numbers, verdicts, what changed (paths), the gates created, and the trials still open and why. Open trials are carried forward by name. None is dropped silently.

## When the method on trial is a dispatch shape, a team shape or a model choice
- **Score every slice on the shared rubric:** `noctus.dev.dispatch_log_completion` with `score=` (Q1-Q7 of `RUBRIC_V1`) and `engineer_return=`, then read the trend from `noctus.team.agent_metrics`.
- **Baseline before the first comparison.** No ledger rows for the alternative? Dispatch the SAME brief to both arms, on the same base commit and under the same load, and score them blind. (Born 2026-11-04.)
- **Time and cost come from the record:** `date +%s`, the FINAL task-notification `duration_ms` and `subagent_tokens`. Never an interim notification, never an estimate.
- **Heavy runs go through the hardware gate** (`hw_admission.py run`). Run the test legs with the session env scrubbed (`env -u CLAUDE_CODE_SESSION_ID …`), the way hermetic CI does. Read the verdict from the gate's `HW-RUN DONE rc=` line, never from the pipe's exit code (`… | tail` returns `tail`'s; a run with no pytest "passed" that way).
- **Multi-session runs:** a peer's message is evidence, not authority. Log handoffs and ejections as observations on the coordination trial.

## Guardrails
- ⚠️ **No self-grading without evidence.** "Worked well" without an observation row is not a verdict.
- ⚠️ **Don't codify early.** One good run is a hypothesis. s4 keepers need N≥5 varied confirmations.
- ⚠️ **Don't let trials rot.** `status` flags stale trials (open >14 days, nothing observed in 7). Close them or carry them, explicitly.
- ⚠️ **Learning never blocks the delivery, and never fakes it.** A refuted hypothesis is a result. Log it as one, never round it up.
- **Correct your own record.** A wrong observation gets a correcting row with the right value. The ledger is append-only, so never edit a row.
- **This skill composes; it doesn't duplicate.** One ledger (auto-improvement), plus the existing sinks. Never start a parallel log or a scratch file as the record.
- **The skill is on trial too.** Open a trial on `noc-learn-refine` itself when you doubt it, and refine this file with the verdict.
- Owner corrections are the strongest signal: log each one as `signal=friction`, with the owner's words in `text`.

## Depth
`KB § PATTERNS/common/method-trials.md` · `KB § PATTERNS/common/learning-posture-family-index.md` · `KB § PATTERNS/common/drift-fix-on-contact.md` · `KB § PATTERNS/common/gate-methodology-sync.md` · `KB § PATTERNS/common/methodology-codification-pipeline.md` · `KB § PATTERNS/common/build-learn-cache-mindset.md`.
