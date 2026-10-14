"""Behaviour probes for the quotes organ's guards (see `noctusai_lib.domain._organ_common.guards`)."""
from __future__ import annotations

from noctusai_lib.domain._organ_common.guards import OrganGuardProbe

_DECLARE = "v_party uuid; v_root uuid := gen_random_uuid(); v_quote uuid;"
_TABLES = ("pty_parties", "quo_quotes")


def _party(s: str) -> str:
    return f"INSERT INTO {s}.pty_parties (org_id, kind, legal_name) VALUES (v_org, 'PF', 'noc probe') RETURNING id INTO v_party;\n"


def _quote(
    s: str, number: str, *, root: str = "v_root", version: int = 1, current: bool = True,
    status: str = "draft", returning: bool = False,
) -> str:
    accepted = ", accepted_at" if status == "accepted" else ""
    accepted_v = ", now()" if status == "accepted" else ""
    ret = " RETURNING id INTO v_quote" if returning else ""
    return (
        f"INSERT INTO {s}.quo_quotes (org_id, number, root_id, version, is_current, party_id, status{accepted}) "
        f"VALUES (v_org, '{number}', {root}, {version}, {str(current).lower()}, v_party, '{status}'{accepted_v}){ret};\n"
    )


def quote_guard_probes(schema: str) -> tuple[OrganGuardProbe, ...]:
    s = schema
    return (
        OrganGuardProbe(
            guard_name="uq_quo_quotes_version",
            kind="unique",
            requires=_TABLES,
            declare=_DECLARE,
            body=_party(s) + _quote(s, "NOC-1") + _quote(s, "NOC-2", current=False),
            permitted="two rows for the same version of one quote",
            rationale="A quote's versions are numbered once: a concurrent revise must not mint two version 2s.",
        ),
        OrganGuardProbe(
            guard_name="uq_quo_quotes_number",
            kind="unique",
            requires=_TABLES,
            declare=_DECLARE,
            body=_party(s) + _quote(s, "NOC-1") + _quote(s, "NOC-1", root="gen_random_uuid()"),
            permitted="two different quotes sharing a number and version",
            rationale="The customer-facing quote number identifies one quote (per version): it is what the buyer quotes back.",
        ),
        OrganGuardProbe(
            guard_name="uq_quo_quotes_current",
            kind="unique",
            requires=_TABLES,
            declare=_DECLARE,
            body=_party(s) + _quote(s, "NOC-1") + _quote(s, "NOC-1", version=2),
            permitted="two current versions of one quote",
            rationale="Exactly one version of a quote is current: the public link and the list must resolve to a single document.",
        ),
        OrganGuardProbe(
            guard_name="uq_quo_quotes_accepted",
            kind="unique",
            requires=_TABLES,
            declare=_DECLARE,
            body=(
                _party(s)
                + _quote(s, "NOC-1", current=False, status="accepted")
                + _quote(s, "NOC-1", version=2, current=False, status="accepted")
            ),
            permitted="two accepted versions of one quote",
            rationale="At most one version of a quote can be accepted: acceptance converts to an order/contract exactly once.",
        ),
        OrganGuardProbe(
            guard_name="quo_quotes_frozen",
            kind="trigger",
            requires=_TABLES,
            declare=_DECLARE,
            variant="update",
            fragment="a quote that left draft is frozen",
            body=(
                _party(s)
                + _quote(s, "NOC-1", status="sent", returning=True)
                + f"UPDATE {s}.quo_quotes SET title = 'noc probe edit' WHERE id = v_quote;"
            ),
            permitted="editing the terms of a quote that left draft",
            rationale="A sent quote is the document the customer decides on: a post-send edit must be a new version.",
        ),
        OrganGuardProbe(
            guard_name="quo_quotes_frozen",
            kind="trigger",
            requires=_TABLES,
            declare=_DECLARE,
            variant="delete",
            fragment="only a draft can be deleted",
            body=(
                _party(s)
                + _quote(s, "NOC-1", status="sent", returning=True)
                + f"DELETE FROM {s}.quo_quotes WHERE id = v_quote;"
            ),
            permitted="deleting a quote that left draft",
            rationale="Only a draft may be deleted: a sent or decided quote is part of the commercial record.",
        ),
        OrganGuardProbe(
            guard_name="quo_lines_frozen",
            kind="trigger",
            requires=(*_TABLES, "quo_lines"),
            declare=_DECLARE,
            fragment="the lines of a quote that left draft are frozen",
            body=(
                _party(s)
                + _quote(s, "NOC-1", status="sent", returning=True)
                + f"INSERT INTO {s}.quo_lines (org_id, quote_id, position, description, qty, unit_price_cents, total_cents) "
                "VALUES (v_org, v_quote, 0, 'noc probe', 1, 100, 100);"
            ),
            permitted="adding a line to a quote that left draft",
            rationale="The lines are part of the frozen document: totals are computed from them at send time.",
        ),
        OrganGuardProbe(
            guard_name="quo_acceptances_append_only",
            kind="trigger",
            requires=(*_TABLES, "quo_acceptances"),
            declare=_DECLARE,
            fragment="quo_acceptances is append-only",
            body=(
                _party(s)
                + _quote(s, "NOC-1", status="sent", returning=True)
                + f"INSERT INTO {s}.quo_acceptances (org_id, quote_id, decision, channel, signer_name, content_sha256) "
                f"VALUES (v_org, v_quote, 'rejected', 'staff', 'noc probe', repeat('a', 64));\n"
                f"UPDATE {s}.quo_acceptances SET signer_name = 'noc probe edit' WHERE quote_id = v_quote;"
            ),
            permitted="an UPDATE of a recorded customer decision",
            rationale="The consent record is evidence: it is written once and never edited.",
        ),
        OrganGuardProbe(
            guard_name="quo_events_append_only",
            kind="trigger",
            requires=("quo_events",),
            fragment="quo_events is append-only",
            body=(
                f"INSERT INTO {s}.quo_events (org_id, quote_id, kind) VALUES (v_org, gen_random_uuid(), 'created');\n"
                f"UPDATE {s}.quo_events SET kind = 'updated' WHERE org_id = v_org;"
            ),
            permitted="an UPDATE of a quote audit-trail row",
            rationale="The quote audit trail is history: it is only ever appended to.",
        ),
    )
