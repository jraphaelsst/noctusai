"""Tests for `noctusai_lib.integrations.vista` adapter layer.

Covers the high-level `VistaCRMAdapter` Protocol + `FakeVistaAdapter`
+ `VistaRESTAdapter` + `get_vista_adapter` factory shipped by
``social-wiring-vista-seed-lift`` 2026-05-20.

Network is NEVER hit — the Real adapter is exercised only at the
construction / typecheck boundary; round-trip semantics are covered
via the Fake.
"""

from __future__ import annotations

import inspect

import pytest

from noctusai_lib.domain.real_estate import PropertyData
from noctusai_lib.integrations.vista import (
    FakeVistaAdapter,
    VistaCRMAdapter,
    VistaNotConfigured,
    VistaRESTAdapter,
    get_vista_adapter,
)


@pytest.mark.asyncio
async def test_fake_vista_adapter_round_trip():
    """Seed a property, fetch by code, get None on missing."""
    seed = PropertyData(
        product_code="ONE10010",
        title="Apartamento 3 quartos — Moema",
        description="Apto reformado",
        address="Rua X, 123",
        price="R$ 1.200.000",
        bedrooms=3,
        area_sqm=120.0,
    )
    adapter = FakeVistaAdapter({"ONE10010": seed})

    fetched = await adapter.get_property("ONE10010")
    assert fetched is seed
    assert fetched.title == "Apartamento 3 quartos — Moema"

    missing = await adapter.get_property("ONE99999")
    assert missing is None


@pytest.mark.asyncio
async def test_fake_vista_adapter_add_property():
    """`add_property` mutates the in-memory store post-construction."""
    adapter = FakeVistaAdapter()
    assert await adapter.get_property("ONE20020") is None

    adapter.add_property(
        "ONE20020",
        PropertyData(product_code="ONE20020", title="Casa", description=""),
    )
    fetched = await adapter.get_property("ONE20020")
    assert fetched is not None
    assert fetched.product_code == "ONE20020"


def test_get_vista_adapter_fake_returns_fake():
    """`get_vista_adapter(fake=True)` returns `FakeVistaAdapter`."""
    adapter = get_vista_adapter(fake=True)
    assert isinstance(adapter, FakeVistaAdapter)


def test_get_vista_adapter_fake_with_seed_data():
    """`fake_data` pre-seeds the Fake at construction."""
    prop = PropertyData(product_code="ONE30030", title="X", description="")
    adapter = get_vista_adapter(fake=True, fake_data={"ONE30030": prop})
    assert isinstance(adapter, FakeVistaAdapter)
    # Synchronous internal access — confirms the seed reached the Fake.
    assert adapter._data["ONE30030"] is prop  # type: ignore[attr-defined]


def test_get_vista_adapter_missing_credentials_raises():
    """Empty `base_url` ∨ empty `api_key` (and fake=False) raises
    `VistaNotConfigured` — same contract as the source `CRMService.__init__`."""
    with pytest.raises(VistaNotConfigured):
        get_vista_adapter(base_url="", api_key="")

    with pytest.raises(VistaNotConfigured):
        get_vista_adapter(base_url="https://x.test", api_key="")

    with pytest.raises(VistaNotConfigured):
        get_vista_adapter(base_url="", api_key="Y")


def test_get_vista_adapter_real_returns_rest_adapter():
    """`get_vista_adapter(base_url=X, api_key=Y)` returns `VistaRESTAdapter`
    — does NOT hit the network (construction only)."""
    adapter = get_vista_adapter(base_url="https://vista.test", api_key="K")
    assert isinstance(adapter, VistaRESTAdapter)


def test_vista_rest_adapter_get_property_is_async():
    """Signature check — `VistaRESTAdapter.get_property` is a coroutine
    function (so it satisfies the `VistaCRMAdapter` Protocol)."""
    assert inspect.iscoroutinefunction(VistaRESTAdapter.get_property)


def test_fake_vista_adapter_satisfies_protocol():
    """Structural typing check: `FakeVistaAdapter` instance is usable as
    a `VistaCRMAdapter` (signature has the async `get_property(code)`)."""
    adapter: VistaCRMAdapter = FakeVistaAdapter()
    assert hasattr(adapter, "get_property")
    assert inspect.iscoroutinefunction(adapter.get_property)


@pytest.mark.asyncio
async def test_vista_rest_adapter_invalid_code_returns_none():
    """`get_property` short-circuits on bad-format codes — no network."""
    adapter = VistaRESTAdapter(base_url="https://vista.test", api_key="K")
    # `not_a_code` doesn't match `^ONE\\d{3,6}$`; returns None without
    # ever opening an HTTP client.
    assert await adapter.get_property("not_a_code") is None
