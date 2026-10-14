"""Parties -- who the org deals with, as an L1 seed organ (roadmap E2/E4/E8).

One row per person or company (`PF` with CPF / `PJ` with CNPJ, check digits validated, stored
without punctuation, unique per org), carrying contact data, an address, state / municipal
registration and any combination of roles (`customer`, `supplier`, `employee`, `carrier`).
Search by name / document / email with a role filter, archive instead of delete, CSV import /
export. `doc` is masked for non-admins (LGPD).

Mount it from a product:

    cfg = PartiesConfig(schema="erp")
    sql = parties_migration(cfg, "erp")                        # -> migrations/0NN_parties.sql
    app.include_router(make_parties_router(cfg, auth_dependency, admin_dependency,
                                           resolve_context=..., get_db=...))
    max_body_path_overrides[IMPORT_UPLOAD_PATH_PATTERN] = IMPORT_UPLOAD_MAX_BYTES

Link, don't absorb (E4): `commerce_customers` stays authoritative for LGPD / consents and later
gains a nullable `party_id`; `fin_entries.party_id` likewise, `counterparty_*` staying a snapshot.

NOC-REMEDIATE[parties-finance-link]: there is NO foreign key to `fin_entries` yet -- it lands
(as a generator flag on `finance_migration` + `PartiesConfig.reference_tables`) after the finance
DRE branch merges. — 2026-10-14
"""
from . import csv_io, parties
from .config import PartiesConfig, PartiesContext
from .csv_io import IMPORT_UPLOAD_MAX_BYTES, IMPORT_UPLOAD_PATH_PATTERN
from .errors import PartiesError
from .parties import normalize_doc, present_party
from .router import make_parties_router
from .sql import PARTIES_TABLES, parties_migration
from .types import PartyKind, PartyRole

__all__ = [
    "IMPORT_UPLOAD_MAX_BYTES",
    "IMPORT_UPLOAD_PATH_PATTERN",
    "PARTIES_TABLES",
    "PartiesConfig",
    "PartiesContext",
    "PartiesError",
    "PartyKind",
    "PartyRole",
    "csv_io",
    "make_parties_router",
    "normalize_doc",
    "parties",
    "parties_migration",
    "present_party",
]
