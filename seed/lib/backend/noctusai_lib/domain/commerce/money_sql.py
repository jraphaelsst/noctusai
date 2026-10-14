"""`commerce_money_migration(cfg, schema)` -- the P4 money-state DDL, as a DELTA over `commerce_migration`.

CONTRACT §2.3. A separate generator on purpose: `commerce_migration`'s output is what a
host's already-applied `012_commerce.sql` is pinned to (`never edit 012`), so the P4
additions are rendered into a NEW host migration from here instead -- the host applies
`commerce_money_migration(cfg, schema)` after the base migration. Prerequisite: the
base tables exist (`CREATE TABLE IF NOT EXISTS` is not enough for the columns added to
`commerce_orders` / `commerce_store_profiles`, which are guarded `ADD COLUMN IF NOT EXISTS`).

What it adds:

* tables `commerce_order_charges` (one row per charge attempt), `commerce_refunds`,
  `commerce_order_reminders` -- org-scoped, RLS on, same policy shape as the base tables;
* `commerce_orders.charge_attempts` / `last_charge_attempt_at` -- the atomic regenerate-
  payment claim is ONE conditional UPDATE over them (status + attempt + cap + spacing),
  so two concurrent regenerations cannot both create a charge;
* `commerce_store_profiles.installments_max` / `installments_interest_free` /
  `installment_interest_monthly_bps` (D33/D41);
* the `partially_refunded` / `disputed` order statuses (the status CHECKs are replaced);
* the `commerce_create_refund` RPC: `SELECT ... FOR UPDATE` on the order, the refundable
  balance recomputed SERVER-SIDE from the paid charge minus the non-failed refunds, one
  `requested` refund at a time, idempotent on the caller's key. SECURITY DEFINER with
  EXECUTE revoked from everyone but `service_role`.

Forward-only and idempotent (the chain replay applies a new file twice). Money is
`BIGINT` cents (CONTRACT W5); every unique is org-scoped.
"""
from __future__ import annotations

from noctusai_lib.domain.sql_templates import set_search_path

from .config import CommerceConfig
from .sql import _in, _section
from .types import ChargeAttemptStatus, OrderStatus, PaymentMethod, ReminderKind, RefundStatus

#: The tables this delta creates, in dependency order. The generator + isolation tests iterate it.
COMMERCE_MONEY_TABLES: tuple[str, ...] = (
    "commerce_order_charges",
    "commerce_refunds",
    "commerce_order_reminders",
)

#: Attempts per order and the gap between two of them are enforced in the claim UPDATE
#: (`orders`/`regenerate`); the DB only needs the column.
CREATE_REFUND_RPC = "commerce_create_refund"


def _status_checks(s: str) -> str:
    """Replace the status CHECKs so `partially_refunded` / `disputed` are legal (drop-then-add)."""
    statuses = _in(OrderStatus)
    return "\n".join(
        [
            "-- Order statuses grow by two (P4): replace the CHECKs (drop-then-add is idempotent).",
            f"ALTER TABLE {s}.commerce_orders DROP CONSTRAINT IF EXISTS commerce_orders_status_check;",
            f"ALTER TABLE {s}.commerce_orders ADD CONSTRAINT commerce_orders_status_check CHECK (status IN ({statuses}));",
            f"ALTER TABLE {s}.commerce_order_events DROP CONSTRAINT IF EXISTS commerce_order_events_from_status_check;",
            f"ALTER TABLE {s}.commerce_order_events ADD CONSTRAINT commerce_order_events_from_status_check "
            f"CHECK (from_status IS NULL OR from_status IN ({statuses}));",
            f"ALTER TABLE {s}.commerce_order_events DROP CONSTRAINT IF EXISTS commerce_order_events_to_status_check;",
            f"ALTER TABLE {s}.commerce_order_events ADD CONSTRAINT commerce_order_events_to_status_check "
            f"CHECK (to_status IN ({statuses}));",
        ]
    )


def _columns(s: str) -> str:
    return f"""-- Orders: the regenerate-payment claim columns (a pre-P4 order with a charge counts as attempt 1).
ALTER TABLE {s}.commerce_orders ADD COLUMN IF NOT EXISTS charge_attempts INTEGER NOT NULL DEFAULT 0 CHECK (charge_attempts >= 0);
ALTER TABLE {s}.commerce_orders ADD COLUMN IF NOT EXISTS last_charge_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now();
UPDATE {s}.commerce_orders SET charge_attempts = 1 WHERE gateway_charge_id IS NOT NULL AND charge_attempts = 0;

-- Store profile: card installments (D33). interest_monthly_bps NULL = follow the platform default (D41).
ALTER TABLE {s}.commerce_store_profiles ADD COLUMN IF NOT EXISTS installments_max INTEGER NOT NULL DEFAULT 12
    CHECK (installments_max BETWEEN 1 AND 12);
ALTER TABLE {s}.commerce_store_profiles ADD COLUMN IF NOT EXISTS installments_interest_free INTEGER NOT NULL DEFAULT 3
    CHECK (installments_interest_free >= 1 AND installments_interest_free <= installments_max);
ALTER TABLE {s}.commerce_store_profiles ADD COLUMN IF NOT EXISTS installment_interest_monthly_bps INTEGER
    CHECK (installment_interest_monthly_bps IS NULL OR installment_interest_monthly_bps BETWEEN 0 AND 2000);"""


def _tables(cfg: CommerceConfig, s: str) -> list[str]:
    o = cfg.org_id_expr
    out: list[str] = []
    out.append(
        _section(
            "Order charges: one row per charge attempt (the buyer can regenerate a payment). `amount_cents` is what was "
            "charged INCLUDING buyer interest; commerce_orders.gateway_charge_id points at the CURRENT attempt.",
            s,
            "commerce_order_charges",
            f"""
CREATE TABLE IF NOT EXISTS {s}.commerce_order_charges (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id             UUID NOT NULL,
    order_id           UUID NOT NULL REFERENCES {s}.commerce_orders(id) ON DELETE CASCADE,
    attempt            INTEGER NOT NULL CHECK (attempt >= 1),
    gateway            TEXT NOT NULL,
    gateway_charge_id  TEXT NOT NULL,
    payment_method     TEXT NOT NULL CHECK (payment_method IN ({_in(PaymentMethod)})),
    installment_count  INTEGER NOT NULL DEFAULT 1 CHECK (installment_count BETWEEN 1 AND 12),
    amount_cents       BIGINT NOT NULL CHECK (amount_cents > 0),
    status             TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ({_in(ChargeAttemptStatus)})),
    checkout_url       TEXT,
    pix_qr             JSONB,
    due_at             TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at          TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_commerce_order_charges_attempt ON {s}.commerce_order_charges (order_id, attempt);
CREATE UNIQUE INDEX IF NOT EXISTS uq_commerce_order_charges_gateway ON {s}.commerce_order_charges (org_id, gateway, gateway_charge_id);
CREATE INDEX IF NOT EXISTS idx_commerce_order_charges_org ON {s}.commerce_order_charges (org_id, order_id);
""",
            o,
        )
    )
    out.append(
        _section(
            "Refunds: requested -> done | failed. requested_by NULL = made in the gateway panel (reason 'gateway'). "
            "At most ONE requested refund per order (the DB backstop of the RPC's check); gateway_refund_id is "
            "nullable because Asaas refunds carry no id (W2).",
            s,
            "commerce_refunds",
            f"""
CREATE TABLE IF NOT EXISTS {s}.commerce_refunds (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id             UUID NOT NULL,
    order_id           UUID NOT NULL REFERENCES {s}.commerce_orders(id) ON DELETE RESTRICT,
    charge_id          UUID NOT NULL REFERENCES {s}.commerce_order_charges(id) ON DELETE RESTRICT,
    amount_cents       BIGINT NOT NULL CHECK (amount_cents > 0),
    reason             TEXT NOT NULL DEFAULT '',
    status             TEXT NOT NULL DEFAULT 'requested' CHECK (status IN ({_in(RefundStatus)})),
    gateway_refund_id  TEXT,
    idempotency_key    TEXT,
    requested_by       UUID,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    done_at            TIMESTAMPTZ,
    CHECK (status <> 'done' OR done_at IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_commerce_refunds_gateway_id ON {s}.commerce_refunds (org_id, gateway_refund_id)
    WHERE gateway_refund_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_commerce_refunds_idempotency ON {s}.commerce_refunds (order_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_commerce_refunds_one_requested ON {s}.commerce_refunds (order_id)
    WHERE status = 'requested';
CREATE INDEX IF NOT EXISTS idx_commerce_refunds_order ON {s}.commerce_refunds (order_id, created_at);
CREATE INDEX IF NOT EXISTS idx_commerce_refunds_org ON {s}.commerce_refunds (org_id);
""",
            o,
        )
    )
    out.append(
        _section(
            "Payment-recovery reminders sent per order (PK = the idempotency of the reminder job).",
            s,
            "commerce_order_reminders",
            f"""
CREATE TABLE IF NOT EXISTS {s}.commerce_order_reminders (
    order_id  UUID NOT NULL REFERENCES {s}.commerce_orders(id) ON DELETE CASCADE,
    kind      TEXT NOT NULL CHECK (kind IN ({_in(ReminderKind)})),
    org_id    UUID NOT NULL,
    sent_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (order_id, kind)
);
CREATE INDEX IF NOT EXISTS idx_commerce_order_reminders_org ON {s}.commerce_order_reminders (org_id);
""",
            o,
        )
    )
    return out


def create_refund_rpc_sql(s: str) -> str:
    """The `commerce_create_refund` function (one transaction, row-locked).

    Returns a jsonb envelope -- never raises for a business refusal -- so the caller maps
    `{status: 'refused', code: ...}` to its own errors without parsing exception text:

        {"status": "created",  "refund": {...}, "charge": {...}, "refundable_cents": n}
        {"status": "replayed", "refund": {...}}                       -- same Idempotency-Key
        {"status": "refused",  "code": "<pt-BR code>", "refundable_cents"?: n}
    """
    return f"""-- Refund creation under a row lock (CONTRACT §2.4 / D32). The order row is locked FOR UPDATE, so two
-- concurrent refunds serialize: the second sees the first's `requested` row and is refused.
CREATE OR REPLACE FUNCTION {s}.{CREATE_REFUND_RPC}(
    p_org_id          UUID,
    p_order_id        UUID,
    p_amount_cents    BIGINT,
    p_reason          TEXT,
    p_requested_by    UUID,
    p_idempotency_key TEXT
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, {s}, pg_temp
AS $fn$
DECLARE
    v_order      {s}.commerce_orders%ROWTYPE;
    v_charge     {s}.commerce_order_charges%ROWTYPE;
    v_prior      {s}.commerce_refunds%ROWTYPE;
    v_row        {s}.commerce_refunds%ROWTYPE;
    v_refunded   BIGINT;
    v_remaining  BIGINT;
    v_amount     BIGINT;
BEGIN
    SELECT * INTO v_order FROM {s}.commerce_orders WHERE id = p_order_id AND org_id = p_org_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'pedido_nao_encontrado');
    END IF;

    IF p_idempotency_key IS NOT NULL THEN
        SELECT * INTO v_prior FROM {s}.commerce_refunds WHERE order_id = p_order_id AND idempotency_key = p_idempotency_key;
        IF FOUND THEN
            RETURN jsonb_build_object('status', 'replayed', 'refund', to_jsonb(v_prior));
        END IF;
    END IF;

    IF v_order.status NOT IN ('paid', 'partially_refunded') THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'pedido_nao_reembolsavel');
    END IF;

    SELECT * INTO v_charge FROM {s}.commerce_order_charges
        WHERE order_id = p_order_id AND status = 'paid' ORDER BY attempt DESC LIMIT 1;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'cobranca_nao_encontrada');
    END IF;

    -- A card order paid in installments is several gateway payments; a single-parcela refund would leave it
    -- half-refunded. Refused here as well as in Python: the RPC must not be a way around the service.
    IF v_charge.installment_count > 1 THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'estorno_parcelado_indisponivel');
    END IF;

    IF EXISTS (SELECT 1 FROM {s}.commerce_refunds WHERE order_id = p_order_id AND status = 'requested') THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'estorno_em_andamento');
    END IF;

    SELECT COALESCE(SUM(amount_cents), 0) INTO v_refunded
        FROM {s}.commerce_refunds WHERE order_id = p_order_id AND status <> 'failed';
    v_remaining := v_charge.amount_cents - v_refunded;
    v_amount := COALESCE(p_amount_cents, v_remaining);
    IF v_amount <= 0 OR v_amount > v_remaining THEN
        RETURN jsonb_build_object('status', 'refused', 'code', 'valor_excede_saldo', 'refundable_cents', v_remaining);
    END IF;

    INSERT INTO {s}.commerce_refunds (org_id, order_id, charge_id, amount_cents, reason, status, idempotency_key, requested_by)
        VALUES (p_org_id, p_order_id, v_charge.id, v_amount, COALESCE(p_reason, ''), 'requested', p_idempotency_key, p_requested_by)
        RETURNING * INTO v_row;

    RETURN jsonb_build_object(
        'status', 'created',
        'refund', to_jsonb(v_row),
        'charge', jsonb_build_object(
            'id', v_charge.id,
            'gateway', v_charge.gateway,
            'gateway_charge_id', v_charge.gateway_charge_id,
            'amount_cents', v_charge.amount_cents,
            'installment_count', v_charge.installment_count
        ),
        'refundable_cents', v_remaining
    );
END;
$fn$;
REVOKE ALL ON FUNCTION {s}.{CREATE_REFUND_RPC}(UUID, UUID, BIGINT, TEXT, UUID, TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION {s}.{CREATE_REFUND_RPC}(UUID, UUID, BIGINT, TEXT, UUID, TEXT) TO service_role;"""


def commerce_money_migration(cfg: CommerceConfig, schema: str) -> str:
    """The P4 money-state DDL for `schema`, as one re-runnable migration body (a delta over `commerce_migration`)."""
    if not schema or not schema.strip():
        raise ValueError("commerce_money_migration requires a non-empty schema")
    sections = [
        "-- Commerce organ, P4 money states -- generated by noctusai_lib.domain.commerce.money_sql (do not hand-edit)",
        f"{set_search_path(schema)};",
        _columns(schema),
        _status_checks(schema),
        *_tables(cfg, schema),
        create_refund_rpc_sql(schema),
    ]
    return "\n\n".join(sections) + "\n"


__all__ = ["COMMERCE_MONEY_TABLES", "CREATE_REFUND_RPC", "commerce_money_migration", "create_refund_rpc_sql"]
