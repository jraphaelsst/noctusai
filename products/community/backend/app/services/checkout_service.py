"""Checkout service — contract §Checkout, amendments A1-A5/A10, product
decisions P1 (CPF)/P2 (Turnstile + abuse caps).

Reuses `noctusai_lib.integrations.payments.checkout`
(`make_hosted_checkout`, `CheckoutRequest`) and
`noctusai_lib.integrations.payments.types.Money` VERBATIM — no new
gateway adapter. Cloudflare Turnstile via this session's seed lift,
`noctusai_lib.integrations.turnstile` (see `KB § INTEGRATIONS/turnstile.md`).

CPF (product decision P1) is validated shape-only in
`schemas/checkout.py` and passed straight through as
`CheckoutRequest.tax_id` — it is NEVER read back off `payload` again
after that call and NEVER written to any table this service touches
(`membros`, `assinaturas`, `pagamentos`) or logged.

Amendment A10's "reuse an existing iniciada subscription... instead of
creating another gateway object" is implemented for ASAAS ONLY, not
Stripe: `AsaasPaymentGateway.create_subscription` is NOT idempotent (a
second call creates a second Asaas subscription and, per the contract's
own wording, "Asaas bills per issued Pix/boleto"), while a Stripe
Checkout Session costs nothing to recreate and is not billed until the
payer completes it — the seed's `HostedCheckout` Protocol also exposes
no "retrieve an existing session's URL" verb (Stripe's Checkout Session
id is not even persisted anywhere on the `assinaturas` row until the
payer completes it), so a genuine "return the same checkout_url" replay
is not achievable for Stripe without a seed enhancement. See
`drift-found:` in this slice's delivery note.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.payments import PaymentGatewayError
from noctusai_lib.integrations.payments.checkout import (
    CheckoutRequest,
    CheckoutSession,
    HostedCheckout,
    make_hosted_checkout,
)
from noctusai_lib.integrations.payments.types import Money
from noctusai_lib.integrations.turnstile import TurnstileVerifier, make_turnstile_verifier

from app.config import settings

logger = logging.getLogger(__name__)

_MEMBROS_TABLE = "membros"
_PLANOS_TABLE = "planos"
_GATEWAY_REFS_TABLE = "plano_gateway_refs"
_ASSINATURAS_TABLE = "assinaturas"
_PAGAMENTOS_TABLE = "pagamentos"

_METODO_GATEWAY = {"cartao": "stripe", "pix": "asaas", "boleto": "asaas"}
_METODO_BILLING_METHOD = {"cartao": "card", "pix": "pix", "boleto": "boleto"}


class CheckoutServiceError(Exception):
    """Domain-level failure surfaced to the router as an HTTP error."""

    def __init__(self, detail: str, *, status_code: int = 502) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _default_hosted_checkout_factory(gateway: str) -> HostedCheckout:
    """Build the `HostedCheckout` for `gateway` from configured settings.

    An empty api key routes to `FakeHostedCheckout` — mirrors
    `make_hosted_checkout`'s own `use_fake` early-dev posture, so a
    fresh clone's tests (and a not-yet-configured deploy) never need
    real Stripe/Asaas credentials to boot.
    """
    if gateway == "stripe":
        if not settings.stripe_secret_key:
            return make_hosted_checkout(use_fake=True)
        return make_hosted_checkout(provider="stripe", stripe_api_key=settings.stripe_secret_key)
    if not settings.asaas_api_key:
        return make_hosted_checkout(use_fake=True)
    return make_hosted_checkout(
        provider="asaas",
        asaas_api_key=settings.asaas_api_key,
        asaas_base_url=settings.asaas_base_url,
    )


def _default_turnstile_verifier() -> TurnstileVerifier:
    return make_turnstile_verifier(secret=settings.community_turnstile_secret or None)


def _parse_asaas_date_or_none(value: Any) -> Optional[str]:
    """Asaas' `dueDate` is `YYYY-MM-DD` — store as a UTC-midnight ISO-8601
    timestamp, or `None` for anything unparseable (never raises)."""
    if not value:
        return None
    try:
        return (
            datetime.strptime(str(value), "%Y-%m-%d")
            .replace(tzinfo=timezone.utc)
            .isoformat()
        )
    except (TypeError, ValueError):
        return None


class CheckoutService:
    def __init__(
        self,
        client: Any,
        *,
        org_id: UUID,
        hosted_checkout_factory: Optional[Callable[[str], HostedCheckout]] = None,
        turnstile_verifier: Optional[TurnstileVerifier] = None,
        reuse_window_minutes: Optional[int] = None,
        max_per_email_per_24h: Optional[int] = None,
        max_per_org_per_hour: Optional[int] = None,
    ) -> None:
        self._client = client
        self._org_id = str(org_id)
        self._hosted_checkout_factory = hosted_checkout_factory or _default_hosted_checkout_factory
        self._turnstile = turnstile_verifier or _default_turnstile_verifier()
        # Config values read HERE (constructor time), not per-call — the
        # DI seam a test uses to exercise the abuse-cap branches with a
        # small cap, without monkeypatching `app.config.settings`
        # (KB § PATTERNS/backend/di-test-seam.md).
        self._reuse_window_minutes = (
            reuse_window_minutes if reuse_window_minutes is not None
            else settings.checkout_reuse_window_minutes
        )
        self._max_per_email_per_24h = (
            max_per_email_per_24h if max_per_email_per_24h is not None
            else settings.checkout_max_per_email_per_24h
        )
        self._max_per_org_per_hour = (
            max_per_org_per_hour if max_per_org_per_hour is not None
            else settings.checkout_max_per_org_per_hour
        )

    async def checkout(self, *, payload: dict, remote_ip: Optional[str] = None) -> dict:
        # 1. Turnstile (product decision P2) — before ANY DB read/write
        # or gateway call. A missing token is `payload.get(...)` → None
        # → treated identically to an empty string by the verifier.
        token = payload.get("turnstile_token") or ""
        verification = await self._turnstile.verify(token, remote_ip=remote_ip)
        if not verification.success:
            raise CheckoutServiceError(
                "Verificação de segurança falhou. Recarregue a página e tente novamente.",
                status_code=403,
            )

        metodo = payload["metodo"]
        gateway = _METODO_GATEWAY[metodo]
        plano_id = str(payload["plano_id"])
        email = payload["email"]

        # 2. Plan + gateway ref — about the PLAN, never the email; safe
        # to fail loud before any membership check (amendment A2 only
        # forbids varying behavior on EMAIL existence, not plan_id).
        plano = self._fetch_active_plano(plano_id)
        if not plano:
            raise CheckoutServiceError("Plano não encontrado.", status_code=404)
        ref = self._fetch_gateway_ref(plano_id, gateway)
        if not ref:
            raise CheckoutServiceError(
                "Este plano ainda não está disponível para esse meio de pagamento.",
                status_code=409,
            )

        # 3. Per-org/hour cap (amendment A10) — org-wide, checked before
        # touching the membros table at all.
        self._check_org_cap()

        # 4. Find-or-create membro (amendments A1/A3): the FOUND branch
        # writes NOTHING to `membros` — not nome, not telefone, not
        # plano_id, not status. Submitted nome/telefone are used ONLY
        # for the gateway customer payload below.
        membro = self._find_or_create_membro(payload)
        self._check_email_cap(membro["id"])

        # Amendment A2: an already-`ativo` email gets the SAME status
        # code and body SHAPE as anyone else — no gateway call, no
        # second real subscription, `checkout_url` is None, and `status`
        # explains what happened (the real explanation goes out-of-band
        # by email, per the contract).
        if membro.get("status") == "ativo":
            assinatura_id = self._insert_assinatura_row(
                membro_id=membro["id"], plano_id=plano_id, gateway=gateway,
                metodo=metodo, ciclo=plano["ciclo"],
                assinatura_externa_id=None, cliente_externo_id=None,
            )
            return {
                "checkout_url": None, "assinatura_id": assinatura_id,
                "membro_id": membro["id"], "pix_qr": None,
                "status": "verifique_seu_email",
            }

        # Amendment A10, Asaas-only leg (see this module's docstring for
        # why Stripe is exempt): reuse a recent `iniciada` subscription
        # instead of creating a second real Asaas subscription.
        if gateway == "asaas":
            reusable = self._find_reusable_assinatura(
                membro_id=membro["id"], plano_id=plano_id, gateway=gateway, metodo=metodo,
            )
            if reusable:
                return {
                    "checkout_url": None, "assinatura_id": reusable["id"],
                    "membro_id": membro["id"], "pix_qr": None,
                    "status": "checkout_em_andamento",
                }

        # 5. Mint the local row's id FIRST so it can travel as the
        # gateway's `external_reference` — the conciliation key
        # `webhooks_service.py` resolves by. This is the ONLY reliable
        # key for a Stripe FIRST payment: Stripe has no subscription id
        # at all until the payer completes the hosted page (amendment A1).
        assinatura_id = str(uuid4())
        hosted_checkout = self._hosted_checkout_factory(gateway)
        request = CheckoutRequest(
            external_reference=assinatura_id,
            email=email,
            name=payload["nome"],
            price=Money(plano["preco_centavos"], "BRL"),
            billing_cycle="monthly" if plano["ciclo"] == "mensal" else "yearly",
            billing_method=_METODO_BILLING_METHOD[metodo],
            # Stripe REQUIRES a pre-created Price id; Asaas ignores
            # plan_ref entirely (it has no first-class price catalog —
            # see `noctusai_lib.integrations.payments.checkout`'s module
            # docstring). The `plano_gateway_refs` row still gates
            # AVAILABILITY for both gateways (§Gateway refs) even though
            # only Stripe's `ref_externo` value is forwarded to the
            # gateway call.
            plan_ref=ref["ref_externo"] if gateway == "stripe" else None,
            success_url=f"{settings.frontend_base_url}/assinar?status=sucesso" if gateway == "stripe" else None,
            cancel_url=f"{settings.frontend_base_url}/assinar?status=cancelado" if gateway == "stripe" else None,
            tax_id=payload.get("cpf"),
        )
        try:
            session = hosted_checkout.create_checkout(request)
        except PaymentGatewayError as exc:
            logger.error("checkout: gateway call failed (gateway=%s): %s", gateway, exc)
            raise CheckoutServiceError(
                "O provedor de pagamento não respondeu. Tente novamente.", status_code=502,
            ) from exc

        self._insert_assinatura_row(
            row_id=assinatura_id, membro_id=membro["id"], plano_id=plano_id,
            gateway=gateway, metodo=metodo, ciclo=plano["ciclo"],
            assinatura_externa_id=session.subscription_id_at_gateway,
            cliente_externo_id=session.customer_id_at_gateway,
        )

        pix_qr_out = None
        if gateway == "asaas":
            self._create_initial_pagamento(
                session=session, membro_id=membro["id"], assinatura_id=assinatura_id,
                gateway=gateway, metodo=metodo, valor_centavos=plano["preco_centavos"],
            )
            if session.pix_qr:
                pix_qr_out = {
                    "payload": session.pix_qr.payload,
                    "imagem_base64": session.pix_qr.encoded_image,
                    "expira_em": session.pix_qr.expiration_date,
                }

        return {
            "checkout_url": session.checkout_url, "assinatura_id": assinatura_id,
            "membro_id": membro["id"], "pix_qr": pix_qr_out, "status": None,
        }

    # ── reads ────────────────────────────────────────────────────────

    def _fetch_active_plano(self, plano_id: str) -> Optional[dict]:
        row = (
            self._client.table(_PLANOS_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("id", plano_id)
            .maybe_single()
            .execute()
        ).data
        if not row or not row.get("ativo"):
            return None
        return row

    def _fetch_gateway_ref(self, plano_id: str, gateway: str) -> Optional[dict]:
        return (
            self._client.table(_GATEWAY_REFS_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("plano_id", plano_id)
            .eq("gateway", gateway)
            .maybe_single()
            .execute()
        ).data

    def _find_reusable_assinatura(
        self, *, membro_id: str, plano_id: str, gateway: str, metodo: str,
    ) -> Optional[dict]:
        cutoff = (
            datetime.now(timezone.utc)
            - timedelta(minutes=self._reuse_window_minutes)
        ).isoformat()
        rows = (
            self._client.table(_ASSINATURAS_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("membro_id", membro_id)
            .eq("plano_id", plano_id)
            .eq("gateway", gateway)
            .eq("metodo", metodo)
            .eq("estado", "iniciada")
            .execute()
            .data
            or []
        )
        candidates = [
            r for r in rows
            if r.get("assinatura_externa_id") and (r.get("created_at") or "") >= cutoff
        ]
        candidates.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        return candidates[0] if candidates else None

    # ── abuse caps (amendment A10) — config values, never literals ────

    def _check_org_cap(self) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        rows = (
            self._client.table(_ASSINATURAS_TABLE)
            .select("id,created_at")
            .eq("org_id", self._org_id)
            .execute()
            .data
            or []
        )
        recent = [r for r in rows if (r.get("created_at") or "") >= cutoff]
        if len(recent) >= self._max_per_org_per_hour:
            raise CheckoutServiceError(
                "Muitas tentativas de assinatura. Tente novamente mais tarde.",
                status_code=429,
            )

    def _check_email_cap(self, membro_id: str) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        rows = (
            self._client.table(_ASSINATURAS_TABLE)
            .select("id,created_at")
            .eq("org_id", self._org_id)
            .eq("membro_id", membro_id)
            .execute()
            .data
            or []
        )
        recent = [r for r in rows if (r.get("created_at") or "") >= cutoff]
        if len(recent) >= self._max_per_email_per_24h:
            raise CheckoutServiceError(
                "Muitas tentativas de assinatura. Tente novamente mais tarde.",
                status_code=429,
            )

    # ── writes ───────────────────────────────────────────────────────

    def _find_or_create_membro(self, payload: dict) -> dict:
        email = payload["email"]
        existing = (
            self._client.table(_MEMBROS_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("email", email)
            .execute()
            .data
            or []
        )
        if existing:
            # Amendment A3: the found branch writes NOTHING. Return the
            # row exactly as stored.
            return existing[0]
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "id": str(uuid4()), "org_id": self._org_id, "nome": payload["nome"],
            "email": email, "telefone": payload.get("telefone"), "status": "pendente",
            "plano_id": None, "origem": "checkout", "tags": [], "observacoes": None,
            "entrou_em": None, "created_at": now, "updated_at": now,
        }
        result = self._client.table(_MEMBROS_TABLE).insert(row).execute()
        if not result.data:
            raise CheckoutServiceError("Falha ao registrar associada.")
        return result.data[0]

    def _insert_assinatura_row(
        self,
        *,
        membro_id: str,
        plano_id: str,
        gateway: str,
        metodo: str,
        ciclo: str,
        assinatura_externa_id: Optional[str],
        cliente_externo_id: Optional[str],
        row_id: Optional[str] = None,
    ) -> str:
        now = datetime.now(timezone.utc).isoformat()
        row_id = row_id or str(uuid4())
        row = {
            "id": row_id, "org_id": self._org_id, "membro_id": membro_id,
            "plano_id": plano_id, "gateway": gateway,
            "assinatura_externa_id": assinatura_externa_id,
            "cliente_externo_id": cliente_externo_id,
            "estado": "iniciada", "metodo": metodo, "ciclo": ciclo,
            "iniciada_em": now, "created_at": now, "updated_at": now,
        }
        result = self._client.table(_ASSINATURAS_TABLE).insert(row).execute()
        if not result.data:
            raise CheckoutServiceError("Falha ao registrar assinatura.")
        return result.data[0]["id"]

    def _create_initial_pagamento(
        self,
        *,
        session: CheckoutSession,
        membro_id: str,
        assinatura_id: str,
        gateway: str,
        metodo: str,
        valor_centavos: int,
    ) -> None:
        """Persist the Asaas first-generated payment's Pix/boleto data at
        CHECKOUT time — the ONLY point this service ever sees
        `session.pix_qr`; a later webhook cannot recover it (see
        amendment A11: `pix_imagem_base64` is nulled once `estado='pago'`,
        which `webhooks_service.py` does when this SAME row is updated).
        """
        payment_raw = (session.raw or {}).get("payment") or {}
        cobranca_id = payment_raw.get("id")
        if not cobranca_id:
            logger.warning(
                "checkout: asaas session had no first-payment id; "
                "no pagamentos row created at checkout time (assinatura_id=%s)",
                assinatura_id,
            )
            return
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "id": str(uuid4()), "org_id": self._org_id, "assinatura_id": assinatura_id,
            "membro_id": membro_id, "gateway": gateway, "cobranca_externa_id": str(cobranca_id),
            "valor_centavos": valor_centavos, "metodo": metodo, "estado": "pendente",
            "vencimento": _parse_asaas_date_or_none(payment_raw.get("dueDate")),
            "url_fatura": session.checkout_url,
            "pix_payload": session.pix_qr.payload if session.pix_qr else None,
            "pix_imagem_base64": session.pix_qr.encoded_image if session.pix_qr else None,
            "created_at": now, "updated_at": now,
        }
        self._client.table(_PAGAMENTOS_TABLE).insert(row).execute()
