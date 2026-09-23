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
import type { ReactNode } from "react";

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
  return (
    <>
      {sectionMarkerStart(sectionKey)}
      {children}
      {sectionMarkerEnd(sectionKey)}
    </>
  );
}

export function MarkedProduct({ slug, children }: { slug: string; children: ReactNode }) {
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
