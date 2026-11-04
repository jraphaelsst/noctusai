"""Platform grants (Julia-line CONTRACT D1-D4): agents wires an agent instance of an org to a product by
minting the credentials and DELIVERING them -- nobody pastes a token.

* :mod:`app.grants.registry` -- the server-side product registry (+ the token-scope allow-list);
* :mod:`app.grants.store` -- ``agents.agent_product_grants`` (Protocol + Fake + Supabase + factory);
* :mod:`app.grants.orgs` -- the org directory read from core (options + existence check);
* :mod:`app.grants.service` -- create / rotate / revoke orchestration.

KB: ``PATTERNS/backend/platform-grants.md``.
"""
