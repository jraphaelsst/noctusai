#!/usr/bin/env node
/**
 * Build-time prerender (contract §0 D5 + §4). Runs AFTER the client build
 * (`vite build --config vite.config.site.ts`, which produces the hashed JS/
 * CSS + the Vite build manifest) and the SSR build (`vite build --config
 * vite.config.site.ssr.ts`, which produces a Node-consumable
 * `entry-server.mjs`). For every route in `lib/routes.ts` (imported via the
 * SSR bundle's re-exports — see `entry-server.tsx`'s bottom section), calls
 * `render(path)`, resolves the NUL-sentinel section/product markers to real
 * HTML comments, wraps the result in a full document with the correct
 * `<head>`, and writes `dist/_site/<route>/index.html`.
 *
 * Also emits the contract's OWN `manifest.json` (route table + product
 * routes, distinct from Vite's `.vite/manifest.json`) and
 * `settings.defaults.json`.
 *
 * Plain Node ESM — no TypeScript loader needed, because every helper it
 * calls is re-exported from the ALREADY-COMPILED `dist/_site-ssr/
 * entry-server.mjs`.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FE_ROOT = path.resolve(__dirname, "..");
const CLIENT_OUT = path.join(FE_ROOT, "dist/_site");
const SSR_OUT = path.join(FE_ROOT, "dist/_site-ssr");

async function main() {
  const ssrEntryPath = path.join(SSR_OUT, "entry-server.mjs");
  if (!fs.existsSync(ssrEntryPath)) {
    throw new Error(`prerender-site: SSR bundle not found at ${ssrEntryPath}. Run the SSR build first.`);
  }
  const manifestPath = path.join(CLIENT_OUT, ".vite/manifest.json");
  if (!fs.existsSync(manifestPath)) {
    throw new Error(`prerender-site: Vite client manifest not found at ${manifestPath}. Run the client build first.`);
  }

  const {
    render,
    ROUTES,
    getPageMeta,
    buildHead,
    resolveMarkersToComments,
    defaultSettings,
    PRODUCT_ORDER,
  } = await import(ssrEntryPath);

  const viteManifest = JSON.parse(fs.readFileSync(manifestPath, "utf-8"));
  const entry = viteManifest["src/website/index-site.html"];
  if (!entry) {
    throw new Error('prerender-site: manifest is missing the "src/website/index-site.html" entry.');
  }
  const assetTags = [
    ...(entry.css ?? []).map((href) => `<link rel="stylesheet" href="/_site/${href}" />`),
    `<script type="module" crossorigin src="/_site/${entry.file}"></script>`,
  ].join("\n    ");

  const sectionKeys = Object.keys(defaultSettings.sections);
  const settingsJson = "__NX_SETTINGS__"; // the BE swaps this for the real public settings at request time
  const builtAt = new Date().toISOString();

  const manifestRoutes = [];
  const productRoutes = {};

  for (const route of ROUTES) {
    for (const [locale, routePath] of [
      ["pt-BR", route.pt],
      ["en", route.en],
    ]) {
      const bodyHtmlRaw = render(routePath);
      const bodyHtml = resolveMarkersToComments(bodyHtmlRaw, sectionKeys, PRODUCT_ORDER);
      const meta = getPageMeta(route.id, locale, route.product);
      const ogImagePath = locale === "en" ? "/_site/og/home-en.png" : "/_site/og/home-pt.png";
      const head = buildHead({ route, locale, path: routePath, meta, assetTags, ogImagePath, settingsJson });
      const htmlLang = locale === "en" ? "en" : "pt-BR";

      const doc = `<!DOCTYPE html>
<html lang="${htmlLang}" data-surface="site">
${head}
<body>
<div id="root">${bodyHtml}</div>
</body>
</html>
`;

      const outDir = path.join(CLIENT_OUT, routePath === "/" ? "." : routePath.replace(/^\//, ""));
      fs.mkdirSync(outDir, { recursive: true });
      fs.writeFileSync(path.join(outDir, "index.html"), doc, "utf-8");

      manifestRoutes.push({
        path: routePath,
        lang: htmlLang,
        file: "index.html",
        alt: locale === "en" ? route.pt : route.en,
        product: route.product ?? null,
      });

      if (route.product) {
        productRoutes[route.product] = productRoutes[route.product] ?? {};
        productRoutes[route.product][locale === "en" ? "en" : "pt"] = routePath;
      }
    }
  }

  fs.writeFileSync(
    path.join(CLIENT_OUT, "manifest.json"),
    JSON.stringify({ routes: manifestRoutes, product_routes: productRoutes, built_at: builtAt }, null, 2),
    "utf-8",
  );
  fs.writeFileSync(
    path.join(CLIENT_OUT, "settings.defaults.json"),
    JSON.stringify(defaultSettings, null, 2),
    "utf-8",
  );

  // The Vite-generated placeholder entry html + its mirrored `src/` tree are
  // build artefacts, not part of the contract's output shape — every real
  // page now lives at `<route>/index.html`.
  const leftoverHtml = path.join(CLIENT_OUT, "src/website/index-site.html");
  if (fs.existsSync(leftoverHtml)) {
    fs.rmSync(path.join(CLIENT_OUT, "src"), { recursive: true, force: true });
  }

  // The SSR bundle is a build-time-only tool. `dist/` is copied whole into
  // the runtime image and served as static files, so leaving it there would
  // publish server-render code at /_site-ssr/*. Remove it once rendering is done.
  fs.rmSync(SSR_OUT, { recursive: true, force: true });

  console.log(`prerender-site: wrote ${manifestRoutes.length} route files to ${CLIENT_OUT}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
