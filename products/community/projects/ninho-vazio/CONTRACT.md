# Ninho Vazio — v1 contract (2026-09-28)

The community product becomes the membership platform for Mônica Tangerino's
"ninho vazio" audience (women 50+, the empty nest as the door to identity).
v1 is a CRM: members register themselves or are registered by staff; three
tiers; Asaas billing with auto-renewal and a grace period; cashflow; a
relationship timeline; grupoterapia scheduling gated by tier; a dashboard on
real data.

**Both sides build to this file.** Field names, paths, status codes and error
texts below are the acceptance gate for every slice. Anything not written here
is not in v1.

Foundation already on `feat/community-ninho-vazio` (do not re-create):
- `backend/migrations/013_ninho_vazio.sql` — all schema below, applied and
  RLS-probed on Postgres 15 (member sees only own rows; staff unchanged; seat
  capacity holds).
- `app/dependencies.py` — `get_current_user_org` now **403s a `membro`**
  ("Área restrita à equipe."); `get_membro_context` → `(user, token, org_id,
  membro_row)` for portal routes; `get_community_role` may return `"membro"`.
- `app/services/eventos_service.py` — `registrar_evento(client, *, org_id,
  membro_id, tipo, descricao, dados=None, autor_id=None)`.
- `app/services/acesso_service.py` — `nivel_grupoterapia(membro, plano)` →
  `"nenhum"|"ouvir"|"falar"`; `pode(nivel, exigido)`.
- `app/schemas/planos.py` — `Entitlements.grupoterapia: "nenhum"|"ouvir"|"falar"`.

## Conventions (unchanged from modules 1–3)

- Base path `/api`. Auth header `Authorization: Bearer <supabase jwt>`.
- Errors: `http_error(status, detail)` → body `{"detail": "<pt-BR text>", "code": "<CODE>"}`.
- Money is always integer **centavos**. Dates `YYYY-MM-DD`; timestamps ISO-8601 UTC.
- Lists: `{"items": [...], "total": int}` plus per-endpoint extras.
- Staff routes: `Depends(get_current_user_org)`; writes add `require_admin`.
  Member routes: `Depends(get_membro_context)`. Public routes: rate-limited,
  `resolve_public_org_id()`, service-role client.
- Timeline: every state change a slice makes to a member, subscription or
  payment ALSO calls `registrar_evento` (same client the write used).

## Roles

| role | who | reaches |
|---|---|---|
| `admin` | Mônica / owner | everything, all writes |
| `moderador` | team | staff reads; no writes except where stated |
| `membro` | end customer (`noctus_users.org_role='membro'`) | `/api/eu`, `/api/portal/*` only |

## Tiers (data, not code)

Three plans, created by `POST /api/planos/padrao` (idempotent by `nome`):

| nome | preco_centavos | ciclo | entitlements.grupoterapia | ordem |
|---|---|---|---|---|
| Gratuito | 0 | mensal | `nenhum` | 0 |
| Ouvinte | 700 | mensal | `ouvir` | 1 |
| Premium | 2700 | mensal | `falar` | 2 |

All other entitlements keep their defaults. Prices are editable in Planos.
"The free plan" everywhere = the active plan with `preco_centavos = 0` and the
lowest `ordem`; if none exists, flows that need it return **409 "Plano gratuito
não configurado."**

## Billing lifecycle (Asaas)

`assinaturas.estado`: `iniciada → ativa → inadimplente → carencia → expirada`,
plus `cancelada`, `pausada` (unchanged). Seed mapping: iniciada=INCOMPLETE,
ativa=ACTIVE, inadimplente=PAST_DUE, carencia=GRACE, cancelada=CANCELED,
expirada=EXPIRED. Every move is validated with the seed's
`noctusai_lib.domain.payments.subscription.transition` (map pt-BR → seed state,
call `transition`, map back). An illegal move is logged + reported, never
applied.

| trigger | subscription | member | other |
|---|---|---|---|
| charge paid (webhook) | `ativa`; `pago_ate` = due date + 1 cycle; `proxima_cobranca` = that date; clears `inadimplente_desde`/`carencia_ate` | `ativo`, `plano_id` = sub's plan | `lancamentos` entrada (origem `pagamento`, categoria `assinatura`, idempotent on `pagamento_id`); evento `pagamento` |
| charge failed / overdue (webhook) | `carencia`; `inadimplente_desde` = now (keep first); `carencia_ate` = inadimplente_desde + `dias_carencia` days | `atrasado` (access KEPT) | evento `assinatura` |
| charge refunded (webhook) | unchanged | unchanged | `lancamentos` saida (origem `estorno`, categoria `estorno`, `estorno_de` = pagamento id, idempotent); evento `pagamento` |
| payment arrives for an `expirada`/`cancelada` sub | unchanged | unchanged | pagamento stored as `pago`, lancamento booked, evento `sistema` "Pagamento recebido após o encerramento — verificar reembolso ou reativação." |
| sweep: `carencia` and `carencia_ate` ≤ now | `expirada`, `expirada_em` = now; cancel at Asaas (failure → `gateway_cancelamento_pendente = true`, retried next sweep) | `ativo` on the **free plan** | evento `assinatura` |
| member/staff cancels | `cancelada`, `cancelada_em`, `cancelamento_solicitado_por`, `cancelamento_motivo`; cancel at Asaas first (existing order) | keeps plan until `pago_ate` | evento `assinatura` |
| sweep: `cancelada` and `pago_ate` ≤ now and member still on that plan | unchanged | `ativo` on the free plan | evento `plano` |

Grace is `configuracoes_cobranca.dias_carencia` (default **5**, row created on
first read). `automacoes_ativas = false` → the sweep reports `skipped` and writes
nothing. The sweep runs hourly via the seed scheduler
(`noctusai_lib.api.scheduler`, wired through `create_product_app(lifespan_startup=…)`)
only when `NOCTUS_SCHEDULERS_ENABLED` is set (same switch as Core), and is also
callable on demand by an admin.

Auto-renewal is Asaas's recurring subscription: each cycle Asaas emits a new
charge and its webhook moves the row as above. Zero-price plans never touch a
gateway.

## Endpoints

### Identity — slice BE-A

**GET `/api/eu`** — any authenticated org user (uses the base auth, not the
staff gate). 200:
```json
{"papel": "admin|moderador|membro", "nome": "str", "email": "str",
 "membro": null | {"id": "uuid", "status": "str", "plano_id": "uuid|null",
                   "plano_nome": "str|null", "nivel_grupoterapia": "nenhum|ouvir|falar"}}
```

**POST `/api/cadastro`** — PUBLIC, rate-limit 5/min per IP, Turnstile token
checked like `/api/checkout` (`turnstile_token`). Body (extra fields rejected):
```json
{"nome": "str 1..120", "email": "email", "telefone": "str|null (same regex as membros)",
 "senha": "str 8..72", "turnstile_token": "str", "aceite_termos": true}
```
Side effects, in order: find-or-create the auth identity
(`noctusai_lib.domain.org.provision_invited_identity`); if the identity already
existed → **409 "Este e-mail já tem cadastro. Entre com sua senha."** and
nothing else happens (never touch an existing password). Then
`attach_user_to_org(org_role="membro")`; then find-or-create the `membros` row
by email (an existing CRM row created by staff or checkout is LINKED — set
`user_id`, keep its data), setting `origem='cadastro'` only on create, status
`ativo`, plan = free plan unless the row already has a plan. Evento `acesso`
"Cadastro realizado pelo site". 201:
```json
{"membro_id": "uuid", "email": "str", "proximo_passo": "entrar"}
```
Errors: 400 `aceite_termos` false ("É preciso aceitar os termos."), 403 Turnstile,
409 above, 409 no free plan, 429.

**POST `/api/membros/{id}/acesso`** — admin. Creates the member's login when
they have none. Generates a 12-char temporary password (`secrets`), provisions
the identity, attaches `org_role='membro'`, sets `membros.user_id`. Evento
`acesso`. 201 `{"email": "str", "senha_temporaria": "str"}` (shown once,
never stored or logged). 409 "Este membro já tem acesso." when `user_id` is set
or the identity already exists (then link `user_id` and return 409 with
detail "Este e-mail já tinha login; o acesso foi vinculado.").

**GET `/api/membros/{id}/eventos`** — staff. Query `page` (1), `page_size`
(50, ≤200). 200 `{"items": [Evento], "total": int}`, newest first.
`Evento = {"id","tipo","descricao","dados","autor_id","autor_nome"|null,"created_at"}`.

**POST `/api/membros/{id}/eventos`** — staff (moderador allowed). Body
`{"tipo": "nota|contato", "descricao": "str 1..2000"}`. 201 Evento.

Existing `POST /api/membros/{id}/status` now persists `motivo` as an evento
`status` (closes NOC-REMEDIATE[status-history]); `PATCH` changing `plano_id`
writes evento `plano`.

### Member portal — slice BE-A

**GET `/api/portal/minha-conta`** — membro. 200:
```json
{"membro": {"id","nome","email","telefone","status","entrou_em"},
 "plano": {"id","nome","preco_centavos","ciclo","nivel_grupoterapia"} | null,
 "assinatura": null | {"id","estado","metodo","proxima_cobranca","pago_ate",
                       "carencia_ate","cancelada_em","gateway"},
 "pagamentos": [{"id","valor_centavos","estado","metodo","vencimento","pago_em","url_fatura"}],
 "planos_disponiveis": [{"id","nome","descricao","preco_centavos","ciclo","nivel_grupoterapia"}]}
```
`assinatura` = the most recent non-`expirada` row, else null. `pagamentos` last 12.

**POST `/api/portal/assinatura/cancelar`** — membro. Body `{"motivo": "str|null ≤500"}`.
Cancels the member's current paid subscription per the lifecycle table
(`cancelamento_solicitado_por='membro'`). 200 the `assinatura` object above.
404 "Você não tem assinatura ativa." · 502 "Não foi possível cancelar no
gateway. Tente novamente." (local row untouched).

Upgrades/new subscriptions from the portal reuse the existing public
`POST /api/checkout` (the FE pre-fills name/email); `charge_paid` links it by email.

### Billing — slice BE-B

**GET `/api/cobranca/configuracoes`** — staff. 200 `{"dias_carencia": int, "automacoes_ativas": bool}`.
**PUT `/api/cobranca/configuracoes`** — admin. Same body (dias 0..60). 200 same.
**POST `/api/cobranca/executar-rotina`** — admin. Runs the sweep now. 200
`{"relatorios": [{"nome","pulado","examinadas","alteradas":[str],"erros":[str]}]}`.
**POST `/api/planos/padrao`** — admin. Creates any missing tier of the table
above. 200 `{"criados": ["Ouvinte", ...], "existentes": ["Gratuito", ...]}`.

`POST /api/checkout` with a zero-price plan → 409 "Este plano é gratuito —
faça seu cadastro." (never calls a gateway). The existing Assinaturas list
item gains `inadimplente_desde, carencia_ate, pago_ate, proxima_cobranca,
expirada_em, cancelamento_solicitado_por, cancelamento_motivo`; its `estado`
filter accepts `carencia` and `expirada`. Existing staff cancel sets
`cancelamento_solicitado_por='equipe'`.

### Cashflow + dashboard — slice BE-C

**GET `/api/lancamentos`** — staff. Query `de`, `ate` (dates, default current
month), `tipo`, `categoria`, `page`, `page_size`. 200:
```json
{"items": [{"id","tipo","categoria","descricao","valor_centavos","data","origem",
            "pagamento_id","membro_id","membro_nome","created_at"}],
 "total": int,
 "totais": {"entradas_centavos": int, "saidas_centavos": int, "saldo_centavos": int}}
```
**POST `/api/lancamentos`** — admin. `{"tipo","categoria","descricao"?,"valor_centavos">0,"data"}`,
`origem` forced to `manual`. 201 item. **PATCH / DELETE `/api/lancamentos/{id}`** — admin,
**only `origem='manual'`** (else 409 "Lançamentos automáticos não podem ser alterados.").
**GET `/api/lancamentos/categorias`** — staff. 200 `{"items": ["str"]}` (distinct, plus
defaults `assinatura, estorno, plataforma, marketing, equipe, impostos, outros`).

**GET `/api/dashboard`** — staff. Query `meses` (default 12, 1..24). 200:
```json
{"kpis": {
   "membros_total": int, "membros_ativos": int,
   "por_plano": [{"plano_id","nome","nivel_grupoterapia","membros": int}],
   "mrr_centavos": int, "arpu_centavos": int,
   "em_carencia": int, "novos_mes": int, "cancelamentos_mes": int,
   "churn_mes_pct": float, "receita_mes_centavos": int, "saldo_mes_centavos": int,
   "conversao_pago_pct": float},
 "series": {
   "mensal": [{"mes": "YYYY-MM", "entradas_centavos", "saidas_centavos",
               "novos_membros", "cancelamentos", "mrr_centavos"}],
   "origem_membros": [{"origem": "str", "membros": int}],
   "status_membros": [{"status": "str", "membros": int}],
   "grupoterapia": [{"sessao_id","titulo","inicio","vagas_fala","reservas": int}]},
 "gerado_em": "timestamp"}
```
Definitions (tests assert these): `membros_ativos` = status ∈ {ativo, atrasado};
`mrr_centavos` = Σ plan price (anual ÷ 12, rounded) over subscriptions in
{ativa, carencia}; `arpu` = mrr ÷ paying members (0 when none);
`churn_mes_pct` = subscriptions that became `cancelada|expirada` this calendar
month ÷ subscriptions `ativa|carencia` at the month's start × 100 (0 when the
base is 0); `conversao_pago_pct` = members on a paid plan ÷ `membros_ativos` × 100;
`mensal[].mrr_centavos` = MRR as of each month's last day, reconstructed from
`ativa_em`/`cancelada_em`/`expirada_em`; `grupoterapia` = the next 10 and last 10
sessions. All months in the window are present (zero-filled), oldest first.
Every number comes from the database — nothing hardcoded or sampled.

### Grupoterapia — slice BE-D

`Sessao = {"id","titulo","descricao","inicio","duracao_minutos","link_sala","vagas_fala","status","reservas": int,"created_at","updated_at"}`

Staff: **GET `/api/grupoterapia/sessoes`** (query `de`, `ate`, `status`; 200 list),
**POST** (admin; `{titulo, descricao?, inicio, duracao_minutos?, link_sala?, vagas_fala?}`; 201),
**PATCH `/{id}`** (admin; partial; `status` may become `realizada|cancelada`),
**DELETE `/{id}`** (admin; only when 0 reservations, else 409 "Sessão com reservas — cancele em vez de excluir."),
**GET `/{id}/reservas`** (staff; `{"items":[{"id","membro_id","membro_nome","status","created_at"}],"total"}`).
Cancelling a session writes an evento `grupoterapia` for each confirmed reservation.

Member: **GET `/api/portal/grupoterapia`** — membro. Upcoming (`inicio` ≥ now − duration) `agendada` sessions:
```json
{"nivel": "nenhum|ouvir|falar",
 "items": [{"id","titulo","descricao","inicio","duracao_minutos","status",
            "vagas_fala","vagas_restantes": int,"minha_reserva": bool,
            "acesso": "bloqueado|ouvir|falar", "link_sala": "str|null"}]}
```
`acesso` = member level capped at the session; `link_sala` is **null unless
`acesso ≠ bloqueado`** (read with the service-role client after the check —
members have no RLS read on sessions). For `nenhum`, items are still listed
(titles/dates) so the portal can show the upgrade path.

**POST `/api/portal/grupoterapia/{id}/reserva`** — membro with `falar`. Calls
`community.reservar_vaga_fala` with the service-role client. 200
`{"status": "confirmada"}` · 403 "Seu plano não inclui a vez de fala." ·
409 "Não há mais vagas de fala nesta sessão." (`lotada`) · 409 "Sessão
indisponível para reservas." (`indisponivel`). Evento `grupoterapia`.
**DELETE same path** — membro; sets the reservation `cancelada`. 204.

## Frontend

Routes are in `frontend/src/App.tsx`. The member area and the back office
share one app; a `membro` must never see staff nav or pages.

- **FE-A (staff)**: Dashboard (`/`) on `GET /api/dashboard` with the lib charts
  (`@noctusai/lib` `design-system/charts`: StatTileRow, AreaChart/BarChart,
  DonutChart, ChartCard); Financeiro gains tab **Fluxo de caixa**
  (`/api/lancamentos` CRUD + totals) and grace/expiry columns + `carencia`/
  `expirada` filters on Assinaturas; Membros detail gains the **timeline**
  (list + add nota/contato) and **Criar acesso** (shows the temp password once);
  Planos form gains the grupoterapia level select + **Criar planos padrão**
  button when missing; Configurações gains **Cobrança** (dias de carência,
  automações, "Executar rotina agora"); new page **Grupoterapia** `/grupoterapia`
  (sessions CRUD + reservations).
- **FE-B (member + public + routing)**: `/cadastro` public signup (Ninho Vazio
  copy; on 201 go to `/login`; if the visitor picked a paid tier, after login send
  them to `/assinar?plano=<id>` pre-filled); `/portal` (minha conta: plan, status,
  grace banner when `carencia`, next charge, payments, upgrade cards → checkout,
  cancel with confirmation); `/portal/grupoterapia` (list; `bloqueado` → upgrade
  card; `ouvir` → "Assistir" link; `falar` → reserve/cancel seat + link);
  role routing via `GET /api/eu`: `membro` → portal nav only and any staff path
  redirects to `/portal`; staff → current nav + Grupoterapia. Landing copy
  re-themed to Ninho Vazio.

Every page: skeleton = `isPending && !data`, refresh = `isFetching && !!data`
(never `isLoading`); empty and error states; pt-BR copy.

## Care line (non-negotiable)

The analysis found comments about wanting to die. The portal footer, the signup
success screen and every grupoterapia screen carry: "Se estiver pesado demais,
procure ajuda. CVV 188 — gratuito, 24 horas." (FE-B owns the shared component;
FE-A uses it on the Grupoterapia page.)

## Out of scope for v1 (named destinations)

- In-platform live room (seed `integrations/live_rooms` + LiveKit): the user decides when.
- Lifting the grace sweep into the seed: Core's `billing_automations` is N=1 of this
  shape and community is N=2 → marker `NOC-REMEDIATE[billing-sweep-seed-lift]` in
  the community sweep; formalize at N=3.
- Stripe card path stays as is (the user chose Asaas; untouched, not extended).
