"""Behaviour probes for the parties organ's guards (see `noctusai_lib.domain._organ_common.guards`)."""
from __future__ import annotations

from noctusai_lib.domain._organ_common.guards import OrganGuardProbe


def party_guard_probes(schema: str) -> tuple[OrganGuardProbe, ...]:
    s = schema
    return (
        OrganGuardProbe(
            guard_name="uq_pty_parties_doc",
            kind="unique",
            requires=("pty_parties",),
            body=(
                f"INSERT INTO {s}.pty_parties (org_id, kind, doc, legal_name) VALUES (v_org, 'PF', '12345678901', 'noc probe a');\n"
                f"INSERT INTO {s}.pty_parties (org_id, kind, doc, legal_name) VALUES (v_org, 'PF', '12345678901', 'noc probe b');"
            ),
            permitted="a second party with the same document in one org",
            rationale="One party per (org, CPF/CNPJ): a duplicate document would split one person's receivables and history over two rows.",
        ),
    )
