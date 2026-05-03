"""StaticRoutingAdapter + mappers tests + GoogleMapsRoutingAdapter
smoke (with mocked httpx client)."""

from unittest.mock import MagicMock

import pytest

from noctusai_lib.integrations.google_maps import (
    Coordinates,
    GoogleMapsRoutingAdapter,
    StaticRoutingAdapter,
    TravelEstimate,
    build_routes_request,
    get_routing_adapter,
    parse_routes_response,
)


def _origin() -> Coordinates:
    return Coordinates(latitude=-23.5, longitude=-46.6)


def _destination() -> Coordinates:
    return Coordinates(latitude=-23.6, longitude=-46.7)


# ---- StaticRoutingAdapter ---------------------------------------------------


def test_static_returns_default_minutes_for_distinct_coordinates() -> None:
    estimate = StaticRoutingAdapter().travel_estimate(_origin(), _destination())
    assert estimate.minutes == 20


def test_static_returns_zero_for_identical_coordinates() -> None:
    origin = _origin()
    estimate = StaticRoutingAdapter().travel_estimate(origin, origin)
    assert estimate.minutes == 0


def test_static_default_minutes_overridable() -> None:
    estimate = StaticRoutingAdapter(default_minutes=30).travel_estimate(
        _origin(), _destination()
    )
    assert estimate.minutes == 30


# ---- Mappers ---------------------------------------------------------------


def test_build_routes_request_carries_lat_lng_and_drive_mode() -> None:
    body = build_routes_request(_origin(), _destination())
    assert body["origin"]["location"]["latLng"] == {
        "latitude": -23.5,
        "longitude": -46.6,
    }
    assert body["destination"]["location"]["latLng"] == {
        "latitude": -23.6,
        "longitude": -46.7,
    }
    assert body["travelMode"] == "DRIVE"
    assert body["routingPreference"] == "TRAFFIC_UNAWARE"


def test_parse_routes_response_extracts_minutes_and_distance() -> None:
    response = {
        "routes": [
            {
                "duration": "1500s",  # 25 minutes
                "distanceMeters": 12345,
            }
        ]
    }
    estimate = parse_routes_response(response)
    assert estimate.minutes == 25
    assert estimate.distance_meters == 12345


def test_parse_routes_response_rounds_seconds_up() -> None:
    response = {"routes": [{"duration": "61s", "distanceMeters": 100}]}
    assert parse_routes_response(response).minutes == 2  # ceil(61/60)


def test_parse_routes_response_handles_missing_routes() -> None:
    estimate = parse_routes_response({"routes": []})
    assert estimate.minutes == 0
    assert estimate.distance_meters is None


def test_parse_routes_response_handles_missing_distance() -> None:
    response = {"routes": [{"duration": "120s"}]}
    estimate = parse_routes_response(response)
    assert estimate.minutes == 2
    assert estimate.distance_meters is None


def test_parse_routes_response_handles_garbage_duration() -> None:
    response = {"routes": [{"duration": "garbage", "distanceMeters": 100}]}
    estimate = parse_routes_response(response)
    assert estimate.minutes == 0


# ---- GoogleMapsRoutingAdapter (mocked) -------------------------------------


def test_google_maps_adapter_posts_to_routes_endpoint_with_api_key() -> None:
    fake_response = MagicMock()
    fake_response.json.return_value = {
        "routes": [{"duration": "1500s", "distanceMeters": 12345}]
    }
    fake_response.raise_for_status = MagicMock()
    fake_client = MagicMock()
    fake_client.post.return_value = fake_response

    adapter = GoogleMapsRoutingAdapter(api_key="key-123", http_client=fake_client)

    estimate = adapter.travel_estimate(_origin(), _destination())

    assert estimate.minutes == 25
    assert estimate.distance_meters == 12345
    fake_client.post.assert_called_once()
    call_args = fake_client.post.call_args
    assert call_args[0][0] == GoogleMapsRoutingAdapter.BASE_URL
    headers = call_args[1]["headers"]
    assert headers["X-Goog-Api-Key"] == "key-123"
    assert headers["X-Goog-FieldMask"] == GoogleMapsRoutingAdapter.FIELD_MASK


# ---- Factory ---------------------------------------------------------------


def test_factory_returns_google_when_api_key_provided() -> None:
    adapter = get_routing_adapter(api_key="key-123")
    assert isinstance(adapter, GoogleMapsRoutingAdapter)


def test_factory_returns_static_when_no_api_key() -> None:
    adapter = get_routing_adapter(api_key=None)
    assert isinstance(adapter, StaticRoutingAdapter)


# ---- Failure modes ---------------------------------------------------------


def test_google_adapter_propagates_5xx_via_raise_for_status() -> None:
    import httpx as _httpx

    fake_response = MagicMock()
    fake_response.raise_for_status.side_effect = _httpx.HTTPStatusError(
        "503 backend overloaded",
        request=MagicMock(),
        response=MagicMock(status_code=503),
    )
    fake_client = MagicMock()
    fake_client.post.return_value = fake_response

    adapter = GoogleMapsRoutingAdapter(api_key="k", http_client=fake_client)
    with pytest.raises(_httpx.HTTPStatusError):
        adapter.travel_estimate(_origin(), _destination())


def test_google_adapter_propagates_timeout() -> None:
    import httpx as _httpx

    fake_client = MagicMock()
    fake_client.post.side_effect = _httpx.TimeoutException("read timeout")

    adapter = GoogleMapsRoutingAdapter(api_key="k", http_client=fake_client)
    with pytest.raises(_httpx.TimeoutException):
        adapter.travel_estimate(_origin(), _destination())


def test_google_adapter_propagates_401_unauthorized() -> None:
    import httpx as _httpx

    fake_response = MagicMock()
    fake_response.raise_for_status.side_effect = _httpx.HTTPStatusError(
        "401 unauthorized",
        request=MagicMock(),
        response=MagicMock(status_code=401),
    )
    fake_client = MagicMock()
    fake_client.post.return_value = fake_response

    adapter = GoogleMapsRoutingAdapter(api_key="bad-key", http_client=fake_client)
    with pytest.raises(_httpx.HTTPStatusError):
        adapter.travel_estimate(_origin(), _destination())


def test_google_adapter_closes_http_client_on_exception() -> None:
    """When adapter constructs its own httpx.Client, it must close it
    even if the request raises (the existing finally block)."""
    import httpx as _httpx

    fake_internal_client = MagicMock()
    fake_internal_client.post.side_effect = _httpx.ConnectError("dns failed")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(_httpx, "Client", lambda **_: fake_internal_client)

        # http_client=None → adapter constructs internally → must close on raise
        adapter = GoogleMapsRoutingAdapter(api_key="k", http_client=None)
        with pytest.raises(_httpx.ConnectError):
            adapter.travel_estimate(_origin(), _destination())

    fake_internal_client.close.assert_called_once()
