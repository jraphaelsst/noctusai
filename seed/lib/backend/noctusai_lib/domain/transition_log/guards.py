"""Behaviour probes for the guards one transition-log render emits (see `noctusai_lib.domain._organ_common.guards`).

`noctus.dev.verify_db_guards` derives them for EVERY aggregate rendered into a product (it re-reads the
config from the render's `-- transition-log-config:` marker), so a pilot never hand-writes a probe. The
fixture fabricates its own event rows with random keys; the events->state foreign key is DEFERRABLE, so
`SET CONSTRAINTS ... DEFERRED` lets the probe write an event with no state row inside its rolled-back
transaction (the FK would only be checked at a COMMIT that never happens).

The positive half -- the erasure function DOES delete the subject's rows under its flag -- is not a refusal,
so it is not an `OrganGuardProbe`: `erasure_probe_parts` hands `verify_db_guards` the pieces of its
inverse-polarity (`write_allowed`) probe.
"""
from __future__ import annotations

from noctusai_lib.domain._organ_common.guards import OrganGuardProbe

from .config import CREATED_EVENT, TransitionLogConfig
from .sql import ERASURES_TABLE

_VALUE = {
    "uuid": "gen_random_uuid()",
    "text": "'noc-probe-' || gen_random_uuid()::text",
    "bigint": "-(floor(random() * 1000000000))::bigint - 1",
    "integer": "-(floor(random() * 1000000))::integer - 1",
}
_STATE = {"uuid": "gen_random_uuid()", "text": "'noc_probe'", "bigint": "0", "integer": "0"}


def probe_declare(cfg: TransitionLogConfig) -> str:
    return " ".join(f"v_k_{k.name} {k.type};" for k in cfg.key)


def probe_setup(cfg: TransitionLogConfig) -> str:
    """Fresh key values + the deferred FK (statements; `v_org` is declared by the harness)."""
    lines = [f"v_k_{k.name} := {_VALUE[k.type]};" for k in cfg.key]
    if cfg.foreign_key:
        lines.append(f"SET CONSTRAINTS {cfg.schema}.{cfg.events_table}_entity_fk DEFERRED;")
    return "\n".join(lines) + "\n"


def probe_insert(cfg: TransitionLogConfig, *, seq: str = "1", event_type: str = CREATED_EVENT, from_state: str = "NULL",
                 data: str = "'{}'::jsonb", actor_kind: str = "'system'") -> str:
    cols = ", ".join(cfg.key_names)
    vals = ", ".join(f"v_k_{n}" for n in cfg.key_names)
    return (f"INSERT INTO {cfg.schema}.{cfg.events_table} (org_id, {cols}, seq, from_state, to_state, event_type, data, actor_kind) "
            f"VALUES (v_org, {vals}, {seq}, {from_state}, {_STATE[cfg.state_type]}, '{event_type}', {data}, {actor_kind})")


def erasure_probe_parts(cfg: TransitionLogConfig) -> dict[str, str]:
    """`declare` / `setup` (one event of a fresh subject) / `erase` (the RPC call into `v_res jsonb`) /
    `remaining` (an integer expression: the subject's rows left after the call)."""
    subject = ", ".join(f"'{n}', v_k_{n}" for n in cfg.key_names)
    match = " AND ".join(f"e.{n} = v_k_{n}" for n in cfg.key_names)
    return {
        "declare": probe_declare(cfg) + " v_res jsonb; v_left integer;",
        "setup": probe_setup(cfg) + probe_insert(cfg) + ";\n",
        "erase": (f"v_res := {cfg.schema}.{cfg.rpc('erase_subject')}(v_org, jsonb_build_object({subject}), "
                  f"'noc probe: erasure path', NULL);"),
        "remaining": f"(SELECT count(*)::integer FROM {cfg.schema}.{cfg.events_table} e WHERE e.org_id = v_org AND {match})",
    }


def transition_log_guard_probes(cfg: TransitionLogConfig) -> tuple[OrganGuardProbe, ...]:
    s, ev = cfg.schema, cfg.events_table
    req = (ev, ERASURES_TABLE)
    decl = probe_declare(cfg)
    setup = probe_setup(cfg)
    first = probe_insert(cfg) + ";\n"
    append_only = f"{ev} is append-only"
    match = " AND ".join(f"{n} = v_k_{n}" for n in cfg.key_names)

    def check(name: str, body: str, permitted: str, rationale: str) -> OrganGuardProbe:
        return OrganGuardProbe(guard_name=f"{ev}_{name}", kind="check", requires=req, declare=decl,
                               body=setup + body + ";", permitted=permitted, rationale=rationale)

    return (
        OrganGuardProbe(
            guard_name=f"guard_{ev}_append_only", variant="update", kind="trigger", requires=req, declare=decl,
            fragment=append_only, body=setup + first + f"UPDATE {s}.{ev} SET data = '{{\"noc\": 1}}'::jsonb WHERE {match};",
            permitted=f"an UPDATE of a {ev} row",
            rationale="A transition event is history: a correction is a NEW event, never an edit of an old one.",
        ),
        OrganGuardProbe(
            guard_name=f"guard_{ev}_append_only", variant="delete", kind="trigger", requires=req, declare=decl,
            fragment=append_only, body=setup + first + f"DELETE FROM {s}.{ev} WHERE {match};",
            permitted=f"a DELETE of a {ev} row without the erasure flag",
            rationale=(f"History is deleted only through {cfg.rpc('erase_subject')} (LGPD erasure, owner decision "
                       "2026-11-07), which sets the transaction-local flag and logs the erasure."),
        ),
        OrganGuardProbe(
            guard_name=f"{ev}_refuse_truncate", kind="trigger", requires=req, declare=decl, fragment=append_only,
            body=f"TRUNCATE {s}.{ev};", permitted=f"a TRUNCATE of {ev}",
            rationale="A TRUNCATE skips row triggers; the statement trigger closes that hole.",
        ),
        OrganGuardProbe(
            guard_name=f"{ERASURES_TABLE}_append_only", kind="trigger", requires=req,
            fragment=f"{ERASURES_TABLE} is append-only",
            body=(f"INSERT INTO {s}.{ERASURES_TABLE} (org_id, aggregate, subject, events_deleted, reason) "
                  f"VALUES (v_org, 'noc_probe', '{{}}'::jsonb, 0, 'noc probe');\n"
                  f"UPDATE {s}.{ERASURES_TABLE} SET reason = 'edited' WHERE org_id = v_org;"),
            permitted="an UPDATE of the erasure log",
            rationale="The erasure log is the evidence an erasure happened lawfully; it is never edited.",
        ),
        OrganGuardProbe(
            guard_name=f"{ERASURES_TABLE}_reason_present", kind="check", requires=req,
            body=(f"INSERT INTO {s}.{ERASURES_TABLE} (org_id, aggregate, subject, events_deleted, reason) "
                  f"VALUES (v_org, 'noc_probe', '{{}}'::jsonb, 0, '  ');"),
            permitted="an erasure logged without a reason",
            rationale="Every erasure names why it happened (the LGPD request it answers).",
        ),
        OrganGuardProbe(
            guard_name=f"uq_{ev}_entity_seq", kind="unique", requires=req, declare=decl,
            body=setup + first + probe_insert(cfg) + ";",
            permitted="two events with the same entity and seq",
            rationale="`seq` orders one entity's history; two events at one position would make the order ambiguous.",
        ),
        check("seq_positive", probe_insert(cfg, seq="0", event_type="transitioned", from_state=_STATE[cfg.state_type]),
              "an event with seq 0", "Sequences start at 1 (the creation event)."),
        check("creation_first", probe_insert(cfg, event_type="transitioned", from_state=_STATE[cfg.state_type]),
              "a non-creation event at seq 1", "Every log starts at its initial state: seq 1 is always a creation event."),
        check("event_type_shape", probe_insert(cfg, seq="2", event_type="Not A Type", from_state=_STATE[cfg.state_type]),
              "an event type that is not snake_case", "Event types are stable machine names, not free text."),
        check("data_object", probe_insert(cfg, data="'[1]'::jsonb"), "a non-object data payload",
              "`data` is always a JSON object so consumers can read keys without type checks."),
        check("actor_kind", probe_insert(cfg, actor_kind="'noc_probe_robot'"), "an unknown actor kind",
              "Who acted is one of a closed set (user / agent / system / integration / synthetic)."),
    )


__all__ = ["erasure_probe_parts", "probe_declare", "probe_insert", "probe_setup", "transition_log_guard_probes"]
