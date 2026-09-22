/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Checkbox } from "./checkbox";

afterEach(() => {
  cleanup();
});

describe("Checkbox", () => {
  it("renders unchecked by default and toggles on click", async () => {
    const user = userEvent.setup();
    const onCheckedChange = vi.fn();
    render(<Checkbox aria-label="etiqueta" onCheckedChange={onCheckedChange} />);
    const box = screen.getByRole("checkbox", { name: "etiqueta" });
    expect(box).toHaveAttribute("data-state", "unchecked");
    await user.click(box);
    expect(onCheckedChange).toHaveBeenCalledWith(true);
  });

  it("respects a controlled checked prop", () => {
    render(<Checkbox aria-label="marcado" checked onCheckedChange={() => {}} />);
    expect(screen.getByRole("checkbox", { name: "marcado" })).toHaveAttribute("data-state", "checked");
  });

  it("keeps the desktop-sized visual box while extending the mobile hit-area", () => {
    render(<Checkbox aria-label="alvo" />);
    const box = screen.getByRole("checkbox", { name: "alvo" });
    expect(box).toHaveClass("h-4", "w-4");
    expect(box).toHaveClass("after:-inset-3", "sm:after:inset-0");
  });
});
