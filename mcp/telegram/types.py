"""Pydantic inputs for every `telegram.*` tool (`extra="forbid"`: a typo'd
argument is a loud 422, not a silently ignored option). Outputs are plain
dicts — the vendor payload shape is authoritative."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class _In(BaseModel):
    model_config = {"extra": "forbid"}


class NoArgs(_In):
    pass


class DialogsListInput(_In):
    limit: int = Field(default=50, ge=1, le=500)
    query: Optional[str] = Field(default=None, description="Case-insensitive title/username filter.")


class MessagesListInput(_In):
    chat: str = Field(description="Numeric chat id or @username.")
    limit: int = Field(default=50, ge=1, le=500)
    offset_id: int = Field(default=0, ge=0, description="Start before this message id (0 = newest).")
    min_id: int = Field(default=0, ge=0, description="Only messages with id greater than this.")
    reverse: bool = Field(default=False, description="Oldest first.")


class MessagesSearchInput(_In):
    chat: Optional[str] = Field(default=None, description="Chat id/@username; omit for a global search.")
    query: str = Field(min_length=1)
    limit: int = Field(default=50, ge=1, le=500)


class MessagesExportInput(_In):
    chat: str
    name: Optional[str] = Field(
        default=None, description="Output base name (no path). Always written under mcp/telegram/.exports/."
    )
    markdown: bool = Field(default=False, description="Also write a .md rendering.")


class MediaDownloadInput(_In):
    chat: str
    message_ids: list[int] = Field(min_length=1, max_length=20)
    out_dir: str = Field(description="Destination directory (created if missing).")
    confirm: bool = False


class MessagesSendInput(_In):
    chat: str
    text: str = Field(min_length=1, max_length=4096)
    confirm: bool = False
