"""Behaviour probes of the engagement organ's guards (see `_organ_common.guards`)."""
from __future__ import annotations

from noctusai_lib.domain._organ_common.guards import OrganGuardProbe

from .sql import POINTS_GUARD_FN, POINTS_GUARD_MESSAGE, UQ_BADGE_RULES, UQ_POINT_RULES


def engagement_guard_probes(schema: str, *, prefix: str = "eng_") -> tuple[OrganGuardProbe, ...]:
    s, p = schema, prefix
    fn, msg = POINTS_GUARD_FN.format(p=p), POINTS_GUARD_MESSAGE.format(p=p)
    seed = (
        f"INSERT INTO {s}.{p}points (org_id, member_id, source, action, points, occurred_at, idempotency_key) "
        "VALUES (v_org, 'm1', 'platform', 'noc', 5, now(), 'k1');\n"
    )
    return (
        OrganGuardProbe(
            guard_name=fn,
            kind="trigger",
            variant="update",
            requires=(f"{p}points",),
            fragment=msg,
            body=seed + f"UPDATE {s}.{p}points SET points = 999 WHERE org_id = v_org;",
            permitted="an UPDATE of a points-ledger row",
            rationale="The points ledger is the audit trail of what each member earned and why: it is appended, never rewritten.",
        ),
        OrganGuardProbe(
            guard_name=fn,
            kind="trigger",
            variant="delete",
            requires=(f"{p}points",),
            fragment=msg,
            body=seed + f"DELETE FROM {s}.{p}points WHERE org_id = v_org;",
            permitted="a direct DELETE of a points-ledger row (outside the LGPD erase function)",
            rationale="Ledger rows leave only through the gated LGPD delete-by-subject path, never by an ad-hoc DELETE.",
        ),
        OrganGuardProbe(
            guard_name=UQ_POINT_RULES.format(p=p),
            kind="unique",
            requires=(f"{p}point_rules",),
            body=(
                f"INSERT INTO {s}.{p}point_rules (org_id, source, action, points) VALUES (v_org, 'platform', 'noc', 1);\n"
                f"INSERT INTO {s}.{p}point_rules (org_id, source, action, points) VALUES (v_org, 'platform', 'noc', 2);"
            ),
            permitted="two point rules for the same (source, action)",
            rationale="An ambiguous rule set would score the same action two ways, depending on which row a query reads first.",
        ),
        OrganGuardProbe(
            guard_name=UQ_BADGE_RULES.format(p=p),
            kind="unique",
            requires=(f"{p}badge_rules",),
            body=(
                f"INSERT INTO {s}.{p}badge_rules (org_id, badge_id, metric, threshold) VALUES (v_org, 'noc', 'points', 1);\n"
                f"INSERT INTO {s}.{p}badge_rules (org_id, badge_id, metric, threshold) VALUES (v_org, 'noc', 'points', 2);"
            ),
            permitted="two badge rules with the same badge id",
            rationale="A badge has one threshold; two would make it earnable at two different bars.",
        ),
    )


__all__ = ["engagement_guard_probes"]
