# Method trials — evaluate a method while using it

> **Rule.** A method we can't fully trust yet (a new skill, KB pattern, MCP tool, seed organ, process, or code pattern) is used as a **trial**: hypothesis + metrics stated before work starts, observations logged as they happen with evidence, refinements applied mid-flight, and a verdict (`adopt · refine · discard · extend`) backed by those observations. Procedure: skill `noc-learn-refine`. Record: `noctus.dev.method_trial`.

Born 2026-10-12 (commerce seed run, decision D23). Owner: *"I'll use some methodology that I can't yet fully trust. I gotta evaluate its behaviour and mechanism and effectiveness and precision and all metrics involved, and optimize/refine with new learnings and findings I come across along the way … auto-improvement consciousness."*

---

## 1 · Why a trial, not just "lessons learned"

The learning-posture family (`learning-posture-family-index.md`) says *notice* friction; the knowledge-lifecycle family says what happens to what you noticed. Neither says how to **judge a method** you're betting on. Lessons logged at the end are biased toward what you remember; a trial forces the bet to be stated first, so the verdict can be wrong in a visible way.

## 2 · The record (auto-improvement ledger, extended — not a new ledger)

`noctus.dev.method_trial` writes to the same ledger as `auto_improvement_log` (orphan `origin/ledgers` branch, cache `.claude/cache/auto-improvement.sqlite`):

| Row kind | Written by | Carries |
|---|---|---|
| `trial` | `action=open` | target, hypothesis, metrics `[{name, how, target}]`, project; `source_ref=trial:<slug>` |
| `trial-obs` | `action=observe` | signal (`measure · friction · surprise · failure · success · note`), text, metric, value, evidence |
| `trial-verdict` | `action=verdict` | verdict, reasoning, changes, follow-up slug |

Observation and verdict rows are written `closed`, so the codification radar and open-item queries stay clean; `action=status` / `action=report` aggregate them. Extending the existing ledger (instead of spawning one) keeps the 3-leg mirror contract and lets `noc-contextualize` / `noc-wrap-up` find trials where they already look.

## 3 · Choosing metrics

Good trial metrics are cheap to observe during the work and tied to the hypothesis:

| Method under trial | Example metrics |
|---|---|
| a skill / procedure | steps skipped or reordered · owner corrections · rework count · wall-clock vs estimate |
| an MCP tool | precision (useful hits / results) · false positives · calls needed per answer · failures |
| a seed organ / vertical seed | consumer-side forks needed · seams missing · lines of market code vs seed code |
| a dispatch / orchestration shape | collisions · integration conflicts · tokens · parallel speed-up (`batch_speed_gain_*`) |
| a code pattern | defects found later · tests needed to pin it · readability complaints |

Unmeasurable → write "unmeasured" and say why; never estimate a number into the record.

## 4 · Verdict routing

`adopt` → `codify_log` s3 (KB/CLAUDE.md); an s4 keeper only after N≥5 varied confirming trials (`methodology-codification-pipeline.md` TEMP rule) · `refine` → edits land in the same branch, follow-up trial opened on the refined version · `discard` → the target is removed or rewritten and its KB home says why · `extend` → follow-up trial with a wider hypothesis.

## 5 · First trials (commerce seed run)

The commerce seed run (`project-history/roadmaps/commerce-seed-2026-10.md`) is the first systematic use: the vertical-seed method (`../architect/vertical-seed.md`), `noc-new-product` v2, the products-inside-products tools and this skill itself are each opened as trials in P2 and judged at the learning rounds (P8, P10).

## Composes with

`learning-posture-family-index.md` · `knowledge-lifecycle-family-index.md` · `methodology-codification-pipeline.md` · `scoped-auto-improvement.md` · `build-learn-cache-mindset.md` · `product-dev-learning-ground.md` · `methodology-execution-discipline.md`.
