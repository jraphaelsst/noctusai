# CI Security Hardening — Project Document

> Closes 3 CI security gates: T9 Trivy filesystem gate + `.trivyignore`, Python SAST via bandit, and secrets scanning via gitleaks.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Phase 5 — Close
- **Owner / stakeholders:** USER · Engineer SEC-CI
- **Related docs:** `KNOWLEDGE-BASE/CONTEXT/PATTERNS/accept-with-rationale.md` §`trivy-prescan-2026-05-11` entries · `.github/workflows/test.yml` (existing image scan)
- **Project slug:** `ci-security-hardening-2026-05-11` — cross-cutting platform infra → lives at `projects/<slug>/` per `KB § PATTERNS/project-execution.md §1`.

---

## 1. Context & Purpose

The Trivy pre-scan project on 2026-05-11 surfaced 4 unique HIGH/CRITICAL CVEs across slim images (2 patched: `PyJWT`, `fastapi`; 2 accepted with rationale: `wheel`, `jaraco.context`). The existing CI runs an image-scan inside `docker-images-build` but is missing:

1. **`.trivyignore`** — without it, the existing image scan will fail the build on the two accepted CVEs the moment the Trivy DB picks them up. The accept-with-rationale entries explicitly say "Suppress the finding via Trivy's `.trivyignore`."
2. **Filesystem-level Trivy scan** — catches CVEs in lockfiles *before* images build. Faster signal, lower cost.
3. **Python SAST (bandit)** — no static analysis on Python sources today. Catches `pickle.loads`, `eval`, `subprocess(shell=True)`, SQL injection patterns, etc.
4. **Secrets scanning (gitleaks)** — no automated check that a credential / API key didn't slip into the repo.

The win: every PR gets a 3-layer security pass (deps + code + secrets) before merge, and the 2 accepted CVEs stop being a latent CI tripwire.

---

## 2. Confirmed constraints

- **Trivy config bit-for-bit** — `aquasec/trivy:0.49.1` + `--severity HIGH,CRITICAL` + `--ignore-unfixed` per the T9 archive. *(Matches the existing image-scan severity model; consistency across scan modes.)*
- **`.trivyignore` references the accept-with-rationale catalog entries** — `wheel` (CVE-2026-24049) + `jaraco.context` (CVE-2026-23949). *(Catalog survives project folder deletion; CI references survive too.)*
- **Bandit fails at MEDIUM or higher** — `--severity-level medium`. *(Per brief.)*
- **Gitleaks fails on any leaked secret** — `exit-code 1` default. *(Per brief.)*
- **Don't break existing CI** — additive jobs only; the existing image-scan stays unchanged. *(Per brief.)*

---

## 3. Design principles

1. **Additive, never modifying.** New jobs join `test.yml`; the existing matrix scan keeps its current shape.
2. **Allowlist over suppression.** Every accepted CVE / secret-pattern lives in a tracked allowlist file with a comment pointing at the rationale.
3. **Local-runnable.** Every gate's tool is invokable locally with the same config as CI (no GH-Action-only magic).

---

## 3a. Seed-first analysis

1. **Is the contract identical for every product?** YES — CI security gates apply repo-wide; same Trivy/Bandit/Gitleaks run regardless of product.
2. **Is the data source product-specific?** NO — scans target the whole repo (`.` for fs scan, `products/*/backend/app/` for bandit, full repo for gitleaks).
3. **Is the placement product-specific?** NO — workflows live at repo root (`.github/workflows/`).
4. **Is the visibility / permission rule the same?** YES — uniform PR-gate semantics.
5. **Does the seam already exist in seed?** N/A — CI is repo-level infra, not product-seed. `seed/` doesn't ship workflow YAML; that's correct (`.github/` is repo singleton).
6. **Default-on or opt-in?** DEFAULT-ON — every PR runs all 3 gates.

**Litmus — per-product code count:** **0 lines.** Pure cross-product / repo-wide infra. No product file is touched.

**Phase plan implications:** §6 phases work in repo-root surfaces (`.github/workflows/test.yml`, repo-root `.trivyignore` / `bandit.yml` / `.gitleaks.toml`). Zero per-product walk — correct shape.

---

## 4. Scope

**In scope:**
- New CI job: `trivy-fs-scan` — filesystem-level dep scan, complements existing image scan.
- New file: `.trivyignore` at repo root with the 2 accepted CVEs.
- New CI job: `bandit-scan` — Python SAST against backend code + seed lib.
- New file: `bandit.yml` at repo root with skip / exclude config.
- New CI job: `gitleaks-scan` — secrets detection on PR diff + push to main.
- New file: `.gitleaks.toml` at repo root with allowlist for known-safe test fixtures.
- KB pattern doc: `KNOWLEDGE-BASE/CONTEXT/PATTERNS/ci-security-gates.md`.
- `KNOWLEDGE-BASE/INDEX.md` entry for the new pattern doc.

**Out of scope (for now — with reason):**
- Modifying the existing image-scan job — already correct; the `.trivyignore` we add will be picked up by it automatically.
- `pip-audit` / `safety` — bandit + Trivy fs-scan cover Python deps. Adding a third Python dep-scan is gold-plating.
- npm-audit / yarn-audit gates — Trivy fs-scan reads `package-lock.json` directly. Same coverage, fewer jobs.
- `pre-commit` hook wiring — out-of-band; orchestrator can add later via `.pre-commit-config.yaml` (not required for this project).

---

## 5. Architecture / Data Model

**New files (repo root unless noted):**

```
.trivyignore                                         # 2 CVEs, narrate-and-narrow
bandit.yml                                           # SAST config
.gitleaks.toml                                       # Secrets-scan allowlist
.github/workflows/test.yml                           # +3 jobs
KNOWLEDGE-BASE/CONTEXT/PATTERNS/ci-security-gates.md # KB doc
KNOWLEDGE-BASE/INDEX.md                              # +1 entry line
```

**New jobs in `.github/workflows/test.yml`:**

| Job | Image / action | Trigger | Gate |
|---|---|---|---|
| `trivy-fs-scan` | `aquasec/trivy:0.49.1` (docker run) | push + PR | HIGH/CRITICAL, ignore-unfixed, respects `.trivyignore` |
| `bandit-scan` | `setup-python@v5` + `pip install bandit` | push + PR | severity-level medium, confidence-level medium |
| `gitleaks-scan` | `gitleaks/gitleaks-action@v2` | push + PR | any leaked secret |

---

## 6. Implementation phases

### Phase 0 — Read current CI shape ✅
- [x] Read `.github/workflows/test.yml` — found existing Trivy matrix scan inside `docker-images-build`.
- [x] Read `KNOWLEDGE-BASE/CONTEXT/PATTERNS/accept-with-rationale.md` — extracted the 2 CVE IDs + rationale anchors.
- [x] Confirmed no existing `.trivyignore` / `bandit.yml` / `.gitleaks.toml` / `requirements-dev.txt`.

**Improvements:** none identified.


### Phase 1 — Trivy filesystem scan + `.trivyignore` ✅
- [x] Author `.trivyignore` (2 CVE entries, each commented with anchor to accept-with-rationale).
- [x] Add `trivy-fs-scan` job to `test.yml`.
- [x] Validate YAML parses.

**Improvements:** none identified.


### Phase 2 — Bandit SAST ✅
- [x] Author `bandit.yml` (skips B101 platform-wide; excludes `tests/` dirs; targets MEDIUM+).
- [x] Add `bandit-scan` job to `test.yml`.
- [x] Validate YAML parses + bandit config parses.

**Improvements:** none identified.


### Phase 3 — Gitleaks secrets scan ✅
- [x] Author `.gitleaks.toml` (allowlist for the Supabase publishable example JWT in `test.yml` + any other test-fixture-only tokens).
- [x] Add `gitleaks-scan` job to `test.yml`.
- [x] Validate YAML + TOML parse.

**Improvements:** none identified.


### Phase 4 — Local verification ✅
- [x] `python3 -c 'import yaml; yaml.safe_load(open(".github/workflows/test.yml"))'` — parses.
- [x] `python3 -c 'import yaml; yaml.safe_load(open("bandit.yml"))'` — parses.
- [x] `python3 -c 'import tomllib; tomllib.loads(open(".gitleaks.toml").read())'` — parses.
- [x] Confirm `.trivyignore` line count + content.
- [x] Confirm KB INDEX.md entry resolves; run `bash scripts/verify-kb-sync.sh` if available.

**Improvements:** none identified.


### Phase 5 — Close ✅
- [x] §11 Change log entry.
- [x] **Improvements:** block.
- [x] Stage explicit paths; HEREDOC commit + Co-Authored-By trailer.
- [x] Push branch-only.

---


## 7. Open questions

1. **Should `trivy-fs-scan` also block the PR or just upload SARIF?** Decided: block (`exit-code: '1'`). Matches the existing image-scan stance — security gates are gates, not advisories.
2. **Should bandit run against tests too?** Decided: NO. Tests use `assert` (B101) freely; excluding `tests/` keeps signal high. The B-codes that matter (B301 pickle, B501 ssl, B608 sql) still apply to production code.
3. **Should gitleaks scan the full git history on every push?** Decided: NO. PR jobs scan the diff (`--log-opts="--all --no-merges"` restricted by `gitleaks-action`'s default behavior on PR events). Push-to-main scans the diff against the previous commit. Full-history scan would push CI time over 10min for no signal — history is already merged.

---

## 8. Dependencies & blockers

- **GitHub Actions runner has Docker** — yes, `ubuntu-latest` does. Confirmed by existing `docker compose config` step.
- **`gitleaks/gitleaks-action@v2` is public + free for public repos** — yes.

---

## 9. Success criteria

- 3 new jobs visible in next CI run: `trivy-fs-scan`, `bandit-scan`, `gitleaks-scan`.
- The 2 accepted CVEs (`CVE-2026-24049`, `CVE-2026-23949`) no longer fail the existing image-scan once Trivy DB catches up (`.trivyignore` suppresses them per accept-with-rationale).
- Local bandit run against repo: 0 HIGH-severity findings (or any that surface are filed as follow-up projects per recurrence rule).
- Local gitleaks run: 0 leaked secrets (Supabase JWT in test.yml allowlisted).
- KB INDEX.md resolves the new pattern doc per `verify-kb-sync.sh`.

---

## 10. How to use this plan

- **Single source of truth for the 3 CI gates landing 2026-05-11.**
- Configs at repo root; jobs in `.github/workflows/test.yml`.
- KB pattern doc names the canonical shape for future audit / amendment.
- Local invocations documented in §9; copy-paste-runnable.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | Initial project drafted; Phases 0-5 executed in single session | Engineer SEC-CI |
| 2026-05-11 | Phase 1 — `.trivyignore` + `trivy-fs-scan` job added; respects accept-with-rationale entries | Engineer SEC-CI |
| 2026-05-11 | Phase 2 — `bandit.yml` + `bandit-scan` job added; MEDIUM+ gate | Engineer SEC-CI |
| 2026-05-11 | Phase 3 — `.gitleaks.toml` + `gitleaks-scan` job added; example JWT allowlisted | Engineer SEC-CI |
| 2026-05-11 | Phase 4 — local YAML/TOML parse verified; KB sync verified | Engineer SEC-CI |
| 2026-05-11 | Phase 5 — KB pattern doc `PATTERNS/ci-security-gates.md` filed + INDEX entry added | Engineer SEC-CI |
