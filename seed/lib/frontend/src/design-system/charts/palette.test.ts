import { describe, expect, it } from "vitest";
import {
  asCssColor,
  buildSequentialScale,
  CHART_PALETTE_FALLBACK,
  heatmapStep,
  readCssVar,
  resolveSeriesColor,
} from "./palette";

describe("resolveSeriesColor", () => {
  const palette = ["A", "B", "C"];

  it("prefers an explicit override (the backend-supplied `cor` field)", () => {
    expect(resolveSeriesColor(0, "#ff0000", palette)).toBe("#ff0000");
  });

  it("cycles the palette by index when no override is given", () => {
    expect(resolveSeriesColor(0, undefined, palette)).toBe("A");
    expect(resolveSeriesColor(1, null, palette)).toBe("B");
    expect(resolveSeriesColor(2, undefined, palette)).toBe("C");
  });

  it("wraps around when there are more series than palette entries", () => {
    expect(resolveSeriesColor(3, undefined, palette)).toBe("A");
    expect(resolveSeriesColor(4, undefined, palette)).toBe("B");
  });

  it("falls back to CHART_PALETTE_FALLBACK when given an empty palette", () => {
    expect(resolveSeriesColor(0, undefined, [])).toBe(CHART_PALETTE_FALLBACK[0]);
  });
});

describe("heatmapStep", () => {
  it("reserves step 0 for a genuine zero value", () => {
    expect(heatmapStep(0, 100)).toBe(0);
  });

  it("never returns step 0 for a positive value (distinct from a null/blank cell)", () => {
    expect(heatmapStep(1, 100, 5)).toBeGreaterThanOrEqual(1);
  });

  it("maps the max value to the top step", () => {
    expect(heatmapStep(100, 100, 5)).toBe(4);
  });

  it("degenerately maps every positive value to step 0 when max <= 0", () => {
    expect(heatmapStep(5, 0)).toBe(0);
    expect(heatmapStep(5, -1)).toBe(0);
  });

  it("clamps a value above max to the top step instead of overflowing", () => {
    expect(heatmapStep(9999, 100, 5)).toBe(4);
  });

  it("treats a negative or non-finite value as step 0", () => {
    expect(heatmapStep(-5, 100)).toBe(0);
    expect(heatmapStep(NaN, 100)).toBe(0);
  });
});

describe("readCssVar", () => {
  it("returns the resolved value when present", () => {
    expect(readCssVar("--x", "fallback", () => "220 70% 55%")).toBe("220 70% 55%");
  });

  it("falls back on an empty/whitespace-only value", () => {
    expect(readCssVar("--x", "fallback", () => "   ")).toBe("fallback");
    expect(readCssVar("--x", "fallback", () => undefined)).toBe("fallback");
  });
});

describe("asCssColor", () => {
  it("wraps a raw `H S% L%` triple in hsl(...)", () => {
    expect(asCssColor("220 70% 55%")).toBe("hsl(220 70% 55%)");
  });

  it("leaves an already-wrapped color alone", () => {
    expect(asCssColor("hsl(220 70% 55%)")).toBe("hsl(220 70% 55%)");
    expect(asCssColor("rgb(1,2,3)")).toBe("rgb(1,2,3)");
  });

  it("leaves a hex color alone", () => {
    expect(asCssColor("#ff0000")).toBe("#ff0000");
  });
});

describe("buildSequentialScale", () => {
  it("produces `steps` colors, lightest first and the base (darkest) last", () => {
    const scale = buildSequentialScale("220 70% 40%", 5);
    expect(scale).toHaveLength(5);
    // Extract lightness (last %-number) from each hsl(...) string and assert monotonic decrease.
    const lightnesses = scale.map((s) => Number(s.match(/([\d.]+)%\)$/)?.[1]));
    for (let i = 1; i < lightnesses.length; i++) {
      expect(lightnesses[i]).toBeLessThanOrEqual(lightnesses[i - 1]);
    }
    // The last step should equal the base lightness.
    expect(lightnesses[lightnesses.length - 1]).toBeCloseTo(40, 0);
  });

  it("falls back to a sane default hue when the input triple is unparseable", () => {
    const scale = buildSequentialScale("not-a-triple", 3);
    expect(scale).toHaveLength(3);
    expect(scale[0]).toMatch(/^hsl\(/);
  });

  it("returns at least one color for steps <= 1", () => {
    expect(buildSequentialScale("220 70% 40%", 1)).toHaveLength(1);
    expect(buildSequentialScale("220 70% 40%", 0)).toHaveLength(1);
  });
});
