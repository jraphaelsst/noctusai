/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { mockRechartsLayout } from "./_recharts-test-utils";
import { DonutChart } from "./DonutChart";

beforeAll(() => mockRechartsLayout());
afterEach(cleanup);

const BUCKETS = [
  { label: "ZAP", total: 40, cor: "#123456" },
  { label: "Site", total: 20, cor: null },
];

// NOTE: under jsdom (no real layout engine), recharts' Pie/Legend height
// negotiation ends up computing a zero-height clip rect for the pie's own
// plot area (a compound-chart quirk distinct from the plain ResponsiveContainer
// 0x0 issue `_recharts-test-utils.ts` fixes for Line/Area/Bar) — the
// `.recharts-pie-sector` <path> elements are not created as a result. The
// Legend, however, DOES render correctly (recharts measures it independently
// of the pie's own clip area), so it is a real, honest surface to assert
// the per-row color-resolution behavior against instead of the sector paths.
describe("DonutChart", () => {
  it("renders one legend entry per row, in row order", () => {
    const { container } = render(<DonutChart data={BUCKETS} nameKey="label" valueKey="total" colorKey="cor" />);
    const items = container.querySelectorAll(".recharts-legend-item-text");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("ZAP");
    expect(items[1]).toHaveTextContent("Site");
  });

  it("applies an explicit colorKey override for the row that has one", () => {
    const { container } = render(<DonutChart data={BUCKETS} nameKey="label" valueKey="total" colorKey="cor" />);
    const icons = container.querySelectorAll(".recharts-legend-icon");
    expect(icons[0]).toHaveAttribute("fill", "#123456");
  });

  it("falls back to the theme palette for a row with no colorKey value", () => {
    const { container } = render(<DonutChart data={BUCKETS} nameKey="label" valueKey="total" colorKey="cor" />);
    const icons = container.querySelectorAll(".recharts-legend-icon");
    const fill = icons[1]?.getAttribute("fill");
    expect(fill).toBeTruthy();
    expect(fill).not.toBe("#123456");
  });

  it("does not throw when colorKey is omitted entirely (every row uses the palette)", () => {
    expect(() =>
      render(<DonutChart data={BUCKETS} nameKey="label" valueKey="total" />),
    ).not.toThrow();
  });
});
