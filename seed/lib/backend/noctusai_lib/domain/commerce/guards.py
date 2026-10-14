"""Behaviour probes for the commerce organ's money + fiscal migration deltas (see `noctusai_lib.domain._organ_common.guards`)."""
from __future__ import annotations

from noctusai_lib.domain._organ_common.guards import OrganGuardProbe

_DECLARE = "v_cust uuid; v_order uuid; v_charge uuid;"
_ORDER_TABLES = ("commerce_customers", "commerce_orders")


def _order(s: str, status: str = "created") -> str:
    return (
        f"INSERT INTO {s}.commerce_customers (org_id, email) VALUES (v_org, 'noc-probe@example.invalid') RETURNING id INTO v_cust;\n"
        f"INSERT INTO {s}.commerce_orders (org_id, token, customer_id, status, subtotal_cents, total_cents, payment_method, gateway) "
        f"VALUES (v_org, 'noc-probe-' || gen_random_uuid()::text, v_cust, '{status}', 100, 100, 'pix', 'noc') RETURNING id INTO v_order;\n"
    )


def _charge(s: str, attempt: int, gw_id: str, into: str = "") -> str:
    ret = f" RETURNING id INTO {into}" if into else ""
    return (
        f"INSERT INTO {s}.commerce_order_charges (org_id, order_id, attempt, gateway, gateway_charge_id, payment_method, amount_cents) "
        f"VALUES (v_org, v_order, {attempt}, 'noc', '{gw_id}', 'pix', 100){ret};\n"
    )


def _refund(s: str, status: str, extra_cols: str = "", extra_vals: str = "") -> str:
    done = ", done_at" if status == "done" else ""
    done_v = ", now()" if status == "done" else ""
    return (
        f"INSERT INTO {s}.commerce_refunds (org_id, order_id, charge_id, amount_cents, status{done}{extra_cols}) "
        f"VALUES (v_org, v_order, v_charge, 10, '{status}'{done_v}{extra_vals});\n"
    )


def commerce_money_guard_probes(schema: str) -> tuple[OrganGuardProbe, ...]:
    s = schema
    refund_tables = (*_ORDER_TABLES, "commerce_order_charges", "commerce_refunds")
    return (
        OrganGuardProbe(
            guard_name="commerce_orders_status_check",
            kind="check",
            requires=_ORDER_TABLES,
            declare=_DECLARE,
            body=_order(s, "noc_invalid"),
            permitted="an order with a status outside the order state machine",
            rationale="Order status is a closed vocabulary (P4 widened it): a typo'd status would strand an order outside every transition.",
        ),
        OrganGuardProbe(
            guard_name="commerce_order_events_from_status_check",
            kind="check",
            requires=(*_ORDER_TABLES, "commerce_order_events"),
            declare=_DECLARE,
            body=(
                _order(s)
                + f"INSERT INTO {s}.commerce_order_events (org_id, order_id, from_status, to_status, source) "
                "VALUES (v_org, v_order, 'noc_invalid', 'paid', 'system');"
            ),
            permitted="an order event leaving a status outside the state machine",
            rationale="The order event log only records real states: its from_status shares the order status vocabulary.",
        ),
        OrganGuardProbe(
            guard_name="commerce_order_events_to_status_check",
            kind="check",
            requires=(*_ORDER_TABLES, "commerce_order_events"),
            declare=_DECLARE,
            body=(
                _order(s)
                + f"INSERT INTO {s}.commerce_order_events (org_id, order_id, to_status, source) "
                "VALUES (v_org, v_order, 'noc_invalid', 'system');"
            ),
            permitted="an order event entering a status outside the state machine",
            rationale="The order event log only records real states: its to_status shares the order status vocabulary.",
        ),
        OrganGuardProbe(
            guard_name="uq_commerce_order_charges_attempt",
            kind="unique",
            requires=(*_ORDER_TABLES, "commerce_order_charges"),
            declare=_DECLARE,
            body=_order(s) + _charge(s, 1, "noc-ch-a") + _charge(s, 1, "noc-ch-b"),
            permitted="two charges for the same attempt number of one order",
            rationale="One charge per (order, attempt): a double-clicked regenerate must not create two live charges.",
        ),
        OrganGuardProbe(
            guard_name="uq_commerce_order_charges_gateway",
            kind="unique",
            requires=(*_ORDER_TABLES, "commerce_order_charges"),
            declare=_DECLARE,
            body=_order(s) + _charge(s, 1, "noc-ch-same") + _charge(s, 2, "noc-ch-same"),
            permitted="two charges sharing one gateway charge id",
            rationale="A gateway charge id belongs to exactly one charge row: a webhook resolves its order through it.",
        ),
        OrganGuardProbe(
            guard_name="uq_commerce_refunds_gateway_id",
            kind="unique",
            requires=refund_tables,
            declare=_DECLARE,
            body=(
                _order(s) + _charge(s, 1, "noc-ch-a", "v_charge")
                + _refund(s, "done", ", gateway_refund_id", ", 'noc-rf'")
                + _refund(s, "done", ", gateway_refund_id", ", 'noc-rf'")
            ),
            permitted="two refunds sharing one gateway refund id",
            rationale="A gateway refund id is recorded once: a replayed refund webhook must not refund the order twice.",
        ),
        OrganGuardProbe(
            guard_name="uq_commerce_refunds_idempotency",
            kind="unique",
            requires=refund_tables,
            declare=_DECLARE,
            body=(
                _order(s) + _charge(s, 1, "noc-ch-a", "v_charge")
                + _refund(s, "done", ", idempotency_key", ", 'noc-idem'")
                + _refund(s, "done", ", idempotency_key", ", 'noc-idem'")
            ),
            permitted="two refunds with the same idempotency key on one order",
            rationale="A retried refund request (same idempotency key) is a replay, never a second refund.",
        ),
        OrganGuardProbe(
            guard_name="uq_commerce_refunds_one_requested",
            kind="unique",
            requires=refund_tables,
            declare=_DECLARE,
            body=_order(s) + _charge(s, 1, "noc-ch-a", "v_charge") + _refund(s, "requested") + _refund(s, "requested"),
            permitted="two in-flight refunds on one order",
            rationale="At most one refund is in flight per order: the DB backstop of the refund RPC's own check.",
        ),
    )


def commerce_fiscal_guard_probes(schema: str) -> tuple[OrganGuardProbe, ...]:
    s = schema
    return (
        OrganGuardProbe(
            guard_name="commerce_store_profiles_nfse_regime_ck",
            kind="check",
            requires=("commerce_store_profiles",),
            body=(
                f"INSERT INTO {s}.commerce_store_profiles (org_id, legal_name, trade_name, cnpj, tax_regime, nfse_mode) "
                "VALUES (v_org, 'noc probe', 'noc probe', '00000000000000', 'simples', 'municipal');"
            ),
            permitted="a Simples store configured for municipal NFS-e",
            rationale="D37: a Simples/MEI store must issue NFS-e through the national emitter; a municipal mode is unrepresentable.",
        ),
    )
