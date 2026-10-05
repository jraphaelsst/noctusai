import { describe, it, expect } from "vitest";

import {
  buildPreviewDocument,
  buildPreviewVars,
  bundleErrors,
  isSafeCssValue,
  previewHeight,
  readDesignSystemFiles,
  resolveColor,
  resolveColors,
  scalesOf,
  type BrandingTokens,
} from "./branding";

const TOKENS: BrandingTokens = {
  name: "Mini",
  color: {
    themes: [
      { id: "light", name: "Light" },
      { id: "dark", name: "Dark" },
    ],
    tokens: [
      { name: "ground", value: "#f4f4f2", usage: "paper" },
      { name: "ink", value: "#111111" },
      { name: "surface", value: { light: "{ground}", dark: "{ink}" }, usage: "bg" },
      { name: "loop-a", value: "{loop-b}" },
      { name: "loop-b", value: "{loop-a}" },
      { name: "evil", value: "red; } body{background:url(x)" },
    ],
  },
  type: { fonts: [], families: { ui: "system-ui, sans-serif", bad: "x; y" }, groups: [] },
  radius: { tokens: [{ name: "radius-pill", value: "999px" }] },
  spacing: { tokens: [{ name: "space-4", value: "4px" }] },
};

describe("colour resolution", () => {
  it("resolves refs per theme", () => {
    expect(resolveColor(TOKENS, "surface", "light")).toBe("#f4f4f2");
    expect(resolveColor(TOKENS, "surface", "dark")).toBe("#111111");
  });
  it("never loops forever and never emits an unsafe value", () => {
    expect(resolveColor(TOKENS, "loop-a", "light")).toBeNull();
    expect(resolveColor(TOKENS, "evil", "light")).toBeNull();
    expect(resolveColor(TOKENS, "missing", "light")).toBeNull();
  });
  it("marks role tokens as derived", () => {
    const byName = Object.fromEntries(resolveColors(TOKENS, "light").map((c) => [c.name, c]));
    expect(byName.surface.derived).toBe(true);
    expect(byName.ground.derived).toBe(false);
  });
});

describe("isSafeCssValue", () => {
  it.each(["#fff", "rgba(0, 0, 0, 0.08)", '"Cormorant Garamond", Georgia, serif', "999px"])("accepts %s", (v) =>
    expect(isSafeCssValue(v)).toBe(true),
  );
  it.each(["a;b", "a}b", "</style>", "url(http://x)", "expression(1)", "javascript:1", "", "x".repeat(201)])(
    "rejects %s",
    (v) => expect(isSafeCssValue(v)).toBe(false),
  );
});

describe("preview document", () => {
  it("exposes tokens as css vars and drops unsafe ones", () => {
    const vars = buildPreviewVars(TOKENS, "dark");
    expect(vars["--surface"]).toBe("#111111");
    expect(vars["--font-ui"]).toBe("system-ui, sans-serif");
    expect(vars["--radius-pill"]).toBe("999px");
    expect(vars["--space-4"]).toBe("4px");
    expect(vars["--evil"]).toBeUndefined();
    expect(vars["--font-bad"]).toBeUndefined();
  });
  it("locks the document down with a CSP and puts html in the body only", () => {
    const doc = buildPreviewDocument({ html: "<div>x</div>", tokens: TOKENS, themeId: "light" });
    expect(doc).toContain("Content-Security-Policy");
    expect(doc).toContain("default-src 'none'");
    expect(doc).not.toMatch(/script-src|connect-src/);
    expect(doc).toContain("img-src data:");
    expect(doc.endsWith("<div>x</div></body></html>")).toBe(true);
  });
  it("only emits font-face for well-formed https urls and allows that origin", () => {
    const doc = buildPreviewDocument({
      html: "",
      tokens: TOKENS,
      themeId: "light",
      fonts: [
        { family: "NX Sans", weight: "400", url: "https://cdn.example/f.woff2?token=abc" },
        { family: "Bad;Family", weight: "400", url: "https://cdn.example/g.woff2" },
        { family: "Ok", weight: "400", url: "http://insecure/h.woff2" },
        { family: "Ok2", weight: "400", url: 'https://x/"onerror' },
      ],
    });
    expect(doc).toContain('font-family:"NX Sans"');
    expect(doc).not.toContain("Bad;Family");
    expect(doc).not.toContain("insecure");
    expect(doc).not.toContain("onerror");
    expect(doc).toContain("font-src https://fonts.gstatic.com https://cdn.example data:");
  });
  it("reads the card height hint", () => {
    expect(previewHeight("<!-- @dsCard group=\"A\" height=110 subtitle=\"x\" -->")).toBe(110);
    expect(previewHeight("<div/>")).toBe(220);
  });
});

describe("scales and errors", () => {
  it("lists non-base scales", () => {
    expect(scalesOf(TOKENS).map((s) => s.key)).toEqual(["radius", "spacing"]);
  });
  it("reads every problem of a rejected bundle", () => {
    expect(bundleErrors({ body: { errors: ["a", "b", 3] } })).toEqual(["a", "b"]);
    expect(bundleErrors(new Error("x"))).toEqual([]);
  });
});

describe("readDesignSystemFiles", () => {
  it("keeps the picked relative paths, base64-encodes and skips .DS_Store", async () => {
    const a = new File(["{}"], "tokens.json");
    Object.defineProperty(a, "webkitRelativePath", { value: "ds/tokens.json" });
    const junk = new File(["x"], ".DS_Store");
    const out = await readDesignSystemFiles([a, junk]);
    expect(out).toEqual([{ path: "ds/tokens.json", content_base64: btoa("{}") }]);
  });
});
