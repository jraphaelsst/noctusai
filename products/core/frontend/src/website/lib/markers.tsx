/**
 * Section/product markers (contract §4): every prerendered page must carry
 * literal `<!--nx:section:KEY-->…<!--/nx:section:KEY-->` and
 * `<!--nx:product:SLUG-->…<!--/nx:product:SLUG-->` HTML comments so the core
 * BE can strip admin-hidden sections/products by string search at request
 * time (D5: build-time prerender + request-time post-processing, no live
 * SSR).
 *
 * React has no JSX syntax for a literal comment NODE (only element/text/
 * fragment children), so `MarkedSection`/`MarkedProduct` emit a NUL-bracketed
 * sentinel as ordinary escaped text — safe because `\u0000` never appears in
 * real rendered copy — and `resolveMarkersToComments` (run once, in
 * `scripts/prerender-site.mjs`, AFTER `renderToString`) swaps every sentinel
 * for the real HTML comment via plain string `split/join` (no HTML parsing,
 * no regex-vs-nested-tag risk).
 */
import { createContext, useContext, type ReactNode } from "react";

/**
 * True ONLY inside `entry-server.tsx`'s `render()` (the build-time prerender
 * pass). Default `false` so `entry-client.tsx`'s hydration — and every
 * subsequent client render — never emits the sentinel at all.
 *
 * This split is required, not cosmetic: the prerender script converts the
 * sentinel to a real HTML COMMENT in the string it writes to disk, so the
 * comment (not a text node) is what the browser's DOM actually contains at
 * that position. If the client tree ALSO rendered the sentinel as a text
 * node, `hydrateRoot` would expect a TEXT node there and find a COMMENT
 * node instead — a type mismatch, not a tolerable "extra node" — which is
 * exactly React hydration error #418/#423 (reproduced 2026-09-23 via a
 * local dev-mode build + Playwright). With the sentinel absent from the
 * client tree, React's hydration walker simply skips the pre-existing
 * comment nodes it has no corresponding vdom entry for, and matches the
 * `<section>` element that follows normally.
 */
export const PrerenderModeContext = createContext(false);
function usePrerenderMode(): boolean {
  return useContext(PrerenderModeContext);
}

function sentinel(kind: "SECTION" | "PRODUCT", edge: "START" | "END", key: string): string {
  return `\u0000NX_${kind}_${edge}:${key}\u0000`;
}

export function sectionMarkerStart(key: string): string {
  return sentinel("SECTION", "START", key);
}
export function sectionMarkerEnd(key: string): string {
  return sentinel("SECTION", "END", key);
}
export function productMarkerStart(slug: string): string {
  return sentinel("PRODUCT", "START", slug);
}
export function productMarkerEnd(slug: string): string {
  return sentinel("PRODUCT", "END", slug);
}

export function MarkedSection({ sectionKey, children }: { sectionKey: string; children: ReactNode }) {
  if (!usePrerenderMode()) return <>{children}</>;
  return (
    <>
      {sectionMarkerStart(sectionKey)}
      {children}
      {sectionMarkerEnd(sectionKey)}
    </>
  );
}

export function MarkedProduct({ slug, children }: { slug: string; children: ReactNode }) {
  if (!usePrerenderMode()) return <>{children}</>;
  return (
    <>
      {productMarkerStart(slug)}
      {children}
      {productMarkerEnd(slug)}
    </>
  );
}

export function resolveMarkersToComments(
  html: string,
  sectionKeys: string[],
  productSlugs: string[],
): string {
  let out = html;
  for (const key of sectionKeys) {
    out = out.split(sectionMarkerStart(key)).join(`<!--nx:section:${key}-->`);
    out = out.split(sectionMarkerEnd(key)).join(`<!--/nx:section:${key}-->`);
  }
  for (const slug of productSlugs) {
    out = out.split(productMarkerStart(slug)).join(`<!--nx:product:${slug}-->`);
    out = out.split(productMarkerEnd(slug)).join(`<!--/nx:product:${slug}-->`);
  }
  return out;
}
