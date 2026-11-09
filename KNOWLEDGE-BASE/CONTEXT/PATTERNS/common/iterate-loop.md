# The iterate loop — create, evaluate, refine, redo

> **Rule.** Something we want to be good (an agent, a skill, a tool, a process) is improved in **rounds** on evidence: build v_n, evaluate the WHOLE set on v_n, split harness defects from target defects, refine one thing, redo. The owner decides when it is good enough. The loop refines itself as it runs. Procedure: skill `noc-iterate`. Record: `noctus.dev.method_trial` (same ledger as `method-trials.md`).

Born 2026-11-08. Owner: *"doc esse processo de criar → refinar → refazer → refinar → refazer... quero isso tipo numa skill … fiz isso pra criar e melhorar o processo de criação de agentes, na prática, e funcionou legal. quero poder repetir pra criar coisas novas e melhorá-las com o tempo."* The sources were Julia's build (v1 → v3, content iterations, the eval-improve loop) and the owner's batch-evaluation and self-improvement loops.

---

## 1 · Two shapes

| Shape | What repeats | Example | What gets refined |
|---|---|---|---|
| **repeat** | the same evaluation set on a new version of ONE target | Julia's eval loop: run the suite, diagnose, patch content through the API, run again | the target |
| **sequence** | one method applied to N items, one item per round | skill-scout vetting one public skill per round | the method (and the item's own outcome) |

A loop can nest both: refining the agent creator is a *sequence* over agents (Julia, media-analyst, …) in which each agent is its own *repeat* loop.

## 2 · Lessons that shaped the steps (from Julia)

- **Wait for the whole batch.** Reading results while the run is still going biased diagnosis toward the first failures.
- **World defects first.** In Julia's iteration 1 (run `1ff82dc7`, 0.947, 17/21), two of the four failures were in the simulated world, not in Julia: string values in criteria, and a "qualified" world without identification. Fixing the prompt for them would have been a false green.
- **Consistency is per (case, content hash).** A pass on an older hash says nothing about the current one. Stable cases are sampled less, never retired, because a later fix can break them.
- **Deciding "consistent" too early is the costly error** (owner: "péssimo"). The loop proposes a stop, and the owner decides.
- **Content is data.** Agent refinements go through the Studio API as DB writes (dry-run, then confirm), never into code or files.

## 3 · The council step

Before a non-trivial refine, five lenses argue the proposed change and one chairman line decides (decision · biggest risk · first step). Source: the LLM-Council analysis (media report v03, 2026-11-08) and the Stanford sycophancy study (Cheng et al., *Science* 2026). Two limits are stated each time it runs:
- in a single session it is ONE model in ONE context playing five roles, so it widens angles but is not independent judgement;
- independence needs separate calls or different models, which is what the multi-judge eval study (owner decision c, 2026-11-08) will measure.

## 4 · Cost per round

Record per round what the evaluation costs: model calls and US$ (eval runs), wall-clock, and owner time at the checkpoint. A round that adds cost without new signal is the cue to propose a stop or change the evaluation set.

## 5 · Runs

| Date | Target | Shape | Rounds | Verdict | Notes |
|---|---|---|---|---|---|
| 2026-11-08 | `skill-scout` (vetting UI UX Pro Max, then marketing skills) | sequence | in progress | — | first run; also refines this loop |

## Composes with

`method-trials.md` (the ledger and verdict routing) · `learning-posture-family-index.md` · `methodology-codification-pipeline.md` · `KB § GUIDES/agent-creation.md` (the agent recipe the loop drives) · skill `noc-learn-refine`.
