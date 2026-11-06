---
name: noc-security-audit
description: Use to run the repeatable exposure and security audit across noc products, agents and routes — triggers "security audit", "exposure audit", "can someone read our prompt", "leak check", "safety check", "audit routes", "is X protected", and after any new product, agent or route batch. Dispatches the security + agents-security advisors with the 8-phase checklist (access tiers, browser exposure, direct DB exposure, LLM leakage, tokens, logs, regression tests, report + learnings log).
version: 1.0.0
---

# noc-security-audit — the repeatable exposure audit

Origin: the 2026-11-05 audit, triggered by a competitor (Core Studio) whose agent prompt was visible in their browser network requests. Sources per phase: `references.md` (one level deep). Every run ends by appending to the Learnings log below; the log is how the audit gets stronger each time.

**Platform IP** = what NoctusAI builds: agent prompts, sections, skills, tool descriptions, evals, compiled prompts, canaries, runtime config. Platform-admin or service-role only. **Default deny** for every route and table.

## Runner

1. Scope: all active products (`deploy/fleet/active-scope.txt`) or the named product/agent/route batch. Note base sha (`origin/dev`).
2. Dispatch **in parallel**, read-only: agent `security` (phases 1, 3, 5, 6, 7) and agent `agents-security` (phases 2, 4, and the LLM half of 5). Hand each this file's phase checklists plus the Learnings log. Each returns the findings table (id · phase · evidence · P-level · fix · proof test).
3. Run phases 2–3 live checks yourself only with read-only credentials; never print secrets or JWTs into the report.
4. Merge findings, rank P0–P3, then the tech lead fixes on branches (one per finding class, regression test in the same commit). Status counts only with file:line on `origin/dev` plus a test; unmerged = "in progress on `<branch>`".
5. Phase 8: write the dated record (`KB § PATTERNS/security/audits/`) and append new checks to the Learnings log.

## Phases

### 1 · Access-tier inventory
Classify every HTTP route: **platform / org / public / service**; anything unclassified is a finding.
- Tool: the access-tiers keeper (`check_*`) and the `noctus.dev` endpoint catalog (being built on `feat/access-tiers-gate`; pattern `access-tiers`, pointer: `KB § PATTERNS/common/` until it lands). Use them if present in the tree.
- Fallback: `grep -rnE "@(router|app)\.(get|post|put|patch|delete)" products/*/backend seed` and list the auth dependency per route (`Depends(...)`); routes with no auth dependency = public/service candidates, each needs a stated reason.
- Check BOLA (object id in path/query ownership-checked?), BOPLA (response fields filtered per role?), BFLA (admin verbs reachable by members?). Routes returning Platform IP must require platform-admin or service role, never "any org member".

### 2 · Browser / network exposure
- Which routes return Platform IP, and which SPA pages call them (`grep -rn "<route>" products/*/frontend lib`). A page that fetches a prompt exposes it to every viewer of devtools.
- Bundles: `curl -s https://<host>/ | grep -oE 'assets/[^"]+\.js'`, then per asset `curl -s <asset> | grep -c sourceMappingURL` (prod must be 0; also try `<asset>.map` → expect 404). Grep bundles for known prompt phrases and canary tokens.
- Error bodies: force 401/403/404/422/500 on a sample of routes; bodies must not carry stack traces, SQL, table names, file paths or config.

### 3 · Direct DB exposure (Supabase / PostgREST)
Browsers hold the anon key and a user JWT, so the DB API is a second API surface. Run read-only SQL:
- Exposed schemas: `select rolname, rolconfig from pg_roles where rolname='authenticator';` (look for `pgrst.db_schemas`).
- Grants: `select table_schema, table_name, grantee, privilege_type from information_schema.role_table_grants where grantee in ('anon','authenticated') and table_schema not in ('pg_catalog','information_schema');` Any Platform IP table with a grant is a finding unless RLS denies non-admins. Compare grants against API role checks: a table the API gates but PostgREST grants is a hole (P1-A).
- Policies: `select schemaname, tablename, policyname, cmd, roles, qual from pg_policies where 'authenticated' = any(roles) or roles = '{public}';` Flag policies whose `qual` checks org membership only (any member reads), where the table holds Platform IP.
- Also: RLS disabled tables (`pg_tables.rowsecurity=false`), SECURITY DEFINER functions and views without `security_invoker`, column privileges.
- Storage: `select id, public from storage.buckets;` and `select * from pg_policies where schemaname='storage';`.
- Live: with a customer JWT and the anon key, `curl -s "$URL/rest/v1/<table>?select=*&limit=1" -H "apikey: $ANON" -H "Authorization: Bearer $JWT" -H "Accept-Profile: <schema>"`. Expect 401/403/empty for every Platform IP table, per schema.

### 4 · LLM-specific leakage and injection
Frame with OWASP LLM01:2025 (prompt injection) and LLM07:2025 (system prompt leakage); the prompt is never the secret, the code floor is the guard.
- Coverage: canary/fingerprint covers EVERYTHING that reaches the model: system prompt, sections, skill bodies, tool descriptions, tool results (P1-B was skill bodies).
- Guard bypass: check de-obfuscated (base64, spacing, leetspeak, translated) and paraphrase leakage, not just exact match.
- Streaming: no delta may leave before the output guard has judged it, else the guard only logs the leak (P1-C).
- Lethal trifecta per agent: private data + untrusted content + outbound channel; remove or isolate a leg.
- Red team: eval cases per finding class in content-v3; report attack-success-rate, not pass/fail. Deeper method: `KB § PATTERNS/security/ai-agent-security-canon.md`.

### 5 · Tokens and secrets
For each product token, channel token, tool token, `noc_` token and service key: what can a thief read or drive, with what blast radius (org vs fleet)? Webhook signatures verified fail-closed, constant-time, replay window (`KB § PATTERNS/security/webhook-signatures.md`). Rotation procedure exists and was exercised; tokens masked in API responses and unreachable from browsers. `git log -S` / gitleaks for committed secrets.

### 6 · Logs and telemetry
Grep log statements and exception handlers for prompt text, message bodies, phone numbers, emails, tokens. Sentry: confirm `before_send` scrubbing and server-side data scrubbing rules, `send_default_pii` off. Usage/telemetry tables: do they store raw prompts or PII, and who can read them (phase 3 grants apply)? LGPD data-category: `KB § PATTERNS/security/lgpd.md`.

### 7 · Tests that keep it fixed
- Auth tests assert strict `== 401` / `== 403`, never `in (401, 404, 422)` (`KB § PATTERNS/compliance/auth-boundary-false-green.md`).
- A keeper gate for each class that can be checked statically (tiers, grants, source maps).
- One regression test per finding, landing in the fix commit; plant-the-secret tests for leaks.

### 8 · Report, fix, learn
Findings table ranked P0–P3 (CVSS 4.0 + reachability), evidence file:line or query output, fix location, proof test, a "not verified" list. Tech lead fixes on branches. Then append to the Learnings log: every check you needed that this file lacked.

## Learnings log (append-only, dated; never edit past entries)

- **2026-11-05** — trigger: a competitor (Core Studio) agent prompt was visible in their browser network requests; we audited ours.
  - **P1-A** PostgREST grants vs API role checks mismatch: the agents schema was readable by non-admin platform-org members via `/rest/v1` because `pg_policies TO authenticated` checked org membership only while the API required platform-admin. New check: phase 3 compares grants/policies to the API tier for every Platform IP table.
  - **P1-B** Skill bodies were not fingerprinted: canary coverage must include everything that reaches the model. New check: phase 4 coverage list.
  - **P1-C** Deltas were streamed before the output guard ran. New check: phase 4 streaming order.
  - **P2-B** Eval runs were open to all org members. New check: phase 1 tier for eval/run routes.

## Guardrails
- Read-only: advisors never edit, commit or push; live checks use read-only credentials; never paste secrets or JWTs into reports.
- Never run a probe against a third party's systems; the competitor trigger is a reason to audit ours only.
- Do not duplicate canon in this file: point at KB.

## Depth
`references.md` (sources, access dates) · `KB § PATTERNS/security/ai-agent-security-canon.md` · `KB § PATTERNS/security/ai-agent-threat-model.md` §3.4 · `KB § PATTERNS/security/appsec-craft-canon.md` · `KB § PATTERNS/security/audits/julia-2026-11.md` (example record) · `KB § PATTERNS/compliance/auth-boundary-false-green.md` · pattern `access-tiers` (lands with `feat/access-tiers-gate`).
