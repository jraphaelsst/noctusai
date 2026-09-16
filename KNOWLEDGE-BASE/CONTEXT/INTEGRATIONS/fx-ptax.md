# BCB PTAX FX rate — consume-side reference (`noctusai_lib.integrations.fx`)

> **Purpose.** Authoritative consume-side reference for the
> ``noctusai_lib.integrations.fx`` seed package. Canonical
> Protocol + Fake + Real + factory shape mirroring `google_maps` /
> `olx`. This platform spends in USD (OpenAI) and charges in BRL —
> every LLM cost record needs the native amount, its BRL conversion,
> AND the rate used, so a historical cost never silently re-prices
> when the exchange rate moves later. This module is the single
> source of that rate.
>
> **Why this lives in KB.** Slice S4 of `edicao-fotos-contract` shipped
> this as a standalone seed organ (no product consumer yet); durable +
> self-contained per [[feedback_absorption_ships_consume_docs]].

---

## 1. What ships

Package: `seed/lib/backend/noctusai_lib/integrations/fx/`.

`__all__`:
- `PtaxRate` — frozen dataclass: `rate: Decimal`, `quote_date: date`,
  `bulletin_at: datetime`, `source: str`. `rate` is a `Decimal`,
  never a `float` — this is money.
- `FxRateAdapter` — `@runtime_checkable` Protocol: `get_ptax(quote_date:
  date) -> PtaxRate`.
- `FakeFxRateAdapter` — deterministic in-memory adapter. Seed with
  `bulletins={date(...): Decimal(...), ...}`; records every lookup on
  `.lookups` for test assertions; `.set_rate(date, Decimal)` to
  seed/override one entry.
- `BcbPtaxAdapter` — real adapter against BCB's public Olinda OData
  PTAX service. Caches by-instance (immutable-past-date rule below).
- `FxError` / `FxBulletinNotFoundError` / `FxUpstreamError` — typed
  errors (`errors.py`). No silent fallback.
- `get_fx_rate_adapter(live: bool = False, **kwargs)` — factory.
- `format_bcb_date`, `parse_ptax_response` — pure mappers (`mappers.py`).

---

## 2. The weekend/holiday walk-back rule (read this before calling)

BCB publishes **no PTAX bulletin** on weekends, holidays, or before
~13:00 BRT on the current day. `get_ptax(quote_date)` returns the
**latest published bulletin with `bulletin.quote_date <= quote_date`**
— NEVER today's date substituted for a missing one, and NEVER an
invented rate.

**Consumers MUST persist the RETURNED `quote_date`**, not the date they
requested — a Sunday lookup for a Friday-priced bulletin must record
"priced 2026-09-11", not "priced 2026-09-13". `bulletin_at` carries the
finer-grained BCB timestamp for audit.

When no bulletin exists **at all** within the adapter's lookback window
(default 10 days — covers any real holiday span, e.g. Christmas/New
Year), both adapters raise `FxBulletinNotFoundError(requested_date,
lookback_days)`. **The correct consumer behaviour is: catch it, mark
the cost record `fx_pending`, and backfill the real rate later** — never
substitute a default rate.

🔴 There is an `LLM_USD_TO_BRL=5.0` env-var default in
`noctusai_lib.integrations.llm.budget`, used ONLY to render a live cost
*estimate* while a call is in flight. It answers a different question
than this module (an estimate for something not-yet-priced vs. the
actual published rate for a specific trading day) and **must never be
used as a fallback for a `FxBulletinNotFoundError`** — doing so would
let a historical cost record silently re-price itself with no audit
trail. See `errors.py` module docstring for the full argument.

---

## 3. Consume recipe

```python
from datetime import date
from decimal import Decimal

from noctusai_lib.integrations.fx import (
    FxBulletinNotFoundError,
    get_fx_rate_adapter,
)

adapter = get_fx_rate_adapter(live=True)  # BcbPtaxAdapter; live=False (default) -> Fake

try:
    ptax = adapter.get_ptax(date.today())
except FxBulletinNotFoundError:
    # mark the cost record fx_pending; backfill later (e.g. a retry
    # once BCB has published, or a widened lookback_days)
    ...
else:
    brl_amount = usd_amount * ptax.rate
    # persist: brl_amount, ptax.rate, ptax.quote_date, ptax.source
```

Tests: instantiate `FakeFxRateAdapter({date(...): Decimal(...)})`
directly (no factory indirection needed) and seed only the business
days you want present — the Fake's walk-back mirrors the Real's, so a
gap in your fixture exercises the SAME `FxBulletinNotFoundError` path
production would take on a real weekend.

---

## 4. The Olinda API shape (learned by probing live, 2026-09-16)

No published OpenAPI/Swagger doc exists for this service, so the shape
below is captured in both this doc and the `bcb_adapter.py` module
docstring (the two are meant to be kept in sync if either drifts):

- Base: `https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata`.
  Public, keyless — no API key, no secret, no auth header.
- We call `CotacaoDolarPeriodo(dataInicial='MM-DD-YYYY',
  dataFinalCotacao='MM-DD-YYYY')?$top=1&$orderby=dataHoraCotacao
  desc&$format=json`, with the window `[quote_date - lookback_days,
  quote_date]`. `$top=1&$orderby=... desc` over that window returns
  **exactly** the newest bulletin at or before `dataFinalCotacao` in
  ONE request — no need to probe day-by-day.
- Response entity is `TipoCotacaoDolar` (the **fechamento-only**
  shape) — deliberately not `TipoCotacaoDolarAberturaOuIntermediario`
  (the intraday-quotes entity, which carries a `tipoBoletim` field and
  includes abertura/intermediate quotes we don't want):
  ```json
  {"value": [{"cotacaoCompra": 5.14840, "cotacaoVenda": 5.14900,
              "dataHoraCotacao": "2026-09-15 13:09:19.199664"}]}
  ```
  `cotacaoVenda` is the venda (sell) rate this module returns.
  `dataHoraCotacao`'s date component is the bulletin's real
  `quote_date`. Fractional-second digit count varies (observed both
  6-digit `.199664` and 5-digit `.70012`) — `strptime`'s `%f` handles
  both.
- **No bulletin** (weekend, holiday, or malformed `dataCotacao`
  string) → `{"value": []}` with **HTTP 200**, never a 4xx. Confirmed
  against `CotacaoDolarDia(dataCotacao='notadate')` too — an empty
  `value` is BCB's ONE "nothing here" signal.
- **Encoding gotcha:** `$orderby`'s space MUST be `%20`, not `+`. BCB's
  OData layer 400s on a literal `+`
  (`"the not-allowed value 'dataHoraCotacao+desc'"`) — which is exactly
  what `httpx`'s own `params=` dict produces (`application/
  x-www-form-urlencoded` `+`-for-space). `bcb_adapter.py` therefore
  builds the query string by hand with `urllib.parse.quote(...,
  safe="")` and passes the fully-formed URL to `client.get(url)` with
  no separate `params=`. Unencoded literal parentheses/single-quotes
  in the OData function-call PATH are accepted as-is.
- Money precision: parse the response body with `json.loads(text,
  parse_float=Decimal)`, not `response.json()` — avoids a float
  round-trip on the rate before it ever reaches a `Decimal`.

---

## 5. Real consumer

None yet — S4 shipped this as a standalone seed organ ahead of a
named consumer (the LLM-cost-in-BRL feature this was built for is a
follow-up slice). First consumer should wire it into the `llm_usage`
cost-recording path (`noctusai_lib.integrations.llm`) — persist
`ptax.rate` / `ptax.quote_date` / `ptax.source` alongside every USD
cost row, and add an `fx_pending` boolean/status column for the
`FxBulletinNotFoundError` backfill path.

Seed tests:
`seed/lib/backend/tests/integrations/fx/test_{fake_adapter,mappers,bcb_adapter}.py`
(33 assertions covering walk-back / lookback-window boundary / typed
errors / Decimal-never-float / URL-encoding regression guard /
in-process caching / Protocol conformance / factory resolution — all
offline, zero network, per [[feedback_seed_fake_real_pattern]]).

---

## 6. Gaps & follow-ups

- No credential/URL signal exists to auto-select Real vs Fake (BCB
  needs none) — the factory's `live: bool` flag is an explicit choice,
  documented in the `__init__.py` factory docstring as a deliberate
  deviation from the coincidental-signal shape (`get_routing_adapter`,
  `get_calendar_adapter`).
- The in-process cache is instance-scoped and unbounded (fine for a
  per-request-lifetime adapter instance; a long-lived singleton
  serving many distinct historical dates would want an eviction policy
  — not needed at N=1 consumer).
- `lookback_days` defaults to 10; a genuinely obscure multi-week BCB
  outage would still raise `FxBulletinNotFoundError` rather than walk
  further back — that's the intended "no silent errors" behaviour, not
  a gap to close reflexively.
