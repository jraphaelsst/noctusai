"""In-memory deterministic `VistaCRMAdapter` for dev + tests.

Distinct from `FakeVistaClient` (the low-level endpoint-shape fake) —
this is the domain-shape fake: seed it with `{code: PropertyData}` and
calls return the seeded PropertyData (or ``None`` when the code isn't
registered).

Use this in product tests / dev when you don't want to drive raw Vista
payloads through the showcase normalizers.
"""

from __future__ import annotations

from noctusai_lib.domain.real_estate import PropertyData


class FakeVistaAdapter:
    """In-memory ``VistaCRMAdapter`` stand-in.

    Seed at construction (``data={...}``) or via ``add_property``.
    ``get_property`` returns the seeded value or ``None``; never raises.
    """

    def __init__(self, data: dict[str, PropertyData] | None = None) -> None:
        self._data: dict[str, PropertyData] = dict(data or {})

    def add_property(self, code: str, prop: PropertyData) -> None:
        self._data[code] = prop

    async def get_property(self, code: str) -> PropertyData | None:
        return self._data.get(code)
