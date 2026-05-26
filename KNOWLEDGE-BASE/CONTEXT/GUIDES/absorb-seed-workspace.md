# Absorbing a separately-developed seed-workspace into noc

> The repeatable end-to-end procedure for taking a **sibling seed-workspace** (a
> functions-development environment built outside noc, against real external APIs)
> and absorbing it into noc as **one new product** + reconciled seed. Written from
> the *proven* `social-wiring` absorption (2026-05-16): a YouTube/WhatsApp/Meta/
> Google media-wiring workspace absorbed as the `social-wiring` CMS product, with
> 4 in-home products consolidated into it and retired.
>
> This guide is **self-contained** — every durable fact is inlined. It references
> code paths and dated architectural facts, never a `projects/` or `archive/`
> folder (those are transient; see the durable-docs-self-contained rule).

---

## When this guide applies

A sibling workspace was used as an isolated **funcs-dev environment** — a place
to build + live-validate integrations against real OpenAI/Google/Meta/WAHA/Vista
APIs, away from noc. It now holds a production-validated stack you want *in* noc.
Trigger phrasings: *"absorb the X workspace"*, *"bring the sibling repo in"*,
*"this repo is done, fold it into noc as a product"*.

It does **NOT** apply to: scaffolding a fresh product (→ `KB § GUIDES/new-product.md`),
or a noc-internal product reshape. The distinguishing trait is **external origin
+ live-validated code that noc's seed may not yet match**.

---

## The 10 gates (in order — each gates the next)

### Gate 0 · Snapshot-preserve (transient safety, NOT a durable anchor)

Commit a whole-tree snapshot of the originating workspace **before touching
anything** — pure rollback insurance during the process.

- **`--no-verify` is a sanctioned safety-net here.** A workspace's own
  governance pre-commit hook (refuses non-promotion edits) is a *false positive*
  for a preservation snapshot. Surface the `--no-verify` use explicitly (no
  silent bypass); it is legitimate for an authorized snapshot of a local-only
  repo.
- The snapshot is **transient** — no durable doc (this guide, KB, CLAUDE.md,
  memory, PROJECT.md) may reference the originating workspace path. It is the
  user's to delete manually after sign-off (Gate 9).

### Gate 1 · Bring source in-home BEFORE any plan depends on it

This is the **hardest-won lesson**. Copy *all* needed artifacts into noc:
promotion manifests, workspace docs, **and the validated product source tree**.

- A true *reconcile* needs the validated SOURCE, not just manifests/notes — a
  plan that depends on reading the sibling later will strand an engineer.
- **Worktree-base vs uncommitted-inputs trap:** agent worktrees branch from
  `origin/main`; they are **blind** to branch-only commits AND untracked root
  files. If authoritative inputs live only on the absorption branch or as
  untracked notes, every `isolation:worktree` engineer is blind to them. Pre-
  dispatch the inputs MUST be **committed-to-base**, OR run **master-tree-
  parallel** (engineers in the shared branch tree, ZERO engineer git ops, file-
  disjoint by package), OR inlined into the brief. (This is the platform-wide
  worktree-base rule — `KB § PATTERNS/architect/branching-and-merging.md` §16.7; absorption
  only consumes it.)
- Bring host-correct **path conventions**: sibling-validated *code* wins
  conflicts, but *paths* follow the host (sibling `integrations/google/x/` →
  noc flat `google_*`).

### Gate 2 · Completeness audit → UNMAPPED-useful list

Produce a sign-off-grade audit: every useful artifact is either mapped by a
promotion manifest/note AND copied in-home, or explicitly surfaced as UNMAPPED-
useful with a named destination. This audit is what lets the user later delete
the workspace with confidence (Gate 9).

- **Prefer "the set" over a count.** Hand-maintained count indices drift (the
  social-wiring workspace's own `PROMOTIONS.md` was stale at 7-of-14). Derive
  any index from the manifest dir; never hand-maintain a parallel count. Going
  forward, seed-workspace scaffolding auto-emits the absorption map
  (`noctus.dev.gen_promotions_index` + the seed-workspace pre-commit drift gate).

### Gate 3 · Interrogate disposition BEFORE any deletion

The user's stated mental model may be wrong. social-wiring: the user called 4
products "stale loose ends"; recon proved 2 were unique production products.
Phase-0 *expand-loudly-on-invalidation* + AskUserQuestion converted a would-be
irreversible mistake into a clean per-product decision (delete-truly-stale vs
absorb-then-retire). **Keep interrogation before any deletion, always.**

### Gate 4 · Scaffold the new product (house single-container model)

Scaffold via `noctus.dev.scaffold_product` — the new product inherits noc's
single-container house model + seed factory by construction. The *product* keeps
its platform + frontend and is re-skinned to its CMS/domain scope; the cross-
product capabilities do NOT stay product-local — they go to seed (Gate 5).

### Gate 5 · Full seed-reconcile (sibling-validated wins)

The default *"seed is canonical"* is **inverted** for an absorption: the sibling
ran live; noc seed may not have. Where they diverge, **noc seed is rewritten to
match the validated sibling** — even for already-seeded adapters.

- Every IO module lands in canonical **Protocol+Fake+Real+factory** shape
  (`KB § PATTERNS/backend/seed-fake-real-adapter.md`). No half-ship.
- **verify-the-seed-ships-it has 4 shapes** — a same-name factory is NOT
  enough. Assert ALL of: (1) backend `__all__` membership (a symbol shipped
  with zero `__all__` + zero tests is a "reconciled-but-invisible" half-ship —
  the `lid_auth` case); (2) frontend `index.ts` re-export membership (the WA-
  hooks case); (3) **factory-signature-compat** — the factory signature the
  *named consumer* needs ships, not merely a same-name factory (a same-name/
  different-contract reconcile is a silent under-ship); (4) **consumer-method-
  set + write-path compat** — the adapter has the methods the named consumer
  calls (Wave-1 reconcile dropped Meta `me()`/`get_page()`) and the consumer's
  write path has a seam (OAuth credential-WRITE). The two new keepers
  `check_seed_export_membership` + `check_hardcoded_product_slug_set` codify
  parts of this; the signature/method-set shapes stay Stage-3 judgment until
  the predicate is deterministic.
- **Master-tree-parallel, file-disjoint, ZERO engineer git ops.** Engineers
  own strictly-disjoint package paths in the shared absorption branch tree;
  the architect stages + commits per package + holds shared deltas for an
  integration commit. **`git stash` is forbidden under a zero-git brief** —
  including for counterfactual/baseline isolation. Use Edit-revert → Edit-
  restore, or a scratch copy. The brief's "ZERO git ops" includes `stash`.
- **Integrations are independent seed modules; combos compose at the product/
  tool layer.** `whatsapp`, `vista`, `meta`, `google_*`, `media`, `youtube`
  each ship standalone. whatsapp+vista / meta+vista workflows orchestrate the
  independent modules at the chatbot-tool/product layer — they are NEVER fused
  in seed. Dispatch grouping (one engineer builds two modules) is an
  orchestration convenience only; the delivered modules stay separate.

### Gate 6 · Port the product + pilot-first consumer adaptation

Port the sibling product functionality into the new product consuming the
reconciled seed. Absorb any consolidated in-home product *domains* into it as
modules behind a `MODULES` registration seam.

- **Pilot-products-first cadence** (`KB § PATTERNS/architect/project-execution.md § 2.12`):
  seed ripples prove on the 3 canonical pilots (`erp-imobiliario` ·
  `therapy-platform` · the new product) + `core` (control-plane), NOT the full
  fleet per change. Non-pilots extend in a gated follow-up wave only after the
  pilots are green. Reconcile changes that are **additive-only exports** ripple
  with zero breakage — pilots are the high-signal canaries that prove this.
- **Pause-on-dependency for contract gaps.** When an engineer finds the
  reconciled seed is contract-incompatible with a validated consumer (resolver-
  Protocol vs credential_store; missing methods; no write seam), the engineer
  **blocks with zero edits and surfaces** — a delete-and-rewrite would destroy
  validated behavior + the regression-test oracle. The architect's methodology-
  consistent response: keep the validated subpackage **product-local at N=1**
  (catalogued in `KB § PATTERNS/common/accept-with-rationale.md` with a named seed-
  convergence destination), build thin product-side bridge adapters if cheap,
  and file the seed-convergence as a gated follow-up. A same-name/different-
  contract factory is a silent under-ship — never force the rewrite.

### Gate 7 · Adapt remaining consumers (mechanical, oracle = tests/builds)

After pilots are green, extend the now-de-risked adaptation shape to non-pilot
survivors. Mechanical, seed-shaped. Oracle = pytest + `vite build`, never grep
(segmented `Path / "a" / "b"` / template literals evade grep — structural-
refactor blindspot). When a count/import assertion fails, `git log -S<dropped-
token>` BEFORE attributing to the most-recent change — misattribution to the
newest commit is the recurring trap (social-wiring mis-attributed a CORS
failure twice before git-`-S` settled it on a pre-branch commit).

### Gate 8 · Teardown (irreversible — only after green)

Delete the consolidated products only after the new product + reconciled
consumers are green. Teardown discipline:

- **Preservation-FIRST sub-gate.** Before any delete: snapshot the doomed
  trees to a holding dir + append the durable ledger
  (`project-history/ledger.ndjson`). Resolve any open LGPD entry (verify the
  vuln did/didn't carry forward to the new product — social-wiring's Fernet
  `CredentialStore` meant the imobi LGPD entry could be *resolved*, not just
  re-homed).
- **Hazard-group commits.** Group co-dependent edits into one commit each:
  sentinel-slug ↔ dir-delete · migration-file ↔ live-DB-mirror · KB-rehome ↔
  CLAUDE-pointer-twin (verify-kb-sync gate). A split hazard group leaves the
  tree transiently invalid.
- **Registry-DERIVE, never re-freeze a literal.** Replace deleted-product
  references with `parse_products_registry()`-derived values (CORS, ports,
  slug sets), not a new frozen literal — a frozen literal just re-stales.
  Codified by `check_hardcoded_product_slug_set` +
  `check_hardcoded_fleet_size_literal`.
- **Verify dangling-refs by content-FORM, not slug-count.** A residual
  doomed-slug mention in the correct dated-retirement form ("Retired
  2026-05-16 → <new-product>") is sanctioned, not dangling. The accept-with-
  rationale catalog hits are the sanctioned durable register, correctly
  preserved.
- **The KB-count auto-stage hook footgun:** `update-kb-counts` (pre-commit)
  silently folds a later hazard-group's KB-doc edits into an earlier commit,
  making `git status` look clean and triggering a false "incomplete-scrub"
  alarm. Resolve by **verifying, not assuming**: `git show <earlier-commit>
  --stat` BEFORE concluding a later group "didn't happen", and grep the
  *content form* not the slug count.
- **Teardown grep scope — provenance + generated artifacts (N≥24, social-wiring 2026-05-16):** the reference-scrub must NOT be limited to functional/import/registration/compose/port refs. It MUST `grep -rnE 'products/<doomed-slug>/'` over **ALL surviving `products/ seed/ mcp/ scripts/ KNOWLEDGE-BASE/`** — provenance comments/docstrings/prose path-pointers ("Mirror of `products/<deleted>/…`") are a `durable-docs-self-contained` violation invisible to the 8-cmd content-form check. Redate them (`the retired <product>, consolidated into <new> <date>`), NOT delete. AND **regenerate every generated artifact whose generator scans the product tree** (`build-init-local-db.sh`, `cli.py --catalog`, outline-corpus baseline) — a generated file can't be hand-redated; re-derive from already-scrubbed source. Sanctioned exclusions: `reference/`, `.integration-holding/`, `archive/`, `ledger.ndjson`, `accept-with-rationale.md`, `.backup/` (gitignored), already-dated-retired lines. Codification candidate: `check_dangling_deleted_product_path` (s4 — `products/<slug>/` literal where slug ∉ live registry ∧ line not dated-retired ∧ not under sanctioned-exclusion).
- **Derived-test + compliance surfaces are part of the scrub (N=14 mcp failures, social-wiring 2026-05-17):** the `grep 'products/<slug>/'` path-scan does NOT catch a test that hardcodes the doomed slug as a *bare string probe* (`get_product_summary("mailing")`, `assert "mailing" in slugs`, `find_orphaned_files("mailing")`). The `mcp/noctusai` product-introspection suite (`test_products` / `test_analyzers` / `test_diff` / `test_compliance`) is a **derived surface that encodes the OLD fleet shape** and silently rots on teardown — discovered only because a later session ran the full mcp suite and *baseline-verified* the failures pre-existing (codebase-is-source-of-truth) instead of assuming them regressions. Teardown MUST additionally: (a) `grep -rn '"<doomed-slug>"' mcp/noctusai/tests/` and repoint every probe to a **registry-derived fixture** (`tests/conftest.py::domain_product`, resolved from `list_products()`), never a new slug literal; (b) capture a **compliance + dep-pin baseline delta** — run `check_all_products()` and `audit_python_deps()` BEFORE teardown and again after, so the absorbed product's pre-existing violations are an explicit, owned delta rather than an ambient "score dropped" mystery later. Whatever you don't fix in-flight is *filed*, never surface-only (`fix-on-contact`).

### Gate 9 · Container refactor → user-gated workspace retirement

Refactor docker/compose/start.sh for the new consolidated topology (deleted
products gone, new product in, house single-container model). Resume the fleet
build. Then deliver a completeness sign-off vs the Gate-2 audit. **The user
retires the originating workspace manually — we never delete it.** Our
deliverable is the explicit "safe to delete" sign-off, not the deletion.

**Container-first (KB § PATTERNS/devops/containerization.md § 1a).** Containerizing the
absorbed product to the house single-container model is **not a final polish — it
is the gate** that lets development continue *inside* the container (the
`runtime-watch` develop-inside loop), not on the host. Render the thin
`backend/Dockerfile` + `docker-compose.yml` from the seed via `noctus.dev.propagate`
(`FROM noctus-seed-*-base`, `runtime-watch` target, `SERVE_SPA_DIR` when the
product ships a `frontend/`). The **green gate is the `check_product_container_shape`
keeper** — it flags a freshly-absorbed-but-uncontainerized product, so this Gate is
not "done" until that keeper is clean for the new slug.

---

## An absorption is a methodology-epoch merge, not just a code move

**The framing (social-wiring 2026-05-17 retrospective).** A separately-developed
product grew under the methodology *as it was when development started*. The noc
fleet kept advancing — new keeper detectors, registry-derived test probes, the
RLS `service_role_bypass` contract, strict dep-pin reconciliation, the
single-container house model, `StrictHttpModel`, chatbot-operational-readiness.
**Absorbing the product imports it from an earlier methodology epoch and exposes
the entire delta at once.** The 14 mcp failures + the 637-issue compliance
baseline social-wiring surfaced were not *created* by the absorption — they are
the **measurable size of how far the platform's methodology advanced while this
product grew elsewhere**. Expect this signal on every absorption; its magnitude
is proportional to (epoch gap) × (product surface).

**What this changes in the procedure:**

- **Budget for the epoch delta.** The absorb estimate must include a
  derived-surface + compliance-baseline reconciliation pass, not just functional
  port + consumer-adapt. The delta is *normal*, not a surprise — size it up front
  by running `check_all_products()` / `audit_python_deps()` / the mcp suite
  against the *pre-absorption* tree so the gap is a known number, not a
  post-merge mystery.
- **Triage the delta explicitly** (`triage-at-decision-time`): bounded +
  in-this-product → fix in-flight (`fix-on-contact`); platform-wide pre-existing
  (the 332 test-patch-target / ~280 silent-except class) → one *filed* remediation
  project, never surface-only; gate-contract questions (an aspirational
  `score==100` that the codification pipeline keeps re-reddening by design) →
  surface to the user with a recommendation + named destination.
- **The newly-scaffolded path is debt-free by construction** — only *absorptions*
  carry an epoch delta (a scaffolded product inherits today's methodology
  whole). This is why the divergent-arch and house-container rules fire on
  absorption only; the epoch-merge framing is their generalization.

## Methodology codified by this flow (three-way-synced)

- **Promotion-map automation** — every separately-developed seed-workspace
  auto-emits + drift-gates an absorption map (`noctus.dev.gen_promotions_index`,
  seed-workspace pre-commit Rule 3). The map DERIVES from the manifest dir;
  never hand-maintain a parallel count.
- **Divergent-arch → house-container rule** — an incoming product whose
  architecture differs from noc's single-container house model MUST be
  refactored to it on absorption (`KB § PATTERNS/devops/containerization.md § 12a`).
- **Pilot-products-first cadence** — `KB § PATTERNS/architect/project-execution.md § 2.12`.
- **verify-the-seed-ships-it 4 shapes** — `KB § PATTERNS/backend/seed-fake-real-adapter.md`.

---

## Anti-patterns (each cost real time on social-wiring)

- Planning a reconcile that depends on reading the sibling *later* (strands
  engineers — Gate 1).
- `isolation:worktree` when authoritative inputs are branch-only/untracked
  (every engineer blind — Gate 1).
- `git stash` for counterfactual isolation under a zero-git brief (Gate 5).
- Deleting before green / treating the snapshot or a `projects/` folder as a
  durable anchor (Gate 8 + durable-docs rule).
- Replacing a deleted-product literal with a *new* frozen literal (re-stales —
  Gate 8).
- Attributing a failed count/import assertion to the newest commit without
  `git log -S` (Gate 7 — mis-attributed twice on social-wiring).
- Forcing a delete-and-rewrite when the seed is contract-incompatible with a
  validated consumer (destroys the oracle — Gate 6 pause-on-dependency).
