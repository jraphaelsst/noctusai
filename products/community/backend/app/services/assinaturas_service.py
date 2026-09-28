"""Assinaturas service — contract §Manager+member views, amendment A14
(cancel is ordered and never swallowed), and the Ninho Vazio cancellation
row of CONTRACT.md §Billing lifecycle: the move is validated by the seed
state machine, records who asked (`membro` | `equipe`) and why, and the
member KEEPS their plan until `pago_ate` — the billing sweep moves them to
the free plan afterwards.

Sort/pagination applied in Python after a scoped fetch — same rationale
every sibling module-1 service documents: the in-repo
`MockSupabaseClient` treats `.order()` as a no-op.

Cancel reuses `noctusai_lib.integrations.payments.make_payment_gateway`
(the headless `PaymentGateway.cancel_subscription`, NOT
`HostedCheckout` — cancellation has no "hosted page" concept) — no new
gateway adapter.
"""
from __future__ import annotations

import functools
import logging
from datetime import datetime
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.integrations.payments import PaymentGatewayError, make_payment_gateway
from noctusai_lib.security.api_keys import resolve_api_key

from app.config import settings
from app.services.ciclo_assinatura import (
    ESTADOS_EM_COBRANCA,
    GatewayNaoConfigurado,
    TransicaoIlegal,
    agora_utc,
    iso,
    validar_transicao,
)
from app.services.eventos_service import registrar_evento

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


class CancelamentoGatewayFalhou(AssinaturasServiceError):
    """The gateway refused (or could not be asked) to cancel; nothing was
    written locally. Callers with their own wording (the member portal)
    map this subclass; the generic detail stays for staff."""

    def __init__(self) -> None:
        super().__init__(
            "O provedor de pagamento não respondeu. Tente novamente.", status_code=502,
        )


def _default_gateway_factory(gateway: str, *, org_id: str):
    """Mirrors `checkout_service._default_hosted_checkout_factory`'s
    org-scoped-resolve-⇒-Fake-on-miss posture (Slice C: `resolve_api_key`
    — org override first, `settings.stripe_secret_key`/`.asaas_api_key`'s
    env fallback unchanged), but for the headless `PaymentGateway`
    (cancel_subscription lives there, not on `HostedCheckout`)."""
    if gateway == "stripe":
        key = resolve_api_key("stripe_secret_key", org_id)
        if not key:
            return make_payment_gateway(use_fake=True)
        return make_payment_gateway(provider="stripe", stripe_api_key=key)
    key = resolve_api_key("asaas_api_key", org_id)
    if not key:
        return make_payment_gateway(use_fake=True)
    return make_payment_gateway(
        provider="asaas", asaas_api_key=key, asaas_base_url=settings.asaas_base_url,
    )


class AssinaturasService:
    def __init__(
        self,
        client: Any,
        *,
        org_id: UUID,
        gateway_factory: Optional[Callable[[str], Any]] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._client = client
        self._org_id = str(org_id)
        # NOC-REMEDIATE[community-gateway-fake-fallback]: the staff default
        # still falls back to the Fake gateway on a missing key (module 2);
        # the member portal and the billing sweep pass
        # `ciclo_assinatura.gateway_estrito`, which refuses instead. — 2026-09-28
        self._gateway_factory = gateway_factory or functools.partial(
            _default_gateway_factory, org_id=self._org_id
        )
        self._clock = clock or agora_utc

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

    def assinatura_em_cobranca(self, *, membro_id: str) -> Optional[dict]:
        """The member's most recent subscription whose charges still run
        (`ativa` / `inadimplente` / `carencia`), or None."""
        rows = (
            self._client.table(_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("membro_id", str(membro_id))
            .in_("estado", list(ESTADOS_EM_COBRANCA))
            .execute()
            .data
            or []
        )
        rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        return rows[0] if rows else None

    async def cancelar(
        self,
        *,
        assinatura_id: str,
        motivo: Optional[str],
        solicitado_por: str = "equipe",
        autor_id: Any = None,
    ) -> dict:
        assinatura = self._fetch(assinatura_id)
        if not assinatura:
            raise AssinaturasServiceError("Assinatura não encontrada.", status_code=404)

        now = self._clock()
        if assinatura.get("estado") != "pausada":
            # `pausada` is the one manager-only state outside the seed
            # machine (amendment A8); ending it is a manager decision. Every
            # other move is the seed's call.
            try:
                validar_transicao(assinatura, "cancelada", now=now)
            except TransicaoIlegal as exc:
                logger.warning("cancelar: refused — %s", exc)
                raise AssinaturasServiceError(
                    "Esta assinatura já está encerrada.", status_code=409,
                ) from exc

        # Amendment A14: cancel at the gateway FIRST, then write
        # locally. No external subscription exists yet (an abandoned
        # Stripe checkout, or the A2/A10 shortcut rows this product
        # creates without ever calling the gateway) ⇒ nothing to cancel
        # remotely, skip straight to the local write.
        if assinatura.get("assinatura_externa_id"):
            try:
                gateway = self._gateway_factory(assinatura["gateway"])
                gateway.cancel_subscription(assinatura["assinatura_externa_id"])
            except (PaymentGatewayError, GatewayNaoConfigurado) as exc:
                logger.error(
                    "cancelar: gateway cancel failed for assinatura_id=%s "
                    "gateway=%s: %s", assinatura_id, assinatura["gateway"], exc,
                )
                raise CancelamentoGatewayFalhou() from exc

        result = (
            self._client.table(_TABLE)
            .update({
                "estado": "cancelada",
                "cancelada_em": iso(now),
                "cancelamento_solicitado_por": solicitado_por,
                "cancelamento_motivo": motivo,
            })
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

        # CONTRACT.md §Billing lifecycle: the member keeps the plan until
        # `pago_ate`; `cobranca_service` moves them to the free plan after.
        quem = "pela própria associada" if solicitado_por == "membro" else "pela equipe"
        registrar_evento(
            self._client, org_id=self._org_id, membro_id=assinatura["membro_id"],
            tipo="assinatura",
            descricao=f"Assinatura cancelada {quem}." + (f" Motivo: {motivo}" if motivo else ""),
            dados={
                "assinatura_id": str(assinatura_id),
                "estado_anterior": assinatura.get("estado"),
                "solicitado_por": solicitado_por,
                "motivo": motivo,
                "pago_ate": row.get("pago_ate"),
            },
            autor_id=autor_id,
        )

        membro_nomes = self._membro_nomes([row.get("membro_id")])
        plano_nomes = self._plano_nomes([row.get("plano_id")])
        return self._to_out(row, membro_nomes, plano_nomes)
