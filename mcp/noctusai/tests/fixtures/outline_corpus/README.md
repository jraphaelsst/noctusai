# Frozen TS-outline corpus

FROZEN, vendored snapshot — a copy, not a symlink, of real `.ts`/`.tsx` files
picked to cover the shapes `outline_typescript.py` handles: a functional
component, a hook, a default-export entrypoint, arrow-function components,
class components, and a re-export barrel. Copied 2026-09-23 (see
`outline_corpus_baseline.json` for the file list + captured symbol counts).

**This directory changes ONLY when someone deliberately updates it** — a new
outliner shape needs coverage, or a real outliner regression fix needs a
regression fixture. It does **not** track live product code: editing
`products/**` never touches this corpus and never drifts
`outline_corpus_baseline.json`. That coupling (baseline measured against the
live, ever-growing product tree) is what made
`test_outline_typescript_corpus.py` fire on ordinary feature work — 9
baseline-bump-only commits since 2026-08 with no sanctioned per-entry
re-ratification path (see `project-history/auto-improvement.ndjson`,
2026-09-01 entry). Freezing the corpus removes the coupling at the root.

Several of these files were chosen specifically because they caused past
false fires against the live tree (kept here as permanent regression
coverage instead of a source of recurring churn):

- `products/core/frontend/src/main.tsx` — entrypoint bootstrap.
- `products/core/frontend/src/lib/api.ts` — top-level functions/consts.
- `products/social-wiring/frontend/src/App.tsx` — arrow-fn component,
  `React.lazy` route table.
- `products/social-wiring/frontend/src/pages/Settings.tsx` — large
  tab-driven page component.
- `products/social-wiring/frontend/src/hooks/useMediaCreation.ts` — a
  `useXxx` hook.
- `products/erp-imobiliario/frontend/src/hooks/useVistaShowcase.ts` /
  `pages/VistaShowcase.tsx` — a hook + the page it backs, post-split (the
  page dropped to a near-barrel 3-symbol shell).
- `products/erp-imobiliario/frontend/src/hooks/useMetas.ts` — a small
  (~4-5 symbol) hook exercising the absolute-floor tolerance.
- `products/personal-finance/frontend/src/hooks/useTransacoes.ts` — another
  hook shape.
- `products/core/frontend/src/website/components/SectionErrorBoundary.tsx` /
  `seed/lib/frontend/src/components/ErrorBoundary.tsx` — `class extends
  React.Component` shapes.
- `seed/lib/frontend/src/components/index.ts` — a pure `export * from "…"`
  re-export barrel.

To update this corpus (new outliner shape, or replacing a stale example):
copy the file(s) in preserving the original repo-relative path under this
directory, then regenerate `outline_corpus_baseline.json` by deleting it and
re-running `pytest mcp/noctusai/tests/test_outline_typescript_corpus.py -m slow`
once (first run recaptures; re-run to enforce). Review the diff before
committing — a baseline change here should be reviewed as an OUTLINER
change, not a routine bump.
