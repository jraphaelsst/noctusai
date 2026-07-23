# `mcp/n8n` — self-hosted n8n connector MCP (workflow-ops surface)

## What this is

A connector-MCP server that exposes the **n8n workflow facilities
needed to manage + debug a self-hosted instance** — workflow
listing/inspection, execution history, and (the debugging core) the
full error payload of a failed execution — as LLM-callable
`n8n.<service>.<action>` tools. It **composes `mcp/_kit`** (same shape
as `mcp/github` / `mcp/vista`): bootstrap, settings, registry, error
envelope, in-tree seed pin — all inherited, ~0 boilerplate re-derived.

It talks to the n8n **public REST API** (`/api/v1`, header
`X-N8N-API-KEY`) through `noctusai_lib.integrations.n8n`'s `N8nClient`
Protocol
(`seed/lib/backend/noctusai_lib/integrations/n8n/`; Protocol + Fake +
Real + factory, the `mcp/google/tools/youtube.py` / `mcp/meta/tools
/ads.py` "thin connector over the seed adapter" pattern). Every tool
in `mcp/n8n/tools/` builds its client through `mcp/n8n/client
.get_client()` — a settings-resolved DI seam, 424-gated when
unconfigured (stricter than the seed factory's own "no api_key →
Fake" default; see `client.py`'s module docstring). The connector owns
only the MCP write-gate (412), the not-configured gate (424), and the
per-instance `.env` credential resolution — the wire mechanics + error
taxonomy live in the seed, once, shared with every other consumer.

## Tool surface

| Tool | Kind | Wraps |
|---|---|---|
| `n8n.workflow.list` | READ | `GET /workflows` |
| `n8n.workflow.get` | READ | `GET /workflows/{id}` (raw, full fidelity) |
| `n8n.workflow.activate` | WRITE — confirm-gated (412) | `POST /workflows/{id}/activate` |
| `n8n.workflow.deactivate` | WRITE — confirm-gated (412) | `POST /workflows/{id}/deactivate` |
| `n8n.workflow.update` | WRITE — confirm-gated (412) | `PUT /workflows/{id}` (sanitized to name/nodes/connections/settings) |
| `n8n.workflow.create` | WRITE — confirm-gated (412) | `POST /workflows` (sanitized) |
| `n8n.workflow.delete` | WRITE — confirm-gated (412), hard-to-reverse | `DELETE /workflows/{id}` |
| `n8n.workflow.set_tags` | WRITE — confirm-gated (412) | `PUT /workflows/{id}/tags` |
| `n8n.execution.list` | READ | `GET /executions?workflowId=&status=` |
| `n8n.execution.get` | READ | `GET /executions/{id}?includeData=true` + best-effort `error_summary` |
| `n8n.execution.delete` | WRITE — confirm-gated (412) | `DELETE /executions/{id}` |
| `n8n.tag.list` | READ | `GET /tags` |
| `n8n.credential.create` | WRITE — confirm-gated (412) | `POST /credentials` (id/name/type only — secret never echoed back) |
| `n8n.credential.delete` | WRITE — confirm-gated (412), hard-to-reverse | `DELETE /credentials/{id}` |
| `n8n.credential.schema` | READ | `GET /credentials/schema/{type}` |
| `n8n.diagnostics.connection_status` | READ | `client.list_workflows(include_archived=True)` — one call doubles as the reachability probe AND the true workflow count (the seed already exhausts pagination) |

**Debugging recipe:** `n8n.execution.list` (filter `workflow_id` +
`status="error"`) → pick the newest → `n8n.execution.get` → read
`error_summary` (`{node, name, message, stack}`, best-effort) with the
raw `execution` as the source of truth.

Writes follow the **confirm-then-execute** gate (`KB §
PATTERNS/llm-bot-security.md`): `confirm` omitted/false ⇒ typed error
`status 412`, **NO side-effect**. `n8n.workflow.update` is
hard-to-reverse — **always `n8n.workflow.get` first and keep that JSON
as a rollback snapshot** before mutating + updating. It auto-strips
read-only keys (id/active/tags/timestamps/versionId/…) so the n8n PUT
won't 400 on additional properties; activation is managed separately
via activate/deactivate.

## Gated-capability honesty

No config / unreachable host / rejected key is a **typed, never-faked**
signal (CLAUDE.md §1): read tools return an `N8nApiError` envelope
(`status` = 424 not-configured | upstream 4xx/5xx | 502 unreachable),
`n8n.diagnostics.connection_status` reports `configured` / `reachable`.
The server boots cleanly with no config and never fabricates a success.

## Config (`mcp/n8n/.env` or env) — SECRET lives here

| Var | Meaning | Default |
|---|---|---|
| `N8N_BASE_URL` | instance root **or** `…/api/v1` URL (both normalize) | — (required) |
| `N8N_API_KEY` | n8n public-API key (`X-N8N-API-KEY`) — **secret** | — (required) |

Unlike `mcp/github` (where `gh auth` owns the secret in a keyring),
n8n's API key has no external store, so it lives in this connector's
own co-located `.env` (gitignored), **independent of the product/root
`.env`** — the "every connector owns its own auth store" principle
(`KB § INTEGRATIONS/vista.md § 1`). Generate the key in the n8n UI →
**Settings → n8n API → Create an API key**. Rotate if it ever leaks.

## Registration (user-gated)

Add to `.mcp.json` under `mcpServers` **only with explicit user
approval** (MCP keep-list rule, CLAUDE.md §1). It reuses the
`mcp/noctusai/.venv` interpreter (already has the `mcp` package; this
connector adds no deps):

```json
"n8n": {
  "command": "mcp/noctusai/.venv/bin/python",
  "args": ["mcp/n8n/server.py"],
  "cwd": "<repo root>"
}
```

## Tests

```
mcp/noctusai/.venv/bin/python -m pytest mcp/n8n/tests/ -q
```

No network — pure validation (confirm gate, URL normalization) or
dependency injection via `n8n.client.configure_client(...)` (the
seed's `FakeN8nClient`, or a tiny local raising stub for typed-error
paths — never a patch of connector code). Wire-shape assertions (exact
PUT/POST bodies, tag-id-body shape, endpoint paths) live in the seed's
own corpus, `seed/lib/backend/tests/integrations/n8n/`. This suite
pins the tool-name set, dotted naming, the confirm gate (no
side-effect — proven by injecting a client that raises on any call),
gated-capability honesty, and best-effort error extraction from
real-shaped run-data.
