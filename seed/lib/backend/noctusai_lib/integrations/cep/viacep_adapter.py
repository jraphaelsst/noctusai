"""Real network CEP lookup — ViaCEP first, BrasilAPI as fallback.

F3 (live prod test, 2026-09-30): there was NO CEP lookup anywhere in the
codebase; 4 of 19 people measured got a wrong `cidade` off a document
field (a neighbourhood-ish value, or — twice — a 57-char whole-address
string a `comprovante_endereco` read dumped straight into `cidade`), while
the CEP printed on the SAME document was correct for 15/19. A CEP is a
much smaller, checkable surface than free text — this adapter is the
single place that resolves one.

- `https://viacep.com.br/ws/{cep}/json/` — tried first; a not-found CEP
  returns HTTP 200 with `{"erro": true}`, never a 404 (ViaCEP's own
  documented shape — checked explicitly, not inferred from status code).
- `https://brasilapi.com.br/api/cep/v1/{cep}` — tried when ViaCEP fails
  OR has no record; a not-found CEP here IS a genuine 404.

🔴 A LOOKUP FAILURE IS LOGGED, NEVER RAISED
--------------------------------------------
Unlike `fx.BcbPtaxAdapter` (a missing PTAX bulletin is fatal to a cost
calculation, so it raises a typed error the caller must handle), a CEP
lookup here is ADVISORY enrichment of an address already read off a
document — a `clientes` row with a document-read cidade/uf and no CEP
corroboration is still strictly better than one this lookup blocked
entirely. Every failure mode (timeout, transport error, non-200, malformed
JSON, an explicit not-found from either service) is logged at `warning`
(recoverable — the caller's own values stay untouched) and the method
returns `None`. A short timeout is load-bearing for the same reason: a
slow/dead CEP service must never stall the extraction pipeline it merely
enriches.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

import httpx

from noctusai_lib.integrations.cep.types import CepEndereco

logger = logging.getLogger(__name__)

_VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"
_BRASILAPI_URL = "https://brasilapi.com.br/api/cep/v1/{cep}"
_DEFAULT_TIMEOUT = 3.0


def _digits(cep: str) -> str:
    return re.sub(r"\D", "", cep or "")


def _formatar(digits: str) -> str:
    return f"{digits[:5]}-{digits[5:]}"


class ViaCepAdapter:
    """Real `CepLookupAdapter` — ViaCEP, BrasilAPI fallback.

    `http_client` is a DI seam for tests (mocked, per the external-vendor-
    SDK carve-out — mirrors `BcbPtaxAdapter`'s own shape); when `None`, one
    short-lived `httpx.Client` is opened per lookup and always closed.
    """

    def __init__(
        self,
        http_client: Optional[httpx.Client] = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._http_client = http_client
        self._timeout = timeout

    def lookup(self, cep: str) -> Optional[CepEndereco]:
        digits = _digits(cep)
        if len(digits) != 8:
            logger.warning("cep.viacep_adapter: %r is not an 8-digit CEP", cep)
            return None

        resultado = self._via_cep(digits)
        if resultado is not None:
            return resultado
        return self._brasil_api(digits)

    # ─── ViaCEP ───────────────────────────────────────────────────────────

    def _via_cep(self, digits: str) -> Optional[CepEndereco]:
        data = self._get_json(_VIACEP_URL.format(cep=digits), servico="ViaCEP")
        if data is None:
            return None
        if data.get("erro"):
            logger.info("cep.viacep_adapter: ViaCEP has no record for %s", _formatar(digits))
            return None
        cidade = data.get("localidade") or None
        uf = data.get("uf") or None
        if not cidade or not uf:
            logger.warning(
                "cep.viacep_adapter: ViaCEP response for %s missing cidade/uf: %r",
                _formatar(digits), data,
            )
            return None
        return CepEndereco(
            cep=_formatar(digits),
            cidade=cidade,
            uf=uf,
            logradouro=data.get("logradouro") or None,
            bairro=data.get("bairro") or None,
        )

    # ─── BrasilAPI (fallback) ─────────────────────────────────────────────

    def _brasil_api(self, digits: str) -> Optional[CepEndereco]:
        data = self._get_json(_BRASILAPI_URL.format(cep=digits), servico="BrasilAPI")
        if data is None:
            return None
        cidade = data.get("city") or None
        uf = data.get("state") or None
        if not cidade or not uf:
            logger.warning(
                "cep.viacep_adapter: BrasilAPI response for %s missing cidade/uf: %r",
                _formatar(digits), data,
            )
            return None
        return CepEndereco(
            cep=_formatar(digits),
            cidade=cidade,
            uf=uf,
            logradouro=data.get("street") or None,
            bairro=data.get("neighborhood") or None,
        )

    # ─── Shared HTTP plumbing ─────────────────────────────────────────────

    def _get_json(self, url: str, *, servico: str) -> Optional[dict[str, Any]]:
        client = self._http_client or httpx.Client(timeout=self._timeout)
        try:
            try:
                response = client.get(url)
            except httpx.HTTPError as exc:
                logger.warning("cep.viacep_adapter: %s request failed: %s", servico, exc)
                return None
        finally:
            if self._http_client is None:
                client.close()

        if response.status_code == 404:
            # BrasilAPI's genuine not-found shape — ViaCEP never 404s (it
            # signals absence via `{"erro": true}` on a 200, handled by the
            # caller once the body parses).
            return None
        if response.status_code != 200:
            logger.warning(
                "cep.viacep_adapter: %s returned HTTP %s", servico, response.status_code,
            )
            return None
        try:
            return response.json()
        except ValueError as exc:
            logger.warning("cep.viacep_adapter: %s returned non-JSON body: %s", servico, exc)
            return None


__all__ = ["ViaCepAdapter"]
