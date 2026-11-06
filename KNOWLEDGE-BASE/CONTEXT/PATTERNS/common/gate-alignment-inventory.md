# Gate alignment inventory

> Generated from `gate-alignment-inventory.json` by `python mcp/noctusai/cli.py --gate-alignment render`. Method and rules: `KB § PATTERNS/common/gate-methodology-sync.md`. Firing counts are measured from 943 Claude Code session transcripts (~/.claude/projects, 2026-08..2026-11-05), tool results only, one count per tool call; guard-events.ndjson for live events (upper-bound-free: tool results only, one count per tool call).

Totals by class: **never-fires** 41, **new (shadow)** 2, **real-drift-catch** 35, **unmeasured** 59, **wall** 12 (of 149 gates). Mechanism burn-down: {'gates': 149, 'declared': 29, 'declared_none_justified': 7, 'undeclared_baseline': 121}.

| Gate | Standard | Construction mechanism | Owner | Firings (sessions) | Class |
|---|---|---|---|---:|---|
| `guard:primary-write` |  | tool:task_branch start (isolates off origin/dev) · injection: scripts/hooks/claude-session | tooling-engineer | 134 (43) | wall |
| `keeper:check-migration-guard-has-probe` | Keeper (gate↔methodology-sync backstop for noctus.dev.verify_db_guards, 2026-09-18): a migration that defines  | tool:scaffold_migration (guard_probe_stubs) · organ guard_probes in noctusai_lib/domain/<o | backend-engineer | 85 (22) | wall |
| `guard:heavy-run` |  | tool:hw_admission (the deny message names the wrapped command) | tooling-engineer | 72 (22) | wall |
| `keeper:check-migration-number-refs-in-tests` | Keeper (ratchet, 2026-10-10): an awake product's backend test must not reference a migration by NUMBER ("217_x | api:noctusai_lib.testing.migrations.migration_path · tool:scaffold_migration (reference_in | backend-engineer | 48 (21) | wall |
| `keeper:check-eight-way-sync` | Keeper: the 8-way methodology surface sync (CLAUDE.md / MEMORY.md / .claude/agents/ / KB / CONTEXTUALIZE.md /  | **NONE** | tooling-engineer | 46 (24) | wall |
| `guard:executor-dispatch` |  | tool:task_branch start (creates the worktree the guard requires) | tooling-engineer | 44 (22) | wall |
| `guard:test-seams` |  | none (a monkeypatch is an in-line choice; the write-time judge of the ADDED lines is the e | tooling-engineer | 18 (9) | wall |
| `keeper:verify-kb-sync` | Verify CLAUDE.md pointers + KB INDEX.md are in sync | tool:kb_sync (regenerates counts; task_branch integrate runs it) | tooling-engineer | 15 (14) | wall |
| `keeper:check-not-configured-carries-marker` | Keeper: every *NotConfigured / *NaoConfigurado exception class in the seed or an active product's backend/app/ | **NONE** | tooling-engineer | 13 (7) | wall |
| `keeper:check-mutation-invalidate-only` | Keeper (2026-10-21): a TanStack useMutation({...}) that neither draws its change (onMutate) nor writes the ser | **NONE** | frontend-engineer | 12 (5) | wall |
| `keeper:check-silent-refusal` | Keeper (2026-10-24, N=4: F75b F76 F78 F86): a refusal the user never sees — a query's empty branch (rows.lengt | **NONE** | frontend-engineer | 12 (8) | wall |
| `keeper:check-upload-route-body-override` | Keeper: every UploadFile-declaring route under products/<slug>/backend/app/ (any annotation shape — UploadFile | **NONE** | backend-engineer | 10 (7) | wall |
| `keeper:check-agent-prompt-text-in-code` | Keeper (Julia v2 D3): prompt text — ToolSpec(description=...), SectionInput(conteudo=...), *_SYSTEM = ..., lon | **NONE** | tooling-engineer | 7 (5) | real-drift-catch |
| `keeper:check-ci-test-matrix-coverage` | Keeper: .github/workflows/test.yml's product-backend-tests / product-frontend-tests `matrix: product:` lists m | **NONE** | devops-engineer | 7 (6) | real-drift-catch |
| `keeper:check-org-identity-function-parity` | Keeper (SEC-2 customer-role isolation, 2026-09-28): every re-declaration of the shared public.current_org_id() | **NONE** | backend-engineer | 6 (4) | real-drift-catch |
| `keeper:check-prod-exposure-consent` | Prod-promotion consent gate: a product's FIRST arrival on deploy/fleet/docker-compose.prod.yml, deploy/tunnel/ | **NONE** | devops-engineer | 6 (5) | real-drift-catch |
| `keeper:check-claude-md-router` | Keeper: CLAUDE.md router discipline — §1 rules are ONE line (rule + `→` pointer, no inlined bodies) and the wh | **NONE** | tooling-engineer | 5 (4) | real-drift-catch |
| `keeper:check-org-role-without-org-id` | Keeper (B3): resolve_org_role/is_org_admin/require_org_admin_role called without org_id= decide admin in the H | **NONE** | backend-engineer | 5 (4) | real-drift-catch |
| `keeper:check-secdef-migration-revokes-execute` | Keeper: a migration creating a SECURITY DEFINER function must REVOKE EXECUTE FROM PUBLIC/anon/authenticated in | KB § PATTERNS/backend/migration-sql-security-gates.md (migration carries the REVOKE lockdo | backend-engineer | 5 (4) | real-drift-catch |
| `keeper:check-async-handler-sync-db` | Keeper (2026-10-21): an async def route handler that calls the SYNC supabase client directly (.execute() / .au | **NONE** | backend-engineer | 4 (4) | real-drift-catch |
| `keeper:check-license-gate-by-construction` | Keeper (round 2, 2026-10-06): the license gate holds BY CONSTRUCTION — no active product hand-rolls an org dep | **NONE** | devops-engineer | 4 (3) | real-drift-catch |
| `keeper:check-new-org-table-rls` | BLOCKING DELTA gate (owner directive 2026-10-26, org-config isolation): a NEW migration's table with an org_id | tool:scaffold_migration (with_table emits the rls_subquery_policy) | backend-engineer | 4 (3) | real-drift-catch |
| `keeper:check-override-is-range` | Keeper: every npm `overrides` entry must be a RANGE (^/~/>=), never an exact version. An exact override wins o | .claude/skills/noc-dep-update/SKILL.md (decision gates) | devops-engineer | 4 (4) | real-drift-catch |
| `keeper:check-postgrest-schema-qualified-table` | Keeper: a Supabase/PostgREST client is ALREADY schema-bound, so `.table(name)`/`.from_(name)` resolves RELATIV | **NONE** | backend-engineer | 4 (4) | real-drift-catch |
| `keeper:check-harness-mod` | Keeper: a Claude Code mod (.claude/mods/*) is a UX layer over the canonical Python gates, never a gate. (a) ma | **NONE** | tooling-engineer | 3 (3) | real-drift-catch |
| `keeper:check-model-dump-json-mode` | Keeper (2026-10-15, orbity live 502): in ACTIVE products' backend/app, a pydantic `.model_dump()` without mode | **NONE** | backend-engineer | 3 (3) | real-drift-catch |
| `keeper:check-no-metadata-authz` | Keeper: user_metadata org_id/role/org_role is USER-WRITABLE — forbid backend reads of it for authorization/sco | **NONE** | backend-engineer | 3 (3) | real-drift-catch |
| `keeper:check-seed-declared-imports` | Keeper: every RUNTIME third-party import in seed/*/backend/<pkg>/ must name a distribution declared in THAT pa | **NONE** | devops-engineer | 3 (3) | real-drift-catch |
| `keeper:check-stale-after-write` | Keepers (2026-10-24) check_mutation_family_write + check_job_start_without_handoff, one scan: (a) a raw useMut | **NONE** | frontend-engineer | 3 (3) | real-drift-catch |
| `guard:release-steward` |  | tool:release_steward (decide() shared by the tool and the hook) | tooling-engineer | 2 (2) | real-drift-catch |
| `keeper:check-conflict-markers` | Keeper: a tracked file committed with unresolved merge-conflict markers. Flags only when an opener (7+ '<') AN | **NONE** | devops-engineer | 2 (2) | real-drift-catch |
| `keeper:check-ledger-pii` | Keeper (severity critical, no suppression marker): personal data (CPF/CNPJ with valid check digit, BR phone, n | api:tools/noctus/dev/_pii_guard.assert_no_pii (ledger writers refuse) | tooling-engineer | 2 (2) | real-drift-catch |
| `keeper:check-mcp-tools-reject-unknown-args` | Keeper: `build_server()` must call `install_strict_tool_arguments(server)` AFTER `register_all`. FastMCP regis | api:install_strict_tool_arguments (after register_all) | tooling-engineer | 2 (2) | real-drift-catch |
| `keeper:check-migration-untyped-empty-array` | Keeper: untyped empty `ARRAY[]` (no ::type) in migration SQL fails on apply with 42P18. Severity high; blockin | **NONE** | backend-engineer | 2 (2) | real-drift-catch |
| `keeper:check-org-picker-ready-policies` | Keeper (org picker): a product whose migration chain last sets products.org_picker_ready=true must have no pol | **NONE** | backend-engineer | 2 (1) | real-drift-catch |
| `keeper:check-piped-exit-code-pattern` | Keeper: verdict-channel-integrity — flags `$?` read off a PIPELINE (reads the LAST stage's exit status, not th | **NONE** | tooling-engineer | 2 (2) | real-drift-catch |
| `keeper:check-primary-checkout-commit` | Keeper: refuse a WORK commit on a shared branch (dev/main/prod) in the PRIMARY checkout — the self-branching r | guard:primary-write (the write is denied before a commit exists) | tooling-engineer | 2 (2) | real-drift-catch |
| `keeper:check-product-declared-imports` | Keeper: every RUNTIME third-party import in an active product's backend/app/ — plus IMPLIED deps (fastapi Form | **NONE** | devops-engineer | 2 (1) | real-drift-catch |
| `keeper:check-db-guard-registry-static` | Keeper (2026-11-05): offline invariants of verify_db_guards DEFAULT_REGISTRY - unique ids, every probe migrati | **NONE** | backend-engineer | 1 (1) | real-drift-catch |
| `keeper:check-hand-copied-org-admin` | Keeper: awake product frontends must not hand-copy the org-admin UX gate (`isProductAdmin // org.role owner/ad | **NONE** | backend-engineer | 1 (1) | real-drift-catch |
| `keeper:check-llm-usage-context-entry` | Keeper: a metered LLM call (chat_with_tools/chat_completion*/run_tool_loop) in products/<slug>/backend/app who | **NONE** | backend-engineer | 1 (1) | real-drift-catch |
| `keeper:check-migration-number-collision` | Keeper: two migrations claiming the same numeric prefix. Leg A (high) = duplicate ON DISK in one product — app | tool:scaffold_migration (next_migration_number reserves across disk/origin/branches) | backend-engineer | 1 (1) | real-drift-catch |
| `keeper:check-no-authenticated-grant-on-content-tables` | Keeper: an agents migration (>= 036) must not GRANT SELECT or CREATE POLICY TO authenticated/anon on a table o | **NONE** | backend-engineer | 1 (1) | real-drift-catch |
| `keeper:check-redis-client-via-seam` | Keeper: every Redis client (redis.Redis/StrictRedis/from_url/ConnectionPool.from_url, aioredis) in seed/** bac | **NONE** | backend-engineer | 1 (1) | real-drift-catch |
| `keeper:check-schema-wide-anon-grant` | Keeper (severity critical, NO allowlist / suppression marker — same posture as --check-storage-bucket-public): | **NONE** | backend-engineer | 1 (1) | real-drift-catch |
| `keeper:check-storage-bucket-public` | Keeper (severity critical, NO allowlist / suppression marker / accept-with-rationale escape hatch — owner dire | **NONE** | backend-engineer | 1 (1) | real-drift-catch |
| `keeper:check-workflow-job-timeouts` | Keeper: every GitHub Actions job (no `uses:`) must declare timeout-minutes <= ceiling (merge-queue drain 360), | **NONE** | devops-engineer | 1 (1) | real-drift-catch |
| `ci:agents-secc-ci` |  | none (end-to-end container verdict; no static construction possible) | devops-engineer | 0 (0) | never-fires |
| `ci:embedding-cache-gate` |  | write-path: pre-commit embedding refresh (cache-auto-freshness) | devops-engineer | 0 (0) | never-fires |
| `ci:merge-queue` |  | none (independent verdict on the merged tree; construction lives in task_branch) | devops-engineer | 0 (0) | never-fires |
| `ci:seed-typecheck` |  | none (a type-checker is the framework-native check; nothing to scaffold) | devops-engineer | 0 (0) | never-fires |
| `ci:test` |  | none (independent verdict on the merged tree; the construction legs live in the keepers it | devops-engineer | 0 (0) | never-fires |
| `guard:harness-signature` |  | none (advisory PostToolUse measurement leg; it never blocks) | tooling-engineer | 0 (0) | never-fires |
| `guard:primary-write-post` |  | none (advisory PostToolUse measurement leg; it never blocks) | tooling-engineer | 0 (0) | never-fires |
| `keeper:check-agent-archetype-contract` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-agent-context-cache-freshness` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-agent-format` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-agent-kb-alignment` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-ai-feature-completeness` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-auth-boundary-false-green` | auth-boundary tests must not pair 401 with a maskable code (404/422) | **NONE** | backend-engineer | 0 (0) | unmeasured |
| `keeper:check-auth-dep-anti-pattern` | route auth dependency anti-patterns | **NONE** | backend-engineer | 0 (0) | unmeasured |
| `keeper:check-auto-improvement-cache-freshness` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-branch-orphan` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-branch-tree-mirror` | Keeper (pre-push HARD-BLOCK): for the given branch (or all non-terminal branches when omitted) verify the bran | write-path: branch_pointer._write_row writes both files | tooling-engineer | 0 (0) | never-fires |
| `keeper:check-cache-uses-locking-helper` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-canonical-organ-consumption` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-codification-debt` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-codification-pipeline-health` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-commands-listed-in-router` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-config-extends-product-settings` |  | **NONE** | devops-engineer | 0 (0) | unmeasured |
| `keeper:check-conftest-env-setdefault` | Keeper: a product conftest that defers a CREDENTIAL/ENDPOINT env key to the ambient environment via `os.enviro | **NONE** | tooling-engineer | 0 (0) | never-fires |
| `keeper:check-consent-routes-mounted` |  | KB § PATTERNS/frontend/consent-routes-mandate.md (consent routes are seed-mounted, never r | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-contextualize-alignment` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-contract-field-provenance-map` | social-wiring's F5 contract generator (card_hub/contrato_gerador) emits ~140 distinct dotted placeholder token | **NONE** | tooling-engineer | 0 (0) | never-fires |
| `keeper:check-dependabot-product-coverage` | Keeper: .github/dependabot.yml must carry an npm block for every products/<slug>/frontend with a package.json, | **NONE** | devops-engineer | 0 (0) | never-fires |
| `keeper:check-detector-has-regression-test` | Keeper: every check_* detector in compliance.py has a `class Test<DetectorCamel>` regression test. Exits 1 on  | tool:scaffold_keeper (emits the Test<Detector> class) | devops-engineer | 0 (0) | never-fires |
| `keeper:check-doc-staleness` | Keeper (CI + pre-push): deterministic doc-staleness gate. With --doc-range BASE..TIP: change-coupling (covered | **NONE** | tooling-engineer | 0 (0) | never-fires |
| `keeper:check-embed-funnel-self-configures` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-engineer-slice-scored` | Backstop for the task_branch integrate slice-score gate: landed engineer slices (branch-tree pointer) with no  | write-path: task_branch integrate refuses slice_unscored | tooling-engineer | 0 (0) | never-fires |
| `keeper:check-every-test-file-is-gated` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-fe-route-missing` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-files-outlined` |  | **NONE** | frontend-engineer | 0 (0) | unmeasured |
| `keeper:check-frontend-config-paths` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-frontend-entrypoint` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-gate-triad` | meta-gate: every gate declares construction leg + owner; decision matrix complete | tool:scaffold_keeper (requires mechanism+owner) · tool:gate_alignment declare | tooling-engineer | 0 (0) | new (shadow) |
| `keeper:check-git-hook-file-tampering` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-git-hooks-bypass` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-git-leftovers` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-gitignore-drift` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-guard-hooks-registered` | Every scripts/hooks/claude-guard-*.py must be referenced by a hook entry in .claude/settings.json (unregistere | **NONE** | tooling-engineer | 0 (0) | never-fires |
| `keeper:check-guc-carveout-guard-hand-written` | Keeper: a NEW migration may not hand-write a trigger function that gates a table mutation on a transaction-loc | **NONE** | backend-engineer | 0 (0) | never-fires |
| `keeper:check-handrolled-core-url` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-hardcoded-product-slug-set` | Keeper: a literal collection of >=3 live product slugs (seed/lib/backend/tests/*.py, AST) or a hardcoded bash  | **NONE** | devops-engineer | 0 (0) | never-fires |
| `keeper:check-harness-mod-integrity` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-hashlib-usedforsecurity` | Keeper: a weak-hash call (hashlib.md5/sha1/new("md5"/"sha1", ...)) in the Bandit scope (products/*/backend/app | **NONE** | backend-engineer | 0 (0) | never-fires |
| `keeper:check-job-start-without-handoff` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-kb-semantic-drift` | Keeper: surfaces when live owns_kb validation diverges from latest ratified baseline by > threshold. Severity  | **NONE** | tooling-engineer | 0 (0) | never-fires |
| `keeper:check-keeper-cache-freshness` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-ledger-drain-after-settle` | Keeper (pre-push HARD-BLOCK): every append-only project-history ledger written during a task_branch run must h | **NONE** | tooling-engineer | 0 (0) | never-fires |
| `keeper:check-lgpd-entry-removal-range` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-lying-loading-state` | Keeper: TanStack Query v5 `isLoading` is FALSE during a background refetch (`isLoading === isPending && isFetc | **NONE** | frontend-engineer | 0 (0) | never-fires |
| `keeper:check-memory-md-index` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-merge-drivers-registered-in-ci` | Keeper: every custom `merge=<name>` in .gitattributes must be registered by scripts/hooks/register-merge-drive | **NONE** | devops-engineer | 0 (0) | never-fires |
| `keeper:check-methodology-doc-refs` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-migration-applied-ledger-drift` | Keeper (pre-push, DB round-trip, warning-only): per product, migration files on disk MINUS rows recorded in <r | **NONE** | backend-engineer | 0 (0) | never-fires |
| `keeper:check-mock-schema-validation` |  | **NONE** | backend-engineer | 0 (0) | unmeasured |
| `keeper:check-mutation-family-write` |  | **NONE** | frontend-engineer | 0 (0) | unmeasured |
| `keeper:check-name-on-nome-select` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-new-dependency-justified` | a NEW dependency carries a measured comparison record (never "is it standard") | .claude/skills/noc-dep-update/SKILL.md (gate 0 + comparison-record template) · mcp/noctusa | tooling-engineer | 0 (0) | new (shadow) |
| `keeper:check-no-direct-llm-sdk-import` | Keeper (D26): refuse direct `anthropic`/`openai` SDK imports in active products' backend app code. LLM calls g | **NONE** | backend-engineer | 0 (0) | never-fires |
| `keeper:check-no-vendor-study-in-git` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-org-owned-definition-not-instanciavel` | An agent definition declared (products/*/ops/agents/**, agent package.yaml) with owner_product AND instanciave | **NONE** | backend-engineer | 0 (0) | never-fires |
| `keeper:check-out-of-contract-trees` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-outlined` | Keeper: every STAGED .py/.ts/.tsx must be AST-outline-able (no SyntaxError / parse failure). Exits 1 on any un | **NONE** | frontend-engineer | 0 (0) | never-fires |
| `keeper:check-path-references` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-phase-state` | Check §6 ↔ §11 phase-state consistency across PROJECT.md files. Exits 1 on any high-severity issue. Used by th | **NONE** | tooling-engineer | 0 (0) | never-fires |
| `keeper:check-phase-state-consistency` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-postgrest-unbounded-query` | Keeper: PostgREST silently caps ANY select at `db-max-rows` (Supabase default 1 000) — no error, no warning, ` | **NONE** | backend-engineer | 0 (0) | never-fires |
| `keeper:check-predeploy-leg-verify-or-block` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-private-accent-fold` | Keeper: no private unicodedata NFKD/NFD accent fold outside noctusai_lib.primitives.accents. Severity high; bl | **NONE** | backend-engineer | 0 (0) | never-fires |
| `keeper:check-private-unique-violation-predicate` | Keeper: no private PostgREST unique-violation predicate outside noctusai_lib.primitives.postgrest_errors. Seve | **NONE** | backend-engineer | 0 (0) | never-fires |
| `keeper:check-prod-cache-reachable` |  | **NONE** | devops-engineer | 0 (0) | unmeasured |
| `keeper:check-prod-compose-env-manifest-sync` | deploy/fleet/env.fleet.keys must document every ${VAR} docker-compose.prod.yml + compose.infra.prod.yml interp | **NONE** | devops-engineer | 0 (0) | never-fires |
| `keeper:check-prod-compose-hardening-parity` | deploy/fleet/docker-compose.prod.yml's agents + academia-de-reciclagem security blocks (cap_drop/cap_add/secur | **NONE** | devops-engineer | 0 (0) | never-fires |
| `keeper:check-product-guide-cochange` |  | **NONE** | devops-engineer | 0 (0) | unmeasured |
| `keeper:check-product-guide-cochange-range` |  | **NONE** | devops-engineer | 0 (0) | unmeasured |
| `keeper:check-product-icon-registered` |  | **NONE** | devops-engineer | 0 (0) | unmeasured |
| `keeper:check-product-lockfile-dep-sync` | Keeper: a product's package-lock.json must carry a `node_modules/<dep>` entry for every dep its package.json d | **NONE** | devops-engineer | 0 (0) | never-fires |
| `keeper:check-product-service-worker` |  | **NONE** | devops-engineer | 0 (0) | unmeasured |
| `keeper:check-product-source-build-dep-pip-seam` |  | **NONE** | devops-engineer | 0 (0) | unmeasured |
| `keeper:check-project-history-staged` | Pre-commit gate: a commit staging project-history/ledger.ndjson must stage the PROJECT-HISTORY.md rendered fro | **NONE** | tooling-engineer | 0 (0) | never-fires |
| `keeper:check-root-requirements-superset` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-section-7-placeholder-consistency` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-seed-compliance` |  | **NONE** | devops-engineer | 0 (0) | unmeasured |
| `keeper:check-seed-template-sync` | Keeper: templates/product-seed/ must equal products/seed/ rendered by the sync (copy + placeholders), EXCEPT t | write-path: pre-commit syncs products/seed -> templates/product-seed | devops-engineer | 0 (0) | never-fires |
| `keeper:check-seed-test-root-ci-coverage` |  | **NONE** | devops-engineer | 0 (0) | unmeasured |
| `keeper:check-seed-version-propagation` |  | **NONE** | devops-engineer | 0 (0) | unmeasured |
| `keeper:check-settings-di-regression` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-skill-format` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-skills-listed-in-router` | Keeper sub-leg of check_eight_way_sync: every .claude/skills/<name>/ MUST be referenced in CLAUDE.md §2 'Proce | **NONE** | tooling-engineer | 0 (0) | never-fires |
| `keeper:check-slowapi-with-pep563` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-stale-branch-pointers` | Safety net (pre-push) behind the task_branch pointer lifecycle: on_going/integrated-worktree-live pointers who | write-path: task_branch start/integrate/cleanup write the transitions | tooling-engineer | 0 (0) | never-fires |
| `keeper:check-stand-in-conformance` | Keeper: a test double (mock/wrapper) must satisfy the same CONTRACT as the real thing it replaces. Built again | **NONE** | backend-engineer | 0 (0) | never-fires |
| `keeper:check-standard-routers-audit` | standard routers mounted per product | **NONE** | backend-engineer | 0 (0) | unmeasured |
| `keeper:check-status-pagina-role-parity` |  | **NONE** | tooling-engineer | 0 (0) | unmeasured |
| `keeper:check-table-has-rls` |  | **NONE** | backend-engineer | 0 (0) | unmeasured |
| `keeper:check-tunnel-ingress-snapshot-sync` | deploy/tunnel/ingress.yml is the declared SINGLE SOURCE OF TRUTH for public hostname->service routing; this as | **NONE** | devops-engineer | 0 (0) | never-fires |
| `keeper:check-version-bump` | Gate MAJOR-bump authorization: refuse working-tree VERSION whose MAJOR exceeds HEAD's unless .major-bump-autho | **NONE** | devops-engineer | 0 (0) | never-fires |
| `keeper:check-waha-instances-render-sync` | deploy/fleet/compose.waha.yml must equal the render of deploy/fleet/waha-instances.yml (one WAHA Core containe | **NONE** | backend-engineer | 0 (0) | never-fires |

## Route auth / exposure gates re-judged for a publicly documented API

| Gate | Verdict | Gap / overlap / decision |
|---|---|---|
| `ci:test` | keep | Hosts trivy-fs/bandit SARIF; their findings should flow to the shared ledger (SARIF) - access-tiers owns the mapping. |
| `keeper:check-auth-boundary-false-green` | overlap | Hand-written auth assertions; the schema-driven contract test (access-tiers) generates strict 401/403 for EVERY documented route. Narrow this to the remaining hand-written tests once it lands; one property, one gate. |
| `keeper:check-auth-dep-anti-pattern` | gap | Tier-blind: asks 'has auth'. With make_router(tier=) the property is 'declared tier'. Refine to require a tier (access-tiers owns). |
| `keeper:check-consent-routes-mounted` | keep | Legal/consent is a public-allowlist category: derive the allowlist's consent entries from this mandate (single source), not a second hand list. |
| `keeper:check-new-org-table-rls` | overlap | Delta gate for org_id tables; D4 'RLS on every non-public table' is the general property. Keep as the org-specific delta; the general gate owns the rest. |
| `keeper:check-no-authenticated-grant-on-content-tables` | gap | Scoped to agents migrations >=036 only: other PostgREST-exposed schemas are unscanned. Subsume into the D4 DB-defaults keeper (access-tiers), then retire this one. |
| `keeper:check-no-metadata-authz` | keep | Backend-only scan; holds with a public route list (a user-writable claim is exploitable either way). |
| `keeper:check-org-role-without-org-id` | keep | Authz correctness on selected org; unchanged. |
| `keeper:check-prod-exposure-consent` | keep | Exposure-surface registration is the owner's decision; unchanged by public docs. |
| `keeper:check-schema-wide-anon-grant` | keep | Critical, no allowlist; no overlap with tier keepers (grants vs routes). |
| `keeper:check-secdef-migration-revokes-execute` | keep | Static twin of verify_db_guards secdef probe: two ends of one property, intentional (commit + predeploy). |
| `keeper:check-standard-routers-audit` | gap | Per-product router audit; must require tier-declared routers, and cover products it skips (active-only scope is unsafe once the full route list is public). |
| `keeper:check-storage-bucket-public` | keep | Critical, no allowlist; storage exposure is not covered by route tiers. |
| `keeper:check-tunnel-ingress-snapshot-sync` | keep | Hostname routing source-of-truth; unchanged. |
| `keeper:check-upload-route-body-override` | keep | Fires 10x/7 sessions = wall by threshold; construction leg missing (seed upload-route factory). NOC-REMEDIATE[gate-wall]. |

## Decision coverage matrix

| # | Decision | Home | Construction | Backstop gate | Telemetry | Branch |
|---|---|---|---|---|---|---|
| D1 | Access tiers on every route and table, platform-wide, default deny. Route construction = `make_router(tier=)` over FastAPI APIRouter `dependencies=` (framework-native; to be MEASURED against alternatives) | KB access-tiers pattern + §1 Gate line (access-tiers) | make_router(tier=) factory; bare route decorator restricted | pending:feat/access-tiers-gate (access-tier keepers) | pending:feat/access-tiers-gate | feat/access-tiers-gate |
| D2 | Closed public allowlist (landing+nav, login/signup/reset, pricing/checkout/thank-you w/o PII sans one-time token, legal/consent, lead forms); webhooks/OAuth callbacks/health in a service/signed tier | KB access-tiers pattern | public allowlist is the only way to declare a public route | pending:feat/access-tiers-gate | pending:feat/access-tiers-gate | feat/access-tiers-gate |
| D3 | /docs and /openapi.json are not public in prod | KB access-tiers pattern | seed app factory disables docs outside dev | pending:feat/access-tiers-gate | pending:feat/access-tiers-gate | feat/access-tiers-gate |
| D4 | DB defaults: RLS on, no browser grants on non-public tables, no anon/PUBLIC read on token/secret/PII, no inactive schema in pgrst.db_schemas; scaffold emits per-table role-matrix test | KB database-rls + migration-sql-security-gates | tool:scaffold_migration emits RLS + role-matrix test (access-tiers branch extends it) | keeper:check-no-authenticated-grant-on-content-tables, keeper:check-schema-wide-anon-grant, keeper:check-storage-bucket-public, keeper:check-new-org-table-rls + access-tier keepers (pending) | gate events via cli wrapper | feat/access-tiers-gate |
| D5 | Effective-state production check = Supabase advisor (candidate, to be MEASURED) + our own SQL, scheduled and pre-deploy | KB access-tiers pattern | tool: effective-state check (access-tiers branch) | pending:feat/access-tiers-gate | pending:feat/access-tiers-gate | feat/access-tiers-gate |
| D6 | One shared living findings ledger exported as SARIF 2.1.0 (candidate standard format, to be MEASURED against the home-grown shape) uploaded to code scanning; baselineState reconcile; suppressions with justification+owner+expiry | KB findings-ledger pattern | noctus.dev.findings_ledger (single writer) | pending:feat/access-tiers-gate | gate wall findings already emitted as SARIF results (gate_alignment.file_wall_findings) | feat/access-tiers-gate |
| D7 | Ledger visibility injected at agent start and dispatch and in every template | KB findings-ledger pattern | SessionStart/dispatch injection + templates | pending:feat/access-tiers-gate | pending:feat/access-tiers-gate | feat/access-tiers-gate |
| D8 | Julia continuous evals on the real turn path (content-change, schedule, handoff triggers; every mistake becomes a permanent case; MODEL/STRUCTURAL/CONTENT attribution; same ledger) | KB agents-eval pattern | eval harness on the real turn path | pending:feat/julia-turn-redesign | pending:feat/julia-turn-redesign | feat/julia-turn-redesign |
| D9 | Red-team leg with promptfoo ONLY if it measures better than in-repo; else a recorded reason | KB agents-eval pattern | comparison record (decision 12) then harness | pending:feat/julia-turn-redesign | pending:feat/julia-turn-redesign | feat/julia-turn-redesign |
| D10 | The triad for every enforceable thing: construction + backstop gate + alignment telemetry; walls ranking; meta-gate | KB § PATTERNS/common/gate-methodology-sync.md (Build triad) · §1 Gate↔methodology line | tool:scaffold_keeper requires mechanism+owner and emits the inventory row; tool:gate_alignment declare | keeper:check-gate-triad | guard-events.ndjson + noctus.dev.gate_alignment walls | feat/gate-alignment |
| D11 | Gate admission/demotion by measured precision: warn-only shadow, effective-FP <= ~10%, owner, actionable refusals | KB § PATTERNS/common/gate-methodology-sync.md (Admission & demotion) | declare_gate defaults placement=warn; shadow record required for a new blocking gate | keeper:check-gate-triad | gate_alignment.gate_stats effective_fp; walls demote flag | feat/gate-alignment |
| D12 | Measured comparison, not standard-by-default: in-repo vs standard tool compared on stated metrics; switch only when the standard wins on the metrics that matter; unmeasured = no switch. SARIF, FastAPI dependency wrapper, Supabase advisor, promptfoo are CANDIDATES to measure | KB § PATTERNS/common/gate-methodology-sync.md (Measured comparison) · skill noc-dep-update gate 0 | comparison-record template in noc-dep-update; mcp/noctusai/dependency-additions.json | keeper:check-new-dependency-justified | warn-first shadow events via cli wrapper | feat/gate-alignment |
| D13 | Research-first is the default for EVERY request: specialists' reliable sources are read (not link-checked), cited in the deliverable, unverified items marked; tool choice follows the measured-switch rule | KB § PATTERNS/common/gate-methodology-sync.md (Sources & how they map; How to apply step 0) · engineer-seed.md + advisor agents L1 line | standing line in .claude/agents/engineer-seed.md and the 7 advisor agents; pattern-authoring checklist step 0; scaffold_keeper requires `source` | keeper:check-gate-triad (new gates carry `source`) + report-only `--gate-alignment sources` (KB deliverables without a sources section; never blocks code commits) | sources report output; gate-triad events | feat/gate-alignment |
| D14 | Public-API-docs readiness: every documented route gated and protected by old+new gates with no gap and no duplicate (each property one gate) | KB § PATTERNS/common/gate-methodology-sync.md (matrix) + access-tiers pattern | make_router(tier=) + schema-driven contract test (pending) · old gates re-judged in `api_review` | old: auth-boundary-false-green (narrow), auth-dep-anti-pattern (require tier), standard-routers-audit, consent-routes-mounted, no-authenticated-grant (subsume), new-org-table-rls, schema-wide-anon-grant, storage-bucket-public, secdef-revokes-execute, no-metadata-authz, upload-route-body-override · new: pending:feat/access-tiers-gate (tier keeper, schema-leak keeper, contract test) | gate events (cli wrapper) · `api_review` verdicts in the inventory | feat/gate-alignment (old-gate review) + feat/access-tiers-gate (new) |
| D15 | False-alarm gates are researched and fixed, not just demoted: containment by demotion -> research with read+cited primary sources -> detector fix with FP/TP regression tests -> re-measure -> re-promote; ledger row + expiry while demoted | KB § PATTERNS/common/gate-methodology-sync.md (Alignment loop, step 4) | declare_gate/inventory `demoted` block (since, expiry, destination) is the only way to hold a gate demoted | keeper:check-gate-triad (fails a demoted gate without destination, or past expiry) | gate_alignment walls: demote flag from measured effective-FP > 10% | feat/gate-alignment |
