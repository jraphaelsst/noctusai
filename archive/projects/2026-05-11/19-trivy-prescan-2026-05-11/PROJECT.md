# trivy-prescan-2026-05-11 — Project Document

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Scan complete → triage drafted → awaiting architect decision (patch vs grace flag)
- **Owner / stakeholders:** rapha (architect); engineer A1
- **Related docs:** KB §11f Trivy first-push grace playbook (referenced from dispatch brief); `KNOWLEDGE-BASE/CONTEXT/PATTERNS/accept-with-rationale.md` (entries appended this project); sibling brief Aggregate-4 (CI workflow edits — separate scope).
- **Project slug:** `trivy-prescan-2026-05-11` — cross-cutting platform security work; lives at `projects/<slug>/` per scope→location rule.

---

## 1. Context & Purpose

T9 (CI Trivy gate) will start blocking pushes that surface HIGH/CRITICAL CVEs on the slim Docker images once it lands. Before T9 deploys, this project pre-scans the two currently-built slim images (`noctus-seed-backend:slim`, `noctus-youtube-crawler-backend:smoke`) using the exact Trivy config T9 will use (`aquasec/trivy:0.49.1`, `--severity HIGH,CRITICAL`, `--ignore-unfixed`), triages every finding into patchable / accept / false-positive, and recommends a first-push action (patch the deps OR open the grace flag).

**Win:** the moment T9 enables the gate, we already know the expected scan result and have a documented plan to land on green.

## 2. Confirmed constraints

- **Scan exactness** — match T9 CI gate config bit-for-bit (`aquasec/trivy:0.49.1` + `--severity HIGH,CRITICAL` + `--ignore-unfixed`). *(Anything looser produces false reassurance.)*
- **Scope is scan + triage only** — no source patches in this commit; no `.github/workflows/test.yml` edits. *(Patching is a follow-up decision; CI edits are sibling brief Aggregate-4.)*
- **CVEs that DO have a fix** can still be "accept" if the fix would break the runtime contract or the package is not in the exercised attack surface. *(Per-CVE analysis required, not auto-patch.)*

## 3. Design principles

1. **Trivy is the ground truth** — JSON output drives the table; human commentary explains the triage, not the count.
2. **Per-CVE rationale** — every finding lands on patch / accept / FP with a one-line reason that survives the project's archival.
3. **The accept-with-rationale catalog is the durable home** — entries land in `KB § PATTERNS/accept-with-rationale.md` so the rationale outlives this project folder.

## 3a. Seed-first analysis

1. **Contract identical for every product?** YES — every product's backend Dockerfile is a slug+port copy of `products/seed/backend/Dockerfile`; the same Python 3.11-slim base + same pip-installed deps means CVE inventories are essentially identical (confirmed empirically: both images return the same 4 unique CVEs).
2. **Data source product-specific?** NO — CVE data is pulled from Trivy's DB; same for every image.
3. **Placement product-specific?** NO — CVE triage and accept-rationale entries live in cross-product KB.
4. **Visibility/permission rule the same?** N/A — this is a scan-and-document project, no runtime gate.
5. **Does the seam already exist in seed?** YES — `KB § PATTERNS/accept-with-rationale.md` is the catalog; this project appends entries there.
6. **Default-on or opt-in?** N/A.

**Litmus** — per-product code count this design requires: **0 lines** (pure cross-product concern; catalog entries cover both images at once).

## 4. Scope

**In scope:**
- Run Trivy against both built slim images with T9-equivalent config.
- Triage each finding into patchable / accept / FP with rationale.
- Draft accept-with-rationale entries for un-fixable findings (or findings where the fix is non-trivial / not yet exercised).
- Recommend first-push action (patch vs grace flag).

**Out of scope (for now):**
- Source patches to `requirements.txt` — *(architect decides whether to dispatch a patch engineer)*.
- `.github/workflows/test.yml` edits — *(sibling brief Aggregate-4 owns CI scope)*.
- Other product images (`adconnect`, `erp-imobiliario`, `personal-finance`, etc.) — *(only `noctus-seed-backend:slim` and `noctus-youtube-crawler-backend:smoke` are pre-cached this session; other slim images will scan identically since they share the Dockerfile pattern)*.

## 5. Architecture / Data Model

N/A — process-only project.

## 6. Phase plan

- **Phase 1 — scan.** Pull / verify `aquasec/trivy:0.49.1`; scan both images; capture JSON + table outputs. *(Done.)*
- **Phase 2 — triage.** Parse JSON; per-CVE: package, installed→fixed, attack-surface check, bucket (patch / accept / FP), rationale. *(Done.)*
- **Phase 3 — draft accept entries.** Append entries to `KB § PATTERNS/accept-with-rationale.md` for findings where "patch" isn't the obvious answer. *(Done.)*
- **Phase 4 — report.** `findings.md` summarizes counts, table, recommended first-push action. *(Done.)*
- **Phase 5 — close.** Commit + push; architect decides whether to dispatch a patch engineer or open the grace flag in T9.

## 7. Open questions

- **Q1.** For starlette CVE-2024-47874 (multipart DoS): we don't expose any FastAPI multipart endpoints today, but the seed includes `BaseHTTPMiddleware` which depends on starlette. Patch via the implicit `fastapi==0.115.0 → 0.115.5+` bump (which brings starlette ≥0.40.0) or accept-with-rationale on the not-exercised attack surface? **Recommendation:** patch — the fastapi bump is a patch-level move with no breaking changes, and it closes the finding cleanly rather than carrying catalog debt.
- **Q2.** For wheel CVE-2026-24049 (wheel-unpack PE): `wheel` is a *build-time* package; in our multi-stage Dockerfile it ends up in the runtime venv via pip's bootstrap. At runtime we never invoke `wheel unpack`. The exploit requires running `wheel unpack <malicious.whl>` on a user-controlled file. **Recommendation:** accept-with-rationale (not-exercised attack surface) + optional follow-up to scrub `wheel` from the runtime venv during the builder→runtime copy (mechanically: `pip uninstall -y wheel` in the builder stage right before the copy). N=1 today; if a second non-exercise-surface package emerges, formalize the scrub step in seed Dockerfile.
- **Q3.** For jaraco.context CVE-2026-23949 (tarball path traversal): transitive via setuptools/pip. Same exposure shape as wheel — we never invoke `jaraco.context.tarball()`. **Recommendation:** same as Q2 — accept-with-rationale.
- **Q4.** For PyJWT CVE-2026-32597 (crit header validation): we use PyJWT for token decoding in the auth path. The exploit requires an attacker to craft a JWT with an unknown `crit` extension. **Recommendation:** patch — PyJWT is in the live token-validation path; the 2.9.0 → 2.12.0 bump is API-compatible (no breaking changes in 2.x); patching is cheaper than carrying the catalog entry.

## 8. Phase tracker

- Phase 1 — scan: complete (2026-05-11)
- Phase 2 — triage: complete (2026-05-11)
- Phase 3 — accept entries: complete (2026-05-11)
- Phase 4 — report: complete (2026-05-11)
- Phase 5 — close: in progress

## 10. Reproduction recipe

```bash
# Pull Trivy (already pre-cached this session)
docker pull aquasec/trivy:0.49.1

# Scan seed
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:0.49.1 image \
    --severity HIGH,CRITICAL --ignore-unfixed --format json --timeout 15m \
    noctus-seed-backend:slim > /tmp/trivy-seed.json

# Scan youtube-crawler
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:0.49.1 image \
    --severity HIGH,CRITICAL --ignore-unfixed --format json --timeout 15m \
    noctus-youtube-crawler-backend:smoke > /tmp/trivy-yt.json

# Note: --timeout 15m needed on the YT run; default 5m hit context-deadline-exceeded.
```

## 11. Change log

- **2026-05-11** — project filed; Phase 1-4 executed in one engineer dispatch; findings.md authored; 2 accept-with-rationale entries appended.
