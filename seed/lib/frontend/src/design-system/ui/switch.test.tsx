/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Switch } from "./switch";

afterEach(() => {
  cleanup();
});

describe("Switch", () => {
  it("renders unchecked by default and toggles on click", async () => {
    const user = userEvent.setup();
    const onCheckedChange = vi.fn();
    render(<Switch aria-label="ativar" onCheckedChange={onCheckedChange} />);
    const toggle = screen.getByRole("switch", { name: "ativar" });
    expect(toggle).toHaveAttribute("data-state", "unchecked");
    await user.click(toggle);
    expect(onCheckedChange).toHaveBeenCalledWith(true);
  });

  it("keeps the desktop-sized visual box while extending the mobile vertical hit-area", () => {
    render(<Switch aria-label="alvo" />);
    const toggle = screen.getByRole("switch", { name: "alvo" });
    expect(toggle).toHaveClass("h-6", "w-11");
    expect(toggle).toHaveClass("after:-inset-y-2", "sm:after:inset-0");
  });
});
