# Orbity rebuild — hardening requirements

> GENERATED from [private study: orbity-live-2026-10] by its `gen_hardening.py` — do not edit by hand.
> Each line is a requirement OUR orbity must meet. `R-<n>` = finding number in the private study
> (the defect description + live evidence live there, outside git, per `KB § PATTERNS/common/app-reverse-engineering.md`).

Priority: **P0** security / data-loss / cut-over blocker · **P1** user-visible bug class · **P2** gap / refinement / architecture · **P3** idea.

## Administrativo (29)

| P | Req | Requirement |
|---|---|---|
| P0 | R-158 | secrets only in Vault/edge function; FE gets a boolean `stripe_configured`; revoke column SELECT from authenticated |
| P0 | R-164 | write amount_paid; status partial; keep remainder open (or split) |
| P0 | R-173 | store amount_brl at write (or convert in one query layer) |
| P0 | R-178 | cancel only the rule + future/pending instances; paid instances immutable |
| P0 | R-201 | server-side scheduled generation, unique(client_id, competence month) |
| P1 | R-161 | one period param drives every query; hide realized chips in forecast |
| P1 | R-165 | derive overdue from due_date server-side |
| P1 | R-167 | keep confirm copy; with amount_paid the revert is lossless |
| P1 | R-168 | persist base, surcharge, discount, paid as columns; never derive history from the live contract |
| P1 | R-176 | invalidate by query-key family; model parent=template, children=instances; convert currency in one place |
| P1 | R-177 | separate expense_rules from expense_instances |
| P1 | R-180 | one RPC; count parent; styled confirm; one enum |
| P1 | R-181 | invalidate expenses query-key family on every expense mutation |
| P1 | R-183 | preselect + derive date; persist gross/bonus/deductions; real holerite PDF |
| P1 | R-185 | name the blast radius in the confirm, or block delete when paid children exist |
| P1 | R-187 | single subscription state machine |
| P1 | R-188 | one shared revert() |
| P1 | R-292 | client_status_events table (cancelled/reactivated with timestamps); churn = f(events); reactivation dialog offering to regenerate charges |
| P1 | R-364 | server-side generation job with an idempotency key per (client, cycle) and a tombstone so a deleted/forgiven cycle is never regenerated |
| P2 | R-160 | allocate by time/tasks/direct costs; show method |
| P2 | R-163 | copy the queue design; one gateway adapter seam |
| P2 | R-166 | free-form receita + show description |
| P2 | R-171 | multi-step cadence; history filters; channel health gates the toggle |
| P2 | R-174 | seed default categories (incl. tributos) + inline create |
| P2 | R-182 | generate current-month salary on create (if payday ≥ today) |
| P2 | R-184 | confirm + end-date picker + "o que fazer com salários pendentes?" |
| P2 | R-189 | delete when no salaries; anonymize otherwise |
| P2 | R-191 | inline fee/status edit; relax required fields on update |
| P2 | R-204 | allocate by hours/tasks, not head-count |

## CRM (27)

| P | Req | Requirement |
|---|---|---|
| P0 | R-130 | "Ganhou → criar cliente" (prefill from lead, link lead_id, optional contract) |
| P0 | R-132 | canonical enum + keep unknown value; patch diff only |
| P0 | R-193 | fire once per lead per stage (idempotency key lead_id+event), never on backward moves |
| P1 | R-103 | one canonical source enum + labels (verify on NOC-TEST lead whether Atualizar wipes source) |
| P1 | R-104 | one label map |
| P1 | R-105 | store date as date / parse local |
| P1 | R-118 | one label map |
| P1 | R-119 | parse local |
| P1 | R-120 | canonical enum + migration |
| P1 | R-125 | one language, key column on lead_statuses |
| P1 | R-128 | one date util: date-only fields stored as `date` and rendered without TZ shift (same root as #214/#240) |
| P1 | R-133 | stable key column |
| P1 | R-135 | soft delete + confirm + keep history |
| P1 | R-137 | render "Etapa: Propostas → Vendas" |
| P1 | R-195 | server-side outbox + retry + status |
| P1 | R-366 | confirm dialog listing linked data; decide policy explicitly — cascade conversations, or keep them attached to the phone number (contact entity) rather than the lead |
| P2 | R-98 | one cached statuses query; server-side period filter |
| P2 | R-102 | Perdido terminal stage + loss reason |
| P2 | R-106 | stop the clock at won/lost; no overdue on closed |
| P2 | R-107 | append-only note timeline |
| P2 | R-121 | normalize E.164 everywhere; dedupe warning |
| P2 | R-122 | owner select |
| P2 | R-124 | history for key fields; patch diff only |
| P2 | R-139 | join/embed |
| P2 | R-196 | agency-default pixel + per-source override |
| P2 | R-199 | one query, shared cache |
| P3 | R-192 | KEEP drag (dnd-kit) — server-side stage hook emits the conversion event (META-PIXEL-FLOW §7), not the browser |

## Configurações (14)

| P | Req | Requirement |
|---|---|---|
| P0 | R-272 | secrets write-only via a backend endpoint into the vault; FE only gets {configured:bool, last4}; column grants revoke SELECT on secret columns |
| P0 | R-273 | invite-by-email magic link; the member sets their own password; optional SSO |
| P0 | R-274 | guard: never allow removing/demoting the last owner (server-side check + disabled menu item with a reason) |
| P1 | R-276 | dirty-check; normalize empty → NULL server-side |
| P1 | R-279 | hide CTA when public_phone null; validate phone (E.164) on save |
| P1 | R-283 | Restaurar = immediate DELETE with confirm + toast; Salvar toast; show 'personalizado' badge when a row exists |
| P1 | R-288 | toast with result count; hide/disable portal button with reason when no customer |
| P1 | R-289 | prompt_type is an enum owned by ONE source (DB enum/lookup table) and the FE derives its card list from it; contract test FE types ⊆ DB enum; CI migration check |
| P1 | R-290 | map backend error codes → pt-BR user messages; log the raw error server-side with a correlation id |
| P2 | R-275 | explicit role→permission matrix UI; audit log of role changes |
| P2 | R-277 | persist preference on profile |
| P2 | R-281 | HMAC/header secret where the provider supports it; webhook health panel (last event, error count, replay) |
| P2 | R-284 | version history + 'testar prompt' preview before save |
| P2 | R-286 | see #272 |

## Clientes (18)

| P | Req | Requirement |
|---|---|---|
| P0 | R-145 | encrypt at rest, reveal-on-demand + audit |
| P0 | R-147 | (process) |
| P1 | R-21 | normalize NFD both sides |
| P1 | R-22 | one health function shared by list + detail |
| P1 | R-140 | one computed score (server/view), list reads it |
| P1 | R-143 | label map; overdue badge |
| P1 | R-151 | confirm/undo; stable layout |
| P1 | R-154 | copy the quick-create; one RPC/transaction |
| P1 | R-311 | collect NPS/CSAT (periodic WhatsApp/email survey to the client, store nps_responses) and compute the health server-side, storing history for trend; until NPS exists, show the pillar as 'sem dados' instead of a fake 20 |
| P1 | R-312 | either real LLM summary of notes/tasks/meetings/payments (cached, regenerated on change) or rename to 'Resumo' |
| P2 | R-142 | honest label or real summary; NPS capture |
| P2 | R-144 | client 360 incl. contract + receivables + origin lead |
| P2 | R-148 | clamp to month end; opt-in or explicit confirm |
| P2 | R-152 | edit own notes |
| P2 | R-153 | require billing fields only when billing/gateway ON; server-side validation; "complete billing data" banner |
| P2 | R-157 | deep-link /tasks?client=<id>; rows open the task drawer |
| P2 | R-200 | defaults OFF for loyalty; start_date default today |
| P2 | R-315 | one contract-period model (start + duration-or-end, months shortcut 6/12/24) shared by Clientes, Contratos and fidelity; single date component |

## Social Media (23)

| P | Req | Requirement |
|---|---|---|
| P0 | R-208 | discard ⇒ ask "excluir/arquivar tarefa?"; restore action; single counter source |
| P0 | R-249 | server-generated token (edge fn), private bucket + signed URLs |
| P1 | R-207 | one RPC/transaction |
| P1 | R-211 | validate period; one counter function |
| P1 | R-214 | parse date-only as local (date-fns parseISO / no TZ shift) |
| P1 | R-222 | open the edit dialog in place (or deep-link ?task=id) |
| P1 | R-226 | open the post form in place |
| P1 | R-227 | step by the active view's unit |
| P1 | R-240 | store date-only fields as `date`, or local midnight with tz |
| P1 | R-247 | status copy by decision; real notification (in-app + WhatsApp/email) |
| P1 | R-248 | decision-aware text; E.164 |
| P1 | R-344 | single enums (format, tone, platform) in one module; platform lists derived from social_media_platforms (enabled defaults + custom) |
| P2 | R-215 | show planned items as ghost entries |
| P2 | R-217 | real edit form |
| P2 | R-224 | explain prerequisite |
| P2 | R-230 | persist caption on the task (caption field + versions) |
| P2 | R-234 | Meta/IG insights via seed meta adapter |
| P2 | R-237 | confirm + in-use guard / soft delete |
| P2 | R-239 | client-approval portal config |
| P2 | R-250 | upload on save or move+cleanup job |
| P2 | R-251 | full activity log |
| P3 | R-212 | re-test live before the rebuild; our version: in-form IA fills the item fields from one ai call, with a visible loading/error state |
| P3 | R-220 | explicit preview → Aplicar |

## Tasks (19)

| P | Req | Requirement |
|---|---|---|
| P0 | R-40 | defaults seeded as DB rows (is_default) or merged FE-side; never gate creation on an empty list |
| P0 | R-55 | PATCH only changed fields; server-side optimistic concurrency (updated_at check) |
| P1 | R-3 | single status-label map |
| P1 | R-30 | do it as a scheduled server job with audit (our seed scheduler) |
| P1 | R-33 | single slug util; store semantic color token |
| P1 | R-35 | server-side activity table |
| P1 | R-36 | include defaults |
| P1 | R-38 | merge default+custom types in one list |
| P1 | R-45 | single RPC/transaction server-side |
| P1 | R-50 | per-subtask row/RPC + activity entry |
| P1 | R-56 | diff assignments; single RPC |
| P1 | R-59 | one slug convention, enum for built-ins |
| P1 | R-65 | render + duplicate from task_clients |
| P1 | R-67 | confirm or undo-toast + soft delete with retention |
| P2 | R-43 | invalidate on settings mutations / refetchOnWindowFocus |
| P2 | R-46 | use a date column |
| P2 | R-48 | localized role label |
| P2 | R-57 | same component for create/edit; fix overflow |
| P2 | R-64 | single source (join table) + view |

## Agenda (14)

| P | Req | Requirement |
|---|---|---|
| P0 | R-86 | never derive status from notes; explicit close-out |
| P1 | R-80 | filter by client/lead + start_time < this.start |
| P1 | R-81 | sync; label by viewed range |
| P1 | R-82 | prompt to close out past meetings |
| P1 | R-83 | masked pt-BR date+time picker |
| P1 | R-89 | carry meeting_id/client/responsible; mark items converted (idempotent) |
| P1 | R-90 | one-click follow-up meeting prefilled; parse dates as local |
| P1 | R-92 | exclude cancelled; reflect status |
| P1 | R-93 | prefill follow_up_date |
| P1 | R-97 | derive one from the other |
| P2 | R-84 | range-bounded query |
| P2 | R-87 | honest save indicator; chips relative to meeting |
| P2 | R-94 | patch changed fields; refresh detail |
| P2 | R-314 | templates interpolate {cliente}/{lead} from the current selection and re-render when the selection changes; templates editable per agency |

## CRM ⚙ Fontes (1)

| P | Req | Requirement |
|---|---|---|
| P0 | R-115 | per-agency secret token in URL/header, enforce active flag, rate-limit |

## CRM ⚙ Investimentos (1)

| P | Req | Requirement |
|---|---|---|
| P0 | R-117 | no nested modals; month picker; owner to confirm with a hand click |

## Client vault (1)

| P | Req | Requirement |
|---|---|---|
| P0 | R-24 | encrypt at rest, reveal-on-click with audit |

## Clientes / Administrativo (1)

| P | Req | Requirement |
|---|---|---|
| P0 | R-293 | select only displayed columns; PII via a detail endpoint with audit |

## Contratos (7)

| P | Req | Requirement |
|---|---|---|
| P0 | R-261 | snapshot is legally right for a signed contract, but mask in lists, LGPD retention/erase policy, purge drafts with the client |
| P1 | R-258 | store monthly + duration; derive total |
| P1 | R-259 | one date util |
| P1 | R-260 | one contract model for both paths |
| P1 | R-263 | structured address; services from client |
| P2 | R-257 | our version: render PDF, e-sign via seed (we have d4sign tooling), status lifecycle draft→sent→signed→active→ended, link to client billing |
| P2 | R-262 | agency profile field |

## E-mail Marketing (3)

| P | Req | Requirement |
|---|---|---|
| P0 | R-265 | secrets server-side only (vault), FE gets a boolean `configured` |
| P1 | R-266 | route registry for deep links (same class as #2) |
| P2 | R-264 | map on a real agency with SendPulse; ours: provider-agnostic email seam (seed) — SendPulse/Resend/SES |

## Lembretes (9)

| P | Req | Requirement |
|---|---|---|
| P0 | R-72 | generate next occurrence on complete (server-side) |
| P1 | R-74 | group completed separately by completed_at |
| P1 | R-76 | append position; semantic color token |
| P1 | R-323 | Agendados = future-dated ∧ not completed; per-filter empty copy ('Nada para hoje'); list header with name/count; show the year when ≠ current year |
| P1 | R-324 | default Média (or an explicit 'Sem prioridade' option) — enum shared FE/DB with a CHECK constraint |
| P2 | R-69 | expose end/count + tags |
| P2 | R-70 | default to current list; pt-BR locale |
| P2 | R-75 | full list CRUD + drag reorder |
| P2 | R-325 | explicit 'Sem lista' option; weekly preset defaults to the date's weekday and shows the next 3 occurrences |

## Master console (1)

| P | Req | Requirement |
|---|---|---|
| P0 | R-301 | platform-admin role in the DB (not an agency id), RLS on master views, audit log for suspend/delete |

## Notification prefs (1)

| P | Req | Requirement |
|---|---|---|
| P0 | R-4 | separate user prefs vs agency settings, role-gated |

## Onboarding (1)

| P | Req | Requirement |
|---|---|---|
| P0 | R-300 | server generates + stores a hashed OTP with TTL/attempt limit and sends a FIXED template; verify endpoint; rate-limit per phone/IP; [their server function] never callable from the browser |

## Public landing lead capture (1)

| P | Req | Requirement |
|---|---|---|
| P0 | R-357 | marketing site + its forms outside the product; anon writes via a rate-limited edge fn with captcha/honeypot, never a direct table INSERT |

## Tráfego (4)

| P | Req | Requirement |
|---|---|---|
| P0 | R-253 | tokens only in vault/server; FE reads a safe view |
| P2 | R-197 | our Meta App Review must be done before selling this |
| P2 | R-252 | map it on a real agency account (Gabriel offered one) before building our traffic module; our seed Meta adapter already has ads/insights |
| P2 | R-254 | provider-agnostic ads seam (Meta first, Google next) |

## /onboarding (1)

| P | Req | Requirement |
|---|---|---|
| P2 | R-358 | one source for steps; trial flow visibly different (no plan step) or drop the param |

## AI layer (1)

| P | Req | Requirement |
|---|---|---|
| P2 | R-320 | per-feature typed endpoints that load the data SERVER-side from ids + period; per-agency AI quota/rate limit + usage log; persist each AI result (ai_runs table) with inputs hash for history and cache |

## Administrativo › Análise Avançada (1)

| P | Req | Requirement |
|---|---|---|
| P1 | R-335 | one finance metrics service: run-rate from contracted MRR (active clients) with collected% beside it; MoM on closed months only; averages over months since first activity; overdue derived (due_date < today ∧ unpaid) in ONE place used by every widget; label 'contratado', not 'garantido' |

## Administrativo › DRE (1)

| P | Req | Requirement |
|---|---|---|
| P2 | R-336 | category registry with an explicit DRE group per category (receita/dedução/imposto/custo/folha/…) seeded with a Brazilian chart of accounts (see accountant advisor); toggle competência vs caixa |

## Administrativo › Equipe (1)

| P | Req | Requirement |
|---|---|---|
| P2 | R-340 | either ship the PPR module it implies (pool %, eligibility, period, per-employee split → salary bonus lines) or drop the field; never store dead config |

## Administrativo › Fluxo de Caixa (2)

| P | Req | Requirement |
|---|---|---|
| P1 | R-338 | filters are part of the period state and reset (or stay visible) when the mode changes; never apply a filter whose control is hidden; hide non-applicable KPIs in forecast mode |
| P1 | R-362 | optimistic remove + stable sort keys; never re-order rows under an open pointer; menus carry the row name in their header |

## Administrativo › Rentabilidade por Cliente (1)

| P | Req | Requirement |
|---|---|---|
| P2 | R-341 | drill-down to the client P&L (invoices, allocated costs, tasks/hours); cap/explain extreme margins; no hover affordance without an action |

## Administrativo › Régua de Cobrança (1)

| P | Req | Requirement |
|---|---|---|
| P1 | R-339 | form state initialised from the server row on every open; unsaved-changes prompt on close; an explicit 'Ativa / Inativa' status chip sourced from the saved row |

## Agenda › Contexto (1)

| P | Req | Requirement |
|---|---|---|
| P1 | R-326 | one status registry (category open/closed per status, incl. custom) and client linkage via the join table everywhere; context panels query 'open' categories, not hard-coded slugs |

## Agenda › Semana/Dia (1)

| P | Req | Requirement |
|---|---|---|
| P1 | R-327 | render 00–24 with auto-scroll to the first meeting/current hour, or expand the range to cover the earliest/latest meeting; never position items outside the rendered range |

## Auth (1)

| P | Req | Requirement |
|---|---|---|
| P2 | R-298 | magic-link + reset-password flow; min 10 chars + breached-password check; no PII in console |

## Billing pages (1)

| P | Req | Requirement |
|---|---|---|
| P2 | R-302 | verify the checkout session server-side, then show the real plan/status; poll [their server function] until active |

## CRM Dashboard (4)

| P | Req | Requirement |
|---|---|---|
| P1 | R-99 | fixed-width label / legend |
| P1 | R-100 | one period scope for the whole dashboard, or label Velocity "atual (todos)" |
| P2 | R-101 | stage-entered_at per transition |
| P2 | R-134 | flag test leads (is_test) and exclude |

## CRM Dashboard ↔ Pipeline (1)

| P | Req | Requirement |
|---|---|---|
| P1 | R-329 | metrics iterate the agency's ordered stage registry (system + custom, with stage category open/won/lost) instead of a fixed list; custom stages insertable at any position |

## CRM Pipeline (1)

| P | Req | Requirement |
|---|---|---|
| P2 | R-332 | distinct empty states (first-run vs no-results with the active query + clear); always-visible compact actions; one shared action registry per entity rendered by every view |

## CRM kanban (2)

| P | Req | Requirement |
|---|---|---|
| P1 | R-126 | stopPropagation on menu; one modal at a time |
| P1 | R-138 | open Nova Reunião prefilled with lead_id |

## CRM lead WhatsApp tab (1)

| P | Req | Requirement |
|---|---|---|
| P2 | R-331 | reads never write: resolve conversations lazily on first real message (in/out); the tab GETs existing rows only; sync runs from the webhook/worker, not a UI view; skip any remote call when the account isn't connected |

## CRM ⚙ Fluxos (2)

| P | Req | Requirement |
|---|---|---|
| P1 | R-112 | validate before save; pick values from the canonical enum |
| P2 | R-113 | single RPC / transaction |

## CRM ⚙ Fluxos WhatsApp (2)

| P | Req | Requirement |
|---|---|---|
| P1 | R-305 | confirm dialog with 'N execuções em andamento serão paradas'; single server RPC/transaction; trash with restore |
| P2 | R-306 | validate on save; mark flow 'incompleto' with per-block errors |

## CRM ⚙ Fontes › Exemplos (1)

| P | Req | Requirement |
|---|---|---|
| P2 | R-333 | capture endpoint accepts a configured success/failure redirect per source (or returns a 303 to it for form-encoded posts); hosted embeddable form with honeypot + rate limit + optional captcha; signed per-source tokens instead of the bare agency UUID |

## CRM ⚙ Status (1)

| P | Req | Requirement |
|---|---|---|
| P2 | R-110 | slug/key column; append order = max+1; rename |

## CRM ⚙ Status / Investimentos (1)

| P | Req | Requirement |
|---|---|---|
| P2 | R-334 | investments carry a reference_month picker (default current) + month navigation on the list; one name per concept; sheet forms wrap instead of clipping |

## Client detail (2)

| P | Req | Requirement |
|---|---|---|
| P2 | R-23 | our client page can be the real 360 |
| P2 | R-27 | flag overdue |

## Clientes ← CRM (1)

| P | Req | Requirement |
|---|---|---|
| P2 | R-149 | lead → client conversion |

## Clientes ↔ Tarefas (1)

| P | Req | Requirement |
|---|---|---|
| P1 | R-155 | single task_types source for every create path |

## Comunicação (2)

| P | Req | Requirement |
|---|---|---|
| P2 | R-202 | our WAHA-based channel |
| P2 | R-205 | copy UX on WAHA; expire stale qr_pending |

## Contratos › Copilot de Contrato / Usar Modelo (1)

| P | Req | Requirement |
|---|---|---|
| P2 | R-348 | sticky action bar; one exit; highlight unresolved variables + block save while any remain |

## Controle de Tráfego › client report link (1)

| P | Req | Requirement |
|---|---|---|
| P2 | R-347 | client_reports table (token hash, scope, range, expires, revoked_at, views) + list/revoke UI; snapshot in storage or recomputed |

## Copy / navigation (1)

| P | Req | Requirement |
|---|---|---|
| P1 | R-330 | every 'go configure X' state is a deep link to the real route (/dashboard/settings?tab=ops#whatsapp) generated from the route registry, never free text |

## Dashboard (4)

| P | Req | Requirement |
|---|---|---|
| P1 | R-14 | one query key / invalidate both |
| P2 | R-16 | deep-link create modals |
| P2 | R-17 | link to filtered list |
| P3 | R-10 | bulk triage action |

## Dashboard onboarding (1)

| P | Req | Requirement |
|---|---|---|
| P1 | R-1 | don't compute onboarding via 6 count queries; one RPC/endpoint |

## Forms (2)

| P | Req | Requirement |
|---|---|---|
| P2 | R-29 | pt-BR inline validation (zod) |
| P2 | R-322 | dirty-form guard on every dialog/wizard + autosaved local draft; inline field errors (zod) — one shared form shell in the component library |

## Help (1)

| P | Req | Requirement |
|---|---|---|
| P2 | R-309 | contextual per-page tours versioned by feature (tour_progress {tour_id: version}); cover every module |

## Importação (3)

| P | Req | Requirement |
|---|---|---|
| P1 | R-268 | count invalid ROWS |
| P2 | R-269 | server-side validation + pt-BR messages + header mapping UI with suggestions |
| P2 | R-271 | accept CSV; show the schema inline |

## Layout (2)

| P | Req | Requirement |
|---|---|---|
| P1 | R-349 | reserved bottom-right safe area on every sticky bar/table; FAB collapses when a sticky action bar is present |
| P2 | R-328 | reserve a bottom padding/safe area equal to the FAB size on scroll containers (or auto-hide the FAB on scroll-end) |

## Mobile Tarefas list (1)

| P | Req | Requirement |
|---|---|---|
| P1 | R-354 | card layout below md for Tarefas/Clientes with title first; never a fixed-width table on mobile |

## Mobile shell (1)

| P | Req | Requirement |
|---|---|---|
| P1 | R-353 | opaque sidebar surface token on the mobile sheet; visual regression test at 390px |

## Notes (2)

| P | Req | Requirement |
|---|---|---|
| P1 | R-5 | flush pending autosave on blur/unmount |
| P2 | R-6 | undo toast |

## Notifications (1)

| P | Req | Requirement |
|---|---|---|
| P1 | R-2 | action URLs must be route-registry-derived, tested |

## Notificações (1)

| P | Req | Requirement |
|---|---|---|
| P2 | R-350 | single pt-BR locale file + lint for pt-PT tokens |

## Privacy policy (1)

| P | Req | Requirement |
|---|---|---|
| P1 | R-299 | versioned policy document with a fixed effective date + changelog; consent records reference the version |

## Public landing `/` (1)

| P | Req | Requirement |
|---|---|---|
| P2 | R-355 | landing claims generated from feature flags / integration status; marketing site separate from the app bundle |

## Public landing footer (1)

| P | Req | Requirement |
|---|---|---|
| P1 | R-356 | real /termos + /privacidade (versioned, #299) linked in footer and sign-up |

## Public report /report/:token (1)

| P | Req | Requirement |
|---|---|---|
| P1 | R-351 | agency name/contact from the token's agency branding (agency_branding already exists for /approve); distinct not-found vs expired states; expiry configurable |

## Public routes / 404 (1)

| P | Req | Requirement |
|---|---|---|
| P2 | R-352 | branded pt-BR 404 inside the shell when authenticated; log unknown paths |

## Relatórios (1)

| P | Req | Requirement |
|---|---|---|
| P2 | R-20 | our orbity has Relatórios (snapshot + public token) — an edge we can show the reference operator |

## Routines (2)

| P | Req | Requirement |
|---|---|---|
| P1 | R-12 | validate 1–31 + define Feb/30-day behaviour |
| P2 | R-13 | keep soft-delete but add undo |

## Social Media › Análises (1)

| P | Req | Requirement |
|---|---|---|
| P2 | R-346 | allow forward months (capacity planning is the point); chart buckets from task_statuses with a stable "outros" bucket |

## Social Media › Calendário (1)

| P | Req | Requirement |
|---|---|---|
| P1 | R-345 | build the filter from task_statuses (or give social posts their own status machine end to end, and map task status → post status in one place) |

## Social Media › Criar com IA (1)

| P | Req | Requirement |
|---|---|---|
| P1 | R-343 | validate per step (custom range ⇒ both dates, fim ≥ início, ≤ 3 months); show período + dias in the Resumo |

## Social Media › Novo Planejamento Manual (1)

| P | Req | Requirement |
|---|---|---|
| P2 | R-342 | pt-BR month picker component (Select mês + ano), sized to content, default = next month |

## Social Media › Planejamentos (1)

| P | Req | Requirement |
|---|---|---|
| P1 | R-359 | confirm dialog that states counts ("7 itens, 6 tarefas geradas") + choice delete/keep tasks; soft-delete with undo toast; FK tasks.content_plan_item_id ON DELETE SET NULL explicitly + badge "plano excluído" |

## Tarefas (12)

| P | Req | Requirement |
|---|---|---|
| P1 | R-223 | skeleton while pending |
| P1 | R-242 | memoize/cached query |
| P1 | R-243 | merge default types; normalize platform slugs |
| P1 | R-244 | dirty-field PATCH; diff assignments; one date convention |
| P1 | R-317 | one task-type registry (DB rows incl. defaults) → label + icon everywhere; never render a slug |
| P1 | R-318 | design-token chip variants with a contrast check (WCAG AA) in the component library; muted outline variant for the empty state |
| P1 | R-360 | confirm + undo toast (soft-delete window); delete approval when its last item goes; storage cleanup on attachment/task delete (DB trigger → queue → storage DELETE); private bucket + signed URLs |
| P2 | R-221 | server cron + configurable retention |
| P2 | R-295 | show recurrence summary ('Repete todos os dias') in review + in the list row |
| P2 | R-296 | server-side trigger on status→done computes next date from recurrence_rule (idempotent on (root, due_date)); show 'n/N' or date chip in title |
| P2 | R-316 | URL-synced filter state + saved views per user ('Minhas', 'Atrasadas', 'Sem responsável'); server-side filtering when the set is paged; '+N sem data ocultas' hint |
| P2 | R-321 | server-side transcription through our own processor (seed transcription organ / Whisper-class model) with upload of the recording, disclosed in the privacy policy; same UX on every browser; keep the audio only if the user opts in |

## Tarefas search (1)

| P | Req | Requirement |
|---|---|---|
| P2 | R-361 | show match snippet; title-only toggle; confirm on destructive row actions |

## Tarefas › Análises (1)

| P | Req | Requirement |
|---|---|---|
| P2 | R-319 | attention = overdue ∨ (completion below target among tasks already due); neutral colour at 0; i18n plurals; type labels from the type registry (#317) |

## Tarefas ⚙ Templates (1)

| P | Req | Requirement |
|---|---|---|
| P1 | R-367 | one policy: archive (soft) everywhere with an "Arquivados" view + restore, copy that matches the behaviour, confirm only for true hard deletes |

## Task detail (1)

| P | Req | Requirement |
|---|---|---|
| P1 | R-53 | update cache from server response; per-subtask writes |

## Tasks list (1)

| P | Req | Requirement |
|---|---|---|
| P1 | R-34 | distinct control + undo toast |

## Tasks ⚙ Tipos (1)

| P | Req | Requirement |
|---|---|---|
| P1 | R-41 | show inactive section with re-enable; implement default toggles (is_default rows) |

## Templates (2)

| P | Req | Requirement |
|---|---|---|
| P1 | R-61 | server-side increment on task insert (trigger/RPC) |
| P1 | R-63 | substitute at create (one task per client, or first client name) |

## UX consistency (2)

| P | Req | Requirement |
|---|---|---|
| P2 | R-73 | one shared confirm/undo pattern (seed organ) |
| P2 | R-96 | one shared confirm organ |

