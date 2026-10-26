"""Behaviour probe of the leads UNIQUE guard (see `_organ_common.guards`)."""
from __future__ import annotations

from noctusai_lib.domain._organ_common.guards import OrganGuardProbe

from .sql import UQ_CHAT


def leads_guard_probes(schema: str, *, table: str = "leads") -> tuple[OrganGuardProbe, ...]:
    s = schema
    return (
        OrganGuardProbe(
            guard_name=UQ_CHAT.format(table=table),
            kind="unique",
            requires=(table,),
            declare="v_conn uuid := gen_random_uuid();",
            body=(
                f"INSERT INTO {s}.{table} (org_id, name, origin, stage, whatsapp_connection_id, whatsapp_chat_id) "
                f"VALUES (v_org, 'noc probe a', 'whatsapp', 'lead', v_conn, '5511900000000@c.us');\n"
                f"INSERT INTO {s}.{table} (org_id, name, origin, stage, whatsapp_connection_id, whatsapp_chat_id) "
                f"VALUES (v_org, 'noc probe b', 'whatsapp', 'lead', v_conn, '5511900000000@c.us');"
            ),
            permitted="a second lead for the same WhatsApp chat in one org",
            rationale="One lead per (org, connection, chat): a duplicate would double-count the same conversation on the funnel.",
        ),
    )


__all__ = ["leads_guard_probes"]
