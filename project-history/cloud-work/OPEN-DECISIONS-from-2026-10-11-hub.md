# Open owner decisions — salvaged from the 2026-10-11 "agent work hub" cloud session

Source: cloud session "Agent work status update" (session_01WKcs1bstuK7BDAgSbVcRWr,
2026-10-11..14). It kept these in a scratchpad ledger inside its own container, which
no longer exists; the transcript was the only copy, so they are absorbed here before
that session is archived (learn-before-archive). Status re-checked 2026-11-09 by the
cloud steward against origin/dev; anything not provable from the tree is marked
**unverified** — the owner ticks or drops it.

## Resolved since (evidence in the tree)

- deploy_verify truncation fix — landed via cloud-work (`fix(deploy_verify): …`, dev 2026-11-09).
- Academia `.eco` domain — on dev (24f9fbcc4); public "Entrar" link removed (owner 2026-11-09, cloud-work-2).
- Social-wiring "delete cliente" — on dev (46f01e398, tombstones lead sources + restaurar). Prod: **unverified**.
- noctusai.com Cloudflare 1033 (2026-10-11, separate session) — prod releases on 2026-10-14
  report 7/7 sites healthy, so the tunnel came back.

## Still open (owner decisions, unverified since 2026-10-14)

1. **Social-wiring org redesign:** one login for many orgs vs one login per org; is the Store org
   Gilson's shop or the product; licences per org; Marina = Admin, new Jurídico role, or Member;
   confirm `feat/invite-accept-ungated` reached prod. (Multi-org S4–S6 shipped 2026-10-14 — may
   answer part of this.)
2. **QuintoAndar / Vista:** go/no-go on the 11 Vista CRM fixes; correct street type (ONE10177 "Abaré");
   share artifact claude.ai/artifact/Tn3GGCHNnF1z2eKxNbdQAb with Agenor and ask if his integration
   reads Quadra/Lote.
3. **Help chat (IgIg):** chat once so `help_chat_conversas` save is confirmed; Giovanna on her org's
   Anthropic key or IgIg's own key.
4. **Store (asleep):** Asaas "Site" = `https://store.noctusai.com` in sandbox + prod (unblocks the
   e2e purchase test); owner for agents migration 017.
5. **Contract walkthrough (social-wiring):** steps 0.3 / 0.4; delete the empty "[P3] 876 Vendedor 1"
   record or not.
6. **Academia (asleep):** fix the 4 unsourced landing numbers; razão social, CNPJ, e-mail; which
   domain is canonical.
7. **Core+seed image swaps / academia-agents cutover:** consent phrases; possibly moot after the
   2026-10-03 redeploy — never confirmed.
8. **Limiar (monica/nosnolimiar):** "Próximo" label on the next arrow; move "Outra ideia" up.
9. **NF-e:** services only, or goods too.
10. **Social-wiring contracts:** PDF or `.docx`; LGPD intake.

## Other loose ends from that hub

- Mac: run `git log origin/dev..` in the primary checkout to see if anything local was never pushed.
- Local session noctusai-1b: `bce607e74` and `9bd6ac926` are on dev; `55ba0c313` (estado-civil) never reached
  origin, but later estado-civil fixes are on dev (49a5fa45e, 60c4301d3) — likely superseded. Prod deploy of
  these: **unverified**. Open decisions: scanned-document option A/B/C, EUROVILLE-535 vs ONE7515.
- `996c64c2` is only a branch-pointer chore (no code); `7c0e5dd4` never reached origin.
- Never reported: triage of 17 failing SW frontend tests; org picker vs spec.
