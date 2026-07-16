import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

/**
 * Vitest config for the seed frontend framework tests.
 *
 * `@noctusai/lib` and its sub-paths are resolved via alias (not npm) because
 * the lib lives at `seed/lib/frontend/` and is consumed the same way by every
 * product's vite build. Aliases are ORDERED LONGEST-PREFIX-FIRST so that
 * `@noctusai/lib/design-system` matches before the bare `@noctusai/lib`.
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
  },
  resolve: {
    // Force vitest to pull peer deps from THIS package's node_modules, not a
    // higher-up copy that node's resolution might find first. Without this
    // the test runner climbs to `/Users/rapha/node_modules/react-router-dom`
    // and hits a UMD bundle that can't find `react` in its relative chain.
    alias: [
      {
        find: "@noctusai/lib/query-client",
        replacement: resolve(__dirname, "../../lib/frontend/src/query-client.ts"),
      },
      // Stub the design-system at the test boundary — the real component set
      // pulls in lucide-react + radix-ui + the full UI deps, which aren't
      // installed in this package. Tests exercise framework logic, not UI.
      {
        find: "@noctusai/lib/design-system",
        replacement: resolve(__dirname, "tests/stubs/design-system.tsx"),
      },
      {
        find: "@noctusai/lib",
        replacement: resolve(__dirname, "../../lib/frontend/src/index.ts"),
      },
      { find: /^react$/, replacement: resolve(__dirname, "node_modules/react") },
      { find: /^react-dom$/, replacement: resolve(__dirname, "node_modules/react-dom") },
      { find: /^react-router-dom$/, replacement: resolve(__dirname, "node_modules/react-router-dom") },
      // `layout.test.tsx` (`sessionAuth`/`supabase` dual-mode) is the first
      // framework test to render `usePageStatus` (lib's `page-status.ts`)
      // under a `QueryClientProvider` constructed IN THE TEST FILE. Without
      // this alias, `page-status.ts`'s bare `@tanstack/react-query` import
      // resolves relative to ITS OWN location (`seed/lib/frontend/src/`) →
      // lib's copy of the package, a SEPARATE module instance from the one
      // the test's `QueryClientProvider` uses → `useContext` sees a
      // mismatched Provider → "Cannot read properties of null (reading
      // 'useContext')". Same class of problem `@noctusai/lib/query-client`'s
      // alias above solves for `createQueryClient` itself; this closes the
      // gap for any REAL lib hook that calls `useQuery`/`useMutation`
      // directly (not just the client-construction helper).
      { find: /^@tanstack\/react-query$/, replacement: resolve(__dirname, "node_modules/@tanstack/react-query") },
    ],
  },
});
