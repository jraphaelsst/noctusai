"""Estimate travel time and distance between two coordinates via Google Maps."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from context import NoctusContext, noctus_context


class CoordinatesInput(BaseModel):
    latitude: float = Field(description="Latitude in decimal degrees.")
    longitude: float = Field(description="Longitude in decimal degrees.")


class TravelEstimateInput(BaseModel):
    origin: CoordinatesInput
    destination: CoordinatesInput


class TravelEstimateOutput(BaseModel):
    minutes: int = Field(description="Estimated travel time in minutes.")
    distance_meters: int | None = Field(
        default=None, description="Distance in meters when available."
    )
    raw: dict[str, Any] | None = None


def travel_estimate(
    payload: TravelEstimateInput,
    ctx: NoctusContext | None = None,
) -> TravelEstimateOutput:
    """Estimate travel time and distance from origin to destination via Google Maps Routes."""
    if ctx is not None:
        return _impl(payload, ctx)
    with noctus_context() as owned_ctx:
        return _impl(payload, owned_ctx)


def _impl(payload: TravelEstimateInput, ctx: NoctusContext) -> TravelEstimateOutput:
    from noctusai_lib.integrations.google_maps import Coordinates

    estimate = ctx.routing.travel_estimate(
        Coordinates(
            latitude=payload.origin.latitude, longitude=payload.origin.longitude
        ),
        Coordinates(
            latitude=payload.destination.latitude,
            longitude=payload.destination.longitude,
        ),
    )
    return TravelEstimateOutput(
        minutes=estimate.minutes,
        distance_meters=estimate.distance_meters,
        raw=estimate.raw,
    )


def register(server: FastMCP) -> None:
    @server.tool(
        name="google.maps.travel_estimate",
        description=travel_estimate.__doc__,
    )
    def _handler(payload: TravelEstimateInput) -> TravelEstimateOutput:
        return travel_estimate(payload)
