"""Behaviour probes of the approvals organ's guards (see `_organ_common.guards`)."""
from __future__ import annotations

from noctusai_lib.domain._organ_common.guards import OrganGuardProbe

from .sql import CK_EVENTS_KIND, CK_EVENTS_MOTIVO, CK_EVENTS_VERSAO, EVENTS_GUARD_FN, EVENTS_GUARD_MESSAGE, UQ_DECIDED, UQ_SUBMITTED


def approvals_guard_probes(schema: str, *, prefix: str = "apr_") -> tuple[OrganGuardProbe, ...]:
    p = prefix
    events = f"{schema}.{p}events"
    declare = "v_subject uuid := gen_random_uuid();"

    def ins(event: str, versao: int = 1, motivo: str = "NULL", subject: str = "v_subject") -> str:
        return (f"INSERT INTO {events} (org_id, subject_kind, subject_id, versao, event, motivo) "
                f"VALUES (v_org, 'roteiro', {subject}, {versao}, '{event}', {motivo});")

    return (
        OrganGuardProbe(
            guard_name=UQ_SUBMITTED.format(p=p), kind="unique", requires=(f"{p}events",), declare=declare,
            body=ins("submitted") + "\n" + ins("submitted"),
            permitted="the same versao submitted twice",
            rationale="A versao is submitted once: a duplicate would make 'what is current' ambiguous.",
        ),
        OrganGuardProbe(
            guard_name=UQ_DECIDED.format(p=p), kind="unique", requires=(f"{p}events",), declare=declare,
            body=ins("approved") + "\n" + ins("rejected", motivo="'x'"),
            permitted="two decisions on one versao",
            rationale="A versao is decided once: an approve and a reject on the same versao would contradict each other.",
        ),
        OrganGuardProbe(
            guard_name=CK_EVENTS_KIND.format(p=p), kind="check", requires=(f"{p}events",), declare=declare,
            body=ins("noc_bogus"),
            permitted="an event of an unknown kind",
            rationale="The event vocabulary is closed: a measure over `event` must never meet a value it does not know.",
        ),
        OrganGuardProbe(
            guard_name=CK_EVENTS_VERSAO.format(p=p), kind="check", requires=(f"{p}events",), declare=declare,
            body=ins("submitted", versao=0),
            permitted="a versao below 1",
            rationale="Versions count from 1; 0 or negative is a bug in the host's versioning.",
        ),
        OrganGuardProbe(
            guard_name=CK_EVENTS_MOTIVO.format(p=p), kind="check", requires=(f"{p}events",), declare=declare,
            body=ins("rejected", motivo="'   '"),
            permitted="a rejection with no motivo",
            rationale="A rejection nobody can act on is noise: the author needs to know what to fix.",
        ),
        OrganGuardProbe(
            guard_name=EVENTS_GUARD_FN.format(p=p), kind="trigger", variant="update", requires=(f"{p}events",), declare=declare,
            fragment=EVENTS_GUARD_MESSAGE.format(p=p),
            body=ins("submitted") + f"\nUPDATE {events} SET note = 'x' WHERE org_id = v_org;",
            permitted="an UPDATE of an approvals event",
            rationale="Events are the audit trail of who approved what and when: appended, never rewritten.",
        ),
        OrganGuardProbe(
            guard_name=EVENTS_GUARD_FN.format(p=p), kind="trigger", variant="delete", requires=(f"{p}events",), declare=declare,
            fragment=EVENTS_GUARD_MESSAGE.format(p=p),
            body=ins("submitted") + f"\nDELETE FROM {events} WHERE org_id = v_org;",
            permitted="a DELETE of an approvals event",
            rationale="An erased event rewrites history (who approved the content that went out): events are never deleted.",
        ),
    )


__all__ = ["approvals_guard_probes"]
