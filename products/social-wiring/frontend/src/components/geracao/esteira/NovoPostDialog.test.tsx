/** NovoPostDialog — headline picker (only unbound), conta select (only when >1), create payload. */
import "@testing-library/jest-dom/vitest";
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ lista: vi.fn(), contas: vi.fn(), mutate: vi.fn() }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/hooks/geracao/useEsteira", () => ({ useCriarPost: () => ({ mutate: m.mutate, isPending: false }) }));
vi.mock("@/hooks/geracao/useHeadlines", () => ({
  useHeadlinesLista: (_marca: string | null, lista: string) => m.lista(lista),
}));
vi.mock("@/hooks/useIntegrationAccounts", () => ({
  useIntegrationAccounts: (o: unknown) => m.contas(o),
}));

import { NovoPostDialog } from "./NovoPostDialog";

const marcas: any[] = [{ id: "m1", name: "Marca Um" }];
const h = (id: string, texto: string, post: unknown = null) => ({ id, texto, post });

beforeEach(() => {
  m.lista.mockImplementation((lista: string) => ({
    data: {
      items:
        lista === "favoritas"
          ? [h("h1", "Fav livre"), h("h2", "Fav usada", { id: "p", titulo: "x", etapa_label: "Ideia" })]
          : [h("h3", "Sug livre")],
    },
  }));
  m.contas.mockReturnValue({ data: [] });
});
afterEach(() => {
  cleanup();
  m.mutate.mockReset();
});

const montar = () =>
  render(<NovoPostDialog open marcas={marcas} marcaIdInicial="m1" onClose={vi.fn()} />);

describe("NovoPostDialog", () => {
  it("lista só headlines sem post, Favoritas antes de Sugeridas", () => {
    montar();
    const opts = Array.from(screen.getByLabelText("Headline do post").querySelectorAll("option")).map((o) => o.textContent);
    expect(opts).toEqual(["Sem headline", "Fav livre", "Sug livre"]);
  });

  it("headline dispensa o título e vai como headline_id", () => {
    montar();
    expect(screen.getByText("Criar post")).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Headline do post"), { target: { value: "h3" } });
    fireEvent.click(screen.getByText("Criar post"));
    expect(m.mutate.mock.calls[0][0]).toMatchObject({ marca_id: "m1", headline_id: "h3", titulo: undefined });
  });

  it("conta: pede só as contas instagram da marca; select some com 1 conta (que é enviada)", () => {
    m.contas.mockReturnValue({ data: [{ id: "c1", account_label: "@um" }] });
    montar();
    expect(m.contas).toHaveBeenCalledWith({ provider: "instagram", marcaId: "m1" });
    expect(screen.queryByLabelText("Conta de destino")).toBeNull();
    fireEvent.change(screen.getByPlaceholderText(/Título do reel/), { target: { value: "T" } });
    fireEvent.click(screen.getByText("Criar post"));
    expect(m.mutate.mock.calls[0][0]).toMatchObject({ titulo: "T", conta_id: "c1" });
  });

  it("com 2+ contas mostra o select e envia a escolhida", () => {
    m.contas.mockReturnValue({
      data: [
        { id: "c1", account_label: "@um" },
        { id: "c2", account_label: "@dois" },
      ],
    });
    montar();
    fireEvent.change(screen.getByLabelText("Conta de destino"), { target: { value: "c2" } });
    fireEvent.change(screen.getByPlaceholderText(/Título do reel/), { target: { value: "T" } });
    fireEvent.click(screen.getByText("Criar post"));
    expect(m.mutate.mock.calls[0][0]).toMatchObject({ conta_id: "c2" });
  });
});
