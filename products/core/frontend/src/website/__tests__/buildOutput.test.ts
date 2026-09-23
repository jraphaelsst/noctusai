/**
 * Build-output acceptance gate (contract §4 — "your acceptance gate").
 * Reads `dist/_site` + `dist/assets`, so it only produces a meaningful
 * verdict AFTER `npm run build` has run. If `dist/_site` is missing, every
 * test in this file is skipped with a clear message rather than failing
 * confusingly on missing files (a fresh checkout with no build yet is not
 * a build defect).
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FE_ROOT = path.resolve(HERE, "../../..");
const SITE_DIR = path.join(FE_ROOT, "dist/_site");
const APP_DIR = path.join(FE_ROOT, "dist");
const BUILT = fs.existsSync(SITE_DIR);

const EXPECTED_ROUTES = [
  "/",
  "/en",
  "/produtos",
  "/en/products",
  "/produtos/social-wiring",
  "/en/products/social-wiring",
  "/produtos/orbity",
  "/en/products/orbity",
  "/produtos/igig",
  "/en/products/igig",
  "/solucoes",
  "/en/solutions",
  "/precos",
  "/en/pricing",
  "/contato",
  "/en/contact",
  "/lista-de-espera",
  "/en/waitlist",
  "/sobre",
  "/en/about",
  "/404",
  "/en/404",
];

function routeFile(routePath: string): string {
  const rel = routePath === "/" ? "" : routePath.replace(/^\//, "");
  return path.join(SITE_DIR, rel, "index.html");
}

describe.skipIf(!BUILT)("build output — dist/_site (contract §4)", () => {
  it("emits every contracted route with a valid file", () => {
    for (const route of EXPECTED_ROUTES) {
      expect(fs.existsSync(routeFile(route)), `missing ${route}`).toBe(true);
    }
  });

  it("every route has exactly one <h1", () => {
    for (const route of EXPECTED_ROUTES) {
      const html = fs.readFileSync(routeFile(route), "utf-8");
      const count = (html.match(/<h1[ >]/g) ?? []).length;
      expect(count, `${route} has ${count} <h1> elements`).toBe(1);
    }
  });

  it("every route carries the __NX_SETTINGS__ placeholder exactly once", () => {
    for (const route of EXPECTED_ROUTES) {
      const html = fs.readFileSync(routeFile(route), "utf-8");
      const count = (html.match(/__NX_SETTINGS__/g) ?? []).length;
      expect(count, `${route} nx-settings placeholder count`).toBe(1);
      expect(html).toContain('<script id="nx-settings" type="application/json">');
    }
  });

  it("every route declares hreflang pt-BR / en / x-default", () => {
    for (const route of EXPECTED_ROUTES) {
      const html = fs.readFileSync(routeFile(route), "utf-8");
      expect(html, `${route} hreflang pt-BR`).toMatch(/hreflang="pt-BR"/);
      expect(html, `${route} hreflang en`).toMatch(/hreflang="en"/);
      expect(html, `${route} hreflang x-default`).toMatch(/hreflang="x-default"/);
    }
  });

  it("every route has a self-canonical link and OG/Twitter meta", () => {
    for (const route of EXPECTED_ROUTES) {
      const html = fs.readFileSync(routeFile(route), "utf-8");
      expect(html).toMatch(/<link rel="canonical" href="https:\/\/noctusai\.com/);
      expect(html).toMatch(/property="og:image"/);
      expect(html).toMatch(/name="twitter:card" content="summary_large_image"/);
    }
  });

  it("the theme no-flash script appears in <head>, once, before any content", () => {
    const html = fs.readFileSync(routeFile("/"), "utf-8");
    const scriptIdx = html.indexOf("nx.theme");
    const headEndIdx = html.indexOf("</head>");
    expect(scriptIdx).toBeGreaterThan(-1);
    expect(scriptIdx).toBeLessThan(headEndIdx);
  });

  it("home wraps every switchable section in the nx:section comment markers", () => {
    const html = fs.readFileSync(routeFile("/"), "utf-8");
    // "trust" is deliberately excluded: it renders (and therefore markers
    // it too) only once at least one trust item is admin-verified — see
    // Home.tsx's empty-state guard (2026-09-23 review). With
    // `content/defaults.ts` shipping zero verified items, the section is
    // genuinely absent from the default build, not a bug.
    for (const key of ["audiences", "products", "custom_builds", "pricing", "faq"]) {
      expect(html, `missing start marker for ${key}`).toContain(`<!--nx:section:${key}-->`);
      expect(html, `missing end marker for ${key}`).toContain(`<!--/nx:section:${key}-->`);
    }
  });

  it("home wraps every curated product chapter in nx:product comment markers", () => {
    const html = fs.readFileSync(routeFile("/"), "utf-8");
    for (const slug of ["social-wiring", "orbity", "igig"]) {
      expect(html, `missing start marker for ${slug}`).toContain(`<!--nx:product:${slug}-->`);
      expect(html, `missing end marker for ${slug}`).toContain(`<!--/nx:product:${slug}-->`);
    }
  });

  it("a product page carries SoftwareApplication + BreadcrumbList JSON-LD", () => {
    const html = fs.readFileSync(routeFile("/produtos/orbity"), "utf-8");
    expect(html).toContain('"@type":"SoftwareApplication"');
    expect(html).toContain('"@type":"BreadcrumbList"');
  });

  it("home carries FAQPage JSON-LD generated from the same FAQ data", () => {
    const html = fs.readFileSync(routeFile("/"), "utf-8");
    expect(html).toContain('"@type":"FAQPage"');
  });

  it("manifest.json is valid and lists every route", () => {
    const manifest = JSON.parse(fs.readFileSync(path.join(SITE_DIR, "manifest.json"), "utf-8"));
    expect(Array.isArray(manifest.routes)).toBe(true);
    expect(manifest.routes.length).toBe(EXPECTED_ROUTES.length);
    expect(typeof manifest.built_at).toBe("string");
    expect(manifest.product_routes).toHaveProperty("orbity");
  });

  it("settings.defaults.json is valid and matches the WebsiteSettings shape", () => {
    const settings = JSON.parse(fs.readFileSync(path.join(SITE_DIR, "settings.defaults.json"), "utf-8"));
    expect(typeof settings.site_enabled).toBe("boolean");
    expect(typeof settings.sections).toBe("object");
    expect(Array.isArray(settings.products)).toBe(true);
    expect(Array.isArray(settings.faq)).toBe(true);
  });

  it("fonts and OG images are present under dist/_site (self-hosted, per-language OG)", () => {
    expect(fs.existsSync(path.join(SITE_DIR, "fonts/inter-latin-400.woff2"))).toBe(true);
    expect(fs.existsSync(path.join(SITE_DIR, "og/home-pt.png"))).toBe(true);
    expect(fs.existsSync(path.join(SITE_DIR, "og/home-en.png"))).toBe(true);
  });

  it("the app bundle's main entry chunk has no WebGLRenderer (three.js isolation)", () => {
    const assetsDir = path.join(APP_DIR, "assets");
    const files = fs.readdirSync(assetsDir).filter((f) => /^index-.*\.js$/.test(f));
    expect(files.length).toBeGreaterThan(0);
    for (const f of files) {
      const content = fs.readFileSync(path.join(assetsDir, f), "utf-8");
      expect(content, `${f} must not import three.js`).not.toContain("WebGLRenderer");
    }
  });
});
