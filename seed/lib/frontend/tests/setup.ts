/**
 * Vitest setup — registers @testing-library/jest-dom matchers
 * (e.g. `toBeInTheDocument()`) on vitest's `expect` so component
 * tests can use them idiomatically.
 *
 * Uses the default `@testing-library/jest-dom` entry (index.mjs) rather than
 * the vitest-specific entrypoint. The reason: `@testing-library/jest-dom/vitest`
 * does `import { expect } from 'vitest'` which resolves from jest-dom's own
 * node_modules, potentially finding a different vitest copy than the running
 * test runner — causing "Invalid Chai property: toBeInTheDocument" when the two
 * vitest instances diverge (e.g. when using the framework's vitest binary to run
 * lib tests). The default `index.mjs` entry instead calls `expect.extend(extensions)`
 * on globalThis.expect, which is always the running test framework's expect
 * (vitest injects it as a global when `globals: true`).
 *
 * Mirrors `seed/framework/frontend/tests/setup.ts` pattern.
 */
import "@testing-library/jest-dom";
