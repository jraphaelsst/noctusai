/** The roteiro flow: tick → "Gerar roteiro" (disabled with none ticked) →
 *  ordering dialog (drag result + required date) → POST with the códigos in the
 *  final order → PDF. Mocked at the hook seam; the dnd-kit gesture itself is not
 *  simulated (jsdom has no layout) — its `onDragEnd` is driven directly. */
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

const m = vi.hoisted(() => ({
  useInteresses: vi.fn(),
  add: vi.fn(),
  remove: vi.fn(),
  criar: vi.fn(),
  pdf: vi.fn(),
  dragEnd: { current: null as null | ((e: unknown) => void) },
}));

vi.mock("@/hooks/useInteresses", () => ({
  useInteresses: m.useInteresses,
  useInteresseMutations: () => ({
    add: { mutate: m.add, isPending: false },
    remove: { mutate: m.remove, isPending: false, variables: undefined },
  }),
}));
vi.mock("@/hooks/usePessoa", () => ({
  usePessoaResumo: () => ({ data: undefined }),
}));
vi.mock("@/hooks/useRoteiros", () => ({
  useCriarRoteiro: () => ({ criar: m.criar, isPending: false }),
  baixarRoteiroPdf: m.pdf,
}));
vi.mock("@/hooks/useCardHub", () => ({
  useImoveisBusca: () => ({ data: { items: [] }, isPending: false, isFetching: false, isError: false }),
}));
vi.mock("@/hooks/useDebouncedValue", () => ({ useDebouncedValue: (v: string) => v }));
vi.mock("@dnd-kit/core", async (orig) => {
  const real = await orig<typeof import("@dnd-kit/core")>();
  return {
    ...real,
    DndContext: ({ children, onDragEnd }: { children: ReactNode; onDragEnd: (e: unknown) => void }) => {
      m.dragEnd.current = onDragEnd;
      return <>{children}</>;
    },
  };
});

import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";

import { ImovelInteressesList } from "./ImovelInteressesList";
import { interesse } from "./fixtures";

afterEach(() => {
  cleanup();
  Object.values(m).forEach((v) => typeof v === "function" && "mockReset" in v && v.mockReset());
});

function comLista(items = ["ONE9001", "ONE9002", "ONE9003"]) {
  m.useInteresses.mockReturnValue({
    data: { items: items.map((c) => interesse(c)), total: items.length },
    isPending: false,
    isFetching: false,
    isError: false,
  });
}

describe("ImovelInteressesList — rows", () => {
  it("renders photo, código, endereço + complemento, R$, origem and a checkbox per row", () => {
    comLista(["ONE9001"]);
    const { getByTestId } = render(<ImovelInteressesList clienteId="c1" />);
    const row = getByTestId("interesse-ONE9001");
    expect(row.querySelector("img")?.getAttribute("src")).toContain("ONE9001");
    expect(row.textContent).toContain("apto 52");
    expect(row.textContent).toMatch(/R\$\s?850\.000/);
    expect(getByTestId("interesse-origem").textContent).toBe("Lead");
    expect(getByTestId("interesse-check-ONE9001")).toBeTruthy();
  });

  it("states: skeleton only on first load, empty, error", () => {
    m.useInteresses.mockReturnValue({ data: undefined, isPending: true, isFetching: true, isError: false });
    const a = render(<ImovelInteressesList clienteId="c1" />);
    expect(a.queryByTestId("interesses-loading")).toBeTruthy();
    a.unmount();

    m.useInteresses.mockReturnValue({ data: { items: [], total: 0 }, isPending: false, isFetching: false, isError: false });
    const b = render(<ImovelInteressesList clienteId="c1" />);
    expect(b.queryByTestId("interesses-vazio")).toBeTruthy();
    b.unmount();

    m.useInteresses.mockReturnValue({ data: undefined, isPending: false, isFetching: false, isError: true });
    const c = render(<ImovelInteressesList clienteId="c1" />);
    expect(c.queryByTestId("interesses-erro")).toBeTruthy();
  });

  it("a refetch with rows on screen keeps the rows (spinner only)", () => {
    m.useInteresses.mockReturnValue({
      data: { items: [interesse("ONE9001")], total: 1 },
      isPending: false,
      isFetching: true,
      isError: false,
    });
    const { queryByTestId } = render(<ImovelInteressesList clienteId="c1" />);
    expect(queryByTestId("interesse-ONE9001")).toBeTruthy();
    expect(queryByTestId("interesses-refreshing")).toBeTruthy();
    expect(queryByTestId("interesses-loading")).toBeNull();
  });

  it("remove calls the mutation with the interesse id", () => {
    comLista(["ONE9001"]);
    const { getByTestId } = render(<ImovelInteressesList clienteId="c1" />);
    fireEvent.click(getByTestId("interesse-remover-ONE9001"));
    expect(m.remove.mock.calls[0][0]).toBe("int-ONE9001");
  });
});

describe("ImovelInteressesList — roteiro flow", () => {
  it("'Gerar roteiro' is disabled until at least one row is checked", () => {
    comLista();
    const { getByTestId } = render(<ImovelInteressesList clienteId="c1" />);
    const gerar = getByTestId("roteiro-gerar") as HTMLButtonElement;
    expect(gerar.disabled).toBe(true);

    fireEvent.click(getByTestId("interesse-check-ONE9002"));
    expect(gerar.disabled).toBe(false);

    fireEvent.click(getByTestId("interesse-check-ONE9002"));
    expect(gerar.disabled).toBe(true);
  });

  it("🔴 posts the códigos in the REORDERED order with the date, then fetches the PDF", async () => {
    comLista();
    m.criar.mockResolvedValue({ id: "rot-1" });
    m.pdf.mockResolvedValue(undefined);
    const { getByTestId } = render(<ImovelInteressesList clienteId="c1" atendimentoId="at-1" />);

    for (const c of ["ONE9001", "ONE9002", "ONE9003"]) {
      fireEvent.click(getByTestId(`interesse-check-${c}`));
    }
    fireEvent.click(getByTestId("roteiro-gerar"));

    // Dialog opens in list order…
    const ordem = () =>
      Array.from(
        getByTestId("roteiro-lista").querySelectorAll("[data-testid^='imovel-visita-ONE']"),
      ).map((e) => e.getAttribute("data-testid")!.replace("imovel-visita-", ""));
    expect(ordem()).toEqual(["ONE9001", "ONE9002", "ONE9003"]);

    // …the user drags ONE9003 to the top.
    const { act } = await import("@testing-library/react");
    act(() => m.dragEnd.current!({ active: { id: "ONE9003" }, over: { id: "ONE9001" } }));
    expect(ordem()).toEqual(["ONE9003", "ONE9001", "ONE9002"]);

    // Date is required.
    const confirmar = getByTestId("roteiro-salvar") as HTMLButtonElement;
    expect(confirmar.textContent).toContain("Confirmar ordem do roteiro");
    expect(confirmar.disabled).toBe(true);
    fireEvent.change(getByTestId("roteiro-data-visita"), { target: { value: "2026-10-10" } });
    fireEvent.click(confirmar);

    await waitFor(() => expect(m.criar).toHaveBeenCalledTimes(1));
    expect(m.criar).toHaveBeenCalledWith({
      titulo: null,
      imoveis: ["ONE9003", "ONE9001", "ONE9002"],
      data_visita: "2026-10-10",
      atendimento_id: "at-1",
    });
    await waitFor(() => expect(m.pdf).toHaveBeenCalledWith("c1", "rot-1"));
  });

  it("only the ticked rows go to the dialog", () => {
    comLista();
    const { getByTestId } = render(<ImovelInteressesList clienteId="c1" />);
    fireEvent.click(getByTestId("interesse-check-ONE9003"));
    fireEvent.click(getByTestId("roteiro-gerar"));
    const codigos = Array.from(
      getByTestId("roteiro-lista").querySelectorAll("[data-testid^='imovel-visita-ONE']"),
    ).map((e) => e.getAttribute("data-testid"));
    expect(codigos).toEqual(["imovel-visita-ONE9003"]);
  });

  it("a failed create does not fetch a PDF and keeps the dialog open", async () => {
    comLista(["ONE9001"]);
    m.criar.mockRejectedValue(new Error("Informe a data da visita."));
    const { getByTestId, queryByTestId } = render(<ImovelInteressesList clienteId="c1" />);
    fireEvent.click(getByTestId("interesse-check-ONE9001"));
    fireEvent.click(getByTestId("roteiro-gerar"));
    fireEvent.change(getByTestId("roteiro-data-visita"), { target: { value: "2026-10-10" } });
    fireEvent.click(getByTestId("roteiro-salvar"));
    await waitFor(() => expect(m.criar).toHaveBeenCalled());
    expect(m.pdf).not.toHaveBeenCalled();
    expect(queryByTestId("criar-roteiro-dialog")).toBeTruthy();
  });
});

describe("ImovelInteressesList — adicionar interesse", () => {
  it("opens the search popup", () => {
    comLista();
    const { getByTestId, queryByTestId } = render(<ImovelInteressesList clienteId="c1" />);
    expect(queryByTestId("adicionar-interesse-dialog")).toBeNull();
    fireEvent.click(getByTestId("interesse-adicionar"));
    expect(queryByTestId("adicionar-interesse-dialog")).toBeTruthy();
    expect(queryByTestId("imovel-busca-input")).toBeTruthy();
  });
});
