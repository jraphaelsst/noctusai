# AppSec craft canon — the method layer of the `security` agent

> **What it is.** The application-security profession's canon (threat modeling, severity, standards,
> authN/authZ, data-layer security, input/output, supply chain, edge, testing, review) mapped onto THIS
> platform: FastAPI products built from the seed, Supabase (PostgREST + RLS + Storage + GoTrue), a
> Cloudflare named tunnel in front of one VPS, WAHA for WhatsApp, LLM providers behind
> `noctusai_lib.integrations.llm`. Owned by agent `security`. Born 2026-11-05 (agent-refinement W1-S2,
> from the verified audit `archive/projects/2026-11-05/01-agent-refinement/audits/audit-security-agents-security.md`).
>
> **Why.** The house lessons (incident ⇒ keeper) are above average, but a reviewer with only lessons can
> only find bugs we already had. The canon adds the method that finds the NEXT class: a threat model per
> trust boundary, a severity vector instead of vibes, a standards map that makes uncovered chapters
> visible, and a fail-closed doctrine that settles the fail-open-vs-fail-closed contradictions our own
> docs carried.
>
> **How to use it.** Not auto-loaded. Open the section the task needs (§ index below). The **house
> mechanism always wins over the general canon**: when a seed helper, keeper or KB pattern already
> solves the problem, the finding says "use `<mechanism>`", never "implement OWASP X". The canon is
> how you *find and rank*; the house mechanism is how it gets *fixed*. Siblings:
> `KB § PATTERNS/security/secure-code-review-checklist.md` (the per-diff checklist) and
> `KB § PATTERNS/security/incident-response-playbook.md` (when something already happened).
> AI-agent threats live in `KB § PATTERNS/security/ai-agent-security-canon.md` (agent `agents-security`).

**Standard term ↔ house term.**

| Standard term | House term / mechanism |
|---|---|
| Tenant | org (`org_id`; trusted source `public.noctus_users`) |
| Privileged DB credential | service-role / admin client (`get_admin_client()`, `get_scoped_admin_client()`) — bypasses RLS |
| Policy enforcement point (API) | `Depends(get_current_user_org)` built by `make_get_current_user_org` |
| Static analysis rule | keeper (`mcp/noctusai/tools/noctus/dev/compliance.py` `check_*`), run by pre-commit + CI |
| Release gate | `noctus.dev.predeploy_check` (+ CI green) |
| Risk acceptance | accept-with-rationale catalog (`KB § PATTERNS/common/accept-with-rationale.md`) |
| Tracked deferral / POA&M item | `NOC-REMEDIATE[<class>]` marker (`KB § PATTERNS/common/remediation-markers.md`) |
| Privacy risk register | `LGPD-WARNINGS.md` (fed by `noctus.dev.lgpd_flag`) |
| Golden image / secure baseline | the seed (`products/seed/`, `seed/lib/backend/noctusai_lib/`) |

**Section index.** §1 scope · §2 threat modeling · §3 reference DFD · §4 severity · §5 standards map ·
§6 fail-closed doctrine · §7 authN/authZ · §8 Supabase/Postgres · §9 input/output · §10 secrets + supply
chain · §11 edge + containers · §12 security testing · §13 anti-patterns · §14 decision checklists ·
§15 worked examples · §16 sources.

---

## 1 · Scope and posture

- **In scope:** every product backend + SPA, the seed and seed-lib, Supabase schemas/policies/buckets,
  the fleet compose + tunnel, the MCP dev toolkit's prod-touching tools, CI security gates (read-only:
  CI workflow edits belong to the git/merge redesign session — flag, do not author).
- **Authorized defensive work only.** Findings are proven by reading code, running read-only tools, or
  a test the executor writes; never by attacking prod.
- **Advisor contract.** `security` writes findings + remediation + proof-test specs; executors fix; the
  tech-lead routes. Every finding carries file:line evidence and a severity vector (§4).

---

## 2 · Threat modeling

**Principle.** Threat modeling answers the Threat Modeling Manifesto's four questions: *What are we
working on? What can go wrong? What are we going to do about it? Did we do a good enough job?* Do it at
design lock, when a NEW trust boundary appears (new provider, new public route, new bucket, new role), and
when a NEW personal-data category enters (`KB § PATTERNS/security/lgpd.md` §2).

**Method — pick by question.**

| Question | Tool | Output |
|---|---|---|
| What can an attacker do at this boundary? | **STRIDE-per-element** on the §3 DFD (Spoofing · Tampering · Repudiation · Information disclosure · Denial of service · Elevation of privilege) | ranked threats per element |
| What can go wrong for the *data subject*? | **LINDDUN** (Linking · Identifying · Non-repudiation · Detecting · Data disclosure · Unawareness · Non-compliance) | privacy threats ⇒ LGPD flags / RIPD trigger |
| How exactly does the P0 happen? | **Attack tree** (goal at the root, AND/OR sub-goals, leaves = concrete preconditions) | the cheapest leaf to cut |
| Did we cover the profession's list? | §5 standards map (ASVS chapter ↔ our doc ↔ keeper) | uncovered chapters |

**How it applies here.** Our recurring incident classes map one-to-one onto STRIDE letters at a few
boundaries: forged webhooks = S/T at TB5 (§15 WE-2); public bucket = I at TB4 (§15 WE-1);
`user_metadata` org = E at TB3 (§15 WE-3); fail-open limiters = D at TB6 (`KB § PATTERNS/security/ai-agent-security-canon.md` §5).
So a STRIDE pass on the §3 diagram is not academic — it is the shape our real bugs already had.

**Output shape (what the agent returns).** (1) the DFD slice touched, boundaries named TB1..TB7;
(2) a threats table `id · element · STRIDE/LINDDUN letter · scenario · existing control (file:line) ·
gap · severity vector · fix where`; (3) named mitigations pointing at house mechanisms; (4) "did we do
enough": the proof tests that would fail if the mitigation regressed.

**Checklist.**
- [ ] Every element on the diagram crossed by the change has a STRIDE row (even "N/A — reason").
- [ ] Personal data in the flow ⇒ LINDDUN pass + `noctus.dev.lgpd_flag` where an answer is "don't know".
- [ ] Each P0/P1 has an attack tree or an explicit precondition list.
- [ ] Each mitigation names the mechanism AND the regression test.

**Anti-patterns.** Threat-model the feature but not the *new boundary* it creates (the bucket flag is a
boundary, §8). Listing threats without existing-control evidence (that is a brainstorm, not a model).
A model with no "did we do enough" leg — it is never re-checked.

---

## 3 · Reference architecture as a DFD (trust boundaries)

```
 [Lead / user / attacker]                     [Providers: WAHA, Meta, Resend, OLX, Stripe, Asaas]
        |                                                  |
   TB1  |  HTTPS, Cloudflare edge (WAF, 1010 UA ban)        | TB5 signed webhooks (HMAC / Svix / Basic)
        v                                                  v
 [Cloudflare named tunnel] --TB2 (cloudflared -> docker network; origin port never public)--+
        |                                                                                   |
        v                                                                                   v
 [Product container: SPA static + FastAPI]  <-- TB3: browser JWT (Supabase access token) --> [Browser SPA]
        |   deps: get_current_user_org, consent_required, limiter          |
        |                                                                  | TB3b: browser -> PostgREST/Storage
   TB4  |  user-scoped client (RLS applies)  /  service role (RLS bypass)  |      directly (publishable key +
        v                                                                  v      user JWT; RLS is the ONLY gate)
 [Supabase: PostgREST + Postgres RLS + Storage routes (public/sign/authenticated) + GoTrue]
        |
   TB6  |  egress: LLM providers (Anthropic/OpenAI/Gemini via noctusai_lib.integrations.llm),
        v          WAHA send, Google/Meta APIs, e-mail   => personal data leaves (LGPD Art. 33)
 [Third parties]

 TB7 ops plane: dev laptop + MCP toolkit (noctus.vps.*, deploy_image, predeploy_check) + GitHub Actions
      --SSH forced-command keys--> VPS (compose fleet, WAHA internal-only, cache-pg)
```

| Boundary | Gate today (house mechanism) | Where it is documented |
|---|---|---|
| TB1 edge | CF WAF; programmatic callers need a browser UA (error 1010) | `KB § PATTERNS/frontend/core-url-routing.md` (§8) · `KB § PATTERNS/devops/prod-watchdog.md` |
| TB2 tunnel → origin | ingress derived from one source of truth; prod exposure is the owner's decision | `KB § PATTERNS/devops/tunnel-ingress-source-of-truth.md` · `KB § PATTERNS/devops/prod-exposure-consent.md` |
| TB3 browser → API | Supabase JWT validated by GoTrue round-trip (`validate_bearer_token`, `seed/lib/backend/noctusai_lib/api/auth/__init__.py:200`); 401 iff provider rejected | `KB § backend/07-AUTH-SECURITY.md` |
| TB3b browser → PostgREST | RLS + grants + schema exposure; `anon` USAGE only | `KB § PATTERNS/backend/database-rls.md` |
| TB4 API → DB | user client = RLS; service role = explicit `.eq("org_id", …)` from `noctus_users` | `KB § PATTERNS/backend/no-metadata-authz.md` |
| TB5 provider → receiver | `webhook_endpoint(...)` verify-before-side-effect, 5-pin contract | `KB § PATTERNS/security/webhook-signatures.md` |
| TB6 API → third party | LLM seam (budget, ledger, consent); egress listed in `LGPD-WARNINGS.md` | `KB § PATTERNS/security/lgpd.md` |
| TB7 ops → VPS | forced-command SSH keys; `vps.exec` hard-deny/read-allowlist/confirm gate | `KB § PATTERNS/devops/ssh-deploy-key-restrictions.md` |

**The boundary people forget: TB3b.** Any table/view/bucket granted to `authenticated`/`anon` is
reachable from the browser *without* our FastAPI in the path; our API-layer checks do not apply there.
That is why grants and views (§8) are first-class findings, not hygiene.

---

## 4 · Severity and prioritization

**Principle.** Every finding carries a vector, and the P-level derives from it — never from tone.
Three inputs: **CVSS v4.0 base** (technical severity), **EPSS** (probability of exploitation in the next
30 days — only for findings that are a published CVE), and **reachability** (is the vulnerable code on a
path our deployed code executes, with attacker-controlled input?). One house multiplier: **LGPD impact**
(the Res. CD/ANPD 15/2024 art. 5 categories — sensitive, children/elderly, financial, authentication,
secrecy-protected, large-scale data).

**Mapping table (house rule).**

| P-level | Condition (first match wins) | Clock |
|---|---|---|
| **P0** | CVSS ≥ 9.0 reachable; ∨ CVSS ≥ 7.0 reachable ∧ (unauthenticated ∨ cross-tenant ∨ LGPD art. 5 category); ∨ CVE on CISA KEV / EPSS ≥ 0.5 and reachable; ∨ an exposure that already happened (⇒ incident playbook) | before the next deploy; incident playbook if data was exposed |
| **P1** | CVSS 7.0–8.9 reachable; ∨ CVSS 4.0–6.9 with the LGPD multiplier | this release train |
| **P2** | CVSS 4.0–6.9; ∨ any High proven unreachable (evidence attached) | `NOC-REMEDIATE[security]` with a named destination |
| **P3** | CVSS < 4.0, defense-in-depth, hardening | backlog / accept-with-rationale |

Rules: reachability can **downgrade one level only with evidence** (call graph, import absence,
config proof); the LGPD multiplier **upgrades one level**; a finding with no vector is not a finding
yet. Compute the score with the FIRST calculator (or the `cvss` PyPI package, which implements v4.0)
and paste the vector string, e.g. `CVSS:4.0/AV:N/AC:L/AT:P/PR:N/UI:N/VC:H/VI:N/VA:N/SC:N/SI:N/SA:N` = 8.2.

**Dependabot / Trivy triage.** A dependency CVE is: (1) reachable? (do we import the vulnerable module
on a request path); (2) EPSS percentile; (3) fixed version available? ⇒ P-level per the table. The
lockfile + range-override rules are the fix path (`KB § PATTERNS/devops/product-lockfile-and-slug-drift.md`,
keeper `check_override_is_range`; skill `noc-dep-update`).

**Anti-patterns.** `high/warning/info` without a vector (the old output shape). Rating by the scanner's
label. Downgrading on "nobody knows the URL" without evidence (security by obscurity is AT:P at best,
§15 WE-1). Calling every LGPD item P0 (the multiplier is one level, not a jump to the top).

---

## 5 · Standards map

**Principle.** Standards are a coverage instrument: map each chapter to the doc + keeper that covers it,
and the empty cells are the review plan.

### 5a · OWASP ASVS 5.0.0 (30 May 2025) ↔ house

| ASVS chapter | Our doc / mechanism | Keeper(s) | Gap |
|---|---|---|---|
| V1 Encoding and Sanitization | §9; `KB § PATTERNS/security/llm-bot-security.md` §2a | — (manual) | no JS/TS SAST |
| V2 Validation and Business Logic | `StrictHttpModel` (`seed/lib/backend/noctusai_lib/api/schemas.py:50`); `KB § PATTERNS/backend/pydantic-strict-http.md` | `check_model_dump_json_mode` | business-flow abuse (API6) manual |
| V3 Web Frontend Security | security headers (`seed/lib/backend/noctusai_lib/api/security_headers.py`; CSP is **report-only**) | — | CSP not enforcing |
| V4 API and Web Service | §7, §9; schema exposure gate | `check_postgrest_unbounded_query`, `check_upload_route_body_override` | — |
| V5 File Handling | upload body caps; storage never public | `check_upload_route_body_override`, `check_storage_bucket_public` | content-type sniffing / AV scan manual |
| V6 Authentication | GoTrue; `validate_bearer_token`; AAL2 for admin gates | `check_auth_dep_anti_pattern`, `check_admin_gate_hand_rolled` | — |
| V7 Session Management | `KB § backend/07-AUTH-SECURITY.md` (refresh, dead-session confirm) | `check_auth_session_mutation_on_shared_client` | refresh-token reuse detection relies on GoTrue |
| V8 Authorization | §7; RLS; no-metadata authz | `check_no_metadata_authz`, `check_org_role_without_org_id`, `check_hand_copied_org_admin`, `check_admin_endpoint_service_role_bypass` | BOLA on service-role reads is manual |
| V9 Self-contained Tokens | SSO JWT verify (`seed/lib/backend/noctusai_lib/api/auth/__init__.py:1120-1145`) | — | audience not product-bound (NOC-REMEDIATE there) |
| V10 OAuth and OIDC | `KB § INTEGRATIONS/oauth-patterns.md` + RFC 9700 rules §7 | — | manual |
| V11 Cryptography | stdlib `hmac.compare_digest`; weak hashes only non-security | `check_hashlib_usedforsecurity` | — |
| V12 Secure Communication | TLS terminates at Cloudflare; tunnel to origin | — | HSTS only when deploy context |
| V13 Configuration | env manifest, fail-closed config (§6) | `check_prod_compose_env_manifest_sync`, `check_conftest_env_setdefault`, `check_dockerfile_vite_supabase_args` | — |
| V14 Data Protection | `KB § PATTERNS/security/lgpd.md` | `check_ledger_pii`, `check_lgpd_entry_removal` | no RIPD/ROPA program |
| V15 Secure Coding and Architecture | seed-first; `check_silent_errors` | `check_silent_errors`, `check_seed_canonical_default` | — |
| V16 Security Logging and Error Handling | `log_auth_401` reasons; audit middleware; Sentry scrubber | `check_silent_errors`, `check_silent_refusal` | no security-event alerting (A09) |
| V17 WebRTC | n/a (no WebRTC) | — | — |

### 5b · OWASP Top 10:2025 — the two that changed our thinking

A01 Broken Access Control · A02 Security Misconfiguration · **A03 Software Supply Chain Failures** (§10) ·
A04 Cryptographic Failures · A05 Injection · A06 Insecure Design · A07 Authentication Failures ·
A08 Software or Data Integrity Failures · A09 Security Logging and Alerting Failures ·
**A10 Mishandling of Exceptional Conditions** (fail-open — §6).

### 5c · OWASP API Security Top 10:2023 — this stack's #1 bug class

API1 Broken Object Level Authorization · API2 Broken Authentication · API3 Broken Object Property Level
Authorization · API4 Unrestricted Resource Consumption · API5 Broken Function Level Authorization ·
API6 Unrestricted Access to Sensitive Business Flows · API7 Server Side Request Forgery · API8 Security
Misconfiguration · API9 Improper Inventory Management · API10 Unsafe Consumption of APIs.

Why API1/3/5 dominate here: every product holds a **service-role client** that bypasses RLS, so the
object-level check lives in Python, per query — exactly where it gets forgotten (§15 WE-3).

### 5c-bis · Access-control requirements we audit against (read 2026-11-05)

- **ASVS 5.0 V8 (Authorization):** 8.2.1 function-level access only for explicitly permitted consumers (= API5) · 8.2.2 data-item level, against IDOR/BOLA (= API1) · 8.2.3 field level (= API3 BOPLA) · 8.3.1 enforce at a trusted service layer, never in client-modifiable code · 8.3.3 decide on the ORIGINATING consumer's rights, not an intermediary's (service-role clients!) · 8.4.1 multi-tenant: an operation must not touch tenants the caller lacks rights to · 8.4.2 admin interfaces get layered protection, not "internal network" trust · 8.1.1-8.1.2 the rules for function/data/field access are DOCUMENTED (= our access-tier inventory, canon-ai §12).
- **OWASP API 2023 prevention, in our terms:** API1 check ownership on every request that takes an object id, random ids help but never replace the check, test the authz logic · API3 return only the fields the role may see (no generic serializers), never auto-bind client input to internal objects, validate responses against a schema · API5 one authz module every function calls, deny by default, admin controllers inherit the admin check.
- **NIST SP 800-53 r5 (OSCAL catalog, read):** AC-3 enforce approved authorizations per the access-control policy · AC-6 least privilege · AC-6.5 restrict privileged accounts · **AC-6.9 log the use of privileged functions** (so platform-admin/service-role reads of Platform IP must leave an audit trail).


### 5d · CWE hot list for our languages

Python/FastAPI: CWE-639 (authz bypass via user-controlled key) · CWE-862/863 (missing/incorrect
authorization) · CWE-918 (SSRF) · CWE-89 (SQL injection — raw SQL in migrations/RPCs) · CWE-209
(error message information exposure) · CWE-532 (sensitive info in logs) · CWE-636 (not failing securely).
TypeScript/React: CWE-79 (XSS via `dangerouslySetInnerHTML`) · CWE-601 (open redirect) · CWE-200
(secrets in the bundle via `VITE_`).

**Anti-pattern.** Citing "OWASP" without the item ID. Every finding names its ASVS requirement area or
Top 10 / API Top 10 ID so coverage can be counted.

---

## 6 · Fail-closed doctrine

**Principle (A10:2025, CWE-636).** When a security-relevant dependency is missing, unknown or
unreachable, the safe state in prod is **deny**: unset secret ⇒ refuse; unknown role/feature ⇒ refuse;
unreadable budget/limit store ⇒ refuse the expensive action (and route a human); exception in an auth
path ⇒ 401/503, never "continue as anonymous-allowed". Fail-open is allowed only in a **named dev
context** (`DEBUG` truthy), and even then it must be loud (WARNING/CRITICAL log, `/api/health`
degraded). Availability-vs-security trade-offs are the owner's call and land in accept-with-rationale
with a removal trigger — never as a silent default.

**How it applies here — the inventory (verified on `origin/dev` 2026-11-05).**

| Site | Behaviour today | Verdict |
|---|---|---|
| Webhook secret unset — `webhook_endpoint(bypass_when_unset=True)` | accepts unsigned, logs CRITICAL in prod; refuses only when `WEBHOOK_REQUIRE_SIGNATURE=1` (`seed/lib/backend/noctusai_lib/security/webhook_signatures.py:52-87`, default OFF) | 🔴 fail-open by default — HELD as an owner-timed step (2026-11-05): flipping the default to refuse in a deploy context was tried and reverted — merge-queue batch `mq-candidate/42047199280-2` failed social-wiring, whose shared WAHA does not sign yet (L2 2026-11-03, `NOC-REMEDIATE[waha-hmac-prod]`), and ~20 live mounts use this verifier with no prod secret inventory. Order: inventory every mount's prod secret → provision → `WEBHOOK_REQUIRE_SIGNATURE=1` per product → then flip the default; receivers: seed `products/seed/backend/app/routers/webhook_router.py:81`, `products/igig/backend/app/routers/lead_webhooks_router.py:123`, `products/erp-imobiliario/backend/app/routers/whatsapp_webhook.py:99`, `products/commerce/backend/app/routers/webhook_router.py:81`, `products/social-wiring/backend/app/routers/whatsapp_router.py:1353,1427` |
| Same, SW WAHA | accept unsigned in deploy context but ERROR `webhook_hmac_desativado` + `/api/health` degraded (`products/social-wiring/backend/app/webhook_hmac.py:1-40`) | 🟡 loud degraded state; `NOC-REMEDIATE[waha-hmac-prod]` names the exit |
| Predeploy | `audit_webhook_secret_present` fails when no `*WEBHOOK_HMAC_SECRET` in the env snapshot (`mcp/noctusai/tools/noctus/dev/predeploy_check.py:528-535`) | 🟢 gate exists; only as good as the snapshot |
| AI consent unknown feature | `is_granted` ⇒ False (`KB § PATTERNS/security/lgpd.md` §9) | 🟢 |
| Prepaid LLM credits unreadable | refuse 503 `LLMCreditsUnverifiable` (`seed/lib/backend/noctusai_lib/integrations/llm/budget.py:33-44`) | 🟢 |
| Monthly LLM budget lookup fails | proceeds (`budget.py:28-31`) | 🟡 documented fail-open; budget is a cost cap, credits are the hard gate |
| Julia per-number limiter, Redis down | text still reaches agents (`products/social-wiring/backend/app/services/julia_protecao_service.py:367-369` ⇒ `erro`; `routers/whatsapp_router.py:1172` stops only `bloqueado`/`limitado`) | 🟡 bounded by agents' DB-backed admission — see `KB § PATTERNS/security/ai-agent-security-canon.md` §15 WE-3 |
| Auth provider transport failure | 503 + `Retry-After`, never 200/anonymous (`KB § backend/07-AUTH-SECURITY.md`) | 🟢 fail-closed without logging users out |
| Staff lookup failure on a Julia line | treated as a lead (never operator tools) (`whatsapp_router.py:640-660`) | 🟢 least privilege on error |
| Trusted-membership read error | propagates so the caller fails closed (`seed/lib/backend/noctusai_lib/api/auth/__init__.py:590-600`) | 🟢 |

**The seed rule.** Because the seed IS the default (CLAUDE.md §1 "Seed defaults = canonical answer"),
a fail-open default in the seed is a fleet-wide finding at the seed, never N per-product findings.

**Checklist.** For each new `except`/fallback on a security path: what is the prod state when this
fires? Is it deny? If not: is it loud (log level + health), owner-accepted (catalog entry), and does it
have a named exit (`NOC-REMEDIATE`)? `check_silent_errors` catches the silent case; the fail-open-loud
case is manual review.

**Anti-patterns.** "Fail-open so legitimate users aren't blocked" with no owner decision. A flag whose
safe value is OFF by default (the `WEBHOOK_REQUIRE_SIGNATURE` shape — safe only if every env remembers
to set it). Logging the degraded state once at boot where nobody looks (pair it with `/api/health`).

---

## 7 · AuthN / AuthZ

**Principle.** Authentication proves *who*; authorization decides *what, on which object, which
property, which function* (API1/API3/API5). Authorization is enforced server-side, per request, from a
source the caller cannot write.

**House mechanisms (use, never re-derive).**
- **Identity:** `validate_bearer_token` asks GoTrue; **401 iff the provider rejected the token**, 503 on
  transport failure (`KB § backend/07-AUTH-SECURITY.md`). Every 401 logs a reason via `log_auth_401`.
- **Org + role:** `Depends(get_current_user_org)` from the `make_get_current_user_org` factory
  (`seed/lib/backend/noctusai_lib/api/auth/__init__.py:735`); org/role come from `public.noctus_users`,
  **never** `user_metadata` (user-writable — Supabase says so explicitly) — `KB § PATTERNS/backend/no-metadata-authz.md`.
  Keepers: `check_auth_dep_anti_pattern`, `check_no_metadata_authz`, `check_org_role_without_org_id`.
- **Function level:** admin gates compose the seed factory (`require_org_admin_for`,
  `seed/lib/backend/noctusai_lib/api/auth/session/scopes.py:196`) which carries the MFA/AAL2 step-up;
  hand-rolled `role == "admin"` skips it (`check_admin_gate_hand_rolled`; FE twin `check_hand_copied_org_admin`).
- **Customer ≠ staff:** org membership with a customer role is not staff access
  (`KB § PATTERNS/backend/database-rls.md` § Customer roles).
- **Object level on service-role reads:** every query carries `.eq("org_id", <trusted org>)` (and the
  object id is re-scoped server-side, never trusted from the body).
- **Property level:** response models with `extra="forbid"` and explicit fields; never return the row
  as-is (credential columns, internal flags).
- **Open redirect:** SSO `next=` is path-only — starts with `/`, not `//`, no backslash
  (`seed/lib/frontend/src/components/SSOCallback.tsx:96-106`) — the reference shape.

**401 vs 403.** 401 = we do not know who you are (missing/invalid/rejected token). 403 = we know, and
you may not. 404 for "exists but not yours" is acceptable to avoid enumeration *only* if consistent.
Tests assert the exact code (`check_test_status_assertion`, `check_auth_boundary_false_green`;
`KB § PATTERNS/compliance/auth-boundary-false-green.md`).

**OAuth (RFC 9700, Jan 2025) — rules for Google/Meta/SSO flows.** Public clients MUST use PKCE (S256);
servers MUST match redirect URIs exactly; the implicit grant SHOULD NOT be used; refresh tokens for
public clients MUST be sender-constrained or rotated; no open redirectors on any redirect URI host.
Applies to `KB § INTEGRATIONS/oauth-patterns.md` flows; GoTrue rotates refresh tokens on use.

**JWT (RFC 8725).** Allow-list the algorithm (never accept `none` or let the token pick); validate `iss`,
`aud`, `exp`; use distinct `aud`/`typ` per token kind to prevent cross-JWT confusion. Our SSO verifier
does the first three and requires `type="sso"` (`seed/lib/backend/noctusai_lib/api/auth/__init__.py:1131-1142`);
its own `NOC-REMEDIATE[security]` (`:1121-1129`) records the gap — audience not bound to the product —
which must close before a second identity-source product verifies SSO tokens. The unverified decode in
`token_cache.py:78` is safe only because it runs on a token GoTrue already accepted (cache-expiry read).

**Checklist.** New route ⇒ which dep authenticates it; which line authorizes the *object*; which
fields can the caller set (BOPLA write) and see (BOPLA read); is it an admin function (factory gate);
strict-status tests for 401 and 403.

**Anti-patterns.** "Route exists behind login" as the authz argument. Org from the body/path/metadata.
Admin endpoints reaching for the service role to "make it work" (`check_admin_endpoint_service_role_bypass`).

---

## 8 · Supabase / Postgres

**Principle.** RLS enabled is a **fact about a table, not a guarantee about the data** (the
erp-certidoes lesson, `KB § PATTERNS/security/lgpd.md` §12). Every route to the data has its own gate:
PostgREST table, view, RPC function, Storage public/sign/authenticated route, service-role client.

**Rules (depth in `KB § PATTERNS/backend/database-rls.md`, backend-owned; this is the security lens).**
1. **Every org table:** `ENABLE ROW LEVEL SECURITY` + org-scoped policy (`check_new_org_table_rls`,
   advisory `check_table_has_rls`); no self-referencing policy (`check_rls_policy_self_reference`).
2. **Write policies need `WITH CHECK`.** Postgres: an UPDATE policy with only `USING` reuses it as the
   check — acceptable when identical; but a `FOR ALL`/`UPDATE` policy whose `USING` admits rows the
   writer must not *produce* (e.g. moving a row to another org) needs an explicit `WITH CHECK` on the
   tenant column. INSERT policies take only `WITH CHECK`. (No keeper — manual.)
3. **Views bypass RLS unless `security_invoker = true`** (Supabase docs; PG15+). Grep evidence on
   `origin/dev`: 16 `CREATE VIEW` statements in product migrations, the newer ones carry
   `WITH (security_invoker = true)` (e.g. `products/social-wiring/backend/migrations/080_vw_lead_corretor_contagem.sql:46`);
   `social_wiring.vw_portal_roi` does not (043/047/081) and is closed instead by revoking browser grants
   (`289_julia_db_lockdown.sql:57,117-120`). Either is acceptable; **neither is a finding** — an
   un-invoker view still granted to `authenticated`/`anon` is. (No keeper — manual; candidate.)
4. **SECURITY DEFINER** functions: pinned `search_path` (`check_function_search_path_pinned`) and
   `REVOKE EXECUTE ... FROM PUBLIC, anon, authenticated` same migration
   (`check_secdef_migration_revokes_execute`; `KB § PATTERNS/backend/migration-sql-security-gates.md`).
5. **Grants:** `anon` gets USAGE only, never a schema-wide table grant (`check_schema_wide_anon_grant`);
   service-role-only content tables are never `TO authenticated` (`check_no_authenticated_grant_on_content_tables`).
6. **Schema exposure** is its own gate (`KB § PATTERNS/backend/database-rls.md` § PostgREST schema exposure;
   `noctus.dev.ensure_schema_exposure`). A schema exposed to the Data API makes every granted object
   browser-reachable (TB3b). Supabase "Hardening the Data API": revoke default privileges on new objects.
7. **Storage:** buckets are never public, no exception (`check_storage_bucket_public` static +
   `noctus.dev.check_storage_no_public_buckets` live in `predeploy_check`); access via short-TTL signed
   URL minted at read time; object paths must not carry personal data (see §15 WE-1 — the certidões
   path embeds the consulta name).
8. **Secret keys / service role** bypass RLS only when the request carries no user token (Supabase
   docs) — never mutate auth session on the shared service client
   (`check_auth_session_mutation_on_shared_client`).
9. **Cross-tenant RLS test harness (standing proof).** For each org table: as role `authenticated` with
   `request.jwt.claims` of a user in org A, `SELECT`/`UPDATE`/`DELETE` an org-B row ⇒ 0 rows / error;
   `INSERT` with `org_id = B` ⇒ policy violation. Shape: `SET LOCAL ROLE authenticated; SELECT
   set_config('request.jwt.claims', '<json>', true); ...` inside a rolled-back transaction, run by
   `noctus.dev.verify_db_guards`-style tooling against a disposable DB. Status: proposed, not built —
   name it in findings as the missing proof.

10. **Exposure verdicts come from EFFECTIVE state, never from a partial migration read.** A chain of
    migrations is a program: a later one (revoke, drop policy) overrides an earlier one. Replay the whole
    chain on a disposable DB, or query the live grants/policies, BEFORE ranking. Reading a few migrations
    is "inferred" at most (lesson 2026-11-05, P1-A false positive: `agents` browser grants had been revoked
    by migration 036 while 001/012/020/031 still showed them).
11. **Effective-state queries (read-only, run in this order):**
    `select rolname, rolconfig from pg_roles where rolname='authenticator'` (`pgrst.db_schemas` = what is
    exposed; PostgREST serves ONLY listed schemas, first = default, switched by `Accept-Profile` /
    `Content-Profile`; `pg_catalog`/`information_schema` cannot be listed) ·
    `select table_schema,table_name,grantee,privilege_type from information_schema.role_table_grants where grantee in ('anon','authenticated')` ·
    `select schemaname,tablename,policyname,cmd,roles,qual from pg_policies` (flag `TO authenticated` with
    an org-membership-only `qual` on a Platform-IP table: every member of any org reads it) ·
    `pg_tables.rowsecurity=false` · views without `security_invoker` · `select id,public from storage.buckets`
    plus `pg_policies where schemaname='storage'` · column privileges
    (`information_schema.column_privileges`). Then the live check: customer JWT + anon key against
    `/rest/v1/<table>` with `Accept-Profile: <schema>`; expected 401/403/empty for every Platform-IP table.
12. **PostgREST role model (read):** `authenticator` logs in with minimal rights and does `SET LOCAL ROLE`
    to the JWT `role` claim (or `anon` when absent); authorization is the database's job, so a table
    grant is an API decision. Keep `authenticator` NOINHERIT, and grant it only the roles it must impersonate.
13. **Data API surface (Supabase "Securing your API", read):** put the intended API in a dedicated schema
    and keep internals unexposed; if no client uses REST/GraphQL, turn the Data API off; turn off
    "Automatically expose new tables" so new objects carry no default grants (functions still get EXECUTE
    via PUBLIC, revoke separately); RLS does not cover functions, so every callable function needs its own
    EXECUTE decision. The page does not say whether new projects may opt out of schema exposure; check the
    project setting instead of assuming.
14. **RPC and GraphQL are separate doors.** `SECURITY DEFINER` functions in an exposed schema are callable
    via `/rest/v1/rpc/<fn>` by anyone holding EXECUTE (default PUBLIC): list with
    `select p.proname, p.prosecdef, has_function_privilege('anon',p.oid,'execute'), has_function_privilege('authenticated',p.oid,'execute') from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname = any(<exposed schemas>)`.
    If `pg_graphql` is installed (`select extname from pg_extension`), `/graphql/v1` introspection exposes
    the same tables: audit it as a second read path (grants decide, not the route).
15. **Column privileges** narrow what RLS cannot (RLS is row-only). Supabase calls them advanced and
    recommends policies first; caveats: a table-level grant still wins over a column revoke, and `select *`
    fails for restricted roles. For secret columns prefer "no browser grant on the table".
16. **Storage (read):** public buckets need no policy and are world-readable (our rule: never public);
    private buckets are closed until `storage.objects` policies open them; upsert needs SELECT+UPDATE too;
    scope by bucket/path/user id; listing needs its own care (operation-aware SELECT).
17. **Run the Supabase advisors** (`get_advisors` type=security via the Supabase MCP, or the dashboard
    linter) as a cheap cross-check on every exposure audit: it flags RLS-off tables, SECURITY DEFINER
    views, mutable search_path, exposed auth users. It is a floor, not the verdict (rule 10).
18. **Platform IP is a data class.** Agent prompts, sections, skills, tool descriptions, evals, compiled
    prompts, canaries and runtime config are platform-admin or service-role only; classify by access tier
    (platform / org / public / service, default deny — `KB § PATTERNS/security/ai-agent-security-canon.md` §12 step 1;
    pattern `access-tiers` lands with `feat/access-tiers-gate`).


**Anti-patterns.** Approving "17 org-scoped policies" on a public bucket. A view added for a dashboard
with a default `GRANT SELECT TO authenticated`. Fixing RLS recursion by switching the endpoint to service
role.

---

## 9 · Input and output

**Principle.** Validate shape at the boundary, encode for the sink, never let input choose a destination.

- **HTTP bodies:** `StrictHttpModel` (`extra="forbid"`) — silent field-drop is both a correctness bug and
  a BOPLA write hole (`KB § PATTERNS/backend/pydantic-strict-http.md`). Writes through
  `model_dump(mode="json")` (`check_model_dump_json_mode`).
- **Injection:** PostgREST builder (parameterized) everywhere; raw SQL only in migrations/RPCs with
  `format('%I', …)`/`%L`; ILIKE patterns length-capped and escaped; never f-string SQL with input.
  Template injection: LLM prompts get user text fenced as data (agents canon). Header injection: never
  echo input into response headers.
- **SSRF (API7 / CWE-918) — any server-side fetch of a URL that input influences:** allow-list hosts;
  build the URL yourself (fixed scheme/port/path); redirects off; resolve DNS and refuse private,
  loopback, link-local and metadata ranges (169.254.169.254) to defeat rebinding; reject ambiguous URLs
  (OWASP SSRF cheat sheet). House reference: SW lead media — host-pinned to the provider, redirects off,
  byte caps streamed (`products/social-wiring/backend/app/services/media_service.py`). The BYOK key
  testers call **fixed** vendor URLs (`products/agents/backend/app/credentials/api_key_testers.py:57,64`) —
  safe while constant; a user-supplied base-URL field would turn them into an SSRF/exfil oracle.
- **File upload:** per-route body ceiling (`check_upload_route_body_override`); verify content type by
  magic bytes, not the header; storage key generated server-side; never public.
- **XSS (React):** JSX escapes by default; the sinks are `dangerouslySetInnerHTML`, `href`/`src` with
  `javascript:` URLs, and markdown renderers. On `origin/dev` the only `dangerouslySetInnerHTML` sites
  are a JSON-LD `<script>` serialised through the seed `safeJsonLd` (`products/core/frontend/src/website/components/SiteFaq.tsx:26`)
  and the shadcn chart style block (`products/erp-imobiliario/frontend/src/components/ui/chart.tsx:70`) —
  both non-user content. Any new site needs DOMPurify or a reasoned exemption. CSP is report-only today
  (`seed/lib/backend/noctusai_lib/api/security_headers.py:7,64`) — moving it to enforcing is the
  defense-in-depth step.
- **Errors:** user-facing pt-BR messages never embed the offending value (`KB § PATTERNS/security/lgpd.md` §4);
  FastAPI's default 422 echoes `input` — public anonymous routes parse the body themselves to avoid
  echo (`products/agents/backend/app/public_ask/router.py:1-14` is the reference).
- **No-leak (owner rule "no-leaking", 2026-11-11): an error body is a CODE, never exception text.** `detail=str(exc)` /
  `f"… {exc}"` hands a stranger the internal hostname (`http://waha-assistant:3000/…`), env-var names and driver
  messages (CWE-209). Raise `noctusai_lib.api.integration_errors.integration_error(code, exc=exc, op=…)`: fixed pt-BR
  message + stable `code`, exception logged server-side, one `integration_error code=… status=…` line per dispatch
  (the telemetry leg). Gate: keeper `check_http_detail_echoes_exception` (`--check-http-detail-echoes-exception`;
  seed = zero tolerance, products ratcheted by `deploy/security/http-detail-echo-baseline.json`,
  `NOC-REMEDIATE[http-detail-echo]`; escape `# detail-safe: <reason>` only for domain-authored text). Verify-then-persist:
  a create that calls an upstream verifies first, so a failed call leaves no row.

**Anti-patterns.** Deny-list SSRF filters. Trusting `Content-Type`. Rendering LLM output as HTML.

---

## 10 · Secrets and supply chain

**Secrets.**
- Resolution chain `org_settings → platform_settings → env`; per-connector `.env`; never a `VITE_`
  secret (everything `VITE_` ships to the browser) — `KB § PATTERNS/devops/environment.md` (devops-owned).
- Every compose `${VAR}` documented, secret-shaped vars never default to empty
  (`check_prod_compose_env_manifest_sync`); conftests never `setdefault` a credential (`check_conftest_env_setdefault`).
- Never log a secret, signature or token (token *shape* only); Sentry scrubber on; ledgers refuse PII
  (`check_ledger_pii`).
- **Rotation runbook (minimum):** revoke at the provider ⇒ set new value in `.env.fleet` / Supabase
  vault ⇒ redeploy via `noctus.dev.deploy_image` ⇒ verify (`predeploy_check`, smoke) ⇒ search logs and
  git history for the old value (gitleaks) ⇒ record in the incident register if it was exposed
  (`KB § PATTERNS/security/incident-response-playbook.md`).

**Supply chain (A03:2025, SLSA).**
- **Pin by digest, prove by provenance.** GitHub Actions pinned to a full-length commit SHA (GitHub's
  hardening guide; lockfiles supersede where adopted) — on `origin/dev` 79 `uses:` lines are tag-pinned,
  including `aquasecurity/trivy-action@v0.36.0`, whose tags were force-pushed to malicious commits on
  2026-03-19/20 (CVE-2026-33634; Aqua: pin to full SHA). Base images by digest. SBOM per image (Syft or
  Trivy `--format cyclonedx`), signature/attestation (Sigstore cosign), target SLSA Build L2 (hosted
  build + signed provenance).
- **npm:** lockfile is the freeze; `overrides` are ranges (`check_override_is_range`); lockfile in sync
  (`check_product_lockfile_dep_sync`); Dependabot covers every active product (`check_dependabot_product_coverage`).
  **Dependency confusion:** `@noctusai/*` must resolve only from our source (workspace/file or a scoped
  registry entry in `.npmrc`); a public package with that name must never be installable.
- **Python:** seed-declared imports (`check_seed_declared_imports`, `check_product_declared_imports`);
  bandit baseline; LLM SDKs only via the seam (`check_no_direct_llm_sdk_import`).
- **Collision zone:** CI workflow edits (SHA-pinning, SBOM, JS SAST, gitleaks full-history) belong to the
  CI/git redesign session — the security agent **flags**, never authors them
  (`KB § PATTERNS/devops/ci-security-gates.md`, devops-owned).

**Anti-patterns.** Tag-pinning a security scanner. Exact-pin `overrides` "for safety" (freezes the
fleet). Rotating a secret without searching where the old one went.

---

## 11 · Edge and infrastructure

- **Origin never exposed:** only cloudflared reaches containers; ingress is derived from one source
  (`check_tunnel_ingress_snapshot_sync`; `KB § PATTERNS/devops/tunnel-ingress-source-of-truth.md`).
  New prod exposure is the owner's decision (`check_prod_exposure_consent`).
- **WAF:** CF blocks non-browser user agents with error 1010 — programmatic callers to `*.noctusai.com`
  send a browser UA (`mcp/noctusai/tools/noctus/dev/_public_edge.py`; `KB § PATTERNS/frontend/core-url-routing.md` §8);
  `*.supabase.co` is not behind it. Security implication: the WAF is a noise filter, not authN —
  never treat "behind CF" as access control.
- **Internal-only services:** WAHA dashboard/API never on a tunnel hostname, API key set, dashboard
  password set; one WAHA per number rendered from `deploy/fleet/waha-instances.yml`
  (`check_waha_instances_render_sync`).
- **Containers:** non-root, `cap_drop: [ALL]`, `no-new-privileges`, read-only rootfs + tmpfs where the
  app allows, memory limits, init. Today pinned for `agents` + `academia-de-reciclagem` only
  (`check_prod_compose_hardening_parity`; SEC-C proof `.github/workflows/agents-secc-ci.yml`) — the rest
  of the fleet is a P2 hardening gap.
- **Ops plane (TB7):** forced-command deploy keys (`KB § PATTERNS/devops/ssh-deploy-key-restrictions.md`);
  `noctus.vps.exec` hard-deny + read-allowlist + confirm gate (`mcp/noctusai/tools/noctus/dev/vps_exec.py:1-20`).

---

### 11b · Browser and network exposure (what a stranger sees in devtools)

Source: OWASP API3 (excessive data in responses), LLM07 (the prompt is not a secret), our 2026-11-05 audit.
1. **Which routes return Platform IP, and which SPA pages fetch them** (`grep` the route in
   `products/*/frontend` and `lib`): a page that fetches a prompt hands it to every viewer, whatever the UI hides.
2. **Bundles:** `curl -s https://<host>/ | grep -oE 'assets/[^"]+\.js'`; per asset `curl -s <asset> | grep -c sourceMappingURL`
   (prod must be 0) and `curl -sI <asset>.map` (expect 404). Grep bundles for known prompt phrases and canary tokens; nothing sensitive in `VITE_*`.
3. **Error bodies:** force 401/403/404/422/500 on a route sample; bodies carry no stack, SQL, table or file names, config.


## 12 · Security testing

- **Auth boundary:** strict `== 401` / `== 403`, never `in (401, 404|422)`
  (`check_auth_boundary_false_green`, `check_test_status_assertion`).
- **Cross-tenant negatives:** for every org-scoped route, a second org's user gets 404/403 and the row
  is unchanged; for every org table, the §8 rule 9 harness.
- **Webhooks:** valid ⇒ 200, tampered ⇒ 401, missing headers ⇒ 401, unset secret in prod context ⇒ 401
  (once fail-closed lands), replay outside window ⇒ 401.
- **Never patch our own guard in tests** (`check_no_self_monkeypatch`) — a patched guard is an untested guard.
- **DAST smoke:** `noctus.dev.spa_smoke` / `sso_smoke` / `prod_watchdog` prove liveness, not security;
  a security smoke = unauthenticated GET/POST to every non-public route ⇒ 401 (derive the route list from
  the app, never by hand).
- **When to fuzz:** parsers of provider payloads (WAHA, Meta), document extraction inputs, any
  hand-written decoder — property-based (Hypothesis) over the parser, not the network.
- **Keepers are regression tests for classes;** every new keeper ships its own regression test
  (`check_detector_has_regression_test`).

---

## 13 · Anti-patterns (each with its incident)

| Anti-pattern | Incident in this repo |
|---|---|
| "RLS enabled" accepted as proof | erp-certidoes public bucket, 2026-09-17 (`KB § PATTERNS/security/lgpd.md` §12) |
| Fail-open default in the seed | `bypass_when_unset=True` inherited by 5 receivers (§6, §15 WE-2; owner-timed rollout) |
| Authorizing on `user_metadata` | SW email_marketing/media_creation routers, 2026-10-06 (`KB § PATTERNS/backend/no-metadata-authz.md`) |
| Signing secret ≠ provider's signing key | erp Meta receiver used the verify token as HMAC secret (fixed 2026-08-03, `products/erp-imobiliario/backend/app/routers/meta_api.py:42-58`) |
| Wrong scheme for a provider | WAHA assumed sha256 hex; it signs sha512 in `X-Webhook-Hmac` (`KB § PATTERNS/security/webhook-signatures.md` §2b) |
| Empty secret in env treated as set | `ASAAS_WEBHOOK_TOKEN=` + conftest `setdefault` (`check_conftest_env_setdefault`) |
| Secret-shaped compose var with empty default | `${JULIA_ANTHROPIC_API_KEY:-}` (`check_prod_compose_env_manifest_sync`) |
| PII written to a permanent ledger | real CPF in `auto-improvement.ndjson` (`check_ledger_pii`) |
| A status/compliance list that overstates | webhook adopters list named nonexistent products (`webhook-signatures.md` § Current adopters) |
| Tag-pinned security action | trivy-action tag hijack CVE-2026-33634 (industry; we are exposed, §10) |

---

## 14 · Decision checklists

**New endpoint.** auth dep · object-level scope line · BOPLA in/out · admin factory if privileged ·
rate limit if public · body cap if upload · strict-status tests (401/403/422) · no input echo in errors ·
LGPD five questions if personal data.

**New table.** RLS + org policy (+ `WITH CHECK` when writes can move tenancy) · grants minimal · not
granted to browsers unless the FE reads it · retention answer · access log if documents/identity ·
`lgpd_flag` for new personal-data columns.

**New view / RPC.** `security_invoker = true` or no browser grant · SECURITY DEFINER ⇒ pinned
`search_path` + EXECUTE revoked · no service-role assumptions inside.

**New webhook.** `webhook_endpoint(...)` with the right scheme · per-request secret resolver ·
fail-closed in prod (§6) · rate limit · idempotency on the provider event id · replay window when the
provider sends a timestamp · status-pinned tests · append to the adopters list only after checking pins.

**New integration (egress).** credential via resolution chain · least-scope token · SSRF rules if any URL
is input-influenced · data minimization · LGPD destination + international-transfer note · timeout +
rate limit (`noctusai_lib.integrations.rate_limit`).

**New personal-data category.** `KB § PATTERNS/security/lgpd.md` intake · LINDDUN pass · lawful basis ·
retention · access log · RIPD trigger check (Art. 38) · withheld-then-activated pattern (lgpd §11).

---

## 15 · Worked examples (grounded)

### WE-1 — erp-certidoes public bucket (2026-09-17)

- **What:** `erp-certidoes` (102 objects, 21 MB: CPF, full names, debt/restriction findings) and
  `erp-geral` were `public = true` (`products/erp-imobiliario/backend/migrations/001_erp_imobiliario.sql`,
  `011_storage_buckets.sql`); Supabase serves public objects via `/object/public/...`, which never
  evaluates `storage.objects` RLS.
- **STRIDE:** Information disclosure at TB3b/TB4 (Storage public route). **LINDDUN:** Identifying + Data disclosure.
- **Severity:** `CVSS:4.0/AV:N/AC:L/AT:P/PR:N/UI:N/VC:H/VI:N/VA:N/SC:N/SI:N/SA:N` = **8.2 High**. AT:P
  because the attacker needs the object path (`<org_id>/certidoes/<consulta nome>/<tipo>_<8 hex>.pdf`,
  built by `products/erp-imobiliario/backend/app/services/certidoes_service.py:398-406,917-922`) — but
  public URLs had been persisted and handed to browsers, so the path is not secret; with a leaked URL the
  vector is AT:N = 8.7. **LGPD multiplier:** financial data (débitos/restrições) + CPF, Res. 15 art. 5 ⇒
  **P0**. (The audit wrote "Critical"; recomputed with the `cvss` package against FIRST v4.0 — High.)
- **Fix shipped:** buckets private, migration `048_storage_no_public_buckets.sql`, two-legged gate with
  no allowlist. **Residual:** object paths embed the consulta *name* (personal data in a storage key that
  appears in logs and signed URLs) — P3 hardening.
- **The missing half:** no incident assessment was ever recorded — was it "risco ou dano relevante"
  (Res. 15 art. 5)? when did the controller "tomar conhecimento"? was the 3-business-day clock started?
  where is the register entry (art. 10, ≥ 5 years)? That decision belongs to
  `KB § PATTERNS/security/incident-response-playbook.md` §9 (retroactive register), and is follow-up #7
  of the agent-refinement project.

### WE-2 — the seed's unsigned-webhook default flowing to three products

- **What:** the seed skeleton ships `bypass_when_unset=True` (`products/seed/backend/app/routers/webhook_router.py:16,81`);
  `scaffold_product` copies it, and it is live in igig (`lead_webhooks_router.py:123`), erp
  (`whatsapp_webhook.py:99`), commerce (`webhook_router.py:81`), plus SW's two WAHA routes. The lib has
  a fail-closed switch, but its safe value is opt-in: `WEBHOOK_REQUIRE_SIGNATURE` defaults OFF
  (`seed/lib/backend/noctusai_lib/security/webhook_signatures.py:52-64`).
- **STRIDE:** Spoofing + Tampering at TB5 (forged leads / messages ⇒ DB writes, agent turns, LLM spend).
  **A10:2025** (fail-open on a missing secret).
- **Severity:** `CVSS:4.0/AV:N/AC:L/AT:P/PR:N/UI:N/VC:N/VI:H/VA:N/SC:N/SI:L/SA:N` = **8.2 High**; AT:P
  because it needs the misconfiguration (secret unset in prod). Unauthenticated + seed-wide ⇒ **P0**.
- **STATUS 2026-11-05: OPEN, HELD as an owner-timed step (2026-11-05): flipping the default to refuse in a deploy context was tried and reverted — merge-queue batch `mq-candidate/42047199280-2` failed social-wiring, whose shared WAHA does not sign yet (L2 2026-11-03, `NOC-REMEDIATE[waha-hmac-prod]`), and ~20 live mounts use this verifier with no prod secret inventory. Order: inventory every mount's prod secret → provision → `WEBHOOK_REQUIRE_SIGNATURE=1` per product → then flip the default. APPROVED by the owner 2026-11-05; inventory done, phases tracked in `project-history/roadmaps/unsigned-webhook-rollout-2026-11.md`.**
- **Fix at the seed, once** (CLAUDE.md §1 "Seed defaults"): `bypass_when_unset` resolves from the deploy
  context (dev-only true), prod refuses with 401 and `/api/health` reports degraded like SW's
  `webhook_hmac_desativado`; strict-401 test; `predeploy_check` keeps the secret-present leg. Products
  inherit; no per-product patch. (Product-code change ⇒ follow-up #1, not this doc.)

### WE-3 — `user_metadata.org_id` + service role = API1 BOLA

- **What:** SW `email_marketing` / `media_creation` routers read `org_id` from `user_metadata`
  (user-writable via `supabase.auth.updateUser({data})`) and queried with the service-role client — any
  user could name another org and read/write its contacts and campaigns
  (`KB § PATTERNS/backend/no-metadata-authz.md`).
- **STRIDE:** Elevation of privilege at TB3 ⇒ Information disclosure + Tampering at TB4. **API1:2023**.
- **Severity:** `CVSS:4.0/AV:N/AC:L/AT:N/PR:L/UI:N/VC:H/VI:H/VA:N/SC:N/SI:N/SA:N` = **8.6 High**;
  cross-tenant ⇒ **P0**.
- **The checklist line it produced:** *every service-role query's tenant filter comes from
  `noctus_users` (via `get_current_user_org`), never the JWT's `user_metadata` or the body* — now
  keeper `check_no_metadata_authz` (s4). This is the model: incident ⇒ checklist line ⇒ keeper.

---

## 16 · Sources

All accessed 2026-11-05. "audit-verified" = fetched by the agent-refinement audit; "fetched" = fetched
again while authoring.

- Threat Modeling Manifesto — https://www.threatmodelingmanifesto.org/ — the Four Questions (audit-verified).
- LINDDUN privacy threat modeling — https://linddun.org/ — the seven categories (fetched).
- OWASP ASVS 5.0.0, 30 May 2025 — https://asvs.owasp.org/ and chapter list https://github.com/OWASP/ASVS/tree/master/5.0/en — §5a (fetched).
- OWASP Top 10:2025 — https://top10.owasp.org/2025 — A03, A10 (fetched).
- OWASP API Security Top 10 2023 — https://api-security.owasp.org/editions/2023/en/0x11-t10/ — API1–API10 (audit-verified).
- OWASP Secure Code Review Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Secure_Code_Review_Cheat_Sheet.html — review method (audit-verified).
- OWASP SSRF Prevention Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html — §9 SSRF rules (fetched).
- NIST SP 800-218 SSDF v1.1 — https://csrc.nist.gov/pubs/sp/800/218/final — secure SDLC practices (audit-verified).
- FIRST CVSS v4.0 — https://www.first.org/cvss/v4-0/ — §4 vectors (audit-verified); scores computed with the `cvss` PyPI package.
- FIRST EPSS — https://www.first.org/epss/ — exploit probability (audit-verified).
- RFC 9700 OAuth 2.0 Security BCP (2025) — https://www.rfc-editor.org/rfc/rfc9700 — PKCE, exact redirect match, implicit, refresh tokens, open redirectors (fetched).
- RFC 8725 JWT BCP — https://www.rfc-editor.org/rfc/rfc8725 — alg allow-list, iss/aud, cross-JWT confusion (audit-verified).
- Supabase, Row Level Security — https://supabase.com/docs/guides/database/postgres/row-level-security — views + `security_invoker`, `user_metadata`, secret keys vs user token (fetched).
- Supabase, Hardening the Data API — https://supabase.com/docs/guides/database/hardening-data-api — grants, default privileges (audit-verified).
- PostgreSQL, CREATE POLICY — https://www.postgresql.org/docs/current/sql-createpolicy.html — USING vs WITH CHECK semantics (fetched).
- GitHub, Security hardening for GitHub Actions — https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions — full-SHA pinning (fetched).
- Aqua, Trivy supply chain attack — https://www.aquasec.com/blog/trivy-supply-chain-attack-what-you-need-to-know — CVE-2026-33634, pin by SHA (audit-verified).
- SLSA build levels — https://slsa.dev/spec/v1.0/levels — provenance target (audit-verified).
- Res. CD/ANPD 15/2024 (text) — https://www.legisweb.com.br/legislacao/?id=458235 — art. 5 relevance criteria used by the LGPD multiplier (fetched; secondary host of the DOU text).
- Supabase, Securing your API — https://supabase.com/docs/guides/api/securing-your-api — READ 2026-11-05: dedicated API schema, Data API off switch, no auto-exposure of new tables, EXECUTE-via-PUBLIC trap, RLS does not cover functions (§8 rule 13).
- Supabase, column-level security — https://supabase.com/docs/guides/database/postgres/column-level-security — READ: row-only RLS vs column privileges, table-grant-wins and `select *` caveats (rule 15).
- Supabase, Storage access control — https://supabase.com/docs/guides/storage/security/access-control — READ: public buckets need no policy, private are deny-by-default, upsert needs SELECT+UPDATE (rule 16).
- PostgREST, schemas — https://docs.postgrest.org/en/stable/references/api/schemas.html (read via the repo source, the site returned 429) — `db-schemas`, `Accept-Profile`/`Content-Profile`, PGRST106, catalog schemas not listable (rule 11).
- PostgREST, authentication — same host, `references/auth` (read via the PostgREST repo docs source, auth reference) — authenticator/anon/user roles, `SET LOCAL ROLE` impersonation (rule 12).
- OWASP API Security 2023 API1/API3/API5 pages — https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization (and 0xa3, 0xa5) — READ: prevention lists summarised in §5c-bis.
- OWASP ASVS 5.0 V8 Authorization — https://github.com/OWASP/ASVS/blob/master/5.0/en/0x17-V8-Authorization.md — READ: requirement ids 8.1.x-8.4.x in §5c-bis.
- NIST SP 800-53 r5 OSCAL catalog — https://github.com/usnistgov/oscal-content (SP800-53 rev5 JSON) — READ: AC-3, AC-6, AC-6.5, AC-6.9 statements (§5c-bis).
- OWASP Logging Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html — READ: tokens, session ids, connection strings, keys, sensitive PII must be removed/masked/hashed before logging (checklist §10).
- Sentry, scrubbing sensitive data — https://docs.sentry.io/security-legal-pii/scrubbing/ — READ: documents server-side/advanced scrubbing only; SDK-side `before_send`/`send_default_pii` live in the SDK docs (NOT read; verify when auditing telemetry).


## Composes-with

`KB § PATTERNS/security/secure-code-review-checklist.md` · `KB § PATTERNS/security/incident-response-playbook.md` ·
`KB § PATTERNS/security/webhook-signatures.md` · `KB § PATTERNS/security/lgpd.md` ·
`KB § PATTERNS/security/ai-agent-security-canon.md` (agents-security) · `KB § PATTERNS/backend/database-rls.md` ·
`KB § PATTERNS/backend/no-metadata-authz.md` · `KB § PATTERNS/compliance/auth-boundary-false-green.md` ·
`KB § PATTERNS/devops/ci-security-gates.md` · agent `security` (owner).

> Access tiers (routes + tables declare platform/org/service/public; public is a closed allowlist; delta-stream + leak-fingerprint + effective-exposure gates): `KB § PATTERNS/security/access-tiers.md`.
