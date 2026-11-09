---
name: noc-iterate
description: Use when the owner wants something built and then improved in rounds until it is good — triggers "iterate on this", "create, refine, redo", "loop until it's consistent", "run the improvement loop", "refine it with each one", "one at a time and refine the method", "use the iterate process", "loop the evals", "melhorar em ciclos", "refinar e refazer". Build v1 → evaluate in a batch → split harness defects from target defects → council → smallest refine → redo; the owner says when it is good enough. The loop also refines itself.
version: 0.1.0
---

# noc-iterate — create → evaluate → refine → redo

The outer loop for making a thing good on evidence: an agent, a skill, an agent definition, a tool, a process. `noc-learn-refine` judges a method while you use it; this skill drives the ROUNDS around it. Both write to the same trial ledger (`noctus.dev.method_trial`). Depth: `KB § PATTERNS/common/iterate-loop.md`.

## Workflow

0. **Frame the loop (once).** Name the **target** (path, DB key or URL) and its **shape**:
   - **repeat**: the same target is evaluated again each round (Julia's eval loop);
   - **sequence**: a method is applied to N items, ONE per round, and each item refines the method (skill-scout vetting one skill at a time).

   Write the **evaluation set** before building: cases, criteria, or the items list. Open TWO trials: `method_trial action=open slug=<target-slug>` (hypothesis + 2–4 observable metrics) and `slug=noc-iterate-<target-slug>` on this skill. Read past verdicts first (`method_trial action=status open_only=false` + `auto_improvement_query target=<target>`).
1. **Build or redo v_n.** Round 1 builds from the best existing source (codebase first, then the reference exemplar, e.g. Julia for agents). Later rounds change ONLY what the last diagnosis named. Record the version identity: a content hash, a commit or a DB version id.
2. **Evaluate in a batch, on v_n.** Run the WHOLE evaluation set against v_n, and wait for EVERY result before you read any of them. Partial reads bias the diagnosis. Sequence shape: process the round's ONE item fully with the current method.
3. **Diagnose: split the defect.** Classify each failure before touching anything:
   - **harness or world defect**: the eval, fixture, simulated data, tool or environment is wrong. Fix it there, never in the target.
   - **target defect**: the target behaved wrong. That one feeds the refine step.
   - **method defect** (sequence shape): the procedure missed, slowed or misled. That one refines the method file.
   Log each finding with `method_trial action=observe` and its evidence.
4. **Council before you refine.** For any non-trivial change, run five lenses on the proposed fix: contrarian (what breaks), first principles (is the premise right), expansionist (what bigger win is missed), outsider (would a newcomer understand it), executor (what exactly changes now). Then one chairman line: decision, biggest risk, first step. In one session this is the single-chat version; the lenses share one model and one context, so say so when you report it.
5. **Refine: the smallest change that fixes the diagnosed defect.** Edit the target (and in sequence shape, the method file). Never lower the bar or delete a failing case to get green. A case is "stable" only per (case, content hash): any content change resets stability. A stable case is SAMPLED less, never retired.
6. **Checkpoint with the owner.** Send one short block per round: version, score or outcome, what failed and why (harness vs target), what changed, what's next. **The owner decides when it is good enough.** Never declare consistency on your own.
7. **Refine this loop.** If the loop itself caused friction (a step was skipped, misordered or useless), edit THIS file in the same branch and log `observe` on `noc-iterate-<target-slug>`.
8. **Close.** `method_trial action=verdict` on both trials, then route what was learned: target-specific lessons → the target's own home (agent KB, skill depth doc, findings ledger); method lessons → the method's KB; loop lessons → `KB § PATTERNS/common/iterate-loop.md`. `noctus.dev.codify_log` only after N≥5 varied confirmations.

## Guardrails
- **The owner owns "done".** You propose a stop; they decide it.
- **One variable per round.** Two simultaneous changes make the next result unreadable.
- **Evidence or it didn't happen**: every observation carries a path, run id, commit or output.
- **Never fix the world inside the target.** A prompt patch that compensates for a broken fixture is a false green.
- **Cost is a metric.** Record tokens, US$ or wall-clock per round when the evaluation calls a model, and stop early when a round adds cost without signal.
- **Writes follow their own gates**: DB content through its API with dry-run first, code on a self-branch, publish and send only with an owner yes.
- **Single-session jobs stay inline.** When the owner asked for one screen, run each round here and empersonate specialists from `.claude/agents/<name>.md` instead of dispatching them.

## Depth
`KB § PATTERNS/common/iterate-loop.md` (the two shapes, worked examples, what a round costs) · `KB § PATTERNS/common/method-trials.md` (the ledger) · skill `noc-learn-refine` (judging a method inside one round).
