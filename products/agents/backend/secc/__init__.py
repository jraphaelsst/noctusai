"""SEC-C — the agents container's real-image isolation proof (roadmap
``julia-agents-academia-2026-09``, row SEC-C).

This package is the proof harness itself, not product code: it builds the
real ``runtime`` + ``secc-proof`` images and asserts the isolation
properties the D1 hardening (``bin/entrypoint.sh`` / ``bin/julia-cli-exec``
/ ``docker-compose.yml``'s security block) claims, against a container
started EXACTLY the way prod will start it. See
``products/agents/backend/secc/run_proof.py`` for the entry point and
``KB § PATTERNS/devops/containerization.md`` for the container model.
"""
