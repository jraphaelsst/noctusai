"""`ImoveisService.get_property_data` — the local-mirror product-code resolver.

Roadmap `social-wiring-imoveis-vista-2026-08`, P2.5: WhatsApp intake +
the youtube-dashboard upload path resolve a product code against
`social_wiring.imoveis` instead of a live Vista call. No fallback branch —
a miss is real information (the code is not in our catalog), and a lookup
failure (DB/transport problem) is a DIFFERENT, louder failure mode than a
clean miss.

Uses a minimal hand-rolled fake (same convention as
`test_imoveis_sync_service.py`'s `_FakeClient`/`_FakeTable`) rather than
`MockSupabaseClient`, because `MockSupabaseClient.schema(...)` returns a
fresh scoped instance on every call — sharing seeded rows across
`ImoveisService._table()`'s own `self._client.schema(...).table(...)` calls
needs identity-caching (`_SchemaCachingClient`, already duplicated 3x
elsewhere in this test tree) this suite doesn't need for a single-table
read path.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from noctusai_lib.domain.real_estate import Imovel, PropertyData

from app.services.imoveis_service import (
    ImoveisLookupError,
    ImoveisService,
    _imovel_to_row,
)

ORG = uuid4()
_SYNCED_AT = "2026-08-03T23:50:31Z"


class _FakeReadTable:
    """Supports the exact chain `ImoveisService.get` issues:
    `.select(...).eq(...).eq(...).limit(...).execute()`."""

    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._filters: dict = {}

    def select(self, *_a, **_kw):
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def limit(self, *_a, **_kw):
        return self

    def execute(self):
        matched = [
            r for r in self._rows
            if all(r.get(k) == v for k, v in self._filters.items())
        ]

        class _Resp:
            data = matched

        return _Resp()


class _FakeReadClient:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def schema(self, _name):
        return self

    def table(self, _name):
        return _FakeReadTable(self._rows)


class _RaisingClient:
    """Simulates a genuine lookup failure (DB/transport problem) —
    distinct from a clean miss."""

    class _Boom:
        def select(self, *_a, **_kw):
            return self

        def eq(self, *_a, **_kw):
            return self

        def limit(self, *_a, **_kw):
            return self

        def execute(self):
            from postgrest.exceptions import APIError

            raise APIError({"message": "connection refused", "code": "08006"})

    def schema(self, _name):
        return self

    def table(self, _name):
        return self._Boom()


def _row(codigo: str, **kw) -> dict:
    imovel = Imovel(codigo=codigo, **kw)
    return _imovel_to_row(imovel, ORG, _SYNCED_AT)


class TestGetPropertyDataHit:
    def test_resolves_a_one_prefixed_code(self):
        row = _row(
            "ONE10640",
            titulo="Apartamento 3 quartos — Moema",
            bairro="Moema",
            cidade="São Paulo",
            valor_venda=1_200_000.0,
            dormitorios=3,
            area_privativa=90.0,
        )
        svc = ImoveisService(_FakeReadClient([row]))

        result = svc.get_property_data(ORG, "ONE10640")

        assert isinstance(result, PropertyData)
        assert result.product_code == "ONE10640"
        assert result.title == "Apartamento 3 quartos — Moema"
        assert result.bedrooms == 3
        assert result.area_sqm == 90.0
        assert result.price == "R$ 1.200.000,00"

    def test_resolves_a_non_one_prefixed_code(self):
        """Census fact: 285/1919 catalog rows carry a non-ONE prefix
        (CA/TE/AR/AP/GA/PR). `CA0190` is a real code on the live tenant —
        the resolver must not special-case the ONE prefix anywhere."""
        row = _row(
            "CA0190",
            titulo="Casa com piscina",
            bairro="Alphaville",
            cidade="Barueri",
            valor_venda=2_500_000.0,
            dormitorios=4,
        )
        svc = ImoveisService(_FakeReadClient([row]))

        result = svc.get_property_data(ORG, "CA0190")

        assert result is not None
        assert result.product_code == "CA0190"
        assert result.title == "Casa com piscina"

    def test_description_sourced_from_vista_raw(self):
        """`PropertyData.description` has no dedicated `Imovel` column — it
        lives in the preserved `vista_raw` payload, same field priority as
        the live-Vista mapper (`VistaRESTAdapter._map_response`)."""
        row = _row("ONE10641", titulo="Studio")
        row["vista_raw"] = {"DescricaoWeb": "Studio mobiliado no centro."}
        svc = ImoveisService(_FakeReadClient([row]))

        result = svc.get_property_data(ORG, "ONE10641")

        assert result.description == "Studio mobiliado no centro."


class TestGetPropertyDataMiss:
    def test_returns_none_not_an_exception(self):
        """A clean miss is real information (not in our catalog) — `None`,
        never a substituted/patched-over value and never a crash."""
        svc = ImoveisService(_FakeReadClient([]))

        result = svc.get_property_data(ORG, "ONE99999")

        assert result is None

    def test_miss_is_scoped_by_org(self):
        """A row for a DIFFERENT org must not leak across the org boundary
        (defense in depth on top of RLS — `ImoveisService`'s own docstring)."""
        other_org_row = _row("ONE10640")  # seeded under ORG below
        svc = ImoveisService(_FakeReadClient([other_org_row]))

        result = svc.get_property_data(uuid4(), "ONE10640")

        assert result is None


class TestGetPropertyDataLookupFailure:
    def test_db_failure_raises_actionable_error_not_a_generic_crash(self):
        """The lookup ITSELF failing (DB/transport) is a different, louder
        failure mode than a clean miss — callers must be able to tell the
        two apart, and the message must name the code (actionable), not be
        a bare stack trace."""
        svc = ImoveisService(_RaisingClient())

        with pytest.raises(ImoveisLookupError) as exc_info:
            svc.get_property_data(ORG, "ONE10640")

        message = str(exc_info.value)
        assert "ONE10640" in message
