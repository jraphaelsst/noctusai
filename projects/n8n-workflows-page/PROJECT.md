# n8n Workflows Page — Project Document

> **Status:** planning complete → wave 1 dispatch.
> **Branch:** `feat/n8n-workflows-page` (tech-lead worktree, off `origin/dev@40a7d144`).
> **Product:** `social-wiring`.
> **Session constraint:** user asked for **zero push** this session (peer agents live). Branch-pointer NOT published — see §8.

---

## 1. Context & Purpose

The operator manages n8n workflows for multiple clients on **one shared self-hosted n8n instance**. Today there is no product surface for this at all: `mcp/n8n/` (16 MCP tools) is agent-side only, and the n8n card in `ClienteModal.tsx` writes credentials that **nothing ever reads back**.

Goal: a `/n8n` page in `social-wiring`, same design spine as the YouTube page, where the operator picks a client and sees **that client's** workflows, organized in folders they control, with full management.

## 2. Confirmed constraints (decided with the user 2026-07-16)

| # | Decision | Rationale |
|---|---|---|
| C1 | **Client key = an n8n tag**, created/chosen by us in the Configurações subtab | n8n **projects are license-gated** — `GET /projects` → 403 on this community-edition instance. Tags are the only viable scoping key. |
| C2 | **Workflows enter a client via a "sem cliente" bucket + drag** → applies the tag through the API | No tag exists on the instance today (verified: all 9 workflows `tags: []`). Tagging must therefore be a **product** capability, not a prerequisite the operator does elsewhere. |
| C3 | **Folder tree is our metadata**, arbitrary nesting, 1 workflow = 1 folder, invisible to n8n | Native n8n folders live inside license-gated projects. Ours is free of that, at the cost of not reflecting back into the n8n UI. |
| C4 | **Full management**: list, activate/deactivate, open-in-n8n, executions, rename, delete, run-via-webhook | User asked for a cockpit, not a read-only mirror. |
| C5 | **Credential is per-client, always**: `base_url` + `api_key` + tag on each client card | User's explicit choice over the hybrid. Accepts repeated entry of the same instance today in exchange for per-client n8n later. |
| C6 | **v1 ships everything**, folders included | No thin-slice; the folder tree is not deferred. |
| C7 | **Run = webhook-only, with an honest disabled button** | The n8n **public API has no execute endpoint** (verified). The UI's `/rest/workflows/run` is internal + session-auth → rejected as a workaround. |

## 3. Verified facts (measured against the live instance, not assumed)

Provenance: raw `GET /api/v1/workflows?limit=50` against the operator's instance, 2026-07-16.

- `GET /workflows` **returns full workflow objects including `nodes`** (36 nodes on the largest). ⇒ `can_run` is computable on the list with **no N+1**, but the payload is heavy: **the backend must strip `nodes` before responding to the FE**.
- Workflow object keys: `active activeVersion activeVersionId connections createdAt id isArchived meta name nodes pinData settings shared staticData tags triggerCount updatedAt versionId`.
- **`isArchived` exists and is true on 2 of 9 workflows** — the list MUST filter archived by default or the page shows junk on day one.
- Trigger flavors in the wild: `n8n-nodes-base.webhook` (4/9), `formTrigger` (3), `executeWorkflowTrigger` (1), `manualTrigger` (1).
- Webhook node `parameters`: `{httpMethod, path, options}` + node-level `webhookId`. `path` is either a friendly slug (`matricula-extractor`) or a bare UUID.
- **A production webhook only fires while the workflow is `active`.** ⇒ `can_run = has_webhook_node AND active AND NOT archived`. Today that is **1 of 9** workflows (`Matrícula Extractor Agent`).
- `base_url` is the **instance root**. API = `{root}/api/v1`, webhook = `{root}/webhook/{path}`. One stored field, two derived URLs. The card's existing `webhook_url` is the wrong shape and is dropped (§7 R1).
- **Cloudflare WAF 403s the default urllib User-Agent** on this host — a browser UA is load-bearing (`mcp/_kit/transport.py:32-34` already documents this for other WAF-fronted connectors). The seed adapter must carry a real UA.
- `PUT /workflows/{id}` 400s on additional properties — body must be sanitized to `name/nodes/connections/settings` (`mcp/n8n/tools/workflow.py:48`).
- `PUT /workflows/{id}/tags` takes tag **ids**, not names (`mcp/n8n/types.py` `WorkflowSetTagsInput`).
- Execution ids are `int`; workflow ids are `str`.

## 3a. Seed-first analysis

- **Consume, don't fork:** the page consumes the canonical organ `SocialDashboardShell` from `@noctusai/lib/design-system` (`seed/lib/frontend/src/design-system/dashboard/SocialDashboardShell.tsx`). Subtabs are **data**, not files. `ConnectedAccountSwitcher` already takes `provider` / `providerLabel` ⇒ `provider="n8n"` needs no new component. Enforced by `check_canonical_organ_consumption`.
- **Seed IO module (S1):** `seed/lib/backend/noctusai_lib/integrations/n8n/` ships **Protocol + Fake + Real + factory** — never Protocol-only (`KB § PATTERNS/backend/seed-fake-real-adapter.md`).
- **No new columns:** `integration_accounts` already carries `client_id`, `channel_info JSONB` (provider-specific metadata) and a `status` lifecycle (`wiring|validating|validated|error|disconnected`) from migration `008`. The client tag lives in `channel_info`; a credential-incomplete card is `status='error'`, not a new invention.
- **Open boundary question** (architect advisory in flight): `mcp/n8n/` already encodes the API facts above in a *sync/urllib/agent-side* layer with its own venv. Is the seed adapter N=2-accept (different layer + transport) or is there a real shared seam? Verdict lands in §11 before S1 dispatch.

## 4. Scope

**In:** seed n8n adapter · folders migration · backend n8n module · `/n8n` page (Workflows + Configurações subtabs, folder tree, drag-and-drop, untagged bucket) · client-card reshape · sidebar + route.

**Out:** reflecting folders back into n8n · running non-webhook workflows · editing workflow graphs (we deep-link into n8n for that) · n8n credential management.

## 4a. Dispatch routing

### 4a.1 Slice → Lens table

| Slice | Lens | Paths (collision zone) | Wave |
|---|---|---|---|
| S1 — seed n8n adapter (Protocol/Fake/Real/factory) | `backend-engineer` | `seed/lib/backend/noctusai_lib/integrations/n8n/` + its tests | 1 |
| S2 — folders migration + RLS | `backend-engineer` | `products/social-wiring/backend/migrations/024_n8n_folders.sql` | 1 |
| S3 — backend n8n module | `backend-engineer` | `products/social-wiring/backend/app/modules/n8n/` + tests | 2 |
| S4 — page, subtabs, folder tree, dnd | `frontend-engineer` | `products/social-wiring/frontend/src/pages/N8n.tsx`, `components/n8n/`, `hooks/useN8n*.ts`, `App.tsx` | 2 |
| S5 — client-card reshape | `frontend-engineer` | `products/social-wiring/frontend/src/components/ClienteModal.tsx` | 1 |

### 4a.2 Collision protocol (decided at dispatch, not at merge)

🔴 **`feat/seed-auth-router-promotion` (engineer A, `on_going`) claims `products/social-wiring/backend/`.** Our S3 files are new and disjoint — **except router registration**.

⇒ **No engineer touches `app/main.py`.** S3 delivers the module + an `APIRouter` export and STOPS. The tech-lead registers the router at integration time, after A lands. An engineer that believes it must edit `main.py` **blocks and surfaces** instead.

Peer branches checked: `seed-kanban-organ` (touches `seed/lib/frontend/` — we only read), `erp-org-from-db-fanout` (touches `seed/lib/backend/.../api/auth/` — disjoint from `integrations/n8n/`), `erp-fe-cookie-session` (erp only).

### 4a.3 Routes-not-taken (pre-rejected by tech-lead)

- **n8n projects as the client key** — 403, license-gated. Not available at any effort.
- **`/rest/workflows/run` (n8n's internal endpoint)** — would make "run" work on every workflow, rejected: undocumented, session-auth, breaks on upgrade. Violates the no-workarounds rule.
- **Folder paths encoded as extra n8n tags** — pollutes the instance tag list and couples folder rename to an external write.
- **Hybrid/platform-level credential** — user chose per-client explicitly (C5).

### 4a.4 Notes — surface + delivery

Every engineer returns a `delivery` note, or `surface` + BLOCK when re-routing mid-flight. Two-leg footer (`drift-found:` / `scoped-improvement:`) mandatory. Engineers SURFACE; tech-lead RESOLVES.

## 5. The FE↔BE contract (S0 — authored before S3/S4 dispatch; both build to this)

Module prefix `/api/n8n`. Shape mirrors `app/modules/youtube/`: concrete `response_model`, **bare typed responses (no envelope)**, `auth: tuple = Depends(get_current_user_org)` unpacked to `coerce_org_uuid(raw_org)`, errors via `HTTPException`.

`account_id` is `integration_accounts.id` (provider=`n8n`, org-scoped by RLS). The switcher supplies it. **No new accounts endpoint** — `ConnectedAccountSwitcher` already reads `/api/integrations/accounts`.

### 5.1 Schemas

```
N8nTagOut          { id: str, name: str }
N8nFolderOut       { id: UUID, name: str, parent_id: UUID | null, position: int }

N8nWorkflowOut {
  id: str                    # n8n workflow id (str, never int)
  name: str
  active: bool
  archived: bool
  tags: list[N8nTagOut]
  folder_id: UUID | null     # our placement; null = tree root
  can_run: bool              # has_webhook_node AND active AND NOT archived
  run_blocked_reason: str | null   # null iff can_run; else the honest reason
  open_url: str              # {base_url}/workflow/{id} — deep link into n8n
  updated_at: datetime | null
}                            # NOTE: `nodes` is NEVER serialized to the FE

N8nWorkflowListResponse  { workflows: list[N8nWorkflowOut], folders: list[N8nFolderOut] }
N8nExecutionOut  { id: int, status: str | null, mode: str | null,
                   started_at: datetime | null, stopped_at: datetime | null }
N8nExecutionListResponse { executions: list[N8nExecutionOut] }
N8nRunResult     { workflow_id: str, dispatched: bool, http_status: int | null }
N8nSettingsOut   { account_id: UUID, base_url: str | null, has_api_key: bool,
                   tag: N8nTagOut | null, status: str, reachable: bool | null }
```

`has_api_key: bool` — the key is **never** echoed back (write-only), mirroring the n8n credential contract.

### 5.2 Endpoints

| Method | Path | Query / Body | Returns | Notes |
|---|---|---|---|---|
| GET | `/api/n8n/workflows` | `account_id`, `scope=client\|unassigned`, `include_archived=false` | `N8nWorkflowListResponse` | `scope=client` → tag-filtered; `scope=unassigned` → workflows with no client tag (the bucket). Folders returned in the same payload — one round-trip renders the tree. |
| POST | `/api/n8n/workflows/{id}/assign` | `{account_id}` | `N8nWorkflowOut` | Adds the client's tag (preserves other tags). The drag-into-client action. |
| DELETE | `/api/n8n/workflows/{id}/assign` | `{account_id}` | `N8nWorkflowOut` | Removes the client's tag → back to the bucket. Also clears placement. |
| PATCH | `/api/n8n/workflows/{id}` | `{account_id, name?, active?, folder_id?}` | `N8nWorkflowOut` | Rename → GET+sanitize+PUT round-trip. `active` → activate/deactivate. `folder_id` → our table only. Fields independent; any subset. |
| DELETE | `/api/n8n/workflows/{id}` | `{account_id}` | `204` | Hard-to-reverse; FE confirms first. |
| POST | `/api/n8n/workflows/{id}/run` | `{account_id}` | `N8nRunResult` | **409** + reason when `can_run` is false. Never fakes a dispatch. |
| GET | `/api/n8n/workflows/{id}/executions` | `account_id`, `limit=20` | `N8nExecutionListResponse` | |
| GET | `/api/n8n/tags` | `account_id` | `list[N8nTagOut]` | Feeds the tag picker in Configurações. |
| POST | `/api/n8n/tags` | `{account_id, name}` | `N8nTagOut` | Create-tag-inline when the client has none yet. |
| GET | `/api/n8n/settings` | `account_id` | `N8nSettingsOut` | Includes a live reachability probe. |
| PUT | `/api/n8n/settings` | `{account_id, base_url?, api_key?, tag_id?}` | `N8nSettingsOut` | Writes credential (Fernet) + `channel_info.tag`. Flips `status`. |
| GET | `/api/n8n/folders` | `account_id` | `list[N8nFolderOut]` | |
| POST | `/api/n8n/folders` | `{account_id, name, parent_id?}` | `N8nFolderOut` | |
| PATCH | `/api/n8n/folders/{folder_id}` | `{name?, parent_id?, position?}` | `N8nFolderOut` | Reparent = drag. **422 on a cycle** (folder into its own descendant). |
| DELETE | `/api/n8n/folders/{folder_id}` | `?reassign_to=<uuid\|null>` | `204` | Children + workflows move to `reassign_to` (default: parent). Never orphans a workflow. |

### 5.3 Status codes (uniform)

`401` unauthenticated (strict — never `in (401, 404)`) · `403` account not in caller's org · `404` unknown account/workflow/folder · `409` run blocked (not webhook-runnable) · `422` invalid tree op (cycle) · `424` account credential missing/incomplete (`status='error'` — the reconnect signal) · `502` n8n unreachable/auth-failed upstream.

**424 vs 502 is load-bearing:** 424 = *we* are not configured (fix the card); 502 = *n8n* said no (fix the instance). A "succeeded empty" must never be reachable through either path — gated-capability honesty.

## 6. Data model (S2 — migration `024_n8n_folders.sql`)

```
social_wiring.n8n_folders
  id UUID PK default gen_random_uuid()
  org_id UUID NOT NULL                       -- RLS anchor, mirrors 011_rls_current_org_id
  account_id UUID NOT NULL REFERENCES social_wiring.integration_accounts(id) ON DELETE CASCADE
  parent_id UUID REFERENCES social_wiring.n8n_folders(id) ON DELETE CASCADE
  name TEXT NOT NULL
  position INT NOT NULL DEFAULT 0
  created_at / updated_at TIMESTAMPTZ
  UNIQUE (account_id, parent_id, name)       -- no two same-named siblings

social_wiring.n8n_workflow_placement
  org_id UUID NOT NULL
  account_id UUID NOT NULL REFERENCES social_wiring.integration_accounts(id) ON DELETE CASCADE
  workflow_id TEXT NOT NULL                  -- n8n id — str, NOT uuid
  folder_id UUID REFERENCES social_wiring.n8n_folders(id) ON DELETE SET NULL
  PRIMARY KEY (account_id, workflow_id)      -- 1 workflow = 1 folder, per account
```

- Placement is keyed `(account_id, workflow_id)` — a workflow carrying two clients' tags appears for both, each with its own independent organization. No conflict by construction.
- `folder_id ON DELETE SET NULL` ⇒ a deleted folder drops its workflows to the root rather than deleting them.
- RLS org-scoped via `current_org_id()`, matching `011_rls_current_org_id.sql`. Cycle prevention is enforced in the service (§5.2 `422`), not by a CHECK.

## 7. Accepted divergences (triage at decision time)

- **R1 — `webhook_url` dropped from the client card.** [A] Accept. It cannot serve the page (§3: run URLs are derived per-workflow from the webhook node, not from a stored account-level URL). Any existing row keeping it is inert. If a consumer of `credential.webhook_url` surfaces, this flips to [F].
- **R2 — existing n8n cards render as "incomplete / reconnect".** [A] Accept. The credential is one Fernet blob; a row written pre-reshape has no `base_url`. It maps to the **existing** `status='error'`, so the UI degrades honestly instead of failing silently at call time.
- **R3 — "run" covers 1 of 9 workflows today.** [A] Accept, user-informed. The button is honest-disabled elsewhere. Reconsider if the ratio stays this low in real use.

## 8. Open questions / blockers

1. **Branch-pointer unpublished** (user: zero push). We are invisible on the global map while peers touch `products/social-wiring/`. MUST publish before integration — tracked as task #1.
2. **Architect verdict on the `mcp/n8n` ↔ seed-adapter boundary** — in flight; lands in §11 before S1 dispatch.
3. **Untracked at repo root**: `PLANO-LANCAMENTO-LIVRO.{md,docx}` — user content, not ours to delete or commit. Surfaced to the user; not blocking (untracked root files do not propagate into worktrees).

## 9. Success criteria

- Sidebar → `/n8n` → pick a client → their workflows appear, filtered by the client's tag, arranged in folders the operator built.
- A workflow dragged out of the "sem cliente" bucket gets the tag **in n8n** and shows up under the client on reload.
- Folders nest, rename, reparent by drag; deleting a folder never loses a workflow.
- Activate/deactivate/rename/delete round-trip to n8n and survive reload.
- "Executar" runs `Matrícula Extractor Agent`; every non-runnable workflow shows a disabled button **with the reason**.
- Archived workflows are hidden unless explicitly asked for.
- A card with no `base_url` shows "reconnect", never a silent empty list.

## 11. Change log

- **2026-07-16** — Planning closed with the user (C1–C7). Live-instance facts measured (§3): nodes-on-list, `isArchived` on 2/9, run-eligibility 1/9, WAF-UA requirement, projects 403. Contract authored (§5). Collision protocol with engineer A set (§4a.2). Architect advisory dispatched on the adapter/connector boundary.
