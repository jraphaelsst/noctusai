"""Behaviour probes for every guard `event_store_migration` emits (see `noctusai_lib.domain._organ_common.guards`).

Registered on the organ (`noctusai_seed.organs.ORGAN_REGISTRY["event_store"].guard_probes`), so
`noctus.dev.verify_db_guards` derives them for EVERY product that rendered the organ -- no hand-written probe.
Each probe makes a fresh stream through `es_append` itself (a fresh `v_org`, never production rows) and then tries
the one operation its guard exists to refuse. A CHECK probe opens the append flag first so the INSERT reaches the
constraint instead of being stopped earlier by the append-only trigger (that would be `ambiguous`, not `refused`).
"""
from __future__ import annotations

from noctusai_lib.domain._organ_common.guards import OrganGuardProbe

from .config import EventStoreConfig
from .sql import EVENTS_TABLE, PROJECTIONS_TABLE, STREAMS_TABLE

_DECLARE = "v_sid uuid := gen_random_uuid(); v_eid uuid;"


def event_store_guard_probes(schema: str) -> tuple[OrganGuardProbe, ...]:
    cfg = EventStoreConfig(schema)
    s, ev, st = schema, f"{schema}.{EVENTS_TABLE}", f"{schema}.{STREAMS_TABLE}"
    req = (EVENTS_TABLE, STREAMS_TABLE, PROJECTIONS_TABLE)
    seed = (f"PERFORM {s}.es_append(v_org, 'noc_probe', v_sid, 0, '[{{\"event_type\": \"noc_probe\"}}]'::jsonb);\n"
            f"SELECT event_id INTO v_eid FROM {ev} WHERE org_id = v_org AND stream_id = v_sid;\n")
    flag_on = f"PERFORM set_config('{cfg.append_guc}', 'on', true);\n"

    def insert_event(*, version: str = "2", event_id: str = "gen_random_uuid()", event_type: str = "'noc_probe'",
                     schema_version: str = "1", data: str = "'{}'::jsonb", metadata: str = "'{}'::jsonb",
                     pii: str = "NULL") -> str:
        return (f"INSERT INTO {ev} (event_id, org_id, stream_type, stream_id, version, event_type, schema_version, data, "
                f"metadata, pii) VALUES ({event_id}, v_org, 'noc_probe', v_sid, {version}, {event_type}, "
                f"{schema_version}, {data}, {metadata}, {pii});")

    def check(name: str, insert: str, permitted: str, rationale: str, kind: str = "check") -> OrganGuardProbe:
        return OrganGuardProbe(guard_name=name, kind=kind, requires=req, declare=_DECLARE,
                               body=seed + flag_on + insert, permitted=permitted, rationale=rationale)

    def stream_check(name: str, values: str, permitted: str, rationale: str) -> OrganGuardProbe:
        return OrganGuardProbe(guard_name=name, kind="check", requires=req, declare=_DECLARE,
                               body=flag_on + f"INSERT INTO {st} (stream_type, stream_id, org_id, version) VALUES ({values});",
                               permitted=permitted, rationale=rationale)

    def projection_check(name: str, values: str, permitted: str, rationale: str) -> OrganGuardProbe:
        return OrganGuardProbe(guard_name=name, kind="check", requires=req,
                               body=(f"INSERT INTO {s}.{PROJECTIONS_TABLE} (projection, handler, target, stream_types, mode) "
                                     f"VALUES ({values});"),
                               permitted=permitted, rationale=rationale)

    ev_guard, st_guard = f"guard_{EVENTS_TABLE}_append_only", f"guard_{STREAMS_TABLE}_append_only"
    ev_msg, st_msg = f"{EVENTS_TABLE} is append-only", f"{STREAMS_TABLE} is written only by es_append"
    return (
        OrganGuardProbe(guard_name=ev_guard, variant="insert", kind="trigger", requires=req, declare=_DECLARE,
                        fragment=ev_msg, body=seed + insert_event(),
                        permitted="a direct INSERT into es_events without es_append",
                        rationale="Only es_append writes events: it holds the stream lock, checks the expected version "
                                  "and runs the synchronous projections in the same transaction."),
        OrganGuardProbe(guard_name=ev_guard, variant="update", kind="trigger", requires=req, declare=_DECLARE,
                        fragment=ev_msg, body=seed + flag_on + f"UPDATE {ev} SET data = '{{\"noc\": 1}}'::jsonb WHERE org_id = v_org;",
                        permitted="an UPDATE of an es_events row (even under the append flag)",
                        rationale="The log is the truth: a correction is a NEW event, never an edit of an old one."),
        OrganGuardProbe(guard_name=ev_guard, variant="delete", kind="trigger", requires=req, declare=_DECLARE,
                        fragment=ev_msg, body=seed + flag_on + f"DELETE FROM {ev} WHERE org_id = v_org;",
                        permitted="a DELETE of an es_events row (even under the append flag)",
                        rationale="No event is ever deleted; LGPD erasure is crypto-shredding, deferred until an event "
                                  "carries personal data (owner rule 2026-11-07)."),
        OrganGuardProbe(guard_name=f"{EVENTS_TABLE}_refuse_truncate", kind="trigger", requires=req, fragment=ev_msg,
                        body=f"TRUNCATE {ev} CASCADE;", permitted="a TRUNCATE of es_events",
                        rationale="A TRUNCATE skips row triggers; the statement trigger closes that hole."),
        OrganGuardProbe(guard_name=st_guard, variant="insert", kind="trigger", requires=req, declare=_DECLARE,
                        fragment=st_msg,
                        body=f"INSERT INTO {st} (stream_type, stream_id, org_id, version) VALUES ('noc_probe', v_sid, v_org, 5);",
                        permitted="a direct INSERT into es_streams without es_append",
                        rationale="A stream's version moves only with its events; a forged stream row breaks the "
                                  "expected-version contract."),
        OrganGuardProbe(guard_name=st_guard, variant="update", kind="trigger", requires=req, declare=_DECLARE,
                        fragment=st_msg, body=seed + f"UPDATE {st} SET version = version + 1 WHERE org_id = v_org;",
                        permitted="a direct UPDATE of es_streams.version",
                        rationale="A version bump without its event would make the next append skip a version."),
        OrganGuardProbe(guard_name=st_guard, variant="delete", kind="trigger", requires=req, declare=_DECLARE,
                        fragment=st_msg, body=seed + flag_on + f"DELETE FROM {st} WHERE org_id = v_org;",
                        permitted="a DELETE of an es_streams row (even under the append flag)",
                        rationale="A stream is never deleted while the log exists."),
        OrganGuardProbe(guard_name=f"{STREAMS_TABLE}_refuse_truncate", kind="trigger", requires=req, fragment=st_msg,
                        body=f"TRUNCATE {st} CASCADE;", permitted="a TRUNCATE of es_streams",
                        rationale="A TRUNCATE skips row triggers; the statement trigger closes that hole."),
        check("uq_es_events_event_id", insert_event(event_id="v_eid"), "two events with the same event_id",
              "event_id is the idempotency key of an append: a retried append must find its first attempt.",
              kind="unique"),
        check("uq_es_events_stream_version", insert_event(version="1"), "two events at the same stream version",
              "One stream position holds one event; the version is the optimistic-concurrency check."),
        check("es_events_version_positive", insert_event(version="0"), "an event at version 0",
              "Stream versions start at 1."),
        check("es_events_schema_version_positive", insert_event(schema_version="0"), "an event with schema_version 0",
              "Payload schema versions start at 1 (upcasters chain from there)."),
        check("es_events_event_type_shape", insert_event(event_type="'Not A Type'"), "a free-text event type",
              "Event types are stable machine names (snake_case, optionally dotted)."),
        check("es_events_data_object", insert_event(data="'[1]'::jsonb"), "a non-object data payload",
              "`data` is always a JSON object so readers can address keys without type checks."),
        check("es_events_metadata_shape", insert_event(metadata="'{\"email\": \"x\"}'::jsonb"), "metadata outside the closed key set",
              "Metadata is ids + provenance only (causation, correlation, actor, source) -- never personal data."),
        check("es_events_pii_reserved", insert_event(pii="'{\"name\": \"x\"}'::jsonb"), "an event carrying a pii payload",
              "LGPD (owner rule 2026-11-07): no personal data in events until crypto-shredding is enabled on purpose."),
        stream_check("es_streams_version_nonnegative", "'noc_probe', v_sid, v_org, -1", "a stream at version -1",
                     "A stream version counts its events."),
        stream_check("es_streams_stream_type_shape", "'Not A Type', v_sid, v_org, 0", "a free-text stream type",
                     "Stream types are stable machine names."),
        projection_check("es_projections_mode", "'noc_probe', 'h', 't', ARRAY['noc_probe'], 'sometimes'",
                         "a projection with an unknown mode", "A projection is either sync (in the append) or async (checkpointed)."),
        projection_check("es_projections_name_shape", "'Not A Name', 'h', 't', ARRAY['noc_probe'], 'async'",
                         "a projection with a free-text name", "Projection names key checkpoints and jobs; they are machine names."),
    )


__all__ = ["event_store_guard_probes"]
