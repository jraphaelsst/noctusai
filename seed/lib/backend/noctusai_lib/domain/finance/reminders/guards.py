"""Behaviour probes for the reminders migration's guards (see `_organ_common.guards`). Bound to the `fin_` prefix."""
from __future__ import annotations

from noctusai_lib.domain._organ_common.guards import OrganGuardProbe

_DECLARE = "v_entry uuid; v_rule uuid;"


def _setup(s: str) -> str:
    return (
        f"INSERT INTO {s}.fin_entries (org_id, direction, description, competence_month, due_date, amount_cents) "
        "VALUES (v_org, 'receivable', 'noc probe', DATE '2026-01-01', DATE '2026-01-31', 100) RETURNING id INTO v_entry;\n"
        f"INSERT INTO {s}.fin_reminder_rules (org_id, channel, offset_days, template) "
        "VALUES (v_org, 'whatsapp', 0, 'noc') RETURNING id INTO v_rule;\n"
    )


def _log(s: str, status: str = "pending") -> str:
    return (
        f"INSERT INTO {s}.fin_reminder_log (org_id, entry_id, rule_id, channel, offset_days, cycle_date, status, recipient, message) "
        f"VALUES (v_org, v_entry, v_rule, 'whatsapp', 0, DATE '2026-01-31', '{status}', '5511', 'noc');\n"
    )


def finance_reminders_guard_probes(schema: str) -> tuple[OrganGuardProbe, ...]:
    s = schema
    return (
        OrganGuardProbe(
            guard_name="uq_fin_reminder_rules_offset",
            kind="unique",
            requires=("fin_reminder_rules",),
            body=(
                f"INSERT INTO {s}.fin_reminder_rules (org_id, channel, offset_days, template) VALUES (v_org, 'whatsapp', -3, 'a');\n"
                f"INSERT INTO {s}.fin_reminder_rules (org_id, channel, offset_days, template) VALUES (v_org, 'whatsapp', -3, 'b');"
            ),
            permitted="a second rule for the same (org, channel, offset)",
            rationale="Two rules at one offset would dun the same client twice on the same day.",
        ),
        OrganGuardProbe(
            guard_name="uq_fin_reminder_log_dedup",
            kind="unique",
            requires=("fin_reminder_log", "fin_reminder_rules", "fin_entries"),
            declare=_DECLARE,
            body=_setup(s) + _log(s) + _log(s),
            permitted="a second log row for the same (receivable, rule, cycle date)",
            rationale="The dedup ledger: without the unique key a retried tick or a second worker dun the client twice.",
        ),
        OrganGuardProbe(
            guard_name="fin_reminder_log_status_check",
            kind="check",
            requires=("fin_reminder_log", "fin_reminder_rules", "fin_entries"),
            declare=_DECLARE,
            body=_setup(s) + _log(s, status="noc_invalid"),
            permitted="a log row with a status outside pending/sent/failed",
            rationale="The retry logic keys on the status vocabulary.",
        ),
    )


__all__ = ["finance_reminders_guard_probes"]
