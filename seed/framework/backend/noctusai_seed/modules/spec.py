"""`ModuleSpec` / `PageSpec` -- a declared bundle (organs + pages + permissions + enablement key) a market product mounts.

A module is the BE half of one sidebar group (`key` is a `ModuleGroupKey`, the FE `defineModule` shares it). The
page-key contract between the two halves is `module_manifest(specs)`: the JSON both sides can generate and compare
(`seed/lib/backend/tests/fixtures/module_manifest.json` pins the cross-language parity; a host commits its own).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from fastapi import APIRouter

from noctusai_lib.domain.module_enablement.keys import (
    MODULE_GROUP_KEYS,
    MODULE_PERMISSION_LEVELS,
    PAGE_STATUS_DEFAULT,
    PAGE_STATUSES,
    is_valid_enablement_key,
    is_valid_page_key,
)

__all__ = ["MANIFEST_VERSION", "ModuleSpec", "PageSpec", "module_manifest", "validate_modules"]

MANIFEST_VERSION = 1


@dataclass(frozen=True)
class PageSpec:
    """One page of a module. `key` is the `status_pagina.nome_pagina` row and the FE `pageKey`."""

    key: str
    path: str
    label: str
    #: default `status_pagina.status` when the page is first seeded.
    status: str = PAGE_STATUS_DEFAULT

    def __post_init__(self) -> None:
        if not is_valid_page_key(self.key):
            raise ValueError(f"invalid page key {self.key!r}")
        if not self.path.startswith("/"):
            raise ValueError(f"page {self.key!r}: path must start with '/' (got {self.path!r})")
        if not self.label.strip():
            raise ValueError(f"page {self.key!r}: label is required")
        if self.status not in PAGE_STATUSES:
            raise ValueError(f"page {self.key!r}: status {self.status!r} not in {PAGE_STATUSES}")


@dataclass(frozen=True)
class ModuleSpec:
    """`organs` are `noctusai_seed.organs.MountedOrgan`s, mounted through `mount_organs`; their routers sit behind the
    per-org enablement guard. `public_routers` (signed / public link routes, each with its own declared tier) are
    mounted WITHOUT the guard: no caller identity exists there to resolve an org from -- keep them to what a
    disabled module may still serve (e.g. an already-sent quote link)."""

    key: str
    organs: tuple[Any, ...] = ()
    pages: tuple[PageSpec, ...] = ()
    #: `permission key -> lowest org role` (`member` | `admin`); exposed to the FE through `GET /api/modules`.
    permissions: Mapping[str, str] = field(default_factory=dict)
    #: per-org enablement key; defaults to `key` (the `public.org_modules.module_key` the platform admin toggles).
    license_key: Optional[str] = None
    public_routers: tuple[APIRouter, ...] = ()

    def __post_init__(self) -> None:
        if self.key not in MODULE_GROUP_KEYS:
            raise ValueError(f"module key {self.key!r} is not a canonical module-group key {MODULE_GROUP_KEYS}")
        object.__setattr__(self, "organs", tuple(self.organs))
        object.__setattr__(self, "pages", tuple(self.pages))
        object.__setattr__(self, "public_routers", tuple(self.public_routers))
        keys = [p.key for p in self.pages]
        if len(set(keys)) != len(keys):
            dupes = sorted({k for k in keys if keys.count(k) > 1})
            raise ValueError(f"module {self.key!r}: duplicate page keys {dupes}")
        paths = [p.path for p in self.pages]
        if len(set(paths)) != len(paths):
            raise ValueError(f"module {self.key!r}: duplicate page paths")
        for perm, level in self.permissions.items():
            if level not in MODULE_PERMISSION_LEVELS:
                raise ValueError(f"module {self.key!r}: permission {perm!r} level {level!r} not in {MODULE_PERMISSION_LEVELS}")
        if self.license_key is not None and not is_valid_enablement_key(self.license_key):
            raise ValueError(f"module {self.key!r}: invalid license_key {self.license_key!r}")

    @property
    def enablement_key(self) -> str:
        return self.license_key or self.key

    @property
    def page_keys(self) -> tuple[str, ...]:
        return tuple(p.key for p in self.pages)


def validate_modules(specs: Sequence[ModuleSpec]) -> None:
    """Cross-module rules: unique module keys, unique enablement keys, and a page lives in exactly ONE module."""
    seen_keys: set[str] = set()
    seen_enablement: dict[str, str] = {}
    seen_pages: dict[str, str] = {}
    for spec in specs:
        if spec.key in seen_keys:
            raise ValueError(f"module {spec.key!r} declared twice")
        seen_keys.add(spec.key)
        other = seen_enablement.setdefault(spec.enablement_key, spec.key)
        if other != spec.key:
            raise ValueError(f"modules {other!r} and {spec.key!r} share enablement key {spec.enablement_key!r}")
        for page in spec.pages:
            owner = seen_pages.setdefault(page.key, spec.key)
            if owner != spec.key:
                raise ValueError(f"page {page.key!r} is declared by modules {owner!r} and {spec.key!r}; a page lives in one module")


def module_manifest(specs: Sequence[ModuleSpec]) -> dict[str, Any]:
    """The page-key contract: deterministic (modules and pages sorted by key). The FE `moduleManifest` emits the same shape."""
    validate_modules(specs)
    return {
        "version": MANIFEST_VERSION,
        "modules": [
            {
                "key": s.key,
                "enablement_key": s.enablement_key,
                "pages": [
                    {"key": p.key, "path": p.path, "label": p.label, "status": p.status}
                    for p in sorted(s.pages, key=lambda p: p.key)
                ],
            }
            for s in sorted(specs, key=lambda s: s.key)
        ],
    }
