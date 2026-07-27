/**
 * Shared Vite configuration factory for NoctusAI products.
 *
 * Products call createViteConfig() instead of manually wiring aliases.
 * The factory handles:
 *   - Seed lib + framework alias resolution
 *   - Framework dependency deduplication
 *   - envDir → repo root (single .env for all frontends)
 *   - VITE_BACKEND_API_URL injection from port config
 *
 * Usage:
 *   import { createViteConfig } from "../../../seed/framework/frontend/vite.config.factory";
 *   export default createViteConfig({ port: 8120, backendPort: 8006 });
 */
import fs from "fs";
import path from "path";
import react from "@vitejs/plugin-react-swc";
import type { UserConfig } from "vite";

interface ViteConfigOptions {
  /** Frontend dev server port */
  port: number;
  /**
   * Backend API port — used only in two-port/native dev (when
   * `VITE_SAME_ORIGIN=1` is NOT set). Default: derived from the
   * `start.sh PRODUCTS` registry by matching the frontend `port`.
   * If unset AND the port is not in the registry, the factory throws
   * (loud build failure) — see `resolveBackendPort` below.
   */
  backendPort?: number;
  /**
   * Database schema name — injected as `VITE_PRODUCT_SCHEMA` for the
   * seed's `createProductSupabase` to consume. Default: `"public"`
   * (Postgres' canonical default). Products with a non-public schema
   * pass it explicitly.
   */
  schema?: string;
  /** Additional Vite plugins */
  plugins?: any[];
  /** Custom extend function for advanced configs (ERP PWA, etc.) */
  extend?: (config: UserConfig) => UserConfig;
}

/**
 * Resolve paths from a product's frontend directory.
 */
function resolveFromProductDir(productDir: string) {
  const grandparent = path.basename(path.resolve(productDir, "../.."));
  const isProduct = grandparent === "products";
  const repoRoot = isProduct
    ? path.resolve(productDir, "../../..")
    : path.resolve(productDir, "../..");
  const seedLib = path.resolve(repoRoot, "seed/lib/frontend/src");
  const seedFramework = path.resolve(repoRoot, "seed/framework/frontend/src");
  const nodeModules = path.resolve(productDir, "node_modules");

  return { repoRoot, seedLib, seedFramework, nodeModules };
}

/**
 * Packages imported by the seed FRAMEWORK (`@noctusai/seed`) that need to
 * resolve from the product's node_modules. Listed here ONCE — never in
 * products.
 *
 * This hand-curated list is the FLOOR, not the whole requirement set: seed
 * ORGAN peer deps are derived at config time by
 * `deriveOrganTransitiveDeps` and unioned in (see `resolveFrameworkDeps`).
 * Mirrors the same two-part shape as the Python audit tool
 * `mcp/noctusai/tools/noctus/dev/check_framework_deps.py` — keep the two in
 * step.
 */
const FRAMEWORK_DEPS = [
  "react",
  "react-dom",
  "react-router-dom",
  "@tanstack/react-query",
  "zustand",
  "sonner",
  "lucide-react",
  "@radix-ui/react-tooltip",
  "@radix-ui/react-hover-card",
  "@radix-ui/react-collapsible",
  "@supabase/supabase-js",
  "clsx",
  "tailwind-merge",
];

/**
 * Specifiers that are NOT installable npm packages: relative paths, the
 * product's own `@/...` source alias, and the seed's self-referencing
 * `@noctusai/...` aliases.
 */
const LOCAL_SPECIFIER_PREFIXES = [".", "@/", "@noctusai/"];

/** `@scope/name/sub/path` → `@scope/name`; `name/sub/path` → `name`. */
function packageNameFromSpecifier(spec: string): string | null {
  if (LOCAL_SPECIFIER_PREFIXES.some((p) => spec.startsWith(p))) {
    return null;
  }
  const parts = spec.split("/");
  if (spec.startsWith("@")) {
    return parts.length >= 2 ? `${parts[0]}/${parts[1]}` : null;
  }
  return parts[0] || null;
}

/** Best-effort `/* *\/` + `//` comment stripper — run BEFORE import matching
 * so prose containing the word "import" inside a JSDoc block can't act as a
 * false anchor for the non-greedy `from "spec"` match. */
function stripComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/\/\/[^\n]*/g, "");
}

function walkSourceFiles(dir: string, acc: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walkSourceFiles(full, acc);
    } else if (/\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name)) {
      acc.push(full);
    }
  }
  return acc;
}

/**
 * Statically derive the external packages `@noctusai/lib` ORGANS import.
 *
 * `FRAMEWORK_DEPS` is a hand-curated literal, and hand-maintained lists
 * drift (`KB § PATTERNS/devops/product-lockfile-and-slug-drift.md`). It
 * drifted exactly once already: the `KanbanBoard` organ brought
 * `@dnd-kit/core` + `/sortable` + `/utilities`, nobody edited the list, and
 * the organ's copy of dnd-kit was therefore NOT deduped against the
 * product's — two `DndContext` module instances, so a consumer's drag
 * silently no-ops (the provider the card's `useDraggable` reads is not the
 * one the board rendered). The Python audit tool grew the same derivation on
 * 2026-07-20 for the package.json-parity leg; this is its build-time twin
 * for the `resolve.dedupe` / `optimizeDeps` leg.
 *
 * Scope, honestly stated: only `seed/lib/frontend/src` (`@noctusai/lib`) is
 * scanned. `seed/framework/frontend/src` (`@noctusai/seed`) is NOT — its
 * deps remain covered by the hand-curated floor above. That is the named
 * manual remainder.
 *
 * Excludes `*.test.ts*` (test-only deps never reach a product build) and
 * whole-declaration `import type` / `export type` (erased before bundling).
 * Best-effort regex scan, not a TS parser: it does not follow dynamic
 * `import()`. A false negative falls back to the `FRAMEWORK_DEPS` floor —
 * it cannot under-report below it.
 */
function deriveOrganTransitiveDeps(seedLibDir: string): string[] {
  if (!fs.existsSync(seedLibDir)) {
    return [];
  }
  const found = new Set<string>();
  // Captures an optional leading `type` keyword + the module specifier.
  // `[^;]*?` is non-greedy and spans newlines so multi-line named imports
  // match too.
  const importRe = /\b(?:import|export)\s+(type\s+)?[^;]*?\bfrom\s+['"]([^'"]+)['"]/g;

  for (const file of walkSourceFiles(seedLibDir)) {
    const text = stripComments(fs.readFileSync(file, "utf-8"));
    let match: RegExpExecArray | null;
    importRe.lastIndex = 0;
    while ((match = importRe.exec(text)) !== null) {
      if (match[1]) continue; // `import type ...` — erased at build time
      const pkg = packageNameFromSpecifier(match[2]);
      if (pkg) found.add(pkg);
    }
  }
  return [...found].sort();
}

/** The hand-curated framework floor UNIONed with derived organ peer deps. */
function resolveFrameworkDeps(seedLib: string): string[] {
  return [...new Set([...FRAMEWORK_DEPS, ...deriveOrganTransitiveDeps(seedLib)])];
}

/**
 * Parse `start.sh PRODUCTS` registry → `frontend_port → backend_port` map.
 *
 * `start.sh` carries the SINGLE source of truth for product → port
 * mapping (under `# BEGIN_PRODUCTS_REGISTRY` / `# END_PRODUCTS_REGISTRY`
 * sentinels). Both the Python seed-lib (`noctusai_lib.config.cors_registry.
 * parse_products_registry`) AND this TS factory parse the same block —
 * registry drift is impossible. Each entry: `slug:Display Name:backend_port:frontend_port`.
 *
 * Per `KB § PATTERNS/seed-canonical-defaults.md` (N=3 2026-05-20):
 * deriving from the registry replaces the prior hand-maintained
 * `PRODUCT_MAP` literal, which silently misrouted any product whose port
 * wasn't in it. Failures here are LOUD (throw) so adding a product
 * without registering it can't ship.
 */
function parseProductsRegistry(repoRoot: string): Record<number, number> {
  const startSh = path.join(repoRoot, "start.sh");
  if (!fs.existsSync(startSh)) {
    return {};
  }
  const text = fs.readFileSync(startSh, "utf-8");
  const beginIdx = text.indexOf("# BEGIN_PRODUCTS_REGISTRY");
  const endIdx = text.indexOf("# END_PRODUCTS_REGISTRY");
  if (beginIdx === -1 || endIdx === -1 || endIdx < beginIdx) {
    return {};
  }
  const block = text.slice(beginIdx, endIdx);
  // Match `"slug:Display:backend_port:frontend_port"` rows. Mirrors
  // the regex shape used by the Python parser in cors_registry.py.
  const entryRe = /"\s*[a-z0-9][a-z0-9-]*\s*:\s*[^:"]*?\s*:\s*(\d+)\s*:\s*(\d+)\s*"/g;
  const out: Record<number, number> = {};
  let match: RegExpExecArray | null;
  while ((match = entryRe.exec(block)) !== null) {
    const backendPort = parseInt(match[1], 10);
    const frontendPort = parseInt(match[2], 10);
    if (!Number.isNaN(backendPort) && !Number.isNaN(frontendPort)) {
      out[frontendPort] = backendPort;
    }
  }
  return out;
}

/**
 * Resolve the backend port for a given frontend `port`.
 *
 * Order: explicit `backendPort` option → registry derivation → THROW.
 * Throwing on unmapped is deliberate: the loud build failure forces
 * the operator to register the product in `start.sh PRODUCTS` (the
 * single source of truth) instead of silently misrouting (`|| 8000`
 * was core's backend port — every unmapped product silently pointed
 * at core, causing opaque CORS toasts the dashboard can't explain).
 */
function resolveBackendPort(
  port: number,
  explicit: number | undefined,
  registry: Record<number, number>,
): number {
  if (explicit !== undefined) {
    return explicit;
  }
  const fromRegistry = registry[port];
  if (fromRegistry !== undefined) {
    return fromRegistry;
  }
  throw new Error(
    `vite.config.factory: frontend port ${port} is not in the start.sh ` +
    `PRODUCTS registry. Either register the product (single source of ` +
    `truth: start.sh # BEGIN_PRODUCTS_REGISTRY block) or pass ` +
    `\`backendPort\` explicitly to createViteConfig. ` +
    `See KB § PATTERNS/seed-canonical-defaults.md — the prior \`|| 8000\` ` +
    `fallback silently misrouted every unmapped product at core.`,
  );
}

export function createViteConfig(options: ViteConfigOptions): UserConfig {
  const { port, backendPort, schema, plugins = [], extend } = options;

  const productDir = process.cwd();
  const { repoRoot, seedLib, seedFramework, nodeModules } = resolveFromProductDir(productDir);

  // Framework floor + organ peer deps derived from the seed lib source.
  // Computed once per config load (the factory already reads the filesystem
  // at this point — see parseProductsRegistry).
  const frameworkDeps = resolveFrameworkDeps(seedLib);

  // Watch mode (the dev `runtime-watch` container runs `vite build --watch`).
  // In watch mode we must NOT empty dist/ before each rebuild: emptying creates
  // a window where dist/index.html is absent, and if the watcher dies mid-pass
  // (crash/transient) it leaves dist EMPTY for the container's lifetime →
  // permanent "SPA bundle not yet built" 503. With emptyOutDir:false the rebuild
  // overwrites files in place, so the last good bundle is always served. One-shot
  // + prod builds keep emptyOutDir:true (clean build). See seed/docker/local-watch.sh.
  const isWatch = process.argv.includes("--watch");

  // Schema injection: explicit factory option → `"public"` (Postgres'
  // architectural canonical default; products with a non-public schema
  // pass it explicitly). NOT keyed by port — port→schema coupling was
  // a per-product literal that drifted as products were added.
  const resolvedSchema = schema ?? "public";

  // Single-container mode (project: containerization-single-container).
  // When `VITE_SAME_ORIGIN=1` is set (every product Dockerfile sets it
  // in both `frontend-build` and `runtime-watch` stages), the SPA is
  // served by uvicorn on the SAME origin as the API, so the API base
  // must be the *runtime* origin (correct for localhost, for
  // *.trycloudflare.com tunnels, and for any deploy host). We inject it
  // as the RAW expression `window.location.origin` (NOT JSON.stringify)
  // so every literal `import.meta.env.VITE_BACKEND_API_URL` in product +
  // seed code is define-rewritten to it with zero per-file changes.
  //
  // Backend port resolution only runs in the two-port/native dev path
  // (when `VITE_SAME_ORIGIN` is NOT set). Throwing on unmapped happens
  // ONLY there — single-container builds never need the port lookup.
  const sameOrigin = process.env.VITE_SAME_ORIGIN === "1";
  let backendApiUrlDefine: string;
  if (sameOrigin) {
    backendApiUrlDefine = "window.location.origin";
  } else {
    const registry = parseProductsRegistry(repoRoot);
    const resolvedBackendPort = resolveBackendPort(port, backendPort, registry);
    backendApiUrlDefine = JSON.stringify(`http://localhost:${resolvedBackendPort}`);
  }

  const config: UserConfig = {
    server: {
      host: "0.0.0.0",
      port,
    },
    plugins: [react(), ...plugins],

    // Read .env from repo root — single source of truth for all frontends.
    // Shared vars (VITE_SUPABASE_URL, VITE_SUPABASE_PUBLISHABLE_KEY, VITE_CORE_URL)
    // live in root .env. Product-specific vars are injected below via define.
    envDir: repoRoot,

    // Inject product-specific env vars that differ per product.
    // These override anything in .env for this specific product.
    define: {
      "import.meta.env.VITE_BACKEND_API_URL": backendApiUrlDefine,
      "import.meta.env.VITE_PRODUCT_SCHEMA": JSON.stringify(resolvedSchema),
    },

    build: {
      // Disable compressed-size reporting. The post-bundle "computing gzip
      // size" step holds every emitted chunk in memory to gzip it for the
      // build summary — a pure dev-report with ZERO runtime impact. On the
      // heaviest frontend (erp-imobiliario: ~3729 modules) this spike OOM-
      // killed (exit 137) the in-container build on the small dev VM (~3.9 GB),
      // even building solo. Vite's own docs recommend disabling it for large
      // projects. Seed-canonical so every product's in-container build inherits
      // the headroom. See KB § PATTERNS/devops/containerization.md.
      reportCompressedSize: false,
      // Never empty dist on a --watch rebuild (see isWatch note above) — a dead
      // watcher must not be able to leave the SPA bundle absent. One-shot/prod
      // builds still get a clean dist.
      emptyOutDir: !isWatch,
    },

    resolve: {
      alias: {
        "@": path.resolve(productDir, "./src"),
        "@noctusai/lib": seedLib,
        "@noctusai/seed": seedFramework,
      },
      dedupe: frameworkDeps,
    },
    optimizeDeps: {
      include: frameworkDeps.map((dep) => `@noctusai/lib > ${dep}`),
    },
  };

  if (extend) {
    return extend(config);
  }

  return config;
}
