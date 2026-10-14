"""Behaviour probes for the contracts organ's guards (see `noctusai_lib.domain._organ_common.guards`)."""
from __future__ import annotations

from noctusai_lib.domain._organ_common.guards import OrganGuardProbe


def _contract(s: str, extra_cols: str = "", extra_vals: str = "") -> str:
    return (
        f"INSERT INTO {s}.ctr_contracts (org_id, title, billing_model{extra_cols}) "
        f"VALUES (v_org, 'noc probe', 'one_time'{extra_vals});\n"
    )


def contracts_guard_probes(schema: str) -> tuple[OrganGuardProbe, ...]:
    s = schema
    return (
        OrganGuardProbe(
            guard_name="uq_ctr_contracts_number",
            kind="unique",
            requires=("ctr_contracts",),
            body=_contract(s, ", number", ", 'noc-1'") + _contract(s, ", number", ", 'NOC-1'"),
            permitted="a case-variant duplicate contract number in one org",
            rationale="A contract number identifies one contract per org (case-insensitive): signatures and receivables cite it.",
        ),
        OrganGuardProbe(
            guard_name="uq_ctr_contracts_quote",
            kind="unique",
            requires=("ctr_contracts",),
            body=_contract(s, ", source_quote_id", ", 'noc-quote'") + _contract(s, ", source_quote_id", ", 'noc-quote'"),
            permitted="two contracts converted from the same quote",
            rationale="Convert-on-accept is idempotent: a quote becomes exactly one contract, however often the conversion is retried.",
        ),
    )
