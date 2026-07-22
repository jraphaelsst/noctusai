/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { mockRechartsLayout } from "./_recharts-test-utils";
import { LineChart } from "./LineChart";

beforeAll(() => mockRechartsLayout());
afterEach(cleanup);

const DATA = [
  { label: "Jan", zap: 10, site: 4 },
  { label: "Fev", zap: 14, site: 6 },
];

describe("LineChart", () => {
  it("renders one SVG path per series", () => {
    const { container } = render(
      <LineChart
        data={DATA}
        xKey="label"
        series={[
          { key: "zap", label: "ZAP" },
          { key: "site", label: "Site" },
        ]}
      />,
    );
    // recharts renders one <path class="recharts-line-curve"> per <Line>.
    expect(container.querySelectorAll(".recharts-line-curve")).toHaveLength(2);
  });

  it("renders a single-series line without a legend (legend only shown for >1 series)", () => {
    const { container } = render(<LineChart data={DATA} xKey="label" series={[{ key: "zap", label: "ZAP" }]} />);
    expect(container.querySelectorAll(".recharts-line-curve")).toHaveLength(1);
    expect(container.querySelector(".recharts-legend-wrapper")).toBeNull();
  });

  it("renders a legend when there is more than one series", () => {
    const { container } = render(
      <LineChart
        data={DATA}
        xKey="label"
        series={[
          { key: "zap", label: "ZAP" },
          { key: "site", label: "Site" },
        ]}
      />,
    );
    expect(container.querySelector(".recharts-legend-wrapper")).not.toBeNull();
  });
});
