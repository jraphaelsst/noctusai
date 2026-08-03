"""The Fake+Real seam is complete — structurally, not by inspection.

`KB § PATTERNS/backend/seed-fake-real-adapter.md`: a seed IO module ships
Protocol + Fake + Real + factory, or it generates consumer-side forks. The
specific failure this guards is a Protocol method implemented only on Real:
it type-checks, it passes review, and it silently forces every consumer of
that method into live-tenant integration tests because the Fake can't stand
in for it.

Asserting the method list from the Protocol rather than hardcoding it means
these tests fail when someone adds a THIRD method to `VistaCRMAdapter` and
forgets the Fake — which is the case a hand-written list would miss.
"""

from __future__ import annotations

import asyncio
import inspect

from noctusai_lib.domain.real_estate import Imovel, ImovelPage
from noctusai_lib.integrations.vista import (
    FakeVistaAdapter,
    VistaCRMAdapter,
    VistaRESTAdapter,
)


def _protocol_methods(proto) -> set[str]:
    return {
        name
        for name, member in vars(proto).items()
        if not name.startswith("_") and inspect.isfunction(member)
    }


def test_protocol_declares_the_expected_surface():
    """Pins the seam so a silent narrowing is visible in the diff."""
    assert _protocol_methods(VistaCRMAdapter) == {
        "get_property",
        "get_imovel",
        "list_imoveis",
    }


def test_fake_implements_every_protocol_method():
    missing = _protocol_methods(VistaCRMAdapter) - set(dir(FakeVistaAdapter))
    assert not missing, f"FakeVistaAdapter is missing {sorted(missing)} — half-shipped seam"


def test_real_implements_every_protocol_method():
    missing = _protocol_methods(VistaCRMAdapter) - set(dir(VistaRESTAdapter))
    assert not missing, f"VistaRESTAdapter is missing {sorted(missing)} — half-shipped seam"


def test_fake_and_real_signatures_agree():
    """A Fake that takes different kwargs is not a stand-in.

    Signature drift is how a Fake stops being swappable without anyone
    noticing — the consumer passes `with_detalhes=True`, the Fake raises
    TypeError, and it only shows up under test.
    """
    for name in _protocol_methods(VistaCRMAdapter):
        fake_sig = inspect.signature(getattr(FakeVistaAdapter, name))
        real_sig = inspect.signature(getattr(VistaRESTAdapter, name))
        assert set(fake_sig.parameters) == set(real_sig.parameters), (
            f"{name}: Fake{tuple(fake_sig.parameters)} != Real{tuple(real_sig.parameters)}"
        )


def test_fake_list_imoveis_paginates_and_reports_totals():
    fake = FakeVistaAdapter()
    for i in range(1, 8):
        fake.add_imovel(Imovel(codigo=f"ONE{1000 + i}"))

    page1 = asyncio.run(fake.list_imoveis(page=1, page_size=3))
    assert isinstance(page1, ImovelPage)
    assert len(page1.items) == 3
    assert page1.total == 7
    assert page1.pages == 3
    assert page1.has_next is True

    last = asyncio.run(fake.list_imoveis(page=3, page_size=3))
    assert len(last.items) == 1
    assert last.has_next is False


def test_fake_accepts_with_detalhes_without_breaking():
    """The Fake has nothing extra to fetch, but must not reject the kwarg."""
    fake = FakeVistaAdapter()
    fake.add_imovel(Imovel(codigo="ONE1001"))
    page = asyncio.run(fake.list_imoveis(with_detalhes=True))
    assert len(page.items) == 1


def test_fake_get_imovel_returns_none_for_unknown_code():
    assert asyncio.run(FakeVistaAdapter().get_imovel("ONE9999")) is None


def test_add_imovel_keys_off_the_models_own_codigo():
    fake = FakeVistaAdapter()
    fake.add_imovel(Imovel(codigo="CA0190"))
    assert asyncio.run(fake.get_imovel("CA0190")) is not None
