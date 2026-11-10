# Owner line — contract v1 (noc-whatsapp-lines Phase 2)

> Status: provisional tech-lead call (2026-11-10, agents session, owner asleep and asked us not to stop).
> Seat in plan: `projects/noc-whatsapp-lines/PROJECT.md` Phase 2. The owner may flip any choice in the morning (§11 change log).

## Why
The owner rule since 2026-11-09 is that "warn me" means a WhatsApp scripted message to the owner
(`KB § PATTERNS/backend/owner-notification-catalog.md`). Today only SW sends WhatsApp, and only from an org's
own line to that org's staff. The owner chose (2026-11-10) a **seed owner line**: NoctusAI's own number (L3,
the third number, not bought yet) sends every owner notification for every product. A client's line is never used.

## Shape: three pieces, one seam each

### 1. Seed: `noctusai_lib.domain.notification_catalog.owner_line` (NEW module, beside catalog.py)
It deliberately lives OUTSIDE `integrations/whatsapp/`, because the Assistant session is changing that package
(line policy S1, `feat/ac-line-policy`). Transport comes in through an injected callable, so the two never collide.

```python
@dataclass(frozen=True)
class OwnerRecipient:
    numero: str            # E.164, e.g. "+5511999999999"
    nome: str | None = None

class OwnerRecipientSource(Protocol):
    def active(self) -> list[OwnerRecipient]: ...          # enabled recipients only; [] = none configured

class OwnerLineTransport(Protocol):
    def send_text(self, numero_e164: str, texto: str) -> None: ...   # raises on failure (never silent)

@dataclass(frozen=True)
class OwnerDispatch:
    status: str            # one of SEND_STATUSES: sent | partial | failed | suppressed | no_recipient
    recipients: int
    delivered: int
    reason: str | None

def notify_owner(product: str, kind: str, texto: str, *, org_id=None,
                 gate: NotificationGate | None = None,
                 recipients: OwnerRecipientSource | None = None,
                 transport: OwnerLineTransport | None = None) -> OwnerDispatch:
    """gate.allowed(kind) -> recipients.active() -> transport.send_text per recipient -> gate.record(...).
    Never raises. Every outcome is recorded."""
```

Rules:
- An undeclared kind raises `UndeclaredNotificationKind`, which is the catalog's existing behaviour.
- Switch off → `suppressed`, nothing is sent.
- No recipients → `no_recipient`, with reason `"nenhum destinatário do dono configurado"`.
- No transport configured (the owner line does not exist yet) → `failed`, reason `"linha_noc_nao_configurada"`, logged at ERROR. This is never a silent skip.
- Each recipient's failure is caught and counted. 0 delivered → `failed`; some delivered → `partial`; all delivered → `sent`. The reason is ≤ 300 chars and never holds the message text or the numbers.
- Defaults: `gate=get_notification_gate(product)`, plus process-wide `configure_owner_line(recipients=…, transport=…)` / `get_owner_line()`, the same pattern as the gate.
- Fake + Real + factory:
  - `FakeOwnerRecipientSource(list)`, `FakeOwnerLineTransport` (records sends, can be told to fail a number).
  - `SupabaseOwnerRecipientSource(core_client_factory)` reads core `public.notification_owner_recipients` (enabled rows, ordered), with a 60 s TTL like the switch.
  - `WahaOwnerLineTransport(client_factory)`: `client_factory()` returns an object with the seed WAHA client's send-text method. It converts E.164 → chat id with the seed phone helpers (`noctusai_lib.primitives.phone`). The factory is injected by the framework, which uses the seed's official WAHA client factory: after S1 lands that is the line-policy factory; before that, the existing construction path.
  - `make_owner_line(core_client_factory, waha_factory)` returns Real when both are configured, else a transport-less line, which records `failed` loudly as above.
- Config: env `NOC_OWNER_LINE_WAHA_URL` (+ `NOC_OWNER_LINE_WAHA_SESSION`, default `default`, + its API key env) names L3. Unset = no transport. The framework installs the line at boot (never fatal), next to the gate (`seed/framework/backend/noctusai_seed/app.py` §3c).

### 2. Core: who receives (migration + admin API + page)
- Core migration (next free core number): `public.notification_owner_recipients`:
  - `id uuid pk`, `numero text NOT NULL CHECK (numero ~ '^\+[1-9][0-9]{7,14}$')`, `nome text`, `ativo boolean NOT NULL default true`, `created_at`, `updated_at`;
  - unique(numero), service-role only (no anon/authenticated grants, RLS on, platform tier).
  - Event-oriented: every change appends to `public.notification_owner_recipient_events` (`recipient_id`, `evento` in `('adicionado','ativado','desativado','removido')`, `ator`, `created_at`), in the same transaction (a trigger or the service).
  - The access-tier declaration and DB guard probe follow the core 117 precedent.
- Admin API under the existing `/api/admin/notifications` router (platform tier):
  - `GET /recipients` → `{data:{items:[{id,numero,nome,ativo,created_at}]}}` (every JSON response uses the router's `{data: …}` envelope)
  - `POST /recipients {numero,nome?}` → 201 `{data: item}`. The number is normalized with `normalize_phone`; 422 `numero_invalido`; 409 `numero_duplicado`.
  - `PATCH /recipients/{id} {ativo?,nome?}` → `{data: item}`; 404 `destinatario_nao_encontrado`.
  - `DELETE /recipients/{id}` → 204 (records the `removido` event).
  - Strict 401 for no auth, 403 for a non-platform-admin.
- Page `AdminNotificacoes.tsx` (core `/admin/notificacoes`): a "Quem recebe os avisos" section with the recipients list, add, toggle and remove, and a status line for the line itself:
  - "Linha NoctusAI: não configurada" when the transport is absent, read from `GET /api/admin/notifications/owner-line` → `{data:{configurada: bool, instancia: str|null}}`;
  - complete loading/empty/error states, pt-BR copy, cache writes (never invalidate-only).

### 3. Agents: the eval-loop gate's two notices
- `products/agents/backend/app/notification_kinds.py` declares `eval_loop_parada` and `eval_loop_checkpoint`, with pt-BR `titulo`/`descricao`/`gatilho` and `canais=("whatsapp","in_app")`.
- `EvalLoopService._notificar` keeps the in-app bell to platform admins and ALSO calls `notify_owner("agents", kind, texto_whatsapp)`.
  - The WhatsApp text is short, scripted pt-BR: agent, suite, why it stopped, best score, cost, and a link to `/agentes`.
  - Dedupe: one notice per loop stop and per checkpoint, the same keys as the bell.
- Tests cover suppressed, no_recipient, transport-less `failed`, and a happy path through the fakes.

## Metrics this enables
Owner-notification sends per kind/product/status over 30 days (core page, already shown), recipient changes over
time (events), and time from loop stop to the owner being notified (`notification_sends.created_at` minus the loop's `encerrado_em`).

## 11 · Change log
- 2026-11-10 (tech-lead, merge review): the admin API uses the router's existing `{data: …}` envelope, not bare bodies, because the sibling routes in `admin_notifications.py` wrap and the page unwraps `.data`. The events timestamp is `created_at`, not `em`, as the measurable-by-design keeper requires. Errors stay flat `{detail, code}`, read by the FE as `ApiError.code`.
