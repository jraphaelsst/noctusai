# Contract — Interessados (public "receber futuras comunicações" signup)

Status: agreed 2026-09-21 · product `academia-de-reciclagem` · both sides build to THIS file.

## Why

The public site (landing, `/como-funciona`, `/a-carta`) opens a popup asking
**"Gostaria de receber futuras comunicações?"** with three fields — Nome,
WhatsApp, E-mail. Submissions are personal data (LGPD): they are stored with a
consent record, readable only by the product's admins, and erasable.

This is the fleet's first unauthenticated WRITE route. Kept product-local
(N=1); a second product needing public lead capture is the trigger to lift it
into the seed as a standard router.

## Data — `academia_de_reciclagem.interessados`

| column | type | notes |
|---|---|---|
| `id` | uuid pk default `gen_random_uuid()` | |
| `nome` | text not null | trimmed, 2–120 chars |
| `whatsapp` | text not null | stored NORMALIZED via `noctusai_lib.primitives.phone.normalize_phone` |
| `email` | text not null | stored lower-cased + trimmed; UNIQUE on `lower(email)` |
| `origem` | text null | public page path the popup was submitted from (`/`, `/como-funciona`, `/a-carta`), ≤ 80 chars |
| `consentimento_versao` | text not null | server constant `v1-2026-09` — identifies the consent wording shown |
| `consentimento_em` | timestamptz not null default `now()` | refreshed on every re-submission |
| `criado_em` / `atualizado_em` | timestamptz not null default `now()` | |

RLS enabled; only a `service_role` policy. **No `anon` grant** — migration
`010_anon_grant_lockdown.sql` stays true. The public route writes through the
backend (service role), never through PostgREST.

## Routes

### `POST /api/public/interessados` — no auth

Request (strict — unknown fields → 422):

```json
{ "nome": "Maria Silva", "whatsapp": "(11) 98765-4321", "email": "maria@exemplo.com",
  "consentimento": true, "origem": "/como-funciona" }
```

- `consentimento` MUST be literally `true` (the act of opting in); anything else → 422.
- `whatsapp` must pass `is_valid_phone`; invalid → 422.
- `email` must be a valid address; invalid → 422.
- `origem` optional.

Responses:

- `201 {"ok": true}` — for a NEW contact **and** for an already-registered
  e-mail (upsert on `lower(email)`: refresh `nome`, `whatsapp`, `origem`,
  `consentimento_em`, `atualizado_em`). Same status + body either way — the
  route never reveals whether an address is registered.
- `422 {"detail": "<pt-BR message>", "code": "invalid", "field": "<nome|whatsapp|email|consentimento>"}`
- `429` — rate limit, per client IP: **5/minute and 30/hour** (product `limiter`).

### `GET /api/interessados?limit=50&offset=0` — authenticated, admin

`200 {"items": [{"id","nome","whatsapp","email","origem","consentimento_versao","consentimento_em","criado_em"}], "total": N}` newest first. `limit` 1–200.
`401` without a session (strict `== 401` in tests) · `403` for a non-admin member.

### `DELETE /api/interessados/{id}` — authenticated, admin

`204` · `404` unknown id · `401` / `403` as above. (LGPD right to erasure.)

## Frontend obligations

- Popup on public pages only (never inside the signed-in app). Shown once per
  visitor after a short delay; closing (X / Esc / "Agora não") suppresses it
  for 30 days, a successful submit suppresses it permanently. Browser storage
  is read/written inside try/catch — it may be unavailable.
- The opt-in is the submit button itself; the popup states plainly what the
  data is used for (future communications from the Academia da Reciclagem).
- Internal page **Interessados** (signed-in, admin) lists the table with
  delete, following the no-lying-loading-state rule.
