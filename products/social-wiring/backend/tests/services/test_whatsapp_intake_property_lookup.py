"""`WhatsAppIntakeService` product-code resolution — local mirror, no Vista.

Roadmap `social-wiring-imoveis-vista-2026-08`, P2.5: `lookup_property`
(the chatbot tool-call surface) resolves against `social_wiring.imoveis`
via `ImoveisService`, never a live Vista call. No fallback branch on a
miss — `lookup_property` reports `property_not_found` (actionable), and a
genuine lookup failure reports `imoveis_lookup_failed` (also actionable,
distinct from a miss) — neither path silently retries against Vista.

Same minimal fake-client convention as `test_imoveis_service.py`.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock
from uuid import uuid4

from noctusai_lib.domain.real_estate import Imovel

from app.services.imoveis_service import _imovel_to_row
from app.services.whatsapp_intake_service import WhatsAppIntakeService

ORG = uuid4()
_SYNCED_AT = "2026-08-03T23:50:31Z"


class _FakeReadTable:
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


def _make_intake(admin_supabase, org_id=ORG) -> WhatsAppIntakeService:
    redis_stub = MagicMock()
    return WhatsAppIntakeService(
        waha_base_url="https://waha.example.com",
        waha_api_key="test-key",
        waha_session="default",
        redis_client=redis_stub,
        authorized_numbers=[],
        crm_service=None,  # unused for lookups after P2.5 — see delivery note
        admin_supabase=admin_supabase,
        youtube_service=None,
        upload_dir="/tmp/uploads",
        org_id=org_id,
    )


class TestLookupPropertyHit:
    def test_one_prefixed_code(self):
        row = _row(
            "ONE10640",
            titulo="Apartamento 3 quartos — Moema",
            bairro="Moema",
            cidade="São Paulo",
            dormitorios=3,
            area_privativa=90.0,
        )
        svc = _make_intake(_FakeReadClient([row]))

        result = asyncio.run(svc.lookup_property("one10640"))

        assert result["ok"] is True
        assert result["product_code"] == "ONE10640"
        assert result["title"] == "Apartamento 3 quartos — Moema"
        assert result["bedrooms"] == 3

    def test_non_one_prefixed_code(self):
        """`CA0190` is a real live code — 285/1919 catalog rows carry a
        non-ONE prefix (roadmap census, 2026-08-03)."""
        row = _row("CA0190", titulo="Casa com piscina", bairro="Alphaville")
        svc = _make_intake(_FakeReadClient([row]))

        result = asyncio.run(svc.lookup_property("CA0190"))

        assert result["ok"] is True
        assert result["product_code"] == "CA0190"
        assert result["title"] == "Casa com piscina"


class TestLookupPropertyMiss:
    def test_miss_fails_loudly_with_an_actionable_error(self):
        """A code not in the local catalog is real information, reported
        as a specific, named error — never a generic crash and never
        silently retried against Vista."""
        svc = _make_intake(_FakeReadClient([]))

        result = asyncio.run(svc.lookup_property("ONE99999"))

        assert result["ok"] is False
        assert result["error"] == "property_not_found"
        assert result["product_code"] == "ONE99999"

    def test_invalid_code_format_rejected_before_any_lookup(self):
        svc = _make_intake(_FakeReadClient([]))

        result = asyncio.run(svc.lookup_property("nope"))

        assert result["ok"] is False
        assert result["error"] == "invalid_product_code"


class TestLookupPropertyBackendFailure:
    def test_db_failure_is_a_distinct_actionable_error_not_a_500(self):
        """The lookup ITSELF failing (DB/transport) must not be reported
        as a plain miss — `imoveis_lookup_failed`, naming the code, not a
        bare exception surfacing to the WhatsApp user."""
        svc = _make_intake(_RaisingClient())

        result = asyncio.run(svc.lookup_property("ONE10640"))

        assert result["ok"] is False
        assert result["error"] == "imoveis_lookup_failed"
        assert result["product_code"] == "ONE10640"
        assert "ONE10640" in result["message"]
