/** ImovelNotasCard — owned notes: add / edit / remove (with confirmation). */
import { afterEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({
  useImovelNotas: vi.fn(),
  criar: vi.fn(),
  atualizar: vi.fn(),
  remover: vi.fn(),
  confirm: vi.fn(),
}));

vi.mock("@/hooks/useImovelDados", () => ({
  useImovelNotas: m.useImovelNotas,
  useImovelNotaMutations: () => ({
    criar: { mutate: m.criar, isPending: false, error: null, reset: vi.fn() },
    atualizar: { mutate: m.atualizar, isPending: false, error: null, reset: vi.fn() },
    remover: { mutate: m.remover, isPending: false, error: null },
  }),
}));
vi.mock("@noctusai/lib/components", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@noctusai/lib/components")>();
  return { ...actual, useConfirm: () => m.confirm };
});

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { ImovelNotasCard } from "./ImovelNotasCard";

afterEach(() => {
  cleanup();
  Object.values(m).forEach((f) => f.mockReset());
});

const nota = (id: string, texto: string, over = {}) => ({
  id,
  codigo: "AP1",
  texto,
  created_at: "2026-11-01T10:00:00Z",
  created_by: { id: "u1", nome: "Ana" },
  updated_at: "2026-11-01T10:00:00Z",
  updated_by: { id: "u1", nome: "Ana" },
  ...over,
});
const ok = (items: unknown[]) => ({ data: items, isPending: false, isFetching: false, isError: false });

describe("ImovelNotasCard", () => {
  it("shows a skeleton while loading, never the empty state", () => {
    m.useImovelNotas.mockReturnValue({ data: undefined, isPending: true, isFetching: true, isError: false });
    render(<ImovelNotasCard codigo="AP1" />);
    expect(screen.getByTestId("imovel-notas-skeleton")).toBeTruthy();
    expect(screen.queryByTestId("imovel-notas-vazio")).toBeNull();
  });

  it("shows the error state with retry when the list failed to load", () => {
    m.useImovelNotas.mockReturnValue({
      data: undefined, isPending: false, isFetching: false, isError: true,
      error: new Error("falhou"), failureCount: 1, refetch: vi.fn(),
    });
    render(<ImovelNotasCard codigo="AP1" />);
    expect(screen.getByTestId("imovel-notas-erro")).toBeTruthy();
    expect(screen.queryByTestId("imovel-notas-vazio")).toBeNull();
  });

  it("shows the empty state", () => {
    m.useImovelNotas.mockReturnValue(ok([]));
    render(<ImovelNotasCard codigo="AP1" />);
    expect(screen.getByTestId("imovel-notas-vazio")).toBeTruthy();
  });

  it("adds a note, and flags the typed draft as unsaved first", () => {
    m.useImovelNotas.mockReturnValue(ok([]));
    render(<ImovelNotasCard codigo="AP1" />);
    expect((screen.getByTestId("imovel-nota-adicionar") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByTestId("imovel-nota-novo-texto"), { target: { value: "Chave com o porteiro" } });
    expect(screen.getByTestId("imovel-nota-novo-nao-salva")).toBeTruthy();
    fireEvent.click(screen.getByTestId("imovel-nota-adicionar"));
    expect(m.criar).toHaveBeenCalledWith({ texto: "Chave com o porteiro" }, expect.any(Object));
  });

  it("edits a note in place", () => {
    m.useImovelNotas.mockReturnValue(ok([nota("n1", "antiga")]));
    render(<ImovelNotasCard codigo="AP1" />);
    fireEvent.click(screen.getByTestId("imovel-nota-editar"));
    fireEvent.change(screen.getByTestId("imovel-nota-edit-texto"), { target: { value: "nova" } });
    expect(screen.getByTestId("imovel-nota-nao-salva")).toBeTruthy();
    fireEvent.click(screen.getByTestId("imovel-nota-edit-salvar"));
    expect(m.atualizar).toHaveBeenCalledWith({ id: "n1", texto: "nova" }, expect.any(Object));
  });

  it("removes only after the operator confirms", async () => {
    m.useImovelNotas.mockReturnValue(ok([nota("n1", "x")]));
    m.confirm.mockResolvedValueOnce(false);
    render(<ImovelNotasCard codigo="AP1" />);
    fireEvent.click(screen.getByTestId("imovel-nota-remover"));
    await waitFor(() => expect(m.confirm).toHaveBeenCalledTimes(1));
    expect(m.confirm.mock.calls[0][0]).toMatchObject({ tone: "danger" });
    expect(m.remover).not.toHaveBeenCalled();

    m.confirm.mockResolvedValueOnce(true);
    fireEvent.click(screen.getByTestId("imovel-nota-remover"));
    await waitFor(() => expect(m.remover).toHaveBeenCalledWith({ id: "n1" }));
  });

  it("hides edit/remove on an optimistic row that has no server id yet", () => {
    m.useImovelNotas.mockReturnValue(ok([nota("optimistic:abc", "enviando")]));
    render(<ImovelNotasCard codigo="AP1" />);
    expect(screen.queryByTestId("imovel-nota-remover")).toBeNull();
  });
});
