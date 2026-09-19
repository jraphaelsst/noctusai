# PROJECT — One Ops: the agents product as a multi-agent chat platform

> **Status:** Phase A in flight (2026-09-19) · **Owner:** tech-lead · **Branch:** `feat/one-ops-agents`
> **Products touched:** `agents` (primary) · `social-wiring` (Phase F)
> **Deploy posture:** 🔴 dev-visible throughout; ONE prod-promotion decision at the end (§7).

---

## 0 · Why this exists

The `Cindy` and `Priscila` spreadsheets are filled by hand, every run, by an agent driving
a browser: read the sheet, resolve each `ONExxxxx` reference against the midiasone Drive,
write link + video-count + a pt-BR `Observação`, then verify by re-exporting the CSV.
Two runs happened in one session on 2026-09-17, and the second had to be **redone end to
end** because the link target differs per sheet (§2.2). That is the N≥2 trigger for
`KB § PATTERNS/common/repetitive-task-skill-codification.md`, and the user's ask is
broader: a **chat window in a product UI** where this work is requested conversationally,
using the same mechanism that will serve Julia and One Chat.

---

## 1 · Decisions taken (interview, 2026-09-19 — these are LOCKED, not assumptions)

| # | Decision | Consequence |
|---|---|---|
| D1 | Google access via a **single service account** | One JSON key covers BOTH accounts; access is granted by sharing, not by logging in (§5) |
| D2 | Agent scope: **general midiasone ops assistant** | Spreadsheet-refs is its first capability, not its definition |
| D3 | Writes are **autonomous, reported after** | No approval gate on the write path — but see D4 |
| D4 | Safety net: **snapshot-before-write + undo** | New table + endpoint; autonomy is only safe because revert is one click |
| D5 | Sheet discovery: **UI registry AND chat** | Registry is source of truth; agent may also resolve by name and offer to register |
| D6 | Per-sheet convention lives in **DB config, editable in UI** | The Priscila mistake becomes a field edit, never a code change |
| D7 | Scope: **all three agents end to end** (Julia, One Chat, One Ops) | Phase F is in scope — see §4 risk |
| D8 | One Chat **moves into `agents`**; social-wiring consumes its API | Inverts today's dependency direction (§2.3) |
| D9 | Agent name: **`one-ops`**, One-family branding | DB key, nav entry, chat page title |
| D10 | Prod: **only at the end**, one decision | Pages stay `status_pagina='desenvolvimento'` until then |

---

## 2 · Current state — evidence, not assumption

### 2.1 `products/agents` is substantially built, not a scaffold

Its `README.md` says "domain code is planned, not built". The code disagrees:

- **Tables:** `agents`, `agent_personas` (versioned + model allowlist), `conversations`,
  `messages`, `approvals`, `session_transcript_entries`, `runtime_settings`,
  `app_integration_config`, credentials — 10 migrations
- **Runtime:** `AgentRuntime` Protocol + `FakeAgentRuntime` + `ClaudeAgentSdkRuntime`,
  approval broker, gate, slot sweeper, transcript mirror, resume-after-restart
- **Tests:** 38 files under `backend/tests/`
- **UI:** `Julia` (chat), `Agentes`, `JuliaPersona`, `Aprovacoes`, `Credenciais`,
  `ConfiguracoesAgente`

⇒ The chat mechanism the user wants is ~80% present. **README drift is a Phase G
fix-on-contact item.**

### 2.2 🔴 The seam is pinned to ONE agent

| Site | Pin |
|---|---|
| `app/runtime/types.py:50` | `key: Literal["julia"]` on `AgentSpec` |
| `app/routers/conversations_router.py:193,265` | `agent_store.get_by_key(ctx.org_id, "julia")` |
| `app/routers/persona_router.py:53,72` | same |
| `app/runtime/__init__.py:26,212` | `_JULIA_DIR = .../agents/julia`, `key="julia"` |

The **data model is already multi-agent** (`get_by_key`, per-agent personas); the
**routers and runtime are not**. `AgentSpec` already carries `skills`, `tools`, `model`,
`effort` — so generalization is a registry lookup plus
`build_julia_spec()` → `build_agent_spec(agent_key, persona_row)`, not a redesign.
`app/agents/julia/plugin/` establishes the per-agent directory convention; a second agent
is a sibling directory.

### 2.3 The One Chat bridge exists and points the WRONG way for D8

Today: `agents` holds a product token scoped `social-wiring:one-chat:read` + `:toggle`
and calls `social-wiring`'s `/api/agents-bridge/one-chat/{connection_id}`
(`app/clients/social_wiring.py`, Fake+Real+factory). social-wiring's
`agents_bridge_router.py` enforces `caller_kind == "product"` and `issuer == "agents"`,
and its docstring states plainly that **no prompt, tool, sender-policy or webhook
behaviour changes anywhere in social-wiring**.

D8 inverts this. See §4.

---

## 3 · Phases

| Phase | Deliverable | Size | Depends on |
|---|---|---|---|
| **A** | `.claude/skills/noc-refs-sheet` — the methodology as source of truth | S | — |
| **B** | Agent-keyed seam: `types.py`, `build_agent_spec`, agent registry, routers | M | — |
| **C** | Sheet registry + convention config: schema, routers, `Planilhas` page | M | B |
| **D** | Google IO seam (Sheets + Drive; Protocol+Fake+Real+factory) + snapshot/undo | M–L | — (Real half needs §5) |
| **E** | `one-ops` agent: agent dir, tools, persona, chat page | M | B, C, D |
| **F** | One Chat inversion (D8) | **L** | B |
| **G** | Julia onto shared mechanism · drift fix-on-contact · prod decision | S–M | all |

**A, B and D are file-disjoint** and can run in parallel once the contract lands.
C depends on B's registry. E is the integration point. F is independent of C/D/E.

### Phase A — scope (in flight)

`.claude/skills/noc-refs-sheet/SKILL.md` carrying: the per-sheet link-target rule, the
duplicate-folder resolution rules, the trap catalogue, and the verification discipline.
Plus 8-way sync: `CLAUDE.md` §2, `CONTEXTUALIZE.md` §4.

**Why the skill comes first even though the product is the goal:** the agent's persona in
Phase E must be *generated from* one methodology document, not a second hand-written copy.
Writing the procedure twice is how the Cindy/Priscila rules drift apart again.

---

## 4 · 🔴 Risk — Phase F splits behaviour from transport

social-wiring owns the live WhatsApp transport: `whatsapp_webhook_router`,
`whatsapp_chat_store`, `whatsapp_chatbot_service`, `whatsapp_outbound`,
`whatsapp_intake_service`. D8 moves One Chat's *management* (persona, settings,
transcripts) into `agents` while transport stays put.

**The failure mode:** every inbound WhatsApp message then needs a cross-product call to
resolve its persona before replying — a new synchronous hop, and a new failure mode, on a
path that is live today. The existing bridge is deliberately one-directional for exactly
this reason.

**Lighter variant worth settling in F's contract:** `agents` owns persona/settings as
**source of truth**, social-wiring **caches** it (push-on-change or TTL). The chat window
and the config live where the user wants them, without a synchronous hop in the message
path.

Decision deferred to F's contract, not to implementation time. Raised 2026-09-19; user
elected to proceed with D8 as stated.

---

## 5 · Google service account — the setup (Phase D's Real half)

🔴 **A service account is its own identity, not a connection to an account.** One SA + one
key reaches BOTH accounts, because access is granted by *sharing*, not by logging in. Two
OAuth connections were rejected: `auth/drive` is a restricted scope, so Testing mode
expires refresh tokens every 7 days — doubled (see memory
`feedback_agent_drive_access_uses_claude_connector`).

**Grants needed — five total:**

| Owner | Resource | Role | Why |
|---|---|---|---|
| joaoraphaelsst | `Cindy` sheet | Editor | we write cells |
| joaoraphaelsst | `Priscila` sheet | Editor | we write cells |
| midiasone12 | `2026` (`1360Sml33ieu8OO7V3vYaVKT3VAd1YFYC`) | Viewer | 2026-style months |
| midiasone12 | `Material 2025` (`1LS8ne4xegVR9xHX_kxcXA2mjqQHj9aN6`) | Viewer | 2025-style months |
| midiasone12 | `FOTOS DIVERSAS` (`1A1TWG6DAB22aJ8TubV8GVt6Wna0tukHO`) | Viewer | strays such as ONE8132 |

Sharing is inherited, so this is three grants on the Drive side — not one per ref.

⚠️ **Known gap:** a duplicate `ONE6649` folder sits loose directly at midiasone's My Drive
root (`0AFjedLF5CGIvUk9PVA`), outside all three. A My Drive root cannot be shared, so that
folder needs either its own grant or — cleaner — to be moved under a year folder. Other
strays may exist; only the folders touched by the first 10 refs were surveyed.

The key lands in the existing `Credenciais` vault, never in env or the repo.

---

## 6 · Non-goals

- Changing WhatsApp transport behaviour in social-wiring (§4)
- Any prod deploy before §7
- Replacing the browser-driven route for Cindy while Phase D is unbuilt — it keeps working
- Making `one-ops` available to other orgs (single-tenant to midiasone for now, per D2)

---

## 7 · Prod promotion

🔴 Per `KB § PATTERNS/devops/prod-exposure-consent.md`, registering a prod exposure surface
is **the user's decision, never an agent's**. Per D10 this project stays dev-visible until
all three agents work end to end, at which point the promotion is requested explicitly and
recorded here with the user's own words. Nothing in Phases A–F may deploy to prod.
