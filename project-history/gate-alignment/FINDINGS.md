# gate-walls -- living findings ledger

> GENERATED next to `findings.ndjson` by `noctus.dev.findings_ledger` (`cli.py --findings-ledger-reconcile gate-walls`). Never edit by hand. Read your scope's open rows before you touch it. KB § PATTERNS/common/living-findings-ledgers.md.

**33 open / in-progress**, 2 fixed, 24 accepted (59 total).

| scope | open | critical | high | medium | in-progress | fixed |
|---|---:|---:|---:|---:|---:|---:|
| architect | 0 | 0 | 0 | 0 | 0 | 0 |
| backend-engineer | 8 | 0 | 0 | 8 | 0 | 0 |
| devops-engineer | 0 | 0 | 0 | 0 | 0 | 0 |
| feat/julia-turn-redesign | 4 | 0 | 0 | 4 | 0 | 0 |
| frontend-engineer | 2 | 0 | 0 | 2 | 0 | 0 |
| keeper:check-applied-md-ledger-parity | 1 | 0 | 0 | 1 | 0 | 0 |
| tooling-engineer | 18 | 0 | 7 | 11 | 0 | 2 |

## Open / in-progress (bulk rows are summarised below; every row is in the NDJSON)

| id | scope | target | kind | sev | status | found |
|---|---|---|---|---|---|---|
| GW-803dceed | tooling-engineer | `guard:executor-dispatch` | wall | high | open | keeper 2026-11-06 |
| GW-68d5d731 | tooling-engineer | `guard:heavy-run` | wall | high | open | keeper 2026-11-06 |
| GW-8a7e7ce8 | tooling-engineer | `guard:primary-write` | wall | high | open | keeper 2026-11-06 |
| GW-49b87ec8 | tooling-engineer | `keeper:check-eight-way-sync` | wall | high | open | keeper 2026-11-06 |
| GW-cdf82c59 | tooling-engineer | `release_steward deliverable derived_current: kb-counts at the branch head` | wall | high | open Refusal class deliverable:derived_current kb-counts (29 hits/14d, 6 sessions). Root cause: whole-tree-derived artifact judged at each branch head. Fixed by construction in adda0ba7d (landed f6830e641): removed from DERIVED_ARTIFACTS, regenerated at merge-queue compose, CI backstop on mq-candidate/dev/main/prod. Guardian needs /mcp reconnect. | tech-lead 2026-11-18 |
| GW-53a628ad | tooling-engineer | `release_steward deliverable scoped set` | wall | high | open | tech-lead 2026-11-12 |
| GW-a896193f | tooling-engineer | `release_steward deliverable scoped_green livetree stage: mcp/noctusai/tests/test_git_bypass_guard.py` | wall | high | open | noctusai-72 2026-11-17 |
| GW-1022ce72 | backend-engineer | `keeper:check-http-detail-echoes-exception` | refusal-class | medium | open | tooling-engineer 2026-11-18 |
| GW-bc89cbbf | backend-engineer | `keeper:check-http-detail-echoes-exception:new_findings-baseline_size` | refusal-class | medium | open | tooling-engineer 2026-11-18 |
| GW-919bc7c3 | backend-engineer | `keeper:check-http-detail-echoes-exception:pre-commit:http-error-body-echoes-exception` | refusal-class | medium | open | tooling-engineer 2026-11-18 |
| GW-eb900c38 | backend-engineer | `keeper:check-migration-guard-has-probe` | refusal-class | medium | open | tooling-engineer 2026-11-18 |
| GW-97778ff9 | backend-engineer | `keeper:check-migration-guard-has-probe:pre-commit:products/*/backend/migrations/*` | refusal-class | medium | open | tooling-engineer 2026-11-18 |
| GW-a7f25735 | backend-engineer | `keeper:check-private-accent-fold:pre-commit:private-accent-fold-unicodedata.normalize-nfd` | refusal-class | medium | open | refusal-recurrence 2026-11-19 |
| GW-1342894b | backend-engineer | `keeper:check-transition-log-hand-written:manual:products/*/backend/migrations/*` | refusal-class | medium | open | refusal-recurrence 2026-11-19 |
| GW-557af972 | backend-engineer | `keeper:check-upload-route-body-override` | wall | medium | open | keeper 2026-11-06 |
| GW-cc13ed14 | feat/julia-turn-redesign | `D8/gate` | matrix-pending | medium | open | keeper 2026-11-06 |
| GW-7a02ce68 | feat/julia-turn-redesign | `D8/telemetry` | matrix-pending | medium | open | keeper 2026-11-06 |
| GW-5eeadec9 | feat/julia-turn-redesign | `D9/gate` | matrix-pending | medium | open | keeper 2026-11-06 |
| GW-ef17b02e | feat/julia-turn-redesign | `D9/telemetry` | matrix-pending | medium | open | keeper 2026-11-06 |
| GW-cd69d7a7 | frontend-engineer | `keeper:check-mutation-invalidate-only` | wall | medium | open | keeper 2026-11-06 |
| GW-f78f6b18 | frontend-engineer | `keeper:check-silent-refusal` | wall | medium | open | keeper 2026-11-06 |
| GW-cea8cd06 | keeper:check-applied-md-ledger-parity | `D45/branch` | matrix-pending | medium | open | keeper 2026-11-19 |
| GW-5393b752 | tooling-engineer | `keeper:check-branch-tree-mirror` | refusal-class | medium | open | tooling-engineer 2026-11-18 |
| GW-490c87c3 | tooling-engineer | `keeper:check-branch-tree-mirror:pre-push:branch-pointer-for-engineer-feat/*` | refusal-class | medium | open | tooling-engineer 2026-11-18 |
| GW-74e4c627 | tooling-engineer | `keeper:check-branch-tree-mirror:pre-push:no-branch-pointer-found-for-create` | refusal-class | medium | open | tooling-engineer 2026-11-18 |
| GW-4aff8e12 | tooling-engineer | `keeper:check-branch-tree-mirror:pre-push:no-branch-pointer-found-for-feat/*` | refusal-class | medium | open | tooling-engineer 2026-11-18 |
| GW-e06fb5d6 | tooling-engineer | `keeper:check-branch-tree-mirror:pre-push:no-branch-pointer-found-for-head` | refusal-class | medium | open | tooling-engineer 2026-11-19 |
| GW-89b3baf2 | tooling-engineer | `keeper:check-engineer-slice-scored` | refusal-class | medium | open | tooling-engineer 2026-11-18 |
| GW-bb262304 | tooling-engineer | `keeper:check-engineer-slice-scored:manual:engineer-slice-feat/*` | refusal-class | medium | open | tooling-engineer 2026-11-19 |
| GW-c1a92b26 | tooling-engineer | `keeper:check-engineer-slice-scored:pre-push:engineer-slice-feat/*` | refusal-class | medium | open | tooling-engineer 2026-11-18 |
| GW-d752a1b6 | tooling-engineer | `keeper:check-not-configured-carries-marker` | wall | medium | open | keeper 2026-11-06 |
| GW-9c0a362f | tooling-engineer | `keeper:verify-kb-sync` | wall | medium | open | keeper 2026-11-06 |
| GW-7407656a | tooling-engineer | `seed timing tests under hw contention` | wall | medium | open | tech-lead 2026-11-12 |

## Accepted (rationale on record)

- GW-06b94da1 backend-engineer `keeper:check-migration-number-refs-in-tests` -- working as designed: caught tests pinning migration numbers; scaffold_migration/next_migration_number are the construction leg; quiet since 2026-11-12
- GW-0bc75047 backend-engineer `keeper:check-postgrest-schema-qualified-table` -- working as designed: schema-qualified PostgREST table refused; quiet since 2026-11-13
- GW-2a531f5e tooling-engineer `keeper:check-agent-kb-alignment` -- working as designed: agent owns_kb alignment; single session on 2026-11-10
- GW-3c78d818 tooling-engineer `keeper:check-polling-request-budget` -- working as designed: refuses a poll over the request budget; author-fixed, quiet since 2026-11-14
- GW-4b0d1c93 frontend-engineer `keeper:check-tailwind-v4-class-names:pre-commit:outline-none-renders-differently-in-tailwind` -- working as designed: one author session fixed a Tailwind v3 class name after the refusal (32 denies in 1 sitting, last 2026-11-16)
- GW-51e8bf87 tooling-engineer `keeper:check-guard-hooks-registered` -- working as designed: guard not registered in settings refused; single session on 2026-11-14
- GW-5f4be806 tooling-engineer `guard:release-steward:guard-timed-out-failed-closed-after-s-fix-the-guard-do-not-b` -- obsolete: guard-timeout burst of 2026-11-11 under hardware contention; read-only calls now `allow-timeout`; 1 timeout deny since 2026-11-14
- GW-62ca7014 tooling-engineer `keeper:check-measurable-by-design` -- working as designed: a lifecycle table without an events table is refused; quiet since 2026-11-10
- GW-6bfd5230 backend-engineer `keeper:check-transition-log-hand-written:pre-commit:products/*/backend/migrations/*` -- working as designed: hand-written transition-log SQL refused in favour of scaffold_migration with_eventos; last deny 2026-11-17 (one session)
- GW-6c3be97e tooling-engineer `keeper:check-stale-branch-pointers` -- working as designed: stale pointers are refused until session_end_sweep auto-heals; last deny 2026-11-16
- GW-6ccdf1e9 backend-engineer `keeper:check-access-tier-tables` -- working as designed: a migration table without a declared access tier is refused; quiet since 2026-11-10
- GW-92001f00 architect `keeper:check-structure-constructor-parity` -- one-day burst (2026-11-10, 3 sessions, 22 denies) fixed in the same sitting; quiet 9d
- GW-946044e4 tooling-engineer `keeper:check-claude-md-router` -- working as designed: router word/rule-count budget refusing a re-bloated CLAUDE.md; quiet since 2026-11-13
- GW-972be65c devops-engineer `keeper:check-detector-has-regression-test` -- working as designed: scaffold_keeper emits the test; quiet since 2026-11-12
- GW-a32cc646 tooling-engineer `keeper:check-tax-canon-no-inline-params` -- working as designed: inline tax parameters refused; single session on 2026-11-07, quiet 12d
- GW-cb6da0da tooling-engineer `keeper:check-findings-ledgers` -- working as designed: ledger-vs-scanner drift detector, remedy is `findings_ledger reconcile`; quiet since 2026-11-11
- GW-cead0a77 tooling-engineer `keeper:check-gate-triad` -- construction shipped: scaffold_keeper returns the declare_command (mechanism+owner+source); quiet since 2026-11-14
- GW-dc00cb0a tooling-engineer `keeper:check-doc-staleness` -- obsolete: advisory-invocation double-count fixed 2026-11-14 (NOC_GATE_ADVISORY logs warn, not deny); no deny since 2026-11-16 at this key
- GW-e32392c6 backend-engineer `keeper:check-private-accent-fold:pre-commit:private-accent-fold-unicodedata.normalize-nfkd` -- working as designed: private accent-fold helper refused in favour of the shared one; single session, last 2026-11-16
- GW-e3743821 tooling-engineer `keeper:check-doc-staleness:manual:unknown` -- working as designed: the blocking doc-staleness invocation refusing a commit whose covered docs were not updated; not a recurring defect
- GW-e382c633 tooling-engineer `keeper:check-motion-import-boundary` -- working as designed: motion import boundary; 2 sessions, quiet since 2026-11-11
- GW-e870c0d1 tooling-engineer `keeper:check-stale-branch-pointers:pre-push:branch-tree-pointer-for-feat/*` -- working as designed: stale pointers are refused until session_end_sweep auto-heals; last deny 2026-11-16
- GW-f9d5cd38 tooling-engineer `keeper:check-doc-staleness:pre-commit:unknown` -- obsolete: advisory-invocation double-count fixed 2026-11-14 (NOC_GATE_ADVISORY logs warn, not deny); no deny since 2026-11-16 at this key
- GW-fdcd72e1 backend-engineer `keeper:check-async-handler-sync-db` -- working as designed: async handler doing sync DB refused (noc async_handlers_to_def codemod is the remedy); quiet since 2026-11-10
