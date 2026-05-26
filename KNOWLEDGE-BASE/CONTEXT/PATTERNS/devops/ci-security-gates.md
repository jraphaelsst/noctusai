# CI security gates

> Three-layer PR security pass: deps (Trivy) + code (bandit) + secrets (gitleaks). Plus the canonical allowlist / baseline patterns that let the gates land without bulk-fixing pre-existing tech debt.

Lives at `.github/workflows/test.yml`. First landed 2026-05-11 via the `ci-security-hardening` project.

## Table of contents

1. The three gates at a glance
2. Trivy — filesystem + image scans
3. Bandit — Python SAST
4. Gitleaks — secrets scanning
5. Allowlist vs baseline — when to use which
6. Job shape — the canonical pattern every security job follows
7. Local invocations
8. Relationship to accept-with-rationale + recurrence rule

---

## 1 · The three gates at a glance

| Gate | Tool | Config file | Action / image | Scope | Gate condition |
|---|---|---|---|---|---|
| **Trivy fs-scan** | `aquasecurity/trivy-action@v0.36.0` | `.trivyignore` | `scan-type: fs` | Lockfiles (`requirements.txt`, `package-lock.json`, `Pipfile.lock`, `yarn.lock`, …) at repo root | HIGH/CRITICAL not in `.trivyignore` — **requires `limit-severities-for-sarif: true`**, else gates on ALL severities (§ 2a) |
| ~~**Trivy image-scan**~~ (removed 2026-05-22) | — | — | was inside `docker-images-build` matrix | — | Removed — duplicated `build-and-push.yml`; image CVE coverage rides the deploy build |
| **Bandit** | `bandit==1.9.4` | `bandit.yml` + `bandit-baseline.json` | `setup-python@v5` + `pip install` | `products/*/backend/app/` + `seed/lib/backend/noctusai_lib/` | NEW MEDIUM+ finding (existing findings grandfathered in baseline) |
| **Gitleaks** | `gitleaks/gitleaks-action@v2` | `.gitleaks.toml` | GH Action | Full repo on push to main; diff on PR | Any leaked secret not in allowlist |

All three gates upload a SARIF report to the GitHub Security tab via `github/codeql-action/upload-sarif@v3` with `if: always()` so the report is visible even when the gate fails.

---

## 2 · Trivy — filesystem + image scans

**Two scan modes, same DB, complementary coverage.**

- **fs-scan** reads lockfiles. Catches vulnerable deps **before** any image builds. Fast (< 30s typically). New job, lands at `trivy-fs-scan`.
- **image-scan** reads the built OCI image. Catches additional CVEs from base OS packages (apt/apk-installed deps). Already wired into `docker-images-build` matrix (per product × role).

Both honour the same `.trivyignore` at repo root. Both use the canonical config (per the T9 spec recorded in `accept-with-rationale.md § "Entries from trivy-prescan-2026-05-11"`):

```
aquasec/trivy:0.49.1 (pinned, not @latest)
--severity HIGH,CRITICAL
--ignore-unfixed
```

The action wraps the CLI; pass `severity` / `ignore-unfixed` / `trivyignores` as YAML keys.

> **Action version:** the fs-scan now pins `aquasecurity/trivy-action@v0.36.0` (the prior `@0.24.0` was **yanked** — 2026-05-22). Tags are v-prefixed. The standalone Trivy **image-scan** matrix was removed 2026-05-22 (it duplicated `build-and-push.yml`'s build); image CVE coverage rides the deploy build, not `test.yml`.

---

## 2a · The severity-filter gotcha — `limit-severities-for-sarif` (THE 2026-05-22 bit)

**A single-step Trivy gate with `format: sarif` does NOT gate on `severity:` unless you also set `limit-severities-for-sarif: true`.**

In `format: sarif` mode, `trivy-action` writes **ALL** severities to the SARIF *regardless* of the `severity:` input (by design — so the GitHub Security tab shows everything). `exit-code: 1` is then evaluated against **that full SARIF**, so the gate trips on **ANY** finding — **including MEDIUM/LOW**. A step that reads `severity: HIGH,CRITICAL` + `format: sarif` + `exit-code: '1'` is therefore a **liar**: it advertises HIGH/CRITICAL but fails on a MEDIUM.

```yaml
# WRONG — fails on MEDIUM despite claiming HIGH/CRITICAL:
with:
  format: sarif
  severity: HIGH,CRITICAL
  exit-code: '1'
# RIGHT — SARIF + exit-code both honor `severity:`:
with:
  format: sarif
  severity: HIGH,CRITICAL
  limit-severities-for-sarif: true   # ← the missing line
  exit-code: '1'
```

**The bit.** 2026-05-22 the fs-scan gate stayed red for hours after the deployable tree was provably 0 HIGH/CRITICAL. Root cause: the SARIF carried **two MEDIUMs** — `CVE-2025-68470` (react-router, CVSS 6.5) + a `jwt-token` (the public Supabase **demo** anon key hardcoded in `playwright.config.ts` + `test.yml`, CVSS 5.5) — and the gate tripped on them. **Fix = both layers (resolve, not ignore):** (1) add `limit-severities-for-sarif: true` so the gate enforces its declared threshold; (2) resolve the two mediums at source anyway — bump `react-router-dom` → 6.30.3, and de-hardcode the demo JWT to a non-secret placeholder (`test-publishable-key-e2e-only`; E2E mocks the backend so no real key is needed). Also removed the now-dead `.gitleaks.toml` allowlist entry for that JWT.

**Diagnostic lessons (how the truth was found — `format: sarif` hides the table):**
- **Raw SARIF is the ground truth** for "what failed the gate": `gh api repos/{owner}/{repo}/code-scanning/analyses` → newest `category=="trivy-fs"` → `gh api .../analyses/{id} -H "Accept: application/sarif+json"`. Read each result's `level` + the rule's `properties.security-severity`.
- **GitHub buckets by CVSS, the Trivy gate uses VENDOR severity** — they diverge. A code-scanning alert shown as "medium" (CVSS 5–6.9) can still be what a *vendor-severity* gate trips on, and a trivy-HIGH can display as CVSS-medium. Don't trust the GitHub bucket to predict the gate.
- **Stale local Trivy DB → false 0.** `trivy fs` reuses a cached DB until `NextUpdate`, so a "fresh" local scan can be hours stale and report a false clean. Force it: `rm -rf ~/Library/Caches/trivy/db` then re-scan. Verify the DB `UpdatedAt` in `metadata.json`.
- **Default scanners are `vuln,secret`.** A diagnostic run with `--scanners vuln` silently skips the secret scanner — and the failer here was a secret. Match CI: no `--scanners` override, or pass both.
- The **public-key false-positive** resolution is **de-hardcoding** (env / non-secret placeholder), NOT a scanner allowlist (the user rightly rejects allowlist-as-fix). A JWT-shaped literal in committed source is bad hygiene even when the value is a documented public demo key.

**Why this dual-scan shape:**
1. **Faster signal.** Lockfile-changed PRs fail in the fs-scan within seconds; no need to wait 5-15min for image builds.
2. **Different surfaces.** Lockfile CVEs surface npm/pip-level issues (lodash, PyJWT); image CVEs surface base-OS issues (Debian openssl, libc). Different attackers, different fixes.
3. **Single allowlist file.** `.trivyignore` works for both modes — one place to track exceptions.

---

## 3 · Bandit — Python SAST

Bandit runs the standard plugin set against backend code with two key configs:

- `bandit.yml` at repo root — `skips`, `exclude_dirs` (tests, venvs, migrations).
- `bandit-baseline.json` at repo root — JSON snapshot of currently-known findings.

**The baseline pattern is the canonical bandit shape for adding the gate to an existing codebase.**

Generated via:
```bash
bandit -r <paths> -c bandit.yml --severity-level medium --confidence-level medium \
  -f json -o bandit-baseline.json --exit-zero
```

Then committed. CI runs:
```bash
bandit -r <paths> -c bandit.yml --severity-level medium --confidence-level medium \
  --baseline bandit-baseline.json -f screen
```

`--baseline` makes bandit return exit=0 if the only findings are ones in the baseline. **Any NEW finding (severity ≥ MEDIUM, confidence ≥ MEDIUM) introduced by a PR fails the job.**

The baseline file is itself tracked technical debt. When a finding in the baseline is fixed, the baseline file should be regenerated (or hand-edited) so the gate stops grandfathering it.

**Why pin to bandit 1.9.4:** verified compatible with Python 3.11+. Earlier 1.7.x line has known incompatibilities with Python 3.12+ AST changes ("`Constant` object has no attribute 's'").

---

## 4 · Gitleaks — secrets scanning

`gitleaks/gitleaks-action@v2` auto-detects the event shape:
- **Push to main:** scans the diff against `HEAD~1` (fast).
- **Pull request:** scans the PR diff against the base branch.

Full-history scan is intentionally out-of-scope: history is already merged, the scan would push CI past 10min for zero new signal.

`.gitleaks.toml` extends the bundled default ruleset (`useDefault = true`) and adds a repo-specific allowlist:
- **`regexes`** match the leaked value itself. Use for known-safe public values (Supabase demo JWT, test-fixture placeholders like `noctus_k_abc123`, `tok_pending_001`).
- **`paths`** match file paths. Use for whole directories that are fixture-only (`tests/fixtures/`, `tests/data/`).

**Don't widen `paths` to `tests/` wholesale** — real secrets can land in test setup. Prefer narrow `regexes` for placeholder patterns.

---

## 5 · Allowlist vs baseline — when to use which

| Mechanism | Tool | Use when |
|---|---|---|
| `.trivyignore` | Trivy | A specific CVE has an accept-with-rationale entry, OR is queued for a follow-up dep-bump project. Comment with anchor to catalog. |
| `bandit-baseline.json` | Bandit | Existing codebase has N pre-existing findings; bulk-fixing them expands scope. Grandfather the existing set; gate NEW findings. |
| `.gitleaks.toml` regexes | Gitleaks | Known-safe public value (demo JWT, documented test placeholder pattern). |
| `.gitleaks.toml` paths | Gitleaks | Whole directory is fixtures (`tests/fixtures/`). |
| `# nosec BXXX` inline | Bandit | Single intentional violation with rationale-in-comment. Keep rare; prefer baseline. |

**Anti-pattern:** sliding everything into the allowlist to silence the gate. Each entry must point at either:
- An `accept-with-rationale` catalog entry (durable register), OR
- A follow-up project that owns the fix.

Silent suppression = silent-error shape (`KB § 01-PHILOSOPHY.md § No silent errors`).

---

## 6 · Job shape — the canonical pattern every security job follows

Every security job in `.github/workflows/test.yml` follows the same 3-step shape:

1. **Run the tool with `--exit-zero` / `exit-code: 0`**, emit SARIF.
2. **Upload SARIF** with `if: always()` so the report is visible even when the gate fails.
3. **Re-run the tool as a gate**, this time with the real exit-code.

The split is intentional: the SARIF upload is the diagnostic value (reviewers see WHICH CVE / WHICH B-code / WHICH leaked-secret-pattern failed). The gate is the merge-blocker.

For Trivy the action does both in one step via `exit-code: '1'` — **but only correctly if `limit-severities-for-sarif: true` is also set** (else `format: sarif` reports all severities and the exit-code gates on all of them, including MEDIUM — see § 2a). For bandit we run twice with different flags; gitleaks-action does both itself.

---

## 7 · Local invocations

Copy-paste ready, same config as CI:

```bash
# Trivy filesystem scan
trivy fs --severity HIGH,CRITICAL --ignore-unfixed --ignorefile .trivyignore .

# Trivy image scan (single image)
trivy image --severity HIGH,CRITICAL --ignore-unfixed --ignorefile .trivyignore \
  noctus-seed-backend:slim

# Bandit — generate baseline (run once when adding the gate)
bandit -r products/*/backend/app/ seed/lib/backend/noctusai_lib/ \
  -c bandit.yml --severity-level medium --confidence-level medium \
  -f json -o bandit-baseline.json --exit-zero

# Bandit — gate (matches CI)
bandit -r products/*/backend/app/ seed/lib/backend/noctusai_lib/ \
  -c bandit.yml --severity-level medium --confidence-level medium \
  --baseline bandit-baseline.json -f screen

# Gitleaks — full repo
gitleaks detect --no-git --source . --config .gitleaks.toml --verbose
```

---

## 8 · Relationship to accept-with-rationale + recurrence rule

- **Every `.trivyignore` CVE entry** that's an accepted CVE (not a queued fix) must have a corresponding entry in `KB § PATTERNS/common/accept-with-rationale.md`. The accept-with-rationale catalog survives project folder deletion; `.trivyignore` references it by short-title.
- **Every `.trivyignore` CVE entry** that's a queued-fix must name the follow-up project in its comment (e.g. `trivy-baseline-cleanup`).
- **Every bandit-baseline entry** is implicit tech debt. If the same B-code surfaces in N≥3 files (across the baseline + new findings), the recurrence rule fires — formalize via a code-pattern fix (e.g. `defusedxml` adoption for all XML parsing).
- **No allowlist entry without a destination.** Same rule as `accept-with-rationale.md § "Accept is a real landing — paperwork keeps it from going silent"`.
