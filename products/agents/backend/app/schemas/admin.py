"""Wire shapes for the platform-admin Credenciais + Configurações do agente
pages. No model here has a field that can carry a secret value: status
exposes ``prefix`` / ``fingerprint`` only, and the one write-only input
(``CredentialValueIn.value``) is never echoed back."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RingKeyOut(BaseModel):
    fingerprint: str
    active_from: datetime
    retire_at: datetime | None
    signing: bool
    state: Literal["staged", "active", "retiring", "retired"]


class CredentialOut(BaseModel):
    name: str
    label: str
    kind: Literal["product_token", "api_key", "key_ring", "config"]
    env_var: str
    configured: bool
    source: Literal["db", "env"] | None
    prefix: str | None = None
    fingerprint: str | None = None
    value: str | None = None  # non-secret config only (julia_agent_id)
    expires_at: datetime | None = None
    days_left: int | None = None
    last_used_at: datetime | None = None
    revoked: bool = False
    scopes: list[str] = Field(default_factory=list)
    renewable: bool
    probeable: bool
    writable: bool
    ring: list[RingKeyOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    severity: Literal["info", "warning", "critical"]


class CredentialListOut(BaseModel):
    items: list[CredentialOut]
    total: int
    alerts: int  # credentials currently at warning/critical severity


class CredentialValueIn(_Strict):
    value: str = Field(min_length=1, max_length=4096)


class ProbeOut(BaseModel):
    name: str
    status: Literal["ok", "unauthorized", "forbidden", "unreachable", "error"]
    ok: bool
    http_status: int | None
    detail: str
    checked_at: datetime


class RenewOut(BaseModel):
    credential: CredentialOut
    warnings: list[str] = Field(default_factory=list)


class AgentSettingOut(BaseModel):
    key: str
    value: Any
    default: Any
    source: Literal["db", "env"]
    editable: bool
    min: int | None = None
    max: int | None = None


class AgentSettingsOut(BaseModel):
    items: list[AgentSettingOut]


class AgentSettingsPatch(_Strict):
    """Omitted key ⇒ unchanged; explicit ``null`` ⇒ back to the env default."""

    approval_timeout_seconds: int | None = None
    max_turns: int | None = None
    messages_rate_limit: str | None = None
