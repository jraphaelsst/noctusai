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
| **L2** | the owner's **personal** number (D46), read-only shadow mode | the owner's **Assistant** (products/assistant) | Assistant session (`feat/assistant-chatbot`, branch steward) |
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
| One WAHA line per container | **yes** (found in P0) | `deploy/fleet/waha-instances.yml` (source of truth, one entry per number) → rendered `deploy/fleet/compose.waha.yml` via `noctus.dev.waha_instance action=render`; keeper `check_waha_instances_render_sync`; `KB § INTEGRATIONS/whatsapp.md` "One WAHA per number". Live instance: `monica` | consume: each line = one registry entry. Coordinate with the Assistant session, whose L2 should be an entry here too |
| Per-LINE send policy (anti-ban: allowlist, never initiate, 30–60 s jitter, ≤2/min ≤30/h ≤100/day, warm-up ramp, kill switch on FIRST/SECOND_WARNING, repetition and loop halts) | **no**. The shared `whatsapp` bucket is 5 rps / burst 10, far too fast for a fresh line | spec: `project-history/assistant-chatbot/research/waha-anti-ban.md` (feat/ac-research-skill) | the **Assistant session builds it** in the seed `integrations/whatsapp` as a per-instance policy; L1 and L3 consume it (agreed 2026-11-10) |
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
- [x] Map live WAHA sessions and containers on the noc VPS (2026-11-10, read-only via `noctus.vps.ps` and WAHA `session/list`):
  - `noctus-services-waha-1` (`devlikeapro/waha:latest`, no healthcheck): one session `default`, WORKING, paired to **"One Chat" …4172**. Its webhook goes to `social.noctusai.com/api/whatsapp/webhook/…`. This is One's current line, the one Julia answers on.
  - `noctus-waha-monica` (`devlikeapro/waha:noweb-2026.9.2`, healthy): **a second WAHA container already runs in prod** for Mônica. One-WAHA-per-container therefore has a live precedent. Phase 1 and the Assistant mechanism must read how it was provisioned (compose, tunnel ingress, base_url) before designing anything new.
  - Drift: the services WAHA floats on `:latest` without a healthcheck, while Mônica's is pinned and healthy. The new L1/L3 containers follow the pinned + healthcheck shape. Re-pinning the services container is deferred to Phase 1, which re-provisions L1 anyway.
- [x] Find which line Julia answers on today and how it is resolved (answered by `noctusai-e1`, 2026-11-10):
  - One (org `fd169d29…`) has exactly ONE `social_wiring.whatsapp_connections` row:
    - id `8fd583bb…`, `base_url http://waha:3000`, `session_name "default"`;
    - `agente_leads_ativo = false`, so the Julia routing switch is OFF.
  - Resolution is `julia_linha.linha_da_org(org)`: the org's active row, else its only row. Several rows with none active raise `LinhaAmbigua`; no row raises `SemLinha`. There is no env fallback.
  - Every SW sender uses it, including the owner-notification dispatch.
  - `(base_url, session_name)` is unique across orgs (SW 321), and create hardcodes `session_name="default"`. That gives one session per WAHA server, which fits one WAHA per container.
  - **Phase 1 approach:** re-point the existing row's `base_url` at L1's container. This carries less risk than adding a second row, which would need `agente_leads_ativo` set on exactly one row. `noctusai-e1` reviews any slice touching `julia_linha` / `whatsapp_connections`.
  - Still open: which phone number the `default` session is paired to (WAHA `session/me`).
- [x] Agree the seam with the Assistant session (2026-11-10):
  - No new mechanism: each line is one `waha-instances.yml` entry.
  - L1 and L3 land first; the Assistant adds `assistant` in the same shape and rebases. One owner per line; the second lander rebases.
  - The Assistant session builds the per-line anti-ban policy in the seed, and we consume it.
  - Nobody else plans work in core Notificações; the owner line is ours.
- [ ] Check where an owner number could live (core settings vs the notification page) and who reads it.
**Improvements:** NOC-FILL-IMPROVEMENTS

### Phase 1 — V1: Julia and the Assistant on separate lines, one server
- [ ] Retire the One Chat leftovers (bot routes, catalog row, docs), with Julia as the line, in three slices: `feat/one-chat-retire-{agents,sw,docs}`. SW hunks are reviewed by `noctusai-e1`.
  - **Delivery order is expand/contract, with all slices in ONE `feat/agents` delivery.** The agents image stops calling the bridge before the SW image deletes the route; otherwise `/api/agents` 404s on the old client. The agents migration that deletes the `one-chat` rows is applied AFTER the new agents image is live, because the old image's `ensure_defaults` would re-seed the row. Tell the dev steward this order when delivering.
- [ ] `auto_reply_enabled` (SW `whatsapp_connections`) stays for now (`NOC-REMEDIATE[drop-auto-reply-enabled]`). Trigger: one-chat-retire is deployed and nothing reads the column. Before dropping it, check prod for any row still `true`. Then ship its own small SW migration with the owner's typed go. It is never bundled with 336/337/338.
- [ ] Add a `julia` (L1) entry in `waha-instances.yml`, pinned with a healthcheck. Re-point One's `whatsapp_connections.base_url` to it. The owner re-scans …4172 there, then the legacy `noctus-services-waha-1` retires.
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

1. ~~The Assistant on your personal number?~~ **Answered (D46, Assistant spec rev 18):** the Assistant goes on the
   PERSONAL number in READ-ONLY shadow mode. It stores inbound messages, runs the implied request and stores the reply it
   would send, and sends nothing (`send: disabled`). Its first job is to classify "about scheduling or not". D42 is
   superseded.
1b. ~~Which number is L1?~~ **Answered (owner, 2026-11-10):** the existing One Chat line …4172. "julia is the new one
   chat"; the One Chat leftovers should have been erased when Julia came in, so they are retired in Phase 1
   (`feat/one-chat-retire`). Phase 1 moves …4172 into its own registry container.
   - Note: the memory from 2026-11-04 said Julia and owner notifications share ONE number. Today's decision supersedes
     it: owner notifications go on L3 (noc's line), never a client's line.
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
