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
| **Trivy fs-scan** | `aquasecurity/trivy-action@0.24.0` | `.trivyignore` | `scan-type: fs` | Lockfiles (`requirements.txt`, `package-lock.json`, `Pipfile.lock`, `yarn.lock`, …) at repo root | HIGH/CRITICAL not in `.trivyignore` |
| **Trivy image-scan** (pre-existing) | `aquasecurity/trivy-action@0.24.0` | `.trivyignore` | inside `docker-images-build` matrix | Every built `noctus-<slug>-<role>` image | HIGH/CRITICAL not in `.trivyignore` |
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

For Trivy the action handles both in one step via `exit-code: '1'`; for bandit we run twice with different flags; gitleaks-action does both itself.

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

- **Every `.trivyignore` CVE entry** that's an accepted CVE (not a queued fix) must have a corresponding entry in `KB § PATTERNS/accept-with-rationale.md`. The accept-with-rationale catalog survives project folder deletion; `.trivyignore` references it by short-title.
- **Every `.trivyignore` CVE entry** that's a queued-fix must name the follow-up project in its comment (e.g. `trivy-baseline-cleanup`).
- **Every bandit-baseline entry** is implicit tech debt. If the same B-code surfaces in N≥3 files (across the baseline + new findings), the recurrence rule fires — formalize via a code-pattern fix (e.g. `defusedxml` adoption for all XML parsing).
- **No allowlist entry without a destination.** Same rule as `accept-with-rationale.md § "Accept is a real landing — paperwork keeps it from going silent"`.
