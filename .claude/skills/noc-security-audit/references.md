# References — noc-security-audit (accessed 2026-11-05; all URLs returned HTTP 200 on that date unless noted)

## Phase 1 · Access tiers
- OWASP API Security Top 10 2023 (API1 BOLA, API3 BOPLA, API5 BFLA): https://owasp.org/API-Security/editions/2023/en/0x11-t10/
- OWASP ASVS (access control chapter): https://owasp.org/www-project-application-security-verification-standard/
- NIST SP 800-53 Rev. 5, AC-3 access enforcement and AC-6 least privilege: https://csrc.nist.gov/projects/cprt/catalog#/cprt/framework/version/SP_800_53_5_1_1/home

## Phase 2 · Browser / network exposure
- OWASP LLM07:2025 System Prompt Leakage (prompt is not a secret; keep authorization out of it): https://genai.owasp.org/llmrisk/llm072025-system-prompt-leakage/
- OWASP API Top 10 2023, API3 BOPLA (excessive data exposure in responses): same URL as phase 1.

## Phase 3 · Direct DB exposure
- Supabase, securing the Data API (exposed schemas, grants): https://supabase.com/docs/guides/api/securing-your-api
- Supabase, Row Level Security: https://supabase.com/docs/guides/database/postgres/row-level-security
- Supabase, column-level security: https://supabase.com/docs/guides/database/postgres/column-level-security
- Supabase Storage access control: https://supabase.com/docs/guides/storage/security/access-control
- PostgREST, schemas (db-schemas, Accept-Profile): https://postgrest.org/en/stable/references/api/schemas.html
- PostgREST, authentication and roles (authenticator role switching): https://postgrest.org/en/stable/references/auth.html (rate-limited, HTTP 429, when checked; re-verify)

## Phase 4 · LLM leakage and injection
- OWASP Top 10 for LLM Applications 2025 (LLM01 prompt injection, LLM07): https://genai.owasp.org/llm-top-10/ and https://genai.owasp.org/llmrisk/llm01-prompt-injection/
- Simon Willison, the lethal trifecta: https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/
- MITRE ATLAS: https://atlas.mitre.org/
- Google Secure AI Framework (SAIF): https://saif.google/secure-ai-framework
- Anthropic, mitigate jailbreaks and prompt injections: https://docs.anthropic.com/en/docs/test-and-evaluate/strengthen-guardrails/mitigate-jailbreaks
- OpenAI, safety best practices: https://platform.openai.com/docs/guides/safety-best-practices

## Phase 5 · Tokens and secrets
- Internal canon: `KB § PATTERNS/security/webhook-signatures.md`; NIST AC-6 (phase 1) for token scope.

## Phase 6 · Logs and telemetry
- OWASP Logging Cheat Sheet (what not to log): https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- Sentry, scrubbing sensitive data: https://docs.sentry.io/security-legal-pii/scrubbing/

## Phase 7 · Tests
- Internal: `KB § PATTERNS/compliance/auth-boundary-false-green.md`.

Note: link existence was verified by HTTP status only; page content for PostgREST auth, NIST catalog and Anthropic/OpenAI pages was not re-read in this pass. Re-verify on each audit and update the access date.
