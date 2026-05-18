"""Pydantic In/Out schemas for the Google connector MCP tools.

Mirrors `mcp/vista/types.py`'s role: every tool's `inputSchema` is a
`*Input.model_json_schema()` and every handler returns a `*Output`
`.model_dump()`. Per `KB § PATTERNS/mcp-tool-conventions.md § 2`, schemas
are the contract the host LLM sees — keep field descriptions actionable.

Write tools (`calendar.create_event`, `youtube.upload_video`) carry a
required `confirm: bool` gate (confirm-then-execute, `KB § PATTERNS/
llm-bot-security.md`): the handler refuses the side-effect unless the
caller explicitly passed `confirm=true`, so a hallucinated/ambiguous LLM
call cannot silently mutate Google state.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ─── Calendar ────────────────────────────────────────────────────────────


class CalendarAttendeeModel(BaseModel):
    email: str = Field(description="Attendee email address.")
    display_name: Optional[str] = Field(
        default=None, description="Optional human-readable name."
    )


class CreateEventInput(BaseModel):
    calendar_id: str = Field(
        description="Target calendar id (e.g. 'primary' or a calendar email)."
    )
    summary: str = Field(description="Event title.")
    start_at: str = Field(
        description="Event start, ISO-8601 datetime (e.g. 2026-05-20T14:00:00)."
    )
    end_at: str = Field(description="Event end, ISO-8601 datetime.")
    timezone: str = Field(description="IANA tz name, e.g. 'America/Sao_Paulo'.")
    description: Optional[str] = Field(default=None, description="Event body text.")
    location: Optional[str] = Field(default=None, description="Free-text location.")
    attendees: list[CalendarAttendeeModel] = Field(
        default_factory=list, description="Optional attendee list."
    )
    request_id: Optional[str] = Field(
        default=None,
        description=(
            "Caller-stable idempotency hint (echoed into the event; the lib "
            "adapters do NOT yet enforce wire-level idempotency — dedupe at "
            "the call site)."
        ),
    )
    confirm: bool = Field(
        default=False,
        description=(
            "WRITE GATE — must be explicitly true to create the event. "
            "False (default) returns a typed error without mutating Calendar."
        ),
    )


class CreatedEventModel(BaseModel):
    event_id: str
    html_link: Optional[str] = None
    raw: dict[str, Any] = Field(default_factory=dict)


class CreateEventOutput(BaseModel):
    created: Optional[CreatedEventModel] = None
    adapter: str = Field(
        description="'fake' (no OAuth creds) or 'real' (OAuth-configured)."
    )


class ListEventsInput(BaseModel):
    calendar_id: str = Field(description="Calendar id to list from.")
    time_min: str = Field(description="Window start, ISO-8601 datetime.")
    time_max: str = Field(description="Window end, ISO-8601 datetime.")


class ListEventsOutput(BaseModel):
    events: list[CreatedEventModel] = Field(default_factory=list)
    adapter: str


# ─── Maps ────────────────────────────────────────────────────────────────


class CoordinatesModel(BaseModel):
    latitude: float
    longitude: float


class TravelEstimateInput(BaseModel):
    origin: CoordinatesModel = Field(description="Origin lat/lng.")
    destination: CoordinatesModel = Field(description="Destination lat/lng.")


class TravelEstimateOutput(BaseModel):
    minutes: int
    distance_meters: Optional[int] = None
    adapter: str = Field(
        description="'static' (no Maps key — flat estimate) or 'google'."
    )


# ─── YouTube ─────────────────────────────────────────────────────────────


class ChannelModel(BaseModel):
    id: str
    title: str
    description: str
    uploads_playlist_id: str


class VideoModel(BaseModel):
    id: str
    title: str
    description: str
    channel_id: str
    published_at: str
    duration_seconds: int
    view_count: int


class GetChannelInput(BaseModel):
    channel_id: str = Field(description="YouTube channel id (UC...).")


class GetChannelOutput(BaseModel):
    channel: Optional[ChannelModel] = None
    quota_units_consumed: int = Field(description="Quota cost of this call.")
    adapter: str


class ListChannelVideosInput(BaseModel):
    channel_id: str = Field(description="YouTube channel id (UC...).")
    page_token: Optional[str] = Field(
        default=None, description="Opaque next-page cursor from a prior call."
    )


class ListChannelVideosOutput(BaseModel):
    videos: list[VideoModel] = Field(default_factory=list)
    next_page_token: Optional[str] = None
    quota_units_consumed: int
    adapter: str


class GetVideoInput(BaseModel):
    video_id: str = Field(description="YouTube video id.")


class GetVideoOutput(BaseModel):
    video: Optional[VideoModel] = None
    quota_units_consumed: int
    adapter: str


# ─── Drive ───────────────────────────────────────────────────────────────


class ParseUrlInput(BaseModel):
    url_or_id: str = Field(
        description=(
            "A Drive share URL (file/d/{id}/..., open?id=, uc?id=, "
            "uc?export=download&id=) OR a bare file id."
        )
    )


class ParseUrlOutput(BaseModel):
    file_id: str = Field(description="Extracted Drive file id.")


class DriveFileModel(BaseModel):
    id: str
    name: str
    size_bytes: int
    mime_type: str
    md5_checksum: Optional[str] = None


class GetMetadataInput(BaseModel):
    file_id: str = Field(description="Drive file id (use drive.parse_url first).")


class GetMetadataOutput(BaseModel):
    file: Optional[DriveFileModel] = Field(
        default=None,
        description="None when the file is missing OR inaccessible (Drive "
        "returns 404 for both — by design).",
    )
    adapter: str = Field(description="'fake' (no api_key) or 'real'.")


class DownloadInput(BaseModel):
    file_id: str = Field(description="Drive file id to download.")
    dest_path: str = Field(
        description="Absolute filesystem path the bytes are written to."
    )


class DownloadOutput(BaseModel):
    file: Optional[DriveFileModel] = None
    written_to: Optional[str] = None
    adapter: str


__all__ = [
    "CalendarAttendeeModel",
    "CreateEventInput",
    "CreatedEventModel",
    "CreateEventOutput",
    "ListEventsInput",
    "ListEventsOutput",
    "CoordinatesModel",
    "TravelEstimateInput",
    "TravelEstimateOutput",
    "ChannelModel",
    "VideoModel",
    "GetChannelInput",
    "GetChannelOutput",
    "ListChannelVideosInput",
    "ListChannelVideosOutput",
    "GetVideoInput",
    "GetVideoOutput",
    "ParseUrlInput",
    "ParseUrlOutput",
    "DriveFileModel",
    "GetMetadataInput",
    "GetMetadataOutput",
    "DownloadInput",
    "DownloadOutput",
]
