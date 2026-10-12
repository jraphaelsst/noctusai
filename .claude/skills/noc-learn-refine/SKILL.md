---
name: noc-learn-refine
description: Use whenever the owner wants learning and refinement to happen WHILE the work happens — triggers "learn during this", "learn while building", "learn as we go", "refine as we go", "auto-improve while you do it", "let's learn from this run", "evaluate this method", "we're testing this approach", "treat this as an experiment", "measure if this works", "improve the skill/tool while using it", or any task the owner frames as a learning round (e.g. the first run of a new process, seed, skill or tool). Treat the method in use as UNTRUSTED-UNDER-EVALUATION — state a hypothesis + metrics up front, log observations as they happen, refine mid-flight, close with an evidence-backed verdict.
version: 1.0.0
---

# noc-learn-refine — auto-improvement consciousness

**Posture.** *"I'm using a method I can't fully trust yet. I will measure how it behaves — effectiveness, precision, cost, friction — and refine it with what I find, while I work, not after."* The method can be a skill, a KB pattern, an MCP tool, a seed organ, a code pattern, a dispatch shape, or this skill itself.

Every trial lands in the shared auto-improvement ledger through ONE tool, `noctus.dev.method_trial`, so the next agent inherits the evidence, not a vibe.

## Workflow

1. **Name what's on trial — before the first action.** List each method you'll rely on that is new, recently changed, or the owner called untrusted. For each, `noctus.dev.method_trial action=open slug=<kebab> target=<skill|tool|KB path|code area> hypothesis="<what it should achieve, falsifiable>" metrics=[{name, how, target}]`. Pick 2–4 metrics you can actually observe: rework count, gate fires, wall-clock vs estimate, defects found later, precision of a tool's output (hits/false hits), owner corrections, tokens. A metric you can't measure is written down as such, never guessed.
2. **Check what the past already says — ONE call.** `noctus.dev.method_trial action=status open_only=false` + `noctus.dev.auto_improvement_query target=<target>`. A prior verdict on the same target is the baseline; compose with it, don't restart.
3. **Observe in the moment.** Each friction, surprise, failure, success or measurement → `action=observe slug=… signal=<measure|friction|surprise|failure|success|note> text=… metric=… value=… evidence=<path|commit|command output>` right when it happens. Evidence or it didn't happen. Route the content too, don't just count it:
   - craft lesson about an organ/component → `noctus.dev.organ_knowledge_append`;
   - project-scoped lesson → `noctus.dev.findings`;
   - process drift or improvement for the methodology → `noctus.dev.auto_improvement_log`.
4. **Refine mid-flight.** When observations contradict the hypothesis, fix the method NOW if the fix is in-scope and low-risk (edit the skill/KB/tool/code in the same branch) and observe again; that's the auto-improvement-at-phase-close rule applied continuously (`KB § PATTERNS/common/proposals-and-improvements.md`). Out-of-scope or risky → name the destination (`NOC-REMEDIATE[...]` or a roadmap open question), never a silent defer.
5. **Checkpoint at every phase/slice boundary.** `action=status slug=…` — compare metrics against targets; tell the owner in one short block what's working, what isn't, what you changed.
6. **Verdict with evidence.** `action=verdict slug=… verdict=<adopt|refine|discard|extend> reasoning="<which observations decided it>" changes=[paths/commits]`. Follow the returned `next_steps`:
   - **adopt** → `noctus.dev.codify_log` stage s3 for the target; a keeper (s4) only after N≥5 confirming trials (`KB § PATTERNS/common/methodology-codification-pipeline.md`).
   - **refine** → the edits are already in; open the follow-up trial on the refined version.
   - **discard** → remove or rewrite the target and record why in its KB home.
   - **extend** → open a follow-up trial with the widened hypothesis.
7. **Report loudly at wrap-up.** `action=report` → in the final reply: trials opened, key numbers, verdicts, what changed (paths), trials still open and why. Open trials are carried forward by name; none silently dropped.

## Guardrails
- ⚠️ **No self-grading without evidence.** "Worked well" without an observation row is not a verdict. Numbers and pointers over adjectives.
- ⚠️ **Don't codify early.** One good run is a hypothesis, not a rule; s4 keepers need N≥5 varied confirmations.
- ⚠️ **Don't let trials rot.** `status` flags stale trials (open >14 days, nothing observed in 7); close or carry them explicitly.
- **This skill composes, it doesn't duplicate.** One ledger (auto-improvement), existing sinks for content (organ knowledge, findings). Never start a parallel log or a scratch file as the record.
- **The skill is on trial too.** When it's the method you doubt, open a trial on `noc-learn-refine` itself and refine this file with the verdict.
- Owner corrections are the strongest signal: log each as `signal=friction` with the owner's words in `text`.

## Depth
`KB § PATTERNS/common/method-trials.md` · `KB § PATTERNS/common/learning-posture-family-index.md` · `KB § PATTERNS/common/methodology-codification-pipeline.md` · `KB § PATTERNS/common/build-learn-cache-mindset.md`.
