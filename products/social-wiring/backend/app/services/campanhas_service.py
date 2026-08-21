"""Campanhas — the campaign spine and the "solicitar campanha" signal.

Scope is deliberately small (user, 2026-08-20: "keep it simple for later
refinement"). What exists here is the minimum that makes the button on the
imóvel detail page real: resolve an imóvel código to its permanent
registry identity, and record a request against it.

Everything resolves through `imovel_registry`, never `imoveis`. A campaign
outlives the listing it promoted — the imóvel selling is the campaign
SUCCEEDING, and the mirror drops sold imóveis on the next nightly sync.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"
_REGISTRY = "imovel_registry"
_SOLICITACOES = "campanha_solicitacoes"
_CAMPANHAS = "campanhas"


class CampanhaError(Exception):
    """The operation itself failed (DB/transport), as distinct from a
    business refusal like "already requested"."""


class ImovelDesconhecido(CampanhaError):
    """The código does not exist in the registry for this org.

    Distinct from a transport failure on purpose: the caller renders this
    as a 404 with an actionable message, not a 500.
    """


class SolicitacaoDuplicada(CampanhaError):
    """A pending request already exists for this imóvel.

    Not an error condition in the ugly sense — it is the partial unique
    index doing its job. The caller turns it into a 409 so the UI can say
    "já solicitado" rather than silently creating a second row.
    """


class CampanhasService:
    def __init__(self, client: Any) -> None:
        self._client = client

    def _t(self, table: str):
        return self._client.schema(_SCHEMA).table(table)

    # ─── Registry resolution ────────────────────────────────────────────

    def resolve_imovel_ref(self, org_id: UUID, codigo: str) -> str:
        """Registry id for `codigo`, case-insensitively.

        Raises `ImovelDesconhecido` on a miss. The registry holds every
        código ever seen — from the catalog, from a lead, from a venda — so
        a miss here genuinely means "we have never heard of this imóvel",
        not "it was sold".
        """
        canonical = (codigo or "").strip().upper()
        if not canonical:
            raise ImovelDesconhecido("código vazio")

        try:
            resp = (
                self._t(_REGISTRY)
                .select("id")
                .eq("org_id", str(org_id))
                .eq("codigo_canonical", canonical)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            raise CampanhaError(
                f"registry lookup failed for {canonical!r}: {exc}"
            ) from exc

        rows = resp.data or []
        if not rows:
            raise ImovelDesconhecido(canonical)
        return rows[0]["id"]

    # ─── Solicitações ───────────────────────────────────────────────────

    def solicitar(
        self,
        org_id: UUID,
        codigo: str,
        *,
        justificativa: Optional[str] = None,
        solicitado_por: Optional[UUID] = None,
    ) -> dict:
        """Record a campaign request for one imóvel.

        The pending-uniqueness is enforced by a partial unique index, and
        this checks first only to return a clean 409 instead of a raw
        constraint violation. The index remains the real guard — two
        concurrent presses race past any read-then-write check, and the
        database is what actually stops the second one.
        """
        ref_id = self.resolve_imovel_ref(org_id, codigo)

        existing = (
            self._t(_SOLICITACOES)
            .select("id")
            .eq("org_id", str(org_id))
            .eq("imovel_ref_id", ref_id)
            .eq("status", "pendente")
            .limit(1)
            .execute()
        )
        if existing.data:
            raise SolicitacaoDuplicada(codigo.strip().upper())

        row = {
            "org_id": str(org_id),
            "imovel_ref_id": ref_id,
            "status": "pendente",
            "justificativa": (justificativa or "").strip() or None,
        }
        if solicitado_por is not None:
            row["solicitado_por"] = str(solicitado_por)

        try:
            resp = self._t(_SOLICITACOES).insert(row).execute()
        except Exception as exc:
            # The index fired between our read and this write — a real
            # concurrent press, not a bug. Report it as the duplicate it is.
            if "uq_sw_campanha_solicitacoes_pendente" in str(exc):
                raise SolicitacaoDuplicada(codigo.strip().upper()) from exc
            raise CampanhaError(f"could not record solicitação: {exc}") from exc

        created = (resp.data or [{}])[0]
        logger.info(
            "campanha solicitada: org=%s codigo=%s ref=%s",
            org_id, codigo.strip().upper(), ref_id,
        )
        return created

    def solicitacao_do_imovel(self, org_id: UUID, codigo: str) -> Optional[dict]:
        """The PENDING request for this imóvel, if any.

        Drives the button's own state — pressed or not — so the page never
        offers an action that will immediately 409.
        """
        try:
            ref_id = self.resolve_imovel_ref(org_id, codigo)
        except ImovelDesconhecido:
            # An imóvel we do not know cannot have a pending request. That
            # is a clean "no", not an error the button should surface.
            return None

        resp = (
            self._t(_SOLICITACOES)
            .select("*")
            .eq("org_id", str(org_id))
            .eq("imovel_ref_id", ref_id)
            .eq("status", "pendente")
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return rows[0] if rows else None

    def listar_solicitacoes(
        self, org_id: UUID, *, status: Optional[str] = None
    ) -> list[dict]:
        """The queue, newest first.

        Joins the registry so a request for a SOLD imóvel still renders
        with a name — that is what the `snap_*` columns are for.
        """
        query = (
            self._t(_SOLICITACOES)
            .select(
                "*, imovel_registry(codigo_canonical, codigo_display, "
                "ativo_no_vista, snap_titulo, snap_bairro, snap_cidade)"
            )
            .eq("org_id", str(org_id))
        )
        if status:
            query = query.eq("status", status)
        resp = query.order("solicitado_em", desc=True).limit(500).execute()
        return resp.data or []


def build_campanhas_service(client: Any) -> CampanhasService:
    return CampanhasService(client)


__all__ = [
    "CampanhaError",
    "CampanhasService",
    "ImovelDesconhecido",
    "SolicitacaoDuplicada",
    "build_campanhas_service",
]
