# TypeScript Strict Mode Migration

Status: **DEFERRED** — to be tackled after v2.4 stabilization.

## Why

TypeScript strict mode (`"strict": true` in tsconfig.json) catches type errors at compile time that currently slip through: null/undefined mishandling, implicit `any` types, missing return types, unreachable code. Enabling it makes the codebase significantly more robust.

## Current State

All 5 frontends have `"strict": false` in tsconfig.json:
- `core/frontend/tsconfig.json`
- `products/erp-imobiliario/frontend/tsconfig.json`
- `products/personal-finance/frontend/tsconfig.json`
- `products/therapy-platform/frontend/tsconfig.json`
- `products/seed/frontend/tsconfig.json` (when created)

## Migration Checklist

### Phase 1: Shared packages (do first — everything depends on these)
- [ ] Enable strict in `shared/frontend/tsconfig.json` (if exists, or add one)
- [ ] Fix all type errors in `shared/frontend/src/*.ts`
- [ ] Fix all type errors in `shared/frontend/src/design-system/**/*.tsx`
- [ ] Add explicit return types to all exported functions
- [ ] Replace all `any` with proper types (especially Supabase client types)

### Phase 2: Core frontend
- [ ] Enable `"strict": true` in `core/frontend/tsconfig.json`
- [ ] Fix null/undefined errors (auth-context, api client, admin pages)
- [ ] Add proper types to all components and hooks
- [ ] Verify build passes with `npx tsc --noEmit`

### Phase 3: Product frontends (one at a time)
- [ ] ERP: enable strict → fix errors → verify build
- [ ] PF: enable strict → fix errors → verify build
- [ ] Therapy: enable strict → fix errors → verify build
- [ ] Seed: enable strict → fix errors → verify build

### Phase 4: Enforce going forward
- [ ] Add `npx tsc --noEmit` to CI pipeline
- [ ] Update CLAUDE.md: "All new code must compile with strict mode"
- [ ] Add pre-commit hook (optional)

## Expected Error Categories

1. **Implicit `any`** — function params without types, untyped destructuring
2. **Null checks** — `user?.email` where `user` could be null but isn't checked
3. **Missing return types** — void functions that should return something
4. **Index signature** — accessing object properties with string keys
5. **Supabase types** — `AnySupabaseClient` pattern needs real generic types

## Estimated Effort

~200-400 type errors across all frontends. Most are mechanical fixes (add `!` assertions, add null checks, add explicit types). Expect 2-3 hours per product.
