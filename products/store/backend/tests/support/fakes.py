"""In-memory, STATEFUL doubles for the store's Protocols (tests only).

Stateful on purpose: idempotency, counters, versioning and claims are the
behaviours under test, and a stateless mock would let them pass vacuously.
"""
from __future__ import annotations

import copy
import itertools
from datetime import datetime, timezone
from typing import Any, Optional

from noctusai_lib.integrations.email import OutgoingEmail, SentEmail

from app.stores.protocols import VersionConflict


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FakeSettingsStore:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def current(self) -> Optional[dict[str, Any]]:
        return copy.deepcopy(max(self.rows, key=lambda r: r["version"])) if self.rows else None

    def append(self, *, version: int, data: dict[str, Any], created_by: Optional[str]) -> dict[str, Any]:
        if any(r["version"] == version for r in self.rows):
            raise VersionConflict(f"version {version} already exists")
        row = {"version": version, "data": copy.deepcopy(data), "created_by": created_by, "created_at": _now()}
        self.rows.append(row)
        return copy.deepcopy(row)


class FakePedidoStore:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self._seq = itertools.count(1)

    def create(self, row: dict[str, Any]) -> dict[str, Any]:
        n = next(self._seq)
        full = {
            "id": f"00000000-0000-0000-0000-{n:012d}",
            "gateway_charge_id": None,
            "checkout_url": None,
            "pago_em": None,
            "email_enviado_em": None,
            "email_erro": None,
            "downloads": 0,
            "created_at": _now(),
            "updated_at": _now(),
            **row,
        }
        self.rows[full["id"]] = full
        return copy.deepcopy(full)

    def _find(self, key: str, value: str) -> Optional[dict[str, Any]]:
        for row in self.rows.values():
            if row.get(key) == value:
                return copy.deepcopy(row)
        return None

    def get_by_token(self, token: str) -> Optional[dict[str, Any]]:
        return self._find("token", token)

    def get_by_id(self, pedido_id: str) -> Optional[dict[str, Any]]:
        row = self.rows.get(pedido_id)
        return copy.deepcopy(row) if row else None

    def get_by_charge_id(self, charge_id: str) -> Optional[dict[str, Any]]:
        return self._find("gateway_charge_id", charge_id)

    def update(self, pedido_id: str, fields: dict[str, Any]) -> Optional[dict[str, Any]]:
        row = self.rows.get(pedido_id)
        if row is None:
            return None
        row.update(fields)
        row["updated_at"] = _now()
        return copy.deepcopy(row)

    def list(self, *, status: Optional[str], limit: int, offset: int) -> list[dict[str, Any]]:
        rows = [r for r in self.rows.values() if status is None or r["status"] == status]
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return copy.deepcopy(rows[offset : offset + limit])

    def claim_email(self, pedido_id: str, *, at_iso: str) -> bool:
        row = self.rows.get(pedido_id)
        if row is None or row["email_enviado_em"] is not None:
            return False
        row["email_enviado_em"] = at_iso
        row["email_erro"] = None
        return True

    def release_email(self, pedido_id: str, *, error: Optional[str]) -> None:
        row = self.rows[pedido_id]
        row["email_enviado_em"] = None
        row["email_erro"] = error

    def take_download(self, token: str, *, max_downloads: int) -> bool:
        for row in self.rows.values():
            if row["token"] == token:
                if row["downloads"] >= max_downloads:
                    return False
                row["downloads"] += 1
                return True
        return False


class FailingEmailSender:
    """An `EmailSender` whose transport is down (external-IO double)."""

    def __init__(self, message: str = "smtp down") -> None:
        self.message = message
        self.attempts = 0

    async def send(self, email: OutgoingEmail) -> SentEmail:
        self.attempts += 1
        raise ConnectionError(self.message)
