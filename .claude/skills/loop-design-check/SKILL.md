---
name: loop-design-check
description: Use before handing a repeating task to an agent loop, or when reviewing an existing one — triggers "design a loop", "review this loop", "loop that fixes tests", "scheduled agent routine", "agent runs overnight", "will this loop run away", "steward loop design", "desenhar um loop", "revisar loop do agente". Gates whether the loop should exist, forces a machine-decidable goal with boundaries, an independent judge and damping, and checks five failure modes (spinning, self-grading, test deletion, mid-run clarification, stale docs).
license: MIT (see LICENSE; vendored, adapted)
metadata:
  version: "1.0.0"
  origin: "github.com/affaan-m/ECC/tree/4adeee6732a12d1540f49a4d50a38ce8c97f9a53/skills/loop-design-check"
---

<!-- vendored: github.com/affaan-m/ECC@4adeee6732a12d1540f49a4d50a38ce8c97f9a53 (skills/loop-design-check/SKILL.md) · MIT · adapted 2026-11-25 -->

# loop-design-check — write the goal a machine can reconcile, then review it before it runs

A model has no built-in steering toward a goal across turns; a loop supplies the feedback. The machine grinds toward the **literal** goal; whether the goal is right, and when to stop, stays with a human. A loop only rewards a goal someone already thought through.

## Action 1 — write a loop

0. **Subtract first (any miss = do not build it):** the task repeats at least weekly · verification is automatable · the budget can take it · the agent has tools that run and show the result. A repo without reconciliation baselines, tests and lint guards only has its errors amplified by a loop.
1. **Machine-decidable goal.** Done-criterion judged yes/no by one command; **plus boundaries** ("must NOT delete or weaken tests, lower coverage, touch X") — a done-criterion without boundaries licenses cheating; **plus** a retry cap N and an escalate-to-human exit. Prefer reconciliation against an external fact (golden sample, upstream total, diff < threshold) over assertions the agent can loosen. Self-check: could someone outside the domain run one command and say whether it is done?
2. **Loop type.** Clear "done" test → servo (stops at goal). Keep a state forever → regulator (acts only on change). Watch until a condition → regulator with an exit. Must run on time → wrap in a schedule.
3. **Skeleton.** Maintenance: read a doc/queue on a timer, dispatch only on change; human writes the problem column, the loop writes results, state advances one way, the script's exit code is final, only a human flips "done". Greenfield: plan / build / judge — the **judge is independent of build** (never grades its own work), deterministic (tests, diff, type check), and build may not edit the acceptance conditions. Three failed retries → human.
4. **Damping.** Retry cap, hard stop, human on the last switch. Negative feedback without damping oscillates and burns budget.
5. **Land in stages:** run once by hand (forces you to state how the judge decides) → harden as a skill/subagents → only then schedule it.

## Action 2 — review a loop (any hit = send it back)

| # | Failure | Question | Antibody |
|---|---|---|---|
| 1 | Platitude goal spins | Can the exit be judged yes/no by a machine? | decidable result condition |
| 2 | "Looks ok" verification | Is the judge the defendant? | independent judge + exit-code rules |
| 3 | Only "tests pass" gates — agent deletes the tests | Is there a boundary besides the done-criterion? | done-criterion AND boundary |
| 4 | Counts on the agent asking mid-run — it will not, it finishes the wrong answer | Any clarify-at-runtime point? | front-load every clarification before launch |
| 5 | Stale docs/memory amplified by speed | Who keeps what the loop reads fresh? | owner + periodic lint |

Red lines (violating any = not allowed to run unattended): the human keeps acceptance; anything you cannot afford to get wrong (merge, publish, move money, deploy) is not delegated; a loop that rewrites its own rules needs **stricter** review before the action, not after.

## Guardrails

- House law wins: never `--no-verify`, never work on the shared `dev`, never auto-merge or auto-deploy from a loop; releases stay with the release steward (`noc-steward`, `noc-ship`).
- This skill covers goal and runaway prevention only; wiring of a specific loop is the owning skill's job (`noc-steward`, `noc-iterate` for the agent eval loop, `noc-daily-ops`).

## Depth

`KB § PATTERNS/common/methodology-execution-discipline.md` (verdict-channel integrity: the judge's verdict must belong to what it judges) · `KB § PATTERNS/common/gate-methodology-sync.md` · evals: `evals.md`.
