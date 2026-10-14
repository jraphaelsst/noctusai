"""Behaviour probes for the finance organ's guards (see `noctusai_lib.domain._organ_common.guards`).

Bound to the default `FinanceConfig` table prefix (`fin_`) -- the prefix the guard names themselves carry.
"""
from __future__ import annotations

from noctusai_lib.domain._organ_common.guards import OrganGuardProbe

_DECLARE = "v_acc uuid; v_entry uuid; v_set uuid; v_led uuid; v_imp uuid; v_rec uuid;"


def _account(s: str) -> str:
    return f"INSERT INTO {s}.fin_accounts (org_id, name, kind) VALUES (v_org, 'noc probe', 'checking') RETURNING id INTO v_acc;\n"


def _entry(s: str, extra_cols: str = "", extra_vals: str = "", returning: str = "") -> str:
    cols = "org_id, direction, description, competence_month, due_date, amount_cents" + extra_cols
    vals = "v_org, 'payable', 'noc probe', DATE '2026-01-01', DATE '2026-01-31', 100" + extra_vals
    return f"INSERT INTO {s}.fin_entries ({cols}) VALUES ({vals}){returning};\n"


def _settlement(s: str, extra_cols: str = "", extra_vals: str = "", returning: str = "") -> str:
    cols = "org_id, entry_id, account_id, kind, settled_on, amount_cents" + extra_cols
    vals = "v_org, v_entry, v_acc, 'payment', DATE '2026-01-31', 100" + extra_vals
    return f"INSERT INTO {s}.fin_settlements ({cols}) VALUES ({vals}){returning};\n"


def _ledger(s: str, extra_cols: str = "", extra_vals: str = "", origin: str = "adjustment", returning: str = "") -> str:
    cols = "org_id, account_id, occurred_on, direction, amount_cents, origin" + extra_cols
    vals = f"v_org, v_acc, DATE '2026-01-31', 'in', 100, '{origin}'" + extra_vals
    return f"INSERT INTO {s}.fin_ledger ({cols}) VALUES ({vals}){returning};\n"


def _line(s: str, fitid: str) -> str:
    return (
        f"INSERT INTO {s}.fin_statement_lines (org_id, import_id, account_id, posted_on, amount_cents, fitid, ledger_id) "
        f"VALUES (v_org, v_imp, v_acc, DATE '2026-01-31', 100, '{fitid}', v_led);\n"
    )


def finance_guard_probes(schema: str) -> tuple[OrganGuardProbe, ...]:
    s = schema
    return (
        OrganGuardProbe(
            guard_name="uq_fin_accounts_gateway",
            kind="unique",
            requires=("fin_accounts",),
            body=(
                f"INSERT INTO {s}.fin_accounts (org_id, name, kind, gateway) VALUES (v_org, 'noc a', 'gateway', 'noc_gw');\n"
                f"INSERT INTO {s}.fin_accounts (org_id, name, kind, gateway) VALUES (v_org, 'noc b', 'gateway', 'noc_gw');"
            ),
            permitted="a second gateway account for the same gateway in one org",
            rationale="One wallet per (org, gateway): two would double-book the same gateway money.",
        ),
        OrganGuardProbe(
            guard_name="uq_fin_categories_name",
            kind="unique",
            requires=("fin_categories",),
            body=(
                f"INSERT INTO {s}.fin_categories (org_id, name, direction) VALUES (v_org, 'noc probe', 'expense');\n"
                f"INSERT INTO {s}.fin_categories (org_id, name, direction) VALUES (v_org, 'NOC PROBE', 'expense');"
            ),
            permitted="a case-variant duplicate root category in one org",
            rationale="Category names are unique per (org, parent), case-insensitively: the DRE groups by category.",
        ),
        OrganGuardProbe(
            guard_name="uq_fin_entries_source_ref",
            kind="unique",
            requires=("fin_entries",),
            body=_entry(s, ", source, source_ref", ", 'import', 'noc-ref'") + _entry(s, ", source, source_ref", ", 'import', 'noc-ref'"),
            permitted="a second entry with the same (source, source_ref)",
            rationale="An external reference books exactly one entry per org: a retried import must be a replay, never a double payable.",
        ),
        OrganGuardProbe(
            guard_name="uq_fin_entries_recurrence_due",
            kind="unique",
            requires=("fin_entries", "fin_recurrences"),
            declare=_DECLARE,
            body=(
                f"INSERT INTO {s}.fin_recurrences (org_id, template, frequency, next_date) "
                "VALUES (v_org, '{}'::jsonb, 'monthly', DATE '2026-01-31') RETURNING id INTO v_rec;\n"
                + _entry(s, ", recurrence_id", ", v_rec")
                + _entry(s, ", recurrence_id", ", v_rec")
            ),
            permitted="two entries generated for the same recurrence and due date",
            rationale="Recurrence generation is idempotent on (recurrence_id, due_date): a re-run must not double the payable.",
        ),
        OrganGuardProbe(
            guard_name="uq_fin_entries_installment",
            kind="unique",
            requires=("fin_entries",),
            declare=_DECLARE,
            body=(
                "v_rec := gen_random_uuid();\n"
                + _entry(s, ", installment_group_id, installment_n, installment_total", ", v_rec, 1, 2")
                + _entry(s, ", installment_group_id, installment_n, installment_total", ", v_rec, 1, 2")
            ),
            permitted="two entries for the same installment number of one group",
            rationale="An installment group carries each number once: a duplicate would bill the same parcel twice.",
        ),
        OrganGuardProbe(
            guard_name="fin_entries_source_check",
            kind="check",
            requires=("fin_entries",),
            body=_entry(s, ", source", ", 'noc_probe_invalid'"),
            permitted="an entry with a source outside the EntrySource vocabulary",
            rationale="Entry sources are a closed vocabulary (the DRE and the idempotency keys depend on it).",
        ),
        OrganGuardProbe(
            guard_name="uq_fin_statement_lines_ledger",
            kind="unique",
            requires=("fin_accounts", "fin_ledger", "fin_statement_imports", "fin_statement_lines"),
            declare=_DECLARE,
            body=(
                _account(s)
                + _ledger(s, returning=" RETURNING id INTO v_led")
                + f"INSERT INTO {s}.fin_statement_imports (org_id, account_id, format, filename, sha256) "
                "VALUES (v_org, v_acc, 'csv', 'noc.csv', 'noc-sha') RETURNING id INTO v_imp;\n"
                + _line(s, "noc-a")
                + _line(s, "noc-b")
            ),
            permitted="two bank statement lines reconciled to the same ledger row",
            rationale="A ledger row is matched by at most one statement line: a double match would reconcile one payment twice.",
        ),
        OrganGuardProbe(
            guard_name="uq_fin_settlements_external",
            kind="unique",
            requires=("fin_accounts", "fin_entries", "fin_settlements"),
            declare=_DECLARE,
            body=(
                _account(s)
                + _entry(s, returning=" RETURNING id INTO v_entry")
                + _settlement(s, ", external_ref", ", 'noc-ext'")
                + _settlement(s, ", external_ref", ", 'noc-ext'")
            ),
            permitted="two settlements with the same (kind, external_ref)",
            rationale="A gateway payment id settles once per org and kind: a replayed webhook must not pay the entry twice.",
        ),
        OrganGuardProbe(
            guard_name="uq_fin_ledger_settlement_origin",
            kind="unique",
            requires=("fin_accounts", "fin_entries", "fin_settlements", "fin_ledger"),
            declare=_DECLARE,
            body=(
                _account(s)
                + _entry(s, returning=" RETURNING id INTO v_entry")
                + _settlement(s, returning=" RETURNING id INTO v_set")
                + _ledger(s, ", settlement_id", ", v_set", origin="settlement")
                + _ledger(s, ", settlement_id", ", v_set", origin="settlement")
            ),
            permitted="two ledger rows with the same (settlement, origin)",
            rationale="A settlement books one ledger row per origin (settlement / fee): the account balance would double-count it.",
        ),
        OrganGuardProbe(
            guard_name="uq_fin_ledger_reverses",
            kind="unique",
            requires=("fin_accounts", "fin_ledger"),
            declare=_DECLARE,
            body=(
                _account(s)
                + _ledger(s, returning=" RETURNING id INTO v_led")
                + _ledger(s, ", reverses_id", ", v_led")
                + _ledger(s, ", reverses_id", ", v_led")
            ),
            permitted="two reversal rows for the same ledger row",
            rationale="A ledger row is reversed at most once: a double reversal would invert the balance twice.",
        ),
    )
