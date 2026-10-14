"""Behaviour probes for the jobs organ's guards (see `noctusai_lib.domain._organ_common.guards`)."""
from __future__ import annotations

from noctusai_lib.domain._organ_common.guards import OrganGuardProbe


def jobs_guard_probes(schema: str) -> tuple[OrganGuardProbe, ...]:
    s = schema
    return (
        OrganGuardProbe(
            guard_name="ux_jobs_dedupe_key",
            kind="unique",
            requires=("jobs",),
            body=(
                f"INSERT INTO {s}.jobs (type, payload, dedupe_key) VALUES ('noc_probe', '{{}}'::jsonb, 'noc-probe-dedupe');\n"
                f"INSERT INTO {s}.jobs (type, payload, dedupe_key) VALUES ('noc_probe', '{{}}'::jsonb, 'noc-probe-dedupe');"
            ),
            permitted="a second job with the same dedupe key",
            rationale="The queue dedupes enqueues on dedupe_key: without the index a retried submit enqueues the same unit of work twice.",
        ),
    )
