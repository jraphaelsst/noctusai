---
name: noc-iterate
description: Use to run an agent's eval REFINEMENT loop in the agents product — triggers "refine the agent", "run the eval loop", "iterate on the evals", "fix the failing evals", "get agente-base / sdr-base / Julia to target", "refinement round", "eval failed, fix the prompt", "rodada de refino", "loop de avaliação", "refinar o agente", "por que não melhorou". One loop under the eval-loop gate: round (whole-suite run with loop_id) → split each failure harness vs target → council → ONE fix on the prompt content → next round, until the gate stops it (95% target, 2 rounds without improvement, US$ 5 cap, max rounds from config).
version: 1.0.0
---

# noc-iterate — error → fix on the prompt → re-measure, under the gate

A plain "Run" only **measures**. Refinement is the loop below; without it nobody acts on a failure (the 2026-11-12 slip:
the owner's first runs on `agente-base`/`sdr-base` had no `loop_id`, no loop existed, nothing was fixed). Owner spec
2026-11-09, corrected 2026-11-12: target **95%**, floor **80%** (`publicacao_limiar`), budget cap **US$ 5** per loop,
max rounds from the **loop config** (`rodadas_max`, owner-editable; the loop stops there), stop after **2 rounds
without improvement**, every non-improving round is an **overcall** with its cost, never re-run an unchanged hash.
Target, cap and max rounds are the platform loop config, frozen on each loop at start; never hard-code them.
Gate: `products/agents/docs/eval-loop-gate-contract.md` (G1–G7). Process owner: agent `agent-creator` §3.

## The loop

0. **Scope.** One loop per `(agent, suite)`. Each layer runs **its own cases only** (a child never runs its ancestors'
   cases). Template order: `agente-base` to the target first, then `sdr-base`, then the child (Julia). A child's loop waits
   until its ancestors are validated (chain gate: prontidão "base validada").
1. **Open the loop** — Studio Evals → "Iniciar loop de refinamento", or `POST /api/studio/agents/{key}/evals/loops`
   `{suite, rodadas_planejadas?, orcamento_usd?}` (platform admin / `studio:evals-run` token). Omitted → the loop config
   (`rodadas_max`, the US$ 5 cap); never above it. Checkpoints at 5/10/15. A loop that already exists → continue it, never open a second.
2. **Round = one whole-suite run with `loop_id`** (`POST …/evals/runs {version_id, loop_id}`; mechanism suite:
   `…/draft/mecanismo-runs?loop_id=`). No `case_ids`, no `repetir_falhas_de`, no `modelo_geracao` inside a loop.
   Wait for the run to close; read `LoopOut.serie[-1]` (score, `falhas`, `melhorou`, `overcall`) and each failing
   result's `saida` + `notas_juiz` + `veredito`.
3. **Split every failure: harness/world vs target** — before touching the prompt.
   - *Harness*: the eval setup lied (raw placeholder `erro`, judged an intermediate step / a narrated tool call, a
     world fixture contradicting the case, a judge criterion the case never stated, a timeout). Fix the HARNESS on a
     branch (code, red-first), never by bending the prompt to it. A harness fix changes no content hash, so the loop's
     next round is refused (G6) until content also changes or the fix ships — that is correct: re-measure after deploy.
   - *Target*: the agent really did the wrong thing. Only these go to step 4.
   - *Judge noise* (criterion over-read): re-read the case's `criterios`; if the case is wrong, fix the CASE
     (`noctus.agents.content kind=evals_comportamento`, dry-run first) and say so — a case edit is a variable too.
4. **Council before the refine** — `noctus.dev.council_ledger action=open_session subject_kind=eval_run
   subject_ref=<run id> stage=iterate`; seats record objections (five lenses), the chair reads `blind_view` only and
   `record_verdict`s by `anon_label`. Councils are Claude Code subagents, never API calls (owner, 2026-11-10).
   `mode=subagents` only when seats really ran as independent subagents, else `mode=single_chat`.
5. **ONE variable per round.** Pick the single highest-value target fix (critical cases first; the fix that serves
   the most failing cases without touching passing ones). Write it on the agent's OWN layer through
   `noctus.agents.content action=set` (dry-run → read the diff → `confirm=True`). Prose sections with the parent's
   `chave` APPEND; single values REPLACE (say "override" in the report). Payloads live outside git
   (`~/.noctusai/private/…`) — platform prompts are IP.
6. **Next round** (step 2). The gate decides, not you:
   G3 target (95%) → `concluido`; G7 budget → `parado` (owner decides); G4 2 rounds without improvement → `parado` + owner
   notified mid-flight with the series, what changed and the failing cases; max rounds (config) exhausted → `concluido`.
   On a G4 stop: do not open a new loop to dodge it — report and ask the owner.
7. **Close** — `council_ledger action=record_event` with the round's score change for every session opened; append
   each finding to `agent-creator` §5 in the same session; report to the owner: version, score series, overcalls +
   cost, fixes per round (harness vs target), overrides, doubts, spend. Publishing stays the owner's act.

## Hard rules

- A failure is never "noted": it is fixed (harness on a branch, target on the layer, case via the content tool) or
  deferred to a named destination.
- Never re-run to "see if it passes" — an unchanged hash with failing cases is refused (G6) by design.
- Never edit a parent's content to make a child pass; fix the layer that owns the behaviour (BASE = conversation +
  safety + honesty + atendimento + handoff/LGPD; SDR = qualification, offers, booking, scoring/follow-up).
- Template cases carry no business: generic placeholders ("Opção A", a free slot); no real customer data (LGPD).

## Depth

`products/agents/docs/eval-loop-gate-contract.md` · `.claude/agents/agent-creator.md` §2–§5 ·
`project-history/roadmaps/agent-templates-2026-11.md` · `KB § PATTERNS/common/council.md` · skill `noc-new-agent`.
