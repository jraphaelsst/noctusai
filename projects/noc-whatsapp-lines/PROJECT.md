# noc-whatsapp-lines — Project Document

> **Status:** Phase 0 (audit) · **Opened:** 2026-11-10 by the owner (session noctusai-e4) · **Branch:** `feat/agents`
> (worktree `.claude/worktrees/agents`, branch steward = the `agents` session) · **Delivers to:** the dev steward via
> `release_steward action=request`; prod go is typed by the owner in the dev steward's session.

## 1. Context & Purpose

NoctusAI needs its **own WhatsApp line**. The trigger: the eval-loop gate (migration 075) must warn the owner when a
loop stops, and since 2026-11-09 "warn me" means a WhatsApp scripted message
(`KB § PATTERNS/backend/owner-notification-catalog.md`). Today only social-wiring sends WhatsApp, from each org's
own line to that org's staff. There is no NoctusAI line and no owner number.

The owner, verbatim (2026-11-10):

> "we're gonna sync our work on creating noctus' own line with the assistant multi-whatsapp probe work. So im setting
> my business number as julia, my personal number will be atached to the assistant job, and i'll get a third number to
> probe even more the multi-whatsapp-line-container-waha is valid … one is julia, second probe is my personal
> assistant, and third, as a validation, we create noc's own agent, after learning from creating all the other
> mechanisms (agents, templates, wiring, and all)"

So this project is **three WhatsApp lines on ONE server (the noc VPS), one WAHA line per container**:

| Line | Number | Who talks on it | Owning work |
|---|---|---|---|
| **L1** | the owner's **business** number | **Julia** (One imobiliária SDR, agents product) | `agents` session (this branch) + SW session `noctusai-e1` for Julia's SW wiring |
| **L2** | the owner's **personal** number | the owner's **Assistant** (products/assistant) | Assistant session (`feat/assistant-chatbot`, branch steward) |
| **L3** | a **third** number, to be bought | **noc's own agent**, which also sends every owner notification | `agents` session (this branch), built LAST |

Validation ladder (the owner's "probe"):

- **V1:** L1 and L2 run side by side, on different numbers, in separate WAHA containers on the same server. Both stay
  healthy and neither sees the other's chats.
- **V2:** L3 joins as a third container. It proves the mechanism scales past two. It is also the first agent built
  end-to-end from everything learned (templates agente-base → sdr-base, the agent creator, wiring, the Assistant run).

## 2. Confirmed constraints

- One WAHA line per container, all on the noc VPS. This is the Assistant's multi-line architecture
  (`project_assistant_product` memory, slice 1). **This project consumes it and never forks it.**
- The owner-notification sender is a **seed** capability that every product calls through the catalog gate
  (`noctusai_lib.domain.notification_catalog`). There are no per-product copies; the catalog pattern says so explicitly.
- Our internal messages never go out from a client's line. This was the owner's choice on 2026-11-10: option 1
  "seed owner line", not "use One's line".
- The eval-loop gate (075) is **held off the dev queue** until the owner line exists. Its stop and checkpoint notices
  ship as declared kinds with a WhatsApp leg, plus the existing in-app bell.
- Fake + Real + factory for every IO seam. No silent fallback: a missing line or number is a recorded `no_recipient`
  or `failed`, never a skip.
- Numbers and QR connection are **owner actions**. Agents never connect a line or type a number.

## 3. Design principles

Seed-first; consume the Assistant's WAHA-per-container mechanism; event-oriented (every send is a
`notification_sends` row); measurable (each line's health and sends are visible on core's Notificações page and the
line's own status).

## 3a. Seed-first analysis

| Need | Exists? | Where | Action |
|---|---|---|---|
| WhatsApp client (WAHA + Meta Cloud) | yes | `seed/lib/backend/noctusai_lib/integrations/whatsapp/` | consume |
| Notification kinds + switch + ledger | yes (2026-11-09) | `noctusai_lib.domain.notification_catalog` + core 117 | consume; declare agents kinds |
| One WAHA line per container | in flight | Assistant slice 1 (`feat/assistant-chatbot`) | consume when it lands; Phase 0 reads its state |
| Owner-line sender (platform session + owner number(s)) | **no** | — | build in the seed (Phase 2): Protocol + Fake + Real + factory; config on core Notificações |
| Agent from templates on its own line | partial | agents layers 073 + creator | Phase 3 |

## 4. Scope

**In:** L1 Julia on the business number; the seed owner-line sender; agents notification kinds; the eval-loop gate's
WhatsApp leg; L3 noc's own agent on the third number.
**Out (owned elsewhere):** L2 Assistant line and the WAHA-per-container mechanism (Assistant session); Julia's SW-side
wiring (`noctusai-e1`); prod migrations and deploy (dev steward).

## 4a. Dispatch routing

| Slice | Lens / agent | Branch (merges INTO `feat/agents`) |
|---|---|---|
| P0 audit: VPS WAHA topology, Julia's current line, Assistant mechanism state | Explore + devops-engineer (read-only) | — |
| Seed owner-line sender + core config | integrations-engineer | `feat/noc-owner-line` |
| agents `notification_kinds.py` + gate WhatsApp leg | backend-engineer | `feat/agents-eval-loop-gate` (rebased) |
| L1 Julia line switch | integrations-engineer + e1 | `feat/julia-business-line` |
| L3 noc agent definition | ai-engineer (creator path) | `feat/noc-agent` |

## 5. Architecture

```
noc VPS
├── waha-julia      (L1, business number)  ← agents channel for Julia
├── waha-assistant  (L2, personal number)  ← products/assistant
└── waha-noc        (L3, third number)     ← noc's own agent + seed owner-line sender
                                              ↑
   every product → notification_catalog gate (allowed? → send via owner line → record)
```

## 6. Implementation phases

### Phase 0 — Audit
- [ ] Map live WAHA sessions and containers on the noc VPS (`noctus.vps.ps`, `noctus.dev.waha_instance`).
- [ ] Find which line Julia answers on today and how the agents channel resolves it.
- [ ] Read the Assistant branch's WAHA-per-container design and its state; agree the seam with the Assistant session.
- [ ] Check where an owner number could live (core settings vs the notification page) and who reads it.
**Improvements:** NOC-FILL-IMPROVEMENTS

### Phase 1 — V1: Julia and the Assistant on separate lines, one server
- [ ] The Assistant session lands its WAHA-per-container mechanism (their branch).
- [ ] Julia moves to the business number on her own container (owner scans the QR).
- [ ] V1 probe: both lines live, isolated, healthy for 24 h.
**Improvements:** NOC-FILL-IMPROVEMENTS

### Phase 2 — Seed owner line + gate WhatsApp leg
- [ ] Seed owner-line sender (Protocol + Fake + Real + factory), configured on core Notificações (line + owner number(s)).
- [ ] agents `notification_kinds.py`: `eval_loop_parada`, `eval_loop_checkpoint`.
- [ ] Eval-loop gate sends through the gate and the owner line; the bell stays. Tests for suppressed and no_recipient.
- [ ] Deliver `feat/agents` (075 included) to the dev steward.
**Improvements:** NOC-FILL-IMPROVEMENTS

### Phase 3 — V2: noc's own agent on L3
- [ ] Owner buys and connects the third number.
- [ ] noc's agent is created through the agent creator from agente-base, after Julia is published.
- [ ] The owner line points at L3. V2 probe: three lines healthy on one server.
**Improvements:** NOC-FILL-IMPROVEMENTS

## 7. Open questions (owner)

1. The Assistant on your **personal** number: this supersedes D42 (the spare number). The Assistant session confirms
   with you.
2. When will the third number exist? Phase 3 starts then. Until then the owner line has no sender, so the eval-loop
   gate stays held: there's no interim channel.
3. Which number(s) receive owner notifications: only yours, or also a second admin?

## 8. Dependencies & blockers

Assistant WAHA-per-container mechanism (Phase 1); the third number (Phase 3); the owner's typed prod go for 075.

## 9. Success criteria

Three WAHA containers on the noc VPS, each on its own number and healthy. A stopped eval loop reaches the owner's
phone on WhatsApp from L3 and shows on core's Notificações page. noc's own agent answers on L3.

## 10. How to use this plan

The `agents` session steers. Sub-slices merge into `feat/agents`; never straight to dev. Peers coordinate through
`release_steward` and SendMessage, naming roles rather than session names.

## 11. Change log

- 2026-11-10 — opened from the owner's answer on the eval-loop gate's notification channel; gate 075 pulled into
  `feat/agents`.
