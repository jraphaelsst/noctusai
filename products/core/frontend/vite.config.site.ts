/**
 * Client build for the public website (contract §4). A SEPARATE Vite entry
 * from `vite.config.ts` (the logged app): different `root` input, different
 * `base` (`/_site/`), different `outDir` (`dist/_site`). Does NOT use
 * `createViteConfig()` — that factory is app-shaped (dev-server port
 * resolution, seed-organ framework-dep dedupe) and the website consumes
 * neither `@noctusai/lib` organs nor `@noctusai/seed` (contract D3: i18n/
 * consent/analytics are website-local).
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

const __dirname = path.dirname(fileURLToPath(import.meta.url));

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
    },
  },
});
