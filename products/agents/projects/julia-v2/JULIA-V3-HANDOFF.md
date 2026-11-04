> Persisted in-repo 2026-11-04 (moved from the session scratchpad) so the context + timeline survive sessions.

# Julia v3 — handoff to a new session (2026-11-03)

**From:** session noctusai-04 [7fa196], which keeps the Vista API work.
**To:** you. You own Julia from here: integrate → ship → content → evals → tell the owner what to publish.

The full prior transcript is in `/Users/rapha/.claude/projects/-Users-rapha-Documents-repository-NoctusAI-noctusai/0b548c30-61d4-4836-a773-cc017c31a7ab.jsonl`. It is large; grep it, don't read it whole.

The design source of truth is `products/agents/projects/julia-v2/CONTRACT.md` §12 (on dev, 5ca7f4dd4). Each branch appends its deviations in §12.5 / §12.11 / §12.12.

## 0 · First

Run skill `noc-contextualize`. Then read §12 of the contract. Then `memory/user_owner_whatsapp_number_julia.md` and `memory/feedback_integration_keys_in_db_not_env.md`.

## 1 · Owner rules (verbatim intent, all still binding)

**Handoff**
- The handoff report goes to the OWNER first, through a swappable destination; later it goes to the lead's responsável.
- The report is "she summarizing the conversation and the lead, and recommendations". It is sent by WhatsApp and saved on the lead card.
- Julia NEVER schedules visits. She collects the days the lead is available and says a broker will get in touch.
- Julia decides when to hand off, even with incomplete data.

**Data and documents**
- Essentials only. For a visit, CPF is mandatory; RG and email are nice-to-have.
- Any ID doc is accepted (rg/cpf/cin/cnh), as numbers or as a photo "with visible data and proper lights". A photo goes to the extractor.

**Offers**
- Offers go ON, sent to the LEAD, not to the owner; the owner evaluates AFTERWARDS from the report (offered + reaction + recommended).
- ALWAYS 3 per batch; each batch is appended to `imoveis_oferecidos`. Ask whether the lead wants more. When there are none left, say so and offer a human.
- Never repeat a property. The offered codes go in the `imoveis_oferecidos` column.
- Property link pattern: `https://oneconsultoriaimobiliaria.com.br/imovel/ONExxxx`. It's already set in `julia_conhecimento_secoes` perfil_whatsapp (One org).

**Conversation**
- Opening: introduce herself, say the lead showed interest in a property, send the campaign link, confirm. On yes: "similar options or describe what you're looking for?" Similar ⇒ lead-oriented questions. Describe ⇒ questionnaire to build the "ideal" property; the word "ideal" must appear.
- Unhappy lead, her own mistake, or drift ⇒ alert the owner on WhatsApp, apologize, say she's in a testing phase if fase_testes is on, and offer a human.
- The name comes from the campaign form. If it's clearly a business name, ask for the person's name; if it sounds like a real name, use it; if in doubt, ask.
- Julia NEVER accesses external links. She says she can't open them. Done: section `links-externos` and eval `link-externo`; the mechanical lock is on the ag-ferramentas branch.
- Julia avoids ANY political matter (owner, 2026-11-04: "julia is to avoid any political matters"): polite, neutral decline, no opinion, back to the property. Drafted: section `temas-proibidos-politica` (`content-v3/julia-v3-secao-politica.json`) and eval `politica-desvio` (`content-v3/evals/politica-desvio.json`); applied post-deploy with the rest of the content.

**Switches and evaluation mode**
- The agents platform switch stops every Julia in every org. The SW switch stops only that org's Julia. One business never affects another.
- Evaluation mode (agents only): while on, Julia replies ONLY to the allow-listed users. The point is that no lead gets a reply before the owner validates her.
- The owner's number, +5511974693365, lives ONLY in core: `public.noctus_users.telefone`. Every consumer stores a USER ID and reads the phone from core. Never put the owner in julia_staff or authorized_numbers.

**Security**
- No prompt injection via WhatsApp or otherwise; auth before any edit.
- Done: H1 staff-output sanitizer + "Resumo gerado pela IA…" label; H2 security rules are human-only and tokens last ≤30 days; H4 destination change is admin-only + audited + notice to the old phone; M1 media checks + verificado=false; M3 dedupe + 30/h cap.
- OPEN: H3 MFA. 0 factors are enrolled; the owner must enroll, then set mfa_policy enforce for agents + social-wiring.

**Process**
- "Draft everything and tell me when to publish and what to publish."
- Julia is the reference (exemplar) for future agents and for AI generation via the UI.

**Contracts (SW)**
- CPF and/or RG under the signature, only values that exist; never empty data.
- OPEN owner decision: make RG optional for contract parties? Readiness currently requires RG + órgão.

## 2 · Branches (all off origin/dev 5ca7f4dd4; none integrated)

| branch | what | state |
|---|---|---|
| feat/julia-v3-ag-controles | agents migrations 055 (lote 3), 056 (plataforma_controles, fase_testes, modo_avaliacao, avaliacao_usuarios UUID[], RPCs); platform kill; evaluation mode with fail-closed phone lookup from core; `avaliacao_resolvidos` (masked for members) | 71154ac4d — full agents suite 5098 passed |
| feat/julia-v3-ag-ferramentas | 057 thread_alertas; sinalizar_alerta, registrar_documento, relatorio (channels/relatorio.py); identification cpf-required; H1/H2/M3; no-external-links static lock | bf33469be — 1 known fail, test_migration_017_shape, until 055/056 merge |
| feat/julia-v3-ag-fe | fase_testes switch, platform kill danger zone, lote input, evaluation-mode member picker (/api/team) | 0a2cf8507 |
| feat/agents-prontidao | 058 exemplar + geracoes.referencia + 'evals' area; GET /prontidao; publish 409 carries prontidao; PUT /plataforma/agentes/{key}/exemplar; POST draft/skills-biblioteca/atualizar; MCP actions prontidao/atualizar_skills; KB GUIDES/agent-creation.md; skill noc-new-agent | 41a1c51d1 — 5068 passed. Likely conflicts with ag-controles in studio_definitions.py / studio_conteudo_router.py |
| feat/agents-prontidao-fe | ProntidaoPanel, reference picker, exemplar switch, re-pin button | bd19d8616 |
| feat/julia-v3-sw-turno | SW 313 (julia_relatorio_destino modo usuario/responsavel + usuario_id, audit, julia_relatorios, imoveis_oferecidos, cliente_documentos.verificado); envio flow `interno`; reports/alerts/docs; H1/H4/M1/M2/M3; paragraph split fix | 071918b94. **STILL RUNNING in noctusai-04** (subagent): L2 HMAC change + WAHA HMAC scheme fix (below). noctusai-04 will forward its report to you |
| feat/julia-v3-sw-fe | JuliaLigadaCard, report-destination member picker, catalog-source card, RelatorioLeadSection, offered-codes chips | 249b0bab0 |
| feat/core-user-telefone | core 096 noctus_users.telefone (E.164 CHECK) + verify_db_guards probe; PATCH /api/auth/profile telefone; seed `resolve_user_phones` in table_reads.py; AccountSettings WhatsApp field | a89a990b5 + e88cf2cfe. Stray worktree `.claude/worktrees/agent-a1c12f1f84a5657e8` (branch worktree-agent-a1c12f1f84a5657e8) is a duplicate of these commits; clean it up |

**Stays in noctusai-04 (Vista work) — do NOT integrate:**
- `feat/julia-v3-sw-catalogo`: SW 314 julia_catalogo_config (fonte vista|espelho, default espelho), VistaCatalogo, contract CPF/RG signature + IDENTIDADE_NAO_VERIFICADA, Vista key → DB, detalhes-walk sync every 2h.
- `feat/sw-imovel-overlay-crud`.

noctusai-04 will integrate those itself and tell you. Julia works without them: catalog fonte defaults to the mirror.

## 3 · Integrate as ONE train

agents + SW + core go together, because SW's contract test needs agents' channels.v2.json statuses `agente_desligado_plataforma` and `restrito_avaliacao`.

- **Order:** core-user-telefone → ag-controles → ag-ferramentas → agents-prontidao → ag-fe → agents-prontidao-fe → sw-turno → sw-fe.
- **Migrations:** agents 055–058, SW 313, core 096.
- Re-run gates on the merged tip.
- At integrate, switch the `NOC-REMEDIATE[resolve-user-phones]` (SW) and `NOC-REMEDIATE[user-phones-seed-helper]` (agents) local readers to the seed `resolve_user_phones`, or leave them marked.
- Then skill noc-ship: bless → promote → `migrate_product sha=<blessed>` for core, agents, social-wiring → deploy_image → deploy_verify + vps.health + spa_smoke.

## 4 · 🔴 WhatsApp webhook HMAC (prod-breaking if mishandled)

**Facts:**
- WAHA signs with `X-Webhook-Hmac` + `X-Webhook-Hmac-Algorithm` (sha512 default). Verified in noctus-waha-monica /app/dist.
- Our seed scheme `sha256_hex` reads `X-Webhook-Hmac-SHA256`, so it can NEVER match.
- Prod root .env (`/opt/noctus/noctusai/.env`) has NO `WAHA_WEBHOOK_HMAC_SECRET`. The shared WAHA (noctus-services-waha-1) does not sign. noctus-waha-monica signs, and Monica's secret is set; whether Monica's inbound is being refused is unknown, so check after the fix.
- TODAY's prod SW code already refuses unsigned webhooks when Julia is on anywhere and no secret is set. So turning Julia ON before HMAC is set up = deaf inbound.

**The fix being built on sw-turno:**
- seed scheme `"waha"`;
- every WAHA consumer switched to it (SW, the seed whatsapp_inbox_router used by Monica, orbity);
- enforce only when a secret is configured, otherwise a loud ERROR + health flag.

**After deploy, with the owner's OK** (they said "fix what needs fixing"):
1. Generate the secret.
2. Set `hmac.key` on the shared WAHA session webhook FIRST.
3. Then set `WAHA_WEBHOOK_HMAC_SECRET` in the VPS root .env.
4. Recreate social-wiring.
5. Verify one signed inbound.

## 5 · Post-deploy content (agents studio, via `noctus.agents.content`, base_url https://agents.noctusai.com, drafts only)

- `ferramenta`: apply `content-v3/julia-v3-ferramentas.json`.
- `texto`: apply `content-v3/julia-v3-textos.json`.
- Pin Julia's draft skills to the newest versions with `action=atualizar_skills`. New draft versions already exist for ofertar-imoveis, intencao-de-visita and transferir-para-humano.
- Write the generator's `area-evals` section; the draft text is in agents-prontidao's report (grep the transcript for "area-evals").
- Mark Julia exemplar: `PUT /api/studio/plataforma/agentes/julia/exemplar`, platform admin.
- Data:
  - SW report destination = the owner's core user, modo usuario.
  - agents evaluation mode = ON with the owner's user.
  - Set the owner's core phone +5511974693365 (core profile).
  - julia_staff stays empty.

The content payloads are committed next to this file in `content-v3/` (ferramentas, textos, secoes, skills, eval cases, imob-lead v3 edits). The eval helper `qual_api.sh METHOD PATH [BODY]` lives in the original scratchpad (`/private/tmp/claude-501/…/0b548c30-…/scratchpad/`); it only curls `https://agents.noctusai.com` with the token from `~/.config/noctus/agents.env`.
- `qual_api.sh METHOD PATH [BODY]` drives eval cases (token from ~/.config/noctus/agents.env).
- `julia-v3-secoes.json`, `-skills.json`, `-secao-erros.json`, `-secao-links.json` are already applied. Do NOT re-apply `julia-v3-secoes.json`: its `erros-e-insatisfacao` is older than `-secao-erros.json` and would revert it.
- `imob-lead/v3_*.json` are already applied to the imob-lead DRAFT.

**Applied 2026-11-04 ~16:30Z (noctusai-3d, after prod ship 322d6be1d):** `julia-v3-ferramentas.json` (2 create, 6 update), `julia-v3-textos.json` (3 create), `julia-v3-secao-politica.json` (secao `temas-proibidos-politica`), `julia-v3-secao-seguranca.json` (item 8 drops "política" and points at the politics secao, so the rule lives in one place), and eval case `politica-desvio` (21 cases now). Owner core phone set (noctus_users.telefone, E.164).
**Still open:**
- `atualizar_skills` has nothing to move until the owner publishes the library-skill drafts of ofertar-imoveis, intencao-de-visita and transferir-para-humano. Re-pin after that, then run the evals on the resulting hash.
- The SW report destination, agents evaluation mode and the exemplar flag refuse service tokens (`user_required`). The owner sets them logged in.
- `area-evals` is not written yet.

## 6 · Evaluate + publish

- Run Julia's 21 evals (20 + `politica-desvio`) on the CURRENT draft hash (Studio).
- The publish modal must show no blocking items and a score ≥ 0.800 (now also via GET /prontidao).
- Tell the owner exactly what to publish, IN ORDER: (1) the imob-lead standard **v3 draft `82e12707-0073-449e-9ccc-e142e6a5eb52`** (rascunho, lote_ofertas=3, v3 criteria); (2) Julia. NOTE: v2 `ce675a7a` is ALREADY PUBLISHED (2026-11-03 22:46) with lote_ofertas=1, so live offers go out 1 per batch until v3 is published. Migrations 054/055 change only the column DEFAULT. (Verified read-only in prod agents.qualificacao_versoes by noctusai-3d.)
- Remind them to turn Julia on per line (SW switch), with evaluation mode ON first.

## 7 · Owner actions still open

- MFA enroll.
- RG optional for contract parties? (The answer goes to noctusai-04, contract code is on sw-catalogo.)
- WAHA session name is still "One Chat".

## 8 · ADDENDUM (2026-11-03) — items the first version left implicit or out

1. **Off means fully off, open threads included.** Owner: "if its drifting, i need to stop it."
   - Both the platform kill and the org switch must stop replies on OPEN threads too, not only on new leads.
   - At integrate, verify it end to end: an existing thread mid-conversation gets no reply once a switch goes off.
2. **Message blocks.** Longer messages are split on `\n\n` and each block is sent separately (`send_paragraphs`).
   - Bug found: agents parts were sent with `split=False`. It is fixed on sw-turno (`_deliver` flattens through `split_for_whatsapp`).
   - Verify it live during evals.
3. **Doc photo from a lead with no cliente card.** It used to be dropped.
   - Fixed on sw-turno: `garantir_cliente` creates or finds the card; failure ⇒ in-app alert `julia_documento_falhou`.
   - Verify it with a test photo during the evaluation.
4. **Testing-phase wording.** The context line renders `Fase de testes: sim|não`, not "ligada".
   - Section `erros-e-insatisfacao` and eval cases `insatisfacao-fase-testes` / `insatisfacao-sem-fase-testes` use that wording; keep them in sync.
   - fase_testes defaults to TRUE: she tells unhappy leads she's in a testing phase.
5. **Vista ↔ Julia (owned by noctusai-04).**
   - Owner: "imoveis should be searched on their api… Map everything so Julia knows exactly where she has to act on." Vista `/imoveis/listar` is currently EMPTY on Vista's side (owner reporting to Vista).
   - noctusai-04 is building the Vista key-in-DB, a per-code refresh every 2h of the mirror, and VistaCatalogo with `julia_catalogo_config` fonte vista|espelho.
   - Until noctusai-04 says otherwise, Julia stays on fonte=espelho (default). Do NOT flip the One org to `vista`.
   - The "map everything" doc is vista.md §6b, on the sw-catalogo branch.
6. **Security items still OPEN (not built yet).** Surface them to the owner and plan them.
   - **Step-up auth + two-person rule** for publishing an agent and for re-enabling a platform-killed agent.
   - **M4:** a read-only Studio facade for turn data (Studio reads must never reach write paths).
   - **L1:** WAHA (unofficial WhatsApp Web) ToS / ban risk. It's an owner-level business risk; the migration path is the official Meta Cloud API. Just make sure the owner has seen it.
   - **H3 MFA:** after the owner enrolls, set `public.mfa_policy` enforce for agents + social-wiring (seed policy `seed/lib/backend/noctusai_lib/api/auth/mfa/policy.py`; product row → fleet → off).
7. **"Draft everything, tell me when + what to publish"** and **"create missing drafts until the publish modal says ready"** apply to Julia AND to the imob-lead standard.
   - The final message to the owner must list the exact publish order and confirm the modal shows ready: no blocking items, score ≥ 0.800 on the current hash.
8. **Earlier work already shipped to prod — don't redo it.**
   - imob-lead v1 published.
   - Lead origin stored.
   - 500-on-publish fixed.
   - WhatsApp renamed to Julia in the UI.
   - Skills-tab lag + publish button.
   - Qualification parameters filled (imob-lead v3 parameters/criterion edits are in the v3 DRAFT 82e12707; v2 ce675a7a is published with lote 1).
9. **Agent-creation process documentation.**
   - Owner: "Document this complete-agent creation process and update our code, so future agents get built properly and mostly complete."
   - It lives in agents-prontidao (KB GUIDES/agent-creation.md + skill noc-new-agent).
   - After deploy, check that the guide matches what Julia actually has: sections, skills, tools, texts, standard, 20 evals, controls, exemplar.

## 9 · TIMELINE — the owner's decisions in order (UTC; from transcript 0b548c30-…)

Later entries SUPERSEDE earlier ones where they conflict. ⟲ marks a reversal.

| when (UTC) | owner said / decided | outcome |
|---|---|---|
| 11-03 19:21 | "contextualize… zoom in to JULIA and sw… what we still gotta do to have julia wired to a whatsapp number… chatting with my meta campaign leads" | session start |
| 11-03 20:05 | Julia must store **which channel the lead came from** (Meta today, **imovelweb soon**); asked for the leads data structure. The Skills tab lags on every checkbox: fix it and tick the boxes | lead origin built + shipped; skills tab fixed |
| 11-03 20:33 | "build the lead origin fix… then ship it all to prod" | shipped |
| 11-03 20:44 | No publish button for "Decisões": publish it, then add the button | done, shipped |
| 11-03 21:07–21:16 | imob-lead v1 standard drafted | v1 **published** (lote 3) |
| 11-03 21:34 | 500 on publishing Julia: fix. Fill in the qualification parameters. **"imoveis no lote… we only deal with 1 imovel por lote… useless"**. "preencher parametros" on validate | 500 fixed; parameters filled. **Offers are ALWAYS 3 per batch** (owner, 11-04): every batch is APPENDED to `imoveis_oferecidos`, so nothing repeats. There was never a 1-per-batch rule for offers; lote_ofertas=3 (migration 055) |
| 11-03 22:57 | WAHA still says "One Chat": **refresh the session** after drafting evals | session restarted; WAHA's own label still showed "One Chat" (owner-visible name on the phone is Julia) |
| 11-03 23:06 | ⟲ **"let's not ofertar imoveis yet"**: Julia gives US the recommendations first; max 3 per run; no repeats; an "offered imoveis" column on the lead with the refs; tell the lead when there are no more options and offer a human | superseded on the destination only (00:40) |
| 11-04 00:40 | ⟲ **"make the offers on, but not sending the recommendations to me, she sends to the lead."** Lead handed to ME first; handoff number swappable, later → the responsável. Julia never schedules visits; she gathers options; she decides when to hand off; only essentials; CPF mandatory, RG + email nice-to-have; any ID doc, numbers or photo ("visible data and proper lights") → extractor. Vista: search their API; update the docs; "map everything so Julia knows exactly where she has to act"; "I still need to update our db so we can stop fetching from Vista and im not doing it now". Paragraph split on \n\n. Switch: agents = all orgs, SW = that org only ("building it to be scalable and sell it"). Contracts: RG + CPF, whichever exists, never empty. 3 per send, ask for more, none left → offer a human. Link pattern …/imovel/ONExxxx. Opening flow with "ideal". Unhappy lead / mistake / drift → WhatsApp alert to the owner, apologize, testing-phase mention, offer a human; testing-phase switch | CONTRACT §12 + all v3 branches |
| 11-04 ~00:45 | "draft everything and tell me when to publish and what to publish" | drafts written (sections, skills, evals, imob-lead v3 draft 82e12707) |
| 11-04 ~00:47 | The doc-photo drop is real; **"name comes from the campaign form"** | name rules in section `identificacao` |
| 11-04 ~00:48 | The form name may be a business: if clearly a business, ask for the person's name; if it sounds real, use it; if in doubt, ask | in section + eval `nome-empresa` |
| 11-04 ~00:50 | Link pattern `https://oneconsultoriaimobiliaria.com.br/imovel/ONExxxx` | — |
| 11-04 00:55 | "fill in for me" (org site). **Keep the link pattern as a rule for now**; different companies will have different URL patterns later, "we're not dealing with this at this moment" | perfil_whatsapp site set in prod |
| 11-04 00:58 | "create missing drafts needed for julia's publishment. Until u open the publish modal and she's ready to be published. Let me know" | → §5/§6 |
| 11-04 ~01:00 | "draft all. We'll use her as reference for future agents filling and AI generating (AI generating via ui)" | exemplar + referencia (agents-prontidao) |
| 11-04 01:05 | Document the complete agent-creation process + update the code. SECURITY: no prompt injection into the system via Julia or into Julia via WhatsApp; "auth before editing"; research online | GUIDES/agent-creation.md, noc-new-agent; H1–H4, M1–M4, L1–L2 |
| 11-04 01:09 | **Evaluation mode** (agents only): Julia on but replies ONLY to the owner, "not having leads replied before we actually validate her workflow" | ag-controles + ag-fe |
| 11-04 ~01:10 | "My number is +5511974693365, update every location… editable via UI everywhere" | made precise at 01:11 (next row) |
| 11-04 01:11 | **"MY number must be set in noc's app. Everywhere that uses it consumes from noc"**: the number is typed ONCE, in noc, and every product reads it from there. No product stores or types it. | core noctus_users.telefone; consumers store user ids |
| 11-04 ~01:15 | **Julia doesn't access external links**; she tells the lead she can't | section links-externos + eval + static lock |
| 11-04 01:26–01:38 | Vista: we have ONE key, `…644c` (full access); `…bced` was the owner's test key, "we never had a quinto andar key"; keys belong in the DB, not .env | → noctusai-04 (Vista) |
| 11-04 01:39 | HMAC: "please fix what needs fixing" | WAHA scheme fix on sw-turno; enable runbook §4 |
| 11-04 01:43–01:48 | Vista sync every 2h + an MCP tool; UI = mirror of Vista + our own overlay with CRUD; document the data-management UI pattern | → noctusai-04 (Vista) |
| 11-04 01:50 | Julia's work handed to this new session; Vista stays in noctusai-04 | this file |
