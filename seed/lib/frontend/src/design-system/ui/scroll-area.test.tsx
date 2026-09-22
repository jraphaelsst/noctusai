/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ScrollArea } from "./scroll-area";

afterEach(() => {
  cleanup();
});

describe("ScrollArea", () => {
  it("renders its children inside the viewport", () => {
    render(
      <ScrollArea data-testid="scroll-area" className="h-40">
        <div>linha 1</div>
      </ScrollArea>,
    );
    expect(screen.getByTestId("scroll-area")).toHaveClass("h-40", "relative", "overflow-hidden");
    expect(screen.getByText("linha 1")).toBeInTheDocument();
  });
});
