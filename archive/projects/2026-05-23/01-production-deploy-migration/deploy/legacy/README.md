# legacy deploy assets — PROMOTED, not archived

The `legacy.noctusai.com` container artifacts that used to live here are **live
production infrastructure**, not project history. They were promoted on
2026-08-26 to the live deploy tree, alongside their siblings (`deploy/fleet`,
`deploy/tunnel`, `deploy/services`):

    deploy/legacy/

Reason: a security fix to the legacy app required a rebuild, and the artifacts
needed to do it were only reachable by archaeology through an archived project —
while the VPS copy had been cleaned down to just `.env`. Live infra must live in
the live tree.

Nothing else about this archived project moved.
