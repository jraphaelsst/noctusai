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
  inbox routers exactly as Monica does (`products/monica/backend/app/routers/whatsapp_router.py:29-34`),
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
