"""Behaviour probes of the assignment organ's guards (see `_organ_common.guards`)."""
from __future__ import annotations

from noctusai_lib.domain._organ_common.guards import OrganGuardProbe

from .sql import (
    CK_EVENTS_KIND,
    CK_MEMBERS_CAPACITY,
    CK_MEMBERS_OOO,
    CK_RULES_KIND,
    CK_SETTINGS_STRATEGY,
    EVENTS_GUARD_FN,
    EVENTS_GUARD_MESSAGE,
    UQ_ASSIGNMENTS,
    UQ_CURSORS,
    UQ_MEMBERS,
    UQ_RULES,
    UQ_SETTINGS,
    UQ_TEAMS,
)


def assignment_guard_probes(schema: str, *, prefix: str = "asg_") -> tuple[OrganGuardProbe, ...]:
    s, p = schema, prefix
    teams, members, rules, cursors = (f"{s}.{p}{n}" for n in ("teams", "members", "rules", "cursors"))
    settings, assignments, events = (f"{s}.{p}{n}" for n in ("settings", "assignments", "events"))
    team = f"INSERT INTO {teams} (org_id, name) VALUES (v_org, 'noc probe team') RETURNING id INTO v_team;\n"
    seat = f"INSERT INTO {members} (org_id, team_id, user_id) VALUES (v_org, v_team, v_user)"
    event = (
        f"INSERT INTO {events} (org_id, subject_kind, subject_id, event, to_user_id) "
        "VALUES (v_org, 'card', gen_random_uuid(), 'assigned', gen_random_uuid());\n"
    )
    declare = "v_team uuid; v_user uuid := gen_random_uuid();"
    return (
        OrganGuardProbe(
            guard_name=UQ_TEAMS.format(p=p), kind="unique", requires=(f"{p}teams",),
            body=(
                f"INSERT INTO {teams} (org_id, name) VALUES (v_org, 'noc probe');\n"
                f"INSERT INTO {teams} (org_id, name) VALUES (v_org, ' NOC Probe ');"
            ),
            permitted="a case-variant duplicate team name in one org",
            rationale="A team name identifies one team per org (case-insensitive); two 'Vendas' / 'vendas' teams split one rotation in half.",
        ),
        OrganGuardProbe(
            guard_name=UQ_SETTINGS.format(p=p), kind="unique", requires=(f"{p}settings",),
            body=(
                f"INSERT INTO {settings} (org_id) VALUES (v_org);\n"
                f"INSERT INTO {settings} (org_id) VALUES (v_org);"
            ),
            permitted="a second settings row for one org",
            rationale="One strategy per org: two settings rows would make 'which strategy runs' depend on read order.",
        ),
        OrganGuardProbe(
            guard_name=UQ_MEMBERS.format(p=p), kind="unique", requires=(f"{p}teams", f"{p}members"), declare=declare,
            body=team + f"{seat};\n{seat};",
            permitted="the same user twice in one team",
            rationale="One seat per user per team: a double seat would give that person two turns in every rotation.",
        ),
        OrganGuardProbe(
            guard_name=UQ_RULES.format(p=p), kind="unique", requires=(f"{p}teams", f"{p}rules"), declare=declare,
            body=(
                team
                + f"INSERT INTO {rules} (org_id, kind, match_value, team_id) VALUES (v_org, 'source', 'noc', v_team);\n"
                + f"INSERT INTO {rules} (org_id, kind, match_value, team_id) VALUES (v_org, 'source', 'noc', v_team);"
            ),
            permitted="two rules for the same (kind, value)",
            rationale="One team per source / unit value: two rules would make 'which team wins' a coin flip.",
        ),
        OrganGuardProbe(
            guard_name=UQ_CURSORS.format(p=p), kind="unique", requires=(f"{p}teams", f"{p}cursors"), declare=declare,
            body=(
                team
                + f"INSERT INTO {cursors} (org_id, team_id, last_user_id) VALUES (v_org, v_team, v_user);\n"
                + f"INSERT INTO {cursors} (org_id, team_id, last_user_id) VALUES (v_org, v_team, v_user);"
            ),
            permitted="two round-robin cursors for one team",
            rationale="A team rotates on one cursor; two would serve the same member twice in a row.",
        ),
        OrganGuardProbe(
            guard_name=UQ_ASSIGNMENTS.format(p=p), kind="unique", requires=(f"{p}assignments",), declare="v_subject uuid := gen_random_uuid();",
            body=(
                f"INSERT INTO {assignments} (org_id, subject_kind, subject_id, user_id, strategy, criterion) "
                "VALUES (v_org, 'card', v_subject, gen_random_uuid(), 'manual', 'manual');\n"
                f"INSERT INTO {assignments} (org_id, subject_kind, subject_id, user_id, strategy, criterion) "
                "VALUES (v_org, 'card', v_subject, gen_random_uuid(), 'manual', 'manual');"
            ),
            permitted="two current owners for one subject",
            rationale="A subject has exactly one current owner: a concurrent double-assign must lose, not create two.",
        ),
        OrganGuardProbe(
            guard_name=CK_MEMBERS_CAPACITY.format(p=p), kind="check", requires=(f"{p}teams", f"{p}members"), declare=declare,
            body=team + f"INSERT INTO {members} (org_id, team_id, user_id, capacity) VALUES (v_org, v_team, v_user, 0);",
            permitted="a member with capacity 0",
            rationale="Capacity is a positive ceiling or NULL (unlimited); 0 is a typo for 'out of office' and would silently starve a member.",
        ),
        OrganGuardProbe(
            guard_name=CK_MEMBERS_OOO.format(p=p), kind="check", requires=(f"{p}teams", f"{p}members"), declare=declare,
            body=(
                team
                + f"INSERT INTO {members} (org_id, team_id, user_id, ooo_from, ooo_until) "
                "VALUES (v_org, v_team, v_user, now(), now() - interval '1 day');"
            ),
            permitted="an out-of-office window that ends before it starts",
            rationale="An inverted window is never active: the member would look available while believing they are away.",
        ),
        OrganGuardProbe(
            guard_name=CK_RULES_KIND.format(p=p), kind="check", requires=(f"{p}teams", f"{p}rules"), declare=declare,
            body=team + f"INSERT INTO {rules} (org_id, kind, match_value, team_id) VALUES (v_org, 'noc_bogus', 'x', v_team);",
            permitted="a rule of an unknown kind",
            rationale="Only `source` / `unit` rules are read by a strategy; any other kind is a rule that can never fire.",
        ),
        OrganGuardProbe(
            guard_name=CK_SETTINGS_STRATEGY.format(p=p), kind="check", requires=(f"{p}settings",),
            body=f"INSERT INTO {settings} (org_id, strategy) VALUES (v_org, 'Not A Slug!');",
            permitted="a strategy name that is not a lowercase slug",
            rationale="A strategy is a builtin or a registered hook name; a malformed one can never resolve.",
        ),
        OrganGuardProbe(
            guard_name=CK_EVENTS_KIND.format(p=p), kind="check", requires=(f"{p}events",),
            body=(
                f"INSERT INTO {events} (org_id, subject_kind, subject_id, event) "
                "VALUES (v_org, 'card', gen_random_uuid(), 'noc_bogus');"
            ),
            permitted="an event of an unknown kind",
            rationale="The event vocabulary is closed: a measure over `event` must never meet a value it does not know.",
        ),
        OrganGuardProbe(
            guard_name=EVENTS_GUARD_FN.format(p=p), kind="trigger", variant="update", requires=(f"{p}events",),
            fragment=EVENTS_GUARD_MESSAGE.format(p=p),
            body=event + f"UPDATE {events} SET to_user_id = gen_random_uuid() WHERE org_id = v_org;",
            permitted="an UPDATE of an assignment event",
            rationale="Events are the audit trail of who owned what and why: appended, never rewritten.",
        ),
        OrganGuardProbe(
            guard_name=EVENTS_GUARD_FN.format(p=p), kind="trigger", variant="delete", requires=(f"{p}events",),
            fragment=EVENTS_GUARD_MESSAGE.format(p=p),
            body=event + f"DELETE FROM {events} WHERE org_id = v_org;",
            permitted="a DELETE of an assignment event",
            rationale="An erased event rewrites history (who was owed the lead, when): events are never deleted.",
        ),
    )


__all__ = ["assignment_guard_probes"]
