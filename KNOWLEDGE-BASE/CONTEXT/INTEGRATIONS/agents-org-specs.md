# agents org-specs — the org's own context (seed client + form organ)

> **Purpose.** Consume-side reference for the org-owned agent context: `agents.agent_org_specs`, declared per
> agent definition (`agent_version_specs`: label / help / `texto|texto_longo` / required), filled via
> `GET|PUT /api/studio/agents/{key}/specs` (`require_admin`), read by prompts as `{{org.<chave>}}`.
> Durable and self-contained. Consumers: `agents` Studio (tab "Especificações") and `nosnolimiar` (page "Contexto").

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

## Product backend proxy (nosnolimiar recipe)

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
`<OrgSpecsForm hooks={hooks} agentKey="nosnolimiar" canEdit={isAdmin} />`.

## Behavior of the form

Declared fields drive the inputs; PUT sends **every** declared key (blank clears); the saved view is committed to the
cache (`useCacheWriteMutation`) and `invalidate` refetches derived views; unsaved edits show a notice + beforeunload
guard (`useUnsavedChanges`); first load is a skeleton (never "empty"); a 422 whose message starts `<chave>:` is
shown on that field, with `conflitos` named via `conflictLabels`.

## Missing values at run time (agents side)

A placeholder is never rendered raw. Optional + empty: omitted. Required + empty: the turn is NOT refused; the prompt
carries the sentinel `INDISPONIVEL`, the agent says it will check and come back, the org is alerted (in-app +
WhatsApp, once per step per conversation), and a lead who insists and accepts is handed to a person
(`info_indisponivel`, second alert). Publish readiness still requires every required spec. Full policy:
`products/agents/projects/julia-v2/CONTRACT.md` ("Spec substitution policy").

## Staff path: NoctusAI fills a company's specs, authorised by the GRANT (owner decision 2026-11-05)

A company that must NOT hold an agents licence (e.g. One Consultoria, `fd169d29-4d0a-4b04-9a5e-25e69407614d`) still needs its
specs (`nome_imobiliaria`, `creci_j`, ...). SW's `PUT /api/channels/agents/{key}/specs` stays refused (403
`edicao_restrita_plataforma`; `NOC-REMEDIATE[channel-specs-write]`) and the studio org PUT writes only the acting org. The permission
is the **grant** -- one `(agent, product, org)` with its own personal token (`KB § PATTERNS/backend/platform-grants.md`) -- plus the
operator's login:

- `GET /api/studio/plataforma/agents/{key}/products/{product}/orgs` -- the picker: orgs with a LIVE grant (`pendente`/`ativo`), each with `status` (`expirado` when `ativo` past `expires_at`), `especificacoes_editor` and `editavel`.
- `GET|PUT /api/studio/plataforma/agents/{key}/products/{product}/orgs/{org_id}/specs` -- same `OrgSpecsOut` / `{valores}` as the org route.
- Conditions: `require_platform_admin` (401; 403 `platform_admin_required`, admin-MFA posture) AND a grant row for exactly `(org_id, key, product)` that is `ativo` and not expired, else **409 `sem_concessao_ativa`** (`status` in the body: `inexistente|pendente|falhou|revogado|expirado`). `definition_org_grants` alone does not count. `404 produto_desconhecido` for a product/agent pair the registry does not grant; `409 org_sem_instancia` / `grant_agente_divergente` when the grant and the org's instance disagree.
- `agent_product_grants.especificacoes_editor` (migration 064, default `plataforma`): the route allows staff only for `plataforma` (else 409 `editor_nao_plataforma`). `org` is RESERVED: switching a grant to it will let the org's own admins edit through the product; that path is not built, and the switch only makes the staff route refuse -- it opens nothing.
- ONE write path: `aplicar_org_specs` (declared keys, per-type validation, 422 per field in block mode). Audit `specs_org_editadas` lands in the TARGET org with `actor` = the platform admin's user id and `depois` = `{chaves, origem: "plataforma", produto, grant_id, org_alvo, ator_plataforma, chaves_alteradas}` (keys only, never values); the row's `updated_by` is the same person.
- Studio UI: tab "Especificacoes por empresa" (`especificacoes-empresas`) on the platform definition, operator only: product (when more than one) -> company (with each grant's status) -> the same `OrgSpecsForm`; a non-editable grant shows why and no form.
- A revoked/expired grant also stops the agent's channel turns (the token gate checks the grant row, not only the token).

## Gaps

- `nosnolimiar` must be the agent's org-side consumer: the agent definition must declare the specs (platform admin work).
- Tests: `seed/lib/backend/tests/integrations/agents/`, `seed/lib/frontend/src/components/org-specs/OrgSpecsForm.test.tsx`.
