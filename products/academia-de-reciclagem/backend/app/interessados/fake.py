"""`FakeInteressadosStore` -- in-memory `InteressadosStore`, same invariants
as `PgInteressadosStore`. Single-threaded, no locking -- a test double, not
a concurrency model (mirrors `app/knowledge/fake.py`'s own note)."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4


class FakeInteressadosStore:
    def __init__(self) -> None:
        self.rows: dict[UUID, dict] = {}

    async def upsert(
        self,
        *,
        nome: str,
        whatsapp: str,
        email: str,
        origem: str | None,
        consentimento_versao: str,
    ) -> None:
        email_key = email.strip().lower()
        now = datetime.now(timezone.utc)
        existing = next(
            (row for row in self.rows.values() if row["email"] == email_key), None
        )
        if existing is not None:
            existing.update(
                nome=nome,
                whatsapp=whatsapp,
                origem=origem,
                consentimento_versao=consentimento_versao,
                consentimento_em=now,
                atualizado_em=now,
            )
            return
        row_id = uuid4()
        self.rows[row_id] = {
            "id": row_id,
            "nome": nome,
            "whatsapp": whatsapp,
            "email": email_key,
            "origem": origem,
            "consentimento_versao": consentimento_versao,
            "consentimento_em": now,
            "criado_em": now,
            "atualizado_em": now,
        }

    async def list(self, *, limit: int, offset: int) -> tuple[list[dict], int]:
        rows = sorted(self.rows.values(), key=lambda r: r["criado_em"], reverse=True)
        total = len(rows)
        return [dict(r) for r in rows[offset : offset + limit]], total

    async def delete(self, interessado_id: UUID) -> bool:
        return self.rows.pop(interessado_id, None) is not None


__all__ = ["FakeInteressadosStore"]
