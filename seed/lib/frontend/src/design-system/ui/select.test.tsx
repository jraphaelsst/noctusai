/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./select";

afterEach(() => {
  cleanup();
});

function renderSelect(onValueChange = vi.fn()) {
  render(
    <Select onValueChange={onValueChange}>
      <SelectTrigger aria-label="status">
        <SelectValue placeholder="Selecione" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="aberto">Aberto</SelectItem>
        <SelectItem value="fechado">Fechado</SelectItem>
      </SelectContent>
    </Select>,
  );
  return onValueChange;
}

describe("Select", () => {
  it("renders the trigger with the placeholder and the h-10 touch target", () => {
    renderSelect();
    const trigger = screen.getByRole("combobox", { name: "status" });
    expect(trigger).toHaveClass("h-10");
    expect(screen.getByText("Selecione")).toBeInTheDocument();
  });

  it("opens the item list and reports a selection", async () => {
    const user = userEvent.setup();
    const onValueChange = renderSelect();
    await user.click(screen.getByRole("combobox", { name: "status" }));
    const option = await screen.findByText("Aberto");
    await user.click(option);
    expect(onValueChange).toHaveBeenCalledWith("aberto");
  });
});
