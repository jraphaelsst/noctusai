"""Finance billing reminders ("dunning") -- WhatsApp reminders before / on / after a receivable's due date.

Rules per org (offsets -3 / 0 / +1 / +7 by default, pt-BR templates with `{nome} {razao_social} {nome_fantasia}
{valor} {vencimento} {link_pagamento} {pix_copia_cola} {dias_atraso}`), selection in the org timezone, a dedup
ledger enforced by a UNIQUE index and written BEFORE the send, a channel Protocol (Fake + Real WhatsApp +
factory) and a daily scheduler job. Wiring + semantics: `service.py`; tables: `sql.py`.

Host wiring:

    cfg = FinanceConfig(schema="myprod")
    sql = finance_reminders_migration(cfg, "myprod")     # -> migrations/0NN_finance_reminders.sql (after finance)
    ports = ReminderPorts(
        channels={"whatsapp": make_reminder_channel("whatsapp", resolve_client=make_waha_client_resolver(store))},
        resolve_contact=my_contact_resolver,             # (scope, entry) -> ReminderContact | None
        skip_reason=my_veto,                             # optional: preserved / cancelled clients
    )
    register_billing_reminders(cfg, get_db=get_admin_client, ports=ports, hour=12)   # job `finance_billing_reminders`
    # HTTP: `mount_finance_reminders(...)` (noctusai_seed.organs) -> `make_finance_reminders_router`, /api/finance/reminders;
    # FE: `<RemindersPage api={api} isAdmin={...} />` (@noctusai/lib finance).
"""
from .channel import (
    FakeReminderChannel,
    ReminderChannel,
    ReminderSendError,
    SendReceipt,
    WhatsAppReminderChannel,
    make_reminder_channel,
    make_waha_client_resolver,
    normalize_br_phone,
)
from .guards import finance_reminders_guard_probes
from .job import JOB_ID, register_billing_reminders
from .router import make_finance_reminders_router
from .service import (
    ReminderPorts,
    create_rule,
    delete_rule,
    ensure_default_rules,
    get_settings,
    list_log,
    list_rules,
    preview_reminders,
    run_reminders_all,
    run_reminders_for_org,
    save_settings,
    set_receivable_opt_out,
    update_rule,
    update_settings,
)
from .sql import REMINDER_TABLES, finance_reminders_migration
from .templates import DEFAULT_RULES, format_brl, render, sample_values, validate_template
from .types import (
    MAX_ATTEMPTS,
    TEMPLATE_VARIABLES,
    PlannedReminder,
    ReminderContact,
    ReminderPlan,
    SkippedReminder,
)

__all__ = [
    "DEFAULT_RULES", "FakeReminderChannel", "JOB_ID", "MAX_ATTEMPTS", "PlannedReminder", "REMINDER_TABLES",
    "ReminderChannel", "ReminderContact", "ReminderPlan", "ReminderPorts", "ReminderSendError", "SendReceipt",
    "SkippedReminder", "TEMPLATE_VARIABLES", "WhatsAppReminderChannel", "create_rule", "delete_rule",
    "ensure_default_rules", "finance_reminders_guard_probes", "finance_reminders_migration", "format_brl",
    "get_settings", "list_log", "list_rules", "make_finance_reminders_router", "make_reminder_channel", "make_waha_client_resolver",
    "normalize_br_phone", "preview_reminders", "register_billing_reminders", "render", "run_reminders_all",
    "run_reminders_for_org", "sample_values", "save_settings", "set_receivable_opt_out", "update_rule", "update_settings",
    "validate_template",
]
