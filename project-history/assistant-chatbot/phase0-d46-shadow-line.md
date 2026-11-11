# Assistant — Phase 0 addendum for D46 (personal line, read-only shadow mode)

> Written 2026-11-10 by the branch steward of `feat/assistant-chatbot` under the owner's free pass.
> D46 (spec doc rev 18, owner typed 2026-11-10) supersedes D42 and widens D38. This addendum
> re-reads `phase0-audit-assistant.md` against D46 and proposes the slice plan; the Phase 0 council
> reviews it (pilot clause D13, `PROJECT.md` §1).

## 1 · What D46 asks

- The Assistant pairs the owner's **personal** WhatsApp number on its own WAHA container.
- **Shadow mode:** every message that lands on the line is stored. For each inbound message the app
  runs the request it implies and stores the reply it *would* send. **Nothing is sent to WhatsApp.**
- **First job:** classify each message as "related to scheduling or not". It is an evaluation set
  before any automation.
- Later: live replies, Google actions, then the rest of the spec. None of that ships in this slice.

## 2 · Phase 0 re-read (gaps from `phase0-audit-assistant.md`, re-judged)

| # | Original gap | Under D46 |
|---|---|---|
| 1 | No pre-store chat filter (self-chat only) | **Gone.** D46 stores everything; the seed default "store all except broadcast/newsletter" fits. |
| 2 | No own-id on the connection | **Deferred.** Not needed to store or classify. Useful later to tell the owner's own messages apart (`fromMe` already does this per message). |
| 3 | No env-trio Calendar resolver | **Deferred** to the slice that executes scheduling requests. |
| 4 | No WhatsApp→LLM loop | **Needed, as a shadow loop:** the seed `on_message` hook (`whatsapp_inbox_router.py:47,309`) fires after store, which is where the classifier and the shadow reply attach. |
| 5 | No single-owner concept | **Still open.** The product is one org with one admin user (the owner); this run records what a "personal product" needs, and does not invent an identity model. |

New gaps that D46 creates:

6. **No "receive on, send off" line state.** The seed has `app_enabled` (`KB § INTEGRATIONS/whatsapp.md` §7). Off means receive nothing **and** send nothing. D46 needs receive on and send refused, fail-closed, for every write the client can make: `send_text`, media, `send_seen` (read receipts; the inbox router mirrors a UI mark-read to WhatsApp when `mirror_read_to_whatsapp=True`, `whatsapp_inbox_router.py:339`), presence/typing, and reactions.
7. **No per-line pacing.** Every line shares the `rate_limit` bucket `"whatsapp"` (5 rps, burst 10; `client.py:368,397`). Research (`research/waha-anti-ban.md`) says a fresh line needs ≤2/min, ≤30/h, ≤100/day with a warm-up ramp. Dormant while sends are disabled, but the seam must exist before the first live reply.
8. **No kill switch on WhatsApp warnings.** WAHA reports session-state changes; a FIRST/SECOND_WARNING or a 463/475 must halt the line's writes and stop restart/re-pair loops.
9. **Storage of third parties' messages from a personal line.** LGPD question for `legal-advisor` (art. 4 I personal-use exemption vs. processing on a NoctusAI server; retention; access). It must be answered before go-live.

## 3 · Candidate decisions (for the council)

- **C1 · The line policy lives in the seed, one per WAHA instance.** It is declared in
  `deploy/fleet/waha-instances.yml` next to the instance (the reviewed source of truth for lines),
  rendered into the product's env contract (`<PRODUCT>_WAHA_LINE_POLICY`, JSON, next to
  `<PRODUCT>_WAHA_BASE_URL`), and enforced by a seed wrapper around `WahaClient` that every write
  goes through. Fields: `send: disabled | allowlist | enabled`, `allowlist`, pacing
  (`per_min`, `per_hour`, `per_day`, `jitter_s`, `warmup`), `read_receipts: false|true`,
  `presence: false|true`, `on_warning: halt`. A keeper refuses an instance without an explicit `send`
  field (fail-closed at config). The wrapper refuses every write when the policy says so, raises a
  typed `LineWriteRefused`, and records an event. Julia's and noc-agent's lines declare their own
  values (agreed with the agents team, 2026-11-10).
- **C2 · `products/assistant` is a new seed-scaffolded product** (`noc-new-product`), with
  `ativo` + `deploy_scope` set by the product catalog. It mounts the seed WhatsApp connections and
  inbox routers exactly as Nós no Limiar does (`products/nosnolimiar/backend/app/routers/whatsapp_router.py:29-34`),
  with `mirror_read_to_whatsapp=False` (belt and braces under C1).
- **C3 · The shadow loop is an `on_message` consumer.** For each inbound message it writes:
  - one classification row: `is_scheduling` true/false, confidence, model, prompt version, latency, cost;
  - one shadow-reply row: the text the Assistant would send, model, prompt version.
  Both are append-only, dated and enum'd (measurable-by-design); each state change is an event (EOA).
  The LLM goes through the seed provider resolution, with a per-day cost cap.
- **C4 · Evaluation first.** The owner labels a sample in a minimal admin page (agree/disagree per
  message). That gives precision/recall for the classifier before any automation. The page is
  admin-only (access tier: org admin).
- **C5 · Deploy.** The fleet gets one `assistant` instance entry after the agents team's Julia
  entry lands (one owner per line; the second lander rebases). Prod deploy under the owner's free
  pass, through the dev steward. The QR pairing is done by the owner in the UI.

## 4 · Slices (each off `feat/assistant-chatbot`, merged back as D2)

| Slice | Owner agent | Files (disjoint) | Depends on |
|---|---|---|---|
| S1 line policy (seed) | integrations-engineer | `seed/lib/backend/noctusai_lib/integrations/whatsapp/line_policy.py` + wrapper + tests; `waha-instances.yml` schema + render + keeper; KB `INTEGRATIONS/whatsapp.md` new §6a | — |
| S2 product scaffold + WhatsApp mount | backend-engineer (+ frontend for the pairing page) | `products/assistant/**` (scaffold), catalog row | — |
| S3 shadow loop + classifier | ai-engineer | `products/assistant/backend/app/shadow/**`, migration for the two tables + event table, prompt + evals | S2 |
| S4 labelling page | frontend-engineer | `products/assistant/frontend/src/pages/avaliacao/**` | S2, S3 contract |
| S5 LGPD note | legal-advisor (read-only) | `project-history/assistant-chatbot/research/lgpd-personal-line.md` | — |
| S6 fleet entry + deploy | devops-engineer, via the dev steward | `deploy/fleet/waha-instances.yml` (`assistant`), env keys | S1, S2, the agents team's Julia entry |

## 5 · Done for this slice (L-ladder from the spec doc, D46 cut)

- **L0:** the owner scans the QR in the Assistant UI; the line shows WORKING.
- **L1:** an inbound message on the personal number appears in the Assistant store within 10 s.
- **L2:** every inbound message has a classification row and a shadow-reply row.
- **L3:** zero WhatsApp writes, proven: the wrapper's refusal events and WAHA's outbound log for the
  line both show 0 sends, 0 seen, 0 presence over 24 h.
- **L4:** the owner labels ≥50 messages; the report shows classifier precision/recall.

---

## 6 · Revision 2 — after council `a1afa844` (phase0, 6 seats, 35 objections, all accepted; ratified 2026-11-10)

Ledger: `project-history/council/2026-11/a1afa844-de99-4c24-a0b4-820446b100bd.ndjson`. Legal input:
`research/lgpd-personal-line.md`. Where this section and §3–§5 disagree, **this section wins**.

**What the code showed** (the chair verified each point read-only):
- seed `_session_config` forces `noweb.store.fullSync=True` and never sets `markOnline` (`client.py:263-266`); merge keeps existing values (`:212-235`); a prod session once ran `markOnline: true` (`:219-221`).
- `on_message` fires for `from_me` and for the router's own sends (`ingest.py:309-323`), and `notify_message` swallows every exception (`:336-345`).
- groups are stored (`ingest.py:68` drops only broadcast/newsletter).
- the webhook HMAC check is skipped when no secret is passed (`whatsapp_inbox_router.py:405`).
- a raw `WahaClient(...)` exists outside the factory (finance reminders `channel.py:142`).
- the WAHA dashboard and Swagger are enabled (`compose.waha.yml:17-20`).

**Plan revision 2:**
1. **Zero writes, three layers:**
   - (a) edge: a deny proxy in front of the assistant WAHA instance refuses send*/sendSeen/presence/typing/reactions; dashboard and Swagger off; API key only in the assistant env;
   - (b) construction: the Assistant mounts no send/read/backfill routes;
   - (c) seed choke point: `WahaClient._request` refuses writes for a `send: disabled` line (`LineWriteRefused` + event); a keeper bans raw `WahaClient(` outside the seed factory; `channel.py:142` moves to the factory.
2. **Session config is policy:** `markOnline=false`, `store.fullSync=false`, recover/restart re-pair loops off for this line. Checked with `GET /api/sessions` before the QR scan.
3. **Policy v1 = `send: disabled|enabled` + session flags**, keyed by WAHA instance. The fleet file is the ceiling; the receive × send state lives on the connection row next to `app_enabled`, with transition events. Pacing, allowlist, warm-up and the kill switch land with the first live-send slice, built on WAHA signals verified on a throwaway number. The send-field keeper ships in the same commit as explicit defaults for existing entries, plus a written rollback.
4. **Input contract before S3:** inbound only (no `from_me`, no API-sourced), 1:1 chats only (groups, status, broadcast skipped at ingest, through a seed pre-store predicate seam), exclusion list, text only to the LLM (media without text → `skipped`), dedup on the WAHA message id, forward-only from `paired_at`.
5. **Intake queue:** `on_message` only appends a pending intake row. A worker classifies and records an outcome enum (`classified|failed|skipped_budget|skipped_excluded`). P9 (cost cap) is verified before S3; if absent, S3 builds it through the seed provider seam.
6. **S3 = classification only.** The shadow reply moves to a later slice, runs only for `is_scheduling`, records whether it lives in the Assistant or links to the agents runtime, and needs an agents-security review first. **Owner to confirm this re-order.**
7. **Reuse seed organs:** `ai_outputs(kind=classification)`; owner labels as append-only events through the ai_feedback organ; unique on (message_id, prompt_version, model); replay job.
8. **Evaluation:** a written definition of "scheduling", blind labels, stratified sampling, S4 = thin admin page on `AIFeedbackButtons`.
9. **LGPD gates the QR scan** (S6 depends on S5): the legal checklist in `research/lgpd-personal-line.md`, including the owner's written acceptance of the WhatsApp ToS risk.
10. **Webhook HMAC required** on the assistant mount; refuse to start in prod without it.
11. **S6 does not depend on the Julia entry** (a rebase at most).
12. **Allocation (X):** a new product, `products/assistant`. Grounds: the owner's own words (memory `project_assistant_product.md`, 2026-11-09): "a small, simple noc product called **Assistant**". Not daily-life, not a nosnolimiar module.

**First step (before anything touches the personal line):** a throwaway-number WAHA instance (the owner's spare number from D42) with markOnline=false, fullSync=false, the edge deny proxy and the dashboard off. Prove the session config, 24 h of zero presence/seen/sends from WAHA itself (P7), and the real session-state events (P8). The owner scans that QR.

**Owner-gated (the steward does not decide these):** pairing the personal number; the WhatsApp ToS risk acceptance; signing the LGPD artefacts; the shadow-reply re-order.

**Revised slices:**

| Slice | Agent | Scope | Depends on |
|---|---|---|---|
| S1 line policy v1 (seed + fleet) | integrations-engineer | items 1(c), 2, 3, the pre-store predicate seam (item 4), the edge deny proxy + dashboard-off in the waha_instance render, the keepers | — |
| S2 product scaffold | backend-engineer | `products/assistant` scaffold; mounts connections + webhook only, HMAC required; input-contract filters through S1's seam; intake table + events | S1 seam (consume) |
| S3 classifier | ai-engineer | worker, prompt, ai_outputs, cost cap, outcome enum, replay | S2, P9 |
| S4 labelling page | frontend-engineer | admin page on AIFeedbackButtons, blind, stratified | S3 |
| S5 LGPD artefacts | legal-advisor (drafts) → owner/OAB sign | ROPA entry, privacy-notice section, retention spec, LI test, ToS-acceptance text | — |
| S6 probe line, then personal line | devops via the dev steward | throwaway instance first; personal instance after S5 is signed | S1, S2, S5, owner |
