# assistant-chatbot: project record (pilot clauses, decisions, revert order)

> Branch steward and outcome recorder: the tech-lead session that owns branch `feat/assistant-chatbot` (noctusai-22 at the time of writing). Written 2026-11-09 by the tech-lead under the owner's free pass; every interim value below is reversible and is reviewed on **2026-11-23**.

## 1 · Pilot clauses (this project only)

Council, decision rights and the product-* agents are **opt-in pilots**. This project opts in; no other project is bound by it.

**Council (D13) — full council at every stage, for this project only.** Guard rails:
- **Seat cap:** 7 seats + the chair per session. When a stage row lists more, take M seats first, then O seats by relevance to the subject, the lenses last; log dropped seats in `open_session` notes.
- **Token budget:** about 1.5M subagent tokens per session. The steward aborts a session that passes 2x that (record `abort` with the reason) and re-scopes the brief.
- **Minimal default for non-pilot runs:** only the M seats of the stage map, and only on a trigger (skill `noc-council`).
- **Kill/keep criterion (after the Assistant run):** keep full council only if accepted objections (chair disposition `accepted`) per 1M tokens beat a single-reviewer pass on one stage run both ways (same subject, one Opus reviewer, same brief); otherwise demote to the minimal default. `council_ledger action=report` supplies the numbers.
- **Outcome recorder:** the branch steward (the tech-lead session of this project) records outcomes (`vindicated|refuted|untested`) at wrap-up, post-deploy or on an incident; `product-analyst` may add rows.
- **Manual review checkpoint: 2026-11-23** (steward + owner): read the report, apply the kill/keep rule, retune the stage map.

**Decision rights (D32) — pilot scoped to `product-engineer`.** Active for `product-engineer` only. The other six executors (backend, frontend, devops, integrations, ai, test, tooling) keep the reference line, marked "pilot: inactive until the pilot review". Activation criterion for them: the 2026-11-23 review shows, over this project's slices, an audit false-block rate under 10 percent and at least one owner-visible decision caught pre-merge. Until then they do not log or classify.

**Advisor-write guard (D34):** shadow-warn now. Switch to enforce when 14 days pass, or 50 guard events accrue (whichever is later), with 0 false positives reviewed by the branch steward. The steward reads `.claude/cache/guard-events.ndjson` (`noctus.dev.gate_alignment action=walls`) at each checkpoint; a false positive resets the counter. The switch is `NOC_ADVISOR_WRITE_MODE=enforce` or the module constant, a one-line change.

## 2 · Decisions

| ID | What | Where decided | Authority |
|---|---|---|---|
| D13 | Full council at every stage of this project (pilot, capped; section 1) | owner decision log, 2026-11-09 | owner |
| D31 | The product catalog (`ativo`, `deploy_scope`) is owned by `product-manager` | `project_assistant_product.md` memory; agent `product-manager` | owner |
| D32 | Executors decide small things in scope under logged decision rights (pilot: `product-engineer` only) | same memory; `KB § PATTERNS/common/engineer-decision-rights.md` | owner |
| D33 | `product-*` advisors get council seats; council stage map extended | same memory; skill `noc-council` | owner |
| D34 | Advisor write-scope guard: spec/notes paths only (shadow, then enforce) | same memory; `advisor_write_guard.py` | owner |

Files that cite these ids point here (`project-history/assistant-chatbot/PROJECT.md` section 2). Research behind them: `project-history/assistant-chatbot/research/`.

## 2a · Browser-runner gate list (council 25e812af, decision `browser-ops-decision.md`)
No server-side browser is built until ALL of these hold:
- (a) The residual Instagram jobs the API cannot do are listed, with recurring demand.
- (b) A measured RSS spike under a cgroup `mem_limit`/`oom_score_adj` shows the runner fits on the VPS without risking WAHA. The source is the local container study.
- (c) A one-command kill switch exists (stop, wipe the volume, the vendor-side revoke steps listed for the owner), plus recorded-DOM fixtures, a Fake the Assistant builds against, and a defined acceptance run (account, action count, who watches).

## 3 · Revert order (each piece backs out independently)

1. **Council:** drop the "pilot" status: set the skill's `description` trigger back to manual only and stop calling `open_session`. Nothing else depends on it; ledger files under `project-history/council/` stay as history. The product-* seat lines in the product agents are inert without the skill.
2. **Decision rights:** remove the `Decisions:` rules from `product-engineer.md` section 7 and the pointer lines in the six executors, and stop the compliance-reviewer pre-merge audit. `noctus.dev.decision_log` and its ledger stay unused (no consumer).
3. **Product-* agents:** delete the four agent files and their canons; restore the owner of `product-working-scope.md` to architect (D31 undone). Council seat columns for PMg/PAr/PAn then drop from the stage map.
4. **`engineer-seed` alias:** a deprecated alias exists for one release (added by a parallel slice); removing `product-engineer` means restoring `engineer-seed.md` from git history.
Order of least to most coupling: 1, 2, 4, 3.
