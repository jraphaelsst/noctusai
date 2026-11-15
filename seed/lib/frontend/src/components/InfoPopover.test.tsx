import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";

import { InfoPopover, InfoSecoes } from "./InfoPopover";

afterEach(cleanup);

describe("InfoPopover", () => {
  it("is an accessible icon button and mounts its body only when opened", () => {
    const Corpo = vi.fn(() => <p>corpo</p>);
    render(
      <InfoPopover label="Sobre: RG" testId="rg">
        <Corpo />
      </InfoPopover>,
    );
    const trigger = screen.getByRole("button", { name: "Sobre: RG" });
    expect(Corpo).not.toHaveBeenCalled();
    expect(screen.queryByTestId("rg-content")).toBeNull();
    fireEvent.click(trigger);
    expect(screen.getByTestId("rg-content").textContent).toContain("corpo");
    expect(Corpo).toHaveBeenCalled();
  });

  it("does not propagate the trigger click to the row it sits in", () => {
    const onRow = vi.fn();
    render(
      <div onClick={onRow}>
        <InfoPopover label="Sobre">x</InfoPopover>
      </div>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Sobre" }));
    expect(onRow).not.toHaveBeenCalled();
  });
});

describe("InfoSecoes", () => {
  it("renders bullets per section, hides empty sections without a vazio, shows vazio otherwise", () => {
    render(
      <InfoSecoes
        titulo="RG"
        secoes={[
          { titulo: "Dados lidos", itens: ["Nome", "Data de nascimento"] },
          { titulo: "Sem nada", itens: [] },
          { titulo: "Usado em", itens: [], vazio: "Nenhum uso" },
        ]}
        nota="nota"
        rodape={<a href="#x">Ver no guia</a>}
      />,
    );
    expect(screen.getByText("RG")).toBeTruthy();
    expect(screen.getAllByRole("listitem").map((l) => l.textContent)).toEqual(["Nome", "Data de nascimento"]);
    expect(screen.queryByText("Sem nada")).toBeNull();
    expect(screen.getByText("Nenhum uso")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Ver no guia" })).toBeTruthy();
  });
});
