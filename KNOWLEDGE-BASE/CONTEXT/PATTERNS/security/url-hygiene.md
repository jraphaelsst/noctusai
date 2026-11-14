# URL hygiene — signed-URL lifetime and PII in query strings

> Two security standards enforced by AST keepers (owner-approved 2026-11-14 from a read-only audit: findings P2-2 and P3-1). URLs are logged by proxies, CDNs, browsers and referers; whatever rides in one is effectively public for as long as those logs live.

## Rules

1. **A signed URL lives at most 600 s unless it says why.** A signed URL is a bearer credential. Pass `expires_in_seconds <= 600`; a longer TTL needs an explicit reason kwarg on the call (`ttl_reason=`, or `reason=` — the seam's final name is being set on `feat/sec-signed-url-ttl-clamp`; the keeper accepts both) or `# signed-url-ttl-ok: <why>` on the line. Why: the URL outlives the session that was authorised to fetch it. Keeper: `check_signed_url_ttl` (`--check-signed-url-ttl`). Resolves int literals, `60 * 60`, module-level int constants; also flags a `signed_url` definition whose TTL parameter defaults above the cap and `*SIGNED_URL*TTL*` constants. Config-field defaults reached through attributes (`cfg.signed_url_ttl_seconds`) are not resolvable and are covered by the seam's own clamp.
2. **No PII in URL query strings.** A route parameter that becomes a query param (explicit `Query(...)`, or a plain scalar on a GET/DELETE handler) must not be named like personal data: tokens `email`, `cpf`, `cnpj`, `rg`, `telefone`, `phone`, `celular`, `whatsapp`, `fone`, `endereco`, bare `documento`, and `e_mail`/`full_name`/`nome_completo`/`cpf_cnpj`/`numero_documento`. Move it to a POST body (search-by-identifier becomes `POST .../search`), or justify with `# pii-query-ok: <reason>` on the parameter line. Deliberately NOT flagged: bare `nome`/`name` (resource search filters, near-zero signal) and `cep` (area-level), and `tipo_documento` (a type, not a number). Why: access logs retain the full URL. Keeper: `check_pii_query_params` (`--check-pii-query-params`).

## Mechanics

Both keepers are per-file RATCHETS (`mcp/noctusai/tests/signed_url_ttl_baseline.json`, `pii_query_params_baseline.json`): a file may carry fewer hits, never more; a fixed hit must lower the baseline (`--lower-signed-url-ttl-baseline`, `--lower-pii-query-params-baseline`). Wired in `scripts/hooks/pre-commit` (backend source or baseline staged; WARN-ONLY through the shadow period, then promote to blocking after >=7 days with a recorded shadow precision per the build triad) and the `review` sweep. Scope: seed + ACTIVE products' backend, tests excluded. Detectors live in `mcp/noctusai/tools/noctus/dev/url_hygiene.py` (shims in `compliance.py`).

Composes with `KB § PATTERNS/security/appsec-craft-canon.md` · `KB § PATTERNS/security/secure-code-review-checklist.md`.
