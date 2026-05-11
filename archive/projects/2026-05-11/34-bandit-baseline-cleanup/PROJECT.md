# bandit-baseline-cleanup — Project Document

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Phase 3 — Baseline regenerated; tests green
- **Owner / stakeholders:** USER · Engineer BANDIT-CLEANUP (dispatched by SEC-CI architect)
- **Related docs:** `bandit-baseline.json`, `bandit.yml`, `.github/workflows/test.yml` (`bandit-scan` job)
- **Project slug:** `bandit-baseline-cleanup` — lives at `projects/<slug>/` (cross-product baseline cleanup spanning 3 products).

---

## 1. Context & Purpose

When SEC-CI shipped the bandit SAST job, it grandfathered 4 pre-existing
findings in `bandit-baseline.json` so the gate would only fail on NEW
issues. This project clears the baseline by addressing the 4 pre-existing
findings (3 XML parsers + 1 SHA1) so the baseline drops to zero and the
gate becomes a strict "no MEDIUM+ findings" line.

---

## 2. Confirmed constraints

- **Findings touch 3 products** — adconnect, erp-imobiliario, therapy-platform; in-flight engineers (STRICT-HTTP, SLOWAPI-PEP563-DETECTOR, HOUND-ABC-FILTER, SEED-RATELIMIT-FIXTURE, RESPONSE-MODEL-AUDIT) are disjoint from these files (verified by `git log` + file-path inspection).
- **SHA1 usage is idempotency, not security** — `hashlib.sha1(...)` in `therapy-platform/scheduling/service.py` derives a Google Calendar `request_id` (events.insert dedup token); not stored anywhere.
- **defusedxml not yet a dep** — must add to requirements.txt of each touched product backend.

---

## 3. Design principles

1. **Smallest possible diff per finding** — drop-in replacements only; no API surface changes.
2. **Verify external compat before swapping** — SHA1 → SHA256 only after confirming no persisted state depends on the hash format.
3. **Test what we touch** — at minimum re-run product pytest; add unit tests if the security swap changes externally-observable behavior.

---

## 3a. Seed-first analysis

1. **Is the contract identical for every product?** NO — each finding is product-local (NF-e parsing vs DIMOB tax XML vs property feeds vs therapy idempotency).
2. **Is the data source product-specific?** YES — each touches product-specific XML schemas / idempotency keys.
3. **Is the placement product-specific?** YES — services bound to product domain.
4. **Is the visibility / permission rule the same?** N/A — defensive parsing / hash choice.
5. **Does the seam already exist in seed?** NO — `defusedxml` is a stdlib-drop-in; no seed abstraction needed. SHA256 is stdlib.
6. **Default-on or opt-in?** Default-on (defensive parsing should be default everywhere).

**Litmus — per-product code count:** A small section per product (4 line-targeted edits across 4 files in 3 products). No replication framing — each is a unique site.

**Recurrence rule:** If another product introduces XML parsing or weak-hash usage at N=2+, file a seed-side helper (e.g., `noctusai_lib.primitives.xml.safe_parse`). Currently N=1 each — no seed move warranted.

---

## 4. Scope

**In scope:**
- Swap `xml.etree.ElementTree.fromstring` → `defusedxml.ElementTree.fromstring` in adconnect/nfe_xml_parser.py.
- Swap `xml.dom.minidom.parseString` → `defusedxml.minidom.parseString` in erp-imobiliario/{dimob_service,xml_feeds}.py.
- Swap `hashlib.sha1` → `hashlib.sha256` in therapy-platform/scheduling/service.py.
- Add `defusedxml>=0.7.1` to adconnect + erp-imobiliario requirements.txt.
- Regenerate `bandit-baseline.json` (should drop to zero results).

**Out of scope (for now):**
- Seed-side XML safe-parser helper — N=1 per product right now; recurrence not fired.
- CI tightening (removing `--baseline` flag from the gate) — separate SEC-CI follow-up.

---

## 5. Architecture / Data Model

No data-model changes. Pure import + call-site replacements.

---

## 6. Phases

| Phase | Goal | Status |
|---|---|---|
| 0 | Inventory baseline (read JSON, confirm file:line accuracy, check collision) | Done |
| 1 | Diagnose each — FIX vs ACCEPT-WITH-RATIONALE | Done — all 4 = FIX |
| 2 | Apply fixes + add `defusedxml` dep | Done |
| 3 | Regenerate baseline + verify zero findings | Done |
| 4 | Per-product pytest verification | Done |

---

## 11. Change Log

- 2026-05-11 — Engineer BANDIT-CLEANUP dispatched on SEC-CI baseline cleanup.
- 2026-05-11 — Phase 0 inventory: all 4 file:line locations confirmed; no in-flight collision.
- 2026-05-11 — Phase 1 diagnosis: all 4 = FIX (SHA1 disposition confirmed: idempotency token, not persisted, SHA256 is drop-in).
- 2026-05-11 — Phase 2 applied: 4 file edits + 2 requirements.txt updates (adconnect + erp-imobiliario).
- 2026-05-11 — Phase 3 baseline regen: `bandit-baseline.json` rewritten with empty `results: []` (minimal 19-line shape; bandit's --baseline only reads `results`).
- 2026-05-11 — Phase 4 pytest:
  - adconnect: 231 passed, 18 skipped (was 230 — added 1 XXE-rejection regression test).
  - erp-imobiliario: targeted services (test_dimob_service + test_xml_feeds_service) — 47 passed. Pre-existing test-env failures elsewhere (`supabase._sync.client.SupabaseException: supabase_url is required` — unrelated to my changes; verified by stashing edits and reproducing same failure).
  - therapy-platform: targeted service (test_scheduling_service) — 12 passed. Pre-existing test-env failures elsewhere (same SupabaseException pattern; unrelated).
- 2026-05-11 — Bandit gate confirmed green: `bandit -r ... --baseline bandit-baseline.json` reports "No issues identified" at MEDIUM+ severity/confidence.

## Findings (5-category) — returned as text per §17.6.1

### Errors / failures
- None directly attributable to this work. (Pre-existing supabase_url test-env failures exist in erp + therapy full suites; confirmed pre-existing via `git stash` baseline comparison.)

### Mistakes / slips
- **Initial assumption that `defusedxml`'s `EntitiesForbidden` was a subclass of `ET.ParseError`.** It is not — `DefusedXmlException` extends `ValueError`, not `ET.ParseError`. The first XXE-regression test failed loudly and revealed the parser's existing `except ET.ParseError` was too narrow to wrap defusedxml's hostile-XML signals. Fixed by widening to `except (ET.ParseError, DefusedXmlException)`. Lesson: when swapping a library, READ the new exception hierarchy, don't assume drop-in shape extends down to error types.

### Lessons
- **The `--baseline` flag for bandit only reads the `results` array** — the metrics block in the JSON is not consulted. A 19-line minimal baseline (errors/generated_at/metrics/results stubs) is sufficient; the auto-generated 9444-line variant is bandit's natural full-output shape but contributes no signal to the gate. Kept the minimal form for diff-readability.
- **defusedxml's `parseString` is API-identical to `xml.dom.minidom.parseString`** including the `.toprettyxml()` method on the returned DOM — the dimob_service and xml_feeds swaps required ZERO call-site changes besides the import line. This is the "drop-in" pattern when it works.
- **SHA1 → SHA256 swap is safe when the hash is an in-flight idempotency token, not a persisted state key.** The therapy-platform `request_id` is sent to Google Calendar's `events.insert` for per-request dedup and is not stored anywhere in our DB, so length/format change is invisible to downstream systems.

### Interesting findings
- **adconnect's nfe_xml_parser already documented the verify-the-seed-ships-it analysis in its module docstring** — the parser is local to adconnect (N=1) with a follow-up project filed at N=2. Good example of "accept-with-rationale" preserved at the call site instead of buried in catalog.
- **The two erp-imobiliario XML services had `except Exception` wrappers around their parseString calls** — already broad enough to catch defusedxml's hostile-XML signals (DefusedXmlException ⊂ Exception). No behavioral change needed at call sites for those products.

### Knowledge pieces
- **defusedxml exception hierarchy:** `DefusedXmlException(ValueError)` is the base; `EntitiesForbidden` / `DTDForbidden` / `ExternalReferenceForbidden` / `NotSupportedError` are siblings. None are subclasses of `xml.etree.ElementTree.ParseError`. To wrap hostile-XML signals into a parser's existing surface error, catch `(ET.ParseError, DefusedXmlException)`.
- **bandit's `--baseline` shape:** only the `results: [...]` array is consulted for the diff. Other top-level keys (`errors`, `generated_at`, `metrics`) can be stubs.
- **Bandit B324 has a `usedforsecurity=False` carve-out** — `hashlib.sha1(..., usedforsecurity=False)` is also accepted by the linter. Used SHA256 instead because it's the cleaner forward-compatible signal (no annotation tax).
