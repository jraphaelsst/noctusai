/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { mockRechartsLayout } from "./_recharts-test-utils";
import { AreaChart } from "./AreaChart";

beforeAll(() => mockRechartsLayout());
afterEach(cleanup);

const DATA = [
  { label: "Jan", zap: 10, site: 4 },
  { label: "Fev", zap: 14, site: 6 },
];

describe("AreaChart", () => {
  it("renders one area per series, overlaying (no stackId) by default", () => {
    const { container } = render(
      <AreaChart
        data={DATA}
        xKey="label"
        series={[
          { key: "zap", label: "ZAP" },
          { key: "site", label: "Site" },
        ]}
      />,
    );
    const areas = container.querySelectorAll(".recharts-area");
    expect(areas).toHaveLength(2);
  });

  it("stacks series onto the same stackId when `stacked` is set", () => {
    const { container } = render(
      <AreaChart
        data={DATA}
        xKey="label"
        stacked
        series={[
          { key: "zap", label: "ZAP" },
          { key: "site", label: "Site" },
        ]}
      />,
    );
    expect(container.querySelectorAll(".recharts-area")).toHaveLength(2);
  });
});
