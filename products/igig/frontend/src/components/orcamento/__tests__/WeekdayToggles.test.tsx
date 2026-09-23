/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

import { WeekdayToggles } from "../WeekdayToggles";

afterEach(cleanup);

describe("WeekdayToggles", () => {
  it("renders S T Q Q S S D with pressed state from the mask", () => {
    render(<WeekdayToggles value={1 | 16} onChange={vi.fn()} />);
    const botoes = screen.getAllByRole("button");
    expect(botoes.map((b) => b.textContent)).toEqual(["S", "T", "Q", "Q", "S", "S", "D"]);
    expect(screen.getByRole("button", { name: "Segunda" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Sexta" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Quarta" })).toHaveAttribute("aria-pressed", "false");
  });

  it("tapping a day emits the toggled bitmask", () => {
    const onChange = vi.fn();
    render(<WeekdayToggles value={1} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Quarta" }));
    expect(onChange).toHaveBeenLastCalledWith(1 | 4);
    fireEvent.click(screen.getByRole("button", { name: "Segunda" }));
    expect(onChange).toHaveBeenLastCalledWith(0);
  });

  it("is inert when disabled (read-only orçamento)", () => {
    const onChange = vi.fn();
    render(<WeekdayToggles value={1} onChange={onChange} disabled />);
    fireEvent.click(screen.getByRole("button", { name: "Domingo" }));
    expect(onChange).not.toHaveBeenCalled();
  });
});
