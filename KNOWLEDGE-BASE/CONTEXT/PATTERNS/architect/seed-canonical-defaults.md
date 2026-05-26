# Seed defaults must be the canonical-shared answer, not what works for consumer #1

> **Rule.** When seed code sets a fallback value that consumers can override (`import.meta.env.X || "default"`, `getenv("X", "default")`, `config.X if config else "default"`), the default MUST be the **canonical answer for the architectural model** — never a literal that happens to match consumer #1.

If the default works for consumer #1 but silently misroutes consumers #2..N, you've shipped a coincidence, not a design.

---

## 1 · Why the bug stays silent

- Consumer #1 keeps working → no signal during dev.
- Consumers #2..N either:
  - (a) override locally → masks the bug everywhere it's overridden;
  - (b) silently misroute → user sees opaque `Servidor indisponivel` / CORS-blocked fetch / cross-product blank state, with no log pointing at the seed default.
- Recurrence is hidden because each consumer's local override looks like normal configuration, not corrective.

---

## 2 · The 2026-05-20 bit — social-wiring

`seed/framework/frontend/src/infra.tsx`:

```ts
// WRONG — silently misroutes every non-core product:
const backendUrl = import.meta.env.VITE_BACKEND_API_URL || "http://localhost:8000";

// RIGHT — same-origin per single-container house model:
const backendUrl = import.meta.env.VITE_BACKEND_API_URL ?? "";
```

The `"http://localhost:8000"` default worked for **core only** (whose backend is on :8000). Every non-core product's FE was silently routed at CORE — CORS preflight killed the fetch, `apiClient` threw a generic `Servidor indisponivel`, every toast pointed at the wrong cause.

**Compounding multi-stage Dockerfile drift.** `ENV VITE_SAME_ORIGIN=1` was set only in the `frontend-build` stage. The `runtime-watch` stage (used by `local-watch` containers) is `FROM runtime`, NOT `FROM frontend-build` — so the env never reached the build at container-start. Even after fixing `infra.tsx`, the FE wasn't being told same-origin until each product Dockerfile's `runtime-watch` stage was patched too (9 Dockerfiles, all 9 needed it).

→ Sibling [[KB § PATTERNS/devops/containerization.md § 10]] `VITE_*` build-arg contract · [[KB § PATTERNS/devops/containerization.md § 12b]] freshness contract caught the symptom, this rule fixes the class.

---

## 2a · The 2026-05-20 second bit — vite factory PRODUCT_MAP + `|| 8000` fallback (N=3)

Even after fixing `infra.tsx` + the 9 `runtime-watch` envs, social-wiring's container **still** served a bundle with `localhost:8000` baked into `VITE_BACKEND_API_URL`. The dashboard kept toasting `Servidor indisponivel (/api/notificacoes/contagem)` etc. Same symptom, deeper root.

`seed/framework/frontend/vite.config.factory.ts`:

```ts
const PRODUCT_MAP: Record<number, { backend: number; schema: string }> = {
  5173: { backend: 8000, schema: "public" },           // core
  8080: { backend: 8001, schema: "erp" },              // erp-imobiliario
  8090: { backend: 8002, schema: "personal-finance" }, // personal-finance
  8095: { backend: 8003, schema: "therapy" },          // therapy-platform
  8100: { backend: 8004, schema: "seed" },             // seed
  8110: { backend: 8005, schema: "daily_life" },       // daily-life
  8130: { backend: 8007, schema: "adconnect" },        // adconnect
  // ⚠ MISSING: 8160 (social-wiring), W2.x ports, dev-team — when a
  //   product's FE port isn't here, the fallback hits.
};

// WRONG — `|| 8000` is a consumer-#1 coincidence: 8000 is CORE's backend
// port. Any non-mapped product falls through to core, then `define`
// injects `JSON.stringify("http://localhost:8000")` into every literal
// `import.meta.env.VITE_BACKEND_API_URL` in product+seed code → bundle
// hardcodes core's port at every consumer.
const resolvedBackendPort = backendPort || productInfo?.backend || 8000;
```

**Two compounding canonical-coincidence bugs**:
1. **`PRODUCT_MAP` drift** — every new product needs an entry added; an unmapped product silently falls to core's port. Same shape as [[KB § PATTERNS/feedback_hardcoded_product_slug_set_keeper]].
2. **`|| 8000` fallback** — even if `PRODUCT_MAP` were exhaustive, the seed fallback for an unknown port should NOT be a per-product literal at all. The architecturally-correct fallback is throw / typed-error (so adding a product without registering it is a loud build failure, not silent misroute).

The bug stayed hidden because `VITE_SAME_ORIGIN=1` (when set) short-circuits the PRODUCT_MAP lookup entirely (`window.location.origin` injected raw). The `infra.tsx` fix worked for products that built with `VITE_SAME_ORIGIN=1`; products whose `runtime-watch` lost the env got the second bug.

**Live remediation in this session** (in-flight, one container): rebuilt social-wiring's FE bundle inside the container with `VITE_SAME_ORIGIN=1` explicitly — bundle now contains 3× `window.location.origin` and zero `VITE_BACKEND_API_URL:"..."` literals. Dashboard works.

**Structural remediation shipped 2026-05-20 (in-flight, per §2.13a):**
- ✅ `PRODUCT_MAP` literal **removed entirely** — the factory now parses the `start.sh PRODUCTS` block at vite build time (the single source of truth the Python seed-lib `noctusai_lib.config.cors_registry.parse_products_registry` already consumes). Both sides derive from the same authored source ⇒ registry drift is structurally impossible.
- ✅ `|| 8000` fallback **replaced by `throw new Error(...)`** in `resolveBackendPort()` — adding a product without registering it in `start.sh PRODUCTS` is now a loud build failure (`vite.config.factory: frontend port N is not in the start.sh PRODUCTS registry...`).
- ✅ Companion bystander fix: `seed/lib/frontend/src/env.ts` `BACKEND_API_URL` `|| 'http://localhost:8000'` → `?? ''` (same class). `CORE_URL` / `CORE_API_URL` annotated `canonical-default-ok` (core IS a named service every product navigates to — not consumer-#1 coincidence; see §4).
- ✅ Stage-4 keeper `check_seed_canonical_default` shipped (Pattern A: URL form; Pattern B: registry-derived numeric port fallback). Block-comment + string-content aware (no false positives in throw-message text explaining the bug). Rationale escape hatch `canonical-default-ok` in 5-line preceding-window or same-line.

The `VITE_SAME_ORIGIN=1` propagation gap during `npm run build` initial-run remains an open audit item — captured in `findings.md` of any future containerization session, not a separate project file.

---

## 3 · The canonical-default test (apply before writing any seed literal)

Before adding `|| "X"` / `getenv(..., "X")` / `config.X if config else "X"` in seed code, ask:

> **"What is the architectural canonical answer for this module's contract — independent of any specific consumer?"**

Worked examples:

| Seed seam | Wrong default (consumer-#1 coincidence) | Right default (canonical) |
|---|---|---|
| HTTP base URL in single-container model | `"http://localhost:8000"` (core's port) | `""` → same-origin / relative URL |
| Vite factory fallback backend port for unmapped FE port | `\|\| 8000` (core's port) | `throw "register the product in PRODUCT_MAP"` — typed error |
| Vite factory product registry | hand-maintained `PRODUCT_MAP` literal | derived from `parse_products_registry()` (single source) |
| DB schema in multi-product schema-isolation | `"public"` | injected via product factory; no literal |
| Auth provider | `SupabaseAuth()` | injected via named seam; no literal |
| LLM model | `"gpt-4o-mini"` | product's configured model |
| Storage backend | `LocalDiskBackend()` | factory-resolved; Fake in tests, Real via env |
| Webhook signature scheme | `"hub_signature"` | per-integration explicit; no literal |
| Redis URL | `"redis://localhost:6379"` | env-required or typed-error |

---

## 4 · The "no canonical answer at seed-level" case

If the canonical answer **genuinely can't be known at seed-level** (e.g. a per-product port, a tenant-scoped path), the default must be one of:

- `""` / `None` / typed-error — **anything but a literal that pretends to know**.

Consumers then either configure explicitly or get a clean failure. A loud `MissingConfigError` at startup is infinitely better than a silent misroute at request time.

---

## 5 · Multi-stage Dockerfile inheritance — paired rule

Env vars declared in stage A are **NOT inherited** by stage B unless `B FROM A`. Every Dockerfile stage that *runs the FE build* (or any other config-consuming step) must re-declare every env the build needs.

Pattern: put `ENV VITE_X=Y` (or its analogues for build-time config) **inside every stage that runs the build**, not just one. In the seed:

- `frontend-build` stage → builds dist at image-bake → needs envs ✓
- `runtime-watch` stage → builds dist at container-start via `vite build --watch` → needs envs ✓ (separately)
- `runtime` (slim, prod) → consumes pre-baked dist → no FE build → doesn't need them

The 9 product Dockerfile patches in the 2026-05-20 commit add `ENV VITE_SAME_ORIGIN=1` to each product's `runtime-watch` stage tail.

→ The auto-propagation path is `scripts/propagate-dockerfiles.sh` — when the seed Dockerfile grows a new ENV, propagate it across the fleet. Future canonical envs should land in seed first, then propagate.

---

## 6 · Detection — codified Stage-4 keeper (shipped 2026-05-20)

`check_seed_canonical_default` lives in `mcp/noctusai/tools/noctus/dev/compliance.py` and runs as part of `check_all_products`. Two regression patterns, both `severity="warning"`:

**Pattern A — URL form:** `(\|\||\?\?)\s*"http(s)?://localhost:\d+"` on the comment-stripped line (string contents preserved so a URL *inside* a string still matches; a `/* ... */` doc comment mentioning the URL does not).

**Pattern B — numeric port fallback:** `\|\|\s*<port>\b` where `<port>` is in the live `start.sh PRODUCTS` registry. Backend ports are obtained via `parse_products_registry()` (derives from the same source the runtime parses — registry drift is impossible). Pattern B scans a **code-only** version of the line (comments AND string contents blanked out) so a `|| 8000` mentioned inside a throw-message string explaining the bug does not re-trigger.

**Scope:** `seed/{lib,framework}/{backend,frontend}/**/*.{py,ts,tsx,js,jsx}`. Product code excluded (a product hardcoding its own port is local choice; the *seed* hardcoding any single product's port is the recurring bug). Vendored deps + `dist/` + `__pycache__` excluded by walk filter.

**Rationale escape hatch:** a `canonical-default-ok` keyword on the same line or in the **5 preceding lines** waives the flag. Use for legitimate named-service references (e.g. `CORE_URL` — core IS a specific named service, not a consumer-#1 coincidence; see §4) and test harnesses bound to a known port. The window allows a normal multi-line comment block to carry the rationale.

**Live tree baseline:** 0 issues after the 2026-05-20 structural fix landed (was 7 before — `infra.tsx`, `env.ts:120`, `vite.config.factory.ts:93`, plus 3 `CORE_URL`/`CORE_API_URL` sites now annotated, plus 1 already-fixed by the morning patch).

**Recurrence count: N=3 → status `[F] formalize` (closed by this keeper):**
1. `infra.tsx` `|| "http://localhost:8000"` default (§2, 2026-05-20 morning) — fixed.
2. [[KB § PATTERNS/backend/pydantic-strict-http.md]] silent-drop sibling shape (loose hook + strict default) — separately codified.
3. `vite.config.factory.ts` PRODUCT_MAP + `|| 8000` fallback (§2a, 2026-05-20 evening — same day, deeper layer) — fixed structurally (PRODUCT_MAP removed; `throw` on unmapped).

Future regressions: pre-commit warn; promote to `severity="high"` (gate-blocking) once any newly-flagged site has been triaged.

---

## 7 · Why this is a separate rule from "Seed first. Always."

"Seed first" says *every product inherits from the seed factory*. This rule says *the seed's defaults must be canonical*. The two compose: a product that correctly inherits from a seed with a non-canonical default still inherits the bug. Fixing the seed without fixing the consumer overrides leaves the override-as-mask in place; fixing the consumer without fixing the seed leaves the next product to bit-by-bit.

**Both directions matter.** When the seed default changes from a coincidence-literal to a canonical answer, audit existing consumer overrides — if a consumer's local override was a workaround for the bad default, the override is now dead code (delete it, per [[KB § PATTERNS/common/accept-with-rationale.md]] cleanup rules).

---

**Doc anchors.** Memory entry: `feedback_seed_defaults_canonical_not_one_consumer.md` · CLAUDE.md §1 bullet (seed-canonical-defaults rule). Sibling: [[KB § PATTERNS/devops/containerization.md § 5c]] sync runbook · [[§ 12b]] freshness contract. Bit: 2026-05-20 social-wiring.
