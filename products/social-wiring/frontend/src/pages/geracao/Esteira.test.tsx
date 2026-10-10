/** Esteira page — URL-backed filters (marca/busca/membro/arquivados) reach the board query. API mocked. */
import "@testing-library/jest-dom/vitest";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({
  board: vi.fn(),
  marcas: vi.fn(),
  equipe: vi.fn(),
}));

vi.mock("@/components/geracao/esteira/EsteiraBoard", () => ({
  EsteiraBoard: ({ filtros, onOpenPost }: any) => {
    m.board(filtros);
    return <button onClick={() => onOpenPost("p9")}>board</button>;
  },
}));
vi.mock("@/components/geracao/esteira/EquipeDialog", () => ({
  EquipeDialog: ({ open }: any) => (open ? <div>equipe-aberta</div> : null),
}));
vi.mock("@/components/geracao/esteira/NovoPostDialog", () => ({
  NovoPostDialog: ({ open, marcaIdInicial }: any) => (open ? <div>novo-post:{marcaIdInicial}</div> : null),
}));
vi.mock("@/hooks/useMarcas", () => ({ useMarcas: () => m.marcas() }));
vi.mock("@/hooks/geracao/useEsteira", () => ({ useEquipe: () => m.equipe() }));

import Esteira from "./Esteira";

const marcas = [
  { id: "m1", name: "Marca Um" },
  { id: "m2", name: "Marca Dois" },
];

function montar(url = "/media-creation/esteira", onOpenPost?: (id: string) => void) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[url]}>
        <Esteira onOpenPost={onOpenPost} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
const ultimo = () => m.board.mock.calls.at(-1)![0];

beforeEach(() => {
  window.localStorage.clear();
  m.marcas.mockReturnValue({ data: marcas, isPending: false });
  m.equipe.mockReturnValue({ data: [{ id: "u1", nome: "Ana" }] });
});
afterEach(() => {
  cleanup();
  m.board.mockReset();
});

describe("Esteira page filters", () => {
  it("sem param e sem marca salva: todas as marcas", () => {
    montar();
    expect(ultimo().marca_id).toBeUndefined();
    expect(screen.getByLabelText("Marca")).toHaveValue("todas");
    expect(screen.getByText("Esteira")).toBeInTheDocument();
  });

  it("primeira visita usa a marca lembrada (sw.pesquisa.marca)", () => {
    window.localStorage.setItem("sw.pesquisa.marca", "m2");
    montar();
    expect(ultimo().marca_id).toBe("m2");
  });

  it("?marca= vence a marca lembrada e 'todas' limpa o filtro", () => {
    window.localStorage.setItem("sw.pesquisa.marca", "m2");
    montar("/x?marca=m1");
    expect(ultimo().marca_id).toBe("m1");
    fireEvent.change(screen.getByLabelText("Marca"), { target: { value: "todas" } });
    expect(ultimo().marca_id).toBeUndefined();
  });

  it("escolher marca filtra e lembra a escolha", () => {
    montar();
    fireEvent.change(screen.getByLabelText("Marca"), { target: { value: "m2" } });
    expect(ultimo().marca_id).toBe("m2");
    expect(window.localStorage.getItem("sw.pesquisa.marca")).toBe("m2");
  });

  it("membro e arquivados entram nos filtros", () => {
    montar();
    fireEvent.change(screen.getByLabelText("Membro"), { target: { value: "u1" } });
    expect(ultimo().membro_id).toBe("u1");
    fireEvent.click(screen.getByLabelText("Mostrar arquivados"));
    expect(ultimo().incluir_arquivados).toBe(true);
  });

  it("busca é debounced", async () => {
    montar();
    await userEvent.type(screen.getByLabelText("Buscar"), "café");
    await waitFor(() => expect(ultimo().busca).toBe("café"));
  });

  it("abre equipe e novo post (prefilled com a marca filtrada); onOpenPost é repassado", () => {
    const onOpen = vi.fn();
    montar("/x?marca=m1", onOpen);
    fireEvent.click(screen.getByText("Equipe"));
    expect(screen.getByText("equipe-aberta")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Novo post"));
    expect(screen.getByText("novo-post:m1")).toBeInTheDocument();
    fireEvent.click(screen.getByText("board"));
    expect(onOpen).toHaveBeenCalledWith("p9");
  });
});
