/**
 * Vitest config for `@noctusai/lib` colocated tests.
 *
 * Tests live next to their sources (e.g. `src/components/FakeModeBadge.test.tsx`).
 * The lib package ships its own devDeps (vitest, @testing-library/*, react, react-dom,
 * jsdom) so the binary is local:
 *
 *   cd seed/lib/frontend && node_modules/.bin/vitest run
 *
 * (The framework binary also works: ../../framework/frontend/node_modules/.bin/vitest run)
 *
 * --- Dual-React guard ---
 * seed/lib/frontend has its own react + react-dom in node_modules. @testing-library/react
 * imports `react-dom/client` (a subpath), and JSX-transformed components import
 * `react/jsx-runtime`. Vite's module graph treats each subpath specifier as an
 * independent entry unless explicitly aliased — so without subpath aliases, react-dom
 * resolves from one copy while react hooks resolve from another, producing a null
 * dispatcher crash ("Cannot read properties of null (reading 'useState')").
 *
 * Fix: alias ALL react subpaths to the same physical copy + resolve.dedupe.
 * Subpath aliases are ordered BEFORE bare forms (longest prefix first).
 *
 * --- Dual-vitest / jest-dom matcher guard ---
 * `@testing-library/jest-dom/vitest` does `import { expect } from 'vitest'` which
 * may resolve to a different vitest copy than the running test runner when using
 * the framework binary — so matchers registered there don't land on the running
 * expect. Fixed in tests/setup.ts by switching to `@testing-library/jest-dom` (the
 * default index.mjs which calls `expect.extend()` on globalThis.expect, always the
 * running framework's expect when `globals: true` is set).
 *
 * NOC-REMEDIATE[harness-vitest-dual-react]: RESOLVED 2026-05-29
 * Root causes:
 *   1. Missing subpath aliases for react-dom/client, react/jsx-runtime,
 *      react/jsx-dev-runtime — these bypassed the bare-specifier aliases,
 *      creating two React instances in the module graph.
 *   2. setup.ts used @testing-library/jest-dom/vitest which imports its own
 *      vitest `expect` — diverges from the running test runner's expect when
 *      the framework binary is used. Fixed by switching to the default
 *      @testing-library/jest-dom entry that uses globalThis.expect.
 * Fix: explicit subpath aliases for all react/* + resolve.dedupe + setup.ts fix.
 */
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

const LIB_REACT = resolve(__dirname, "node_modules/react");
const LIB_REACT_DOM = resolve(__dirname, "node_modules/react-dom");

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: [resolve(__dirname, "tests/setup.ts")],
    include: ["src/**/*.test.{ts,tsx}"],
  },
  resolve: {
    // Collapse all react / react-dom references to a single physical copy so
    // hook dispatcher state is shared. Subpath aliases are REQUIRED because
    // @testing-library/react imports `react-dom/client` and JSX-transformed
    // components import `react/jsx-runtime` — Vite treats each subpath specifier
    // independently unless explicitly aliased, producing two React instances.
    dedupe: ["react", "react-dom"],
    alias: [
      // Subpaths FIRST (longest-prefix-first so they match before bare forms).
      { find: /^react-dom\/client$/, replacement: resolve(LIB_REACT_DOM, "client.js") },
      { find: /^react-dom\/test-utils$/, replacement: resolve(LIB_REACT_DOM, "test-utils.js") },
      { find: /^react\/jsx-runtime$/, replacement: resolve(LIB_REACT, "jsx-runtime.js") },
      { find: /^react\/jsx-dev-runtime$/, replacement: resolve(LIB_REACT, "jsx-dev-runtime.js") },
      // Bare forms last.
      { find: /^react$/, replacement: LIB_REACT },
      { find: /^react-dom$/, replacement: LIB_REACT_DOM },
    ],
  },
});
