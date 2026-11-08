/**
 * Client build for the public website (contract §4). A SEPARATE Vite entry
 * from `vite.config.ts` (the logged app): different `root` input, different
 * `base` (`/_site/`), different `outDir` (`dist/_site`). Does NOT use
 * `createViteConfig()` — that factory is app-shaped (dev-server port
 * resolution, schema/slug defines). It DOES consume the `@noctusai/lib/marketing` landing organs and
 * the seed design tokens (Tailwind via the product's postcss config); i18n/consent/
 * analytics stay website-local (contract D3).
 *
 * `build.manifest: true` emits `.vite/manifest.json`, which
 * `scripts/prerender-site.mjs` reads to know the real hashed asset URLs for
 * each prerendered page's `<head>`.
 *
 * Invoked by `npm run build:site` (wired in `package.json`), never by the
 * app's own `npm run build`'s first step.
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
  base: "/_site/",
  plugins: [react()],
  publicDir: path.resolve(__dirname, "src/website/public-assets"),
  envDir: path.resolve(__dirname, "../../.."),
  build: {
    outDir: "dist/_site",
    emptyOutDir: true,
    manifest: true,
    reportCompressedSize: false,
    rollupOptions: {
      input: path.resolve(__dirname, "src/website/index-site.html"),
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
