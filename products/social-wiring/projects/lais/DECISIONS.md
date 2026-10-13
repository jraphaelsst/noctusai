# lais — decisions and open questions

## Owner answers
| Date | Question | Answer |
| --- | --- | --- |
| 2026-10-13 | Scope of phase 1 | Map everything (pages, buttons, fields, flows, logic, data relations); **no own module**; stages until the owner says "go all the way". |
| 2026-10-13 | Where the study lives | `products/social-wiring/projects/lais/` (next to CoreStudio). |
| 2026-10-13 | Start Stage 2 now? | First no (review S1); then **go Stage 2, including the Bubble edit forms**. |
| 2026-10-13 | Which CRM | The real Lais sends to **Vista** (confirmed in S2: forwarding `vista-v2`). Our module will send **from SW to SW itself**; both run on the same environment. |
| 2026-10-13 | Where our chatbot lives in SW | WhatsApp leaves Conexões and becomes its own nav group, named **"Lais" for now** (renamed later): Lais › Conversas `/lais/conversas`, Lais › Configurações `/lais/configuracoes`; future pages join the group. Shipped on dev `551a64b3b` (+ migration 252, not applied). |
| 2026-10-13 | Transport | **WAHA now, WhatsApp Cloud API later.** |
| 2026-10-13 | Phone number | **Different numbers**: the real Lais keeps its number (→ Vista); ours uses another number (→ SW). |

## Open
- Stage 3 (mechanisms deep-dive: AI reply style from read chats, reengage/visit flows end-to-end) or "go all the way" — owner's call.
- Security observations to report to Lastro (agency param in Bubble URLs; 4-digit history code) — owner's call.
- Release of the Lais nav group (`551a64b3b` + migration 252) — owner's call.
