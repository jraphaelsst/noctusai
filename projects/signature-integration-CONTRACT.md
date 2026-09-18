# Signature integration — contract (seed `signature` IO module + social-wiring wiring)

> Authored once by the tech-lead (skill `noc-contract-first`); every slice builds TO this file and its
> tests assert against it. A slice that needs a change **stops and surfaces it**, never re-guesses.
>
> Origin: 2026-09-17. The contract generator ships a PDF + `.docx` and stops there. `status`
> (`enviado_assinatura` / `assinado`) is a free-text dropdown with no behavior. This contract closes the
> last mile: generated document → provider envelope → signed copy back as a version.

---

## 0 · Two findings that shape this contract (verified, not assumed)

**F1 — `erp-imobiliario`'s `signature_provider.py` is a scaffold that lies. It is NOT the thing to lift.**
- ClickSign: `POST /api/v1/documents` with `"content_base64": ""  # Would be actual file content`
  (`products/erp-imobiliario/backend/app/services/signature_provider.py:99`) — the document is never uploaded.
- DocuSign: no API call at all; returns `uuid4().hex` as `external_id` with **`"dry_run": False`**
  (`:172-179`) — a mock that reports itself as real. That is the silent-error shape CLAUDE.md §1 forbids.
- D4Sign: posts `{"name":..., "url":...}` to `/documents/upload` (`:205`), which is not D4Sign's upload
  contract (real upload is multipart into a cofre/`uuid_safe`).
- No webhook signature validation anywhere in the provider.

⇒ **We do not lift this file.** We author a correct seed IO module and then migrate erp ONTO it
(replication-to-seed symmetry). Lifting the scaffold would ship a half-real adapter into the seed —
the exact `seed-fake-real-adapter` half-ship trap.

**F2 — no signing credentials exist on the platform.** Probed `public.platform_settings`,
`public.org_settings`, `social_wiring.credentials`: **zero** rows matching clicksign / docusign / d4sign.

⇒ The **Real** leg ships unit-tested against the pinned wire shapes below, and is **unverifiable against
the live provider until the office supplies a D4Sign token + cryptKey + cofre uuid.** No slice may claim
"verified end to end" without them. The named refusal `ASSINATURA_PROVEDOR_NAO_CONFIGURADO` is what a
credential-less org gets — never a mock envelope.

**Provider scope: D4Sign only.** 7 of the 8 sample contracts name D4Sign, and clause 2.13's wording is
D4Sign's. ClickSign/DocuSign are **not** in this contract; the Protocol admits them later without change.

---

## 1 · Seed IO module — `noctusai_lib/integrations/signature/`

Follows `KB § PATTERNS/backend/seed-fake-real-adapter.md`: **Protocol + Fake + Real + factory, all four
in the same commit.** Product code imports the factory and the types, never `httpx` and never a vendor name.

### 1.1 `types.py` — value objects (frozen dataclasses) + Protocol

```python
PapelSignatario = Literal["comprador", "vendedor", "testemunha", "interveniente", "intermediario"]
StatusAssinatura = Literal["pendente", "parcial", "concluido", "cancelado", "expirado"]

@dataclass(frozen=True)
class Signatario:
    nome: str
    email: str
    cpf: str                      # digits only, 11 chars, mod-11 valid (reuse documents.cpf.is_valid)
    papel: PapelSignatario
    ordem: int = 0                # 0 = no enforced order

@dataclass(frozen=True)
class DocumentoParaAssinar:
    nome: str                     # filename shown in the provider UI, e.g. "Promessa - v3.pdf"
    conteudo: bytes               # the ACTUAL bytes. Never a URL. (F1: this is what erp got wrong.)
    mime_type: str = "application/pdf"

@dataclass(frozen=True)
class EnvelopeCriado:
    external_id: str              # provider's document/envelope id
    link_assinatura: str          # https URL an operator can open
    provedor: str                 # "d4sign"
    signatarios: tuple[SignatarioRemoto, ...]
    criado_em: datetime           # tz-aware UTC

@dataclass(frozen=True)
class SignatarioRemoto:
    email: str
    external_id: str
    assinado_em: datetime | None = None

@dataclass(frozen=True)
class EventoAssinatura:
    external_id: str
    status: StatusAssinatura
    provedor: str
    ocorrido_em: datetime
    signatarios: tuple[SignatarioRemoto, ...] = ()
    documento_assinado_disponivel: bool = False
```

```python
class SignatureAdapter(Protocol):
    async def criar_envelope(
        self, documento: DocumentoParaAssinar, signatarios: Sequence[Signatario]
    ) -> EnvelopeCriado: ...

    async def consultar(self, external_id: str) -> EventoAssinatura: ...

    async def baixar_assinado(self, external_id: str) -> bytes: ...
    #   Raises DocumentoAssinadoIndisponivel when status != "concluido".

    def validar_webhook(
        self, corpo: bytes, cabecalhos: Mapping[str, str]
    ) -> EventoAssinatura: ...
    #   Raises WebhookInvalido on a bad/absent signature. NEVER returns None. Synchronous on purpose:
    #   it is pure verification + parsing, no I/O.

    async def cancelar(self, external_id: str, motivo: str) -> EventoAssinatura: ...
```

### 1.2 Exceptions (`exceptions.py`) — all subclass `SignatureError`

| Exception | Raised when |
|---|---|
| `ProvedorNaoConfigurado` | credentials absent for this org. **The factory raises this — it never returns a Fake in `real=True` mode.** |
| `WebhookInvalido` | signature header missing or does not verify |
| `DocumentoAssinadoIndisponivel` | `baixar_assinado` before `status == "concluido"` |
| `ProvedorIndisponivel` | transport/5xx/timeout from the provider |
| `EnvelopeRecusado` | provider 4xx with its message attached |

🔴 **No silent fallback.** There is no `_enviar_interno`. A credential-less org gets
`ProvedorNaoConfigurado`, which the product maps to a typed 422 naming what to configure.

### 1.3 `fake.py` — `FakeSignatureAdapter`

Deterministic and stateful in memory, so a product test drives the whole lifecycle with no network:
- `criar_envelope` → `external_id = "fake-" + sha256(nome + emails)[:16]`, link
  `https://fake.assinatura.local/{external_id}`, status `pendente`.
- `marcar_assinado(email)` (test-only helper) flips one signatario; all signed ⇒ `concluido`.
- `baixar_assinado` returns `b"%PDF-1.4 fake-signed ..."` once `concluido`, else raises.
- `validar_webhook` accepts a JSON body `{"external_id":..., "status":...}` with header
  `x-fake-signature: <sha256 of body>`; anything else raises `WebhookInvalido`.

### 1.4 `real.py` — `D4SignAdapter` (pinned wire shapes)

Base `https://secure.d4sign.com.br/api/v1`. Auth by query string `?tokenAPI=<t>&cryptKey=<c>`
(D4Sign does not accept these as headers). All calls `timeout=30`, one `httpx.AsyncClient` per adapter.

| Step | Call | Notes |
|---|---|---|
| 1. Upload | `POST /documents/{uuid_safe}/uploadbinary` — JSON `{"base64_binary_file": <b64>, "mime_type": "application/pdf", "name": <nome>}` | `uuid_safe` = the cofre, from credential `d4sign_safe_uuid`. Response `{"uuid": ...}` ⇒ `external_id`. **The bytes go up here** — this is F1's fix. |
| 2. Signers | `POST /documents/{uuid}/createlist` — `{"signers":[{"email":..., "act":"1", "foreign":"0", "certificadoicpbr":"0", "assinatura_presencial":"0"}]}` | one call, all signers |
| 3. Send | `POST /documents/{uuid}/sendtosigner` — `{"message": ..., "skip_email": "0", "workflow": "0"}` | |
| 4. Status | `GET /documents/{uuid}` → `statusId` | map: `1,2→pendente`, `3→parcial`, `4→concluido`, `5,6→cancelado`, `7→expirado` |
| 5. Download | `GET /documents/{uuid}/download` → `{"url": ...}`, then GET that url → bytes | |
| 6. Cancel | `POST /documents/{uuid}/cancel` — `{"comment": motivo}` | |

**Webhook validation.** D4Sign posts form-encoded with an HMAC in `Content-HMAC`
(`hmac_sha256(cryptKey, raw_body)`, hex). `validar_webhook` recomputes with `hmac.compare_digest` and
raises `WebhookInvalido` on mismatch. Body fields consumed: `uuid`, `type_post`, `message`.

**Credentials** (via `noctusai_lib.config.credentials.resolve_credential`, org-scoped):
`d4sign_api_token`, `d4sign_crypt_key`, `d4sign_safe_uuid`. Any missing ⇒ `ProvedorNaoConfigurado`
naming *which* one.

### 1.5 `factory.py`

```python
def make_signature_adapter(
    *, real: bool = False, provedor: str = "d4sign", org_id: str | None = None,
    resolver: Callable[[str, str | None], str | None] = resolve_credential,
) -> SignatureAdapter
```
Fake by default (seed rule). `real=True` + unknown `provedor` ⇒ `ValueError`. `real=True` + missing
credential ⇒ `ProvedorNaoConfigurado`. `resolver` is the Class-B DI test seam
(`KB § PATTERNS/backend/di-test-seam.md`) — never monkeypatch the module attribute.

### 1.6 · Sandbox + contract-verification harness (built 2026-09-17, no D4Sign account yet)

F2 (§0) still holds: **no D4Sign account exists on the platform.** Until one does, every wire shape in
`real.py` beyond what this section pins is a documented guess, each carrying its own
`NOC-REMEDIATE[d4sign-*]` marker at its call site. This section is what a future session reads to turn
each guess into an answer **fast** — the whole point of building this now instead of waiting for
credentials to show up and re-discovering all six corners from scratch.

**What exists:**

- `noctusai_lib.testing.d4sign_sandbox.D4SignSandbox` — a runnable local stub speaking the wire shapes
  THIS section pins (all 6 calls) plus a `_control/*` surface to advance an envelope through
  pending → parcial → concluido and emit the matching webhook with a real `Content-HMAC` (computed
  against the sandbox's own `crypt_key` — the exact function `real.py`'s `validar_webhook` verifies
  against). Drive it in-process via `httpx.ASGITransport(app=sandbox.app())` (zero network, what every
  test does) or run it standalone (`python -m noctusai_lib.testing.d4sign_sandbox --port 8790`) for a
  human with curl/Postman.
- `noctusai_lib.testing.d4sign_harness.run_contract_harness(mode=...)` — one named, executable
  assertion per marker below, selected by `mode="sandbox"` (today) or `mode="real"` (once credentials
  exist) — **never** by editing the harness. Every result carries a `status` from a closed vocabulary
  (`sandbox_coherent` / `verified_live` / `contradicted_live` / `unverified_needs_live` /
  `not_configured`) that makes a sandbox run structurally impossible to mistake for a live-vendor
  confirmation — `verified_live`/`contradicted_live` are LITERALLY UNREACHABLE from `mode="sandbox"`.
- `noctus.dev.d4sign_contract_verify` (MCP tool) — the same harness, agent-callable, mirroring
  `noctus.dev.sso_smoke`'s honesty contract (missing credentials ⇒ every marker `not_configured`,
  never a silent sandbox fallback).

**The 6 markers, and what answers each one:**

| # | Marker | Question | Answered by |
|---|---|---|---|
| 1 | `d4sign-portal-link` | Does `uploadbinary`'s response carry a real portal-link field, or is the synthesized `secure.d4sign.com.br/documents/{uuid}` URL correct? | `mode="real"`: inspect `raw_upload_response` for keys beyond `uuid`. |
| 2 | `d4sign-signer-external-id` | Does `createlist`'s response carry a real per-signer id? | `mode="real"`: inspect `raw_createlist_response`. |
| 3 | `d4sign-webhook-type-post` | Does `type_post` share the `statusId` vocabulary? | Needs a captured LIVE webhook (no D4Sign API can trigger a test delivery) — see below. |
| 4 | `d4sign-status-per-signer` | Does `GET /documents/{uuid}` carry per-signer detail? | `mode="real"`: inspect `raw_status_response` for keys beyond `statusId`. |
| 5 | `d4sign-sendtosigner-message` | Does D4Sign actually surface a caller-supplied message to signers? | Cannot auto-verify even with credentials — a human must check the real notification e-mail. Always `unverified_needs_live`. |
| 6 | `d4sign-error-body-shape` | Does a 4xx/5xx body carry `message`/`error`/`erro`? | `mode="real"`: provoke a real 4xx and eyeball the evidence — human judgement call, not auto-verdict. |

**Credential drop-in path (exactly what to set, where):**

1. Set three org-scoped values through the platform credential chain (`noctusai_lib.config.credentials.
   resolve_credential` — `org_settings` → `platform_settings` → env, per §1.4/§1.5):
   `d4sign_api_token`, `d4sign_crypt_key`, `d4sign_safe_uuid`. Fastest path for a first manual run: env
   vars `D4SIGN_API_TOKEN` / `D4SIGN_CRYPT_KEY` / `D4SIGN_SAFE_UUID` (tier 3, no DB write needed). For a
   real org, insert rows into `public.org_settings` keyed by `(org_id, key)` instead — never a
   product-local store (F1's `ProvedorNaoConfigurado` refusal only ever checks this one chain).
2. Run `await run_contract_harness(mode="real", org_id="<org-uuid>")` (or the MCP tool
   `noctus.dev.d4sign_contract_verify(mode="real", org_id=...)`). Markers 1/2/4/6 answer immediately
   from the first real API round-trip the harness makes.
3. Marker 3 (webhook vocabulary) additionally needs a captured live delivery: point the D4Sign
   dashboard's webhook URL at any reachable receiver (a temporary tunnel is enough), sign a real test
   document, save the raw POST body + headers as `{"body": "...", "headers": {...}}` to a JSON file,
   and pass `captured_webhook_path=<that file>` to the same call.
4. Marker 5 (sendtosigner message) never auto-resolves — open the notification e-mail a real signer
   receives and confirm the operator-supplied `mensagem` (contract §3.1) appears as sent.
5. **Once a marker's `status` comes back `verified_live`:** delete its `NOC-REMEDIATE[d4sign-*]` marker
   in `real.py` and fold the confirmed shape into this section's pinned wire table (§1.4) — the marker's
   job is done. **`contradicted_live`:** fix `real.py` to consume the real field instead of
   guessing/synthesizing, THEN delete the marker. Never delete a marker on a `sandbox_coherent` or
   `unverified_needs_live` result — those confirm nothing about the live vendor.

🔴 Do not read a clean `mode="sandbox"` harness run as "verified end to end" (F2's own ban still
applies) — `HarnessReport.all_verified_live` is hardcoded `False` whenever any marker is not
`verified_live`, and no sandbox marker can ever be `verified_live` by construction.

---

## 2 · social-wiring — migration 134

`134_contrato_assinatura.sql`. Additive only; no data touched.

```sql
create table if not exists social_wiring.atendimento_contrato_assinaturas (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  contrato_id uuid not null references social_wiring.atendimento_contratos(id),
  versao_id  uuid not null references social_wiring.atendimento_contrato_versoes(id),
  provedor text not null,
  external_id text not null,
  link_assinatura text not null,
  status text not null default 'pendente'
    check (status in ('pendente','parcial','concluido','cancelado','expirado')),
  signatarios jsonb not null default '[]'::jsonb,
  enviado_em timestamptz not null default now(),
  enviado_por uuid,
  concluido_em timestamptz,
  versao_assinada_id uuid references social_wiring.atendimento_contrato_versoes(id),
  cancelado_motivo text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
-- ONE live envelope per contract; a cancelled/expired one may be superseded.
create unique index if not exists atendimento_contrato_assinaturas_viva
  on social_wiring.atendimento_contrato_assinaturas (contrato_id)
  where status in ('pendente','parcial');
create unique index if not exists atendimento_contrato_assinaturas_externo
  on social_wiring.atendimento_contrato_assinaturas (provedor, external_id);
```
RLS: org-scoped select/insert/update mirroring `atendimento_contratos`' existing policies **verbatim**
(read them; do not invent a new shape). Service-role bypass for the webhook path.

`atendimento_contrato_versoes.origem` gains the value `'assinado'` (the signed copy comes back as a
version). Widen the existing CHECK; do not drop and recreate without `IF EXISTS`.

Ends with `NOTIFY pgrst, 'reload schema';`.

---

## 3 · Endpoint contract

All routes org-scoped through the existing `card_hub` auth dependency (`auth_parts`, `card_hub/auth.py`).
Bodies are **strict** — unknown fields rejected 422 (`KB § PATTERNS/backend/pydantic-strict-http.md`).

### 3.1 `POST /api/clientes/{cliente_id}/contratos/{contrato_id}/assinatura` → **201**

Request:
```json
{ "versao_id": "uuid",
  "signatarios": [ { "nome": "…", "email": "…", "cpf": "12345678901",
                     "papel": "comprador", "ordem": 0 } ],
  "mensagem": "optional, <= 500 chars" }
```
Response **201**:
```json
{ "assinatura_id": "uuid", "external_id": "…", "link_assinatura": "https://…",
  "provedor": "d4sign", "status": "pendente",
  "signatarios": [ { "email": "…", "external_id": "…", "assinado_em": null } ],
  "enviado_em": "2026-09-17T20:00:00Z" }
```

**Side-effects + state-after** (the stateful legs `noc-contract-first` requires):
1. The version's **PDF bytes** are read from storage and uploaded to the provider.
2. One `atendimento_contrato_assinaturas` row exists with `status='pendente'`.
3. `atendimento_contratos.status` **is already** `'enviado_assinatura'` when this returns 201 — the FE
   does not set it.
4. An LGPD access row is logged for the version read (same `acessos_table` path `url_versao` uses).

**Error taxonomy** (`status → codigo → pt-BR message`):

| Status | `codigo` | Cause | Message |
|---|---|---|---|
| 400 | `ASSINATURA_SEM_SIGNATARIOS` | empty list | "Informe ao menos um signatário." |
| 400 | `ASSINATURA_SIGNATARIO_INVALIDO` | bad email or CPF failing mod-11 | "CPF ou e-mail inválido para {nome}." |
| 404 | `CONTRATO_NAO_ENCONTRADO` / `VERSAO_NAO_ENCONTRADA` | not in this org, or soft-deleted | — |
| 409 | `ASSINATURA_JA_ENVIADA` | a `pendente`/`parcial` envelope exists | "Este contrato já está em assinatura." |
| 422 | `ASSINATURA_VERSAO_NAO_GERADA` | `versao.origem != 'gerado'` | "Só uma versão gerada pode ir para assinatura." |
| 422 | `ASSINATURA_PROVEDOR_NAO_CONFIGURADO` | `ProvedorNaoConfigurado`; `details.faltando` names the credentials | "Configure a plataforma de assinatura em Configurações." |
| 502 | `ASSINATURA_PROVEDOR_ERRO` | `ProvedorIndisponivel` / `EnvelopeRecusado`; `details.provedor_mensagem` carries the provider's text | "A plataforma de assinatura recusou o envio." |

🔴 **No 2xx may ever be returned with a mocked envelope.** (F1.)

### 3.2 `GET …/{contrato_id}/assinatura` → **200**

The live envelope, or **404** `ASSINATURA_NAO_ENCONTRADA` when none. Same body as 3.1 plus
`concluido_em`, `versao_assinada_id`, `cancelado_motivo`. **Read-only — never calls the provider**
(the webhook is the source of truth; polling the vendor on every page render is not).

### 3.3 `POST …/{contrato_id}/assinatura/cancelar` → **200**

Body `{ "motivo": "…" }` (required, 3..500 chars). Cancels at the provider, sets `status='cancelado'`
and `cancelado_motivo`. State-after: `atendimento_contratos.status` returns to `'em_revisao'`.
**409** `ASSINATURA_NAO_CANCELAVEL` when already `concluido`.

### 3.4 `POST /api/webhooks/assinatura/{provedor}` → **200 `{"ok": true}`**

**Unauthenticated by design; authenticity is the provider HMAC.** Mounted OUTSIDE the org-auth
dependency, on the existing webhook router pattern.

- Signature invalid/absent ⇒ **401** `WEBHOOK_ASSINATURA_INVALIDA`. Never 200.
- Unknown `external_id` ⇒ **200** `{"ok": true, "ignorado": true}` (a retired envelope must not make the
  provider retry forever) — and log at WARNING.
- Idempotent: replaying the same event is a no-op. Keyed on `(provedor, external_id, status)`.

**State-after on `status='concluido'`:**
1. `baixar_assinado` fetches the signed PDF.
2. It is stored as a **new version row** with `origem='assinado'`, next `numero`, `rotulo` =
   `"Assinado — {provedor}"`; its id lands in `assinaturas.versao_assinada_id`.
3. `assinaturas.status='concluido'`, `concluido_em` set.
4. `atendimento_contratos.status='assinado'`.

A download failure must **not** lose the event: persist `status='concluido'` first, leave
`versao_assinada_id` NULL, log `NOC-REMEDIATE[assinatura-download-retry]`, and still return 200.

---

## 4 · Frontend contract

`useContratos.ts` gains `assinatura` query + `enviarParaAssinatura` / `cancelarAssinatura` mutations,
consuming §3 **verbatim**.

- **"Enviar para assinatura"** appears only on a version with `origem === 'gerado'` and only when no live
  envelope exists.
- A dialog prefills signatários from the contract's partes (compradores + vendedores) and the org's two
  `org_testemunhas`; the operator may edit e-mails. Empty e-mail blocks submit client-side.
- While `pendente`/`parcial`: a status chip + "Abrir no {provedor}" link + "Cancelar envio".
- On `concluido`: the signed version appears in the list like any other; the chip reads "Assinado".
- **`status` stops being freely editable once an envelope exists** — the select is disabled with the
  hint "definido pela plataforma de assinatura". (Deprecation: the manual `enviado_assinatura` /
  `assinado` picks are now derived, not typed.)
- Loading: `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data` — never bare
  `isLoading` (`KB § PATTERNS/frontend/lying-loading-state.md`).
- 422 `ASSINATURA_PROVEDOR_NAO_CONFIGURADO` renders `details.faltando` inline with a link to
  Configurações, matching how `GeradorContratoSection` renders `faltando`.

---

## 5 · erp-imobiliario migration (replication-to-seed symmetry)

`products/erp-imobiliario/backend/app/services/signature_provider.py` is **deleted** and
`assinatura_service.py` consumes `make_signature_adapter`. Behavior changes on purpose, and the slice
must say so in its commit body:
- the DocuSign mock that claimed `dry_run: False` is gone — an unconfigured org now gets a typed refusal;
- ClickSign/DocuSign are not re-implemented in this pass. An erp org pointing at either gets
  `ProvedorNaoConfigurado` naming the provider as unsupported. **Surface to the tech-lead before landing
  if any erp org actually has clicksign/docusign credentials** (none did at authoring time — verified).

---

## 6 · Test recipes (each slice asserts against THIS file)

- **Seed**: Fake drives the full lifecycle; Real is tested against pinned response fixtures for each of
  the 6 D4Sign calls + HMAC validation (valid, tampered, absent); factory raises
  `ProvedorNaoConfigurado` naming each missing credential; `real=True` never returns a Fake.
- **SW backend**: every row of the §3.1 error table has a test; auth-boundary tests assert **strict
  `== 401`** (`KB § PATTERNS/compliance/auth-boundary-false-green.md`); webhook idempotency; the
  `concluido` path produces a version row with `origem='assinado'`; migration 134 shape test.
- **SW frontend**: vitest for the dialog prefill, the disabled-status rule, both refusal renderings, and
  the two loading signals.
- **E2E-shape check** (the one `noc-contract-first` mandates): a contract test hitting the real route with
  the Fake adapter injected, asserting the exact §3.1 201 body the FE destructures.

## 7 · Anti-goals

- ❌ Lift erp's `signature_provider.py` as-is. (F1.)
- ❌ Any silent fallback to a mock envelope, in any layer.
- ❌ Poll the provider on page render. The webhook is the source of truth.
- ❌ Store the signed PDF anywhere but as a normal version row (one storage path, one LGPD log).
- ❌ Claim "verified end to end" without D4Sign credentials. (F2.)
- ❌ ClickSign/DocuSign adapters in this pass.
