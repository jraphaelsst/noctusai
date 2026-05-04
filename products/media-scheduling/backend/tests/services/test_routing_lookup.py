"""Same-condominium duration semantics + condo-aware travel lookup.

Ported from `whatsapp-google-scheduling/tests/test_condominium_travel_service.py`.

Source-side: `app.services.condominium_travel_service.CondominiumTravelService`
sat between the routing adapter (Coordinates → minutes) and the scheduling
engine (location_id → minutes). The product replaces it with
`app.services.routing_lookup.RoutingLookup` — same shape (id-keyed
travel_minutes), driven by the seed `RoutingAdapter` Protocol.

Translated:
  - SQLAlchemy session of condominiums → minimal Supabase-shaped stub
    (the product is Supabase-client-native).
  - "Same condominium" returns 0 minutes WITHOUT calling the adapter (the
    seed engine relies on this convention to skip transition buffers
    within a single locality).
  - Coordinate-cache-per-instance behavior preserved.
  - Missing-coords fallback preserved (configurable via constructor).
"""

from __future__ import annotations

from dataclasses import dataclass

from noctusai_lib.integrations.google_maps import Coordinates, StaticRoutingAdapter
from noctusai_lib.integrations.google_maps.types import TravelEstimate

from app.services.routing_lookup import RoutingLookup


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


@dataclass
class _StubResponse:
    data: object


class _StubBuilder:
    def __init__(self, table: str, store: dict[int, dict]):
        self._table = table
        self._store = store
        self._filter_id: int | None = None

    def select(self, *_args, **_kwargs) -> "_StubBuilder":
        return self

    def eq(self, col: str, value: object) -> "_StubBuilder":
        if col == "id":
            self._filter_id = int(value)  # type: ignore[arg-type]
        return self

    def single(self) -> "_StubBuilder":
        return self

    def execute(self) -> _StubResponse:
        if self._filter_id is None:
            return _StubResponse(data=None)
        return _StubResponse(data=self._store.get(self._filter_id))


class _StubSchema:
    def __init__(self, store: dict[int, dict], track_calls: list[str] | None = None):
        self._store = store
        self._track = track_calls

    def table(self, name: str) -> _StubBuilder:
        if self._track is not None:
            self._track.append(name)
        return _StubBuilder(name, self._store)


class _StubSupabase:
    """Minimal `supabase.Client` shape exercised by `RoutingLookup._coords`:
    `.schema("media_scheduling").table("condominiums").select(...).eq("id", x).single().execute()`.
    """

    def __init__(self, condos: dict[int, dict]):
        self._store = condos
        self.table_calls: list[str] = []

    def schema(self, _name: str) -> _StubSchema:
        return _StubSchema(self._store, self.table_calls)


class _RecordingAdapter:
    """Source: `_RecordingAdapter` — counts coordinate-pair invocations."""

    def __init__(self) -> None:
        self.calls: list[tuple[Coordinates, Coordinates]] = []

    def travel_estimate(
        self, origin: Coordinates, destination: Coordinates
    ) -> TravelEstimate:
        self.calls.append((origin, destination))
        return TravelEstimate(minutes=22)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_returns_zero_minutes_for_same_condominium_without_calling_adapter() -> None:
    adapter = _RecordingAdapter()
    sb = _StubSupabase({1: {"latitude": -23.6, "longitude": -46.8}})
    lookup = RoutingLookup(supabase=sb, adapter=adapter)  # type: ignore[arg-type]

    assert lookup.travel_minutes(1, 1) == 0
    assert adapter.calls == []
    # Same-id short-circuit must skip the DB roundtrip too.
    assert sb.table_calls == []


def test_resolves_coordinates_and_calls_adapter_for_distinct_condominiums() -> None:
    adapter = _RecordingAdapter()
    sb = _StubSupabase(
        {
            1: {"latitude": -23.60, "longitude": -46.88},
            2: {"latitude": -23.59, "longitude": -46.83},
        }
    )
    lookup = RoutingLookup(supabase=sb, adapter=adapter)  # type: ignore[arg-type]

    minutes = lookup.travel_minutes(1, 2)

    assert minutes == 22
    assert len(adapter.calls) == 1
    origin, destination = adapter.calls[0]
    assert origin == Coordinates(latitude=-23.60, longitude=-46.88)
    assert destination == Coordinates(latitude=-23.59, longitude=-46.83)


def test_falls_back_to_default_when_coordinates_missing() -> None:
    adapter = _RecordingAdapter()
    sb = _StubSupabase(
        {
            1: {"latitude": -23.60, "longitude": -46.88},
            2: {"latitude": None, "longitude": None},
        }
    )
    lookup = RoutingLookup(
        supabase=sb,  # type: ignore[arg-type]
        adapter=adapter,
        fallback_minutes_when_coords_missing=45,
    )

    minutes = lookup.travel_minutes(1, 2)

    assert minutes == 45
    assert adapter.calls == []  # adapter never invoked when coords missing.


def test_caches_coordinate_lookups_per_instance() -> None:
    sb = _StubSupabase(
        {
            1: {"latitude": -23.60, "longitude": -46.88},
            2: {"latitude": -23.59, "longitude": -46.83},
        }
    )
    lookup = RoutingLookup(
        supabase=sb,  # type: ignore[arg-type]
        adapter=StaticRoutingAdapter(default_minutes=20),
    )

    lookup.travel_minutes(1, 2)
    lookup.travel_minutes(1, 2)
    lookup.travel_minutes(2, 1)

    # Per-instance cache: each unique condo_id resolves at most once,
    # regardless of how many times it appears as origin or destination.
    assert sb.table_calls.count("condominiums") == 2
