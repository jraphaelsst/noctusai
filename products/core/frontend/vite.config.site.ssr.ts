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

const __dirname = path.dirname(fileURLToPath(import.meta.url));

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
    },
  },
});
