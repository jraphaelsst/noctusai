/**
 * Tests for `createProductVitestConfig` — the shared vitest config factory
 * absorbed into the seed framework on 2026-04-27 (replaces per-product
 * copy-pasted vitest.config.ts files).
 */
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import path from "path";

import {
  createProductVitestConfig,
  type ProductVitestConfigOptions,
} from "../vitest.config.factory";


// The factory reads `process.cwd()` at call time. Pin it to a representative
// product directory for deterministic alias assertions, then restore.
const ORIGINAL_CWD = process.cwd();
const FAKE_PRODUCT_DIR = path.resolve(ORIGINAL_CWD, "../../../products/erp-imobiliario/frontend");

describe("createProductVitestConfig", () => {
  beforeEach(() => {
    // Vitest can't really chdir between tests reliably, so we override via
    // process.cwd spy. Restore in afterEach.
    vi.spyOn(process, "cwd").mockReturnValue(FAKE_PRODUCT_DIR);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns the canonical jsdom + globals + exclude shape", () => {
    const config = createProductVitestConfig();

    expect(config.test?.globals).toBe(true);
    expect(config.test?.environment).toBe("jsdom");
    expect(config.test?.exclude).toContain("**/node_modules/**");
    expect(config.test?.exclude).toContain("**/dist/**");
    // The headline reason this factory exists — without this exclude, vitest's
    // default include scoops up Playwright e2e tests and crashes the whole run.
    expect(config.test?.exclude).toContain("e2e/**");
  });

  it("wires the four seed-scope aliases from the product directory", () => {
    const config = createProductVitestConfig();
    const aliases = config.resolve?.alias as Record<string, string>;

    expect(aliases["@"]).toBe(path.resolve(FAKE_PRODUCT_DIR, "./src"));
    expect(aliases["@noctusai/lib"]).toMatch(/seed\/frontend\/lib\/src$/);
    expect(aliases["@noctusai/seed"]).toMatch(/seed\/frontend\/framework\/src$/);
    expect(aliases["@noctusai/seed/infra"]).toMatch(/seed\/frontend\/framework\/src\/infra\.tsx$/);
  });

  it("layers excludeExtra on top of defaults without dropping them", () => {
    const config = createProductVitestConfig({ excludeExtra: ["custom-glob/**"] });

    expect(config.test?.exclude).toContain("e2e/**");
    expect(config.test?.exclude).toContain("custom-glob/**");
  });

  it("layers aliasExtra on top of defaults without overriding seed paths", () => {
    const config = createProductVitestConfig({
      aliasExtra: { "@my-pkg": "/abs/path/to/my-pkg" },
    });
    const aliases = config.resolve?.alias as Record<string, string>;

    expect(aliases["@my-pkg"]).toBe("/abs/path/to/my-pkg");
    expect(aliases["@noctusai/seed/infra"]).toMatch(/infra\.tsx$/);
  });

  it("respects environment override (e.g., 'happy-dom')", () => {
    const config = createProductVitestConfig({ environment: "happy-dom" });

    expect(config.test?.environment).toBe("happy-dom");
  });

  it("invokes extend(...) for last-mile mutation when provided", () => {
    const config = createProductVitestConfig({
      extend: (cfg) => ({
        ...cfg,
        test: { ...cfg.test, name: "custom-suite" },
      }),
    });

    expect(config.test?.name).toBe("custom-suite");
    expect(config.test?.environment).toBe("jsdom");
  });
});
