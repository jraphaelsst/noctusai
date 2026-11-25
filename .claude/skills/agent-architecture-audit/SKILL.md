---
name: agent-architecture-audit
description: Use when an agent or LLM feature misbehaves and the failing layer is unknown, or before shipping an agent stack — triggers "the agent got worse", "works in the playground but not in our wrapper", "tool is flaky", "agent skipped the tool", "old topic leaks into new chat", "answer differs from what the user sees", "which layer is broken", "agente piorou", "auditar camadas do agente". Walks the 12 layers from system prompt to persistence, falsifies wrapper regression before blaming the model, and ranks findings with code-first fixes.
license: MIT (see LICENSE; vendored, adapted)
metadata:
  version: "1.0.0"
  origin: "github.com/affaan-m/ECC/tree/4adeee6732a12d1540f49a4d50a38ce8c97f9a53/skills/agent-architecture-audit"
---

<!-- vendored: github.com/affaan-m/ECC@4adeee6732a12d1540f49a4d50a38ce8c97f9a53 (skills/agent-architecture-audit/SKILL.md) · MIT · adapted 2026-11-25 (upstream metadata origin: oh-my-agent-check) -->

# agent-architecture-audit — which layer corrupted the answer?

The base model is usually right; the layers we wrap around it make it worse. Falsify the wrapper before blaming the model.

## The 12 layers (any can corrupt the answer)

| # | Layer | Typical fault |
|---|---|---|
| 1 | System prompt (incl. inherited base/scope layers) | conflicting instructions, bloat |
| 2 | Session history | stale context from earlier turns |
| 3 | Long-term memory | pollution across sessions, old topics in new chats |
| 4 | Distillation / summaries | compressed artifacts re-entering as facts |
| 5 | Active recall | redundant re-summary layers |
| 6 | Tool selection | wrong routing, a required tool skipped |
| 7 | Tool execution | claims a call it never made |
| 8 | Tool interpretation | output misread or ignored |
| 9 | Answer shaping | format corruption |
| 10 | Platform rendering / transport | channel mutates a valid answer |
| 11 | Hidden repair loops | silent retry/fallback LLM pass rewriting output |
| 12 | Persistence | expired state reused as live evidence |

## Workflow

1. **Scope:** target agent, entrypoints, model/provider, symptom, when it started, which layers apply.
2. **Reproduce without the wrapper** (same model, same input, bare call) vs with it. Divergence proves wrapper regression; no divergence points at the model or the input.
3. **Collect evidence from code and traces**, not prose: where the prompt is assembled, tool router, memory admission, every LLM call site (hidden second passes), fallback/retry paths, output post-processing, the transport. Trace rows and logs before opinions.
4. **Map each finding:** symptom · mechanism · source layer · root cause · evidence (file:line or trace row) · confidence 0–1. Never let a clean current state erase a dirty historical incident.
5. **Fix order — code before prompt:** (1) gate required tools in code, not "must use tool X" in prose; (2) remove or contract hidden repair agents; (3) cut context duplicated across prompt + history + memory + summary; (4) memory admission: user corrections outrank agent assertions, an agent monologue never becomes memory; (5) tighten distillation triggers; (6) pass-through rendering; (7) typed envelopes internally, not prose.
6. **Report** severity-ranked (critical = confidently wrong operational behaviour · high · medium · low): findings first, architecture diagnosis, ordered fix plan. No compliments up front.

## Seven quick questions

Can the model skip a required tool and still answer? Does old content appear in new turns? Is the same fact in prompt AND memory AND history? Does a second LLM pass run before delivery? Does delivered text differ from generated text? Are tool requirements only in prompt text? Can the agent's own output become persistent memory? A "yes" names the layer.

## Guardrails

- Read-only diagnosis; the fix is a normal branch. Platform prompts are IP — keep payloads outside git.
- Security-class findings (injection, tool abuse, exfiltration) belong to agent `agents-security` and `KB § PATTERNS/security/ai-agent-security-canon.md`; this skill diagnoses correctness and fidelity.
- Eval-loop refinement of a prompt is `noc-iterate`; this skill finds when the fault is not the prompt.

## Depth

`KB § PATTERNS/security/ai-agent-security-canon.md` (§8 memory, §10 output handling) · `KB § PATTERNS/backend/llm-tool-audit.md` · agent `agent-creator` · evals: `evals.md`.
