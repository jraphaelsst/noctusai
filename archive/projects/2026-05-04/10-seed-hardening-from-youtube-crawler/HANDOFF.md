# HANDOFF.md — seed-hardening-from-youtube-crawler

> **Purpose.** Architect (Claude Opus 4.7) is pausing on user instruction. Phase 0 + Phase 1 + Phase 2 are CLOSED on the integration branch. Phase 3 engineers have COMPLETED their work and PUSHED their branches, but the architect-side Phase 3 work (merge + close + project-close) is NOT YET DONE. This doc is the next agent's runbook.

- **Created:** 2026-05-04 by architect.
- **Integration branch:** `seed-hardening-from-youtube-crawler` (16 commits ahead of origin/main).
- **Tip commit:** `223d6ba` (`phase(...): Phase 2 ✅ — Batch B close`).
- **PROJECT.md status:** "Phase 0 ✅ → Phase 1 ✅ → Phase 2 ✅ → Phase 3 ready" (Phase 3 has all 4 sub-tasks `[ ]`; engineer-side branches contain ticked versions awaiting merge).

---

## 1. State at handoff

### Branches that exist (all pushed to origin)

| Branch | Tip SHA | Tests reported by engineer | Notes |
|---|---|---|---|
| `seed-hardening-from-youtube-crawler` (integration) | `223d6ba` | 850/850 seed-lib + 33/33 framework | Phase 0+1+2 closed; Phase 3 NOT merged. |
| `sh-yt-fakemode` (Phase 3.1, Engineer G) | `f470cde` | 15/15 vitest | New `seed/lib/frontend/` test infra; vitest config + setup created. |
| `sh-yt-storage` (Phase 3.2, Engineer H) | `e5e059a` | 52/52 storage; 902/902 full seed-lib in their worktree | Protocol+Fake+Local+Supabase+factory. |
| `sh-yt-quota` (Phase 3.3, Engineer I) | `d1e5a3f` | 30/30 quota; 880/880 full seed-lib in their worktree | Sliding-window; Redis WATCH/MULTI; fakeredis-compatible. |
| `sh-yt-scaffold-polish` (Phase 3.4, Engineer J) | `45051e9` | 16/16 scaffold + 7/7 validate_product | 4 fixes bundled (slug placeholder + .env.example whitelist + range reservation + validate enforcement). |

### Worktrees still attached

```
noctusai-worktrees/sh-yt-encrypted-tokens     (Phase 1.2 — already merged)
noctusai-worktrees/sh-yt-youtube              (Phase 1.3 — already merged)
noctusai-worktrees/sh-yt-migration-scaffolder (Phase 1.4 — already merged)
noctusai-worktrees/sh-yt-jobs                 (Phase 2.1+2.2 — already merged)
noctusai-worktrees/sh-yt-oauth                (Phase 2.3 — already merged)
noctusai-worktrees/sh-yt-health               (Phase 2.4 — already merged)
noctusai-worktrees/sh-yt-fakemode             (Phase 3.1 — AWAITING MERGE)
noctusai-worktrees/sh-yt-storage              (Phase 3.2 — AWAITING MERGE)
noctusai-worktrees/sh-yt-quota                (Phase 3.3 — AWAITING MERGE)
noctusai-worktrees/sh-yt-scaffold-polish      (Phase 3.4 — AWAITING MERGE)
```

The Phase 1 + 2 worktrees can be removed (`git worktree remove ...`) at project close OR left alone (they're harmless). The Phase 3 worktrees should stay until merging is verified, in case you need to re-run anything inside them.

### Test counts trajectory

| Phase | seed-lib backend | framework backend | mcp scaffold |
|---|---|---|---|
| Phase 0 → 1.1 (SMTP only) | 703/703 | n/a | n/a |
| Phase 1 close | **738/738** | n/a | **26/26** |
| Phase 2 close | **850/850** (+112: 73 jobs + 39 oauth) | **33/33** (+15 health) | 26/26 |
| Phase 3 expected at integration tip after merge | ~932 (+82: 52 storage + 30 quota; FakeMode is frontend only) | 33/33 | ~42 (+16: 9 scaffold + 7 validate_product) |

The 932 figure is approximate (engineer worktree counts overlap because each worktree only had its own additions on top of the Phase 2 baseline; merging combines them). After all four merges, run pytest at the integration tip to confirm the actual integrated count.

---

## 2. Next steps — runbook (ordered)

### Step 1 — Merge the 4 Phase 3 branches (sequential, with conflict resolution)

Each merge will conflict on `projects/seed-hardening-from-youtube-crawler/PROJECT.md` (each engineer ticked their own sub-task and added a §11 row) and `projects/seed-hardening-from-youtube-crawler/findings.md` (each engineer appended entries). Pattern is exactly the same as Phase 1 + 2 merges — see commits `64ebc1c`, `fe6988f`, `e757c21`, `98d1864` for reference resolutions.

**Resolution recipe for PROJECT.md §6 Phase 3 list:** the integration HEAD has all 4 sub-tasks `[ ]`; each branch's HEAD has ITS sub-task `[x]` and the others still `[ ]`. After all 4 merges, all 4 should be `[x]`. Resolve each conflict by accepting that engineer's `[x]` line and keeping the integration HEAD's `[ ]` lines for the unmerged ones (until the next merge updates them).

**Resolution recipe for §11 Change log:** union — keep all engineers' rows in chronological order (most recent at top per existing convention).

**Resolution recipe for findings.md:** union all entries; place them in their semantic sections (Errors / Lessons / Interesting findings / Knowledge pieces / Surprises) by category. Don't dump engineers' new sections at the bottom — refactor into the existing sections like the Phase 1+2 merge resolutions did (see commit `64ebc1c`'s findings.md for the pattern).

```bash
cd /Users/rapha/Documents/repository/NoctusAI/noctusai
git fetch . sh-yt-fakemode sh-yt-storage sh-yt-quota sh-yt-scaffold-polish

# 1.1 — FakeMode (frontend; smallest blast radius — start here)
git merge --no-ff sh-yt-fakemode -m "merge(seed-hardening-from-youtube-crawler): Phase 3.1 — frontend FakeModeBadge + useEnvMode"
# resolve PROJECT.md + findings.md conflicts → git add → git commit --no-edit

# 1.2 — Storage
git merge --no-ff sh-yt-storage -m "merge(seed-hardening-from-youtube-crawler): Phase 3.2 — integrations/storage"

# 1.3 — Quota
git merge --no-ff sh-yt-quota -m "merge(seed-hardening-from-youtube-crawler): Phase 3.3 — integrations/quota"

# 1.4 — Scaffold polish (LARGER conflict surface — Engineer J modified scaffold.py
#        which Engineer C also modified in Phase 1.4. Read both diffs carefully
#        before resolving.)
git merge --no-ff sh-yt-scaffold-polish -m "merge(seed-hardening-from-youtube-crawler): Phase 3.4 — scaffold polish (slug + .env.example + range-reserve + validate)"
```

### Step 2 — Run integrated pytest at the integration tip

```bash
cd /Users/rapha/Documents/repository/NoctusAI/noctusai
/Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/pytest seed/lib/backend/tests/ -q
/Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/pytest seed/framework/backend/tests/ -q
/Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/pytest mcp/noctusai/tests/test_scaffold.py mcp/noctusai/tests/test_scaffold_migration.py mcp/noctusai/tests/test_validate_product.py -q
cd seed/lib/frontend && npm run test
```

If anything is red:
- Engineer J's `scaffold.py` Fix 2 changes the file-extension behavior from positive whitelist to "text-by-default + binary-suffix skip". This may interact with Engineer C's `scaffold_migration.py` if both touched the same module. Read the conflict carefully.
- Engineer J added `template_dir=` injection seam to `scaffold_product` for hermetic tests. Verify this doesn't break the existing scaffold tests (their counts went 7→16; the +9 are the new ones).

### Step 3 — Triage Phase 3 findings (5+ items)

Read `findings.md` after the merges to get the full list. Known items from engineer reports:

1. **Engineer G — `seed/lib/frontend/` had no test infra** — Engineer G added vitest config + setup + scripts. Worth pinning in `KB § PATTERNS/frontend.md` as the seed's canonical frontend test setup. Three-way-sync candidate.
2. **Engineer G — `seed/framework/frontend/vitest.config.ts` `@noctusai/lib` alias bug** — points at non-existent `seed/framework/lib/src/index.ts` (should be `seed/lib/frontend/src/index.ts`). Pre-existing; one-line fix in a separate PR. **Do this fix as a Phase 3 close drive-by** (same pattern as the seed-shadow-purge-helper-lift drive-by I did at Phase 0).
3. **Engineer I — `fakeredis` 2.x doesn't ship Lua** — Engineer I pivoted to WATCH/MULTI; documented as "the test fake is part of the seed contract; if production primitive doesn't run on the fake, it's half-shipped." **Worth promoting to memory + KB pattern** as a methodology rule.
4. **Engineer J — vite factory PRODUCT_MAP comments use abbreviated forms** (`// ERP` instead of `// erp-imobiliario`) — `erp-imobiliario` slug literally not in PRODUCT_MAP. The new `validate_product` check correctly fails on this. **Real gap; one-line factory edit** in a follow-up batch (or a Phase 3 drive-by).
5. **Engineer J — `scaffold_product` reads noc's template via `get_noctusai_home()`** — worktree-side template edits invisible to in-worktree tests. Added `template_dir=` injection seam. Worth noting as a methodology lesson.

**Plus the deferred-from-Phase-2 items still pending at project close:**
- `MockSupabaseClient` testing pattern → `KB § PATTERNS/testing.md` (Engineer D's Phase 2 finding).
- OAuth router refresh-encryption seam doc (Engineer E's Phase 2 finding).
- Worktree-venv editable-install gap → file as future project candidate (Engineer F's Phase 2 finding).
- `integrations/google_calendar/oauth_adapter.py` → consume `security/oauth/GoogleProvider` (Engineer E's Phase 2 finding).

### Step 4 — Phase 3 close commit

After merges + integrated pytest green + triage applied:

1. Edit `projects/seed-hardening-from-youtube-crawler/PROJECT.md`:
   - Flip top-of-doc `Status:` line to `Phase 0 ✅ → Phase 1 ✅ → Phase 2 ✅ → Phase 3 ✅ → ready to close`.
   - Add `### Phase 3 — Batch C (polish + propagation) ✅` header (current is unmarked) and an `**Improvements:**` block summarizing the 5 Phase 3 findings + their triage outcomes (the literal `**Improvements:**` label is REQUIRED — the pre-commit hook checks for it before allowing ✅).
   - Add §11 row for Phase 3 close.
2. Stage + commit: `phase(seed-hardening-from-youtube-crawler): Phase 3 ✅ — Batch C close + cross-cutting fixes`.

### Step 5 — Project close: archive + push to main

Per `feedback_archive_system.md` + `feedback_no_auto_commit.md` (gate carve-out (b)):

1. Final pytest sanity run (all 3 layers + frontend build).
2. **Three-way sync (KB / CLAUDE.md / memory) for any new methodology rule** surfaced during the project. Candidates from findings:
   - "The test fake is part of the seed contract" (Engineer I).
   - The pre-commit hook venv-discovery worktree-aware fix (Phase 1 close, already shipped — verify memory entry exists or add one).
   - The `MockSupabaseClient` pattern (Engineer D).
3. Archive the project folder via `mcp__noctusai__noctus_dev_archive` — this `git mv`s `projects/seed-hardening-from-youtube-crawler/` to `archive/projects/2026-05-04/<NN>-seed-hardening-from-youtube-crawler/`. The MCP tool auto-numbers `<NN>`.
4. Final commit: `chore(projects): close seed-hardening-from-youtube-crawler — archived to archive/projects/2026-05-04/<NN>-seed-hardening-from-youtube-crawler/ [seed-hardening-from-youtube-crawler close]`.
5. **`git push origin seed-hardening-from-youtube-crawler:main`** — fast-forward to main per branching methodology (the orchestrator pushes; per `feedback_orchestrator_role.md` the architect/orchestrator does the final push). If non-FF, see `KB § PATTERNS/branching-and-merging.md § 10` for non-FF integration recipe.
6. Verify on remote: `git log origin/main --oneline -20` should show the 16+ commits at the tip.
7. Clean up worktrees if desired: `git worktree remove noctusai-worktrees/sh-yt-*` (10 to remove). Branches can be deleted after merge with `git branch -d sh-yt-*` and `git push origin --delete sh-yt-*`.

### Step 6 — Update youtube-crawler product workspace

The whole point of this project was to lift the surfaces YT crawler will consume. After project close, draft `~/Documents/repository/NoctusAI/noctusai-youtube-crawler/products/youtube-crawler/projects/youtube-crawler-build/PROJECT.md` whose Phase 1 reads "consume Batch A surfaces" (encrypted_tokens, youtube integration, SMTP, scaffold_migration) — Batch A blockers from the original critique. Phase 2/3 of YT crawler can lean on Batch B/C surfaces too.

This is a NEW project (different scope), not part of seed-hardening's close. File when YT-crawler work begins.

---

## 3. Findings deferred for project close (full list)

To be addressed during Step 3 above + the three-way sync in Step 5:

### Apply inline (small + clear destination):
- **Vite alias fix** (Engineer G #2): `seed/framework/frontend/vitest.config.ts` — change `@noctusai/lib` alias from `seed/framework/lib/src/index.ts` to `seed/lib/frontend/src/index.ts`. One-line drive-by.
- **Vite factory PRODUCT_MAP** (Engineer J #4): `seed/lib/frontend/vite.config.factory.ts` — replace abbreviated comments (`// ERP`) with full slugs (`// erp-imobiliario`, etc.) so `validate_product`'s new check passes for existing products. Multi-line drive-by.
- **`MockSupabaseClient` pattern doc** (Engineer D Phase 2): `KB § PATTERNS/testing.md` — add a section showing `inserted_payloads` / `updated_payloads` / `set_rpc_data` as the canonical zero-monkey-patch shape for Real-Supabase tests.

### Three-way sync (memory + KB + CLAUDE.md):
- **"Test fake is part of the seed contract"** (Engineer I) — `feedback_seed_fake_real_pattern.md` should mention that production primitives MUST run against the fake (so the fake is exercised by every test that exercises the real). Engineer I's `fakeredis-no-Lua` story is the cautionary tale.
- **`asyncio.Event.wait()` with timeout > `time.sleep()` for any worker that wants both responsiveness AND idle amortization** (Engineer D) — worth pinning to `KB § PATTERNS/backend.md` or a new entry.

### File as future projects (sorted by priority):
1. **`worktree-bootstrap-venv-editable-installs`** — when a worktree modifies seed packages, the venv's editable install points at the MAIN repo (not the worktree). Engineer F + several others hit this. Needs design (shared venv vs per-worktree).
2. **`google-calendar-oauth-consume-generic-provider`** — migrate `integrations/google_calendar/oauth_adapter.py` to consume `security/oauth/GoogleProvider`. Engineer E's Phase 2 follow-up.
3. **`mcp-tests-worktree-aware-path-resolution`** — 8 pre-existing MCP tests use hardcoded `Path.relative_to(REPO_ROOT)` that breaks in worktrees. Engineer C surfaced (Phase 1.4).
4. **`email-module-canonical-protocol-fake-real-refactor`** — refactor `integrations/email/digest.py` from flat-function shape to canonical Protocol+Fake+Real+factory (now that SMTP is a second consumer per user's "absorbed in the future" framing).
5. **`youtube-integration-tests-relocate-to-tests-integrations`** — cosmetic relocate (Engineer B, accepted-with-rationale at Phase 1 close). Trivial when next integration is added.

---

## 4. Notes on what was already done (for context)

### Three-way sync items already shipped:
- `MEMORY.md` index entry for `feedback_no_auto_commit.md` flipped from "default never; carve-outs" → "DO commit at gates" framing. The body file was already correct.
- `KB § PATTERNS/accept-with-rationale.md` got 2 entries (TestSqlTemplatesIntegration N=2 + youtube test path).

### Cross-cutting fixes already shipped (Phase 1 close):
- `scripts/pre-commit` blocks 2 + 5 — venv-discovery falls back to main repo's venv via `git rev-parse --git-common-dir` when running inside a worktree.
- `seed/lib/backend/pyproject.toml` — `cryptography>=42.0` promoted from transitive to explicit dep.

### What's NOT done that would otherwise be expected:
- No `improvements.md` regeneration via `python mcp/noctusai/cli.py --improvements ...` — do this in Step 5 if the project workflow expects it (read `KB § PATTERNS/proposals-and-improvements.md` to confirm).
- No bundled phase proposals filed in `projects/.../proposals/` — the per-phase proposal artifact (`KB § PATTERNS/proposals-and-improvements.md`) was implicitly merged into the §6 `**Improvements:**` blocks rather than separate `.md` files. Decide at close whether to file separate proposal docs or accept the inline-improvement shape.

---

## 5. Engineer dispatch log (for reference)

All engineers were given:
- Self-contained briefs (zero-context).
- Worktree path + branch name (already created off integration tip).
- Reference patterns (e.g. `google_calendar` for Protocol+Fake+Real+factory).
- Write-authorization for `findings.md` + `PROJECT.md` (to override the "NEVER create *.md" default).
- Verification commands (pytest, build).
- Git instructions (stage own files only, commit message format, push branch, DO NOT merge).

Engineer subagent IDs (in case continuation is needed):
- Engineer A (1.2): `aa0f3dcef46f35324`
- Engineer B (1.3): `ae384721d6d783ca7`
- Engineer C (1.4): `a2e5609c2a669fb9a`
- Engineer D (2.1+2.2): `a16497d9786322ec3`
- Engineer E (2.3): `a97b5d28783a0d1e6`
- Engineer F (2.4): `a9f56533ddbd933df`
- Engineer G (3.1): `afa552e6f15250fe4`
- Engineer H (3.2): `ac0c1f652905c8b80`
- Engineer I (3.3): `ad8948643c5cb8dde`
- Engineer J (3.4): `a673994bc3307796b`

(SendMessage to these IDs revives the engineer with their full prior context if you need to ask follow-up questions about implementation details.)

---

## 6. Security note re: Engineer H's push

The system flagged a security warning when Engineer H pushed `sh-yt-storage`. The push WAS authorized — the brief explicitly said `git push -u origin sh-yt-storage`, and the user's "roll end-to-end" framing covered all engineer-side branch pushes (consistent with all 9 other engineers' pushes). The warning misfired because the security layer didn't see the architect's brief as authorization. Acknowledge if asked; not a real policy violation.

---

## 7. Quick-reference: where everything lives

| What | Where |
|---|---|
| Integration branch tip | `223d6ba` on `seed-hardening-from-youtube-crawler` |
| Project doc | `projects/seed-hardening-from-youtube-crawler/PROJECT.md` |
| Findings | `projects/seed-hardening-from-youtube-crawler/findings.md` |
| This handoff | `projects/seed-hardening-from-youtube-crawler/HANDOFF.md` |
| New seed surfaces | `seed/lib/backend/noctusai_lib/{security/encrypted_tokens,security/oauth,integrations/youtube,integrations/storage,integrations/quota,domain/jobs}` |
| Modified `create_product_app` | `seed/framework/backend/noctusai_seed/app.py` |
| New MCP tools | `mcp/noctusai/tools/noctus/dev/{scaffold_migration,validate_product (extended)}` |
| Modified scaffold tool | `mcp/noctusai/tools/noctus/dev/scaffold.py` (Phase 3.4 — slug + .env.example + range-reserve) |
| Frontend additions | `seed/lib/frontend/src/{components/FakeModeBadge,hooks/useEnvMode}` |
| New explicit dep | `seed/lib/backend/pyproject.toml` line for `cryptography>=42.0` |
| Worktree-aware pre-commit | `scripts/pre-commit` blocks 2 + 5 |
| Accept-with-rationale catalog | `KNOWLEDGE-BASE/CONTEXT/PATTERNS/accept-with-rationale.md` |

---

End of handoff. Good luck. The hard work (Phase 0 + 1 + 2 close + Phase 3 engineer dispatch) is done; the remaining work is mostly merge resolution + close ceremony + the three-way sync. Estimated effort: 1–2 hours of focused architect time.
