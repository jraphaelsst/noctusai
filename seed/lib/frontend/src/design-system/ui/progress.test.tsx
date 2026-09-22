/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { Progress } from "./progress";

afterEach(() => {
  cleanup();
});

describe("Progress", () => {
  it("renders the indicator translated to reflect the value", () => {
    render(<Progress data-testid="progress" value={40} />);
    const root = screen.getByTestId("progress");
    const indicator = root.firstElementChild as HTMLElement;
    expect(indicator.style.transform).toBe("translateX(-60%)");
  });

  it("treats a missing value as 0", () => {
    render(<Progress data-testid="progress" />);
    const root = screen.getByTestId("progress");
    const indicator = root.firstElementChild as HTMLElement;
    expect(indicator.style.transform).toBe("translateX(-100%)");
  });
});
