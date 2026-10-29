"""Behaviour probes of the clients UNIQUE guards (see `_organ_common.guards`)."""
from __future__ import annotations

from typing import Optional

from noctusai_lib.domain._organ_common.guards import OrganGuardProbe

from .config import ClientsConfig
from .sql import UQ_LEAD, UQ_SLOT


def clients_guard_probes(schema: str, config: Optional[ClientsConfig] = None) -> tuple[OrganGuardProbe, ...]:
    cfg = config or ClientsConfig()
    s, c, se, sc = schema, cfg.clients_table, cfg.sessions_table, cfg.schedules_table
    return (
        OrganGuardProbe(
            guard_name=UQ_LEAD.format(table=c),
            kind="unique",
            requires=(c,),
            declare="v_lead uuid := gen_random_uuid();",
            body=(
                f"INSERT INTO {s}.{c} (org_id, name, status, lead_id) VALUES (v_org, 'noc probe a', 'ativo', v_lead);\n"
                f"INSERT INTO {s}.{c} (org_id, name, status, lead_id) VALUES (v_org, 'noc probe b', 'ativo', v_lead);"
            ),
            permitted="a second client converted from the same lead in one org",
            rationale="One client per lead: a duplicate would split one person's sessions and money across two records.",
        ),
        OrganGuardProbe(
            guard_name=UQ_SLOT.format(table=se),
            kind="unique",
            requires=(c, sc, se),
            declare="v_client uuid := gen_random_uuid(); v_sched uuid := gen_random_uuid();",
            body=(
                f"INSERT INTO {s}.{c} (id, org_id, name, status) VALUES (v_client, v_org, 'noc probe', 'ativo');\n"
                f"INSERT INTO {s}.{sc} (id, org_id, client_id, weekday, slot_time, duration_min, starts_on) "
                f"VALUES (v_sched, v_org, v_client, 0, '10:00', 50, CURRENT_DATE);\n"
                f"INSERT INTO {s}.{se} (org_id, client_id, schedule_id, starts_at, duration_min, status) "
                f"VALUES (v_org, v_client, v_sched, '2030-01-07 13:00+00', 50, 'agendada');\n"
                f"INSERT INTO {s}.{se} (org_id, client_id, schedule_id, starts_at, duration_min, status) "
                f"VALUES (v_org, v_client, v_sched, '2030-01-07 13:00+00', 50, 'agendada');"
            ),
            permitted="a second generated session for the same schedule slot",
            rationale="Materialization is idempotent on (schedule_id, starts_at): a duplicate would show and bill the slot twice.",
        ),
    )


__all__ = ["clients_guard_probes"]
