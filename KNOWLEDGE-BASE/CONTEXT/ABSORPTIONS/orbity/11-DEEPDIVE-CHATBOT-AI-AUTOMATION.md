# 11 — Deep-Dive: Chatbot / AI / Automation CONTENT (knowledge capture)

> The actual battle-tested CONTENT — prompts, flow defaults, scoring constants, message copy — a real agency runs, captured faithfully. **Key provenance finding: the gold is overwhelmingly in CODE (system prompts, default messages, builder presets, thresholds), NOT in seeded DB rows.** There are zero seed `INSERT`s of flows/scoring-rules/templates; `setup-demo-account` plants clients/leads/tasks, never automation content. Per-agency tuned rows (`agency_ai_prompts`, real `automation_flows`, `lead_scoring_rules`) live in their **live DB**, which we don't have. Below = the canonical defaults Orbity ships. All AI via Lovable gateway `ai.gateway.lovable.dev`, model `google/gemini-3-flash-preview`.

## 1. AI assistant prompts (`ai-assist`, `ai-support-chat`)

`ai-assist` = one dispatcher routing 13 `type`s, each `base_prompt (custom||default) + TECHNICAL_INSTRUCTIONS + dateContext`, **forced into a tool-call** (OpenAI function-calling). All pt-BR.

**System prompts (faithful):**
- **`prefill_task`/`improve_task`** — *"Você é um assistente de agência de marketing digital. Extraia os dados estruturados de uma tarefa…"* auto-classifies `suggested_type ∈ {redes_sociais, criativos, trafego}`. `improve_task` = enhance-not-replace (*"MELHORE e DESENVOLVA … NÃO mude o propósito"*).
- **`prefill_post`** — *"Você é um social media manager profissional…"* caption + hashtags + `creative_instructions` (image: headlines/subtítulos/CTAs; reels: "mini roteiro").
- **`report_traffic`** — *"Você é um gestor de tráfego pago profissional. Gere uma mensagem direcionada ao cliente…"* resumo+análise+próximo passo, **WhatsApp-formatted** (`*negrito*`+emojis, R$). Explicitly **to the client**.
- **`campaign_analysis`** — *"Você é um analista sênior de tráfego pago…"* week-over-week trends, pontos de atenção, recomendações. Explicitly **to the gestor** — the *inverse audience* of report_traffic.
- **`analytics_review`** — *"Você é um analista de produtividade de agências…"* structured team review: summary, workload_analysis, bottlenecks, client_alerts, suggestions[], **`performance_score` 1-10** (Crítico 1-3 / Precisa Melhorar 4-5 / Bom 6-7 / Muito Bom 8-9 / Excelente 10), weighted "taxa de conclusão (peso maior), atrasos, distribuição, tarefas sem dono".
- **`content_planning`** — *"Você é um estrategista de conteúdo … planejamento mensal completo…"* across types (educativo/autoridade/conversão/prova social/bastidores/storytelling) × formats (carrossel/feed/reels/stories). **"NÃO gere legendas — a legenda é criada separadamente."** Generates `freq_semanal × semanas`, avoids weekends.
- **`edit_plan_item`** — single-item, "considera o contexto dos demais conteúdos … variar temas e não repetir".
- **`generate_caption`** — *"Você é um social media copywriter profissional…"* knobs: `tone (profissional/descontraido/inspiracional/educativo)`, `platform`, `includeHashtags`, `includeCTA`, `includeContact`.
- **`generate_contract`** — *"Você é um advogado especialista em contratos de prestação de serviços de marketing digital…"* fixed 8-clause skeleton (OBJETO, VALOR/PAGAMENTO, PRAZO, OBRIGAÇÕES DA CONTRATADA/CONTRATANTE, RESCISÃO/MULTA, CONFIDENCIALIDADE, FORO). Input: `client_name/contact, agency_name, monthly_value, duration_months, penalty_percent, custom_instructions`. Valores por extenso.
- **`email_generation`** — *"Você é um copywriter especialista em e-mail marketing…"* HTML only, tokens `{{Nome}}`/`{{Telefone}}`.

**Tool schemas (the real value = field taxonomy):** `extract_task_data`/`extract_post_data` share `title, description, priority(low|medium|high), suggested_type, mentioned_clients[], mentioned_users[], suggested_date(ISO8601), platform, post_type(feed|stories|reels|carrossel|video), hashtags[], creative_instructions`. Crucially extracts **executor names from NL** ("a Laryssa vai fazer"→mentioned_users) and **relative dates** ("entregar sexta","dia 28","amanhã"). `extract_content_plan` → `items[]` each `{day_number, post_date, content_type, format, objective, hashtags}`.

**Orbi (support chatbot, `ai-support-chat`):** one large pt-BR system prompt. Identity *"Você é a **Orbi** 🤖, assistente de suporte … da Orbity"*. A **module-routing / RAG-less navigator** — embeds a markdown table of all 13 modules→routes→descriptions + a per-module cheat-sheet. Rules: PT-BR, emojis, ≤3-4 short paragraphs, **clickable route links** `[CRM](/dashboard/crm)`, and **"Sempre termine com `💡 Dica:` + insight acionável"**. Agency context (name/plan/counts) appended at runtime. Streams SSE.

**Per-agency overridable:** `agency_ai_prompts (agency_id, prompt_type, custom_prompt)` — only the **base persona** is overridable (TECHNICAL_INSTRUCTIONS + tool schema + dateContext always appended). ⚠️ migration ships CHECK `IN ('task','post')` but the function reads 8 types → the other 6 either altered out-of-band or silently fail INSERT (latent bug). `generate_contract`/`improve_task`/`edit_plan_item`/`email_generation` + Orbi = **not** overridable.

## 2. Automation flow playbooks

**No seeded/default flows.** The legacy cadence engine (`whatsapp_message_templates` w/ phase/step_position/delay_minutes, `process-whatsapp-ghosting`/`process-lead-ghosting`) was **fully decommissioned** by `20260523123000` (templates `is_active=false`, controls finished, auto_contact/ghosting=false, old crons unscheduled) → replaced by the per-minute `process-automation-pending-actions`. The new engine is 100% config-driven (authored at runtime), but the **FE builder ships canonical defaults** (`src/components/crm/WhatsAppAutomationFlows.tsx`):

- **Default first message:** *"Olá, {nome}! Vi que você demonstrou interesse em {servico_interesse}. Posso te enviar mais detalhes?"*
- **Default media step:** *"Olá, {nome}! Segue o material sobre {servico_interesse}."*
- **Default skeleton:** trigger `lead_created`, schedule window Mon-Fri 08:00-17:00 America/Sao_Paulo, `outside_window_behavior: schedule_next_available`, single immediate WhatsApp step. **Default delay 10 min. Default condition `source equals "Meta Ads"` (`on_false:stop`). Default action `create_task` "Follow-up comercial". Default branch `lead_replied is_true`.**
- **Trigger vocabulary:** `lead_created, pipeline_stage_entered, lead_idle, whatsapp_message_received, keyword_received, tag_added, owner_changed, task_created, task_completed, meeting_created, proposal_sent, client_created, lead_status_changed, manual`.
- **Step types:** condition, send_whatsapp, send_whatsapp_media, delay, action, branch, end. **Condition fields:** source, status, assigned_to, tags, service_interest, budget, company, lead_replied, custom_field, campaign. **Operators:** equals, not_equals, contains, not_contains, exists, not_exists, greater_than, less_than. **Actions:** create_task, move_lead, add_tag, remove_tag, assign_owner, update_status, notify_team, pause_automation, end_automation.
- **Default stop_rules:** `stop_on_reply:true, stop_on_final_status:true, stop_on_manual_owner_change:false, stop_on_tag_added:"", avoid_conflicts:true` — the "stop chasing on reply / on won-or-lost" discipline baked in by construction.

## 3. Lead qualification rules (`process-lead-qualification` + `lead_scoring_rules`)

No seeded example rules (per-agency per-form). Engine constants (the durable knowledge):
- **Rule shape:** `(form_id, question, answer, score, is_blocker)`, **`score CHECK(-2..2)`** (Likert per Q/A).
- **Matching:** accent-stripped/lowercased/underscore-normalized both sides.
- **Temperature thresholds (canonical cutoffs):** `is_blocker` → `score=-10`, cold (breaks immediately); `≥5 → hot`; `≥2 → warm`; else cold. No rules/custom_fields → `unconfigured`, score 0, cold.
- **Pipeline→Meta CAPI map:** `scheduled→Schedule, proposal→SubmitApplication, won→Purchase`.
- **CRM attention cadence (FE `CRMAlerts.tsx`)** — the human day-thresholds an agency works by: **cold = no contact 30+ days**; **stale/urgent = hot+overdue OR value ≥ R$5000 with no `next_contact`**; follow-up "X dias em atraso" off `next_contact < hoje`.

## 4. WhatsApp templating + conversation logic (`_shared/whatsapp.ts`)
- **Variables — two syntaxes coexist:** `{{key}}` AND `{key}` (single-brace via lookbehind/ahead so `{{x}}` not double-matched), case-insensitive, **unknown key → empty string** (silent). Automation palette: `{nome},{telefone},{email},{empresa},{responsavel},{origem},{etapa},{status},{servico_interesse},{tag},{data_reuniao}`. Billing: `{nome_cliente},{valor}/{valor_formatado},{data_vencimento},{link_pagamento}/{link_fatura}` + Mustache conditional `{{#link}}…{{/link}}`.
- **Content extraction** (`extractMessageContent`) — Uazapi/Baileys normalizer priority: `conversation → extendedTextMessage.text → text → imageMessage.caption → videoMessage.caption → documentMessage.fileName → [áudio]/[sticker]/[localização]`.
- **Phone** — strip non-digits, drop leading 0, **prepend `55` for 10-11-digit locals**, `phoneVariants` for matching.
- **Conversation auto-promotion (`resolveConversation`)** — find-or-create by account_id + any phone variant (race-safe re-read); back-fill `lead_id/client_id/remote_jid`; **context promotion only upgrades** (null or `lead` → `client/billing/system`, never demotes). Contexts `lead|client|billing|system`.

## 5. Content generation + notification copy (real templates)
- **Caption gen** — tones profissional/descontraido/inspiracional/educativo, 3 toggles (hashtags on, CTA on, contact off).
- **Weekly content-plan WhatsApp** (`WeeklySummaryDialog`): *"Olá! Segue o planejamento de conteúdo da semana para \*{clientName}\* 📱"* … `*Semana 1 (dd/MM a dd/MM) – N posts*` … `📅 Seg dd/MM — 🎠 {title}` … *"Qualquer ajuste é só me chamar! ✅"*
- **Billing reminders** (gateway-specific): Asaas *"Olá {{nome_cliente}}, … fatura no valor de {{valor_formatado}} vence em {{data_vencimento}}. Segue o link … Asaas:\n{{link_fatura}}"*; PIX *"… para pagar via PIX, me avise por aqui que envio a chave."*; separate Lembrete (antes/no dia) vs Atraso (cobrança) templates + `discount_days_before`.
- **Trial/verification** (7-day): start *"Olá {name}! Seu período de teste na Orbity começou. Você tem {days} dias…"*; reminders at **2 days** + **1 day**; code *"… use o código: {code}"*.
- **Email templates** (3 ship-with, "Jeito Senseys"): Prospecção B2B, Boas-vindas/Onboarding (briefing→Kick-off→aprovar planejamento), Aviso de Vencimento.
- **Meeting reminder:** *"Olá {clientName}, passando para lembrar da nossa reunião \*{title}\* agendada para hoje às \*{time}\*. Até lá!"*

## 6. What's genuinely valuable to learn
1. **Forced-tool-call extraction over free-text** — schema (field taxonomy) IS the product; prompt is thin. Especially **NL→struct extraction of executor names + relative dates**.
2. **Audience-inverted prompt pairs** (`report_traffic` to client vs `campaign_analysis` to manager from the same data) + WhatsApp-formatting baked into the prompt (paste-ready).
3. **The Orbi pattern** — a module-routing support bot whose system prompt embeds the app nav map + route links + mandatory `💡 Dica` close. Cheap, no-RAG, high-utility; portable to noc help surfaces.
4. **Config-driven automation engine with stop-rules-by-construction** + schedule-window `outside_window_behavior` (don't message at 2am) + the trigger/field/operator/action taxonomy.
5. **Lead-scoring model** — −2…+2 Likert + `is_blocker` short-circuit + 5/2 thresholds + normalized matching + pipeline→CAPI event map.
6. **Dual `{{var}}`/`{var}` templating + Mustache conditionals + silent-unknown-key + context auto-promotion (never demote).**
7. **The default copy itself** — billing cadence (before/on-day/overdue), trial nudges (2d/1d), 3 email archetypes, weekly-plan WhatsApp — real agency-tested templates to adapt, not invent.

## 7. Open questions / code-vs-DB
- **Most operational content lives in the agency's live DB, not the repo** — real flows, real scoring rules, custom personas, tuned templates are all empty of seed data. We see shape + defaults, not the agency's tuned production rows. Getting the real playbooks needs a read of their production DB (which we don't have).
- `agency_ai_prompts` CHECK mismatch (`IN('task','post')` vs 8 read types) — latent bug.
- `setup-demo-account` seeds realistic demo CRM/ops data (12 clients, 25 leads w/ sources facebook_ads/instagram/google_ads/indicacao/linkedin/whatsapp/site, 30 tasks, 15 posts, 7-stage pipeline) — a good **demo-fixture pattern**, no automation content.
- Hardcoded anon JWT in the flow-worker cron `net.http_post` (config-in-migration smell).
- All AI via Lovable gateway (Gemini) — noc would route through `noctusai_lib.integrations.llm` (with cost-logging Orbity lacks).
