# WAHA anti-ban gates for the Assistant's spare number (noc-research run 1, 2026-11-09/10)
Short: WhatsApp gives rules, no numbers. Unofficial client = ToS breach by itself (temp/permanent ban or device-linking loss). Bulk/auto-messaging forbidden; ML classifier bans; blocks/reports cut limits. All numbers below are vendor/community heuristics (WAHA, Green-API, Whapi, GitHub), not WhatsApp's. Numberless gates matter most: allowlist-only replies, never initiate, no groups, no links by default, never restart/re-pair on a warning.

| Gate | Value | Conf | Sources |
|---|---|---|---|
| Warm-up | ≥24h after registration before QR; d1-3 receive only + manual use (owner chats incl. audio/files); from d4 replies only ~1/2h; ramp 12→100/day over d4-11; "settled" after 25-30 clean days; ban resets | low | green-api (T4), whapi (T4) — agree on wait-before-QR |
| Rate | random 30-60s gap per send; ≤4 msgs/h per contact; ≤2/min, ≤30/h, ≤100/day per line (cap during warm-up); quiet hours | low-med | waha.devlike.pro how-to-avoid-blocking (T1 vendor); whapi; per-line hour cap = agents-security proposal |
| Reply-only | never initiate; known-contact send = owner-approved + owner-triggered, one short message, ≤1 new conversation/day | high | WAHA ("never initiate", "only reply"); WhatsApp Terms (e) |
| Allowlist | strangers 0 replies / 0 LLM turns; classify by number, never pushName | high | canon §6.2; OWASP LLM10 |
| Media | no outbound media except owner-requested, ≤1 per reply | unverified (house proposal) | none |
| Links | 0 by default; https + allowlisted domain only; never in first message | med | WAHA; whapi; OWASP LLM05 |
| Repetition | never same text twice in 24h to different chats; hash outbound; 3 identical hashes in window → halt | med | WAHA, green-api, whapi |
| Groups | drop group/status@broadcast/newsletter/broadcast before LLM; never join/create; group-admin via whatsapp_groups bucket 0.2 rps | med-high | Baileys #1869 (T4); canon §6.3 |
| Presence | sendSeen → startTyping → random wait scaled to length → stopTyping → send | med | WAHA |
| Session | no restart/logout/re-pair on 463/475; restrictions lift alone; one instance per session | med | WAHA |
| Ban warning | FIRST/SECOND_WARNING, 463/475 → kill switch: stop all outbound except owner replies, alert owner, no reconnect; 5-10 spam tags ≈ ban | med | WAHA; Baileys #1392 |
| Flooding | unknown sender → store-only (assistant: drop); allowlisted ≤20 turns/h, ≤4k chars input; fail closed if limiter store down | high gate / low numbers | OWASP LLM10; canon §5 |
| Injection→spam/links | no model-chosen destination; reply target = inbound chat id; third-party sends need owner approval; filter links in output | high | OWASP LLM01/05/06; canon §3 |
| Get-reported | follows from allowlist + reply-only + no groups + STOP handled without the model | high | canon §6.5; Business Policy |
| Bot loops | write outbound record before fromMe echo; halt chat after >6 bot replies in 2 min without human gap or repeated hashes; alert owner | high gate / low threshold | canon §5 detectar_loop |

Fix-on-contact: shared "whatsapp" bucket = 5 rps / burst 10 (KB INTEGRATIONS/whatsapp.md ~322) — far above these; Assistant needs its own slow bucket.

Key claims (read 2026-11-09): unofficial apps → ban/link loss (faq.whatsapp.com/1217634902127718) verified; Terms forbid bulk/auto-messaging/automated access verified; "not designed for automated or bulk"; ML bans; receiving many msgs doesn't ban (faq 1104252539917581) verified; Business Policy (updated 2026-09-23) verified but binds Business not personal WAHA; WAHA figures verified-as-WAHA-advice, unverified as real thresholds; warm-up unverified (two non-independent T4); ~300 new-contact convos → 463 timelock (waha#1992 contributor) unverified; "general-purpose-bot ban from 2026-01-15" (canon §6.7) UNVERIFIED — not on the policy page; Oct-2025 ban wave hit non-bots (Baileys #1869) contested; OWASP mitigations verified via WebFetch summariser (recheck wording).
What would change it: a WhatsApp numeric primary; WAHA page change (re-read <180d); move to Cloud API; number history (virtual/previously banned); owner letting the bot initiate.
Register rows: faq.whatsapp.com confirmed; whatsapp.com/legal graded T1; whatsappbusiness.com graded T1; waha.devlike.pro confirmed; green-api.com T4; support.whapi.cloud T4; github.com unverified; genai.owasp.org T1.
