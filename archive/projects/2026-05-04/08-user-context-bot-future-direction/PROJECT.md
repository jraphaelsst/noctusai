# user-context-bot-future-direction — Project Document

> **DRAFT — IDEA PRESERVATION ONLY.** Captured during the 2026-05-03 absorption-evaluation session. The sibling's `projects/personal-assistant-bot/PROJECT.md` (planning artifact only — no code shipped) gets ported here so it isn't lost when the sibling repo is deleted. Phase planning is intentionally skeletal. Promote to active project only when the user explicitly says so.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** **Deferred — design preserved, implementation not scheduled**
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Related docs:** `projects/whatsapp-seed-absorption/PROJECT.md`, `projects/mcp-server-expansion/PROJECT.md`, `projects/llm-tool-call-audit/PROJECT.md`. Same dependency triangle as `dev-observability-bot-future-direction`.
- **Project slug:** `user-context-bot-future-direction`. Lives at `projects/<slug>/`.

---

## 1. Context & Purpose

Sibling's `projects/personal-assistant-bot/PROJECT.md` outlines a WhatsApp bot for **authenticated end-users** to query *their own* data (profile, appointments, summaries). Self-only enforcement at the MCP-tool layer: every tool that returns user data takes `user_id` and the framework rejects any call where `user_id != caller_user_id`. The pattern is generic — applies to any NoctusAI product where end-users may want async self-service over WhatsApp (therapy patients querying upcoming sessions, daily-life users asking about their goals, ERP brokers asking "what showings do I have today?").

This project preserves the pattern + design surface inside `noctusai/` so the idea isn't lost when the sibling folder is deleted. **No code lands from this draft.**

The differentiator versus `dev-observability-bot-future-direction`: that one is *staff-facing, read-only, system-internals*. This one is *user-facing, self-only, personal-data*. Different auth model, different tool surface, different LGPD posture.

---

## 2. Confirmed constraints

- **Defer entirely** — preserved during absorption batch; not scheduled.
- **Self-only enforcement at the framework layer.** Every personal-data tool gets `user_id`; the dispatcher rejects if `user_id != caller`. Not bolted on at consumer level — built into the tool decorator pattern. Sibling makes this explicit.
- **LGPD-first per `KB § PATTERNS/lgpd.md`.** Any tool that returns user PII or Art. 11 sensitive data (clinical text in therapy) gets the LGPD five-questions treatment. Cache disabled for sensitive data per `KB § 04-SHARED-LIBRARY.md § llm/`.
- **Per-product wiring.** Same bot pattern, different consumers — therapy patients, daily-life users, ERP brokers each get their own bot instance with their own tool registry + system prompt + WAHA session.

---

## 3. Design principles (carried over from sibling)

For when this project promotes:

1. **Composes the seed chatbot framework**, same as `dev-observability-bot-future-direction`.
2. **Self-only enforcement is a framework concern, not a tool concern.** The MCP tool decorator (or `noctusai_lib.domain.chatbot` dispatcher) enforces; tools just declare "this is personal-data" and rely on the framework.
3. **LGPD redaction at the audit-write boundary.** `arguments` / `result` fields in `tool_call_audits` get redaction passes for personal data; the project's first phase decides the redaction policy.
4. **Per-consumer system prompt.** No shared "personal assistant" prose; each consumer (therapy / daily-life / ERP) writes its own.
5. **Read-mostly with explicit write surfaces.** Sibling's plan: write tools (e.g., "reschedule my appointment") get explicit confirmation steps in the conversation flow.

---

## 3a. Seed-first analysis

Deferred until the project promotes. When promoted:
- Self-only enforcement → framework-level (in `noctusai_lib.domain.chatbot` or new `noctusai_lib.domain.ai.self_only`).
- Per-consumer system prompts + tools → product-level.
- Per-product code count target: a small section per consumer (system prompt + tool registry + WAHA session config).

---

## 4. Scope (preserved from sibling)

**Captured-but-not-scheduled scope** (for when this promotes):

- Self-only enforcement primitive at framework or `noctusai_lib.domain.ai`.
- Reference tool surface (the sibling's example list, generalized):
  - `noctus.user.get_profile(user_id)`
  - `noctus.user.list_my_appointments(user_id)`
  - `noctus.user.list_my_recent_messages(user_id, since)`
  - `noctus.user.get_my_summary(user_id)`
- Per-product wiring template (therapy first candidate; daily-life close second).
- LGPD redaction policy for audit rows (decided in Phase 0 when promoted).
- Conversation-level confirmation pattern for write tools.

**Out of scope for THIS draft:** anything implementation-flavored.

---

## 5. Architecture / Data Model

Reference sibling design at (sibling-folder-relative) `projects/personal-assistant-bot/PROJECT.md`. **Do not depend on the sibling path post-absorption.** Substance preserved in §3, §4 above.

The bot composes:
- `noctusai_lib.integrations.whatsapp`
- `noctusai_lib.domain.chatbot`
- `noctusai_lib.domain.ai.tool_audit` (with LGPD redaction)
- Self-only enforcement primitive
- Per-consumer MCP tools under `platform.user.*` (or `<product>.user.*`)

---

## 6. Implementation phases

**No phases scheduled.** When promoted:

### Phase 0 — Decide build surface + first consumer (NOT SCHEDULED)
- [ ] Confirm WhatsApp seed feature wired and a product consumer exists.
- [ ] Decide first consumer (therapy / daily-life / ERP).
- [ ] Run LGPD five questions over the planned tool surface.

---

## 7. Open questions

1. **Self-only enforcement: framework or each tool?** Recommendation: framework. Decided at promotion.
2. **Cross-user lookups for staff (e.g., therapist viewing patient via the same bot)?** Recommendation: **separate bot product** — mixing staff + patient in one WAHA session is an LGPD risk. Decided at promotion.
3. **Conversation memory scope: per-user or per-(user, product)?** Recommendation: per-(user, product) — a patient using both therapy + daily-life shouldn't have memories cross-product.
4. **Redaction policy in audit rows: hash, redact, or omit?** Decided in Phase 0 when promoted.

---

## 8. Dependencies & blockers

- **`projects/whatsapp-seed-absorption/`** — must complete.
- **`projects/llm-tool-call-audit/`** + LGPD redaction extension.
- First-consumer product wiring decision.

---

## 9. Success criteria (deferred)

To be defined when promoted.

---

## 10. How to use this draft

- Promote by flipping Status, writing Phase 0, scaffolding consumer wiring (e.g., `products/therapy-platform/projects/therapy-patient-bot/`).
- Do NOT depend on sibling repo paths.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | Initial draft, ported from sibling `projects/personal-assistant-bot/PROJECT.md`. Implementation deferred per user direction. | claude-opus-4-7 |

---

## 12. No-leftovers constraint

Sibling repo (`whatsapp-google-scheduling/`) will be deleted. Substance from sibling's `projects/personal-assistant-bot/PROJECT.md` is inlined above. No KB doc landed during this project's eventual execution should reference sibling paths.
