"""Store Protocols (the Fake in tests/support/fakes.py satisfies the same)."""
from __future__ import annotations

from typing import Any, Optional, Protocol


class VersionConflict(Exception):
    """The settings version a writer expected is no longer the current one
    (or two writers raced for the same new version)."""


class SettingsStore(Protocol):
    def current(self) -> Optional[dict[str, Any]]:
        """Latest `{version, data, created_by, created_at}` row, or None."""
        ...

    def append(self, *, version: int, data: dict[str, Any], created_by: Optional[str]) -> dict[str, Any]:
        """Insert version `version`. Raises `VersionConflict` when it already exists."""
        ...


class PedidoStore(Protocol):
    def create(self, row: dict[str, Any]) -> dict[str, Any]: ...

    def get_by_token(self, token: str) -> Optional[dict[str, Any]]: ...

    def get_by_id(self, pedido_id: str) -> Optional[dict[str, Any]]: ...

    def get_by_charge_id(self, charge_id: str) -> Optional[dict[str, Any]]: ...

    def update(self, pedido_id: str, fields: dict[str, Any]) -> Optional[dict[str, Any]]: ...

    def list(self, *, status: Optional[str], limit: int, offset: int) -> list[dict[str, Any]]: ...

    def claim_email(self, pedido_id: str, *, at_iso: str) -> bool:
        """Atomically set `email_enviado_em` iff it is still NULL. True for the
        single caller that won; every concurrent/replayed caller gets False."""
        ...

    def release_email(self, pedido_id: str, *, error: Optional[str]) -> None:
        """Undo a claim whose send failed: clear `email_enviado_em` and record `error`."""
        ...

    def take_download(self, token: str, *, max_downloads: int) -> bool:
        """Atomically `downloads += 1` iff `downloads < max_downloads`. True when taken."""
        ...
