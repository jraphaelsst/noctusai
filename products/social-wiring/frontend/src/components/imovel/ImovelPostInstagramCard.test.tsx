/** ImovelPostInstagramCard — list / add / remove of the Instagram posts mapped to an imóvel. */
import { afterEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ query: vi.fn(), adicionar: vi.fn(), remover: vi.fn(), addState: {} as Record<string, unknown> }));

vi.mock("@/hooks/useImovelPostsInstagram", () => ({
  useImovelPostsInstagram: m.query,
  useImovelPostInstagramMutations: () => ({
    adicionar: { mutate: m.adicionar, isPending: false, error: null, ...m.addState },
    remover: { mutate: m.remover, isPending: false, error: null },
  }),
}));

import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { ImovelPostInstagramCard } from "./ImovelPostInstagramCard";

afterEach(() => {
  cleanup();
  m.query.mockReset();
  m.adicionar.mockReset();
  m.remover.mockReset();
  m.addState = {};
});

const post = { id: "p1", shortcode: "AAAAA11111", codigo_imovel: "AP1", permalink: null, created_at: "2026-11-17T10:00:00Z" };

describe("ImovelPostInstagramCard", () => {
  it("shows a skeleton while loading, never the empty state", () => {
    m.query.mockReturnValue({ data: undefined, isPending: true, isError: false });
    render(<ImovelPostInstagramCard codigo="AP1" />);
    expect(screen.getByTestId("imovel-post-instagram-skeleton")).toBeTruthy();
    expect(screen.queryByTestId("imovel-post-instagram-vazio")).toBeNull();
  });

  it("shows the error state when the list failed to load", () => {
    m.query.mockReturnValue({ data: undefined, isPending: false, isError: true, error: new Error("falhou"), failureCount: 1, refetch: vi.fn() });
    render(<ImovelPostInstagramCard codigo="AP1" />);
    expect(screen.getByTestId("imovel-post-instagram-erro")).toBeTruthy();
  });

  it("shows the empty state in pt-BR", () => {
    m.query.mockReturnValue({ data: [], isPending: false, isError: false });
    render(<ImovelPostInstagramCard codigo="AP1" />);
    expect(screen.getByTestId("imovel-post-instagram-vazio").textContent).toContain("Nenhum post vinculado");
  });

  it("lists posts and removes one", () => {
    m.query.mockReturnValue({ data: [post], isPending: false, isError: false });
    render(<ImovelPostInstagramCard codigo="AP1" />);
    expect(screen.getByTestId("imovel-post-instagram-item").textContent).toContain("AAAAA11111");
    fireEvent.click(screen.getByTestId("imovel-post-instagram-remover"));
    expect(m.remover).toHaveBeenCalledWith({ id: "p1" });
  });

  it("adds a post by link and keeps the button disabled while empty", () => {
    m.query.mockReturnValue({ data: [], isPending: false, isError: false });
    render(<ImovelPostInstagramCard codigo="AP1" />);
    const botao = screen.getByTestId("imovel-post-instagram-adicionar") as HTMLButtonElement;
    expect(botao.disabled).toBe(true);
    fireEvent.change(screen.getByTestId("imovel-post-instagram-url"), { target: { value: " https://www.instagram.com/reel/AAAAA11111/ " } });
    fireEvent.click(botao);
    expect(m.adicionar.mock.calls[0][0]).toEqual({ url: "https://www.instagram.com/reel/AAAAA11111/" });
  });

  it("draws the server refusal under the form", () => {
    m.query.mockReturnValue({ data: [], isPending: false, isError: false });
    m.addState = { error: new Error("Informe o link de um post ou reel do Instagram") };
    render(<ImovelPostInstagramCard codigo="AP1" />);
    expect(screen.getByTestId("imovel-post-instagram-add-erro").textContent).toContain("Informe o link");
  });
});
