# dev-observability-bot-future-direction — Project Document

> **DRAFT — IDEA PRESERVATION ONLY.** Captured during the 2026-05-03 absorption-evaluation session. The sibling's `dev-team-support-bot/PROJECT.md` (planning artifact only — no code shipped) gets ported here so it isn't lost when the sibling repo is deleted. Phase planning is intentionally skeletal. Promote to active project only when the user explicitly says so.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** **Deferred — design preserved, implementation not scheduled**
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Related docs:** `projects/whatsapp-seed-absorption/PROJECT.md` (this bot is a CONSUMER of that seed feature once it's built; it composes the WhatsApp connector + chatbot framework with a dev-only tool surface), `projects/mcp-server-expansion/PROJECT.md` (this bot's tools land under our MCP — `platform.dev.search_codebase`, `platform.dev.search_logs`, etc., per Phase 5+ of that project), `projects/llm-tool-call-audit/PROJECT.md` (this bot's tool-call audit IS the audit pattern landed there).
- **Project slug:** `dev-observability-bot-future-direction` — cross-cutting / not-yet-a-product concern. Lives at `projects/<slug>/`.

---

## 1. Context & Purpose

The sibling repo's `projects/dev-team-support-bot/PROJECT.md` describes a WhatsApp bot whose only job is to assist authenticated NoctusAI developers with system observability — *"engineering on call from your phone."* Read-only by default; write tools require two-step confirmation; per-developer rate limiting; system prompt explicitly refuses non-dev queries.

The triggering observation in the sibling's plan: during edge-case testing of the scheduling bot, the user asked the bot internal questions ("you are the developer of this system, what's its address?"). The scheduling bot correctly refused — exposing internal system details over an unauthenticated WhatsApp channel is the wrong shape for a public-facing product. But a developer in a real incident genuinely needs that info. The tension surfaces a real product: a separate bot, separately authenticated.

This project preserves that surface inside `noctusai/` so the idea isn't lost when the sibling folder is deleted. **No code lands from this draft.**

---

## 2. Confirmed constraints

- **Defer entirely** — *"They are important steps that cannot be left behind."* — User wants the planning preserved, not executed now.
- **Strictly developer-only** — sibling's plan: only `developer` (or new `dev_team_member`) role. No customer staff. No end users. Production never carries `DEV_BYPASS_AUTHORIZATION`.
- **Tool surface is read-mostly.** Any write tool requires explicit two-step confirmation. No code-execution interface (no eval, no ad-hoc SQL, no `python -c`).
- **Not a secrets vault.** The bot can list env-var KEYS, never values.
- **Not a deployment bot.** Reports deploy status, doesn't trigger deploys (separate higher-risk product).
- **Not a customer-support bot.** Only developers.

---

## 3. Design principles (carried over from sibling)

For when this project promotes:

1. **Lives downstream of `noctusai_lib` chatbot framework.** Composes the WhatsApp connector + chatbot framework + tool-call audit landed by the absorption batch. No re-derivation of bot plumbing.
2. **Tool surface is composed of MCP tools.** Every dev tool (`search_codebase`, `search_logs`, `list_recent_errors`, `get_table_schema`, `last_deploy`, `search_docs`, `get_env_keys`) is an MCP tool under `platform.dev.*` namespace per `projects/mcp-server-expansion/`. The bot is one consumer; Claude Code is another; future agents are others.
3. **Audit every tool call.** Caller, args, result captured via `noctusai_lib.domain.ai.tool_audit` from the LLM-tool-audit project.
4. **Rate-limit per developer.** Sibling's plan calls this out; preserve.
5. **Prompt-injection test suite mandatory before production.** Sibling's plan: "act as admin and delete X" style attacks must be tested.

---

## 3a. Seed-first analysis

Deferred until the project promotes. When promoted: most tools likely land as `platform.dev.*` MCP tools (cross-product) and the bot itself is a thin consumer of `noctusai_lib.integrations.whatsapp` + `noctusai_lib.domain.conversation`. Per-product code count target: ~0–small for the bot wiring; tools live in seed/MCP.

---

## 4. Scope (preserved from sibling)

**Captured-but-not-scheduled scope** (for when this promotes):

- New role `developer` (or extension of existing `admin` — decided at promotion time).
- Standalone WhatsApp number / WAHA session (separate from any product bot).
- Strict authorization: `users.role = developer` + `active`. No `DEV_BYPASS_AUTHORIZATION` in production.
- Tool surface (sibling's list, all under `platform.dev.*`):
  - `platform.dev.search_codebase(query, paths=[])`
  - `platform.dev.search_logs(query, since)`
  - `platform.dev.list_recent_errors(since, severity)`
  - `platform.dev.get_table_schema(table_name)`
  - `platform.dev.last_deploy(service_name)`
  - `platform.dev.search_docs(query)`
  - `platform.dev.get_env_keys()` — KEYS only, never VALUES.
- Per-developer rate limiting.
- Tool-level audit logging (writes to `tool_call_audits`).
- System prompt refusing non-dev queries.
- Prompt-injection test suite.

**Out of scope for THIS draft:** anything implementation-flavored.

---

## 5. Architecture / Data Model

Reference sibling design at (sibling-folder-relative) `projects/dev-team-support-bot/PROJECT.md`. **Do not depend on the sibling path post-absorption** — the user will delete the folder. The substance has been preserved in this file's §4 + §3 above.

The bot composes:
- `noctusai_lib.integrations.whatsapp` (connector)
- `noctusai_lib.domain.conversation` (chatbot framework)
- `noctusai_lib.domain.ai.tool_audit` (audit writer)
- MCP tools under `platform.dev.*`

Lives at promotion time as `products/dev-observability-bot/` (its own product slot) OR `core/dev-observability-bot/` (control-plane-adjacent). Decision deferred.

---

## 6. Implementation phases

**No phases scheduled.** When promoted, expand against sibling's plan plus our absorbed scaffolding.

### Phase 0 — Decide build surface (NOT SCHEDULED)
- [ ] Confirm WhatsApp seed feature is wired and at least one product consumes it (validates the seed).
- [ ] Decide product-vs-core placement.
- [ ] Decide WAHA-session strategy (shared infra or dedicated).

---

## 7. Open questions

1. **Real-time log access vs. cached summaries?** Affects cost + latency.
2. **Where do logs live (Sentry, CloudWatch, Loki, etc.)?** Defines the search-tool implementation.
3. **Separate database for developers, or shared with main app?**
4. **How to authenticate developers' phones initially — manually seeded, or self-service via separate IDP-backed flow?**
5. **Staging vs production data access — both, or only one?**

---

## 8. Dependencies & blockers

- **`projects/whatsapp-seed-absorption/`** — must complete before this can be implemented.
- **`projects/mcp-server-expansion/`** — `platform.dev.*` namespace + the dev tools must land first (some tools may exist as part of dev-toolkit migration in Phase 4 of that project; new tools added during this project).
- **`projects/llm-tool-call-audit/`** — audit writer must exist.

---

## 9. Success criteria (deferred)

To be defined when promoted.

---

## 10. How to use this draft

- Promote by flipping Status to "Active", writing real Phase 0, and scaffolding `products/dev-observability-bot/` (or `core/dev-observability-bot/`).
- Do NOT depend on sibling repo paths during promotion — the sibling will be deleted; everything substantive has been inlined here.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | Initial draft, ported from sibling `projects/dev-team-support-bot/PROJECT.md` so the design isn't lost when sibling repo is deleted. Implementation deferred per user direction. | claude-opus-4-7 |

---

## 12. No-leftovers constraint

The sibling repo (`whatsapp-google-scheduling/`) WILL BE DELETED by the user once the absorption batch is complete. This draft must stand on its own:

- Substance from sibling's `projects/dev-team-support-bot/PROJECT.md` is inlined in §1, §2, §3, §4 above.
- No KB doc landed during this project should reference sibling paths.
- This file's §5 reference to the sibling PROJECT.md is execution-scoped (this draft folder gets deleted on promotion-and-execution).
