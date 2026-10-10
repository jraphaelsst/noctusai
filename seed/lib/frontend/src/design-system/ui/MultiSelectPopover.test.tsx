/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MultiSelectPopover } from "./MultiSelectPopover";

afterEach(() => cleanup());

const opts = [
  { value: "a", label: "Alfa" },
  { value: "b", label: "Beta" },
  { value: "c", label: "Gama" },
];

describe("MultiSelectPopover", () => {
  it("shows the selected count and emits onToggle", async () => {
    const onToggle = vi.fn();
    render(<MultiSelectPopover label="Letras" options={opts} selected={["a"]} onToggle={onToggle} testId="ms" />);
    expect(screen.getByTestId("ms")).toHaveTextContent("1");
    await userEvent.click(screen.getByTestId("ms"));
    await userEvent.click(screen.getByTestId("ms-option-b"));
    expect(onToggle).toHaveBeenCalledWith("b");
  });

  it("disables unchecked options at the max cap and shows maxMessage", async () => {
    render(
      <MultiSelectPopover label="L" options={opts} selected={["a"]} onToggle={() => {}} max={1} maxMessage="Limite" testId="ms" />,
    );
    await userEvent.click(screen.getByTestId("ms"));
    expect(screen.getByTestId("ms-option-b")).toBeDisabled();
    expect(screen.getByTestId("ms-option-a")).not.toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent("Limite");
  });

  it("renders chips and triggerLabel", () => {
    render(
      <MultiSelectPopover label="Nichos" triggerLabel="Selecionar nichos" options={opts} selected={["c"]} onToggle={() => {}} showChips />,
    );
    expect(screen.getByRole("button", { name: /Selecionar nichos/ })).toBeInTheDocument();
    expect(screen.getByLabelText("Nichos selecionados")).toHaveTextContent("Gama");
  });

  it("filters options by search when there are more than 6", async () => {
    const many = Array.from({ length: 8 }, (_, i) => ({ value: `v${i}`, label: `Item ${i}` }));
    render(<MultiSelectPopover label="L" options={many} selected={[]} onToggle={() => {}} testId="ms" />);
    await userEvent.click(screen.getByTestId("ms"));
    await userEvent.type(screen.getByTestId("ms-search"), "Item 3");
    expect(screen.getByTestId("ms-option-v3")).toBeInTheDocument();
    expect(screen.queryByTestId("ms-option-v4")).not.toBeInTheDocument();
  });

  it("shows emptyMessage with no options", async () => {
    render(<MultiSelectPopover label="L" options={[]} selected={[]} onToggle={() => {}} emptyMessage="Vazio" testId="ms" />);
    await userEvent.click(screen.getByTestId("ms"));
    expect(screen.getByText("Vazio")).toBeInTheDocument();
  });
});
