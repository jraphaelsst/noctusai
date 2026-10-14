"""Behaviour probes for the purchasing organ's guards (see `noctusai_lib.domain._organ_common.guards`)."""
from __future__ import annotations

from noctusai_lib.domain._organ_common.guards import OrganGuardProbe

_DECLARE = "v_order uuid;"


def _order(s: str) -> str:
    return f"INSERT INTO {s}.pur_orders (org_id, number, supplier_name) VALUES (v_org, 1, 'noc probe') RETURNING id INTO v_order;\n"


def _receipt(s: str, no: int) -> str:
    return (
        f"INSERT INTO {s}.pur_receipts (org_id, order_id, receipt_no, received_on, goods_cents, adjustment_cents, "
        f"total_cents, order_goods_before_cents, idempotency_key) "
        f"VALUES (v_org, v_order, {no}, DATE '2026-01-31', 0, 0, 0, 0, 'noc-idem');\n"
    )


def purchasing_guard_probes(schema: str) -> tuple[OrganGuardProbe, ...]:
    s = schema
    return (
        OrganGuardProbe(
            guard_name="pur_settings_log_append_only",
            kind="trigger",
            requires=("pur_settings_log",),
            fragment="pur_settings_log is append-only",
            body=(
                f"INSERT INTO {s}.pur_settings_log (org_id, kind) VALUES (v_org, 'threshold');\n"
                f"UPDATE {s}.pur_settings_log SET kind = 'approver_added' WHERE org_id = v_org;"
            ),
            permitted="an UPDATE of the approval-governance audit log",
            rationale="Who changed the approval threshold or the approver set is audit evidence: appended once, never rewritten.",
        ),
        OrganGuardProbe(
            guard_name="pur_order_lines_received_bounds",
            kind="check",
            requires=("pur_orders", "pur_order_lines"),
            declare=_DECLARE,
            body=(
                _order(s)
                + f"INSERT INTO {s}.pur_order_lines (org_id, order_id, line_no, description, qty, unit_cost_cents, line_total_cents, received_qty) "
                "VALUES (v_org, v_order, 1, 'noc probe', 1, 100, 100, 2);"
            ),
            permitted="receiving more than was ordered on a line",
            rationale="A line can never be over-received: stock and the payable are booked from received quantity.",
        ),
        OrganGuardProbe(
            guard_name="uq_pur_receipts_idem",
            kind="unique",
            requires=("pur_orders", "pur_receipts"),
            declare=_DECLARE,
            body=_order(s) + _receipt(s, 1) + _receipt(s, 2),
            permitted="two receipts sharing one idempotency key",
            rationale="A retried receive POST (same idempotency key) is a replay, never a second receipt posting stock and money.",
        ),
    )
