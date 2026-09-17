"""Assinaturas service — contract §Manager+member views, amendment A14
(cancel is ordered and never swallowed).

Sort/pagination applied in Python after a scoped fetch — same rationale
every sibling module-1 service documents: the in-repo
`MockSupabaseClient` treats `.order()` as a no-op.

Cancel reuses `noctusai_lib.integrations.payments.make_payment_gateway`
(the headless `PaymentGateway.cancel_subscription`, NOT
`HostedCheckout` — cancellation has no "hosted page" concept) — no new
gateway adapter.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.integrations.payments import PaymentGatewayError, make_payment_gateway

from app.config import settings
from app.services.membros_service import MembrosService

logger = logging.getLogger(__name__)

_TABLE = "assinaturas"
_MEMBROS_TABLE = "membros"
_PLANOS_TABLE = "planos"


class AssinaturasServiceError(Exception):
    """Domain-level failure surfaced to the router as an HTTP error."""

    def __init__(self, detail: str, *, status_code: int = 502) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _default_gateway_factory(gateway: str):
    """Mirrors `checkout_service._default_hosted_checkout_factory`'s
    empty-credential-⇒-Fake posture, but for the headless
    `PaymentGateway` (cancel_subscription lives there, not on
    `HostedCheckout`)."""
    if gateway == "stripe":
        if not settings.stripe_secret_key:
            return make_payment_gateway(use_fake=True)
        return make_payment_gateway(provider="stripe", stripe_api_key=settings.stripe_secret_key)
    if not settings.asaas_api_key:
        return make_payment_gateway(use_fake=True)
    return make_payment_gateway(
        provider="asaas", asaas_api_key=settings.asaas_api_key,
        asaas_base_url=settings.asaas_base_url,
    )


class AssinaturasService:
    def __init__(
        self,
        client: Any,
        *,
        org_id: UUID,
        gateway_factory: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self._client = client
        self._org_id = str(org_id)
        self._gateway_factory = gateway_factory or _default_gateway_factory

    # ── reads ────────────────────────────────────────────────────────

    async def list(
        self,
        *,
        membro_id: Optional[str] = None,
        estado: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        query = self._client.table(_TABLE).select("*").eq("org_id", self._org_id)
        if membro_id:
            query = query.eq("membro_id", str(membro_id))
        if estado:
            query = query.eq("estado", estado)
        rows = query.execute().data or []
        rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        total = len(rows)
        start = (page - 1) * page_size
        page_rows = rows[start:start + page_size]
        membro_nomes = self._membro_nomes([r.get("membro_id") for r in page_rows])
        plano_nomes = self._plano_nomes([r.get("plano_id") for r in page_rows])
        items = [self._to_out(r, membro_nomes, plano_nomes) for r in page_rows]
        return {"items": items, "total": total}

    def _fetch(self, assinatura_id: str) -> Optional[dict]:
        return (
            self._client.table(_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("id", str(assinatura_id))
            .maybe_single()
            .execute()
        ).data

    def _membro_nomes(self, membro_ids: list) -> dict[str, str]:
        ids = sorted({str(i) for i in membro_ids if i})
        if not ids:
            return {}
        rows = (
            self._client.table(_MEMBROS_TABLE)
            .select("id,nome")
            .eq("org_id", self._org_id)
            .in_("id", ids)
            .execute()
            .data
            or []
        )
        return {str(r["id"]): r["nome"] for r in rows}

    def _plano_nomes(self, plano_ids: list) -> dict[str, str]:
        ids = sorted({str(i) for i in plano_ids if i})
        if not ids:
            return {}
        rows = (
            self._client.table(_PLANOS_TABLE)
            .select("id,nome")
            .eq("org_id", self._org_id)
            .in_("id", ids)
            .execute()
            .data
            or []
        )
        return {str(r["id"]): r["nome"] for r in rows}

    @staticmethod
    def _to_out(row: dict, membro_nomes: dict[str, str], plano_nomes: dict[str, str]) -> dict:
        return {
            **row,
            "membro_nome": membro_nomes.get(str(row.get("membro_id"))),
            "plano_nome": plano_nomes.get(str(row.get("plano_id"))),
        }

    # ── writes ───────────────────────────────────────────────────────

    async def cancelar(self, *, assinatura_id: str, motivo: str) -> dict:
        assinatura = self._fetch(assinatura_id)
        if not assinatura:
            raise AssinaturasServiceError("Assinatura não encontrada.", status_code=404)

        # Amendment A14: cancel at the gateway FIRST, then write
        # locally. No external subscription exists yet (an abandoned
        # Stripe checkout, or the A2/A10 shortcut rows this product
        # creates without ever calling the gateway) ⇒ nothing to cancel
        # remotely, skip straight to the local write.
        if assinatura.get("assinatura_externa_id"):
            gateway = self._gateway_factory(assinatura["gateway"])
            try:
                gateway.cancel_subscription(assinatura["assinatura_externa_id"])
            except PaymentGatewayError as exc:
                logger.error(
                    "cancelar: gateway cancel failed for assinatura_id=%s "
                    "gateway=%s: %s", assinatura_id, assinatura["gateway"], exc,
                )
                raise AssinaturasServiceError(
                    "O provedor de pagamento não respondeu. Tente novamente.",
                    status_code=502,
                ) from exc

        now = datetime.now(timezone.utc).isoformat()
        result = (
            self._client.table(_TABLE)
            .update({"estado": "cancelada", "cancelada_em": now})
            .eq("org_id", self._org_id)
            .eq("id", str(assinatura_id))
            .execute()
        )
        if not result.data:
            # Amendment A14: cancelled at the gateway but the LOCAL
            # write failed — log at ERROR with a reconciliation marker
            # and 502, never swallow (silently doing nothing here means
            # we stop billing while still serving access).
            logger.error(
                "cancelar: RECONCILIATION-NEEDED — gateway cancelled but the "
                "local write returned no rows for assinatura_id=%s gateway=%s "
                "assinatura_externa_id=%s",
                assinatura_id, assinatura["gateway"], assinatura.get("assinatura_externa_id"),
            )
            raise AssinaturasServiceError(
                "Falha ao registrar o cancelamento localmente. Contate o suporte.",
                status_code=502,
            )
        row = result.data[0]

        membros_service = MembrosService(self._client, org_id=self._org_id)
        await membros_service.set_status(
            membro_id=assinatura["membro_id"], novo_status="cancelado", motivo=motivo,
        )

        membro_nomes = self._membro_nomes([row.get("membro_id")])
        plano_nomes = self._plano_nomes([row.get("plano_id")])
        return self._to_out(row, membro_nomes, plano_nomes)
