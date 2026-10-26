# agents org-specs — the org's own context (seed client + form organ)

> **Purpose.** Consume-side reference for the org-owned agent context: `agents.agent_org_specs`, declared per
> agent definition (`agent_version_specs`: label / help / `texto|texto_longo` / required), filled via
> `GET|PUT /api/studio/agents/{key}/specs` (`require_admin`), read by prompts as `{{org.<chave>}}`.
> Durable and self-contained. Consumers: `agents` Studio (tab "Especificações") and `monica` (page "Contexto").

## What ships

| Layer | Where | Names |
|---|---|---|
| Backend client | `noctusai_lib.integrations.agents` | `AgentsOrgSpecsClient` (Protocol: `get_org_specs(agent_key, *, token)`, `put_org_specs(agent_key, valores, *, token)` -> `OrgSpecs`), `FakeAgentsOrgSpecsClient`, `HttpAgentsOrgSpecsClient`, `make_agents_org_specs_client(*, base_url, allow_fake=False)`, types `OrgSpecs` / `OrgSpecDeclarada` |
| Shared transport + errors | same package | `AgentsHttpTransport` (httpx, timeout/network mapping, `raise_for_status` hook), `raise_for_agents_status`, `AgentsClientError` + `AgentsNotConfigured` / `AgentsTokenInvalid` / `AgentNotFound` / `AgentsBadRequest(.fields)` / `AgentsUpstreamError` / `AgentsTimeout` |
| Frontend organ | `@noctusai/lib/components` (`components/org-specs/`) | `createOrgSpecsHooks(api, { path?, queryKey?, invalidate? })` -> `{ useOrgSpecs, useUpdateOrgSpecs }`; `<OrgSpecsForm hooks agentKey canEdit? notice? intro? emptyMessage? conflictLabels? formatError? />` |

social-wiring's Julia channel client (`app/clients/agents.py`, turns / threads / handoffs, authenticated by the org's
`pk_` channel token) stays product-side: it subclasses `AgentsHttpTransport` and the seed error bases; only the
generic part moved. Fake is never silent: without a base URL the factory raises `AgentsNotConfigured` unless
`allow_fake=True` is passed explicitly.

## Auth: the PUT acts as the logged-in user

The org-specs routes are user routes, not channel routes. The client takes the user's bearer **per call** and
forwards it unchanged, so agents' `require_admin` and RLS decide who may read/write. Never substitute a service
token (a non-admin would then edit the org's context). A 401/403 from agents surfaces as `AgentsTokenInvalid`.

## Product backend proxy (monica recipe)

```python
from noctusai_lib.integrations.agents import (
    AgentsBadRequest, AgentsClientError, AgentsNotConfigured, AgentsTokenInvalid, make_agents_org_specs_client)

def _client():  # base_url = resolve_product_url("agents"); allow_fake only from an explicit dev setting
    return make_agents_org_specs_client(base_url=settings.agents_url, allow_fake=settings.agents_allow_fake)

@router.get("/api/contexto")
async def get_contexto(request: Request):
    return (await _client().get_org_specs(AGENT_KEY, token=bearer_of(request))).as_dict()

@router.put("/api/contexto")
async def put_contexto(body: ContextoIn, request: Request):
    try:
        out = await _client().put_org_specs(AGENT_KEY, body.valores, token=bearer_of(request))
    except AgentsBadRequest as exc:   # re-emit {detail, code, **fields}: the organ pins it on the field
        raise HTTPException(422, detail={"detail": str(exc), "code": exc.code, **exc.fields})
    return out.as_dict()
```
Map `AgentsTokenInvalid` -> 403, `AgentsNotConfigured` -> 503, other `AgentsClientError` -> 502. Frontend:
`const hooks = createOrgSpecsHooks(api, { path: () => "/api/contexto" })` and
`<OrgSpecsForm hooks={hooks} agentKey="monica" canEdit={isAdmin} />`.

## Behavior of the form

Declared fields drive the inputs; PUT sends **every** declared key (blank clears); the saved view is committed to the
cache (`useCacheWriteMutation`) and `invalidate` refetches derived views; unsaved edits show a notice + beforeunload
guard (`useUnsavedChanges`); first load is a skeleton (never "empty"); a 422 whose message starts `<chave>:` is
shown on that field, with `conflitos` named via `conflictLabels`.

## Gaps

- `monica` must be the agent's org-side consumer: the agent definition must declare the specs (platform admin work).
- Tests: `seed/lib/backend/tests/integrations/agents/`, `seed/lib/frontend/src/components/org-specs/OrgSpecsForm.test.tsx`.
