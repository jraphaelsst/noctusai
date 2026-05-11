"""Tests for `app.services.maps` — Phase 8 Google Maps routing wiring.

Verifies:
  * ``GoogleMapsTravelLookup.travel_minutes`` delegates to the seed
    ``RoutingAdapter`` and handles missing-coord rows + same-id pairs.
  * ``configure_maps_module`` builds a ``MapsModule`` with a
    `StaticRoutingAdapter` fallback when no api_key is supplied.
  * Custom adapter injection seam works.
  * ``load_condominium_coords`` parses rows + filters incomplete ones.

Per the rule "No monkey-patching of our own code" — patches target
the Supabase boundary via `MockSupabaseClient`; adapter swaps go
through the explicit ``adapter=`` injection seam.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.google_maps import (
    Coordinates,
    StaticRoutingAdapter,
    TravelEstimate,
)
from noctusai_lib.testing import MockSupabaseClient, MockSupabaseResponse


ORG_ID = "00000000-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# Module reset fixture
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_maps_module():
    from app.services import maps as maps_mod

    maps_mod._reset_for_tests()
    yield
    maps_mod._reset_for_tests()


# ---------------------------------------------------------------------------
# GoogleMapsTravelLookup
# ---------------------------------------------------------------------------


class TestGoogleMapsTravelLookup:
    """`GoogleMapsTravelLookup.travel_minutes` bridges location-id → coords
    → seed RoutingAdapter."""

    def test_returns_zero_for_same_location(self):
        from app.services.maps import GoogleMapsTravelLookup

        adapter = StaticRoutingAdapter(default_minutes=20)
        coords = {
            "condo-a": Coordinates(latitude=-23.55, longitude=-46.63),
        }
        lookup = GoogleMapsTravelLookup(adapter=adapter, location_coords=coords)

        assert lookup.travel_minutes("condo-a", "condo-a") == 0

    def test_delegates_to_adapter_for_distinct_locations(self):
        from app.services.maps import GoogleMapsTravelLookup

        adapter = StaticRoutingAdapter(default_minutes=25)
        coords = {
            "condo-a": Coordinates(latitude=-23.55, longitude=-46.63),
            "condo-b": Coordinates(latitude=-23.60, longitude=-46.70),
        }
        lookup = GoogleMapsTravelLookup(adapter=adapter, location_coords=coords)

        # StaticRoutingAdapter returns its default_minutes for distinct coords.
        assert lookup.travel_minutes("condo-a", "condo-b") == 25

    def test_returns_default_when_origin_unknown(self):
        from app.services.maps import GoogleMapsTravelLookup

        adapter = StaticRoutingAdapter(default_minutes=20)
        coords = {
            "condo-b": Coordinates(latitude=-23.60, longitude=-46.70),
        }
        lookup = GoogleMapsTravelLookup(
            adapter=adapter,
            location_coords=coords,
            default_minutes=99,
        )

        # Origin missing → returns default.
        assert lookup.travel_minutes("condo-MISSING", "condo-b") == 99

    def test_returns_default_when_destination_unknown(self):
        from app.services.maps import GoogleMapsTravelLookup

        adapter = StaticRoutingAdapter(default_minutes=20)
        coords = {
            "condo-a": Coordinates(latitude=-23.55, longitude=-46.63),
        }
        lookup = GoogleMapsTravelLookup(
            adapter=adapter,
            location_coords=coords,
            default_minutes=7,
        )
        assert lookup.travel_minutes("condo-a", "condo-MISSING") == 7

    def test_add_location_updates_mapping(self):
        from app.services.maps import GoogleMapsTravelLookup

        adapter = StaticRoutingAdapter(default_minutes=20)
        lookup = GoogleMapsTravelLookup(adapter=adapter, location_coords={})

        # Initially nothing known → returns default 0.
        assert lookup.travel_minutes("condo-a", "condo-b") == 0

        lookup.add_location("condo-a", Coordinates(latitude=-23.55, longitude=-46.63))
        lookup.add_location("condo-b", Coordinates(latitude=-23.60, longitude=-46.70))
        # Now both known → static adapter returns its default.
        assert lookup.travel_minutes("condo-a", "condo-b") == 20

    def test_uses_custom_adapter_estimate(self):
        """Sanity-check: a custom RoutingAdapter returning a specific
        TravelEstimate.minutes is honored by GoogleMapsTravelLookup."""
        from app.services.maps import GoogleMapsTravelLookup

        class _CustomAdapter:
            def travel_estimate(self, origin, destination) -> TravelEstimate:
                # Asymmetric to confirm origin/destination are passed through.
                return TravelEstimate(minutes=42, distance_meters=5000)

        coords = {
            "condo-a": Coordinates(latitude=-23.55, longitude=-46.63),
            "condo-b": Coordinates(latitude=-23.60, longitude=-46.70),
        }
        lookup = GoogleMapsTravelLookup(
            adapter=_CustomAdapter(), location_coords=coords,
        )
        assert lookup.travel_minutes("condo-a", "condo-b") == 42


# ---------------------------------------------------------------------------
# configure_maps_module
# ---------------------------------------------------------------------------


class TestConfigureMapsModule:
    def test_defaults_to_static_when_no_api_key(self):
        from app.services.maps import configure_maps_module, get_maps_module

        module = configure_maps_module(api_key=None)
        assert isinstance(module.adapter, StaticRoutingAdapter)
        assert get_maps_module() is module

    def test_accepts_supplied_adapter(self):
        from app.services.maps import configure_maps_module

        class _CustomAdapter:
            def travel_estimate(self, origin, destination) -> TravelEstimate:
                return TravelEstimate(minutes=11)

        custom = _CustomAdapter()
        module = configure_maps_module(adapter=custom)
        assert module.adapter is custom

    def test_wires_location_coords_into_travel_lookup(self):
        from app.services.maps import configure_maps_module

        coords = {
            "condo-a": Coordinates(latitude=-23.55, longitude=-46.63),
            "condo-b": Coordinates(latitude=-23.60, longitude=-46.70),
        }
        module = configure_maps_module(location_coords=coords)
        assert module.travel_lookup.travel_minutes("condo-a", "condo-a") == 0
        # StaticRoutingAdapter default_minutes is 20.
        assert module.travel_lookup.travel_minutes("condo-a", "condo-b") == 20

    def test_get_raises_when_not_configured(self):
        from app.services.maps import get_maps_module

        with pytest.raises(RuntimeError, match="not configured"):
            get_maps_module()


# ---------------------------------------------------------------------------
# load_condominium_coords
# ---------------------------------------------------------------------------


class TestLoadCondominiumCoords:
    def test_returns_coords_for_each_row(self):
        from app.services.maps import load_condominium_coords

        db = MockSupabaseClient(data=[])
        scoped = db.schema("imobi_scheduling")
        scoped.set_sequential_responses(
            "condominiums",
            [
                MockSupabaseResponse(
                    data=[
                        {"id": "c1", "latitude": -23.55, "longitude": -46.63},
                        {"id": "c2", "latitude": -23.60, "longitude": -46.70},
                    ]
                )
            ],
        )
        # `load_condominium_coords` opens its own .schema(...) instance,
        # so we need to seed responses at the same path it'll hit. We
        # monkey-patch by re-binding `db.schema` to return our scoped.
        db.schema = lambda name, _scoped=scoped: _scoped

        coords = load_condominium_coords(db, org_id=ORG_ID)
        assert "c1" in coords
        assert coords["c1"].latitude == pytest.approx(-23.55)
        assert coords["c1"].longitude == pytest.approx(-46.63)
        assert "c2" in coords

    def test_skips_rows_missing_coords(self):
        from app.services.maps import load_condominium_coords

        db = MockSupabaseClient(data=[])
        scoped = db.schema("imobi_scheduling")
        scoped.set_sequential_responses(
            "condominiums",
            [
                MockSupabaseResponse(
                    data=[
                        {"id": "c1", "latitude": -23.55, "longitude": -46.63},
                        {"id": "c2", "latitude": None, "longitude": -46.70},
                        {"id": "c3", "latitude": -23.60, "longitude": None},
                    ]
                )
            ],
        )
        db.schema = lambda name, _scoped=scoped: _scoped

        coords = load_condominium_coords(db, org_id=ORG_ID)
        assert "c1" in coords
        assert "c2" not in coords
        assert "c3" not in coords

    def test_returns_empty_on_db_error(self):
        from app.services.maps import load_condominium_coords

        class _BrokenClient:
            def schema(self, _name):
                raise RuntimeError("connection refused")

        coords = load_condominium_coords(_BrokenClient(), org_id=ORG_ID)
        assert coords == {}
