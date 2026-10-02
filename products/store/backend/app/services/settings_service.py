"""Landing settings — the versioned ledger the public page and the admin editor share.

Contract §2. `DEFAULT_SETTINGS` is the ONE place the defaults live; version 1
is seeded by `migrations/007_store_core.sql` from the same values (a test
parses the migration literal and compares). When the ledger is empty the
service reports `(0, DEFAULT_SETTINGS)` — never `{}`.

`anchor_total_cents` is DERIVED (Σ anchor_cents), never stored.
`author.has_photo` is DERIVED from storage at read time (the photo upload
therefore never bumps the settings version and never turns an admin's open
editor into a 409): the stored flag is only the fallback when storage is
unreachable.
"""
from __future__ import annotations

import copy
import logging
from typing import Any, Optional

from app.schemas.store import LandingSettings
from app.services.assets import AssetService
from app.stores.protocols import SettingsStore, VersionConflict

logger = logging.getLogger(__name__)

PHOTO_PUBLIC_PATH = "/api/public/autor/foto"

DEFAULT_SETTINGS: dict[str, Any] = {
    "product_name": "Contrato Blindado de Compra e Venda",
    "price_cents": 4700,
    "items": [
        {"label": "Contrato À Vista (Word + PDF)", "anchor_cents": 9700},
        {"label": "Contrato Financiado (Word + PDF)", "anchor_cents": 9700},
        {"label": "Contrato Parcelado com confissão de dívida", "anchor_cents": 12700},
        {"label": "Lista de 14 certidões e documentos", "anchor_cents": 4700},
    ],
    "guarantee_days": 7,
    "author": {
        "name": "Gilson",
        "role": "corretor de imóveis",
        "bio": (
            "O Gilson acompanha negociações de compra e venda do sinal à entrega das chaves. "
            "Este modelo nasceu dos contratos assinados nessas negociações, reunidos em um só "
            "texto e transformados em um modelo genérico que qualquer pessoa pode preencher."
        ),
        "has_photo": False,
    },
    "checkout_enabled": True,
}


class SettingsVersionConflict(Exception):
    """`expected_version` is not the current version (HTTP 409)."""


class SettingsService:
    def __init__(self, store: SettingsStore, assets: AssetService) -> None:
        self._store = store
        self._assets = assets

    # ── reads ────────────────────────────────────────────────────────────
    def current(self) -> tuple[int, dict[str, Any]]:
        """`(version, data)` straight from the ledger (no photo derivation)."""
        row = self._store.current()
        if row is None:
            return 0, copy.deepcopy(DEFAULT_SETTINGS)
        return int(row["version"]), dict(row["data"])

    async def _has_photo(self, stored: bool) -> bool:
        try:
            return await self._assets.photo_key() is not None
        except Exception:  # noqa: BLE001 - the page must render without the photo
            logger.warning("settings: could not check the author photo in storage; using stored flag", exc_info=True)
            return stored

    async def admin_view(self) -> dict[str, Any]:
        version, data = self.current()
        data = copy.deepcopy(data)
        author = dict(data.get("author") or {})
        author["has_photo"] = await self._has_photo(bool(author.get("has_photo")))
        data["author"] = author
        return {"version": version, "data": data}

    async def public_view(self) -> dict[str, Any]:
        _version, data = self.current()
        out = copy.deepcopy(data)
        author = dict(out.get("author") or {})
        has_photo = await self._has_photo(bool(author.get("has_photo")))
        author["has_photo"] = has_photo
        author["photo_url"] = PHOTO_PUBLIC_PATH if has_photo else None
        out["author"] = author
        out["anchor_total_cents"] = sum(int(i["anchor_cents"]) for i in out.get("items", []))
        return out

    # ── write ────────────────────────────────────────────────────────────
    def update(self, new_data: LandingSettings, expected_version: int, created_by: Optional[str]) -> int:
        """Append version+1. `SettingsVersionConflict` when `expected_version`
        is stale — read fresh from the store, a write never races a cached read."""
        current_version, current_data = self.current()
        if expected_version != current_version:
            raise SettingsVersionConflict(f"expected_version={expected_version} != current={current_version}")
        payload = new_data.model_dump(mode="json")
        # has_photo is server-owned (derived from storage) — keep what the
        # ledger already holds rather than trusting the client's copy.
        payload["author"]["has_photo"] = bool((current_data.get("author") or {}).get("has_photo", False))
        try:
            row = self._store.append(version=current_version + 1, data=payload, created_by=created_by)
        except VersionConflict as exc:
            raise SettingsVersionConflict(str(exc)) from exc
        return int(row["version"])


__all__ = ["DEFAULT_SETTINGS", "PHOTO_PUBLIC_PATH", "SettingsService", "SettingsVersionConflict"]
