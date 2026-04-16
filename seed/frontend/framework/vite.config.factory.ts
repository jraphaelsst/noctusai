/**
 * Shared Vite configuration factory for NoctusAI products.
 *
 * Products call createViteConfig() instead of manually wiring aliases.
 * The factory handles all resolution for seed/lib and seed/framework
 * imports, so products never need to add package aliases when the
 * framework or lib adds new dependencies.
 *
 * Usage in a product's vite.config.ts:
 *
 *   import { createViteConfig } from "../../../seed/frontend/framework/src/vite";
 *   export default createViteConfig({ port: 8120 });
 *
 * For products that need custom config (PWA, plugins, etc.):
 *
 *   import { createViteConfig } from "../../../seed/frontend/framework/src/vite";
 *   export default createViteConfig({
 *     port: 8120,
 *     extend: (config) => {
 *       config.plugins.push(VitePWA({ ... }));
 *       return config;
 *     },
 *   });
 */
import path from "path";
import react from "@vitejs/plugin-react-swc";
import type { UserConfig } from "vite";

interface ViteConfigOptions {
  /** Dev server port */
  port: number;
  /** Additional Vite plugins */
  plugins?: any[];
  /** Custom extend function for advanced configs (ERP PWA, etc.) */
  extend?: (config: UserConfig) => UserConfig;
}

/**
 * Resolve the paths from a product's frontend directory.
 *
 * Works for both products/<name>/frontend (3 levels up to repo root)
 * and core/frontend (2 levels up to repo root).
 */
function resolveFromProductDir(productDir: string) {
  // Detect if we're in core/frontend (2 levels) or products/<name>/frontend (3 levels)
  const repoRoot = path.resolve(productDir, "../../.."); // default: products/<name>/frontend → repo root
  const seedLib = path.resolve(repoRoot, "seed/frontend/lib/src");
  const seedFramework = path.resolve(repoRoot, "seed/frontend/framework/src");
  const nodeModules = path.resolve(productDir, "node_modules");

  return { repoRoot, seedLib, seedFramework, nodeModules };
}

/**
 * Packages imported by the seed framework and lib that need to resolve
 * from the product's node_modules. Listed here ONCE — never in products.
 *
 * When the framework adds a new dependency, add it here.
 * All products get the fix automatically.
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

export function createViteConfig(options: ViteConfigOptions): UserConfig {
  const { port, plugins = [], extend } = options;

  // __dirname won't work here since this file is imported by the product.
  // The product's vite.config.ts should pass __dirname or we detect from cwd.
  // For now, we resolve relative to process.cwd() which Vite sets to the project root.
  const productDir = process.cwd();
  const { seedLib, seedFramework, nodeModules } = resolveFromProductDir(productDir);

  // Build package aliases — resolve ALL framework deps from the product's node_modules
  const packageAliases: Record<string, string> = {};
  for (const dep of FRAMEWORK_DEPS) {
    packageAliases[dep] = path.resolve(nodeModules, dep);
  }

  const config: UserConfig = {
    server: {
      host: "0.0.0.0",
      port,
    },
    plugins: [react(), ...plugins],
    resolve: {
      alias: {
        "@": path.resolve(productDir, "./src"),
        "@noctusai/lib": seedLib,
        "@noctusai/seed": seedFramework,
        ...packageAliases,
      },
      dedupe: FRAMEWORK_DEPS,
    },
  };

  if (extend) {
    return extend(config);
  }

  return config;
}
