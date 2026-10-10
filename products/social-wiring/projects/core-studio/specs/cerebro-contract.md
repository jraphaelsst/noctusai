# Segundo Cérebro — build contract v1 (2026-10-09)

> Drafted by the architect advisor, adopted and **amended by the tech-lead in §10** (§10 wins over
> every other section where they differ — mainly: transcription goes through the shared
> `transcription-contract.md` product layer, not a module-local table). Shape follows
> `pesquisa-contract.md`.

Behaviour reference: `pesquisa-cerebro-spec.md` §3, §4 (Brain, BrainQuestion), §5.5, §6.3, §9
(live-verified, wins over §3); `mechanisms.md` §3; `page-map-v2.md` §6–§9; `DECISIONS.md`.
Where this file differs from CoreStudio, this file wins (§9).

**Scope v1:** brain list per marca (4 **Sistema** + **custom**); content editor (markdown, file
import, rename/delete custom); questionnaire for Sistema brains (typed or **voice** answers,
**non-blocking AI review**, **synthesis** into content); **profile bio** per marca (headline
"Núcleo de Influência" source); **Minhas extrações** (pasted text → applied to N brains; URL
sources per §10). Headline/roteiro consumption is a later module.

## 1 · Owner decisions encoded

- Brains per marca (`social_wiring.marcas`), brand switcher shared with Minha Pesquisa.
- 4 Sistema brains — Núcleo de Influência, História de Criação, Histórias de Vida do Especialista,
  Método do Especialista — questions verbatim from spec §9 / page-map §8; created lazily and
  idempotently per marca; cannot be renamed or deleted. Custom brains: free markdown, no questionnaire.
- Núcleo de Influência for headlines = the **profile bio** (`cs_marca_perfil.bio`), separate from
  the brain of the same name.
- **AI review never blocks**: per answer the AI suggests verdict (`approved`/`rejected`) + reason +
  optional improved answer; user accepts or dismisses; synthesis is always allowed.
- **Voice answers**: recorded per question, transcribed via the shared transcription service.
- **Minhas extrações kept**.
- Synthesis via `noctusai_lib.integrations.llm.chat_completion` behind an injectable seam; both
  prompts DRAFT for owner validation, aligned with Método Audience (`prompts/methodology.py`).

## 2 · Data model (one migration; number from `noctus.dev.scaffold_migration`, never hand-picked)

All `org_id` tables: RLS like `cs_research_items` (`org_id = (SELECT public.current_org_id_for('social_wiring'))`
+ service_role ALL). Static tables: authenticated select-true + service_role ALL. `updated_at`
triggers use `social_wiring.set_updated_at_media_creation()`. Forward-only, idempotent, same
`current_org_id_for` guard as 217.

### `cs_brain_templates` (static, seeded)
`slug` text PK (`historia-de-criacao`, `historias-de-vida`, `metodo-do-especialista`,
`nucleo-de-influencia`) · `name` (verbatim: História de Criação · Histórias de Vida do Especialista ·
Método do Especialista · Núcleo de Influência) · `description` · `sort_order` (1 História de Criação,
2 Histórias de Vida, 3 Método, 4 Núcleo).

### `cs_brain_questions` (static, seeded)
`id` text PK `<template_slug>.<NN>` · `template_slug` FK · `position` 1..N (group = `(position-1)/3`) ·
`text` verbatim · `hint` NULL (captured for Núcleo only, from
`captures/crawl-2026-10-06/pages/html__cores_questions_3081.html`) · `optional` bool (Núcleo 02, 04,
07, 13, 15 — DRAFT). Counts: Núcleo 15, História de Criação 9, Histórias de Vida 4, Método 7.
Seed SQL for both static tables is **generated** by `app/modules/media_creation/cerebro_templates.py :: seed_sql()`;
a test asserts the migration carries that exact text (same pattern as `pesquisa_variables.py`).

### `cs_brains`
`id` uuid PK · `org_id` · `marca_id` FK CASCADE · `kind` CHECK (`sistema`,`custom`) with
CHECK `(kind='sistema') = (template_slug IS NOT NULL)` · `template_slug` NULL FK · `name` 1..80 trimmed ·
`content` text NOT NULL default '' ≤ 200 000 (CHECK) · `content_version` int default 0 (bumped on
every write) · `synthesis_status` CHECK (`idle`,`processing`,`error`) default `idle` ·
`synthesis_error` · `synthesis_started_at`, `synthesized_at` · `created_by`, `created_at`, `updated_at`.
Unique `(marca_id, template_slug) WHERE kind='sistema'`; unique `(marca_id, lower(name))`; index `(marca_id, created_at)`.

**Function** `social_wiring.cs_brain_append(p_brain uuid, p_org uuid, p_block text) RETURNS int` —
`content = CASE WHEN btrim(content)='' THEN p_block ELSE content || E'\n\n---\n\n' || p_block END`,
`content_version + 1`, one statement, returns new version; raises `check_violation` over 200 000;
`SECURITY INVOKER`, `SET search_path = social_wiring, public`. The only write path for imports/extractions.

### `cs_brain_answers`
`id` · `org_id` · `brain_id` FK CASCADE · `question_id` FK (service asserts same template) ·
`text` ≤ 10 000 default '' · `transcricao_id` uuid NULL FK `social_wiring.transcricoes` ON DELETE SET NULL
(§10) · `review_status` CHECK (`none`,`pending`,`done`,`error`) default `none` · `review_verdict` NULL
CHECK (`approved`,`rejected`) · `review_reason` · `review_improved` · `review_decision` NULL CHECK
(`accepted`,`dismissed`) · `review_error` · `reviewed_text_sha` (any later text change resets
`review_*` to `none`) · `review_requested_at`, `updated_at`. Unique `(brain_id, question_id)`.

### `cs_brain_imports` (editor appends)
`id` · `org_id` · `brain_id` FK CASCADE · `kind` CHECK (`file`,`youtube`) · `filename`,
`storage_path`, `size_bytes` (file) · `source_url` (youtube) · `transcricao_id` NULL FK ·
`status` CHECK (`processing`,`appended`,`error`) · `chars_appended` · `error_message` · audit cols.

### `cs_extractions` + `cs_extraction_targets` (Minhas extrações)
`cs_extractions`: `id` · `org_id`, `marca_id` FK CASCADE · `name` 1..120 · `source_kind` CHECK
(`url`,`text`) · `source_url` · `transcript` ≤ 200 000 (editable before applying) · `transcricao_id`
NULL FK · `status` CHECK (`transcribing`,`ready`,`applied`,`error`) · `error_message` · audit cols.
(Name check: Pesquisa wave 2 already has `cs_extraction_jobs`; these are distinct tables, prefix kept
for the module — the BE slice may rename to `cs_brain_extractions` if the reviewer finds it confusing.)
`cs_extraction_targets`: `extraction_id` FK CASCADE, `brain_id` FK CASCADE, `applied_at` NULL, PK
`(extraction_id, brain_id)`; every target must belong to the extraction's marca (422).

### `cs_marca_perfil`
`marca_id` PK FK CASCADE · `org_id` · `bio` text ≤ 5 000 default '' · `updated_by`, `updated_at`.

### Storage + nav
Bucket `social-wiring-cerebro` `public=false` (ON CONFLICT DO NOTHING) for **uploaded files only**
(voice audio lives in the transcription bucket, §10); no authenticated storage policy, backend-only,
signed URLs 900 s; paths `{org}/{marca}/{brain}/files/{uuid}-{filename}`.
`INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES ('media-creation-cerebro','desenvolvimento') ON CONFLICT DO NOTHING`.

## 3 · Async statuses

| Thing | States | Moves via |
|---|---|---|
| Brain synthesis | `idle → processing → idle` or `→ error` | `BackgroundTasks`; sweep: `processing` > 10 min → `error` "Tempo esgotado ao gerar o cérebro" |
| Answer review | `none → pending → done/error`; then `review_decision` | `BackgroundTasks`; sweep: `pending` > 10 min → `error` |
| Voice transcription | the shared `transcricoes` statuses (§10) | shared transcription job + completion hook |
| Brain import (file) | `processing → appended/error` | `BackgroundTasks`; stale > 15 min → `error` |
| Extraction | created `ready` (text) / `transcribing → ready` (url, §10) `→ applied/error` | user "Aplicar" |

Derived brain display status (not stored): `processando` if synthesis `processing` or any import
`processing`; else `pronto` if content non-blank; else `vazio` → labels `Vazio`/`Pronto`/`Processando`.

Completion routing for voice (idempotent): answer blank → `text := transcript`; else
`text := text + "\n\n" + transcript`; review resets.

Scheduler: `app/modules/media_creation/cerebro_scheduler.py :: configure()` (certidoes idiom) runs
the stale sweeps. Locally the seed scheduler doesn't fire, so reads also refresh pending state.

## 4 · Endpoints — prefix `/api/media-creation/cerebro`, auth `get_current_user_org`

`success_response`; pt-BR `detail`; foreign marca/brain/extraction/question → **404**; forbidden
operation on an existing brain → **409**; bodies `StrictHttpModel`; 202 via `success_response(status_code=202)`.

| # | Method + path | Request | `data` |
|---|---|---|---|
| 1 | `GET /templates` | — | `BrainTemplate[]` (with questions) |
| 2 | `GET /brains` | `marca_id` | `BrainSummary[]` — ensures the 4 Sistema brains exist first; Sistema by `sort_order`, then custom by `created_at` |
| 3 | `POST /brains` | `{marca_id, name}` | 201 `BrainSummary` (custom); duplicate → 409 "Já existe um cérebro com esse nome" |
| 4 | `GET /brains/{id}` | — | `BrainDetail` |
| 5 | `PATCH /brains/{id}` | `{name}` | `BrainSummary`; Sistema → 409 "Cérebros do sistema não podem ser renomeados" |
| 6 | `DELETE /brains/{id}` | — | 204; Sistema → 409 "Cérebros do sistema não podem ser excluídos"; deletes its storage objects (failures logged + surfaced) |
| 7 | `PUT /brains/{id}/content` | `{content ≤200 000, expected_version}` | `BrainSummary`; version mismatch → 409 "O conteúdo do cérebro mudou enquanto você editava."; synthesis running → 409 "Aguarde a geração do cérebro terminar." |
| 8 | `PUT /brains/{id}/answers/{question_id}` | `{text ≤10 000}` | `Answer` (autosave; resets stale review) |
| 9 | `POST /brains/{id}/answers/reset` | `{confirm: true}` | `{deleted}` — "Zerar Tudo" (content untouched) |
| 10 | `POST /brains/{id}/review` | `{question_ids?}` (default: every non-empty answer) | 202 `{queued}`; none → 422 "Responda ao menos uma pergunta" |
| 11 | `POST /brains/{id}/answers/{question_id}/suggestion` | `{action:'accept'\|'dismiss'}` | `Answer` (accept with `improved` → `text := improved`) |
| 12 | `POST /brains/{id}/synthesize` | `{mode:'replace'\|'append', expected_version}` | 202 `{brain}`; Sistema only (custom → 409); ≥1 answer else 422; running → 409 |
| 13 | `POST /brains/{id}/answers/{question_id}/audio` | multipart `arquivo` | `Answer` with its `transcricao` — delegates to the shared submit (§10: same caps, 413/415/422/429/503 codes) |
| 14 | `POST /brains/{id}/imports/file` | multipart `file` (pdf/docx/txt/md/csv by extension **and** sniffed bytes, ≤ 20 MB) | 202 `BrainImport` |
| 15 | `POST /brains/{id}/imports/youtube` | `{links: string[1..10]}` | **phase 2 (§10)** — 501 until enabled |
| 16 | `GET /brains/{id}/imports` | `limit ≤50` (20) | `BrainImport[]` newest first |
| 17 | `GET /perfil` | `marca_id` | `Perfil` (empty bio if none) |
| 18 | `PUT /perfil` | `{marca_id, bio ≤5 000}` | `Perfil` |
| 19 | `GET /extracoes` | `marca_id`, `q?`, `limit` 1–100 (20), `offset` | `{items: ExtractionSummary[], total}` |
| 20 | `POST /extracoes` | `{marca_id, name, brain_ids: uuid[1..20], text?: string ≤200 000, url?: string}` — exactly one; `url` is **phase 2** (422 "Extração por link ainda não disponível" until enabled) | 201 `ExtractionDetail` (`text` → `ready`) |
| 21 | `GET /extracoes/{id}` | — | `ExtractionDetail` |
| 22 | `PATCH /extracoes/{id}` | `{name?, transcript?, brain_ids?}` | `ExtractionDetail` (transcript edit when `ready`/`applied`) |
| 23 | `POST /extracoes/{id}/apply` | `{brain_ids?}` (default: unapplied targets) | `{applied, skipped}` — appends `### Extração: «name» (dd/mm/aaaa)\n\n<transcript>` via `cs_brain_append`; idempotent per target; `applied` when all done; not ready → 409 |
| 24 | `DELETE /extracoes/{id}` | — | 204 (text already appended stays) |

Append headers (single source in `cerebro_service`): `### Arquivo: «filename» (dd/mm/aaaa)` ·
`### YouTube: «title|url» (dd/mm/aaaa)` · `### Extração: «name» (dd/mm/aaaa)`. Over 200 000 →
import/extraction `error` "O cérebro excederia o limite de 200.000 caracteres." — never truncated silently.

File text extraction (14): seed helper `noctusai_lib.integrations.documents.plain_text.extract_plain_text(content, filename) -> PlainText{text, error}`
(slice S0b): PDF via the existing `make_document_transcriber()` (text layer first, vision per page),
DOCX via python-docx (paragraphs + tables), TXT/MD/CSV UTF-8 then explicit cp1252, else typed error.
Empty → "Não foi possível ler texto deste arquivo."

```ts
type BrainKind = 'sistema' | 'custom'
type BrainDisplayStatus = 'vazio' | 'pronto' | 'processando'
type SynthesisStatus = 'idle' | 'processing' | 'error'
type ReviewStatus = 'none' | 'pending' | 'done' | 'error'
type ReviewVerdict = 'approved' | 'rejected'
type ReviewDecision = 'accepted' | 'dismissed'
type TranscricaoStatus = 'na_fila' | 'processando' | 'concluida' | 'falhou' | 'cancelada'   // shared, transcription-contract §4
type ImportStatus = 'processing' | 'appended' | 'error'
type ExtractionStatus = 'transcribing' | 'ready' | 'applied' | 'error'

type BrainQuestion = { id: string; position: number; group: number; text: string; hint: string | null; optional: boolean }
type BrainTemplate = { slug: string; name: string; description: string; sort_order: number; questions: BrainQuestion[] }
type BrainSummary = { id: string; marca_id: string; kind: BrainKind; template_slug: string | null; name: string;
                      status: BrainDisplayStatus; content_chars: number; answered: number | null;
                      total_questions: number | null; synthesis_status: SynthesisStatus; updated_at: string }
type Transcricao = { id: string; status: TranscricaoStatus; posicao: number | null; duracao_s: number | null;
                     texto: string | null; erro: { codigo: string; mensagem: string } | null }
type Answer = { question_id: string; text: string; updated_at: string | null; transcricao: Transcricao | null;
                review: { status: ReviewStatus; verdict: ReviewVerdict | null; reason: string | null;
                          improved: string | null; decision: ReviewDecision | null; error: string | null } }
type BrainImport = { id: string; kind: 'file' | 'youtube'; filename: string | null; source_url: string | null;
                     status: ImportStatus; chars_appended: number | null; error_message: string | null; created_at: string }
type BrainDetail = BrainSummary & { content: string; content_version: number; synthesis_error: string | null;
                     synthesized_at: string | null; template: BrainTemplate | null; answers: Answer[]; imports: BrainImport[] }
type Perfil = { marca_id: string; bio: string; updated_at: string | null }
type ExtractionTarget = { brain_id: string; brain_name: string; applied_at: string | null }
type ExtractionSummary = { id: string; marca_id: string; name: string; source_kind: 'url' | 'text'; source_url: string | null;
                           status: ExtractionStatus; error_message: string | null; targets: ExtractionTarget[]; created_at: string }
type ExtractionDetail = ExtractionSummary & { transcript: string | null }
```

## 5 · AI layer (both DRAFT)

Seam: `get_cerebro_llm()` FastAPI dependency → `CerebroLlm = Callable[[system, user, org_id], Awaitable[str]]`,
default wraps `chat_completion(..., temperature=0.2)` (same shape as `get_pesquisa_llm`); background
tasks receive the resolved callable.

**Review** (`prompts/cerebro_review.py`): one call per request; input template name + each
`{question_id, question, hint, optional, answer}`; output strict JSON array
`[{question_id, verdict, reason, improved|null}]`. Criteria: answers the question; concrete, not
generic; specialist's voice; long enough; optional "Ainda não" approved; `improved` never invents
facts/numbers/stories. Parser: unknown ids ignored; missing id → that answer `error` "A IA não avaliou
esta resposta."; non-JSON or LLM exception → all pending in the request `error` "Falha ao revisar com IA".

**Synthesis** (`prompts/cerebro_synthesis.py`): one call; input template, its section outline, Q&A
pairs (non-empty; rejected included — non-blocking). Markdown only; first person; **preserve literal
coined names** (audience, enemy, method, self-title — Método Audience beats depend on them); never
invent; omit empty sections. Outlines: **Núcleo** (from owner's brain 3081): `### Perfil Profissional` ·
`### Público-Alvo e Desafios` · `### Solução e Transformação` · `### Histórias de Sucesso`;
**História de Criação** (DRAFT): Antes · O que me motivou · Desafios · Quase desisti · Ponto de virada ·
Quem me tornei · Missão · O que me move · Legado; **Histórias de Vida** (DRAFT): Histórias que me
forjaram · Descobertas e ensinamentos · Pessoas que ajudei · Grandes conquistas; **Método** (DRAFT):
Passo a passo · Pilares · O essencial · Fases · Nomes das etapas · Nome do método · O que as pessoas pulam;
plus closing `### Elementos para conteúdo` (literal audience/enemy/belief/method names) on every brain (§10).
Write: `replace` → content := output; `append` → `cs_brain_append`; `expected_version` checked at write
time (mismatch → `error` "O conteúdo mudou durante a geração; gere novamente."); LLM failure → `error`
"Ocorreu um erro ao gerar o cérebro. Tente novamente." — content untouched, no partial write.

## 6 · Frontend

Routes (`App.tsx`; static `extracoes` outranks `:brainId`): `/media-creation/cerebro` (list, title
**Cérebros Personalizados**, subtitle **Segundo cérebro**) · `/media-creation/cerebro/extracoes`
(**Minhas extrações**) · `/media-creation/cerebro/:brainId` (editor) ·
`/media-creation/cerebro/:brainId/perguntas` (questionnaire, Sistema only; custom → editor).

Sidebar (both nav configs): under **Criação de mídia**, after Pesquisa, sub-group **Segundo Cérebro**
› **Cérebros** (`/media-creation/cerebro`, icon `Brain`, `route: "media-creation-cerebro"`) ·
**Minhas extrações** (`/media-creation/cerebro/extracoes`, same page key) (§10).

Brand switcher: reuse `components/pesquisa/MarcaSwitcher.tsx` + `hooks/useMarcaPesquisa.ts` (already on dev).

**List**: header `+ Criar Cérebro` · `Minhas extrações`; **Bio card** "Bio do perfil" (helper "Usada
como Núcleo de Influência na geração de headlines."; textarea + count; Salvar; **Usar a bio do
Instagram** only when the marca has a connected IG account — fills, user saves); cards 3/row: name,
`Sistema` badge, `Vazio`/`Pronto`/`Processando`, `N de M respondidas`, **Acessar Cérebro** (Sistema
with 0 answers + empty content → `/perguntas`, else editor); modal **Criar Cérebro Personalizado**
(`Nome do Cérebro:`, placeholder `Ex: Reels Instagram`) → navigates to the editor.

**Editor**: back, title, `Sistema` badge or ✎ **Renomear Cérebro** + 🗑 (confirm "Tem certeza? Você
realmente deseja deletar este Cérebro?" Cancelar/Deletar); subtitle "Alimente este cérebro com o seu
conhecimento — quanto mais rico, melhores os resultados da IA."; buttons `Responder perguntas`
(Sistema) · `Enviar arquivo` · (`Transcrever do YouTube` hidden until phase 2); card **Conteúdo do
cérebro** (`N caracteres`, textarea, **Aplicar Alterações**, `Alterações não aplicadas` while dirty);
409 → modal "O conteúdo mudou (um arquivo ou transcrição foi anexado)" **Copiar meu texto** /
**Recarregar**; synthesis running → read-only + banner "Gerando cérebro…"; **Importações** panel with
chips; poll 3 s while anything non-terminal. **Enviar arquivo** modal: "Importar arquivo para o
cérebro", dropzone "Clique para escolher ou arraste o arquivo aqui", "PDF DOCX TXT MD CSV · máx. 20 MB",
"O conteúdo será adicionado abaixo do texto já existente no cérebro.", client messages "Selecione um
arquivo antes de enviar." / "Formato não suportado. Use PDF, DOCX, TXT, MD ou CSV." / "Arquivo muito grande. Limite: 20 MB.".

**Questionnaire**: header `Cérebro` / `Personalize seu cérebro` / Voltar; card `«name» - Sistema`;
`Progresso das respostas N de M`; numbered cards (bold question, italic hint, textarea "Escreva sua
resposta aqui", `N caracteres`); toggle **Prefiro falar ⇄ Prefiro escrever**; voice mode uses the
**seed organ** recorder (§10) — record/stop, `mm:ss`, 10-min auto-stop, upload on stop; unsupported →
"Ops! Parece que seu navegador não tem suporte para esse recurso, tente outro!"; mic denied →
"Erro ao acessar o microfone. Verifique as permissões!"; reveal in groups of 3 ("Grupo X de Y -
Continue respondendo as próximas perguntas"; all shown if >3 answered on load); autosave on blur +
1.5 s debounce; chip priority `Salvando…` → `Na fila (posição N)` / `Transcrevendo áudio…` →
`Falha na transcrição` (+ message from `erro.mensagem`) → `Revisando…` → suggestion `Aprovada`/`Rejeitada`
+ `Motivo: «reason»` (with `improved`: "Resposta sugerida" **Usar sugestão** / **Manter minha resposta**;
without: **OK**) → `Respondida` → `Aguardando resposta`; transcript lands in the textarea for review,
never written to the brain directly; `beforeunload` guard while uploads/autosave in flight; footer
**Zerar Tudo** ("Confirmar Exclusão" / "Sim, Zerar Tudo") · **Salvar Rascunho** ("Rascunho salvo com
sucesso!") · **Revisar com IA** ("Respostas enviadas para revisão. Aguarde...") · **Finalizar
Respostas** (≥1 answer; never gated by review; non-empty content → modal **Substituir o conteúdo
atual** / **Anexar abaixo**; "Gerando cérebro..." → editor "Cérebro gerado!" or error toast).

**Minhas extrações**: table ID · Data · Nome · Cérebros · Status (`Transcrevendo`/`Pronta`/`Aplicada`/`Falha`);
search `Pesquisar...`; "Carregar mais"; **Nova Extração** modal (`Nome:` `ex: Pesquisa 1` · `Extrair
para:` brain multi-select + inline "Clique aqui para criar um novo núcleo" → POST 3 · `Transcrição:`
`Cole aqui sua transcrição...` · (`Url:` toggle hidden until phase 2) · **Criar Transcrição**); row
actions **Ver** (editable when ready, **Salvar**, **Aplicar aos cérebros**), **Excluir** (confirm);
empty "Nenhuma extração encontrada.".

All pages: `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`,
`placeholderData`, never `isLoading`; error state **Tentar novamente**; mutations invalidate
`["sw","cerebro", marcaId]`. Components in `src/components/cerebro/`: `ImportarArquivoModal`,
`SugestaoRevisao`, `BioPerfilCard`, `NovaExtracaoModal`, `labels.ts`.

## 7 · Transcription (see §10 — superseded)

## 8 · Tests (minimum)

Backend (`tests/modules/media_creation/test_cerebro*.py`, storage via `FakeStorageBackend`): 4
templates, counts 15/9/4/7, Núcleo hints present, migration text == `seed_sql()`; strict `== 401`
everywhere; cross-org 404 (marca, brain, extraction, question of another template); `GET /brains`
creates Sistema brains once; custom CRUD, duplicate 409, Sistema rename/delete 409; content PUT
version conflict 409; `cs_brain_append` bumps version, refuses > 200k; answer edit resets stale
review; review parser (valid, unknown id, missing id, non-JSON, LLM exception); accept/dismiss;
synthesis allowed with rejected/unreviewed, 0 answers 422, replace vs append, LLM failure leaves
content byte-identical + `error`, version moved mid-run → `error`, concurrent 409; audio submit
delegates to the shared transcription service (fake) and completion fills/appends the answer exactly
once; file import docx/txt/csv/pdf, extension vs sniffed mismatch 415, empty → `error`; extractions
text → `ready`, apply idempotent per target, foreign-marca target 422; stale sweeps; perfil GET/PUT.
Frontend: list (4 Sistema + custom, badges, progress, CRUD), bio card + IG prefill only with an
account, editor save + 409 modal + import modal validation, questionnaire (reveal, autosave, mocked
`MediaRecorder`/`getUserMedia` incl. unsupported + denied, chips accept/dismiss, Finalizar enabled
despite rejected, replace/append modal), extractions create + apply, two-signal loading on marca switch.

## 9 · Deliberate differences from CoreStudio

Per marca; one id space (no core/brain split, no sync store); `beliefs` type and tutorial banner
dropped; AI review non-blocking; voice answers live (dormant in CoreStudio), one upload per recording
(no 1 MiB chunks); polling instead of Pusher; re-synthesis asks replace/append; optimistic
concurrency; atomic server-side appends; Minhas extrações reachable from the menu, "apply to
variables" dropped (Extrair Pesquisa covers it); DELETE instead of GET navigation.

## 10 · Tech-lead amendments (win over the sections above)

1. **Transcription = the shared product layer from `transcription-contract.md`**, not a module-local
   table. Voice audio is submitted to the shared social-wiring transcription service (table
   `social_wiring.transcricoes`, `contexto_tipo='cerebro_resposta'`, `contexto_ref='{brain_id}:{question_id}'`,
   same quotas/caps/error codes, private bucket `sw-transcricoes`, **audio deleted right after
   transcription** — LGPD decision already taken). Consequently: no `cs_transcriptions` table, no audio
   playback/download endpoint, no audio retention in `social-wiring-cerebro`. The Cérebro module
   registers a **completion hook** for `cerebro_resposta` that routes the transcript into the answer
   (idempotent). The shared transcription product slice (S3 in `transcription-contract.md`) is a
   prerequisite of the voice part only; everything else in this contract can ship first.
2. **Seed recorder organ**: the MediaRecorder component is built in the seed lib frontend
   (`useAudioRecorder` + `VoiceAnswerInput`, transcription-contract S4), not as a product-local
   `GravadorDeVoz`.
3. **URL sources are phase 2** (YouTube import, extraction by link): the transcriber has no egress
   by design, so the product would have to download media (yt-dlp: SSRF, huge files, a new
   dependency). Ships after a `security` review, with a pre-download duration check and the same
   quotas. v1 ships file import, pasted-text extractions and voice.
4. **Owner open questions — tech-lead defaults until the owner says otherwise:** raw append (no LLM
   condensing) · "apply to variables" dropped · hints/optional for the 3 non-Núcleo templates left
   NULL/false until the owner provides them; Núcleo optional set kept as DRAFT · add `### Elementos para
   conteúdo` · bio card on the list page with IG prefill, no "gerar bio" helper in v1 · Minhas extrações
   in the sidebar · reveal in groups of 3. **Still asked:** import the owner's existing CoreStudio
   brains (Núcleo answers + content, custom Call de diagnóstico / Formulário / Narrativa) — into which marca?
5. **Migration number** from `noctus.dev.scaffold_migration` at build time (other sessions hold
   social-wiring numbers in flight).

## Slice plan (file-disjoint)

- **S0b (engineer-seed)** — `seed/lib/backend/noctusai_lib/integrations/documents/plain_text.py` + tests
  (2nd consumer after `drive_census._extract_docx`; optionally migrate that one). Don't edit existing
  `noctusai_lib` `__init__` files.
- **BE-A brains core (backend)** — the migration (all §2 DDL), `cerebro_templates.py`,
  `schemas/cerebro.py`, `services/cerebro_service.py`, `services/cerebro_ai.py`,
  `prompts/cerebro_review.py`, `prompts/cerebro_synthesis.py`, `routers/cerebro.py`, `cerebro_scheduler.py`,
  endpoints 1–12, 16–18, tests.
- **BE-B sources (backend, after S0b + BE-A)** — file import (14), extractions (19–24), the voice
  submit (13) + completion hook once the shared transcription product slice exists.
- **FE-A list + editor + bio (frontend)** — `src/types/cerebro.ts` (verbatim §4, first commit),
  `hooks/useCerebro.ts`, `pages/cerebro/{CerebroLista,CerebroEditor}.tsx`, components, `App.tsx`
  (routes + sidebar).
- **FE-B questionnaire (frontend)** — `hooks/useCerebroPerguntas.ts`, `pages/cerebro/CerebroPerguntas.tsx`,
  `components/cerebro/SugestaoRevisao.tsx` (voice toggle wired to the seed organ when it lands).
- **FE-C extrações (frontend)** — `hooks/useExtracoes.ts`, `pages/cerebro/MinhasExtracoes.tsx`,
  `components/cerebro/NovaExtracaoModal.tsx`.
FE-A registers FE-B/FE-C pages at fixed paths (default exports); FE-B/FE-C never edit `App.tsx`.
`media_creation/__init__.py` router lines are additive (C2).
