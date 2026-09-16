"""Effective Julia runtime specs: an admin override (DB) wins, the env
setting is the default (Configurações do agente page).

Editable: ``approval_timeout_seconds`` (contract §E.2 "Timeout"),
``max_turns`` (§E.5), ``messages_rate_limit`` (§E rate limit).
Read-only: ``julia_cli_slots`` — structural (one uid + one tmpfs mount per
slot in the image and compose, §E.11), so changing it needs a redeploy.

Every consumer reads at use time through the process singleton, whose
short cache is invalidated by this process's own writes — so a change is
live without a redeploy (other workers within ``credential_cache_ttl_seconds``).
"""
from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal
from uuid import UUID

import yaml

from app.stores.runtime_settings import RuntimeSettingsStore

logger = logging.getLogger(__name__)

__all__ = [
    "EDITABLE_KEYS",
    "RuntimeSettingsError",
    "RuntimeSettingsService",
    "SettingView",
    "get_runtime_settings_service",
    "install_runtime_settings_service",
    "reset_for_testing",
]

EDITABLE_KEYS = ("approval_timeout_seconds", "max_turns", "messages_rate_limit")

_RATE_LIMIT_RE = re.compile(r"^[1-9]\d{0,4}/(second|minute|hour|day)$")
_SPEC_PATH = Path(__file__).resolve().parent.parent / "agents" / "julia" / "spec.yaml"
_MAX_TURNS_LIMIT = 200
_MIN_APPROVAL_TIMEOUT = 30


class RuntimeSettingsError(ValueError):
    def __init__(self, field: str, detail: str) -> None:
        super().__init__(detail)
        self.field = field
        self.detail = detail


@dataclass(frozen=True)
class SettingView:
    key: str
    value: Any
    default: Any
    source: Literal["db", "env"]
    editable: bool
    min: int | None = None
    max: int | None = None


def _spec_max_turns() -> int:
    data = yaml.safe_load(_SPEC_PATH.read_text(encoding="utf-8")) or {}
    return int(data.get("max_turns", 40))


class RuntimeSettingsService:
    def __init__(
        self,
        store: RuntimeSettingsStore,
        settings: Any,
        *,
        ttl_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._store = store
        self._settings = settings
        self._ttl = ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._cached: tuple[float, dict[str, Any]] | None = None

    # ── defaults (env) ─────────────────────────────────────────────────

    def _defaults(self) -> dict[str, Any]:
        configured_turns = getattr(self._settings, "julia_max_turns", None)
        return {
            "approval_timeout_seconds": int(getattr(self._settings, "approval_timeout_seconds", 300)),
            "max_turns": int(configured_turns) if configured_turns else _spec_max_turns(),
            "messages_rate_limit": str(getattr(self._settings, "messages_rate_limit", "20/minute")),
        }

    def _max_approval_timeout(self) -> int:
        # An approval wait happens INSIDE a turn; it must end before the
        # turn deadline or a pending approval is cut off by the timeout.
        return int(getattr(self._settings, "turn_timeout_seconds", 600)) - 30

    def _overrides(self) -> dict[str, Any]:
        now = self._clock()
        with self._lock:
            cached = self._cached
        if cached is not None and now - cached[0] < self._ttl:
            return cached[1]
        try:
            rows = self._store.get_all()
        except Exception:
            # Loud, and the env default still applies: a DB blip must not
            # stop Julia from answering.
            logger.exception("agents.runtime_settings_read_failed — using env defaults")
            rows = {}
        with self._lock:
            self._cached = (now, rows)
        return rows

    def _effective(self, key: str) -> Any:
        override = self._overrides().get(key)
        if override is not None:
            try:
                return self._validate(key, override)
            except RuntimeSettingsError:
                logger.error("agents.runtime_setting_invalid_in_db key=%s — using env default", key)
        return self._defaults()[key]

    # ── typed accessors (consumers) ────────────────────────────────────

    def approval_timeout_seconds(self) -> int:
        return int(self._effective("approval_timeout_seconds"))

    def max_turns(self) -> int:
        return int(self._effective("max_turns"))

    def messages_rate_limit(self) -> str:
        return str(self._effective("messages_rate_limit"))

    # ── page ───────────────────────────────────────────────────────────

    def view(self) -> list[SettingView]:
        defaults = self._defaults()
        overrides = self._overrides()
        bounds = {
            "approval_timeout_seconds": (_MIN_APPROVAL_TIMEOUT, self._max_approval_timeout()),
            "max_turns": (1, _MAX_TURNS_LIMIT),
            "messages_rate_limit": (None, None),
        }
        views = [
            SettingView(
                key=key,
                value=self._effective(key),
                default=defaults[key],
                source="db" if overrides.get(key) is not None else "env",
                editable=True,
                min=bounds[key][0],
                max=bounds[key][1],
            )
            for key in EDITABLE_KEYS
        ]
        slots = int(getattr(self._settings, "julia_cli_slots", 3))
        views.append(SettingView(key="julia_cli_slots", value=slots, default=slots, source="env", editable=False))
        return views

    def _validate(self, key: str, value: Any) -> Any:
        if key == "messages_rate_limit":
            if not isinstance(value, str) or not _RATE_LIMIT_RE.match(value.strip()):
                raise RuntimeSettingsError(key, "Use o formato N/second|minute|hour|day, ex.: 20/minute.")
            return value.strip()
        if isinstance(value, bool) or not isinstance(value, int):
            raise RuntimeSettingsError(key, "Deve ser um número inteiro.")
        if key == "approval_timeout_seconds":
            high = self._max_approval_timeout()
            if not _MIN_APPROVAL_TIMEOUT <= value <= high:
                raise RuntimeSettingsError(
                    key, f"Entre {_MIN_APPROVAL_TIMEOUT} e {high} segundos (menor que o limite do turno)."
                )
            return value
        if key == "max_turns":
            if not 1 <= value <= _MAX_TURNS_LIMIT:
                raise RuntimeSettingsError(key, f"Entre 1 e {_MAX_TURNS_LIMIT}.")
            return value
        raise RuntimeSettingsError(key, "Configuração desconhecida ou somente leitura.")

    def update(self, patch: dict[str, Any], *, updated_by: UUID | None) -> list[SettingView]:
        """``None`` for a key resets it to the env default. All-or-nothing:
        every value is validated before the first write."""
        validated: dict[str, Any] = {}
        for key, value in patch.items():
            if key not in EDITABLE_KEYS:
                raise RuntimeSettingsError(key, "Configuração desconhecida ou somente leitura.")
            validated[key] = None if value is None else self._validate(key, value)
        for key, value in validated.items():
            if value is None:
                self._store.delete(key)
            else:
                self._store.put(key, value, updated_by=updated_by)
            logger.info("agents.runtime_setting_changed key=%s reset=%s", key, value is None)
        with self._lock:
            self._cached = None
        return self.view()


_singleton: RuntimeSettingsService | None = None


def get_runtime_settings_service(settings: Any) -> RuntimeSettingsService:
    """Process singleton (its cache must be shared by every consumer)."""
    global _singleton
    if _singleton is None:
        from app.stores.runtime_settings import get_runtime_settings_store

        _singleton = RuntimeSettingsService(
            get_runtime_settings_store(settings),
            settings,
            ttl_seconds=float(getattr(settings, "credential_cache_ttl_seconds", 30) or 0),
        )
    return _singleton


def install_runtime_settings_service(service: RuntimeSettingsService) -> None:
    """Explicit DI seam for the process singleton (tests install one over a
    Fake store — consumers outside FastAPI's DI, like the rate-limit
    callable, read the singleton directly)."""
    global _singleton
    _singleton = service


def reset_for_testing() -> None:
    global _singleton
    _singleton = None
