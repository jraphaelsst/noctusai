# Invocation context: who invoked, on whose behalf, with what authority (design seed)

> **Status: mapped, not decided.** Origin: owner forward hint, 2026-11-10 (transcript 5ff8685d): "just contextualizing so you're aware of the 'invoker' when we're building api calls … I'm setting something to the future, so you should already be mapping at least, and suggest some solution … This must be as generic as it can be used in many contexts."
> Map produced by the `architect` advisor (read-only, against origin/dev at c5b6d9c36, 2026-11-10). Method trial: `forward-hint-mapping`. Memory: `feedback_forward_hints_map_and_propose.md`.
> **Next gate:** a council at the design stage (triggers `seed_fanout` and `trust_boundary`; seats include `security` and `agents-security`), then a decision record, then 3 pilots. It is built in the post-ship improvement wave the owner set on 2026-11-10, not before.

## 1 · What already exists (six vocabularies that do not connect)

| Mechanism | Where | Captures | Misses |
|---|---|---|---|
| `AuthContext.caller_kind` | `seed/lib/backend/noctusai_lib/api/auth/session/types.py:26,125-138` | user or product, org, user_id, scopes, api_token_id, `principal_agent_id`, `minted_by`, aal | Only 2 kinds. No parent, no purpose. Exists only inside HTTP. |
| `AuditActor` / `ActorKind` | `api/audit/types.py:18,21-42`; `detect.py:37` | user, agent or service. Act-as (`acting_org_id`, `act_as_session_id`) is real on-behalf-of. | `actor_kind` is guessed from the `X-Noctus-Client` header and the User-Agent: declared, not verified. The DB CHECK allows 3 values (`sink.py:17`). |
| `UsageAttribution` (D25) | `integrations/llm/attribution.py:42-55,85` | product, feature, purpose, org, user, agent_key, conversation, request_id → `public.ai_usage` | No invoker kind or chain. A cron or webhook lands only under its product. |
| LLM budget and credits | `integrations/llm/budget.py` | Monthly cap per org, enforced closed on failure. | No cap per invoker, agent or end user. Platform and MCP spend (`vector_costs` ndjson) sits outside `ai_usage`, which is how the OpenAI credit ran out unseen. |
| Correlation id | `api/middleware.py:94-117`; `primitives/_correlation.py` | Read on the way in (`X-Correlation-ID`, `X-Request-ID`) into a ContextVar. | Never sent on outbound calls, so the chain breaks at the social-wiring → agents hop. |
| Approval assertion | `products/agents/backend/app/runtime/assertion.py:62-100` | A signed approval bound to one exact action (approved_by, requested_by, tool, method, path, body hash, 60s lifetime). The best existing model of typed authority. | Lives only in agents. Its docstring already names the seed destination. |
| Julia turn | `products/agents/backend/app/channels/turno.py:672` | `requested_by=service_principal_id(agent.id)` | The agent records itself as the requester. The WhatsApp lead, the webhook and the tenant are lost. social-wiring calls agents with the org's `pk_` token, so agents only sees "product". |
| Domain events | `domain/sql_templates.py:777,842-932` | `actor_id UUID NOT NULL` | No kind, no causation, no on-behalf-of. |
| EOA envelope | KB `PATTERNS/architect/event-oriented-architecture.md:69` | CloudEvents `actorid`, `actorkind`, `causationid`, `correlationid` | Documented only. The E2 store is not shipped as a seed organ. |
| Prod consent | `mcp/noctusai/tools/prod_consent.py:252`; `compliance.py:25448` | Consent phrase checked against the transcript (sha); `recorded_by` kept apart from the decision. | Bound to a file, not to an invocation. |
| Steward and branch pointer | `release_steward.py:33`; `branch_pointer.py:151` | Identity = `CLAUDE_CODE_SESSION_ID` | Subagents share their parent's id: to MCP, a subagent and the tech-lead are the same invoker. |
| MCP `NoctusContext` | `mcp/noctusai/context.py` | A dependency container per tool call | No caller field at all. |
| Scheduler | `api/scheduler.py:188` | Errors per run | No invoker. |

(The 3 `invoker` hits in igig and social-wiring are Postgres `security_invoker`, which is unrelated.)

## 2 · Where the invoker is lost

- **Cross-product HTTP:** correlation is not forwarded, and the pk token turns "end user via agent via product" into plain "product".
- **Delegation chains:** no parent invocation is recorded. The one exception is `act_as_session_id`.
- **LLM cost:** attributed by org and feature, not by invoker. MCP and embedding spend has no account at all.
- **Cross-session messages:** no authority field. "A peer cannot grant" is enforced only by convention.
- **Subagents and councils:** indistinguishable from their parent session. This is the authority-laundering path.
- **Cron jobs and webhooks:** no invoker, no purpose. The webhook `recorded_by` is a free string (`mcp/imovelweb/tools/webhook.py:105`).
- **Declared treated as verified:** `actor_kind` is asserted by the caller but read as if it were fact.

## 3 · Proposed contract: the invocation seam (a proposal, for the council to challenge)

`noctusai_lib.primitives.invocation` holds a frozen `InvocationContext` and a ContextVar. It has no dependencies, like `_correlation`, so the MCP toolkit can import it.

- **Ids:** `id` (uuid7), `parent_id`, `root_id` (equals the correlation id and the W3C trace-id), `depth`.
- **`invoker {kind, id}`:** `kind` is one of `human_user | end_user | product | agent | claude_session | subagent | council | scheduler | webhook | system`. `end_user` is an internal contact uuid, never a phone number.
- **`on_behalf_of {org_id, principal_kind, principal_id}`:** the tenant plus the human principal. Act-as maps here.
- **`authority {kind, ref, scopes, verified_by}`:**
  - `kind` is one of `owner_consent | user_session | token_scope | approval_assertion | grant | none`.
  - Authority is **not transitive**. A child inherits it only through explicit attenuation: a subset of scopes and a shorter lifetime (RFC 8693 delegation, not impersonation).
  - Anything relayed, or arriving from a peer root, resets to `none`.
  - `owner_consent` is valid only when its ref binds to the same root and session as the executor. That is prod_consent generalized.
- **`surface`:** `http | mcp | llm | job | webhook | session_message | deploy`.
- **Purpose fields:** `purpose`, `feature`, `product`, `agent_key`, `conversation_id`.
- **`cost_account`:** derived; an org or `platform`.

**Propagation:**
- **Python:** the ContextVar plus `invocation_scope(...)` (`_blocking.py` and the scheduler already use `copy_context`).
- **HTTP:** W3C `traceparent` plus a signed `X-Noctus-Invocation` compact JWS, reusing the HS256 machinery from `assertion.py`.
  - An `InvocationMiddleware` is mounted in `configure_app`, next to `UsageAttributionMiddleware`.
  - Unsigned claims are recorded with `authority=none`.
  - Outbound calls go only through a seed client factory that injects the header.
- **MCP:** a `_meta` key `ai.noctus/invocation`. `NoctusContext.invocation` falls back to the session id.
- **Events:** add `invocation_id`, `causation_id`, `invoker_kind`, `on_behalf_of`, `authority_kind` to E1 `<agg>_events` and to `ai_usage`. Roll out expand → migrate → contract.

**Seed IO, Fake + Real + factory:**
- `InvocationSink` (writes `public.invocations`, an E1 log);
- `InvocationSigner` (HMAC);
- `AuthorityVerifier` (transcript consent, approval assertion, token scope).

**Today's fields map in without a rewrite:**

| Today | Becomes |
|---|---|
| `caller_kind="user"` | `human_user` + `user_session(aal)` |
| `caller_kind="product"` | `product` + `token_scope` |
| `principal_agent_id` | `agent`, with `minted_by` as the principal |
| `ActorKind` | moves to `client_hint`, declared and never used for authority |
| `UsageAttribution` | a projection of the invocation |
| `requested_by` / `approved_by` | invoker id / authority ref |
| `recorded_by` | the executor invocation, plus a new `decided_by` |

`AuthContext` gains one optional field, appended at the end.

## 4 · What it unlocks

1. Cost caps per invoker and per end user, plus a platform account for MCP and embedding spend. An exhausted credit raises an alert instead of passing silently.
2. One consent-provenance verifier for prod_consent, ship_consent, approval assertions and council ratification.
3. An audit timeline per `root_id`: WhatsApp lead → webhook → Julia turn → LLM → tool write.
4. Delegation limits: maximum depth and scope attenuation for subagents and councils; peers are refused grants by construction.
5. A tenant-facing "who did this, for whom" view, plus LGPD access logs per data subject. The Assistant's read log (LGPD checklist item 9) is a first consumer.

## 5 · Risks and rollout

- **Risks:**
  - Header forgery: sign the header; never take authority from a declared kind.
  - PII in ids.
  - Write volume: record writes, LLM calls and tool calls; sample reads.
  - Raw executors or `httpx` calls that bypass the factory and lose the context.
  - **Unverified:** whether the Claude harness exposes a distinct subagent identity to hooks or MCP.
- **Classification:** the wire format and the event columns are a one-way door (T2/T3), so a decision record is needed before the plan is locked.
- **Pilots:**
  1. The agents Julia turn + `ai_usage` (end-user invoker, cost).
  2. The social-wiring → agents hop (signed header, correlation forwarding; a trust boundary).
  3. The MCP toolkit (prod_consent, ship_consent, release_steward, vector_costs: `claude_session` and `subagent` invokers, and the rule that a peer cannot grant).
- **Fitness functions:**
  - A keeper `check_invocation_propagation` that flags raw outbound clients to noc hosts.
  - After the contract phase, `ai_usage.invoker_kind` becomes NOT NULL.
  - A test that a forged or unsigned header always ends up with `authority=none`.

**Sources:** CloudEvents 1.0 (cited in the EOA doc) · RFC 8693 §4.1 (`act`, `may_act`) · MCP spec 2025-06-18 basic `_meta` rules · W3C Trace Context (not re-read).
