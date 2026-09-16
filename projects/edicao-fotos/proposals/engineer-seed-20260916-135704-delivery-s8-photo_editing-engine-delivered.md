## Delivery — Slice S8 (`noctusai_lib.domain.photo_editing`)

Branch `feat/ef-s8-photo-engine` @ `987cf4e8` (base `origin/dev` b6f0a08a). Not pushed; the tech-lead integrates.

### Shipped
- Modules: `types` · `prompts/` (5 versioned, sha-pinned) · `guide` · `naming` · `zipper` · `dataset` · `costs` · `learning` · `access` · `pipeline` · `handlers` · `ports` · `repository` (Protocol + InMemory + Supabase targeting SW 121-126 + Core 046).
- 8 idempotent handlers over one `PhotoEditingPorts` seam; `build_worker` binds retry-once.
- Consumes image_edit / imaging / image_sizing / llm / fx / jobs / permissions / quota. No product import.
- KB `PATTERNS/backend/photo-editing-seed.md` + INDEX row/tree + backend-engineer owns_kb + body pointer.

### Verification (fakes only — no live OpenAI; no credits)
- `tests/domain/photo_editing`: 101 passed, including a Worker-driven upload-to-zip run and real-pixel output-size checks.
- Full seed lib: 4609 passed / 1 skipped (rc 0).
- `--verify-kb-sync` rc 0 · `--check-seed-declared-imports` rc 0 · `--check-seed-test-root-ci-coverage` rc 0 · pre-commit eight-way-sync OK (the first attempt was blocked on a missing agent-body pointer, now fixed).

### codification-events
s1: `analyze_images` returns no usage (`NOC-REMEDIATE[llm-analyze-images-usage]`) · s1: `MockSupabaseClient.schema()` drops table state per call · s2/s3/s4: none.

### drift-found
- `noctus.dev.branch_pointer` writes to the PRIMARY checkout (local `dev`), and its push is dirty-blocked by primary residue (`mcp/noctusai/catalog.md`, `vistaEmail.md`). This is PROJECT.md §C9 wrong-tree #1, recurring.
- Stale `on_going` pointers for branches already on dev: `feat/ef-s3b-image-edit`, `feat/ef-s5-payments`; `feat/igig-foundation` (2026-08-09) claims `seed/lib/backend/noctusai_lib/domain`.
- PROJECT.md has no §4a dispatch-routing section.
- The W1 migrations commit left `02-LANDSCAPE.md` kb-counts stale; the pre-commit regeneration landed in this commit.

### scoped-improvement
- The llm organ's `analyze_images` should return usage (or a result object); until it does, evaluator and rule-proposer calls have no `cost_ledger` row.
- `MockSupabaseClient.schema(name)` should memoize scoped clients. The tests use a composing wrapper instead.
- `branch_pointer` needs a `worktree_path` parameter (the §C9 family).
