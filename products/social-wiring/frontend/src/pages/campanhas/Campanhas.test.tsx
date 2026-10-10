/**
 * Campanhas page — list / create body / 409 on the veiculação row /
 * 400 unknown códigos / delete confirm. Real hooks, `api` stubbed at the
 * module boundary (the hooks' own seam), picker stubbed.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const m = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
  pick: "ONE1",
}));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: m.get, post: m.post, patch: m.patch, delete: m.del },
}));
vi.mock("@noctusai/lib", () => {
  class ApiError extends Error {
    status: number | null;
    body: unknown;
    constructor(status: number | null, message: string, body?: unknown) {
      super(status === null ? message : `[${status}] ${message}`);
      this.status = status;
      this.body = body;
    }
    get code(): string | null {
      const c = (this.body as { code?: unknown } | undefined)?.code;
      return typeof c === "string" ? c : null;
    }
  }
  return { ApiError };
});
vi.mock("@/components/card/ImovelCodigoPicker", () => ({
  ImovelCodigoPicker: (p: { onChange: (c: string | null) => void }) => (
    <button data-testid="picker-stub" onClick={() => p.onChange(m.pick)}>
      pick
    </button>
  ),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { ApiError } from "@noctusai/lib";
import Campanhas from "./Campanhas";

const camp = {
  id: "c1",
  nome: "Lançamento X",
  imoveis: [{ codigo: "ONE1", titulo: "Apto" }],
  veiculacoes: [{ id: "v1", canal: "meta_ads", nivel: "ad", ref_codigo: "999" }],
  created_at: "2026-10-01T10:00:00Z",
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Campanhas />
    </QueryClientProvider>,
  );
}

async function abrirNovaComVeiculacao(ref = "123") {
  renderPage();
  fireEvent.click(await screen.findByTestId("campanhas-nova"));
  fireEvent.change(screen.getByTestId("campanha-nome"), { target: { value: "Minha" } });
  fireEvent.click(screen.getByTestId("picker-stub"));
  fireEvent.click(screen.getByTestId("campanha-veic-add"));
  fireEvent.change(screen.getByTestId("campanha-veic-ref-0"), { target: { value: ref } });
}

beforeEach(() => {
  m.pick = "ONE1";
  m.get.mockResolvedValue({ data: [camp] });
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Campanhas", () => {
  it("renders the list", async () => {
    renderPage();
    expect(await screen.findByText("Lançamento X")).toBeTruthy();
    expect(screen.getByText("ONE1")).toBeTruthy();
    expect(screen.getByText("Anúncio · 999")).toBeTruthy();
  });

  it("shows the empty state", async () => {
    m.get.mockResolvedValue({ data: [] });
    renderPage();
    expect(await screen.findByTestId("campanhas-vazio")).toBeTruthy();
  });

  it("shows the error state", async () => {
    m.get.mockRejectedValue(new Error("boom"));
    renderPage();
    expect(await screen.findByTestId("campanhas-erro")).toBeTruthy();
  });

  it("create posts the contract body", async () => {
    m.post.mockResolvedValue({ data: camp });
    await abrirNovaComVeiculacao("123");
    fireEvent.click(screen.getByTestId("campanha-salvar"));
    await waitFor(() => expect(m.post).toHaveBeenCalled());
    expect(m.post).toHaveBeenCalledWith("/api/campanhas", {
      nome: "Minha",
      imovel_codigos: ["ONE1"],
      veiculacoes: [{ canal: "meta_ads", nivel: "ad", ref_codigo: "123" }],
    });
  });

  it("shows the 409 veiculacao_em_uso on its row", async () => {
    m.post.mockRejectedValue(
      new ApiError(409, "A veiculação 123 já pertence a outra campanha", {
        detail: "x",
        code: "veiculacao_em_uso",
      }),
    );
    await abrirNovaComVeiculacao("123");
    fireEvent.click(screen.getByTestId("campanha-salvar"));
    const row = await screen.findByTestId("campanha-veic-erro-0");
    expect(row.textContent).toContain("já pertence a outra campanha");
  });

  it("lists unknown códigos from a 400", async () => {
    m.post.mockRejectedValue(
      new ApiError(400, "Imóveis desconhecidos: ZZ1, ZZ2", { detail: "x" }),
    );
    await abrirNovaComVeiculacao();
    fireEvent.click(screen.getByTestId("campanha-salvar"));
    const erro = await screen.findByTestId("campanha-erro");
    expect(erro.textContent).toContain("ZZ1, ZZ2");
  });

  it("delete confirms, then calls DELETE", async () => {
    m.del.mockResolvedValue(undefined);
    renderPage();
    fireEvent.click(await screen.findByTestId("campanha-excluir-c1"));
    expect(m.del).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByTestId("campanha-excluir-confirmar"));
    await waitFor(() => expect(m.del).toHaveBeenCalledWith("/api/campanhas/c1"));
  });

  it("edit PATCHes the replaced imóveis + veiculações and refetches the list", async () => {
    m.patch.mockResolvedValue({ data: camp });
    renderPage();
    fireEvent.click(await screen.findByTestId("campanha-editar-c1"));
    expect((screen.getByTestId("campanha-nome") as HTMLInputElement).value).toBe("Lançamento X");
    fireEvent.change(screen.getByTestId("campanha-nome"), { target: { value: "Renomeada" } });
    fireEvent.click(screen.getByTestId("campanha-imovel-remover-ONE1"));
    m.pick = "ONE2";
    fireEvent.click(screen.getByTestId("picker-stub"));
    fireEvent.change(screen.getByTestId("campanha-veic-ref-0"), { target: { value: "555" } });
    const gets = m.get.mock.calls.length;
    fireEvent.click(screen.getByTestId("campanha-salvar"));
    await waitFor(() => expect(m.patch).toHaveBeenCalled());
    expect(m.patch).toHaveBeenCalledWith("/api/campanhas/c1", {
      nome: "Renomeada",
      imovel_codigos: ["ONE2"],
      veiculacoes: [{ canal: "meta_ads", nivel: "ad", ref_codigo: "555" }],
    });
    await waitFor(() => expect(m.get.mock.calls.length).toBeGreaterThan(gets));
  });
});
