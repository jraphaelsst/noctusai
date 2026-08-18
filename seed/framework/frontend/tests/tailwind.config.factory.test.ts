/**
 * Tests for `createTailwindConfig` — proves the theme seam
 * (`ownTheme`/`darkMode`) is backwards compatible with every existing
 * no-arg consumer, and that opting out of the base preset behaves as
 * documented (drop, never silently merge, two colour spaces).
 */
import { describe, it, expect } from "vitest";

import { createTailwindConfig } from "../tailwind.config.factory";
import base from "../../../lib/frontend/src/design-system/tailwind.config.base";

describe("createTailwindConfig", () => {
  it("no-arg call is byte-identical across repeated invocations (deterministic)", () => {
    const a = createTailwindConfig();
    const b = createTailwindConfig();
    // plugins carries a `require()`'d function; compare everything else
    // structurally and the plugin list by length/identity of the module.
    expect(a.content).toEqual(b.content);
    expect(a.presets).toEqual(b.presets);
    expect(a.plugins?.length).toBe(b.plugins?.length);
    expect("theme" in a).toBe(false);
    expect("darkMode" in a).toBe(false);
  });

  it("no-arg call inherits the base preset and canonical content globs (unchanged consumer shape)", () => {
    const config = createTailwindConfig();

    expect(config.presets).toEqual([base]);
    expect(config.content).toEqual([
      "./src/**/*.{ts,tsx}",
      "./index.html",
      "../../../seed/lib/frontend/src/**/*.{ts,tsx}",
      "../../../seed/framework/frontend/src/**/*.{ts,tsx}",
    ]);
    // No `theme` / `darkMode` key at all — not even `undefined` — so a
    // consumer's `presets: [base]` is the sole source of both, exactly as
    // before this seam existed.
    expect("theme" in config).toBe(false);
    expect("darkMode" in config).toBe(false);
  });

  it("extraContent / extraPlugins still layer on top of the defaults", () => {
    const marker = () => ({});
    const config = createTailwindConfig({
      extraContent: ["./extra/**/*.tsx"],
      extraPlugins: [marker],
    });

    expect(config.content).toContain("./extra/**/*.tsx");
    expect(config.content).toContain("./src/**/*.{ts,tsx}");
    expect(config.plugins).toContain(marker);
    expect(config.plugins?.length).toBe(2); // tailwindcss-animate + marker
  });

  it("ownTheme drops the base preset entirely instead of merging it", () => {
    const ownTheme = { extend: { colors: { primary: "oklch(var(--primary) / <alpha-value>)" } } };
    const config = createTailwindConfig({ ownTheme, darkMode: "class" });

    expect(config.presets).toBeUndefined();
    expect(config.theme).toEqual(ownTheme);
    expect(config.darkMode).toBe("class");
    // The content globs and plugin are still seed-owned even on this seam —
    // only the colour-bearing preset is swappable.
    expect(config.content).toEqual([
      "./src/**/*.{ts,tsx}",
      "./index.html",
      "../../../seed/lib/frontend/src/**/*.{ts,tsx}",
      "../../../seed/framework/frontend/src/**/*.{ts,tsx}",
    ]);
    expect(config.plugins?.length).toBe(1);
  });

  it("darkMode is ignored when ownTheme is not supplied (base preset stays the sole source)", () => {
    const config = createTailwindConfig({ darkMode: "media" });

    expect(config.presets).toEqual([base]);
    expect("darkMode" in config).toBe(false);
  });
});
