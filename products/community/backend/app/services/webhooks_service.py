"""Webhooks service — contract §Webhooks, amendments A1, A4, A5, A8, A11, A15,
plus the Ninho Vazio billing lifecycle (projects/ninho-vazio/CONTRACT.md
§Billing lifecycle): paid → `ativa` with `pago_ate`/`proxima_cobranca`;
failed/overdue → `carencia` (access kept); refunded → an `estorno`
lancamento; every paid/refunded charge books cashflow exactly once; every
state change writes the member timeline.

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
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Optional
from uuid import uuid4

from noctusai_lib.domain.payments import EventInbox, SubscriptionState
from noctusai_lib.integrations.payments.types import Money
from noctusai_lib.integrations.payments.webhook_events import GatewayEvent
from postgrest.exceptions import APIError

from app.services.ciclo_assinatura import (
    ESTADO_PARA_SEED,
    SEED_PARA_ESTADO,
    TransicaoIlegal,
    agora_utc,
    calcular_carencia_ate,
    formatar_data,
    formatar_reais,
    hoje_local,
    inicio_do_dia,
    iso,
    ler_configuracoes,
    ler_data,
    ler_timestamp,
    somar_ciclo,
    validar_transicao,
)
from app.services.eventos_service import registrar_evento
from app.services.membros_service import MembrosService

logger = logging.getLogger(__name__)

_ASSINATURAS_TABLE = "assinaturas"
_PAGAMENTOS_TABLE = "pagamentos"
_MEMBROS_TABLE = "membros"
_LANCAMENTOS_TABLE = "lancamentos"

#: Postgres unique_violation — the replay-safety net on
#: `lancamentos_pagamento_unique` / `lancamentos_estorno_unique`.
_UNIQUE_VIOLATION = "23505"

EVENTO_PAGAMENTO_APOS_ENCERRAMENTO = (
    "Pagamento recebido após o encerramento — verificar reembolso ou reativação."
)

# Stripe's `GatewaySubscriptionStatus` mapped to the seed's domain states.
# `unpaid` (Stripe's "subscription itself unpaid") is treated identically
# to `past_due` — both mean "the most recent charge did not succeed".
# The pt-BR ↔ seed mapping itself lives in `ciclo_assinatura` (CONTRACT.md
# §Billing lifecycle) — one table for every caller.
_GATEWAY_STATUS_TO_DOMAIN_STATE: dict[str, SubscriptionState] = {
    "trialing": SubscriptionState.TRIALING,
    "active": SubscriptionState.ACTIVE,
    "past_due": SubscriptionState.PAST_DUE,
    "unpaid": SubscriptionState.PAST_DUE,
    "canceled": SubscriptionState.CANCELED,
    "incomplete": SubscriptionState.INCOMPLETE,
}


def _extract_due_date(event: GatewayEvent):
    """The charge's own due date (Asaas `payment.dueDate`), or None.

    Stripe invoices carry no due date on the paid path — the caller falls
    back to the payment day, which is what "due date" means for a card
    charged on its renewal day.
    """
    if event.gateway != "asaas":
        return None
    payment = (event.raw or {}).get("payment") or {}
    return ler_data(payment.get("dueDate"))


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
    def __init__(
        self,
        client: Any,
        *,
        inbox: EventInbox,
        org_id: Any,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._client = client
        self._inbox = inbox
        # Slice C (user decision 2026-09-17): defense-in-depth org scoping.
        # Community is single-tenant today (one org per deployment), so
        # this was never reachable in practice — but `_resolve_assinatura`
        # previously matched ANY row by `id`/`(gateway, assinatura_
        # externa_id)` with no org filter at all. Scoping the query here
        # means a resolved `assinatura` row's `org_id` is ALWAYS this
        # service's `org_id` by construction (every read/write below that
        # trusts `assinatura["org_id"]` inherits that guarantee).
        self._org_id = str(org_id)
        # Clock seam (tests pin "now"; production reads the wall clock).
        self._clock = clock or agora_utc

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
        lifecycle events (every Asaas renewal charge)."""
        if event.external_reference:
            row = (
                self._client.table(_ASSINATURAS_TABLE)
                .select("*")
                .eq("id", str(event.external_reference))
                .eq("org_id", self._org_id)
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
                .eq("org_id", self._org_id)
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

    def _evento(self, assinatura: dict, tipo: str, descricao: str, dados: dict) -> None:
        registrar_evento(
            self._client, org_id=assinatura["org_id"], membro_id=assinatura["membro_id"],
            tipo=tipo, descricao=descricao,
            dados={"assinatura_id": str(assinatura["id"]), **dados},
        )

    def _unknown(self, event: GatewayEvent) -> None:
        logger.warning(
            "webhooks: %s for unknown assinatura "
            "(gateway=%s external_reference=%s subscription_id=%s charge_id=%s event_id=%s)",
            event.kind, event.gateway, event.external_reference,
            event.subscription_id_at_gateway, event.charge_id_at_gateway, event.event_id,
        )

    # ── charge_paid — CONTRACT.md §Billing lifecycle row 1 + "payment
    # arrives for an expirada/cancelada sub" (amendment A1 kept) ─────────

    async def _handle_charge_paid(self, event: GatewayEvent) -> None:
        assinatura = self._resolve_assinatura(event)
        if not assinatura:
            self._unknown(event)
            return
        self._ensure_externa_ids(assinatura, event)
        now = self._clock()
        pagamento, anterior = self._upsert_pagamento(event, assinatura, estado="pago", now=now)
        # A second charge_paid for the SAME charge (Asaas fires both
        # PAYMENT_CONFIRMED and PAYMENT_RECEIVED for a card) carries a new
        # event id, so the inbox lets it through: every write below is
        # idempotent, and the timeline is written once.
        repeticao = anterior == "pago"
        if pagamento is not None:
            self._lancar(
                coluna="pagamento_id", pagamento=pagamento, assinatura=assinatura,
                tipo="entrada", origem="pagamento", categoria="assinatura",
                descricao="Pagamento de assinatura", data=hoje_local(now),
            )
        valor = (pagamento or {}).get("valor_centavos") or 0
        dados_pagamento = {
            "pagamento_id": str(pagamento["id"]) if pagamento else None,
            "valor_centavos": valor,
        }

        estado = assinatura.get("estado")
        if estado in ("cancelada", "expirada"):
            # Amendment A4 kept: an ended subscription is NEVER silently
            # re-activated by a late charge. The money is real, so it is
            # stored and booked, and a human is told to decide.
            logger.warning(
                "webhooks: charge_paid for ended assinatura_id=%s estado=%s (event_id=%s)",
                assinatura["id"], estado, event.event_id,
            )
            if not repeticao:
                self._evento(
                    assinatura, "sistema", EVENTO_PAGAMENTO_APOS_ENCERRAMENTO,
                    {**dados_pagamento, "estado": estado},
                )
            return
        if estado == "pausada":
            # Manager-only state (amendment A8): the payment is recorded,
            # the subscription does not move.
            logger.warning(
                "webhooks: charge_paid for manager-paused assinatura_id=%s — "
                "estado kept (event_id=%s)", assinatura["id"], event.event_id,
            )
            if not repeticao:
                self._evento(
                    assinatura, "pagamento",
                    f"Pagamento de {formatar_reais(valor)} recebido (assinatura pausada).",
                    dados_pagamento,
                )
            return

        if estado != "ativa":
            try:
                validar_transicao(assinatura, "ativa", now=now)
            except TransicaoIlegal as exc:
                logger.error("webhooks: charge_paid not applied — %s (event_id=%s)", exc, event.event_id)
                return

        vencimento = _extract_due_date(event) or hoje_local(now)
        proxima = somar_ciclo(vencimento, assinatura.get("ciclo") or "mensal")
        pago_ate = inicio_do_dia(proxima)
        updates: dict = {"estado": "ativa", "inadimplente_desde": None, "carencia_ate": None}
        atual_pago_ate = ler_timestamp(assinatura.get("pago_ate"))
        # A late webhook for an OLDER charge never moves the paid-through
        # date backwards.
        if atual_pago_ate is None or pago_ate > atual_pago_ate:
            updates["pago_ate"] = iso(pago_ate)
            updates["proxima_cobranca"] = proxima.isoformat()
        else:
            pago_ate = atual_pago_ate
        if not assinatura.get("ativa_em"):
            updates["ativa_em"] = iso(now)
        self._client.table(_ASSINATURAS_TABLE).update(updates).eq(
            "id", assinatura["id"]
        ).execute()

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
        # function, in the same handling pass. Otherwise
        # `MembrosService.set_status` 409s ("Defina um plano antes de
        # ativar o membro.") and the claimed inbox key would swallow the
        # payment.
        membro_updates: dict = {"plano_id": assinatura["plano_id"]}
        if not membro.get("entrou_em"):
            membro_updates["entrou_em"] = iso(now)
        self._client.table(_MEMBROS_TABLE).update(membro_updates).eq(
            "id", membro["id"]
        ).execute()

        membros_service = MembrosService(self._client, org_id=assinatura["org_id"])
        await membros_service.set_status(membro_id=membro["id"], novo_status="ativo")

        if not repeticao:
            self._evento(
                assinatura, "pagamento",
                f"Pagamento de {formatar_reais(valor)} confirmado — acesso até "
                f"{formatar_data(pago_ate)}.",
                {**dados_pagamento, "estado_anterior": estado, "pago_ate": iso(pago_ate)},
            )

    # ── charge_failed / PAYMENT_OVERDUE — the grace path ──────────────

    async def _handle_charge_failed(self, event: GatewayEvent) -> None:
        """CONTRACT.md §Billing lifecycle row 2.

        The seed parser maps Asaas `PAYMENT_OVERDUE` to `charge_failed`
        (`webhook_events._ASAAS_EVENT_KIND_MAP`), so an overdue renewal
        lands here. The seed machine has no ACTIVE → GRACE edge; the move
        is validated as the path ACTIVE → PAST_DUE → GRACE and written as
        its end state.
        """
        assinatura = self._resolve_assinatura(event)
        if not assinatura:
            self._unknown(event)
            return
        self._ensure_externa_ids(assinatura, event)
        now = self._clock()
        pagamento, anterior = self._upsert_pagamento(
            event, assinatura, estado="falhou", now=now, nao_rebaixar=("pago", "estornado"),
        )
        if anterior in ("pago", "estornado"):
            # A stale overdue delivered after the charge was paid.
            logger.warning(
                "webhooks: charge_failed ignored — charge already %s "
                "(assinatura_id=%s event_id=%s)", anterior, assinatura["id"], event.event_id,
            )
            return

        estado = assinatura.get("estado")
        if estado in ("cancelada", "expirada", "pausada"):
            logger.warning(
                "webhooks: charge_failed ignored for assinatura_id=%s estado=%s (event_id=%s)",
                assinatura["id"], estado, event.event_id,
            )
            return

        caminho: tuple[str, ...]
        if estado == "carencia":
            caminho = ()
        elif estado == "inadimplente":
            caminho = ("carencia",)
        else:
            caminho = ("inadimplente", "carencia")
        if caminho:
            try:
                validar_transicao(assinatura, *caminho, now=now)
            except TransicaoIlegal as exc:
                # e.g. `iniciada`: a first charge that never succeeded has
                # nothing to be lenient about — no grace is granted.
                logger.error(
                    "webhooks: charge_failed not applied — %s (event_id=%s)", exc, event.event_id,
                )
                return

        inadimplente_desde = ler_timestamp(assinatura.get("inadimplente_desde")) or now
        carencia_ate = ler_timestamp(assinatura.get("carencia_ate"))
        mudou = bool(caminho) or carencia_ate is None
        if carencia_ate is None:
            dias = ler_configuracoes(self._client, assinatura["org_id"]).get("dias_carencia")
            carencia_ate = calcular_carencia_ate(inadimplente_desde, dias)
        if mudou:
            self._client.table(_ASSINATURAS_TABLE).update({
                "estado": "carencia",
                "inadimplente_desde": iso(inadimplente_desde),
                "carencia_ate": iso(carencia_ate),
            }).eq("id", assinatura["id"]).execute()

        # Access is KEPT during grace: the member moves to `atrasado`, not
        # off the plan.
        membros_service = MembrosService(self._client, org_id=assinatura["org_id"])
        await membros_service.set_status(
            membro_id=assinatura["membro_id"], novo_status="atrasado",
        )

        if mudou or anterior != "falhou":
            self._evento(
                assinatura, "assinatura",
                f"Cobrança não paga — em carência até {formatar_data(carencia_ate)}. "
                "Acesso mantido.",
                {
                    "pagamento_id": str(pagamento["id"]) if pagamento else None,
                    "estado_anterior": estado,
                    "inadimplente_desde": iso(inadimplente_desde),
                    "carencia_ate": iso(carencia_ate),
                },
            )

    # ── charge_refunded — no subscription/member status change ────────

    def _handle_charge_refunded(self, event: GatewayEvent) -> None:
        assinatura = self._resolve_assinatura(event)
        if not assinatura:
            self._unknown(event)
            return
        self._ensure_externa_ids(assinatura, event)
        now = self._clock()
        pagamento, anterior = self._upsert_pagamento(event, assinatura, estado="estornado", now=now)
        # Contract: "no member status change (a manager decides)."
        if pagamento is None:
            return
        self._lancar(
            coluna="estorno_de", pagamento=pagamento, assinatura=assinatura,
            tipo="saida", origem="estorno", categoria="estorno",
            descricao="Estorno de pagamento", data=hoje_local(now),
        )
        if anterior != "estornado":
            valor = pagamento.get("valor_centavos") or 0
            self._evento(
                assinatura, "pagamento", f"Estorno de {formatar_reais(valor)} registrado.",
                {"pagamento_id": str(pagamento["id"]), "valor_centavos": valor},
            )

    # ── subscription_updated (Stripe only — amendments A4, A8) ────────

    async def _handle_subscription_updated(self, event: GatewayEvent) -> None:
        assinatura = self._resolve_assinatura(event)
        if not assinatura:
            self._unknown(event)
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
            # Amendment A8: pausada is manager-only, never webhook-driven.
            logger.warning(
                "webhooks: subscription_updated ignored for manager-paused "
                "assinatura_id=%s (event_id=%s)", assinatura["id"], event.event_id,
            )
            return
        if current_estado not in ESTADO_PARA_SEED:
            logger.warning(
                "webhooks: assinatura_id=%s has unmapped estado=%r (event_id=%s)",
                assinatura["id"], current_estado, event.event_id,
            )
            return

        target_estado = SEED_PARA_ESTADO[target_domain_state]
        if target_estado == current_estado:
            return  # already there — no-op, not an error

        # Amendment A4: the seed's `transition()` is the legality gate —
        # Stripe invoice retries routinely interleave a cancel with a late
        # charge_paid. An illegal move is logged and never applied (200,
        # never a 5xx retry storm).
        now = self._clock()
        try:
            validar_transicao(assinatura, target_estado, now=now)
        except TransicaoIlegal as exc:
            logger.warning(
                "webhooks: illegal transition ignored — %s (event_id=%s)", exc, event.event_id,
            )
            return

        updates: dict = {"estado": target_estado}
        if target_estado == "cancelada":
            updates["cancelada_em"] = iso(now)
            updates["cancelamento_solicitado_por"] = "sistema"
        self._client.table(_ASSINATURAS_TABLE).update(updates).eq(
            "id", assinatura["id"]
        ).execute()

        if target_estado == "cancelada":
            membros_service = MembrosService(self._client, org_id=assinatura["org_id"])
            await membros_service.set_status(
                membro_id=assinatura["membro_id"], novo_status="cancelado",
            )
        self._evento(
            assinatura, "assinatura",
            f"Assinatura atualizada pelo gateway: {current_estado} → {target_estado}.",
            {"estado_anterior": current_estado, "estado": target_estado},
        )

    # ── pagamentos upsert (amendments A11, A15) ───────────────────────

    def _upsert_pagamento(
        self,
        event: GatewayEvent,
        assinatura: dict,
        *,
        estado: str,
        now: datetime,
        nao_rebaixar: tuple[str, ...] = (),
    ) -> tuple[Optional[dict], Optional[str]]:
        """Insert-or-update the `pagamentos` row for this charge.

        Returns `(row, estado_anterior)` — `estado_anterior` is None for a
        newly inserted row. A row already in one of `nao_rebaixar` is left
        untouched (returned as-is) so a stale event can't downgrade it.
        """
        cobranca_id = event.charge_id_at_gateway
        if not cobranca_id:
            logger.warning(
                "webhooks: %s event with no charge_id_at_gateway (event_id=%s)",
                event.kind, event.event_id,
            )
            return None, None
        existing = (
            self._client.table(_PAGAMENTOS_TABLE)
            .select("*")
            .eq("gateway", event.gateway)
            .eq("cobranca_externa_id", str(cobranca_id))
            .maybe_single()
            .execute()
        ).data
        now_iso = iso(now)
        amount_cents = _extract_amount_cents(event)

        if existing:
            anterior = existing.get("estado")
            if anterior in nao_rebaixar:
                return existing, anterior
            updates: dict = {"estado": estado}
            if estado == "pago" and not existing.get("pago_em"):
                updates["pago_em"] = now_iso
            if estado == "pago":
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
            return {**existing, **updates}, anterior

        if amount_cents is None:
            logger.error(
                "webhooks: could not extract a charge amount from the %s "
                "payload (gateway=%s cobranca_externa_id=%s) — defaulting "
                "valor_centavos to 0", event.kind, event.gateway, cobranca_id,
            )
        vencimento = _extract_due_date(event)
        row = {
            "id": str(uuid4()), "org_id": assinatura["org_id"],
            "assinatura_id": assinatura["id"], "membro_id": assinatura["membro_id"],
            "gateway": event.gateway, "cobranca_externa_id": str(cobranca_id),
            "valor_centavos": amount_cents if amount_cents is not None else 0,
            "metodo": assinatura["metodo"], "estado": estado,
            "pago_em": now_iso if estado == "pago" else None,
            "vencimento": iso(inicio_do_dia(vencimento)) if vencimento else None,
            "url_fatura": None, "pix_payload": None,
            "pix_imagem_base64": None, "created_at": now_iso, "updated_at": now_iso,
        }
        written = self._client.table(_PAGAMENTOS_TABLE).insert(row).execute().data or []
        return (written[0] if written else row), None

    # ── lancamentos — cashflow booking, idempotent per charge ─────────

    def _lancar(
        self,
        *,
        coluna: str,
        pagamento: dict,
        assinatura: dict,
        tipo: str,
        origem: str,
        categoria: str,
        descricao: str,
        data,
    ) -> bool:
        """Book one `lancamentos` row keyed by `coluna` (`pagamento_id` for
        an entrada, `estorno_de` for a refund). Returns True when written.

        Replay-safe twice over: an existing row for this charge is found
        first; a concurrent delivery that races past that read hits the
        partial UNIQUE index (migration 013) and its 23505 is handled here
        as "already booked" — any other database error propagates.
        """
        pagamento_id = str(pagamento["id"])
        valor = int(pagamento.get("valor_centavos") or 0)
        if valor <= 0:
            logger.error(
                "webhooks: lancamento %s not booked — pagamento_id=%s has "
                "valor_centavos=%s (amount missing from the gateway payload)",
                origem, pagamento_id, valor,
            )
            return False
        existing = (
            self._client.table(_LANCAMENTOS_TABLE)
            .select("id")
            .eq(coluna, pagamento_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if existing:
            return False
        row = {
            "id": str(uuid4()), "org_id": assinatura["org_id"], "tipo": tipo,
            "categoria": categoria, "descricao": descricao, "valor_centavos": valor,
            "data": data.isoformat(), "origem": origem,
            "pagamento_id": pagamento_id if coluna == "pagamento_id" else None,
            "estorno_de": pagamento_id if coluna == "estorno_de" else None,
            "membro_id": assinatura["membro_id"],
        }
        try:
            self._client.table(_LANCAMENTOS_TABLE).insert(row).execute()
        except APIError as exc:
            if exc.code != _UNIQUE_VIOLATION:
                raise
            logger.info(
                "webhooks: lancamento for %s=%s already booked by a concurrent "
                "delivery", coluna, pagamento_id,
            )
            return False
        return True
