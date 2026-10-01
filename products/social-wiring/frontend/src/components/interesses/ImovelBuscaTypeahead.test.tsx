/** Typeahead: the list narrows as the código is typed until one is left; a row
 *  click selects it. The data layer is mocked at the hook seam (contract-shaped
 *  rows from `GET /api/imoveis/busca`). */
import { afterEach, describe, expect, it, vi } from "vitest";

const { mockBusca } = vi.hoisted(() => ({ mockBusca: vi.fn() }));
vi.mock("@/hooks/useCardHub", () => ({ useImoveisBusca: mockBusca }));
vi.mock("@/hooks/useDebouncedValue", () => ({ useDebouncedValue: (v: string) => v }));

import { cleanup, fireEvent, render } from "@testing-library/react";

import { ImovelBuscaTypeahead } from "./ImovelBuscaTypeahead";
import { imovelResumo } from "./fixtures";

afterEach(() => {
  cleanup();
  mockBusca.mockReset();
});

const ALL = ["ONE9001", "ONE9002", "ONE9481"].map((c) => imovelResumo(c));
/** What the server does: narrow by prefix of the typed term. */
function servidor(termo: string) {
  const items = ALL.filter((i) => i.codigo.startsWith(termo.trim().toUpperCase()));
  return { data: { items }, isPending: false, isFetching: false, isError: false };
}

describe("ImovelBuscaTypeahead", () => {
  it("narrows the list as the código is typed until one is left", () => {
    mockBusca.mockImplementation(servidor);
    const { getByTestId, queryByTestId } = render(<ImovelBuscaTypeahead onSelect={vi.fn()} />);
    const input = getByTestId("imovel-busca-input");

    fireEvent.change(input, { target: { value: "ON" } });
    expect(mockBusca).toHaveBeenLastCalledWith("ON");
    expect(queryByTestId("imovel-busca-item-ONE9001")).toBeTruthy();
    expect(queryByTestId("imovel-busca-item-ONE9481")).toBeTruthy();

    fireEvent.change(input, { target: { value: "ONE94" } });
    expect(mockBusca).toHaveBeenLastCalledWith("ONE94");
    expect(queryByTestId("imovel-busca-item-ONE9001")).toBeNull();
    expect(queryByTestId("imovel-busca-item-ONE9481")).toBeTruthy();
  });

  it("each row shows photo, código, endereço + complemento and R$", () => {
    mockBusca.mockImplementation(servidor);
    const { getByTestId } = render(<ImovelBuscaTypeahead onSelect={vi.fn()} />);
    fireEvent.change(getByTestId("imovel-busca-input"), { target: { value: "ONE9481" } });
    const row = getByTestId("imovel-busca-item-ONE9481");
    expect(row.querySelector("img")?.getAttribute("src")).toBe("https://img.test/ONE9481.jpg");
    expect(row.textContent).toContain("ONE9481");
    expect(row.textContent).toContain("Rua das Flores, 10 — Centro, Florianópolis/SC · apto 52");
    expect(row.textContent).toMatch(/R\$\s?850\.000/);
  });

  it("clicking a row selects it; rows already on the list are disabled", () => {
    mockBusca.mockImplementation(servidor);
    const onSelect = vi.fn();
    const { getByTestId } = render(
      <ImovelBuscaTypeahead onSelect={onSelect} jaNaLista={["one9001"]} />,
    );
    fireEvent.change(getByTestId("imovel-busca-input"), { target: { value: "ONE9" } });

    expect((getByTestId("imovel-busca-item-ONE9001") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(getByTestId("imovel-busca-item-ONE9002"));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0][0].codigo).toBe("ONE9002");
  });

  it("empty and error states are explicit; one char asks for more", () => {
    mockBusca.mockReturnValue({ data: { items: [] }, isPending: false, isFetching: false, isError: false });
    const { getByTestId, queryByTestId, rerender } = render(<ImovelBuscaTypeahead onSelect={vi.fn()} />);
    fireEvent.change(getByTestId("imovel-busca-input"), { target: { value: "O" } });
    expect(getByTestId("imovel-busca-resultados").textContent).toContain("ao menos 2");

    fireEvent.change(getByTestId("imovel-busca-input"), { target: { value: "ZZZ" } });
    expect(queryByTestId("imovel-busca-vazio")).toBeTruthy();

    mockBusca.mockReturnValue({ data: undefined, isPending: false, isFetching: false, isError: true });
    rerender(<ImovelBuscaTypeahead onSelect={vi.fn()} />);
    expect(queryByTestId("imovel-busca-erro")).toBeTruthy();
  });

  it("never claims 'no results' while a request is in flight and nothing is shown yet", () => {
    mockBusca.mockReturnValue({ data: undefined, isPending: true, isFetching: true, isError: false });
    const { getByTestId, queryByTestId } = render(<ImovelBuscaTypeahead onSelect={vi.fn()} />);
    fireEvent.change(getByTestId("imovel-busca-input"), { target: { value: "ONE9" } });
    expect(queryByTestId("imovel-busca-carregando")).toBeTruthy();
    expect(queryByTestId("imovel-busca-vazio")).toBeNull();
  });
});
