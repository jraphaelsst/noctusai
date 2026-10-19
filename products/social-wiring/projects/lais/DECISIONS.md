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
| 2026-10-14 | Who Julia answers on the shared number | **Only chats that start after she is switched on** (snapshot of existing chats at switch-on; contract §11.1). |
| 2026-10-14 | Privacy notice | **Create a page, don't propose** — per-org public notice at `/privacidade/<slug>`, default text now, owner refines later (contract §11.2). First message must disclose the virtual assistant and link it (§11.3). |
| 2026-10-14 | Handoff notification | **The connection's owner for now, swappable for an admin.** Never a member-only, corretor, dev or jurídico (contract §11.4). |
| 2026-10-15 | Stage 3 (read conversations) | **Yes.** Owner authorizes reading Lais lead conversations for the mechanism study. Still blocked by the session's PII classifier (needs a permission rule on the owner's side, or anonymised excerpts pasted). Raw text never in the repo. |
| 2026-10-15 | WhatsApp Cloud API (templates, Disparos, owner updates, Meta-form first contact) | **After the owner verifies the app with Meta** (Meta App Review / business verification). Until then WAHA only; waves 12–13 wait on it. |
| 2026-10-15 | Client-history link (Lais' 4-digit code) | **Never a shared code — login required.** Each conversation has its own id/thread link; it opens only for a logged-in user who OWNS that conversation (assigned attendant / connection owner) **or is an org admin/owner**. Other members of the same org cannot open it; users of another org never can (org isolation is absolute). |
| 2026-10-15 | Credit analysis + Google reviews | **Build both** (later waves; credit analysis needs a provider decision + LGPD consent step). |
| 2026-10-15 | Lead distribution (roleta / last attendant / teams) | **SW owns the data and rules** (teams, members, distribution mode, last-responsible); **Julia consumes it** via the agents API at handoff. |
| 2026-10-19 | Listing link Julia sends | **`<site>/imovel/<codigo>`** (e.g. `…/imovel/ONE9551`; the Vista code as stored). Per org in "Meu negócio › Perfil do WhatsApp" → `link_imovel` (default `{site}/imovel/{codigo}`; empty = no link). |
| 2026-10-19 | Meta first contact: "Abordagem comercial" vs "neutra" | **Confirmed for now:** comercial when the lead came by a specific listing (código / form REF), else neutra. **Editable by prompt:** the rule is Julia's prompt section `decisao-abordagem-meta` in the agents studio; SW asks `POST /api/channels/agents/lead-imob/decisoes/abordagem-meta`. Without that section the confirmed rule applies; agents unreachable ⇒ local rule, recorded on the event. |

## Open
- Stage 3 (mechanisms): owner said YES (2026-10-15) but the session's PII classifier still refuses the read (re-tried 2026-10-15, denied). Unblock = a permission rule on the owner's side, or anonymised excerpts pasted into the chat.
- Security observations to report to Lastro (agency param in Bubble URLs; 4-digit history code) — owner's call.

## Done
- Lais nav group live in prod (`67e60888d`, migrations 252 + 253 applied by the release lane, 2026-10-13).
