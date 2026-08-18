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
 *   - Test-env stand-ins for the required `VITE_SUPABASE_*` build vars, so a
 *     test that merely reaches the infra module transitively does not die at
 *     import (see `test.env` below).
 *   - **React single-instance guard** (see below) so a product test can RENDER
 *     a seed organ, not just call its hooks.
 *
 * --- Dual-React guard ---
 * A product's `react-dom` lives in `products/<slug>/frontend/node_modules`,
 * while a seed ORGAN's `react` resolves from `seed/lib/frontend/node_modules`.
 * Two physical React copies ⇒ the renderer's dispatcher comes from one and the
 * organ's hooks from the other ⇒ `Cannot read properties of null (reading
 * 'useState')` the moment a product test renders anything out of
 * `@noctusai/lib/components`.
 *
 * `vite.config.factory.ts` never had this problem: its `resolve.dedupe` list
 * already carries `react`/`react-dom`, so the BUILD collapses them. This
 * factory claimed to mirror it but omitted the dedupe — a silent drift that
 * only surfaced when a product first tried to render an organ under vitest
 * (orbity `Funil.test.tsx`, 2026-07-28). Same two root causes, same fix as
 * `seed/lib/frontend/vitest.config.ts` solved for the lib's own colocated
 * tests on 2026-05-29: `resolve.dedupe` PLUS explicit SUBPATH aliases —
 * `@testing-library/react` imports `react-dom/client` and JSX-transformed
 * components import `react/jsx-runtime`, and Vite treats every subpath
 * specifier as an independent module entry unless it is aliased by name.
 *
 * Everything collapses onto the PRODUCT's copy (the one `react-dom` already
 * renders with). Alias order is longest-prefix-first: subpaths before bare.
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
import fs from "fs";
import path from "path";
import type { UserConfig } from "vitest/config";
import { resolveFrameworkDeps } from "./vite.config.factory";

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

/**
 * Stand-in values for the BUILD-time vars the seed refuses to start without.
 * Applied to `process.env` at config-load time so Vite's `loadEnv` folds them
 * into `import.meta.env` for every transformed module. See the `test.env`
 * comment inside the factory for why the config key alone does not suffice.
 */
const TEST_VITE_ENV: Record<string, string> = {
  VITE_SUPABASE_URL: "http://localhost:54321",
  VITE_SUPABASE_PUBLISHABLE_KEY: "test-anon-key-not-a-secret",
};

for (const [key, value] of Object.entries(TEST_VITE_ENV)) {
  // Never clobber a real value — a product or CI job may set its own.
  if (!process.env[key]) process.env[key] = value;
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
  // The product's own React copy — the one its `react-dom` renders with, and
  // therefore the one every seed organ must be collapsed onto (dual-React
  // guard in the header docstring).
  const productReact = path.resolve(productDir, "node_modules/react");
  const productReactDom = path.resolve(productDir, "node_modules/react-dom");
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
      // Deterministic stand-ins for the two BUILD-time vars the seed's
      // `supabase.ts` refuses to start without. Vite inlines `VITE_*` at
      // `vite build`; under vitest nothing inlines them, so ANY test whose
      // import chain reaches `@noctusai/seed/infra` — even transitively,
      // even when the test never touches Supabase — dies at module scope
      // with the build-args help text.
      //
      // Products had been routing around this by mocking the infra module in
      // each affected test file (30 files across the fleet). That works until
      // a component quietly gains an import that reaches infra: the test file
      // that never needed the mock starts failing for a reason unrelated to
      // what it asserts. Exactly that happened on 2026-08-18 — adding a
      // webhook card to social-wiring's Configuracao page took 14 unrelated,
      // long-passing tests red in CI.
      //
      // Values are obvious non-secrets and are never dialled: the client is
      // constructed but every test either mocks the api boundary or renders
      // against fixtures. A product needing different values passes them via
      // `extend`. This does NOT weaken the production guard — the real check
      // runs in `main.tsx` before render, at build time, where it belongs.
      //
      // Declared BOTH here and on `process.env` at config-load time (see
      // `TEST_VITE_ENV` above the factory). `test.env` alone is not enough:
      // in Vitest 4 it populates `process.env` but NOT `import.meta.env`
      // (measured 2026-08-18), and the seed reads through a DYNAMIC key
      // (`import.meta.env?.[viteKey]`), which vite's `define` cannot rewrite
      // either. Vite's `loadEnv` DOES fold prefix-matching `process.env`
      // keys into `import.meta.env`, so setting them before the config is
      // returned is what actually reaches the seed.
      env: { ...TEST_VITE_ENV },
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
      // Collapse every framework / organ peer dep onto ONE physical copy,
      // resolved from the product root. Same list the BUILD dedupes — reused
      // from `vite.config.factory.ts` rather than restated, so an organ that
      // brings a new peer dep is covered in both places at once.
      //
      // react/react-dom are the hook-dispatcher case; the rest matter for the
      // same reason `@dnd-kit` did at build time — a second `DndContext`
      // module is a second provider, and the card's `useDraggable` then reads
      // a context the board never wrote to.
      //
      // FILTERED to what the product actually installed. `dedupe` means
      // "resolve this bare specifier from the project root", so listing a
      // package the product does NOT have turns a previously-working fallback
      // (resolve it from the seed lib's node_modules) into a hard resolution
      // error — personal-finance has no `@dnd-kit/*` and its whole suite went
      // red on the unfiltered list. A dep the product doesn't own has no
      // second copy to collapse, so filtering costs nothing.
      dedupe: resolveFrameworkDeps(seedLib).filter((dep) =>
        fs.existsSync(path.join(productDir, "node_modules", dep))
      ),
      // Object form, deliberately: `extend` callers spread this as a record
      // (`{...peerAlias, ...config.resolve.alias}` — products/dev-team), and
      // spreading an ARRAY into an object silently yields `{0:…,1:…}`, which
      // drops every alias including `@`. Key ORDER still matters — Vite tries
      // entries in insertion order and matches on `id === key || id.startsWith(key + "/")`,
      // so every subpath key must precede its bare prefix.
      alias: {
        // React subpaths, explicitly. `dedupe` above handles BARE specifiers;
        // a subpath like `react-dom/client` (what `@testing-library/react`
        // imports) or `react/jsx-runtime` (what the JSX transform emits) is a
        // separate module entry that dedupe does NOT collapse — the exact hole
        // `seed/lib/frontend/vitest.config.ts` documented on 2026-05-29.
        "react-dom/client": path.join(productReactDom, "client.js"),
        "react-dom/test-utils": path.join(productReactDom, "test-utils.js"),
        "react/jsx-runtime": path.join(productReact, "jsx-runtime.js"),
        "react/jsx-dev-runtime": path.join(productReact, "jsx-dev-runtime.js"),

        "@": path.resolve(productDir, "./src"),
        "@noctusai/lib": seedLib,
        // Subpath alias — products' tests typically `vi.mock("@noctusai/seed/infra", ...)`
        // to stub the api at the seed boundary. Before its bare prefix.
        "@noctusai/seed/infra": seedInfra,
        "@noctusai/seed": seedFramework,
        ...aliasExtra,
      },
    },
  };

  return extend ? extend(config) : config;
}
