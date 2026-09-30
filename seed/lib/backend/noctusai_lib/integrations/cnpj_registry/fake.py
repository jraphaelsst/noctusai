"""In-memory `CnpjRegistryLookup` — no IO, no BrasilAPI/ReceitaWS account
needed.

Mirrors `noctusai_lib.integrations.turnstile.fake.FakeTurnstileVerifier`'s
posture: the executable example of the contract, plus test seams
(`registrar`, a scripted `erro`) so a consumer's own suite can drive the
found / not-found / upstream-error branches without ever calling the real
APIs.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from noctusai_lib.integrations.documents.cnpj import normalize as normalize_cnpj

from .types import CnpjRegistryFields


class FakeCnpjRegistryLookup:
    """Deterministic in-memory `CnpjRegistryLookup`.

    Default posture: any CNPJ not explicitly `registrar`-ed resolves to a
    synthetic `ativa` company (mirrors `documents.cartao_cnpj.
    FakeCartaoCnpjExtractor`'s own "unscripted call succeeds with plausible
    synthetic data" default) — a consumer's happy-path tests don't need to
    fabricate a registry response for every CNPJ they touch.

    Two escape hatches:

    * `registrar(cnpj, fields)` — script a SPECIFIC CNPJ's own result
      (a `baixada` company, a `None` situação, whatever the test needs).
    * `erro=` at construction — every `lookup()` call raises this exception
      instead (`CnpjNotFoundError`/`CnpjRegistryUpstreamError` — a test
      driving the "lookup failed, field stays NULL" branch).
    """

    def __init__(self, *, erro: Optional[BaseException] = None) -> None:
        self._erro = erro
        self._resultados: dict[str, CnpjRegistryFields] = {}
        #: Recorded calls (normalised CNPJ), so a test can assert on
        #: intent — which CNPJ was actually looked up — not just the
        #: outcome. Mirrors `FakeTurnstileVerifier.calls`.
        self.chamadas: list[str] = []

    def registrar(self, cnpj: str, fields: CnpjRegistryFields) -> None:
        self._resultados[normalize_cnpj(cnpj)] = fields

    async def lookup(self, cnpj: str) -> CnpjRegistryFields:
        cnpj_norm = normalize_cnpj(cnpj)
        self.chamadas.append(cnpj_norm)
        if self._erro is not None:
            raise self._erro
        resultado = self._resultados.get(cnpj_norm)
        if resultado is not None:
            return resultado
        return CnpjRegistryFields(
            cnpj=cnpj_norm,
            razao_social="EMPRESA FAKE SINTETICA CONSULTA PUBLICA LTDA",
            situacao_cadastral="ativa",
            situacao_cadastral_bruta="ATIVA",
            data_situacao_cadastral=date(2010, 3, 15),
            source="fake",
            raw={},
        )


__all__ = ["FakeCnpjRegistryLookup"]
