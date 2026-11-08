"""Behaviour probes of the metas organ's UNIQUE / trigger guards (see `_organ_common.guards`)."""
from __future__ import annotations

from noctusai_lib.domain._organ_common.guards import OrganGuardProbe

from .sql import (
    CLOSINGS_IMMUTABLE_FN,
    UQ_CLOSINGS_KEY,
    UQ_EVENTS_DEDUPE,
    UQ_GOALS_KEY,
    UQ_MEMBERS_ACTIVE,
    UQ_RULES_KEY,
    UQ_SETTINGS_ORG,
    UQ_TEAMS_NAME,
)


def metas_guard_probes(schema: str, *, prefix: str = "mt_") -> tuple[OrganGuardProbe, ...]:
    s, p = schema, prefix

    def period(var: str = "v_period") -> str:
        return (
            f"INSERT INTO {s}.{p}periods (org_id, name, kind, starts_on, ends_on) "
            f"VALUES (v_org, 'noc probe', 'monthly', '2026-01-01', '2026-01-31') RETURNING id INTO {var};\n"
        )

    def team() -> str:
        return f"INSERT INTO {s}.{p}teams (org_id, name) VALUES (v_org, 'noc probe team') RETURNING id INTO v_team;\n"

    def goal(subject: str = "NULL", scope: str = "company") -> str:
        return (
            f"INSERT INTO {s}.{p}goals (org_id, scope, subject_id, category, target, period_id) "
            f"VALUES (v_org, '{scope}', {subject}, 'noc', 10, v_period);\n"
        )

    closing = (
        period()
        + f"INSERT INTO {s}.{p}closings (org_id, period_id, member_id) VALUES (v_org, v_period, gen_random_uuid()) RETURNING id INTO v_closing;\n"
    )
    return (
        OrganGuardProbe(
            guard_name=UQ_TEAMS_NAME.format(p=p),
            kind="unique",
            requires=(f"{p}teams",),
            body=(
                f"INSERT INTO {s}.{p}teams (org_id, name) VALUES (v_org, 'noc probe');\n"
                f"INSERT INTO {s}.{p}teams (org_id, name) VALUES (v_org, 'noc probe');"
            ),
            permitted="two teams with the same name in one org",
            rationale="Two teams named alike make every team picker, ranking row and goal target ambiguous.",
        ),
        OrganGuardProbe(
            guard_name=UQ_MEMBERS_ACTIVE.format(p=p),
            kind="unique",
            requires=(f"{p}teams", f"{p}team_members"),
            declare="v_team uuid; v_user uuid := gen_random_uuid();",
            body=(
                team()
                + f"INSERT INTO {s}.{p}team_members (org_id, team_id, user_id) VALUES (v_org, v_team, v_user);\n"
                f"INSERT INTO {s}.{p}team_members (org_id, team_id, user_id) VALUES (v_org, v_team, v_user);"
            ),
            permitted="a user joining the same team twice while still a member",
            rationale="One active membership per (team, user): a double row would count the member's events twice in the team's rollup.",
        ),
        OrganGuardProbe(
            guard_name=UQ_GOALS_KEY.format(p=p),
            kind="unique",
            requires=(f"{p}periods", f"{p}goals"),
            declare="v_period uuid;",
            body=period() + goal() + goal(),
            permitted="two company goals of one category in the same period",
            rationale="One goal per (scope, subject, category) per period: the company -> team -> member cascade must not double a target.",
        ),
        OrganGuardProbe(
            guard_name=UQ_SETTINGS_ORG.format(p=p),
            kind="unique",
            requires=(f"{p}settings",),
            body=(
                f"INSERT INTO {s}.{p}settings (org_id) VALUES (v_org);\n"
                f"INSERT INTO {s}.{p}settings (org_id) VALUES (v_org);"
            ),
            permitted="a second scoring-settings row for one org",
            rationale="Scoring conversion has ONE answer per org; two rows would let two requests rank the same people differently.",
        ),
        OrganGuardProbe(
            guard_name=UQ_RULES_KEY.format(p=p),
            kind="unique",
            requires=(f"{p}rules",),
            body=(
                f"INSERT INTO {s}.{p}rules (org_id, event_type, modality, points) VALUES (v_org, 'noc', 'default', 1);\n"
                f"INSERT INTO {s}.{p}rules (org_id, event_type, modality, points) VALUES (v_org, 'noc', 'default', 2);"
            ),
            permitted="two org-wide point rules for the same event type and modality",
            rationale="An ambiguous rule set would pick a winner at random and score the same event two ways.",
        ),
        OrganGuardProbe(
            guard_name=UQ_EVENTS_DEDUPE.format(p=p),
            kind="unique",
            requires=(f"{p}events",),
            declare="v_member uuid := gen_random_uuid();",
            body=(
                f"INSERT INTO {s}.{p}events (org_id, member_id, event_type, occurred_on, dedupe_key) VALUES (v_org, v_member, 'noc', '2026-01-02', 'k1');\n"
                f"INSERT INTO {s}.{p}events (org_id, member_id, event_type, occurred_on, dedupe_key) VALUES (v_org, v_member, 'noc', '2026-01-02', 'k1');"
            ),
            permitted="a replayed source event scoring twice",
            rationale="A retried webhook or job (same dedupe_key) is ONE scoring event; two rows would double the member's points.",
        ),
        OrganGuardProbe(
            guard_name=UQ_CLOSINGS_KEY.format(p=p),
            kind="unique",
            requires=(f"{p}periods", f"{p}closings"),
            declare="v_period uuid; v_member uuid := gen_random_uuid();",
            body=(
                period()
                + f"INSERT INTO {s}.{p}closings (org_id, period_id, member_id) VALUES (v_org, v_period, v_member);\n"
                f"INSERT INTO {s}.{p}closings (org_id, period_id, member_id) VALUES (v_org, v_period, v_member);"
            ),
            permitted="closing the same period twice for one member",
            rationale="One closing snapshot per (period, member): a double close must not duplicate anyone's history.",
        ),
        OrganGuardProbe(
            guard_name=CLOSINGS_IMMUTABLE_FN.format(p=p),
            kind="trigger",
            variant="update",
            requires=(f"{p}periods", f"{p}closings"),
            declare="v_period uuid; v_closing uuid;",
            fragment=f"{p}closings is immutable",
            body=closing + f"UPDATE {s}.{p}closings SET unified_score = 999 WHERE id = v_closing;",
            permitted="an UPDATE of a closing snapshot",
            rationale="A closed period's snapshot is the historical record bonuses and rankings were paid on: it is never rewritten.",
        ),
        OrganGuardProbe(
            guard_name=CLOSINGS_IMMUTABLE_FN.format(p=p),
            kind="trigger",
            variant="delete",
            requires=(f"{p}periods", f"{p}closings"),
            declare="v_period uuid; v_closing uuid;",
            fragment=f"{p}closings is immutable",
            body=closing + f"DELETE FROM {s}.{p}closings WHERE id = v_closing;",
            permitted="a DELETE of a closing snapshot",
            rationale="A closed period's snapshot is the historical record bonuses and rankings were paid on: it is never erased.",
        ),
    )


__all__ = ["metas_guard_probes"]
