/**
 * Vitest config for `@noctusai/lib` colocated tests.
 *
 * Tests live next to their sources (e.g. `src/components/FakeModeBadge.test.tsx`).
 * The lib package itself does not ship dev-dep test tooling — vitest +
 * @testing-library/* are devDeps of `seed/framework/frontend/`. To run these
 * tests, invoke vitest from this directory using the framework's installed
 * binary; node module resolution will climb into `seed/framework/frontend/node_modules`.
 *
 * Running locally:
 *   cd seed/framework/frontend && npm install   # one-time
 *   cd seed/lib/frontend && ../../framework/frontend/node_modules/.bin/vitest run
 *
 * Future packaging: when seed/lib/frontend gets its own vitest devDep, this
 * config becomes self-contained.
 */
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

const FRAMEWORK_ROOT = resolve(__dirname, "../../framework/frontend");

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: [resolve(__dirname, "tests/setup.ts")],
    include: ["src/**/*.test.{ts,tsx}"],
  },
  resolve: {
    alias: [
      // Pull peer deps from the framework's node_modules where they live.
      { find: /^react$/, replacement: resolve(FRAMEWORK_ROOT, "node_modules/react") },
      { find: /^react-dom$/, replacement: resolve(FRAMEWORK_ROOT, "node_modules/react-dom") },
    ],
  },
});
