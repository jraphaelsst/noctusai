/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { TableSkeleton } from "./TableSkeleton";

afterEach(cleanup);

describe("TableSkeleton", () => {
  it("renders the default 5 rows x 4 columns shape plus a header row", () => {
    const { container } = render(<TableSkeleton />);
    expect(container.querySelectorAll("thead th")).toHaveLength(4);
    expect(container.querySelectorAll("tbody tr")).toHaveLength(5);
    expect(container.querySelectorAll("tbody td")).toHaveLength(20);
  });

  it("honors custom rows/columns", () => {
    const { container } = render(<TableSkeleton rows={3} columns={6} />);
    expect(container.querySelectorAll("thead th")).toHaveLength(6);
    expect(container.querySelectorAll("tbody tr")).toHaveLength(3);
    expect(container.querySelectorAll("tbody td")).toHaveLength(18);
  });

  it("omits the header row when showHeader=false", () => {
    const { container } = render(<TableSkeleton showHeader={false} />);
    expect(container.querySelector("thead")).not.toBeInTheDocument();
  });

  it("announces exactly ONE status region for the whole table (not one per cell)", () => {
    render(<TableSkeleton rows={4} columns={3} />);
    expect(screen.getAllByRole("status")).toHaveLength(1);
  });
});
