# agno-dev-team-future-direction — Project Document

> **This is a living document, not a rigid checklist.**
>
> **DRAFT — IDEA PRESERVATION ONLY.** This project is **not scheduled**. Its purpose is to capture the design surfaced during the 2026-05-03 absorption-evaluation session so the idea isn't lost. Phase planning is intentionally skeletal. Promote to active project only when the user explicitly says so.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** **Deferred — design captured, implementation not scheduled**
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Related docs:** Reference design at `~/Documents/repository/NoctusAI/automations/KNOWLEDGE-BASE/CONTEXT/07-DEV-TEAM.md` (469-line spec) + companion docs in the same `KNOWLEDGE-BASE/` (`06-AGENTS.md` rewrite, `PATTERNS/ast.md`, `PATTERNS/data-protection.md`, `INSTRUCTIONS/01-AGENTS.md` (Phase 7 of that project), `INSTRUCTIONS/02-TOOLS.md` (Phase 7)). Methodology consolidation project at `~/Documents/repository/NoctusAI/automations/projects/methodology-restructure/PROJECT.md` + `AUDIT.md`.
- **Project slug:** `agno-dev-team-future-direction` — cross-cutting / not-yet-a-product concern. Lives at `projects/<slug>/`.

---

## 1. Context & Purpose

In a sibling lab repo (`~/Documents/repository/NoctusAI/automations/`), the user has been building a multi-agent dev team on top of **agno** — an 11-specialist hybrid system (`coordinate` backbone + `collaborate` sub-teams for design-review / code-review / incident-response). The design is documented in `automations/KNOWLEDGE-BASE/CONTEXT/07-DEV-TEAM.md` (469 lines, finished spec).

**Important fact established in the 2026-05-03 evaluation session:** the design is complete on paper but **the Python implementation does not exist yet** (no `from agno` imports anywhere on disk; `automations/projects/methodology-restructure/PROJECT.md` shows Phases 0–4 ✅ complete (KB consolidation + AST-first principle), Phase 5+ pending; the actual `dev-team/` Python package gets scaffolded in Phase 7). The user's recollection of "very performable, fast and good quality" cannot be from this code — it doesn't exist. Possible explanation: an ephemeral prototype run elsewhere, or recall of design-doc rigor. **To be confirmed by the user before any scheduling.**

This document preserves the absorbable design so we don't lose it. **No code lands from this project.** It exists so a future "let's go" decision has a starting point that isn't a fresh re-evaluation.

---

## 2. Confirmed constraints

- **Defer entirely** — *"for the agno team, bring it in as a project deffered, we're not tackling it now, although i have much interest in it. But we have priorities."* — Idea is high-interest but lower-priority than the WhatsApp / MCP / LLM-audit / scheduling absorptions. *(Drives the no-phases / preservation-only stance.)*
- **Confirm "performable" claim before promoting** — analyst surfaced that the agno code doesn't actually exist on disk. User to verify whether their recollection is from an ephemeral prototype or design quality. If a prototype exists, point to it; if not, the future implementation starts greenfield.
- **Adopt as design reference** — *"yes, create the project with this mapping idea i mentioned, seems a safe transitioning pattern, not the actual project but a draft of the idea, so we dont lose it later."* — This file IS that draft.

---

## 3. Design principles (carried over from sibling design)

For when this project promotes from deferred to active:

1. **Hybrid topology:** `coordinate` backbone (Leader → specialist) + `collaborate` sub-teams for design-review, code-review, incident-response. Avoids the noise of full-collaborate and the blind spots of pure-coordinate.
2. **Leader presents one face.** Specialists return structured outputs to the Leader; the Leader synthesises the user-facing reply. Behavioural rules in `CLAUDE.md §1` apply to every agent.
3. **Per-agent tool allowlists.** 15-tool catalog × 11 agents × per-namespace allowlists. The keeper is a tool the Security agent uses, not its own assistant — resolves the "agents that edit vs. keepers that observe" tension.
4. **Two-layer charter** (~1.5K shared + ~1-2K role) totalling ~3K cached tokens per agent. Prompt caching essential.
5. **Provider-agnostic model assignment via YAML.** Every agent's model lives in `configs/<name>.yaml`; swap Opus → Codex or Sonnet → Gemini is a config edit. Default v1: Opus on Leader/PM/Architect/Security/CodeReviewer; Sonnet on the rest.
6. **Hybrid memory** — shared project memory + per-agent craft memory. Three-way sync rule extends.
7. **CLI v1 → MCP v2 interface.** Phase 7 (in sibling's plan) ships `python -m dev_team run "<task>"`; MCP-server interface deferred.
8. **Cost-aware routing.** Trivial work goes to Claude Code direct; multi-file / multi-domain / unclear-scope work goes to the team. Sibling's published numbers: ~$0.50–1.50 per full-team feature, 2–4× more than direct (verify against current rates).

---

## 3a. Seed-first analysis

Deferred until the project promotes from draft to active. The seed-first questions don't apply meaningfully to a not-yet-scheduled platform-tooling effort; they'll be filled when implementation phases land.

---

## 4. Scope

**Captured-but-not-scheduled scope** (for when this promotes):

- Decision: build inside `noctusai/` (the platform monorepo) vs. extract `automations/dev-team/` and consume as MCP. Tradeoffs surface during Phase 0 of an active version of this project.
- Implementation phases inherited from sibling's Phase 5–11 (seed reference stack, keeper minimal v1, dev-team scaffold, memory wiring, incident-response team + eval harness, docs).
- Three-way sync of the team's design into our `KB § PATTERNS/` and `CLAUDE.md`.

**Out of scope for THIS draft:**

- Anything implementation-flavored. This file preserves the idea.

---

## 5. Architecture / Data Model

The reference design lives at `~/Documents/repository/NoctusAI/automations/KNOWLEDGE-BASE/CONTEXT/07-DEV-TEAM.md`. Read it cold — it's complete and self-contained. Highlights:

- **§1 Architecture:** hybrid topology + structural diagram + default workflow
- **§2 Roles:** 11 specialists × {mission, responsibilities, outputs, inputs, handoffs, sub-team membership, tools}
- **§3 Tool catalog:** 15 tools × per-agent availability matrix
- **§4 Charter architecture:** two-layer prompt design + cost shape (~33K cached tokens for full team)
- **§5 Memory architecture:** shared project memory + per-agent craft memory
- **§6 Interface to Claude Code:** CLI v1 + MCP v2
- **§7 When to call the team vs. Claude Code direct:** routing table
- **§8 Cost & latency model:** concrete $/turn numbers
- **§9 Provider-agnostic model assignment:** YAML config + eval harness
- **§10 The incident_response_team:** spec
- **§11 Resolved tensions:** 7 tensions × resolution × ownership
- **§12 Open questions / future work**

---

## 6. Implementation phases

**No phases are scheduled.** When this promotes:

### Phase 0 — Confirm prototype claim + decide build location (NOT SCHEDULED)
- [ ] User confirms whether the "performable, fast, good quality" recall maps to an ephemeral prototype (point to it) or to the design quality (greenfield from spec).
- [ ] Decide: build inside `noctusai/dev-team/` or build in `automations/` and consume cross-repo. Tradeoffs documented.
- [ ] Run sibling Phase 0 (audit) on the chosen location.

### Phase N — (placeholder)
- [ ] To be planned when promoted.

---

## 7. Open questions

1. **Where the prototype is, if it exists.** User to confirm before any planning.
2. **Build inside `noctusai/` or extract `automations/`?** Cross-repo coupling vs. consolidation. No recommendation until promoted; depends on whether `automations/` continues to exist as a methodology lab or merges back.
3. **Cost ceiling.** What dollars-per-feature is acceptable before we route around the team? Decided when promoted.

---

## 8. Dependencies & blockers

- **Decision to promote.** Hard blocker.
- **Confirmation of prototype existence (or lack thereof).**

---

## 9. Success criteria (deferred)

To be defined when promoted. As a starting point, sibling's success criteria from `automations/projects/methodology-restructure/PROJECT.md` are reusable.

---

## 10. How to use this draft

- **Read the sibling design first:** `cat ~/Documents/repository/NoctusAI/automations/KNOWLEDGE-BASE/CONTEXT/07-DEV-TEAM.md` (~10 min read).
- **Update §11 Change Log if anything material changes** (e.g., user finds the prototype, or the sibling design evolves).
- **Promote by:** flipping Status to "Active" + writing real Phase 0 + linking to sibling's project execution.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | Initial draft. Idea preservation only. Implementation deferred per user direction. Sibling design fully referenced; no code lands from here. | claude-opus-4-7 |

---

## 12. No-leftovers constraint

The sibling lab repo (`~/Documents/repository/NoctusAI/automations/`) WILL ALSO BE DELETED by the user once the absorption batch is complete (per user direction: *"im gonna dump both folder after the absorption is complete"* — both = `whatsapp-google-scheduling/` AND `automations/`):

- **The 469-line design at `automations/KNOWLEDGE-BASE/CONTEXT/07-DEV-TEAM.md` will not survive.** When this project promotes from "Deferred" to "Active", a Phase 0 task is to **inline the relevant substance** of that design into this project's §3, §4, §5 — replacing the references currently in §1 + §5 — so the project stands alone.
- **Recommended action BEFORE the user deletes `automations/`:** copy the 07-DEV-TEAM.md content into this project's `agno-dev-team-design.md` reference artifact (sibling file in this folder). That preserves the 469-line spec independently.
- **No KB doc landed by promotion-and-execution may reference `automations/` paths.**
- **`PATTERNS/ast.md`, `PATTERNS/data-protection.md`, `PATTERNS/database.md` from `automations/`** — if those are absorbed into our KB, that's a separate sync action (likely part of the user's broader methodology consolidation). Flag in the absorption-mapping methodology doc the user wants to write at the end of this batch.
