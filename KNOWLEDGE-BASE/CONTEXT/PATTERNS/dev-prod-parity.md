# Dev↔prod parity — verify in the PRODUCTION SHAPE, not just dev-green

> The platform's **highest-recurrence drift class** (N≥3). "Works in dev" `≠` "works in prod": the slim prod image is a **structurally different environment**. A change is **not done** until verified in the **production shape** (slim image / live VPS) — `pytest`-green `∧` `vite build`-clean `≠` "works in prod".
>
> This doc is the **discipline** ("what differs between dev and prod, and how you prove the prod shape"). Its **executable form** is [[deploy-config-contract]] (every dev↔prod-divergent knob routes through a seed seam + a boot guard). Its **value-correctness** sibling is [[seed-canonical-defaults]] (a default must be the canonical answer, ¬ a consumer-#1 coincidence).

---

## 1 · Rule

**Be extra careful with any env-sensitive code: dev and prod are STRUCTURALLY DIFFERENT environments.** Dev runs the `runtime-watch` container (source bind-mounted, `node` present, `vite build --watch`, files + env for config). Prod runs the slim `runtime` image (baked `dist`, `node` absent, **no `start.sh` / no PRODUCTS registry**, env-only config). Code that reads its truth from a **dev-only artifact** or leans on a **dev-convenience default** keeps dev green and silently misroutes prod.

The cure has two halves, both mandatory:
- **Authoring time** — ask the parity question (§3) for every env-sensitive line; route divergent knobs through the [[deploy-config-contract]] seam.
- **Deploy time** — **live-probe the prod path** end-to-end (§4); never mark "done" off dev-green alone.

---

## 2 · The dev↔prod difference checklist (noc-specific · OPEN taxonomy)

Each row is a dimension on which dev and the slim prod image differ. A non-fitting new instance → **add a row**, never force-fit.

| Dimension | Dev (`runtime-watch`) | Slim prod (`runtime`) | Implication |
|---|---|---|---|
| `start.sh` / PRODUCTS registry | present | **ABSENT** | Never derive runtime behavior from the registry; derive from `PRODUCT_URL_*` env **directly** (`check_derives_from_dev_only_artifact` enforces). |
| `node` / build tooling | present | absent | No runtime `vite`; the SPA is the **baked `dist`**. |
| FE `dist` | built on demand | **baked at image-build** | `VITE_*` are baked ⇒ change requires a **rebuild**, not a restart. |
| Config source | files `∨` env | **env-only** | Runtime config via `getenv`; route required-in-prod knobs through `resolve_config(..., required_in_prod=True)`. |
| DB `public.products.url_base` | `http://localhost:<port>` (by design) | same (localhost, by design) | **Override via env, never edit the DB**: `PRODUCT_URL_<SLUG>` → `PRODUCT_URL_PATTERN` → DB. |
| CORS allow-origins | registry-derivable | registry **empty** | `derive_cors_origins` reads `PRODUCT_URL_*` env directly + `@registry:all`; pre-deploy gated by `prod_config_parity`. |
| `public.products` rows | full local set | **only what was mirrored to prod** | A missing row ⇒ no launcher tile (social-wiring 032 was unmirrored until 2026-05-22). |
| CI dependency install | per-product reqs | **root superset** | Every per-product dep must be in the root superset (the `sqlalchemy`/`defusedxml` CI-only `ModuleNotFound`). |
| Product LLM key | any provider | **OpenAI / Gemini (no Anthropic key)** | Product-facing LLM calls default to OpenAI/Gemini in prod. |
| `VITE_*` (build-time) vs `getenv` (runtime) | both live | build-time **baked**, runtime per-request | Build-time knob wrong ⇒ rebuild; runtime knob wrong ⇒ restart/recreate. |

---

## 3 · Authoring time — the parity question

For every env-sensitive line, ask: **"Does this hold in the slim prod container, not just my dev box? If dev and prod differ on this dimension, what proves prod works?"**

- **Deriving from a file/artifact?** Confirm it exists in the slim image (`start.sh`, registry, build tool). If it might be absent, **derive from env** with a typed-error / `""` fallback (¬ a localhost literal — [[seed-canonical-defaults]]).
- **Reading config?** Know the layer: build-time (`VITE_*`, baked ⇒ rebuild) vs runtime (`getenv`, per-request ⇒ restart/recreate).
- **A required-in-prod knob with no safe default?** Route it through `require_prod_config([...])` so a missing value **fails the boot loudly**, ¬ silently falls to dev ([[deploy-config-contract]] §4).

---

## 4 · Deploy time — verify in the prod shape (live-probe)

Dev-green is necessary, ¬ sufficient. Before "done":

- **FE bundle** — confirm the baked bundle carries the prod URL (¬ `http://localhost:<port>`).
- **CORS** — `OPTIONS`-preflight the prod origin: `200 + access-control-allow-origin: <origin>`; an evil origin must `400`.
- **Pre-deploy gate** — run `noctus.dev.predeploy_check` with a prod env snapshot so `prod_config_parity` ([[deploy-config-contract]] §5b) catches a present-but-`localhost` value before it ships.
- **Risky cutover** — keep the working override in place during the switch; remove it only **after** the new path is live-verified.
- **Container freshness** — if the running container serves code this session changed, confirm runtime parity (`KB § PATTERNS/containerization.md § 12b`).

---

## 5 · Special cases (each a narrower instance of this rule)

- [[seed-canonical-defaults]] — the **value** is wrong (a consumer-#1-coincidence default).
- [[deploy-config-contract]] — the **executable seam**: divergent knobs → `resolve_config`/`require_prod_config`; the `check_derives_from_dev_only_artifact` keeper (static) + the `prod_config_parity` pre-deploy gate (value-correctness) + the boot guard (runtime presence) are its three legs.
- `KB § PATTERNS/boundary-contract-tests.md` **B4** — container env propagation (`.env` ↔ compose ↔ stage chain ↔ container).
- `KB § PATTERNS/containerization.md § 12b` — a stale running container ("tests green" ≠ "container reflects the fix").

---

## 6 · Slip history — the N≥3 that born the rule (2026-05-20 → 22)

1. `infra.tsx` defaulted the backend URL to `http://localhost:8000` — fine for core, misrouted every other product's FE → CORS → "Servidor indisponível" toasts.
2. Cross-product nav SSO'd users to `http://localhost:8080` in prod: no `PRODUCT_URL_*` override ⇒ fell to the DB `url_base` (seeded localhost **by design**).
3. The sharpest — `derive_cors_origins` built CORS from the `start.sh` PRODUCTS registry, but **the slim prod image ships NO `start.sh`** ⇒ registry empty ⇒ CORS collapsed to localhost-only ⇒ apex login down. Even a *canonical* default wouldn't have saved it: the **derivation source itself was absent in prod**. (CI sibling: per-product test deps missing from the root superset ⇒ `ModuleNotFound` in CI only.)

Each was shipped by a prior agent who verified **dev**, not **prod**. That recurrence (N≥3) is why this is a standing rule, not a war story.

---

**Doc anchors.** Memory: `feedback_dev_prod_parity_verify_in_prod_shape.md`. CLAUDE.md: the "Finish the session — verify" §1 bullet pointer + §2 Map. Siblings: [[deploy-config-contract]] (executable form) · [[seed-canonical-defaults]] (value-correctness). Specifics: `reference_cross_product_nav_url_resolution`. Born 2026-05-22 (nav-remap → prod-CORS session); doc authored 2026-05-23.
