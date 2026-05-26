# n8n connector MCP — `mcp/n8n`

> The **self-hosted n8n workflow-ops surface** exposed as LLM-callable
> tools: workflow list/inspect, execution history, and the full error
> payload of a failed execution (the debugging core). Talks to the n8n
> public REST API (`/api/v1`, `X-N8N-API-KEY`). Composes `mcp/_kit`
> (same shape as github/vista). Built 2026-05-19.

## Why it exists

The `claude.ai`-managed n8n connector binds to the vendor's hosted side
— it can't reach a **self-hosted** instance (`n8n.noctusai.com`):
authenticates fine, then lists zero workflows / "not found". So this
connector wraps the instance's own **public REST API** with an
operator-issued API key — the only path to manage/debug self-hosted
n8n workflows from an agent.

## Tool surface (`n8n.<service>.<action>`, 3-segment dotted)

| Tool | Kind | REST wrapped |
|---|---|---|
| `n8n.workflow.list` | READ | `GET /workflows` (active/name filter) |
| `n8n.workflow.get` | READ | `GET /workflows/{id}` (raw, full fidelity) |
| `n8n.workflow.activate` | WRITE 🔒 confirm | `POST /workflows/{id}/activate` |
| `n8n.workflow.deactivate` | WRITE 🔒 confirm | `POST /workflows/{id}/deactivate` |
| `n8n.workflow.update` | WRITE 🔒 confirm | `PUT /workflows/{id}` (sanitized → name/nodes/connections/settings) |
| `n8n.workflow.create` | WRITE 🔒 confirm | `POST /workflows` (sanitized) |
| `n8n.workflow.delete` | WRITE 🔒 confirm (hard-to-reverse) | `DELETE /workflows/{id}` |
| `n8n.workflow.set_tags` | WRITE 🔒 confirm | `PUT /workflows/{id}/tags` |
| `n8n.credential.create` | WRITE 🔒 confirm | `POST /credentials` (`{name,type,data}`; secret never echoed back) |
| `n8n.credential.delete` | WRITE 🔒 confirm (hard-to-reverse) | `DELETE /credentials/{id}` |
| `n8n.credential.schema` | READ | `GET /credentials/schema/{type}` (discover required `data` keys) |
| `n8n.execution.delete` | WRITE 🔒 confirm | `DELETE /executions/{id}` |
| `n8n.tag.list` | READ | `GET /tags` |
| `n8n.execution.list` | READ | `GET /executions?workflowId=&status=` |
| `n8n.execution.get` | READ | `GET /executions/{id}?includeData=true` + best-effort `error_summary` |
| `n8n.diagnostics.connection_status` | READ | `GET /workflows?limit=1` probe |

- Writes: confirm-then-execute (`KB § PATTERNS/security/llm-bot-security.md`).
  `confirm` ≠ true ⇒ typed error `status 412`, ¬ side-effect.
- `n8n.workflow.update` (`PUT /workflows/{id}`) is hard-to-reverse —
  ALWAYS `n8n.workflow.get` first ∧ keep that JSON as a rollback
  snapshot before mutate→update. Handler auto-strips read-only keys
  (id/active/tags/timestamps/versionId/…) so the PUT won't 400 on
  additional properties; activation managed separately. Added
  2026-05-19 (user asked to programmatically fix a workflow).
- **Debug recipe**: `execution.list` (`workflow_id` + `status="error"`)
  → newest → `execution.get` → read `error_summary`
  `{node,name,message,stack}` (best-effort; raw `execution` = source of
  truth, `None` summary never fabricated).
- **Credentials — so workflows stop hard-coding secrets inline.**
  `credential.create` (`POST /credentials`) registers a secret once;
  nodes then reference it by id. n8n stores credential `data`
  **write-only by design** — the instance never echoes a stored secret
  back (not even to its own UI), so create returns only id/name/type
  and there is **NO list/get/read-credential public endpoint**. We
  deliberately do NOT invent one (gated-capability honesty — a "list
  credentials" tool would either lie or leak). `credential.schema`
  (`GET /credentials/schema/{type}`) is the *only* credential-discovery
  surface — it returns the *shape* of a type (e.g. `httpHeaderAuth` ⇒
  `{name,value}`), never any stored value. `credential.delete` is
  hard-to-reverse (the secret is unrecoverable; referencing nodes break
  until re-pointed). Added 2026-05-19.
- **Endpoint surface probed live 2026-05-19** (codebase-is-source-of-
  truth applied to an external API — endpoints verified, not assumed).
  Available: workflows · executions · tags · `workflows/{id}/tags` ·
  users · credentials (`POST`/`DELETE`). Deliberately ¬ surfaced:
  `/variables` + `/projects` (403 license-gated on this instance — a
  tool would perpetually 401/403); `/source-control` (404 on this
  version) — triage = accept-with-rationale (re-probe before adding).
  ⚠️ `GET /credentials/schema/{type}` returned **404** on the
  2026-05-19 probe of this instance/version, yet the `credential.*`
  tools were built 2026-05-19 per explicit direction (workflows must
  stop hard-coding secrets). This is **safe by gated-capability
  honesty**: if the endpoint 404s on the live instance, `schema`
  returns a typed never-faked `status 404` envelope — it never
  fabricates a schema; `create`/`delete` (`POST`/`DELETE /credentials`)
  were probe-confirmed available. Prior accept-with-rationale (revisit
  on version bump) thus stands for `schema` *availability*; the tool
  ships now and degrades honestly until the version exposes it.

## Architecture

- Composes `_kit`: `configure_stderr_logging` · `run_stdio_server`
  (stdio bootstrap, PyPI-`mcp`-shadow + in-tree seed pin) ·
  `make_get_settings` · `build_registry` · `typed_error`. Connector
  body ≈ the leaf tool modules + `api.py` only.
- **External seam** = `n8n.api.request_json` (stdlib `urllib`, zero
  deps — mirrors github wrapping stdlib `subprocess`). Single HTTP
  boundary; tests `patch("n8n.api.request_json")` (external-service
  patch sanctioned, CLAUDE.md §1; our code never patched).
- `normalize_base_url` — instance root ∨ `…/api/v1` URL normalize
  identically (operator can't misconfigure the suffix).

## Config — SECRET lives in the connector's own `.env`

`mcp/n8n/.env` (gitignored) — `N8N_BASE_URL` + `N8N_API_KEY`. n8n's API
key has no external store (unlike github's `gh` keyring), so it lives
in the connector's co-located dotenv, **independent of the
product/root `.env`** — the "every connector owns its own auth store"
principle (`KB § INTEGRATIONS/vista.md § 1`; vista's base_url+api_key
shape). Key issued in n8n UI → Settings → n8n API. The key is a
non-expiring JWT — rotate on any leak.

## Gated-capability honesty

No config (424) / unreachable host (502) / rejected key (upstream
4xx) is a typed never-faked envelope (`status` carried);
`connection_status` reports `configured`/`reachable`. Server boots
clean with no config; never fabricates success.

## Registration (user-gated)

`.mcp.json` add **only with explicit user approval** (MCP keep-list
rule, CLAUDE.md §1). Reuses the `mcp/noctusai/.venv` interpreter (has
`mcp`; connector adds no deps):

```json
"n8n": { "command": "mcp/noctusai/.venv/bin/python",
         "args": ["mcp/n8n/server.py"], "cwd": "<repo root>" }
```

## Tests

`mcp/noctusai/.venv/bin/python -m pytest mcp/n8n/tests/ -q` — no
network; pins tool-name set, dotted naming, confirm gate (¬
side-effect), gated-honesty (424), best-effort error extraction from
real-shaped run-data, registry coherence. `tests/test_credential.py`
adds the credential gate/happy/schema/typed-error + no-list/get-by-
design pins (10 tests). 31 tests at the 2026-05-19 credential add.

## First real use (build-session dogfood)

Built to debug workflow `dKXJgslv7_N4w9v1fDqUe` ("Matrícula Extractor
Agent", a WAHA→WhatsApp doc-extraction flow). `execution.get`
pinpointed: node **HTTP Request** url `={{ $json.data.eventMsg.media.
docMessage.URL }}` → `NodeOperationError: URL parameter must be a
string, got undefined` — the WAHA webhook fires for non-document
events (session.status / engine heartbeats / non-doc messages), so
`docMessage` is `null` and the unconditional download runs before the
`VerificaTipoMsg`/`VerificaTipoDoc` switches. Fix = a type/existence
guard *before* HTTP Request.
