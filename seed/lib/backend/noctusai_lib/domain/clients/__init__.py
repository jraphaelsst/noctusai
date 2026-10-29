"""Clients -- people served in recurring sessions (therapy patients, trainees, students), as an L1 seed organ.

One client = a person under care: their sessions (dates, times, status), weekly slots that generate sessions, tags,
and the money of each charged session -- booked as a receivable in the finance organ through the `FinanceBooking`
seam (so cash flow / DRE include it) and paid by hand (pix / dinheiro / cartão ...; no gateway). Statuses, session
statuses, payment methods and the nouns are DATA (`ClientsConfig`): the code never names a vertical.

A lead becomes a client with `ClientsService.ensure_from_lead` (idempotent on `(org_id, lead_id)`); a host wires it
to the leads organ's `LeadsConfig.on_stage_entered` hook.

Mount it from a product (`noctusai_seed.organs.mount_clients` does this binding):

    config = ClientsConfig(noun_singular="Paciente", noun_plural="Pacientes", timezone="America/Sao_Paulo")
    sql = clients_migration("monica", config)                         # -> migrations/0NN_clients.sql
    store = build_clients_store(admin_client, config)
    booking = SupabaseFinanceBooking(admin_client, FinanceConfig(schema="monica"))
    service = ClientsService(store, config, booking)
    app.include_router(create_clients_router(store_factory=..., get_current_user_org=auth,
                                             admin_dependency=admin, config=config, booking_factory=...))
"""
from .config import (
    DEFAULT_PAYMENT_METHODS,
    DEFAULT_SESSION_STATUSES,
    DEFAULT_STATUSES,
    ClientsConfig,
    ClientStatus,
    PaymentMethod,
    SessionStatus,
)
from .errors import (
    CLIENTE_COM_FINANCEIRO,
    SESSAO_COM_PAGAMENTO,
    VALOR_EXCEDE_ABERTO,
    ClientConflictError,
    ClientsError,
)
from .guards import clients_guard_probes
from .router import create_clients_router
from .service import MAX_AGENDA_DAYS, ClientsService
from .sql import CLIENTS_MIGRATION_HEADER, clients_migration, clients_table_ddl
from .store import ClientFilters, ClientsStore, FakeClientsStore
from .supabase_store import SupabaseClientsStore, build_clients_store

__all__ = [
    "CLIENTE_COM_FINANCEIRO",
    "CLIENTS_MIGRATION_HEADER",
    "ClientConflictError",
    "ClientFilters",
    "ClientStatus",
    "ClientsConfig",
    "ClientsError",
    "ClientsService",
    "ClientsStore",
    "DEFAULT_PAYMENT_METHODS",
    "DEFAULT_SESSION_STATUSES",
    "DEFAULT_STATUSES",
    "FakeClientsStore",
    "MAX_AGENDA_DAYS",
    "PaymentMethod",
    "SESSAO_COM_PAGAMENTO",
    "SessionStatus",
    "SupabaseClientsStore",
    "VALOR_EXCEDE_ABERTO",
    "build_clients_store",
    "clients_guard_probes",
    "clients_migration",
    "clients_table_ddl",
    "create_clients_router",
]
