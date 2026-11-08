/**
 * SSR (Node-stage-only) build of `entry-server.tsx` (contract §0 D5 — the
 * runtime image has no Node, so this bundle is consumed ONLY by
 * `scripts/prerender-site.mjs` at build time, never shipped to the runtime
 * container). Separate from `vite.config.site.ts` (the client/browser
 * build): `build.ssr` mode skips asset-URL rewriting and CSS extraction,
 * neither of which a Node-imported render function needs.
 */
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { fileURLToPath } from "url";
import { resolveFrameworkDeps } from "../../../seed/framework/frontend/vite.config.factory";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// The site build consumes the seed landing organs (`@noctusai/lib/marketing`) and the seed
// tokens (`@noctusai/seed/index.css`), so it resolves them exactly like `createViteConfig`
// does for the app build (same aliases, same framework-dep dedupe => ONE React).
const seedLib = path.resolve(__dirname, "../../../seed/lib/frontend/src");
const seedFramework = path.resolve(__dirname, "../../../seed/framework/frontend/src");

export default defineConfig({
  plugins: [react()],
  envDir: path.resolve(__dirname, "../../.."),
  build: {
    ssr: path.resolve(__dirname, "src/website/entry-server.tsx"),
    outDir: "dist/_site-ssr",
    emptyOutDir: true,
    reportCompressedSize: false,
    rollupOptions: {
      output: { format: "es", entryFileNames: "entry-server.mjs" },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@noctusai/lib": seedLib,
      "@noctusai/seed": seedFramework,
    },
    dedupe: resolveFrameworkDeps(seedLib),
  },
});
