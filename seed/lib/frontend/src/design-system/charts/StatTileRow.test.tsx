/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { StatTileRow } from "./StatTileRow";

afterEach(cleanup);

describe("StatTileRow", () => {
  it("renders its children", () => {
    render(
      <StatTileRow>
        <div>Tile A</div>
        <div>Tile B</div>
      </StatTileRow>,
    );
    expect(screen.getByText("Tile A")).toBeInTheDocument();
    expect(screen.getByText("Tile B")).toBeInTheDocument();
  });

  it("applies the established responsive grid classes", () => {
    const { container } = render(
      <StatTileRow>
        <div>Tile A</div>
      </StatTileRow>,
    );
    const grid = container.firstElementChild as HTMLElement;
    expect(grid.className).toContain("grid-cols-1");
    expect(grid.className).toContain("sm:grid-cols-2");
    expect(grid.className).toContain("lg:grid-cols-4");
  });
});
