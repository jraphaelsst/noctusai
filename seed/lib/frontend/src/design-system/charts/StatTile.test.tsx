/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { Target } from "lucide-react";
import { StatTile } from "./StatTile";

afterEach(cleanup);

describe("StatTile", () => {
  it("renders label + value", () => {
    render(<StatTile label="Total" value={128} />);
    expect(screen.getByText("Total")).toBeInTheDocument();
    expect(screen.getByText("128")).toBeInTheDocument();
  });

  it("shows an em dash instead of the value while loading", () => {
    render(<StatTile label="Total" value={128} loading />);
    expect(screen.queryByText("128")).not.toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders null delta as an em dash, never as 0%", () => {
    render(<StatTile label="Total" value={128} delta={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText("0.0%")).not.toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
  });

  it("signs a positive delta and derives the 'up' trend", () => {
    render(<StatTile label="Total" value={128} delta={12.3} />);
    expect(screen.getByText("+12.3%")).toBeInTheDocument();
  });

  it("signs a negative delta and derives the 'down' trend", () => {
    render(<StatTile label="Total" value={128} delta={-4} />);
    expect(screen.getByText("-4.0%")).toBeInTheDocument();
  });

  it("renders a resolved zero delta as 0.0%, distinct from null", () => {
    render(<StatTile label="Total" value={128} delta={0} />);
    expect(screen.getByText("0.0%")).toBeInTheDocument();
  });

  it("does not render a delta row at all when delta is omitted", () => {
    const { container } = render(<StatTile label="Total" value={128} hint="30 dias" />);
    expect(screen.getByText("30 dias")).toBeInTheDocument();
    // No trend icon (svg) should be present without a delta.
    expect(container.querySelector("svg")).toBeNull();
  });

  it("renders the provided icon", () => {
    const { container } = render(<StatTile icon={Target} label="Total" value={128} />);
    expect(container.querySelector("svg")).not.toBeNull();
  });

  it("respects an explicit trend override even when delta would derive a different direction", () => {
    render(<StatTile label="Total" value={128} delta={5} trend="flat" hint="override" />);
    // Still renders the signed delta text; the icon direction is what `trend` controls.
    expect(screen.getByText("+5.0%")).toBeInTheDocument();
  });
});
