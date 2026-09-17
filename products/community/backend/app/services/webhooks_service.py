"""Webhooks service — contract §Webhooks, amendments A1, A4, A5, A8, A11, A15.

Reuses `noctusai_lib.domain.payments` (`EventInbox` for idempotency,
`SubscriptionState`/`Subscription`/`transition` for the legality check)
and the ALREADY-VERIFIED, ALREADY-NORMALIZED `GatewayEvent` this
module's router hands it (via
`noctusai_lib.integrations.payments.webhook_events.parse_webhook_event`)
— no re-derivation of either.

Ordering is load-bearing (amendment A5) and lives in `handle()`: claim
FIRST (the router already verified the signature before this is ever
called), side effects in one pass, `release()` on ANY exception then
re-raise — never silently swallow a bug, but never let a duplicate
delivery re-run either.

Member status changes route through `app.services.membros_service.
MembrosService.set_status` — the SAME function
`POST /api/membros/{id}/status` uses (contract requirement: "the rules
stay in one place").
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from uuid import uuid4

from noctusai_lib.domain.payments import EventInbox, Subscription, SubscriptionState, transition
from noctusai_lib.integrations.payments.types import Money
from noctusai_lib.integrations.payments.webhook_events import GatewayEvent

from app.services.membros_service import MembrosService

logger = logging.getLogger(__name__)

_ASSINATURAS_TABLE = "assinaturas"
_PAGAMENTOS_TABLE = "pagamentos"
_MEMBROS_TABLE = "membros"

# Amendment A8 — the three vocabularies mapped EXPLICITLY. `pausada` has
# no domain-state counterpart and is never produced by this mapping — a
# webhook never transitions a subscription INTO or OUT OF `pausada`
# (manager-only, per the amendment).
_ESTADO_TO_DOMAIN_STATE: dict[str, SubscriptionState] = {
    "iniciada": SubscriptionState.INCOMPLETE,
    "ativa": SubscriptionState.ACTIVE,
    "inadimplente": SubscriptionState.PAST_DUE,
    "cancelada": SubscriptionState.CANCELED,
}

_DOMAIN_STATE_TO_ESTADO: dict[SubscriptionState, str] = {
    SubscriptionState.INCOMPLETE: "iniciada",
    SubscriptionState.TRIALING: "iniciada",
    SubscriptionState.ACTIVE: "ativa",
    SubscriptionState.PAST_DUE: "inadimplente",
    SubscriptionState.GRACE: "inadimplente",
    SubscriptionState.CANCELED: "cancelada",
    SubscriptionState.EXPIRED: "cancelada",
}

# Stripe's `GatewaySubscriptionStatus` mapped to the SAME domain states
# used above. `unpaid` (Stripe's "subscription itself unpaid") is
# treated identically to `past_due` — both mean "the most recent charge
# did not succeed", which is exactly what PAST_DUE represents here.
_GATEWAY_STATUS_TO_DOMAIN_STATE: dict[str, SubscriptionState] = {
    "trialing": SubscriptionState.TRIALING,
    "active": SubscriptionState.ACTIVE,
    "past_due": SubscriptionState.PAST_DUE,
    "unpaid": SubscriptionState.PAST_DUE,
    "canceled": SubscriptionState.CANCELED,
    "incomplete": SubscriptionState.INCOMPLETE,
}


def _extract_amount_cents(event: GatewayEvent) -> Optional[int]:
    """Amendment A15: amounts are REPORTED data, never authorization.

    `GatewayEvent` itself carries no amount field (see
    `noctusai_lib.integrations.payments.webhook_events`) — only `raw`,
    the gateway's own envelope, has it. Returns `None` (never raises) on
    any shape this doesn't recognize; the caller logs an ERROR and
    defaults to `0` rather than guessing.
    """
    raw = event.raw or {}
    if event.gateway == "stripe":
        obj = (raw.get("data") or {}).get("object") or {}
        for key in ("amount_paid", "amount_due", "total"):
            value = obj.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
        return None
    if event.gateway == "asaas":
        payment = raw.get("payment") or {}
        value = payment.get("value")
        if value is None:
            return None
        try:
            return Money.from_decimal_reais(Decimal(str(value))).amount_cents
        except (InvalidOperation, TypeError, ValueError):
            return None
    return None


class WebhooksService:
    def __init__(self, client: Any, *, inbox: EventInbox) -> None:
        self._client = client
        self._inbox = inbox

    async def handle(self, event: GatewayEvent) -> None:
        """Claim → dispatch → (release + re-raise) on failure.

        The router has ALREADY verified the signature before this is
        called (amendment A5's ordering constraint) — `handle()` only
        owns the claim/dispatch/release half.
        """
        claimed = self._inbox.claim(gateway=event.gateway, event_id=event.event_id)
        if not claimed:
            logger.info(
                "webhooks: duplicate delivery ignored (gateway=%s event_id=%s)",
                event.gateway, event.event_id,
            )
            return
        try:
            await self._dispatch(event)
        except Exception:
            self._inbox.release(gateway=event.gateway, event_id=event.event_id)
            raise

    async def _dispatch(self, event: GatewayEvent) -> None:
        if event.kind == "ignored":
            return
        if event.kind == "charge_paid":
            await self._handle_charge_paid(event)
        elif event.kind == "charge_failed":
            await self._handle_charge_failed(event)
        elif event.kind == "charge_refunded":
            self._handle_charge_refunded(event)
        elif event.kind == "subscription_updated":
            await self._handle_subscription_updated(event)

    # ── resolution — amendment A15: NEVER trust the payload for
    # authorization; resolve OUR OWN rows by the gateway's object ids ──

    def _resolve_assinatura(self, event: GatewayEvent) -> Optional[dict]:
        """Amendment A1: `external_reference` (our own `assinaturas.id`,
        set at checkout time) is the PRIMARY resolution path — it is the
        ONLY key that exists for a Stripe FIRST payment, since Stripe
        has no subscription id until the payer completes checkout.
        `(gateway, assinatura_externa_id)` is the fallback for later
        lifecycle events."""
        if event.external_reference:
            row = (
                self._client.table(_ASSINATURAS_TABLE)
                .select("*")
                .eq("id", str(event.external_reference))
                .maybe_single()
                .execute()
            ).data
            if row:
                return row
        if event.subscription_id_at_gateway:
            rows = (
                self._client.table(_ASSINATURAS_TABLE)
                .select("*")
                .eq("gateway", event.gateway)
                .eq("assinatura_externa_id", event.subscription_id_at_gateway)
                .execute()
                .data
                or []
            )
            if rows:
                return rows[0]
        return None

    def _ensure_externa_ids(self, assinatura: dict, event: GatewayEvent) -> None:
        if not assinatura.get("assinatura_externa_id") and event.subscription_id_at_gateway:
            self._client.table(_ASSINATURAS_TABLE).update(
                {"assinatura_externa_id": event.subscription_id_at_gateway}
            ).eq("id", assinatura["id"]).execute()
            assinatura["assinatura_externa_id"] = event.subscription_id_at_gateway

    # ── charge_paid (amendment A1: first-payment activation) ──────────

    async def _handle_charge_paid(self, event: GatewayEvent) -> None:
        assinatura = self._resolve_assinatura(event)
        if not assinatura:
            logger.warning(
                "webhooks: charge_paid for unknown assinatura "
                "(gateway=%s external_reference=%s subscription_id=%s event_id=%s)",
                event.gateway, event.external_reference,
                event.subscription_id_at_gateway, event.event_id,
            )
            return
        self._ensure_externa_ids(assinatura, event)
        self._upsert_pagamento(event, assinatura, estado="pago")

        if assinatura.get("estado") == "cancelada":
            # Amendment A4: a cancelled/removed subscription is NEVER
            # silently re-activated by a late-arriving charge_paid
            # (routine with gateway invoice retries).
            logger.warning(
                "webhooks: charge_paid ignored for already-cancelled "
                "assinatura_id=%s (event_id=%s)", assinatura["id"], event.event_id,
            )
            return

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        self._client.table(_ASSINATURAS_TABLE).update(
            {"estado": "ativa", "ativa_em": now_iso}
        ).eq("id", assinatura["id"]).execute()

        membro = (
            self._client.table(_MEMBROS_TABLE)
            .select("*")
            .eq("id", assinatura["membro_id"])
            .maybe_single()
            .execute()
        ).data
        if not membro:
            logger.error(
                "webhooks: charge_paid assinatura_id=%s references a "
                "missing membro_id=%s", assinatura["id"], assinatura["membro_id"],
            )
            return

        # Amendment A1 — the load-bearing ordering: set `plano_id` from
        # the PAID subscription's plano_id BEFORE calling the status
        # function, in the same handling pass (this backend has no
        # cross-table DB transaction primitive via the Supabase REST
        # client, so "same transaction" is "same sequential pass,
        # nothing else runs between the two writes"). Otherwise
        # `MembrosService.set_status` 409s
        # ("Defina um plano antes de ativar o membro.") and the claimed
        # inbox key would swallow the payment.
        membro_updates: dict = {"plano_id": assinatura["plano_id"]}
        if not membro.get("entrou_em"):
            membro_updates["entrou_em"] = now_iso
        self._client.table(_MEMBROS_TABLE).update(membro_updates).eq(
            "id", membro["id"]
        ).execute()

        membros_service = MembrosService(self._client, org_id=assinatura["org_id"])
        await membros_service.set_status(membro_id=membro["id"], novo_status="ativo")

    # ── charge_failed ──────────────────────────────────────────────────

    async def _handle_charge_failed(self, event: GatewayEvent) -> None:
        assinatura = self._resolve_assinatura(event)
        if not assinatura:
            logger.warning(
                "webhooks: charge_failed for unknown assinatura "
                "(gateway=%s external_reference=%s subscription_id=%s event_id=%s)",
                event.gateway, event.external_reference,
                event.subscription_id_at_gateway, event.event_id,
            )
            return
        self._ensure_externa_ids(assinatura, event)
        self._upsert_pagamento(event, assinatura, estado="falhou")

        if assinatura.get("estado") == "cancelada":
            logger.warning(
                "webhooks: charge_failed ignored for already-cancelled "
                "assinatura_id=%s (event_id=%s)", assinatura["id"], event.event_id,
            )
            return

        self._client.table(_ASSINATURAS_TABLE).update(
            {"estado": "inadimplente"}
        ).eq("id", assinatura["id"]).execute()

        membros_service = MembrosService(self._client, org_id=assinatura["org_id"])
        await membros_service.set_status(
            membro_id=assinatura["membro_id"], novo_status="atrasado",
        )

    # ── charge_refunded — no subscription/member status change ────────

    def _handle_charge_refunded(self, event: GatewayEvent) -> None:
        assinatura = self._resolve_assinatura(event)
        if not assinatura:
            logger.warning(
                "webhooks: charge_refunded for unknown assinatura "
                "(gateway=%s charge_id=%s event_id=%s)",
                event.gateway, event.charge_id_at_gateway, event.event_id,
            )
            return
        self._ensure_externa_ids(assinatura, event)
        self._upsert_pagamento(event, assinatura, estado="estornado")
        # Contract: "no member status change (a manager decides)."

    # ── subscription_updated (amendments A4, A8) ──────────────────────

    async def _handle_subscription_updated(self, event: GatewayEvent) -> None:
        assinatura = self._resolve_assinatura(event)
        if not assinatura:
            logger.warning(
                "webhooks: subscription_updated for unknown assinatura "
                "(gateway=%s external_reference=%s subscription_id=%s event_id=%s)",
                event.gateway, event.external_reference,
                event.subscription_id_at_gateway, event.event_id,
            )
            return
        self._ensure_externa_ids(assinatura, event)

        gateway_status = event.subscription_status
        if gateway_status is None:
            # Asaas never carries a subscription status on any event
            # (webhook_events.py's module docstring); this event kind
            # never fires on that path in the first place, so reaching
            # here means an unexpected payload shape.
            logger.warning(
                "webhooks: subscription_updated with no subscription_status "
                "(gateway=%s event_id=%s)", event.gateway, event.event_id,
            )
            return
        target_domain_state = _GATEWAY_STATUS_TO_DOMAIN_STATE.get(gateway_status)
        if target_domain_state is None:
            logger.warning(
                "webhooks: unrecognized gateway subscription_status=%r (event_id=%s)",
                gateway_status, event.event_id,
            )
            return

        current_estado = assinatura.get("estado")
        if current_estado == "pausada":
            # Amendment A8: pausada is manager-only, never
            # webhook-driven — a webhook never moves a paused
            # subscription in either direction.
            logger.warning(
                "webhooks: subscription_updated ignored for manager-paused "
                "assinatura_id=%s (event_id=%s)", assinatura["id"], event.event_id,
            )
            return
        current_domain_state = _ESTADO_TO_DOMAIN_STATE.get(current_estado)
        if current_domain_state is None:
            logger.warning(
                "webhooks: assinatura_id=%s has unmapped estado=%r (event_id=%s)",
                assinatura["id"], current_estado, event.event_id,
            )
            return

        target_estado = _DOMAIN_STATE_TO_ESTADO[target_domain_state]
        if target_estado == current_estado:
            return  # already there — no-op, not an error

        # Amendment A4: call `transition()` and let it be the legality
        # gate. Stripe invoice retries routinely deliver
        # subscription_updated=cancelled interleaved with a late
        # charge_paid, which would otherwise attempt an illegal move; a
        # `ValueError` here is logged + swallowed (200), never a 5xx /
        # retry storm.
        now = datetime.now(timezone.utc)
        transient_subscription = Subscription(
            id=str(assinatura["id"]),
            external_reference=str(assinatura["id"]),
            gateway=assinatura["gateway"],
            id_at_gateway=assinatura.get("assinatura_externa_id") or "",
            state=current_domain_state,
            created_at=now,
            updated_at=now,
        )
        try:
            transition(transient_subscription, target_domain_state, now=now)
        except ValueError:
            logger.warning(
                "webhooks: illegal transition %s -> %s ignored "
                "(assinatura_id=%s event_id=%s)",
                current_domain_state.value, target_domain_state.value,
                assinatura["id"], event.event_id,
            )
            return

        updates: dict = {"estado": target_estado}
        if target_estado == "cancelada":
            updates["cancelada_em"] = now.isoformat()
        self._client.table(_ASSINATURAS_TABLE).update(updates).eq(
            "id", assinatura["id"]
        ).execute()

        membro_status = None
        if target_estado == "cancelada":
            membro_status = "cancelado"
        # target_estado == "pausada" is unreachable here (A8: no gateway
        # status maps to it) — kept out of this branch entirely rather
        # than a dead `elif`, per the mapping table above.
        if membro_status:
            membros_service = MembrosService(self._client, org_id=assinatura["org_id"])
            await membros_service.set_status(
                membro_id=assinatura["membro_id"], novo_status=membro_status,
            )

    # ── pagamentos upsert (amendments A11, A15) ───────────────────────

    def _upsert_pagamento(self, event: GatewayEvent, assinatura: dict, *, estado: str) -> None:
        cobranca_id = event.charge_id_at_gateway
        if not cobranca_id:
            logger.warning(
                "webhooks: %s event with no charge_id_at_gateway (event_id=%s)",
                event.kind, event.event_id,
            )
            return
        existing = (
            self._client.table(_PAGAMENTOS_TABLE)
            .select("*")
            .eq("gateway", event.gateway)
            .eq("cobranca_externa_id", str(cobranca_id))
            .maybe_single()
            .execute()
        ).data
        now_iso = datetime.now(timezone.utc).isoformat()
        amount_cents = _extract_amount_cents(event)

        if existing:
            updates: dict = {"estado": estado}
            if estado == "pago":
                updates["pago_em"] = now_iso
                # Amendment A11: pix_imagem_base64 is nulled once paid.
                updates["pix_imagem_base64"] = None
            if amount_cents is not None and amount_cents != existing.get("valor_centavos"):
                # Amendment A15: reported data, never authorization —
                # log and move on, never gate access on this.
                logger.warning(
                    "webhooks: reported amount %s differs from stored "
                    "valor_centavos %s (gateway=%s cobranca_externa_id=%s)",
                    amount_cents, existing.get("valor_centavos"), event.gateway, cobranca_id,
                )
            self._client.table(_PAGAMENTOS_TABLE).update(updates).eq(
                "id", existing["id"]
            ).execute()
            return

        if amount_cents is None:
            logger.error(
                "webhooks: could not extract a charge amount from the %s "
                "payload (gateway=%s cobranca_externa_id=%s) — defaulting "
                "valor_centavos to 0", event.kind, event.gateway, cobranca_id,
            )
        row = {
            "id": str(uuid4()), "org_id": assinatura["org_id"],
            "assinatura_id": assinatura["id"], "membro_id": assinatura["membro_id"],
            "gateway": event.gateway, "cobranca_externa_id": str(cobranca_id),
            "valor_centavos": amount_cents if amount_cents is not None else 0,
            "metodo": assinatura["metodo"], "estado": estado,
            "pago_em": now_iso if estado == "pago" else None,
            "vencimento": None, "url_fatura": None, "pix_payload": None,
            "pix_imagem_base64": None, "created_at": now_iso, "updated_at": now_iso,
        }
        self._client.table(_PAGAMENTOS_TABLE).insert(row).execute()
