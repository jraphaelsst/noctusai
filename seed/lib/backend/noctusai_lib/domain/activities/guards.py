"""Behaviour probes for the activities organ's guards (see `noctusai_lib.domain._organ_common.guards`)."""
from __future__ import annotations

from noctusai_lib.domain._organ_common.guards import OrganGuardProbe

_DECLARE = "v_act uuid;"


def _type(s: str) -> str:
    return f"INSERT INTO {s}.act_types (org_id, slug, label, kind) VALUES (v_org, 'noc_probe', 'noc probe', 'task');\n"


def _activity(s: str, cols: str = "", vals: str = "", *, entity_kind: str = "lead", kind: str = "task", title: str = "noc probe") -> str:
    extra_c = f", {cols}" if cols else ""
    extra_v = f", {vals}" if vals else ""
    return (
        f"INSERT INTO {s}.act_activities (org_id, entity_kind, entity_id, type_slug, kind, title{extra_c}) "
        f"VALUES (v_org, '{entity_kind}', gen_random_uuid(), 'noc_probe', '{kind}', '{title}'{extra_v})"
    )


def _with_activity(s: str) -> str:
    return _type(s) + _activity(s) + " RETURNING id INTO v_act;\n"


def _event(s: str, event: str = "atividade_criada") -> str:
    return f"INSERT INTO {s}.act_events (org_id, activity_id, event) VALUES (v_org, v_act, '{event}')"


def activities_guard_probes(schema: str) -> tuple[OrganGuardProbe, ...]:
    s = schema
    return (
        OrganGuardProbe(
            guard_name="act_types_slug_shape",
            kind="check",
            requires=("act_types",),
            body=f"INSERT INTO {s}.act_types (org_id, slug, label, kind) VALUES (v_org, 'Bad Slug', 'noc', 'task');",
            permitted="an activity type whose slug is not a lowercase identifier",
            rationale="A type slug is the stable machine key presets and code key on; it must be a lowercase identifier.",
        ),
        OrganGuardProbe(
            guard_name="act_types_kind_valid",
            kind="check",
            requires=("act_types",),
            body=f"INSERT INTO {s}.act_types (org_id, slug, label, kind) VALUES (v_org, 'noc_probe', 'noc', 'party');",
            permitted="an activity type with a kind outside task/call/meeting/visit",
            rationale="The kind is the behavioural family of an activity; an unknown kind would have no behaviour to follow.",
        ),
        OrganGuardProbe(
            guard_name="act_types_label_nonblank",
            kind="check",
            requires=("act_types",),
            body=f"INSERT INTO {s}.act_types (org_id, slug, label, kind) VALUES (v_org, 'noc_probe', '   ', 'task');",
            permitted="an activity type with a blank label",
            rationale="A type is picked by its label in the UI: a blank one is an invisible choice.",
        ),
        OrganGuardProbe(
            guard_name="act_activities_entity_kind_shape",
            kind="check",
            requires=("act_types", "act_activities"),
            body=_type(s) + _activity(s, entity_kind="Bad Kind") + ";",
            permitted="an activity linked to an entity kind that is not a lowercase identifier",
            rationale="entity_kind is a machine key (lead, cliente, contrato ...): free text would split one kind into spellings.",
        ),
        OrganGuardProbe(
            guard_name="act_activities_kind_valid",
            kind="check",
            requires=("act_types", "act_activities"),
            body=_type(s) + _activity(s, kind="party") + ";",
            permitted="an activity with a kind outside task/call/meeting/visit",
            rationale="Same four behavioural families as the types table: the copy on the row can never leave the set.",
        ),
        OrganGuardProbe(
            guard_name="act_activities_title_nonblank",
            kind="check",
            requires=("act_types", "act_activities"),
            body=_type(s) + _activity(s, title="  ") + ";",
            permitted="an activity with a blank title",
            rationale="An activity is listed by its title: a blank one is an unreadable row in every task list.",
        ),
        OrganGuardProbe(
            guard_name="act_activities_state_exclusive",
            kind="check",
            requires=("act_types", "act_activities"),
            body=_type(s) + _activity(s, "done_at, cancelled_at", "now(), now()") + ";",
            permitted="an activity that is both done and cancelled",
            rationale="done and cancelled are mutually exclusive end states: both set would make the completion metrics double-count.",
        ),
        OrganGuardProbe(
            guard_name="act_activities_outcome_valid",
            kind="check",
            requires=("act_types", "act_activities"),
            body=_type(s) + _activity(s, "done_at, outcome", "now(), 'talvez'") + ";",
            permitted="an activity outcome outside realizada/nao_realizada/sem_resposta",
            rationale="The outcome is an enum so completion quality is measurable; free text would not aggregate.",
        ),
        OrganGuardProbe(
            guard_name="act_events_event_valid",
            kind="check",
            requires=("act_types", "act_activities", "act_events"),
            declare=_DECLARE,
            body=_with_activity(s) + _event(s, "row_updated") + ";",
            permitted="an event named outside the activity intent vocabulary",
            rationale="Events are named by business intent (atividade_criada ...), never by row mechanics.",
        ),
        OrganGuardProbe(
            guard_name="act_events_append_only",
            kind="trigger",
            requires=("act_types", "act_activities", "act_events"),
            declare=_DECLARE,
            fragment="act_events is append-only",
            variant="update",
            body=_with_activity(s) + _event(s) + f";\nUPDATE {s}.act_events SET event = 'atividade_concluida' WHERE org_id = v_org;",
            permitted="an UPDATE of an activity event",
            rationale="The activity history is immutable: a correction is a new compensating event, never an edit.",
        ),
        OrganGuardProbe(
            guard_name="act_events_append_only",
            kind="trigger",
            requires=("act_types", "act_activities", "act_events"),
            declare=_DECLARE,
            fragment="act_events is append-only",
            variant="delete",
            body=_with_activity(s) + _event(s) + f";\nDELETE FROM {s}.act_events WHERE org_id = v_org;",
            permitted="a DELETE of an activity event",
            rationale="The activity history is immutable: no event is ever removed.",
        ),
    )


__all__ = ["activities_guard_probes"]
