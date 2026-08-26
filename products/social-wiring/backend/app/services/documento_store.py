"""One document store, configured per surface. The N=3 formalization.

WHAT KEPT BEING RE-ANSWERED
---------------------------
Three tables now hold uploaded files — `cliente_documentos` (057),
`imovel_documentos` (075) and `atendimento_documentos` (078) — and each needs
the same six steps: validate the type/mime/size, put the bytes in storage
under an org-first key, insert a row, list the live ones, mint a short-TTL
signed URL, soft-delete with a recorded reason.

🔴 WHY THIS IS WORTH ONE HOME AND THE LGPD POSTURE IS NOT
----------------------------------------------------------
The three surfaces genuinely DIFFER on LGPD, and that difference is load-
bearing: a matrícula is a public registry document about a property, an RG is
personal data about a natural person, an imposto de renda is their income.
Flattening that into one policy would be wrong.

But the difference is entirely "does an access get logged, and is there a
retention clock" — two switches. Everything under them is identical, and the
identical part contains the bits that are silently wrong when copied:

- the storage key MUST begin with the literal `org_id` (migration 057's
  object-RLS policies match on that first path segment — a key that starts
  with anything else is readable across orgs);
- a soft-deleted row must be excluded from every list (a copy that forgets is
  a document the user believes they deleted, still on screen);
- the signed-URL TTL is short and minted per request, never stored.

A copy that gets those wrong looks and tests exactly like one that does not.

WHAT THIS DOES **NOT** OWN
--------------------------
Per-surface behaviour stays with the surface: extraction queuing
(`imovel_hub`), the `cliente_documento_tipos` allow-list table, retention
sweeps, and every "what does this document MEAN" decision.

NOC-REMEDIATE[dry-documento-store]: `card_hub.documentos_service` predates
this and is NOT yet migrated onto it. It is the LGPD-complete original and its
retention sweep + tipos table are wired into a scheduler and a data table, so
moving it is its own change with its own test surface — not a rider on this
one. Named destination: the next change that touches that file.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.services import table_reads

#: Short TTL, minted per request, never stored.
SIGNED_URL_TTL_SECONDS = 300


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today() -> "datetime.date":
    return datetime.now(timezone.utc).date()


def format_bytes_human(n: int) -> str:
    """Human-readable byte count for a user-facing limit message.

    Never integer-divides to a misleading "0MB" — the legacy 800 KB cap's
    `n // (1024*1024)` evaluated to exactly 0, so a user over the limit was
    told "excede o limite de 0MB", which reads as a broken feature rather
    than a real limit.
    """
    mb = n / (1024 * 1024)
    if mb >= 1:
        return f"{mb:.1f}MB"
    return f"{n / 1024:.0f}KB"


@dataclass(frozen=True)
class DocumentoStore:
    """One configured document surface.

    `owner_col` is the column naming what the document belongs to
    (`cliente_id`, `codigo`, `atendimento_id`), and `prefixo` is the storage
    path segment after the org — so keys read
    `{org_id}/{prefixo}/{owner}/{document_id}`.

    🔴 `acessos_table` is what turns LGPD logging on. `None` means this
    surface's documents are not personal data (see `imovel_documentos`), and
    that is a claim the caller is making deliberately, not a default it fell
    into — which is why it has no default value here.
    """

    table: str
    owner_col: str
    prefixo: str
    bucket: str
    tipos: tuple[str, ...]
    max_bytes: int
    mimes: frozenset[str]
    acessos_table: Optional[str]

    # ─── validation ───────────────────────────────────────────────────

    def validar(
        self,
        *,
        tipo_documento: str,
        content_type: str,
        tamanho_bytes: int,
        max_bytes: Optional[int] = None,
    ) -> None:
        """Refuse an upload we will not store, naming the limit it hit.

        🔴 `max_bytes` is an override PARAMETER so no test has to monkeypatch
        the configured value. Patching it would mean the test exercises a
        guard it invented rather than the one the product runs — a compliance
        keeper flags exactly that, and it has already caught it once here.
        """
        limite = self.max_bytes if max_bytes is None else max_bytes
        if tipo_documento not in self.tipos:
            raise ValidationError_(
                f"tipo_documento desconhecido: {tipo_documento!r}. "
                f"Permitidos: {', '.join(self.tipos)}",
                field="tipo_documento",
            )
        if content_type not in self.mimes:
            raise ValidationError_(
                f"Tipo de arquivo não permitido: {content_type}. "
                f"Permitidos: {', '.join(sorted(self.mimes))}",
                field="mime_type",
            )
        if tamanho_bytes > limite:
            raise ValidationError_(
                f"Arquivo excede o limite de {format_bytes_human(limite)} "
                f"({format_bytes_human(tamanho_bytes)} enviado)",
                field="tamanho_bytes",
            )

    # ─── reads ────────────────────────────────────────────────────────

    def listar_linhas(self, client: Any, org_id: UUID, owner: Any) -> list[dict]:
        """Every LIVE row for this owner, newest first.

        The soft-delete filter is here, once. A surface that forgot it would
        keep showing a document the user believes they deleted.
        """
        rows = table_reads.paged_rows(
            client,
            self.table,
            org_id,
            eq_filters={self.owner_col: str(owner)},
            refine=lambda q: q.is_("deleted_at", "null"),
        )
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return rows

    def exigir(
        self, client: Any, org_id: UUID, owner: Any, documento_id: UUID
    ) -> dict:
        rows = (
            table_reads.table(client, self.table)
            .select("*")
            .eq("org_id", str(org_id))
            .eq(self.owner_col, str(owner))
            .eq("id", str(documento_id))
            .execute()
        ).data or []
        if not rows or rows[0].get("deleted_at"):
            raise NotFoundError(self.table, str(documento_id))
        return rows[0]

    # ─── writes ───────────────────────────────────────────────────────

    async def guardar(
        self,
        client: Any,
        storage: StorageBackend,
        org_id: UUID,
        owner: Any,
        *,
        filename: str,
        content_type: str,
        data: bytes,
        tipo_documento: str,
        enviado_por: Optional[UUID],
        extra: Optional[dict] = None,
    ) -> dict:
        """Validate → put → insert. Returns the inserted row."""
        self.validar(
            tipo_documento=tipo_documento,
            content_type=content_type,
            tamanho_bytes=len(data),
        )

        documento_id = uuid4()
        # 🔴 The org_id MUST be the first path segment — migration 057's
        # object-RLS policies match on it. A key shaped any other way is
        # readable across orgs.
        storage_path = f"{org_id}/{self.prefixo}/{owner}/{documento_id}"
        await storage.put(
            bucket=self.bucket,
            key=storage_path,
            data=data,
            content_type=content_type,
            metadata={"nome_original": filename},
        )

        row = {
            "id": str(documento_id),
            "org_id": str(org_id),
            self.owner_col: str(owner),
            "storage_path": storage_path,
            "nome_original": filename,
            "mime_type": content_type,
            "tamanho_bytes": len(data),
            "tipo_documento": tipo_documento,
            "enviado_por": str(enviado_por) if enviado_por else None,
            "deleted_at": None,
            "delete_motivo": None,
            "created_at": now_iso(),
            **(extra or {}),
        }
        table_reads.table(client, self.table).insert(row).execute()
        return row

    async def url(
        self,
        client: Any,
        storage: StorageBackend,
        org_id: UUID,
        owner: Any,
        documento_id: UUID,
        *,
        usuario_id: Optional[UUID] = None,
        intent: str = "view",
    ) -> dict:
        """Mint a short-TTL signed URL, logging the access when configured."""
        if intent not in ("view", "download"):
            raise ValidationError_(f"intent inválido: {intent!r}", field="intent")
        documento = self.exigir(client, org_id, owner, documento_id)
        signed = await storage.signed_url(
            bucket=self.bucket,
            key=documento["storage_path"],
            expires_in_seconds=SIGNED_URL_TTL_SECONDS,
        )
        self.log_acesso(client, org_id, documento_id, usuario_id, intent)
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=SIGNED_URL_TTL_SECONDS)
        ).isoformat()
        return {"url": signed, "expires_at": expires_at}

    def remover(
        self,
        client: Any,
        org_id: UUID,
        owner: Any,
        documento_id: UUID,
        *,
        motivo: str,
        usuario_id: Optional[UUID] = None,
    ) -> None:
        self.exigir(client, org_id, owner, documento_id)
        patch: dict[str, Any] = {
            "deleted_at": now_iso(),
            "delete_motivo": motivo,
        }
        if self.acessos_table:
            patch["delete_solicitado_por"] = str(usuario_id) if usuario_id else None
        table_reads.table(client, self.table).update(patch).eq(
            "id", str(documento_id)
        ).execute()
        self.log_acesso(client, org_id, documento_id, usuario_id, "delete")

    # ─── retention ────────────────────────────────────────────────────

    def varrer_expirados(self, client: Any, org_id: UUID) -> int:
        """Soft-delete every live row whose `retencao_ate` has passed.

        The GENERIC half of a retention sweep — "the clock has run out, remove
        the file and record that the system did it". Deciding WHEN the clock
        runs out is per-surface and stays with the surface: `cliente` stamps
        `retencao_ate` at upload, `atendimento` recomputes it from the deal's
        `closed_at` before calling this.

        The delete is attributed to no user (`usuario_id=None`) on purpose — a
        scheduled sweep is a system action, and attributing it to a person
        would put a deletion in someone's audit trail that they did not make.
        """
        rows = (
            table_reads.table(client, self.table)
            .select("id")
            .eq("org_id", str(org_id))
            .is_("deleted_at", "null")
            .lte("retencao_ate", today().isoformat())
            .execute()
        ).data or []
        for row in rows:
            documento_id = UUID(row["id"])
            patch: dict[str, Any] = {
                "deleted_at": now_iso(),
                "delete_motivo": "retenção expirada (sweep automático)",
            }
            # Same condition `remover` uses — a surface without an access log
            # has no `delete_solicitado_por` column to write to.
            if self.acessos_table:
                patch["delete_solicitado_por"] = None
            table_reads.table(client, self.table).update(patch).eq(
                "id", row["id"]
            ).execute()
            self.log_acesso(client, org_id, documento_id, None, "delete")
        return len(rows)

    # ─── the LGPD switch ──────────────────────────────────────────────

    def log_acesso(
        self,
        client: Any,
        org_id: UUID,
        documento_id: UUID,
        usuario_id: Optional[UUID],
        acao: str,
    ) -> None:
        """Append to the access log — a no-op for surfaces that have none.

        NOT a silent fallback: `acessos_table=None` is an explicit statement
        that this surface's documents are not personal data, made at
        construction and readable there.
        """
        if not self.acessos_table:
            return
        table_reads.table(client, self.acessos_table).insert(
            {
                "id": str(uuid4()),
                "org_id": str(org_id),
                "documento_id": str(documento_id),
                "usuario_id": str(usuario_id) if usuario_id else None,
                "acao": acao,
                "created_at": now_iso(),
            }
        ).execute()

    def listar_acessos(
        self, client: Any, org_id: UUID, documento_id: UUID
    ) -> list[dict]:
        """The access log for one document.

        Deliberately does NOT go through `exigir`: a soft-deleted document's
        log — including its own delete entry — must stay readable. Soft delete
        is not erasure.
        """
        if not self.acessos_table:
            return []
        rows = table_reads.paged_rows(
            client,
            self.acessos_table,
            org_id,
            eq_filters={"documento_id": str(documento_id)},
        )
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return rows


__all__ = [
    "SIGNED_URL_TTL_SECONDS",
    "DocumentoStore",
    "format_bytes_human",
    "now_iso",
    "today",
]
