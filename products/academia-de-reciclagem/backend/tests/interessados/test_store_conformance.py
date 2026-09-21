"""Protocol-conformance + behavior suite for `InteressadosStore`.

Runs EXCLUSIVELY against `FakeInteressadosStore` -- `PgInteressadosStore`
needs a live Postgres, which this slice is forbidden from applying
migrations to (see `app/interessados/pg.py`'s
`NOC-REMEDIATE[test]` note).
"""
from __future__ import annotations

import inspect
from uuid import uuid4

import pytest

from app.interessados.fake import FakeInteressadosStore
from app.interessados.store import InteressadosStore

_KW = inspect.Parameter.KEYWORD_ONLY

_EXPECTED_SIGNATURES: dict[str, list[tuple[str, inspect._ParameterKind]]] = {
    "upsert": [
        ("nome", _KW), ("whatsapp", _KW), ("email", _KW),
        ("origem", _KW), ("consentimento_versao", _KW),
    ],
    "list": [("limit", _KW), ("offset", _KW)],
    "delete": [],
}


@pytest.mark.parametrize("method_name,expected", _EXPECTED_SIGNATURES.items())
def test_fake_matches_protocol_signature(method_name, expected):
    proto_method = getattr(InteressadosStore, method_name)
    fake_method = getattr(FakeInteressadosStore, method_name)
    for method in (proto_method, fake_method):
        params = [
            (name, p.kind)
            for name, p in inspect.signature(method).parameters.items()
            if name != "self"
        ]
        # `delete` takes one positional id param -- assert it exists,
        # without pinning its literal name (both sides use
        # `interessado_id`, but this test's job is Protocol/Fake parity,
        # not bikeshedding the name twice).
        if method_name == "delete":
            assert len(params) == 1
            continue
        assert params == expected, (method, params, expected)


@pytest.fixture
def store() -> FakeInteressadosStore:
    return FakeInteressadosStore()


class TestUpsert:
    @pytest.mark.asyncio
    async def test_new_email_creates_one_row(self, store):
        await store.upsert(
            nome="Maria Silva", whatsapp="+5511987654321", email="Maria@Exemplo.com",
            origem="/como-funciona", consentimento_versao="v1-2026-09",
        )
        rows, total = await store.list(limit=50, offset=0)
        assert total == 1
        assert rows[0]["email"] == "maria@exemplo.com"  # lower-cased
        assert rows[0]["nome"] == "Maria Silva"

    @pytest.mark.asyncio
    async def test_resubmission_refreshes_same_row_not_a_duplicate(self, store):
        await store.upsert(
            nome="Maria Silva", whatsapp="+5511987654321", email="maria@exemplo.com",
            origem="/", consentimento_versao="v1-2026-09",
        )
        first_rows, _ = await store.list(limit=50, offset=0)
        first_id = first_rows[0]["id"]
        first_consentimento_em = first_rows[0]["consentimento_em"]

        await store.upsert(
            nome="Maria S. Silva", whatsapp="+5511999998888", email="MARIA@EXEMPLO.COM",
            origem="/a-carta", consentimento_versao="v1-2026-09",
        )
        rows, total = await store.list(limit=50, offset=0)
        assert total == 1  # still one row, not two
        assert rows[0]["id"] == first_id
        assert rows[0]["nome"] == "Maria S. Silva"
        assert rows[0]["whatsapp"] == "+5511999998888"
        assert rows[0]["origem"] == "/a-carta"
        assert rows[0]["consentimento_em"] >= first_consentimento_em


class TestList:
    @pytest.mark.asyncio
    async def test_newest_first_and_pagination(self, store):
        for i in range(3):
            await store.upsert(
                nome=f"Pessoa {i}", whatsapp="+5511987654321",
                email=f"pessoa{i}@exemplo.com", origem=None,
                consentimento_versao="v1-2026-09",
            )
        rows, total = await store.list(limit=2, offset=0)
        assert total == 3
        assert len(rows) == 2
        # newest first: last-inserted appears first.
        assert rows[0]["email"] == "pessoa2@exemplo.com"

        page2, total2 = await store.list(limit=2, offset=2)
        assert total2 == 3
        assert len(page2) == 1
        assert page2[0]["email"] == "pessoa0@exemplo.com"


class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_existing_returns_true(self, store):
        await store.upsert(
            nome="Maria Silva", whatsapp="+5511987654321", email="maria@exemplo.com",
            origem=None, consentimento_versao="v1-2026-09",
        )
        rows, _ = await store.list(limit=1, offset=0)
        assert await store.delete(rows[0]["id"]) is True
        _, total = await store.list(limit=50, offset=0)
        assert total == 0

    @pytest.mark.asyncio
    async def test_delete_unknown_id_returns_false(self, store):
        assert await store.delete(uuid4()) is False
