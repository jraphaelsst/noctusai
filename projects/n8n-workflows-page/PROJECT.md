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
- **Seed IO module (S1a):** `seed/lib/backend/noctusai_lib/integrations/n8n/` ships **Protocol + Fake + Real + factory** — never Protocol-only (`KB § PATTERNS/backend/seed-fake-real-adapter.md`).
- **Layout is the mailchimp shape, NOT youtube's.** `KB § PATTERNS/backend/seed-fake-real-adapter.md:16-24` documents `__init__.py` (public surface + factory) / `types.py` (value objects + `@runtime_checkable` Protocol + error hierarchy) / `mappers.py` (pure raw→VO) / `fake_adapter.py` / `<vendor>_adapter.py`. `integrations/youtube/`'s `protocol.py`/`fake.py`/`real.py`/`factory.py` is **off-pattern** — its own docstring claims lineage from `google_calendar`, which does not use that layout either. mailchimp is also the functional twin: external HTTP + per-tenant API key + httpx + `get_mailchimp_client(api_key=None)` → Fake when the key is absent.
- **No new columns:** `integration_accounts` already carries `client_id`, `channel_info JSONB` (provider-specific metadata) and a `status` lifecycle (`wiring|validating|validated|error|disconnected`) from migration `008`. The client tag lives in `channel_info`; a credential-incomplete card is `status='error'`, not a new invention.
- **Provider registry already declares n8n** — `app/services/integration_providers.py:99-120`, `manual_key_fields: [webhook_url, api_key(optional)]`, no `base_url`. S5 **extends this entry**; it does not open a second credential path. `SUPPORTED_PROVIDER_IDS` mirrors the SQL CHECK at `005_integration_accounts.sql:24`, which already includes `'n8n'` ⇒ no migration for the provider id.
- **Multi-account is already navigated.** The seed `CredentialStore` is single-row-per-`(org, provider)`, but this product deliberately persists per-account credentials on the `integration_accounts` row instead (`integration_accounts_router.py:444` says so explicitly). C5 (per-client credentials) therefore needs no seed change.

### 3a.1 Architect verdict — the `mcp/n8n` ↔ seed boundary (RESOLVED, `[F]ormalize`)

The tech-lead's premise ("connectors live in a separate venv ⇒ can't share the seed") was **false**. `mcp/_kit/seed_pin.py:16-20` exists solely to pin `noctusai_lib` to the in-tree seed — itself formalized at N=2 — and `_kit/bootstrap.py:32-39` runs it before any connector imports. ~40 files under `mcp/` import `noctusai_lib`, including `mcp/n8n/tests/test_smoke.py:38`.

The house convention is the opposite of the premise: **the connector is a thin wrapper over the seed adapter** — `mcp/google/tools/youtube.py:1` ("thin wrappers over the seed YouTube client"), `mcp/meta/tools/ads.py:31`. `mcp/n8n/api.py` owns HTTP only because no seed n8n adapter exists yet: the N=1 pre-lift state.

⇒ There is no triage here. Building S1a while leaving `mcp/n8n/api.py:28-69` with its own `normalize_base_url` + status taxonomy **creates** the fork. `KB § PATTERNS/architect/project-execution.md:671`: *"if the cleaner shape IS already cross-cutting and the lift is buildable now, lift now."* Two legs, one commit-set (`no incomplete commits`). User ratified the two-leg scope 2026-07-16.

**Stays connector-side** (the real, narrow boundary): `ConfirmationRequiredError`/412 write-gate (`api.py:45-54` — MCP contract, a product API has its own authz) · the 424 not-configured gate (`api.py:89-94` — the seed factory's equivalent is "no api_key → Fake") · `mcp/n8n/settings.py` env/`.env` single-instance resolution (the product resolves per-org creds from `integration_accounts`).

**Anti-drift mechanism** (so the facts in §3 are not re-learned by trial and error), in order of strength: (1) Protocol + `__init__.py` docstrings as the fact carrier — `integrations/youtube/__init__.py:28-32` is the worked example; (2) `noctus.dev.organ_knowledge_append` (`known_facts`/`errors_encountered`); (3) a seed test corpus at `seed/lib/backend/tests/integrations/n8n/` making the facts executable. A KB prose doc is the weakest and is explicitly **not** the mechanism.

## 4. Scope

**In:** seed n8n adapter · folders migration · backend n8n module · `/n8n` page (Workflows + Configurações subtabs, folder tree, drag-and-drop, untagged bucket) · client-card reshape · sidebar + route.

**Out:** reflecting folders back into n8n · running non-webhook workflows · editing workflow graphs (we deep-link into n8n for that) · n8n credential management.

## 4a. Dispatch routing

### 4a.1 Slice → Lens table

| Slice | Lens | Paths (collision zone) | Wave |
|---|---|---|---|
| S1 — seed n8n adapter (**leg a**) + `mcp/n8n` refactored to consume it (**leg b**) — ONE commit-set | `backend-engineer` | `seed/lib/backend/noctusai_lib/integrations/n8n/`, `seed/lib/backend/tests/integrations/n8n/`, `seed/lib/backend/pyproject.toml`, `mcp/n8n/` | 1 |
| S2 — folders migration + RLS | `backend-engineer` | `products/social-wiring/backend/migrations/024_n8n_folders.sql` | 1 |
| S3 — backend n8n module | `backend-engineer` | `products/social-wiring/backend/app/modules/n8n/` + tests | 2 |
| S4 — page, subtabs, folder tree, dnd | `frontend-engineer` | `products/social-wiring/frontend/src/pages/N8n.tsx`, `components/n8n/`, `hooks/useN8n*.ts`, `App.tsx` | 2 |
| S5 — client-card reshape + provider-registry field-set | `frontend-engineer` | `products/social-wiring/frontend/src/components/ClienteModal.tsx`, `products/social-wiring/backend/app/services/integration_providers.py` | 1 |

**Fix-on-contact carried by S1:** `httpx` is imported by ~10 seed modules (`meta/_meta_api.py`, `mailchimp/client.py`, `vista/client.py`, …) but **undeclared** in `seed/lib/backend/pyproject.toml`, arriving only transitively via supabase/openai. A new httpx-based adapter compounds that debt — and it bites hardest on the connector path, which has its own install. S1 declares it.

### 4a.2 Collision protocol (decided at dispatch, not at merge)

🔴 **`feat/seed-auth-router-promotion` (engineer A, `on_going`) claims `products/social-wiring/backend/`.** Our S3 files are new and disjoint — **except router registration**.

⇒ **No engineer touches `app/main.py`.** S3 delivers the module + an `APIRouter` export and STOPS. The tech-lead registers the router at integration time, after A lands. An engineer that believes it must edit `main.py` **blocks and surfaces** instead.

S5 also reaches into A's subtree for one file (`app/services/integration_providers.py` — the provider field-set). File-disjoint from A's auth-router promotion, so it proceeds — but S5 touches **that file only** on the backend side, and blocks-and-surfaces if it finds itself wanting a second.

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
  UNIQUE (account_id, parent_id, name)       -- no two same-named siblings (non-root only — see below)
  + partial unique index ON (account_id, name) WHERE parent_id IS NULL   -- the root-level half

social_wiring.n8n_workflow_placement
  org_id UUID NOT NULL
  account_id UUID NOT NULL REFERENCES social_wiring.integration_accounts(id) ON DELETE CASCADE
  workflow_id TEXT NOT NULL                  -- n8n id — str, NOT uuid
  folder_id UUID REFERENCES social_wiring.n8n_folders(id) ON DELETE SET NULL
  PRIMARY KEY (account_id, workflow_id)      -- 1 workflow = 1 folder, per account
```

- 🔴 **`UNIQUE (account_id, parent_id, name)` alone is a defective spec** (tech-lead's error, caught by the S2 engineer against a throwaway postgres container before it shipped): SQL treats each `NULL` as distinct for uniqueness, so it does **not** stop two same-named folders at the **root**. The stated intent ("no two same-named siblings") needs BOTH the constraint and a partial unique index `ON (account_id, name) WHERE parent_id IS NULL`. Root dedup is wanted — the UI gives the operator no way to tell two identically-named root folders apart. Fixed in `024` in place (unmerged ⇒ amend, not a remediation migration for a defect that never shipped).
- Placement is keyed `(account_id, workflow_id)` — a workflow carrying two clients' tags appears for both, each with its own independent organization. No conflict by construction.
- `folder_id ON DELETE SET NULL` ⇒ a deleted folder drops its workflows to the root rather than deleting them.
- RLS org-scoped via `current_org_id()`, matching `011_rls_current_org_id.sql`. Cycle prevention is enforced in the service (§5.2 `422`), not by a CHECK.

## 7. Accepted divergences (triage at decision time)

- **R1 — `webhook_url` dropped from the client card.** [A] Accept. It cannot serve the page (§3: run URLs are derived per-workflow from the webhook node, not from a stored account-level URL). Any existing row keeping it is inert. If a consumer of `credential.webhook_url` surfaces, this flips to [F].
- **R2 — existing n8n cards render as "incomplete / reconnect".** [A] Accept. The credential is one Fernet blob; a row written pre-reshape has no `base_url`. It maps to the **existing** `status='error'`, so the UI degrades honestly instead of failing silently at call time.
- **R3 — "run" covers 1 of 9 workflows today.** [A] Accept, user-informed. The button is honest-disabled elsewhere. Reconsider if the ratio stays this low in real use.

## 8. Open questions / blockers

1. **Branch-pointer unpublished** (user: zero push). We are invisible on the global map while peers touch `products/social-wiring/`. MUST publish before integration — tracked as task #1.
2. ~~Architect verdict on the `mcp/n8n` ↔ seed-adapter boundary~~ — **RESOLVED**, see §3a.1. `[F]ormalize`, two legs, one commit-set; user ratified the scope.
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
- **2026-07-16 (later)** — Architect verdict landed (§3a.1) and **corrected three tech-lead errors** before any code was written: (1) the "connectors are a separate venv" premise was false (`_kit/seed_pin.py`) ⇒ S1 grows leg b, the connector refactor, ratified by the user; (2) the planned adapter layout (youtube-shaped) was off-pattern ⇒ mailchimp shape per `KB § PATTERNS/backend/seed-fake-real-adapter.md:16-24`; (3) `integration_providers.py:99-120` already declares the n8n field-set ⇒ S5 extends it rather than opening a second credential path. Plus one fix-on-contact (undeclared `httpx` in the seed pyproject). Worth recording: the advisory cost ~4 minutes and moved three decisions before they became commits.
