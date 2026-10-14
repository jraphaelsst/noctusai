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
| 2026-10-13 | Where the agent lives | **Build the agent in the `agents` product**, as the reference implementation for agent routing and product ↔ agents communication via API. The page-0 items (persona, provider, runtime, test chat) are the **agent spec**. SW keeps the WhatsApp transport and calls agents over an API. |
| 2026-10-13 | What SW builds | SW pages **mirror Lais and its sub-pages** (Conhecimento, Perguntas essenciais, Envio, Reengajamento, Visitas, …) — a rebuild of Lais' surface over our agent. |
| 2026-10-13 | Number / connection | Owner sets it up in the UI with SW's existing WAHA connection + QR flow. **For now the same number as One Chat** (One Consultoria). Must be **swappable**. |
| 2026-10-13 | Multi-tenant | SW will be sold to another client besides One Consultoria → every personal/tenant item (keys, tokens, numbers, persona, knowledge) is per-org configuration, never hard-coded; designed to swap. |
| 2026-10-13 | Persona name | **Julia** (shown to leads). |
| 2026-10-13 | Provider | **OpenAI now, switchable** by configuration (Anthropic account at its monthly limit until 2026-11-01). |

## Open
- Stage 3 (mechanisms): paused — reading more lead conversations was refused by the session's PII permission check; continue only with the owner's explicit permission rule or anonymised excerpts the owner pastes.
- Security observations to report to Lastro (agency param in Bubble URLs; 4-digit history code) — owner's call.
- Same number as One Chat: senders on the connection's authorized list keep reaching One Chat (operator); everyone else would reach Julia — confirm before switching Julia on (see `specs/julia-agent-contract.md`).

## Done
- Lais nav group live in prod (`67e60888d`, migrations 252 + 253 applied by the release lane, 2026-10-13).
