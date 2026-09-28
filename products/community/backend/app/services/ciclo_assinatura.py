"""Billing lifecycle primitives — CONTRACT.md §Billing lifecycle (Asaas).

One home for what the webhooks, the cancellation paths and the billing
sweep all need, so none of them re-derives it:

* the pt-BR `assinaturas.estado` ↔ seed `SubscriptionState` mapping, and
  `validar_transicao`, which runs every requested move (or path of moves)
  through the seed's `noctusai_lib.domain.payments.subscription.transition`
  — the ONLY legality check. An illegal move raises `TransicaoIlegal`; the
  caller logs/reports it and writes nothing.
* date math for `pago_ate` / `proxima_cobranca` (calendar-aware +1 cycle,
  America/Sao_Paulo day boundaries, stored as UTC ISO strings so string
  comparisons in tests and timestamptz comparisons in Postgres agree).
* the per-org billing settings row (`configuracoes_cobranca`, created on
  first read with the contract defaults).
* "the free plan" (active, `preco_centavos = 0`, lowest `ordem`).
* a STRICT gateway factory for the paths this slice adds: a missing key
  raises `GatewayNaoConfigurado` instead of silently falling back to the
  Fake gateway (a Fake "success" would stop nothing at Asaas while the
  local row says it did).
"""
from __future__ import annotations

import calendar
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from noctusai_lib.domain.payments import Subscription, SubscriptionState, transition
from noctusai_lib.integrations.payments import PaymentGatewayError, make_payment_gateway
from noctusai_lib.security.api_keys import resolve_api_key
from postgrest.exceptions import APIError

from app.config import settings

logger = logging.getLogger(__name__)

FUSO_HORARIO = ZoneInfo("America/Sao_Paulo")

_CONFIG_TABLE = "configuracoes_cobranca"
_PLANOS_TABLE = "planos"

DIAS_CARENCIA_PADRAO = 5

#: CONTRACT.md §Billing lifecycle — seed mapping. `pausada` is deliberately
#: absent: it is a manager-only state outside the seed machine (module 2,
#: amendment A8), so no automated move goes into or out of it.
ESTADO_PARA_SEED: dict[str, SubscriptionState] = {
    "iniciada": SubscriptionState.INCOMPLETE,
    "ativa": SubscriptionState.ACTIVE,
    "inadimplente": SubscriptionState.PAST_DUE,
    "carencia": SubscriptionState.GRACE,
    "cancelada": SubscriptionState.CANCELED,
    "expirada": SubscriptionState.EXPIRED,
}

#: Reverse mapping. TRIALING has no pt-BR state of its own (Stripe only;
#: this product never starts a trial) and folds into `iniciada`.
SEED_PARA_ESTADO: dict[SubscriptionState, str] = {
    **{seed: estado for estado, seed in ESTADO_PARA_SEED.items()},
    SubscriptionState.TRIALING: "iniciada",
}

#: Subscriptions whose charges still run at the gateway ("current paid
#: subscription" for the member portal's cancel).
ESTADOS_EM_COBRANCA = ("ativa", "inadimplente", "carencia")

#: Subscriptions a paid plan change REPLACES (CONTRACT.md §Billing
#: lifecycle): the ones still billing plus an `iniciada` one whose first
#: Pix/boleto is still open at the gateway.
ESTADOS_VIVOS = ("iniciada", *ESTADOS_EM_COBRANCA)


class TransicaoIlegal(ValueError):
    """A requested estado move the seed state machine refuses."""

    def __init__(self, *, assinatura_id: Any, atual: Optional[str], alvo: str) -> None:
        self.assinatura_id = str(assinatura_id)
        self.atual = atual
        self.alvo = alvo
        super().__init__(
            f"transição ilegal {atual} → {alvo} (assinatura {assinatura_id})"
        )


class GatewayNaoConfigurado(RuntimeError):
    """No API key resolves for the gateway this subscription lives on."""


def validar_transicao(assinatura: dict, *alvos: str, now: datetime) -> None:
    """Validate `assinatura.estado → alvos[0] → alvos[1] → …` with the seed.

    Each hop goes through `transition`; the first refused hop raises
    `TransicaoIlegal`. A current estado outside the seed mapping
    (`pausada`, or anything unknown) is itself illegal to move
    automatically.
    """
    atual = assinatura.get("estado")
    estado_seed = ESTADO_PARA_SEED.get(atual)
    if estado_seed is None:
        raise TransicaoIlegal(
            assinatura_id=assinatura.get("id"), atual=atual, alvo=alvos[0] if alvos else "?",
        )
    snapshot = Subscription(
        id=str(assinatura.get("id")),
        external_reference=str(assinatura.get("id")),
        gateway=str(assinatura.get("gateway") or ""),
        id_at_gateway=assinatura.get("assinatura_externa_id") or "",
        state=estado_seed,
        created_at=now,
        updated_at=now,
    )
    for alvo in alvos:
        try:
            snapshot = transition(snapshot, ESTADO_PARA_SEED[alvo], now=now)
        except (ValueError, KeyError) as exc:
            raise TransicaoIlegal(
                assinatura_id=assinatura.get("id"),
                atual=SEED_PARA_ESTADO.get(snapshot.state, atual),
                alvo=alvo,
            ) from exc


# ── dates ──────────────────────────────────────────────────────────────


def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    """UTC ISO-8601 — one textual format for every timestamp this slice writes."""
    return dt.astimezone(timezone.utc).isoformat()


def ler_timestamp(value: Any) -> Optional[datetime]:
    """Parse a timestamptz as PostgREST returns it (or as tests seed it)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            logger.error("ciclo_assinatura: timestamp ilegível %r", value)
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def ler_data(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        logger.error("ciclo_assinatura: data ilegível %r", value)
        return None


def hoje_local(now: datetime) -> date:
    return now.astimezone(FUSO_HORARIO).date()


def inicio_do_dia(d: date) -> datetime:
    """00:00 America/Sao_Paulo on `d`, as an aware datetime."""
    return datetime.combine(d, time.min, tzinfo=FUSO_HORARIO)


def somar_ciclo(d: date, ciclo: str) -> date:
    """`d` + one billing cycle, clamping the day (31 Jan + 1 month = 28/29 Feb)."""
    if ciclo == "anual":
        year, month = d.year + 1, d.month
    else:
        year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def formatar_data(dt: datetime | date) -> str:
    if isinstance(dt, datetime):
        dt = dt.astimezone(FUSO_HORARIO).date()
    return dt.strftime("%d/%m/%Y")


def formatar_reais(centavos: int) -> str:
    reais, cents = divmod(int(centavos), 100)
    return f"R$ {reais:,}".replace(",", ".") + f",{cents:02d}"


# ── settings row ───────────────────────────────────────────────────────


def ler_configuracoes(client: Any, org_id: Any) -> dict:
    """The org's `configuracoes_cobranca` row, created with the defaults
    (5 days of grace, automations on) on first read."""
    org = str(org_id)
    rows = (
        client.table(_CONFIG_TABLE).select("*").eq("org_id", org).limit(1).execute().data
        or []
    )
    if rows:
        return rows[0]
    padrao = {"org_id": org, "dias_carencia": DIAS_CARENCIA_PADRAO, "automacoes_ativas": True}
    try:
        written = client.table(_CONFIG_TABLE).insert(padrao).execute().data or []
    except APIError as exc:
        if exc.code != "23505":
            raise
        # A concurrent first read created it between our select and insert.
        logger.info("ciclo_assinatura: configuracoes_cobranca criada em paralelo (org=%s)", org)
        rows = (
            client.table(_CONFIG_TABLE).select("*").eq("org_id", org).limit(1).execute().data
            or []
        )
        return rows[0] if rows else padrao
    return written[0] if written else padrao


def calcular_carencia_ate(inadimplente_desde: datetime, dias_carencia: int) -> datetime:
    return inadimplente_desde + timedelta(days=int(dias_carencia))


# ── free plan ──────────────────────────────────────────────────────────


def plano_gratuito(client: Any, org_id: Any) -> Optional[dict]:
    """CONTRACT.md §Tiers: the active plan with `preco_centavos = 0` and the
    lowest `ordem`; None when the org has none."""
    rows = (
        client.table(_PLANOS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("ativo", True)
        .eq("preco_centavos", 0)
        .execute()
        .data
        or []
    )
    if not rows:
        return None
    rows.sort(key=lambda r: (r.get("ordem") or 0, r.get("nome") or ""))
    return rows[0]


# ── strict gateway factory ─────────────────────────────────────────────


def gateway_estrito(gateway: str, *, org_id: str):
    """Headless `PaymentGateway` for `gateway`, or `GatewayNaoConfigurado`.

    Same key resolution as `assinaturas_service._default_gateway_factory`
    (org-scoped `community.credentials` first, then the env fallback), minus
    its Fake-on-miss branch.
    """
    if gateway == "stripe":
        key = resolve_api_key("stripe_secret_key", org_id)
        if not key:
            raise GatewayNaoConfigurado("Chave da Stripe não configurada.")
        return make_payment_gateway(provider="stripe", stripe_api_key=key)
    if gateway == "asaas":
        key = resolve_api_key("asaas_api_key", org_id)
        if not key:
            raise GatewayNaoConfigurado("Chave do Asaas não configurada.")
        return make_payment_gateway(
            provider="asaas", asaas_api_key=key, asaas_base_url=settings.asaas_base_url,
        )
    raise GatewayNaoConfigurado(f"Gateway desconhecido: {gateway!r}.")


def cancelar_no_gateway(assinatura: dict, gateway_factory: Callable[[str], Any]) -> Optional[str]:
    """Stop the subscription's future charges at its gateway.

    Returns None on success (or when no gateway object exists — the A2/A10
    shortcut rows never reached one), else an error text for the caller to
    report and to flag `gateway_cancelamento_pendente` with; the billing
    sweep retries every flagged row. Never raises for a gateway refusal or
    a missing key — both are "pending", never a silent success.
    """
    externa = assinatura.get("assinatura_externa_id")
    if not externa:
        return None
    try:
        gateway_factory(assinatura["gateway"]).cancel_subscription(externa)
    except (PaymentGatewayError, GatewayNaoConfigurado) as exc:
        logger.error(
            "ciclo_assinatura: gateway cancel failed for assinatura_id=%s gateway=%s: %s",
            assinatura["id"], assinatura.get("gateway"), exc,
        )
        return f"{assinatura['id']}: cancelamento no gateway falhou: {exc}"
    return None


def marcar_cancelamento_pendente(
    client: Any, org_id: Any, assinatura_id: Any, pendente: bool,
) -> None:
    """Set/clear `gateway_cancelamento_pendente` (the sweep's retry flag)."""
    client.table("assinaturas").update({"gateway_cancelamento_pendente": pendente}).eq(
        "org_id", str(org_id)
    ).eq("id", str(assinatura_id)).execute()


__all__ = [
    "DIAS_CARENCIA_PADRAO",
    "ESTADOS_EM_COBRANCA",
    "ESTADOS_VIVOS",
    "ESTADO_PARA_SEED",
    "FUSO_HORARIO",
    "GatewayNaoConfigurado",
    "SEED_PARA_ESTADO",
    "TransicaoIlegal",
    "agora_utc",
    "calcular_carencia_ate",
    "cancelar_no_gateway",
    "formatar_data",
    "formatar_reais",
    "gateway_estrito",
    "hoje_local",
    "inicio_do_dia",
    "iso",
    "ler_configuracoes",
    "ler_data",
    "ler_timestamp",
    "marcar_cancelamento_pendente",
    "plano_gratuito",
    "somar_ciclo",
    "validar_transicao",
]
