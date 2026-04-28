import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

/**
 * Vitest config for the seed frontend framework tests.
 *
 * `@noctusai/lib` and its sub-paths are resolved via alias (not npm) because
 * the lib lives at `seed/frontend/lib/` and is consumed the same way by every
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
        replacement: resolve(__dirname, "../lib/src/query-client.ts"),
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
        replacement: resolve(__dirname, "../lib/src/index.ts"),
      },
      { find: /^react$/, replacement: resolve(__dirname, "node_modules/react") },
      { find: /^react-dom$/, replacement: resolve(__dirname, "node_modules/react-dom") },
      { find: /^react-router-dom$/, replacement: resolve(__dirname, "node_modules/react-router-dom") },
    ],
  },
});
