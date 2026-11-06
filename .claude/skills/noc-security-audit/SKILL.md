---
name: noc-security-audit
description: Use to run the repeatable exposure and security audit across noc products, agents and routes — triggers "security audit", "exposure audit", "can someone read our prompt", "leak check", "safety check", "audit routes", "is X protected", and after any new product, agent or route batch. Thin runner: dispatches the security + agents-security advisors over the canon's exposure steps, then the tech lead fixes on branches.
version: 2.0.0
---

# noc-security-audit — thin runner (depth lives in KB)

Origin: 2026-11-05, a competitor's agent prompt was visible in their network requests, so we audited ours. The method, checks, queries and sources are NOT here; they are in the canon and grow there.

## Run order
1. Scope: active products (`deploy/fleet/active-scope.txt`) or the named product/agent/route batch; note the `origin/dev` sha.
2. Dispatch read-only, in parallel, each told to follow canon §12 and to read the latest record in `KB § PATTERNS/security/audits/`:
   - agent `security`: access-tier inventory, browser/network exposure, direct DB exposure, tokens/secrets, logs/telemetry, tests. → `KB § PATTERNS/security/ai-agent-security-canon.md` §12 (step 1 and door order) · `KB § PATTERNS/security/appsec-craft-canon.md` §8 rules 10-18 and §11b · `KB § PATTERNS/security/secure-code-review-checklist.md` §3, §10.
   - agent `agents-security`: model path (fingerprint coverage, de-obfuscated/paraphrase, guard-before-stream, trifecta, red-team cases). → canon §2 (LLM07), §3, §10 · `KB § PATTERNS/security/ai-agent-threat-model.md` §3.4, §7 item 11.
3. Verdicts come from EFFECTIVE state (replay the whole migration chain or query live grants/policies), never a partial read. Live checks use read-only credentials; never paste secrets or JWTs.
4. Rank P0-P3 with evidence; the tech lead fixes on branches (one regression test per finding, strict `== 401/403`).
5. Write the dated record (`KB § PATTERNS/security/audits/<scope>-<yyyy-mm>.md`, template in canon §12) and fold every NEW check into the matching canon section in the same change. That is the learnings log: the dated records plus the canon's own sections. Do not keep a second log here.

## Guardrails
- Advisors never edit, commit or push. Never probe third-party systems.
- Access-tier tooling (`check_*` keepers + endpoint catalog) is landing on `feat/access-tiers-gate` (pattern `access-tiers`); until on dev use the grep fallback in canon §12.

## Depth
`KB § PATTERNS/security/ai-agent-security-canon.md` · `appsec-craft-canon.md` · `ai-agent-threat-model.md` · `secure-code-review-checklist.md` · `audits/julia-2026-11.md` (example record, incl. the 2026-11-05 exposure audit).
