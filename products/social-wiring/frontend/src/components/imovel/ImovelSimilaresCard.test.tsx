import { afterEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({
  similares: vi.fn(),
  interessados: vi.fn(),
  add: vi.fn(),
  addHookFor: vi.fn(),
}));
vi.mock("@/hooks/useImovelRelacionamentos", () => ({
  useImovelSimilares: m.similares,
  useImovelInteressados: m.interessados,
}));
vi.mock("@/hooks/useInteresses", () => ({
  useInteresseMutations: (id: string) => {
    m.addHookFor(id);
    return { add: { mutate: m.add, isPending: false } };
  },
}));

import { cleanup, fireEvent, render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { ImovelSimilaresCard } from "./ImovelSimilaresCard";
import { imovelResumo } from "@/components/interesses/fixtures";

afterEach(() => {
  cleanup();
  Object.values(m).forEach((f) => f.mockReset());
});

const similar = (c: string, score: number) => ({
  ...imovelResumo(c),
  score,
  justificativa: "Mesmo bairro. Faixa de preço próxima",
  reasons: ["Mesmo bairro", "Faixa de preço próxima"],
});

const doRender = () =>
  render(
    <MemoryRouter>
      <ImovelSimilaresCard codigo="ONE9001" />
    </MemoryRouter>,
  );

describe("ImovelSimilaresCard", () => {
  it("rows carry the busca face + score + reason chips", () => {
    m.similares.mockReturnValue({
      data: { items: [similar("ONE9100", 82.4)], total: 1, sem_semantica: 0 },
      isPending: false,
      isFetching: false,
      isError: false,
    });
    const { getByTestId } = doRender();
    const row = getByTestId("similar-ONE9100");
    expect(row.textContent).toContain("ONE9100");
    expect(row.textContent).toContain("apto 52");
    expect(getByTestId("similar-score").textContent).toBe("82 pts");
    expect(row.textContent).toContain("Mesmo bairro");
    expect(row.textContent).toContain("Faixa de preço próxima");
  });

  it("empty state shows the server's `aviso` when present", () => {
    m.similares.mockReturnValue({
      data: { items: [], total: 0, sem_semantica: 0, aviso: "Imóvel fora do catálogo — sem base para comparar." },
      isPending: false,
      isFetching: false,
      isError: false,
    });
    expect(doRender().getByTestId("similares-vazio").textContent).toContain("fora do catálogo");
  });

  it("'Adicionar ao interesse de…' picks an interessado and POSTs the similar's código", () => {
    m.similares.mockReturnValue({
      data: { items: [similar("ONE9100", 70)], total: 1, sem_semantica: 0 },
      isPending: false,
      isFetching: false,
      isError: false,
    });
    m.interessados.mockReturnValue({
      data: {
        items: [
          { interesse_id: "i1", cliente_id: "c1", nome: "Ana" },
          { interesse_id: "i2", cliente_id: "c2", nome: "Bruno" },
        ],
        total: 2,
      },
      isPending: false,
      isFetching: false,
      isError: false,
    });
    const { getByTestId } = doRender();
    fireEvent.click(getByTestId("similar-adicionar-ONE9100"));
    const confirmar = getByTestId("similar-interessado-confirmar") as HTMLButtonElement;
    expect(confirmar.disabled).toBe(true);
    fireEvent.change(getByTestId("similar-interessado-select"), { target: { value: "c2" } });
    expect(m.addHookFor).toHaveBeenLastCalledWith("c2");
    fireEvent.click(confirmar);
    expect(m.add.mock.calls[0][0]).toEqual({ codigo: "ONE9100", origem: "manual" });
  });

  it("error / loading states", () => {
    m.similares.mockReturnValue({ data: undefined, isPending: false, isFetching: false, isError: true });
    expect(doRender().queryByTestId("similares-erro")).toBeTruthy();
    cleanup();
    m.similares.mockReturnValue({ data: undefined, isPending: true, isFetching: true, isError: false });
    expect(doRender().queryByTestId("similares-loading")).toBeTruthy();
  });
});
