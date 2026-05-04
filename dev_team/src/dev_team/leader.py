"""dev_team Team Leader factory.

Public surface (contract):
    build_leader(config) -> agno.agent.Agent

Stub raises NotImplementedError; E engineer ships the real factory.
"""

from __future__ import annotations


def build_leader(config):
    """Build the Team Leader Agent. Stub — E engineer ships."""
    raise NotImplementedError(
        "build_leader is shipped by the team-assembly engineer (E)."
    )


__all__ = ["build_leader"]
