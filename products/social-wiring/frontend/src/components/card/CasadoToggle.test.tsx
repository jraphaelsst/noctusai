import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { CasadoToggle } from "./CasadoToggle";

afterEach(() => {
  cleanup();
});

describe("CasadoToggle", () => {
  it("renders checked, labelled plainly 'Casado(a)'", () => {
    render(<CasadoToggle onDesmarcar={vi.fn()} testId="casado-toggle-x" />);
    expect(screen.getByText("Casado(a)")).toBeTruthy();
    expect(
      screen.getByRole("checkbox", { name: "Casado(a)" }).getAttribute("data-state"),
    ).toBe("checked");
  });

  it("calls onDesmarcar when unchecked — never a component-local flip", () => {
    const onDesmarcar = vi.fn();
    render(<CasadoToggle onDesmarcar={onDesmarcar} testId="casado-toggle-x" />);
    fireEvent.click(screen.getByRole("checkbox", { name: "Casado(a)" }));
    expect(onDesmarcar).toHaveBeenCalledTimes(1);
  });

  it("disables the control while saving", () => {
    render(<CasadoToggle onDesmarcar={vi.fn()} salvando testId="casado-toggle-x" />);
    const box = screen.getByRole("checkbox", { name: "Casado(a)" }) as HTMLButtonElement;
    expect(box.disabled).toBe(true);
  });
});
