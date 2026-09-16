"""Real BCB Olinda PTAX adapter — venda (sell), fechamento (closing) rate.

**API shape learned by probing the live API on 2026-09-16** (kept here
because the Olinda OData service has no published OpenAPI/Swagger doc a
future agent could read instead):

- Base: `https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata`
- We call `CotacaoDolarPeriodo(dataInicial='MM-DD-YYYY',dataFinalCotacao=
  'MM-DD-YYYY')?$top=1&$orderby=dataHoraCotacao desc&$format=json` with
  `dataInicial = quote_date - lookback_days` and `dataFinalCotacao =
  quote_date`. This does the "walk back to the latest bulletin `<=
  quote_date`" logic in ONE request — BCB's own `$top=1&$orderby=...
  desc` over the window returns exactly the newest bulletin at or before
  `dataFinalCotacao`; no need to probe day-by-day.
- No API key / auth required — Olinda PTAX is a public, keyless OData
  service.
- Response shape is the `TipoCotacaoDolar` entity (fechamento-ONLY —
  deliberately NOT `TipoCotacaoDolarAberturaOuIntermediario`, the
  intraday-quotes entity that carries a `tipoBoletim` field and would
  need filtering to keep only the closing bulletin):
  `{"value": [{"cotacaoCompra": 5.1484, "cotacaoVenda": 5.149,
  "dataHoraCotacao": "2026-09-15 13:09:19.199664"}]}`.
  `cotacaoVenda` is the venda (sell) rate this module returns.
  `dataHoraCotacao`'s date component IS the bulletin's real quote_date
  (may differ from the requested date after a walk-back).
- No bulletin exists on weekends, holidays, or (same-day) before ~13:00
  BRT → `value: []`, HTTP 200 (never a 4xx). A garbage `dataCotacao`
  string ALSO returns `{"value": []}` rather than erroring — confirmed
  against `CotacaoDolarDia(dataCotacao='notadate')`. So an empty `value`
  is BCB's one and only "nothing here" signal; `parse_ptax_response`
  returns `None` for it and this adapter turns that into
  `FxBulletinNotFoundError`, never a different error class.
- `$orderby`'s space MUST be percent-encoded as `%20`, not `+`. BCB's
  OData layer 400s on a literal `+` (`"the not-allowed value
  'dataHoraCotacao+desc'"`) — which is exactly what `httpx`'s own
  `params=` dict encoding produces (it uses `application/
  x-www-form-urlencoded` `+`-for-space, matching `urllib.parse.
  quote_plus`, not `quote`). So this adapter builds the query string by
  hand with `urllib.parse.quote(..., safe="")` (default `%XX` encoding)
  and passes the fully-formed URL string to `client.get(url)` with no
  separate `params=` — verified end-to-end against the live API.
  Unencoded literal parentheses/single-quotes in the PATH portion (the
  OData function-call syntax itself) are accepted as-is by BCB; only
  the query-string space needed manual handling.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import quote

import httpx

from noctusai_lib.integrations.fx.errors import FxBulletinNotFoundError, FxUpstreamError
from noctusai_lib.integrations.fx.mappers import format_bcb_date, parse_ptax_response
from noctusai_lib.integrations.fx.types import PtaxRate

logger = logging.getLogger(__name__)

_BASE_URL = "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata"
_DEFAULT_LOOKBACK_DAYS = 10
_DEFAULT_TIMEOUT = 10.0


class BcbPtaxAdapter:
    """Real BCB Olinda PTAX adapter.

    Caches by requested `quote_date` AND by the bulletin's actual
    `quote_date` in-process: a past date's fechamento bulletin is
    immutable (BCB never revises a published PTAX), so a repeat lookup
    for the same date must not re-hit the network.
    """

    def __init__(
        self,
        http_client: httpx.Client | None = None,
        lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._http_client = http_client
        self._lookback_days = lookback_days
        self._timeout = timeout
        self._cache: dict[date, PtaxRate] = {}

    def get_ptax(self, quote_date: date) -> PtaxRate:
        cached = self._cache.get(quote_date)
        if cached is not None:
            return cached

        result = self._fetch(quote_date)
        self._cache[quote_date] = result
        self._cache.setdefault(result.quote_date, result)
        return result

    def _fetch(self, quote_date: date) -> PtaxRate:
        url = self._build_url(quote_date)

        client = self._http_client or httpx.Client(timeout=self._timeout)
        try:
            try:
                response = client.get(url)
            except httpx.HTTPError as exc:
                logger.warning("fx.bcb_adapter: request to Olinda failed: %s", exc)
                raise FxUpstreamError(f"BCB Olinda unreachable: {exc}") from exc
        finally:
            if self._http_client is None:
                client.close()

        if response.status_code != 200:
            logger.warning(
                "fx.bcb_adapter: Olinda returned HTTP %s for %s",
                response.status_code,
                quote_date.isoformat(),
            )
            raise FxUpstreamError(
                f"BCB Olinda returned HTTP {response.status_code} "
                f"for quote_date={quote_date.isoformat()}"
            )

        try:
            payload = json.loads(response.text, parse_float=Decimal)
        except ValueError as exc:
            raise FxUpstreamError(f"BCB Olinda returned non-JSON body: {exc}") from exc

        try:
            rate = parse_ptax_response(payload)
        except (KeyError, ValueError) as exc:
            raise FxUpstreamError(
                f"BCB Olinda response shape unexpected: {payload!r}"
            ) from exc

        if rate is None:
            raise FxBulletinNotFoundError(quote_date, self._lookback_days)
        return rate

    def _build_url(self, quote_date: date) -> str:
        start = quote_date - timedelta(days=self._lookback_days)
        path = (
            "CotacaoDolarPeriodo(dataInicial='"
            f"{format_bcb_date(start)}',dataFinalCotacao='"
            f"{format_bcb_date(quote_date)}')"
        )
        query = "$top=1&$orderby=" + quote("dataHoraCotacao desc", safe="") + "&$format=json"
        return f"{_BASE_URL}/{path}?{query}"


__all__ = ["BcbPtaxAdapter"]
