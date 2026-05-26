# 07 — AI Features Context

> **LLM access is platform-level.** Every product calls `noctusai_lib.llm` —
> `chat_completion`, `generate_embedding`, `transcribe_audio`, `analyze_image`.
> The seed framework auto-wires `configure_credentials()` + default
> `LLMConfig` during `create_product_app()`. Products inherit multi-provider
> access (OpenAI real; Anthropic + Gemini guarded stubs) without writing any
> LLM plumbing. Credential resolution is 3-tier (org_settings →
> platform_settings → env). Full reference:
> `KNOWLEDGE-BASE/CONTEXT/04-SHARED-LIBRARY.md` (LLM section).
>
> **LGPD contract** (non-negotiable): clinical free text never lands in a
> response cache. Every Therapy `chat_completion` call passes `cache=False`
> — see `KNOWLEDGE-BASE/CONTEXT/PATTERNS/security/lgpd.md` + `LGPD-WARNINGS.md`.
>
> ERP: `products/erp-imobiliario/backend/app/` · defaults: gpt-4o-mini + text-embedding-3-small
> Therapy: `products/therapy-platform/backend/app/` · defaults: gpt-4o (override) + Whisper

## ERP AI Service (`services/ai_service.py`) [also: E4 follow-up draft — ai-expansion Phase 15, 2026-04-24; E2/E6/E7/E8/E10 P1 indicators — ai-expansion Phase 6, 2026-04-25]

**E4 — Client follow-up draft.** `draft_follow_up(cliente_nome, last_interaction_days, etapa_atual?, imovel_interesse?, observacoes?, org_id?)` → `{channel: "whatsapp", subject: None, body: str}`. Called when a lead has no activity for > 14 days. Endpoint: `POST /api/ai/leads/{lead_id}/follow-up-draft` with body `{cliente_id, imovel_interesse?}`. Frontend hook: `useFollowUpDraft()`. Pulls lead name / stage / notes from `clientes` and computes `days_since_activity` from `updated_at`. `PROMPT_VERSION_FOLLOW_UP = "erp-followup@v1"` for cache invalidation. `cache=True` (deterministic `temperature=0`). Graceful degrade: returns empty body on `(LLMNotConfigured, RuntimeError)`.

### Phase 6 P1 indicators (persist to `erp.ai_outputs` via `noctusai_lib.ai.persist_output`)

All five services follow the same shape: input → `chat_completion(cache=True, org_id=...)` → AIOutput-shaped dict. The router wraps the dict in `AIOutput(...)` and persists; reads come from the seed `/api/ai/outputs` standard router (opted in via `standard_routers=["...", "ai_outputs"]` in `main.py`).

| Code | Service | Endpoint | ref_type | Kind | Prompt version |
|---|---|---|---|---|---|
| **E2** | `classify_whatsapp_intent(message_text, cliente_nome?, org_id?)` | `POST /api/ai/whatsapp-intent {cliente_id, message_text, cliente_nome?}` | `cliente` | `classification` | `erp-whatsapp-intent@v1` |
| **E6** | `score_certidoes(cliente_nome, certidoes, org_id?)` | `POST /api/ai/clientes/{cliente_id}/certidoes-score` | `cliente` | `score` (0-100) | `erp-certidoes-score@v1` |
| **E7** | `generate_metas_coach_tip(user_nome, progresso_percent, dias_restantes, eventos_recentes?, org_id?)` | `POST /api/ai/metas/coach-tip {user_id, user_nome, progresso_percent, dias_restantes, eventos_recentes?}` | `user_metas` | `narrative` | `erp-metas-coach@v1` |
| **E8** | `assess_photo_compliance(imovel_descricao?, fotos, org_id?)` | `POST /api/ai/imoveis/{imovel_id}/photo-compliance` | `ativo` | `flag` (ok/revisar/reprovado) + 0-100 score | `erp-photo-compliance@v1` |
| **E10** | `score_search_relevance(query, imovel_data, org_id?)` | `POST /api/ai/search-relevance {imovel_id, query}` | `ativo` | `score` (0-1 relevance) | `erp-search-relevance@v1` |

Each service short-circuits on empty input (no LLM call) and returns a fallback `_empty_output()` dict on LLM unavailability. Frontend hooks (`useWhatsAppIntent`, `useCertidoesScore`, `useMetasCoachTip`, `usePhotoCompliance`, `useSearchRelevance`) live in `hooks/useAI.ts` and invalidate `['ai_outputs', refType, refId]` on success so the matching `<AIIndicator/>` rerenders. Read-side wires shipped: `<AIIndicator refType="cliente" refId={...}/>` on `ClienteDetalhes.tsx`; `<AIIndicator refType="ativo" refId={...}/>` on `ImovelDetalhes.tsx`. Migration: `021_ai_outputs.sql` (RLS via `org_id` auto-fill from `public.current_org_id()`).

---


Three capabilities via `POST /api/ai/*`:

| Endpoint | Model Temp | Input → Output |
|----------|-----------|----------------|
| `/generate-description` | 0.7 | Property data → `{ titulo_sugerido, descricao }` |
| `/lead-score` | 0.3 | Client profile → `{ score (0-100), justificativa, recomendacao }` |
| `/suggest-price` | 0.3 | Property + comparables → `{ preco_sugerido, faixa_min, faixa_max, analise }` |

API key resolution: `resolve_credential("openai_api_key", org_id)` → org_settings → platform_settings → env.

## Embedding Service (`services/embedding_service.py`)

Model: text-embedding-3-small (1536d). Every ativo gets **two vectors**:
- `embedding` — what the ativo IS (profile: description, location, specs)
- `embedding_interesses` — what the ativo WANTS (from `interesses` JSONB array)

Auto-triggered on POST/PATCH `/api/ativos`. Gracefully skips when `OPENAI_API_KEY` is missing.

## Matching Service (`services/matching.py`)

**Bilateral matching**: both sides must want what the other offers.
- B→A: `cosine(imovel.embedding, permuta.embedding_interesses)` — does the permuta want this?
- A→B: `cosine(permuta.embedding, imovel.embedding_interesses)` — does the owner want this?

### Flow

```
For each (imovel, permuta) pair:
  1. Skip same-owner and inactive
  2. Compute structured sub-scores: region (30), price (25), specs (20)
  3. Hard filters (_passa_filtros_minimos):
     - Bilateral A→B and B→A checks
     - Type-specific gates (same state for permuta_imovel; explicit auto interest for permuta_automovel)
     - Must score meaningfully in ≥2 of 3 categories
  4. Interest alignment (15) + listing quality (10)
  5. Bilateral embedding similarity (threshold: 0.60 per direction)
  6. Final score: embedding-enhanced composite if available, else pure rule-based (100 pts max)
```

### Composite Formula (with embeddings)

| Component | Weight |
|-----------|--------|
| Bilateral embedding similarity | 40% |
| Price compatibility | 25% |
| Specs compatibility | 20% |
| Interest alignment | 15% |

**Upsert protection**: matches marked `aceito`/`rejeitado` are never overwritten by re-generation.

### Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /api/matching/gerar` | Generate matches (single or full scan) |
| `POST /api/matching/embed` | Embed single ativo |
| `POST /api/matching/embed-batch` | Batch embed unembedded ativos |
| `GET /api/matching` | List matches with filters + ativo summaries |
| `PATCH /api/matching/{id}` | Update match status |

## Therapy AI Pipeline

Orchestrated by `ai_pipeline` service:
1. **Transcription** (Whisper) → text from session audio
2. **Summary** (GPT) → dual-track: therapist-facing clinical + patient-facing accessible
3. **Longitudinal** (GPT) → cross-session analysis (min 4 sessions, second person "Você...")
4. **Crisis detection** → keyword analysis on content, severity assessment

Audio kept 24h after transcription for download, then auto-deleted. Summary versions: infinite retention. Prompt hierarchy: per-therapist > per-clinic > global default.

## Core C2 — Weekly audit-log narrative digest (`services/audit_digest_service.py`) — ai-expansion Phase 9, 2026-04-25

First adopter of the P3 pattern (`noctusai_lib.email.digest.send_digest`) outside of ERP metas. Aggregates the last `period_days` (default 7) of `public.audit_logs` for an org → counts per `action` + per `user_id` + a privileged-action highlight list → asks `chat_completion(cache=True, temperature=0)` for a 3-paragraph PT narrative → renders `(html, text)` inline (consistent with `metas_digest_service.py`) → fans out via `send_digest` to every `noctus_users.role='admin'` recipient in the org.

| Endpoint | Behavior |
|---|---|
| `POST /api/admin/audit-digest/{org_id}?period_days=7` | Build + send to all org admins. Returns `{sent, results[], summary, subject}` with one `DigestSendResult` per recipient. Platform-admin only. |
| `GET /api/admin/audit-digest/{org_id}/preview?period_days=7` | Build + return rendered html/text + recipient list + summary. No send. Platform-admin only. |

LGPD posture: only metadata enters the prompt (action / resource_type / user_id prefix, never raw user-content text); cache-safe at `temperature=0`. Privileged actions hardcoded in `_HIGH_PRIORITY_ACTIONS` always bubble into the highlight list (`user.role_changed`, `user.deleted`, `billing.subscription_canceled`, `license.revoked`, `api_key.revoked`, `settings.security_changed`). `prompt_version = "core-audit-digest@v1"`. Trigger: cron / n8n posts to the endpoint weekly (typically Monday morning).

**Rendering choice:** inline f-string HTML (mirrors metas digest reference adopter). Jinja was deliberately rejected by Phase 4 as scope creep; if a third digest adopter shares layout shell with these two we'll formalize then per the recurrence rule.

## Personal Finance AI Service (`services/ai_service.py` + `services/monthly_narrative_service.py`) — ai-expansion Phases 7 + 10, 2026-04-25

**Phase 7 P1 indicators** — both persisted to `"personal-finance".ai_outputs` via `noctusai_lib.ai.persist_output` and read by `<AIIndicator refType="transacao" refId={t.id}/>` on `Transacoes.tsx`. Standard router opt-in: `standard_routers=["health", "notificacoes", "team", "ai_outputs"]` in `app/main.py`.

| Code | Service | Endpoint | Kind | Prompt version |
|---|---|---|---|---|
| **P1-opp** | `categorize_transaction(descricao, valor, tipo, comerciante?, available_categories?, org_id?)` | `POST /api/ai/transacoes/{transacao_id}/categorize` | `classification` | `pf-categorize@v1` |
| **P3-opp** | `flag_recurring_expense(descricao, valor, tipo, similar_history?, org_id?)` | `POST /api/ai/transacoes/{transacao_id}/recurring-flag` | `flag` (recorrente / pontual / incerto) + 0-1 score | `pf-recurring@v1` |

`categorize_transaction` matches its returned label against the user's existing `categorias` rows by name (case-insensitive) and returns `matched_categoria_id` so the UI can offer a one-click "apply suggestion" action. Both services `cache=True` + `temperature=0` (transactional metadata is not personal narrative — caches across the same org freely). Frontend hooks: `useCategorizeTransaction`, `useRecurringFlag` in `frontend/src/hooks/useAI.ts`. Migration: `006_ai_outputs.sql`.

**Phase 10 P2-opp monthly financial narrative** — second P3 digest adopter platform-wide. `services/monthly_narrative_service.py::build_narrative` aggregates the past `period_days` (default 30) of `transacoes` → receita/despesa totals + top categorias + savings rate → `chat_completion(cache=True, temperature=0)` for a 3-paragraph PT narrative (panorama / observações / dica) → renders `(html, text)` via inline f-strings → returns `(Digest, summary_dict)`. `send_monthly_narrative` adds delivery via `noctusai_lib.email.digest.send_digest`.

| Endpoint | Behavior |
|---|---|
| `GET /api/ai/monthly-narrative?period_days=30` | Build + return digest body + structured summary (no email). Used by the dashboard card via `useMonthlyNarrative` hook. |
| `POST /api/ai/monthly-narrative/send {recipient, period_days}` | Build + send via Resend (cron-friendly). Returns `{sent, dry_run, external_id, error, subject, summary}`. |

LGPD posture: amounts + category names enter the prompt; `comerciante` deliberately omitted. `prompt_version = "pf-monthly-narrative@v1"`.

## Daily Life Today's Brief (`services/daily_brief_service.py`) — ai-expansion Phase 13, 2026-04-25

D1 today's brief — first adopter of the **P4 LayoutEnrichment.aiBadge** pattern (shipped by Phase 5). Aggregates today's data for the calling user:

- Tarefas with `data_vencimento = today` and status in (pendente, em_progresso)
- Eventos with `inicio` between today's 00:00 and 24:00
- Active habits (`metas.tipo='habito'`, `status='ativa'`, `frequencia='diario'`) with no check-in for today
- Yesterday's `concluida` task count (for the "concluiu N ontem" comparison line)

Builds two outputs:
- `chip` — ≤32 char compact summary like `"3 tarefas · 2 hábitos · 1 evento"` or `"tudo livre hoje"` when nothing is scheduled. Plural/singular Portuguese forms.
- `summary` — 1-2 sentence PT narrative (≤200 chars, hard-truncated at word boundary) via `chat_completion(cache=False, temperature=0)`. **`cache=False`** matches D6 weekly-review and D4 note-extraction — Daily Life data is personal-narrative-adjacent.

Endpoint: `GET /api/ai/daily-brief` (caller-scoped via `get_current_user`). Frontend hook: `useDailyBrief()` in `frontend/src/hooks/useAI.ts` (TanStack `useQuery`, 15-min staleTime, `retry: false`). Component: `<DailyBriefBadge>` in `frontend/src/components/DailyBriefBadge.tsx` mounted via `useLayoutEnrichment.aiBadge` in `App.tsx`. Auto-hides when the hook returns `error`/`undefined`.

`prompt_version = "daily-life-daily-brief@v1"`.

## Daily Life Weekly Review (`services/weekly_review_service.py`) — ai-expansion Phase 11, 2026-04-25

D6 Friday weekly review — third P3 digest adopter. Aggregates the past `period_days` (default 7) of `tarefas` (status counts) + `metas` + `checkins` (per-habit streaks) + `notas` (count only — content stays personal) + `sessoes_foco` (focus minutes) → asks `chat_completion(cache=False, temperature=0)` for a 3-paragraph PT review (panorama / observação / recomendação) → renders `(html, text)` → fans out via `send_digest`.

**`cache=False`** — Daily Life data is personal-narrative-adjacent (matches D4 note-extraction posture in this same product); two users with identical aggregates should not collide cache keys. Notas count is the only signal that surfaces the existence of personal text — content never enters the prompt.

| Endpoint | Behavior |
|---|---|
| `GET /api/ai/weekly-review?period_days=7` | Build for caller. Returns body + summary. No send. Hook target. |
| `POST /api/ai/weekly-review/send {recipient, user_id?, user_label?, period_days}` | Build + send via Resend (cron-friendly). 403 if `user_id` differs from caller (cross-user requires admin token). |

`prompt_version = "daily-life-weekly-review@v1"`.

## Daily Life AI Wrappers (`services/ai_service.py`) — ai-expansion Phase 16, 2026-04-24

**D4 — Note-to-task extraction.** `extract_tasks_from_note(note_content, org_id?)` → `[{title, due_hint?}, ...]`. Endpoint: `POST /api/notes/{note_id}/extract-tasks` (auth-scoped to note owner). Frontend hook: `useExtractTasksFromNote()` in `src/hooks/useNotas.ts`. **`cache=False`** — note content may be personal (journal entries) and must NOT hash into a shared cache key. Caps at 10 tasks. Empty content / whitespace-only → returns empty without calling LLM. `PROMPT_VERSION_EXTRACT_TASKS = "daily-life-extract-tasks@v1"`. Service never creates task records — UI confirms each item before promoting to a real task.

---

## Mailing AI Wrappers (`services/ai_service.py`)

Shipped in `ai-expansion` Phase 14 (2026-04-24). Five `chat_completion`-backed wrappers exposed via `/api/ai/*` + typed frontend hooks in `src/hooks/useAI.ts`. All use `cache=True` for deterministic outputs. Low LGPD (marketer-authored copy only; no contact PII in prompts).

| Feature | Service fn | Endpoint | Hook | What it does |
|---|---|---|---|---|
| **M1 Subject gen** | `generate_subjects(summary)` | `POST /api/ai/subjects` | `useGenerateSubjects()` | Returns 3–5 `{text, tone}` variants (urgência / curiosidade / direto / social / benefício). |
| **M2 Template draft** | `draft_template(prompt)` | `POST /api/ai/template-draft` | `useDraftTemplate()` | Returns responsive HTML body (heading + bullets + CTA; no `<html>`/`<body>` shell). |
| **M5 Re-engagement** | `reengagement_variants(context)` | `POST /api/ai/reengagement` | `useReengagementVariants()` | Returns 3 `{tone, subject, body_html}` variants for inactive segments. |
| **M6 Deliverability** | `review_deliverability(html, subject?)` | `POST /api/ai/deliverability` | `useDeliverabilityReview()` | Returns `{findings: [{code, severity, message}]}`. Codes: risky_phrasing / missing_unsubscribe / link_heavy / all_caps / misleading_subject / tracking_only_urls. |
| **M7 Translation** | `translate_template(html, lang)` | `POST /api/ai/translate` | `useTranslateTemplate()` | Translates PT → EN/ES/FR preserving HTML + `{{placeholders}}`. |

Per-feature `PROMPT_VERSION = "mailing-ai@v1"` bumps invalidate the response cache.

Graceful degradation: every service catches `(LLMNotConfigured, RuntimeError)` and returns an empty/pass-through default so the UI can render a no-AI fallback. Follow-up (deferred): per-page integration — page-level buttons to invoke the hooks; currently `src/hooks/useAI.ts` is consumable but no specific editor page wires it yet.

### M4 — Campaign debrief (ai-expansion Phase 12, 2026-04-25)

Fourth P3 digest adopter. After a campaign finishes (`status='enviada'` or `completed_at` set), `services/campaign_debrief_service.py::build_debrief` aggregates `mailing.send_logs` (per-status counts) + `mailing.link_clicks` (top URLs) → computes sent / delivered / open / click / bounce rates → asks `chat_completion(cache=True, temperature=0)` for a 3-paragraph PT debrief (panorama / what worked / recommendation) → renders `(html, text)`. `send_campaign_debrief` adds delivery via `send_digest`.

| Endpoint | Behavior |
|---|---|
| `GET /api/ai/campaigns/{campaign_id}/debrief` | Build for campaign. Returns body + summary. 404 if campaign not found. |
| `POST /api/ai/campaigns/{campaign_id}/debrief/send {recipient}` | Build + send via Resend. Manual fallback / re-run path. |

**Auto-trigger (2026-04-27, `auto-trigger-campaign-debrief` project).** `services/send_service.py::_finalize_campaign_if_done` runs after every batch in `_send_batch` (success, dry-run, or failure path). When zero `send_logs` rows remain in `status='queued'` for the campaign, it atomically flips `campaigns.status` from `enviando` → `enviada` (`.neq('status', 'enviada')` is the idempotency boundary — exactly one caller wins) and dispatches `send_campaign_debrief` with the recipient resolved from `campaigns.debrief_recipient` (override) or `auth.users` lookup by `created_by`. Failures during recipient lookup or debrief send are logged at WARN and swallowed; the campaign is finalized regardless. The manual `POST .../debrief/send` endpoint stays as the canonical re-run path.

Recipient emails NEVER enter the prompt; per-link click counts are anonymous totals. `prompt_version = "mailing-campaign-debrief@v1"`.

### M3 — Contact segmentation (ai-expansion Phase 8, 2026-04-25)

Persisted P1 indicator. Shipped as `services/segmentation_service.py` + `POST /api/ai/segment-contacts` + `useSegmentContacts()` hook.

Pipeline: build a per-contact embedding text (`nome | empresa | tags | custom_fields`) → `noctusai_lib.llm.generate_embedding` (`text-embedding-3-small`) per contact → pure-Python greedy cosine clustering (`threshold=0.78`, `max_segments=8`, no sklearn dep) → one `chat_completion(cache=True, temperature=0)` per cluster to produce a 2-3 word PT label + ≤18-char uppercase chip → persist N rows (one per contact) to `mailing.ai_outputs` via `noctusai_lib.ai.persist_output`. Read side: `<AIIndicator refType="contact" refId={c.id} hideIcon/>` in the email cell of `Contacts.tsx`. Trigger: header "Segmentar" button on `Contacts.tsx`.

Body shape: `{list_id?: string, threshold?: number, max_segments?: number}`. Without `list_id`, segments all `status="active"` contacts in the org (capped at 500). Returns `{persisted: AIOutput[], segmented: int}`.

LGPD: contact emails are PII but never enter the LLM prompt (`_build_contact_text` uses only nome / empresa / tags / custom_fields keys; falls back to `email=...` only when nothing else is available — flagged in the inline doc-comment). The naming `chat_completion` sees aggregated tags + empresa, not emails. `cache=True` is safe at the cluster-naming level (output tied to cluster shape, not individual contact PII).

Migration: `002_ai_outputs.sql` creates `mailing.ai_outputs` with `org_id` defaulting to `public.current_org_id()` (Postgres forbids subqueries in DEFAULT, so we lean on the platform helper instead of inlining the JWT subquery used in the rest of `mailing.*` RLS). `prompt_version = "mailing-segment@v1"`.
