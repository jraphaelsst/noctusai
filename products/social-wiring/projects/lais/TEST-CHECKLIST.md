# Live test checklist — Lais module (our own agent, "Julia")

One section per shipped page. Walk it with the owner in prod; tick each line or note what broke.
Contract: `specs/julia-agent-contract.md` (§11 wins over §10, §10 over §1–§9).

## Page 0 — Julia (agent in `agents`, routing in SW) — LIVE in prod 2026-10-14 (2ca3372b5)

### Setup (owner, once per company)
- [ ] Agents › Chaves de IA (`/chaves-ia`): paste the company's OpenAI key → Testar shows success; the key is never shown back in full.
- [ ] Agents › Agent Studio › agent `lead-imob` (`/studio/lead-imob`): provider OpenAI, model `gpt-5.6-terra`; edit persona/instructions; the test chat answers; publish a version.
- [ ] Same agent › Canais tab (`/studio/lead-imob?tab=canais`): create a token → shown once, copy it; the list shows it with label `canal social-wiring · lead-imob:…`; revoke works (then re-create).
- [ ] SW › Lais › Agente (`/lais/agente`), card "Conexão com o Agents": "Colar token do canal" → "Token do Agents salvo"; a wrong token gives "token inválido"; "Editar Julia no Agents" opens `/studio/lead-imob` (not the academia Julia).
- [ ] Card "Aviso de privacidade": fill company name, contact e-mail, WhatsApp → the public page `/privacidade/<slug>` opens without login and shows them; leaving the link empty is refused.

### Switching on (One Chat number)
- [ ] In "Julia nos números do WhatsApp", switch the number to "Julia ligada neste número" → only allowed with a non-empty authorized-numbers list; a snapshot of existing chats is taken (if it fails, nothing switches on).
- [ ] An authorized number writing → still goes to One Chat (operator bot), never to Julia.
- [ ] A chat that existed before switch-on → Julia stays silent.
- [ ] A NEW number writing → Julia answers; her first message is the disclosure "Oi! Eu sou a Julia, assistente virtual da {empresa}. 😊 Como tratamos seus dados: {link}", then the answer.
- [ ] Groups: a message from a group reaches One Chat only if the group is explicitly allowed AND the sender is authorized; Julia never answers in groups.

### Conversas (`/lais/conversas`)
- [ ] Julia's chats show the chip "Julia atendendo" in the header (only on the connection where she is on).
- [ ] "Assumir conversa" (admin only) → chip "Atendimento humano", she stops answering that chat; "Devolver à Julia" → she answers again.
- [ ] "Apagar dados deste contato (LGPD)" → confirm → the lead's conversation data is deleted in `agents`; repeating it is harmless.

### Handoff and limits
- [ ] Lead asks for a human → the "Dono da conexão" gets the handoff notice (or the org owner/admin chosen instead; never a member-only, corretor, dev or jurídico).
- [ ] Spam the chat → at most 10 Julia replies per hour per chat, 30 per minute per number; extra messages are dropped, not queued.
- [ ] With no OpenAI key or the daily cap (5 USD/company) reached → Julia stays silent and SW logs why; One Chat is unaffected.

### Owner decisions to take while testing
- [ ] Julia's instructions/persona final text.
- [ ] Keep the 10/h and 30/min limits and the 5 USD/day cap, or change them.
- [ ] LGPD open items: OpenAI DPA per company; controller contact data on the notice.
