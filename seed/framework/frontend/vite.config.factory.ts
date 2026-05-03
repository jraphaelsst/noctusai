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
import path from "path";
import react from "@vitejs/plugin-react-swc";
import type { UserConfig } from "vite";

interface ViteConfigOptions {
  /** Frontend dev server port */
  port: number;
  /** Backend API port — injected as VITE_BACKEND_API_URL (default: port - 114 heuristic, or specify explicitly) */
  backendPort?: number;
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
 * Packages imported by the seed framework and lib that need to resolve
 * from the product's node_modules. Listed here ONCE — never in products.
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
];

/**
 * Product mapping — frontend port → backend port + schema.
 * The factory injects both VITE_BACKEND_API_URL and VITE_PRODUCT_SCHEMA
 * so products don't need any config files beyond vite.config.ts.
 */
const PRODUCT_MAP: Record<number, { backend: number; schema: string }> = {
  5173: { backend: 8000, schema: "public" },       // Core
  8080: { backend: 8001, schema: "erp" },           // ERP
  8090: { backend: 8002, schema: "personal-finance" }, // PF
  8095: { backend: 8003, schema: "therapy" },       // Therapy
  8100: { backend: 8004, schema: "seed" },          // Seed
  8110: { backend: 8005, schema: "daily_life" },    // Daily Life
  8120: { backend: 8006, schema: "mailing" },       // Mailing
};

export function createViteConfig(options: ViteConfigOptions): UserConfig {
  const { port, backendPort, plugins = [], extend } = options;

  const productDir = process.cwd();
  const { repoRoot, seedLib, seedFramework, nodeModules } = resolveFromProductDir(productDir);

  // Resolve from product map
  const productInfo = PRODUCT_MAP[port];
  const resolvedBackendPort = backendPort || productInfo?.backend || 8000;
  const resolvedSchema = productInfo?.schema || "public";

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
      "import.meta.env.VITE_BACKEND_API_URL": JSON.stringify(`http://localhost:${resolvedBackendPort}`),
      "import.meta.env.VITE_PRODUCT_SCHEMA": JSON.stringify(resolvedSchema),
    },

    resolve: {
      alias: {
        "@": path.resolve(productDir, "./src"),
        "@noctusai/lib": seedLib,
        "@noctusai/seed": seedFramework,
      },
      dedupe: FRAMEWORK_DEPS,
    },
    optimizeDeps: {
      include: FRAMEWORK_DEPS.map((dep) => `@noctusai/lib > ${dep}`),
    },
  };

  if (extend) {
    return extend(config);
  }

  return config;
}
