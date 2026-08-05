"""Omie MCP settings — multi-ENVIRONMENT credential profiles.

Omie has no sandbox/staging tenant: an "environment" in Omie is a
**company** (`empresa`), and every company issues its OWN
`app_key` / `app_secret` pair from its own app registration. An agency or
a multi-company operator therefore juggles N credential pairs, and the
single most dangerous mistake is issuing a write against the wrong one.

So this connector is environment-first by construction: **every** tool
takes an `environment` argument, an environment can be pinned
`readonly`, and no tool ever resolves credentials implicitly beyond the
declared default.

Resolution (first match wins per environment name):

1. `OMIE_ENVIRONMENTS` — a JSON object, the canonical multi-tenant form::

       {"acme-prod":  {"app_key": "...", "app_secret": "...",
                       "label": "Acme Ltda", "cnpj": "12.345.678/0001-90",
                       "readonly": true},
        "acme-test":  {"app_key": "...", "app_secret": "..."}}

2. `OMIE_ENV__<NAME>__APP_KEY` / `__APP_SECRET` / `__LABEL` / `__CNPJ` /
   `__READONLY` — flat per-environment vars, for secret stores that can't
   hold JSON. `<NAME>` is upper-snake; it maps to a kebab environment
   name (`OMIE_ENV__ACME_PROD__APP_KEY` → `acme-prod`).

3. `OMIE_APP_KEY` + `OMIE_APP_SECRET` — the single-company shorthand,
   registered under the name `default`.

`OMIE_DEFAULT_ENVIRONMENT` names the environment used when a tool call
omits `environment` (falls back to `default`, else the sole configured
environment, else unresolved → typed error at call time).

Env wins over the co-located `.env` (the `_kit.settings` rule). Secrets
are NEVER returned by a tool — `OmieEnvironment.redacted()` is the only
shape that crosses the MCP boundary.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from _kit.settings import ConnectorSettings, _load_dotenv

_DOTENV_DIR = Path(__file__).resolve().parent

# Omie's own documented ceilings (ajuda.omie.com.br § Limites de Consumo):
#   960 req/min per IP · 240 req/min per IP+app_key+method
#   4 concurrent per IP+app_key+method · 100 records/page max
DEFAULT_TIMEOUT_SECONDS = 45.0


def _truthy(v: Optional[str]) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on", "sim"}


@dataclass(frozen=True)
class OmieEnvironment:
    """One Omie company's credential profile.

    Frozen: a tool handler cannot mutate shared credential state.
    """

    name: str
    app_key: str
    app_secret: str
    label: Optional[str] = None
    cnpj: Optional[str] = None
    readonly: bool = False
    source: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.app_key) and bool(self.app_secret)

    def redacted(self) -> dict:
        """The ONLY shape that crosses the MCP boundary — never the secret.

        `app_key` is shown as last-4 so an operator can tell two
        environments apart in a tool result without the value leaking.
        """
        return {
            "name": self.name,
            "label": self.label,
            "cnpj": self.cnpj,
            "readonly": self.readonly,
            "app_key_suffix": ("…" + self.app_key[-4:]) if self.app_key else None,
            "app_secret_set": bool(self.app_secret),
            "configured": self.configured,
            "source": self.source,
        }


@dataclass(frozen=True)
class OmieSettings(ConnectorSettings):
    """Process-wide Omie config: the environment registry + transport knobs."""

    base_url: str = "https://app.omie.com.br/api/v1"
    environments: tuple[OmieEnvironment, ...] = ()
    default_environment: Optional[str] = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    #: "full" (default) advertises the curated per-resource CRUD tools too;
    #: "core" advertises only environments + catalog + call + diagnostics.
    #: Capability is identical either way — `omie.call.invoke` reaches all 461
    #: methods — so this trades host context budget, never reach.
    tool_profile: str = "full"

    @property
    def configured(self) -> bool:
        return any(e.configured for e in self.environments)

    def names(self) -> list[str]:
        return [e.name for e in self.environments]

    def get(self, name: Optional[str]) -> OmieEnvironment:
        """Resolve an environment by name, or the default when `name` is None.

        Raises `OmieConfigError` (typed, 424) rather than guessing — an
        implicit fallback to "whatever is configured" is exactly how a
        write lands on the wrong company.
        """
        from .errors import OmieConfigError  # local: avoid import cycle

        if not self.environments:
            raise OmieConfigError(
                "No Omie environment is configured. Set OMIE_ENVIRONMENTS (JSON), "
                "or OMIE_ENV__<NAME>__APP_KEY/__APP_SECRET, or OMIE_APP_KEY + "
                f"OMIE_APP_SECRET — in the process env or {_DOTENV_DIR / '.env'}."
            )
        if name:
            for e in self.environments:
                if e.name == name:
                    return e
            raise OmieConfigError(
                f"Unknown Omie environment {name!r}. Configured: {self.names()}."
            )
        if self.default_environment:
            for e in self.environments:
                if e.name == self.default_environment:
                    return e
            raise OmieConfigError(
                f"OMIE_DEFAULT_ENVIRONMENT={self.default_environment!r} is not a "
                f"configured environment. Configured: {self.names()}."
            )
        for e in self.environments:
            if e.name == "default":
                return e
        if len(self.environments) == 1:
            return self.environments[0]
        raise OmieConfigError(
            f"{len(self.environments)} Omie environments are configured "
            f"({self.names()}) and none is named 'default'. Pass `environment` "
            "explicitly, or set OMIE_DEFAULT_ENVIRONMENT."
        )


def _from_json_blob(raw: str) -> list[OmieEnvironment]:
    """Parse `OMIE_ENVIRONMENTS`. A malformed blob RAISES — a silently
    ignored credential map would present as 'no environments configured'
    and send the operator hunting the wrong problem."""
    from .errors import OmieConfigError

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise OmieConfigError(f"OMIE_ENVIRONMENTS is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise OmieConfigError(
            "OMIE_ENVIRONMENTS must be a JSON object mapping "
            "environment-name → {app_key, app_secret, ...}."
        )
    out = []
    for name, cfg in data.items():
        if not isinstance(cfg, dict):
            raise OmieConfigError(
                f"OMIE_ENVIRONMENTS[{name!r}] must be an object, got {type(cfg).__name__}."
            )
        out.append(
            OmieEnvironment(
                name=str(name),
                app_key=str(cfg.get("app_key") or ""),
                app_secret=str(cfg.get("app_secret") or ""),
                label=cfg.get("label"),
                cnpj=cfg.get("cnpj"),
                readonly=bool(cfg.get("readonly", False)),
                source="OMIE_ENVIRONMENTS",
            )
        )
    return out


def _from_flat_vars(merged: dict) -> list[OmieEnvironment]:
    """Collect `OMIE_ENV__<NAME>__APP_KEY` families into environments."""
    prefix, suffix = "OMIE_ENV__", "__APP_KEY"
    names = [
        k[len(prefix): -len(suffix)]
        for k in merged
        if k.startswith(prefix) and k.endswith(suffix)
    ]
    out = []
    for raw_name in sorted(names):
        base = f"{prefix}{raw_name}__"
        out.append(
            OmieEnvironment(
                name=raw_name.lower().replace("_", "-"),
                app_key=merged.get(f"{base}APP_KEY", ""),
                app_secret=merged.get(f"{base}APP_SECRET", ""),
                label=merged.get(f"{base}LABEL"),
                cnpj=merged.get(f"{base}CNPJ"),
                readonly=_truthy(merged.get(f"{base}READONLY")),
                source=f"{base}*",
            )
        )
    return out


@lru_cache(maxsize=1)
def get_settings() -> OmieSettings:
    """Process-cached settings. `get_settings.cache_clear()` re-reads."""
    dot = _load_dotenv(_DOTENV_DIR / ".env")
    # Env wins over the dotfile, per the _kit resolution rule.
    merged = {**dot, **{k: v for k, v in os.environ.items() if k.startswith("OMIE_")}}

    envs: list[OmieEnvironment] = []
    seen: set[str] = set()
    for candidate in (
        _from_json_blob(merged["OMIE_ENVIRONMENTS"]) if merged.get("OMIE_ENVIRONMENTS") else [],
        _from_flat_vars(merged),
        (
            [
                OmieEnvironment(
                    name="default",
                    app_key=merged.get("OMIE_APP_KEY", ""),
                    app_secret=merged.get("OMIE_APP_SECRET", ""),
                    label=merged.get("OMIE_LABEL"),
                    cnpj=merged.get("OMIE_CNPJ"),
                    readonly=_truthy(merged.get("OMIE_READONLY")),
                    source="OMIE_APP_KEY/OMIE_APP_SECRET",
                )
            ]
            if merged.get("OMIE_APP_KEY")
            else []
        ),
    ):
        for e in candidate:
            if e.name not in seen:  # earlier source wins; never silently overwrite
                seen.add(e.name)
                envs.append(e)

    timeout = merged.get("OMIE_TIMEOUT_SECONDS")
    profile = (merged.get("OMIE_TOOL_PROFILE") or "full").strip().lower()
    if profile not in {"full", "core"}:
        from .errors import OmieConfigError

        raise OmieConfigError(
            f"OMIE_TOOL_PROFILE={profile!r} is not valid — use 'full' or 'core'."
        )
    return OmieSettings(
        base_url=(merged.get("OMIE_BASE_URL") or "https://app.omie.com.br/api/v1").rstrip("/"),
        environments=tuple(envs),
        default_environment=merged.get("OMIE_DEFAULT_ENVIRONMENT"),
        timeout_seconds=float(timeout) if timeout else DEFAULT_TIMEOUT_SECONDS,
        tool_profile=profile,
    )


__all__ = ["OmieEnvironment", "OmieSettings", "get_settings", "DEFAULT_TIMEOUT_SECONDS"]
