/**
 * Shared Vitest configuration factory for NoctusAI products.
 *
 * Products call createProductVitestConfig() instead of hand-wiring globals,
 * jsdom, exclude patterns, and seed alias paths. The factory handles:
 *   - Default test environment (jsdom + globals)
 *   - Standard exclude — `e2e/**` keeps Playwright tests out of vitest's
 *     default include glob; `node_modules` + `dist` are obvious.
 *   - Seed lib + framework alias resolution (mirrors `vite.config.factory.ts`).
 *   - `@noctusai/seed/infra` subpath alias so `vi.mock(...)` can stub the
 *     api at the seed boundary in product hook tests.
 *
 * Mirrors the pattern established by `vite.config.factory.ts` —
 * config-time code lives at this literal path because the vitest/vite
 * config files run before any package alias is wired up; subpath imports
 * of `@noctusai/seed/...` would not resolve at config-time.
 *
 * Usage:
 *   // products/<X>/frontend/vitest.config.ts
 *   import { createProductVitestConfig } from "../../../seed/framework/frontend/vitest.config.factory";
 *   export default createProductVitestConfig();
 *
 * With overrides:
 *   export default createProductVitestConfig({
 *     excludeExtra: ["custom-glob/**"],
 *     aliasExtra: { "@my-pkg": path.resolve(__dirname, "./libs/my-pkg") },
 *   });
 */
import path from "path";
import type { UserConfig } from "vitest/config";

export interface ProductVitestConfigOptions {
  /** Extra excludes layered ON TOP of defaults (`node_modules`, `dist`, `e2e/**`). */
  excludeExtra?: string[];
  /** Extra path aliases layered ON TOP of defaults (`@`, `@noctusai/lib`, `@noctusai/seed`, `@noctusai/seed/infra`). */
  aliasExtra?: Record<string, string>;
  /** Test environment override. Defaults to `"jsdom"`. */
  environment?: "jsdom" | "node" | "happy-dom";
  /** Extra setup files layered ON TOP of the default (the shared seed setup
   *  that provisions `localStorage`/`sessionStorage` jsdom omits). */
  setupFilesExtra?: string[];
  /** Last-mile mutation hook for advanced configs. */
  extend?: (config: UserConfig) => UserConfig;
}

/**
 * Resolve repo + seed paths from a product's frontend directory.
 * Mirrors `vite.config.factory.ts::resolveFromProductDir` exactly so the
 * two factories never drift on path math.
 */
function resolveFromProductDir(productDir: string) {
  const grandparent = path.basename(path.resolve(productDir, "../.."));
  const isProduct = grandparent === "products";
  const repoRoot = isProduct
    ? path.resolve(productDir, "../../..")
    : path.resolve(productDir, "../..");
  const seedLib = path.resolve(repoRoot, "seed/lib/frontend/src");
  const seedFramework = path.resolve(repoRoot, "seed/framework/frontend/src");
  const seedInfra = path.resolve(seedFramework, "infra.tsx");
  return { repoRoot, seedLib, seedFramework, seedInfra };
}

export function createProductVitestConfig(
  options: ProductVitestConfigOptions = {}
): UserConfig {
  const {
    excludeExtra = [],
    aliasExtra = {},
    environment = "jsdom",
    setupFilesExtra = [],
    extend,
  } = options;

  const productDir = process.cwd();
  const { repoRoot, seedLib, seedFramework, seedInfra } = resolveFromProductDir(productDir);
  // Shared setup file lives beside this factory (seed/framework/frontend/).
  // Resolved absolutely because config-time code runs before alias wiring.
  const seedSetup = path.resolve(seedFramework, "../vitest.setup.ts");

  const config: UserConfig = {
    // The seed setup file + seed alias targets live OUTSIDE the product root
    // (and in a worktree, vite's workspace-root detection resolves through the
    // symlinked node_modules to the PRIMARY repo). Explicitly allow the repo
    // root so vite can load them regardless of worktree/symlink layout.
    server: {
      fs: { allow: [repoRoot] },
    },
    test: {
      globals: true,
      environment,
      // Seed setup provisions localStorage/sessionStorage that vitest's jsdom
      // env omits — runs before any test module imports (so module-scope
      // persist stores are constructed against real storage).
      setupFiles: [seedSetup, ...setupFilesExtra],
      exclude: [
        "**/node_modules/**",
        "**/dist/**",
        "e2e/**",
        ...excludeExtra,
      ],
    },
    resolve: {
      alias: {
        "@": path.resolve(productDir, "./src"),
        "@noctusai/lib": seedLib,
        "@noctusai/seed": seedFramework,
        // Subpath alias — products' tests typically `vi.mock("@noctusai/seed/infra", ...)`
        // to stub the api at the seed boundary.
        "@noctusai/seed/infra": seedInfra,
        ...aliasExtra,
      },
    },
  };

  return extend ? extend(config) : config;
}
