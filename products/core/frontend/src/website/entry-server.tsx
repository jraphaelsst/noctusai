/**
 * Website SSR entry (Node stage only — the runtime image has no Node,
 * contract §0 D5). `render(path)` is the only export: given a path, returns
 * the fully rendered body markup for `#root`. No `window`/`document` at
 * module scope anywhere in this file's import graph (three.js is reached
 * only via a dynamic `import()` from `hero3d/HeroScene.tsx`'s client-only
 * effect, never touched here).
 */
import { StrictMode } from "react";
import { renderToString } from "react-dom/server";
import { StaticRouter } from "react-router";
import { AppRoutes } from "./routes";

export function render(path: string): string {
  return renderToString(
    <StrictMode>
      <StaticRouter location={path}>
        <AppRoutes />
      </StaticRouter>
    </StrictMode>,
  );
}

// Re-exported so `scripts/prerender-site.mjs` (plain Node, no TS loader) can
// import every build-time helper it needs from this ONE compiled bundle
// instead of hand-rolling a second bundling step for `lib/*.ts` + `content/*.ts`.
export { ROUTES } from "./lib/routes";
export { getPageMeta } from "./lib/pageMeta";
export { buildHead } from "./lib/headHtml";
export { resolveMarkersToComments } from "./lib/markers";
export { defaultSettings } from "./content/defaults";
export { PRODUCT_ORDER } from "./content/products";

