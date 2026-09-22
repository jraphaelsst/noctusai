/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { Avatar, AvatarFallback, AvatarImage } from "./avatar";

afterEach(() => {
  cleanup();
});

describe("Avatar", () => {
  it("renders the fallback when there is no image", () => {
    render(
      <Avatar data-testid="avatar">
        <AvatarImage src="" alt="" />
        <AvatarFallback>JR</AvatarFallback>
      </Avatar>,
    );
    expect(screen.getByTestId("avatar")).toHaveClass("h-10", "w-10", "rounded-full");
    expect(screen.getByText("JR")).toBeInTheDocument();
  });

  it("merges a custom className on the root", () => {
    render(
      <Avatar data-testid="avatar" className="ring-2">
        <AvatarFallback>X</AvatarFallback>
      </Avatar>,
    );
    expect(screen.getByTestId("avatar")).toHaveClass("ring-2");
  });
});
