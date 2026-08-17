/**
 * Regression guard for the incident this factory's theme seam exists to
 * prevent: p-studio shipped to prod on 2026-08-17 with a hand-rolled
 * `tailwind.config.ts` that scanned only `./src`, silently purging every
 * Tailwind class used inside the seed's own `AppShell`/`Sidebar`/`Header`
 * (`seed/lib` + `seed/framework`) — less than half the live CSS reached
 * users.
 *
 * Every product's `products/<slug>/frontend/tailwind.config.ts` must
 * either:
 *   (a) call `createTailwindConfig(...)` from this factory (the normal
 *       case — the content globs are then structurally inherited, not
 *       copy-pasted), or
 *   (b) if some future product genuinely can't call the factory, its own
 *       `content` array must still literally cover the two seed source
 *       globs this factory's `DEFAULT_CONTENT` uses.
 *
 * This is a source-scan, not a runtime resolution — it can't catch a glob
 * that's present but wrong, but it DOES catch the exact failure shape
 * from the incident: a product silently missing the seed-source globs
 * entirely.
 */
import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../..");
const PRODUCTS_DIR = path.join(REPO_ROOT, "products");

const SEED_GLOBS = [
  "seed/lib/frontend/src/**/*.{ts,tsx}",
  "seed/framework/frontend/src/**/*.{ts,tsx}",
];

function listProductTailwindConfigs(): string[] {
  return fs
    .readdirSync(PRODUCTS_DIR, { withFileTypes: true })
    .filter((e) => e.isDirectory())
    .map((e) => path.join(PRODUCTS_DIR, e.name, "frontend", "tailwind.config.ts"))
    .filter((p) => fs.existsSync(p));
}

describe("every product tailwind.config.ts scans the seed's own source", () => {
  const configs = listProductTailwindConfigs();

  it("finds at least one product config to check (sanity — an empty scan hides everything)", () => {
    expect(configs.length).toBeGreaterThan(5);
  });

  it.each(configs)("%s", (configPath) => {
    const src = fs.readFileSync(configPath, "utf8");
    const usesFactory = /createTailwindConfig\s*\(/.test(src);

    if (usesFactory) {
      // Inherits DEFAULT_CONTENT structurally — covered by
      // tailwind.config.factory.test.ts, nothing more to assert per-product.
      expect(usesFactory).toBe(true);
      return;
    }

    // Opted out of the factory entirely (no product currently does this,
    // but a future one might via a from-scratch config) — its OWN content
    // array must still name both seed globs literally, or the shell
    // renders unstyled exactly like the incident.
    for (const glob of SEED_GLOBS) {
      expect(src, `${configPath} does not call createTailwindConfig() AND is missing the seed glob "${glob}" — the exact shape of the 2026-08-17 p-studio incident.`).toContain(glob);
    }
  });
});
