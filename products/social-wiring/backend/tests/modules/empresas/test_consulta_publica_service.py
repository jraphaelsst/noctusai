"""`empresas.consulta_publica_service.resolver_pendentes` — the bounded
catch-up pass for every `empresas` row the automatic (c2) fill at
Crednet-creation time missed (owner decision, 2026-09-30: "the system
resolves itself; humans only when it truly can't").

WHAT THESE PIN
--------------
1. Every `situacao_cadastral IS NULL` row is picked up, oldest-first.
2. A row with `situacao_cadastral` already set is never selected (no
   redundant lookup).
3. A resolved row's `dados_origem` becomes `consulta_publica_cnpj` and a
   Cartão-CNPJ-sourced row is NEVER touched (the fill-empty contract —
   pinned again here at the sweep's OWN call boundary, not just in
   `dados_service`'s unit tests).
4. A lookup failure for ONE row is logged and skipped — never stops the
   run, never raises.
5. `limite` bounds the pass.
"""
from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from noctusai_lib.integrations.cnpj_registry import (
    CnpjNotFoundError,
    CnpjRegistryFields,
    FakeCnpjRegistryLookup,
)

from app.modules.empresas import consulta_publica_service
from tests.modules.empresas.conftest import ORG_ID, empresa_row

CNPJ_A = "11222333000181"
CNPJ_B = "12345678000195"
CNPJ_C = "98765432000198"


def _leitura(cnpj: str, **over) -> CnpjRegistryFields:
    base = dict(
        cnpj=cnpj, razao_social="EMPRESA PUBLICA LTDA",
        situacao_cadastral="ativa", situacao_cadastral_bruta="ATIVA",
        data_situacao_cadastral=date(2010, 3, 15), source="brasilapi", raw={},
    )
    base.update(over)
    return CnpjRegistryFields(**base)


class TestResolverPendentes:
    @pytest.mark.asyncio
    async def test_null_situacao_rows_are_resolved(self, client, scoped):
        empresa_id = str(uuid4())
        scoped.set_table_data("empresas", [
            empresa_row(empresa_id, cnpj=CNPJ_A, situacao_cadastral=None),
        ])
        lookup = FakeCnpjRegistryLookup()
        lookup.registrar(CNPJ_A, _leitura(CNPJ_A))

        resultado = await consulta_publica_service.resolver_pendentes(scoped, lookup)

        assert resultado == {"encontrados": 1, "resolvidos": 1, "falhas": 0}
        row = scoped.table("empresas").select("*").execute().data[0]
        assert row["situacao_cadastral"] == "ativa"
        assert row["dados_origem"] == "consulta_publica_cnpj"

    @pytest.mark.asyncio
    async def test_an_already_filled_row_is_never_selected(self, client, scoped):
        empresa_id = str(uuid4())
        scoped.set_table_data("empresas", [
            empresa_row(
                empresa_id, cnpj=CNPJ_A, situacao_cadastral="baixada",
                dados_origem="cartao_cnpj",
            ),
        ])
        lookup = FakeCnpjRegistryLookup()

        resultado = await consulta_publica_service.resolver_pendentes(scoped, lookup)

        assert resultado == {"encontrados": 0, "resolvidos": 0, "falhas": 0}
        assert lookup.chamadas == []
        row = scoped.table("empresas").select("*").execute().data[0]
        assert row["situacao_cadastral"] == "baixada"  # untouched
        assert row["dados_origem"] == "cartao_cnpj"  # untouched

    @pytest.mark.asyncio
    async def test_a_lookup_failure_is_skipped_not_raised(self, client, scoped):
        empresa_id = str(uuid4())
        scoped.set_table_data("empresas", [
            empresa_row(empresa_id, cnpj=CNPJ_A, situacao_cadastral=None),
        ])
        lookup = FakeCnpjRegistryLookup(
            erro=CnpjNotFoundError(CNPJ_A, source="brasilapi")
        )

        resultado = await consulta_publica_service.resolver_pendentes(scoped, lookup)

        assert resultado == {"encontrados": 1, "resolvidos": 0, "falhas": 1}
        row = scoped.table("empresas").select("*").execute().data[0]
        assert row.get("situacao_cadastral") is None  # left untouched, not guessed

    @pytest.mark.asyncio
    async def test_one_failure_does_not_stop_the_rest_of_the_run(self, client, scoped):
        e1, e2, e3 = str(uuid4()), str(uuid4()), str(uuid4())
        scoped.set_table_data("empresas", [
            empresa_row(e1, cnpj=CNPJ_A, situacao_cadastral=None, created_at="2026-01-01T00:00:00+00:00"),
            empresa_row(e2, cnpj=CNPJ_B, situacao_cadastral=None, created_at="2026-01-02T00:00:00+00:00"),
            empresa_row(e3, cnpj=CNPJ_C, situacao_cadastral=None, created_at="2026-01-03T00:00:00+00:00"),
        ])
        lookup = FakeCnpjRegistryLookup()
        lookup.registrar(CNPJ_A, _leitura(CNPJ_A))
        # CNPJ_B deliberately unregistered but the Fake's own `erro=` is not
        # set — so it resolves too (the synthetic default). To exercise a
        # PARTIAL failure, script the Fake to raise via a thin wrapper that
        # fails only for CNPJ_B.

        class _Parcial:
            def __init__(self, inner):
                self._inner = inner
                self.chamadas: list[str] = []

            async def lookup(self, cnpj):
                self.chamadas.append(cnpj)
                if cnpj == CNPJ_B:
                    raise CnpjNotFoundError(cnpj, source="brasilapi")
                return await self._inner.lookup(cnpj)

        lookup.registrar(CNPJ_C, _leitura(CNPJ_C, situacao_cadastral="baixada"))
        parcial = _Parcial(lookup)

        resultado = await consulta_publica_service.resolver_pendentes(scoped, parcial)

        assert resultado == {"encontrados": 3, "resolvidos": 2, "falhas": 1}
        rows = {r["id"]: r for r in scoped.table("empresas").select("*").execute().data}
        assert rows[e1]["situacao_cadastral"] == "ativa"
        assert rows[e2].get("situacao_cadastral") is None
        assert rows[e3]["situacao_cadastral"] == "baixada"

    @pytest.mark.asyncio
    async def test_limite_bounds_the_pass(self, client, scoped):
        ids = [str(uuid4()) for _ in range(3)]
        cnpjs = [CNPJ_A, CNPJ_B, CNPJ_C]
        scoped.set_table_data("empresas", [
            empresa_row(i, cnpj=c, situacao_cadastral=None, created_at=f"2026-01-0{n+1}T00:00:00+00:00")
            for n, (i, c) in enumerate(zip(ids, cnpjs))
        ])
        lookup = FakeCnpjRegistryLookup()

        resultado = await consulta_publica_service.resolver_pendentes(scoped, lookup, limite=2)

        assert resultado["encontrados"] == 2

    @pytest.mark.asyncio
    async def test_no_pending_rows_is_a_noop(self, client, scoped):
        scoped.set_table_data("empresas", [])
        lookup = FakeCnpjRegistryLookup()

        resultado = await consulta_publica_service.resolver_pendentes(scoped, lookup)

        assert resultado == {"encontrados": 0, "resolvidos": 0, "falhas": 0}
        assert lookup.chamadas == []
