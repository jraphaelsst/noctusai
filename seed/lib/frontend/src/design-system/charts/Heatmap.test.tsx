/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Heatmap } from "./Heatmap";

afterEach(cleanup);

describe("Heatmap", () => {
  it("renders one row per ano and one column per month", () => {
    render(
      <Heatmap
        anos={[2025, 2026]}
        cells={{ "2025": Array(12).fill(0), "2026": Array(12).fill(0) }}
        max={10}
      />,
    );
    expect(screen.getByText("2025")).toBeInTheDocument();
    expect(screen.getByText("2026")).toBeInTheDocument();
    expect(screen.getByText("Jan")).toBeInTheDocument();
    expect(screen.getByText("Dez")).toBeInTheDocument();
  });

  it("renders a null cell blank with a 'Sem dados' title, never a value", () => {
    const cells = { "2026": [null, 5, ...Array(10).fill(null)] };
    render(<Heatmap anos={[2026]} cells={cells} max={10} />);
    const nullCell = screen.getAllByRole("button")[0];
    expect(nullCell).toHaveAttribute("title", "Sem dados");
    expect(nullCell.textContent).toBe("");
  });

  it("renders a genuine zero as a filled (non-null) step, distinct from a null cell", () => {
    const cells = { "2026": [0, ...Array(11).fill(null)] };
    render(<Heatmap anos={[2026]} cells={cells} max={10} />);
    const zeroCell = screen.getAllByRole("button")[0];
    expect(zeroCell).not.toHaveAttribute("title", "Sem dados");
    expect(zeroCell.getAttribute("title")).toContain("Jan/2026");
  });

  it("fires onCellClick with (ano, mes, value) on click", () => {
    const onCellClick = vi.fn();
    const cells = { "2026": [7, ...Array(11).fill(null)] };
    render(<Heatmap anos={[2026]} cells={cells} max={10} onCellClick={onCellClick} />);
    fireEvent.click(screen.getAllByRole("button")[0]);
    expect(onCellClick).toHaveBeenCalledWith(2026, 1, 7);
  });

  it("does not attach a click handler crash when onCellClick is omitted", () => {
    const cells = { "2026": [7, ...Array(11).fill(null)] };
    render(<Heatmap anos={[2026]} cells={cells} max={10} />);
    expect(() => fireEvent.click(screen.getAllByRole("button")[0])).not.toThrow();
  });

  it("treats a missing year row as all-null (defensive against a sparse `cells` map)", () => {
    render(<Heatmap anos={[2019]} cells={{}} max={10} />);
    const firstCell = screen.getAllByRole("button")[0];
    expect(firstCell).toHaveAttribute("title", "Sem dados");
  });
});
