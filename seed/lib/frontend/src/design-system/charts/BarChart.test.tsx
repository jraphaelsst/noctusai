/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { mockRechartsLayout } from "./_recharts-test-utils";
import { BarChart } from "./BarChart";

beforeAll(() => mockRechartsLayout());
afterEach(cleanup);

const DATA = [
  { label: "Ana", total: 10 },
  { label: "Bruno", total: 14 },
];

describe("BarChart", () => {
  it("renders vertical bars by default", () => {
    const { container } = render(<BarChart data={DATA} xKey="label" series={[{ key: "total", label: "Total" }]} />);
    expect(container.querySelectorAll(".recharts-bar-rectangle")).toHaveLength(DATA.length);
  });

  it("renders ranked horizontal bars when `horizontal` is set", () => {
    const { container } = render(
      <BarChart data={DATA} xKey="label" series={[{ key: "total", label: "Total" }]} horizontal />,
    );
    expect(container.querySelectorAll(".recharts-bar-rectangle")).toHaveLength(DATA.length);
    // In recharts, layout="vertical" is the internal name for horizontal bars.
    expect(container.querySelector(".recharts-wrapper")?.innerHTML).toContain("recharts-bar");
  });
});
