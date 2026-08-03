"""In-memory deterministic `VistaCRMAdapter` for dev + tests.

Distinct from `FakeVistaClient` (the low-level endpoint-shape fake) —
this is the domain-shape fake: seed it with `{code: PropertyData}` and
calls return the seeded PropertyData (or ``None`` when the code isn't
registered).

Use this in product tests / dev when you don't want to drive raw Vista
payloads through the showcase normalizers.

**Both halves of the seam live here.** When `VistaCRMAdapter` grew
`get_imovel` / `list_imoveis` (roadmap P2.0b), this Fake grew them in the
same commit. A Protocol method with only a Real implementation is a
half-shipped seam: it silently forces every consumer of the new method into
integration tests against a live tenant, which is the failure
`KB § PATTERNS/backend/seed-fake-real-adapter.md` exists to prevent.
"""

from __future__ import annotations

from typing import Optional

from noctusai_lib.domain.real_estate import Imovel, ImovelPage, PropertyData


class FakeVistaAdapter:
    """In-memory ``VistaCRMAdapter`` stand-in.

    Seed at construction (``data={...}`` for `PropertyData`, ``imoveis={...}``
    for `Imovel`) or via ``add_property`` / ``add_imovel``. Getters return the
    seeded value or ``None``; never raise.

    The two stores are independent on purpose — a test exercising only the
    YouTube fan-out seeds `PropertyData` and never thinks about `Imovel`,
    and vice versa.
    """

    def __init__(
        self,
        data: dict[str, PropertyData] | None = None,
        imoveis: dict[str, Imovel] | None = None,
    ) -> None:
        self._data: dict[str, PropertyData] = dict(data or {})
        self._imoveis: dict[str, Imovel] = dict(imoveis or {})

    # ── PropertyData surface ──

    def add_property(self, code: str, prop: PropertyData) -> None:
        self._data[code] = prop

    async def get_property(self, code: str) -> PropertyData | None:
        return self._data.get(code)

    # ── Imovel surface ──

    def add_imovel(self, imovel: Imovel) -> None:
        """Register an `Imovel`, keyed by its own `codigo`.

        Takes the model rather than a ``(code, model)`` pair — the code is
        already on it, and accepting both invites them to disagree.
        """
        self._imoveis[imovel.codigo] = imovel

    async def get_imovel(self, code: str) -> Optional[Imovel]:
        return self._imoveis.get(code)

    async def list_imoveis(
        self, *, page: int = 1, page_size: int = 50, with_detalhes: bool = False
    ) -> ImovelPage:
        """Paginate the seeded imóveis in insertion order.

        `with_detalhes` is accepted and ignored: the Fake's imóveis are
        already whole, so there is no second call to make. Honouring the
        signature still matters — a consumer that passes it must not break
        when swapped onto the Fake, which is the point of the seam.
        """
        items = list(self._imoveis.values())
        total = len(items)
        pages = max(1, (total + page_size - 1) // page_size)
        start = max(0, (page - 1) * page_size)
        return ImovelPage(
            items=items[start : start + page_size],
            total=total,
            page=page,
            pages=pages,
        )
