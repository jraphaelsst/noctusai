"""SEC hotfix 2026-10-06 — the legacy-JWT bridge takes the org from the TRUSTED
``noctus_users`` row, never ``user_metadata.org_id``.

The shared fixture authenticates a user whose METADATA org is ``DEFAULT_ORG_ID``.
Before the fix, an owner of org A who wrote org B's id into their own metadata
became admin of org B (role from the trusted row, org from metadata).
"""
from __future__ import annotations

from uuid import UUID

from tests.routers.conftest import DEFAULT_ORG_ID, seed_org_role

_PERSONA = {"nome": "Julia", "papel": "assistente", "model": "claude-sonnet-5", "effort": "medium"}
_OTHER_ORG = UUID("22222222-2222-4222-8222-222222222222")


def test_owner_of_other_org_cannot_read_metadata_orgs_persona(agents_client):
    # Victim org (== the spoofed metadata org) has a published persona.
    agents_client.stores.agents.ensure_default_agents(DEFAULT_ORG_ID)
    seed_org_role(agents_client, org_id=DEFAULT_ORG_ID, role="owner")
    assert agents_client.put("/api/agents/julia/persona", json=_PERSONA).status_code == 200

    # The SAME user is, per the trusted row, an owner of ANOTHER org only.
    seed_org_role(agents_client, org_id=_OTHER_ORG, role="owner")
    resp = agents_client.get("/api/agents/julia/persona")
    assert resp.status_code == 404, resp.text  # sees their own (empty) org, not the victim's


def test_owner_of_other_org_cannot_write_metadata_orgs_persona(agents_client):
    agents_client.stores.agents.ensure_default_agents(DEFAULT_ORG_ID)
    seed_org_role(agents_client, org_id=_OTHER_ORG, role="owner")
    agents_client.put("/api/agents/julia/persona", json=_PERSONA)  # lands in _OTHER_ORG (or 4xx)

    # Nothing was written into the metadata (victim) org.
    seed_org_role(agents_client, org_id=DEFAULT_ORG_ID, role="owner")
    assert agents_client.get("/api/agents/julia/persona").status_code == 404


def test_user_without_trusted_row_is_refused_even_if_metadata_names_an_org(agents_client):
    agents_client.mock_supabase.set_table_data("noctus_users", [])
    resp = agents_client.get("/api/agents/julia/persona")
    assert resp.status_code == 403, resp.text
