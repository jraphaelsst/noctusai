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

→ Sibling [[KB § PATTERNS/containerization.md § 10]] `VITE_*` build-arg contract · [[KB § PATTERNS/containerization.md § 12b]] freshness contract caught the symptom, this rule fixes the class.

---

## 3 · The canonical-default test (apply before writing any seed literal)

Before adding `|| "X"` / `getenv(..., "X")` / `config.X if config else "X"` in seed code, ask:

> **"What is the architectural canonical answer for this module's contract — independent of any specific consumer?"**

Worked examples:

| Seed seam | Wrong default (consumer-#1 coincidence) | Right default (canonical) |
|---|---|---|
| HTTP base URL in single-container model | `"http://localhost:8000"` (core's port) | `""` → same-origin / relative URL |
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

## 6 · Detection — codify when recurrence ≥3

A keeper detector that scans seed source for literal defaults matching known per-product ports would catch this regression class. Shape:

```python
# pseudocode for check_seed_canonical_default
def check_seed_canonical_default(file):
    for match in re.finditer(r'\|\|\s*"http://localhost:\d+"', source):
        yield Issue(severity="high",
                    message="Seed default is a per-product port literal "
                            "(consumer-#1 coincidence). Use same-origin '' instead.")
```

**Current recurrence count: N=2** — this (`VITE_BACKEND_API_URL` 2026-05-20) + the [[KB § PATTERNS/pydantic-strict-http.md]] silent-drop sibling shape (loose hook + strict default).

**Status: [A] accept-with-rationale at the memory level** until N=3 triggers Stage-4 codification ([[KB § PATTERNS/methodology-codification-pipeline.md]]). Filed: `seed-canonical-defaults-keeper` (follow-up project on N=3 trigger).

---

## 7 · Why this is a separate rule from "Seed first. Always."

"Seed first" says *every product inherits from the seed factory*. This rule says *the seed's defaults must be canonical*. The two compose: a product that correctly inherits from a seed with a non-canonical default still inherits the bug. Fixing the seed without fixing the consumer overrides leaves the override-as-mask in place; fixing the consumer without fixing the seed leaves the next product to bit-by-bit.

**Both directions matter.** When the seed default changes from a coincidence-literal to a canonical answer, audit existing consumer overrides — if a consumer's local override was a workaround for the bad default, the override is now dead code (delete it, per [[KB § PATTERNS/accept-with-rationale.md]] cleanup rules).

---

**Doc anchors.** Memory entry: `feedback_seed_defaults_canonical_not_one_consumer.md` · CLAUDE.md §1 bullet (seed-canonical-defaults rule). Sibling: [[KB § PATTERNS/containerization.md § 5c]] sync runbook · [[§ 12b]] freshness contract. Bit: 2026-05-20 social-wiring.
