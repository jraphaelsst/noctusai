/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { FilterBar } from "./FilterBar";

afterEach(cleanup);

describe("FilterBar", () => {
  it("renders its filter control slots", () => {
    render(
      <FilterBar>
        <input aria-label="busca" />
      </FilterBar>,
    );
    expect(screen.getByLabelText("busca")).toBeInTheDocument();
  });

  it("renders no chip row when chips is empty", () => {
    render(
      <FilterBar>
        <input aria-label="busca" />
      </FilterBar>,
    );
    expect(screen.queryByText("Limpar tudo")).not.toBeInTheDocument();
  });

  it("renders each chip label and fires its own onClear", () => {
    const onClearOrigem = vi.fn();
    const onClearAno = vi.fn();
    render(
      <FilterBar
        chips={[
          { key: "origem", label: "Origem: ZAP", onClear: onClearOrigem },
          { key: "ano", label: "Ano: 2026", onClear: onClearAno },
        ]}
      >
        <input aria-label="busca" />
      </FilterBar>,
    );
    expect(screen.getByText("Origem: ZAP")).toBeInTheDocument();
    expect(screen.getByText("Ano: 2026")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Remover filtro Origem: ZAP"));
    expect(onClearOrigem).toHaveBeenCalledTimes(1);
    expect(onClearAno).not.toHaveBeenCalled();
  });

  it("shows 'Limpar tudo' only when chips are present AND onClearAll is given", () => {
    const onClearAll = vi.fn();
    const { rerender } = render(
      <FilterBar chips={[{ key: "a", label: "A", onClear: () => {} }]}>
        <input aria-label="busca" />
      </FilterBar>,
    );
    expect(screen.queryByText("Limpar tudo")).not.toBeInTheDocument();

    rerender(
      <FilterBar chips={[{ key: "a", label: "A", onClear: () => {} }]} onClearAll={onClearAll}>
        <input aria-label="busca" />
      </FilterBar>,
    );
    fireEvent.click(screen.getByText("Limpar tudo"));
    expect(onClearAll).toHaveBeenCalledTimes(1);
  });

  it("respects a custom clearAllLabel", () => {
    render(
      <FilterBar chips={[{ key: "a", label: "A", onClear: () => {} }]} onClearAll={() => {}} clearAllLabel="Reset">
        <input aria-label="busca" />
      </FilterBar>,
    );
    expect(screen.getByText("Reset")).toBeInTheDocument();
  });

  it("toggles the collapsed state via the mobile Filtros button", () => {
    render(
      <FilterBar defaultCollapsed>
        <input aria-label="busca" />
      </FilterBar>,
    );
    const toggle = screen.getByRole("button", { name: /Filtros/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });
});
