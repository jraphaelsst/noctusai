import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), patch: vi.fn(), post: vi.fn(), delete: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@noctusai/seed/infra", () => ({ api }));
vi.mock("@noctusai/lib/components", async (orig) => ({ ...(await orig<object>()), useConfirm: () => async () => true }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import JuliaModelos from "@/pages/julia/Modelos";
import JuliaDisparos from "@/pages/julia/Disparos";
import JuliaProprietarios from "@/pages/julia/Proprietarios";
import { NovoModeloModal, inserirParametro } from "./modelos/NovoModeloModal";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}
const M = { id: "m1", nome: "Boas-vindas", categoria: "Primeiro contato", conteudo: "Oi {{nome_pessoa}}, sou a {{nome_julia}}", status: "rascunho" };
const D = (id: string, status: string, tipo = "remarketing") => ({ id, nome: `Disp ${id}`, status, tipo, contatos: 3 });

const mockLista = (t: string) =>
  api.get.mockImplementation(async (u: string) => (u.endsWith("/1") ? { data: { ...D("1", "rascunho"), alvos: [] } } : { data: [D("1", "rascunho")], meta: { transporte: t } }));

beforeEach(() => Object.values(api).forEach((f) => f.mockReset()));
afterEach(cleanup);

describe("Modelo modal", () => {
  it("inserirParametro respects the 1024 cap", () => {
    expect(inserirParametro("ab", "nome_pessoa", 1)?.texto).toBe("a{{nome_pessoa}}b");
    expect(inserirParametro("x".repeat(1020), "nome_pessoa", 0)).toBeNull();
  });
  it("inserts params, counts chars, creates", async () => {
    api.post.mockResolvedValue({ data: M });
    wrap(<NovoModeloModal open onOpenChange={() => {}} />);
    fireEvent.change(screen.getByLabelText("Nome do modelo"), { target: { value: "Teste" } });
    fireEvent.change(screen.getByLabelText("Conteúdo da mensagem"), { target: { value: "Oi " } });
    fireEvent.click(screen.getByText("Nome da pessoa"));
    expect((screen.getByLabelText("Conteúdo da mensagem") as HTMLTextAreaElement).value).toContain("{{nome_pessoa}}");
    expect(screen.getByTestId("modelo-contador").textContent).toBe("18/1024");
    fireEvent.change(screen.getByLabelText("Conteúdo da mensagem"), { target: { value: "y".repeat(2000) } });
    expect(screen.getByTestId("modelo-contador").textContent).toBe("1024/1024");
    fireEvent.click(screen.getByText("Criar"));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/julia/modelos", expect.objectContaining({ nome: "Teste", categoria: "Outros" })));
  });
});

describe("Modelos page", () => {
  it("lists with category counts and simulates in the preview", async () => {
    api.get.mockResolvedValue({ data: [M] });
    wrap(<JuliaModelos />);
    fireEvent.click(await screen.findByTestId("modelo-card"));
    expect(screen.getByText("Primeiro contato (1)")).toBeTruthy();
    fireEvent.change(await screen.findByLabelText("Nome da pessoa"), { target: { value: "Ana" } });
    expect(screen.getByTestId("preview-bolha").textContent).toBe("Oi Ana, sou a {{nome_julia}}");
  });
  it("shows empty state", async () => {
    api.get.mockResolvedValue({ data: [] });
    wrap(<JuliaModelos />);
    expect(await screen.findByTestId("modelos-vazio")).toBeTruthy();
  });
});

describe("Disparos", () => {
  it("tabs filter with counts and badge shows when not cloud", async () => {
    api.get.mockResolvedValue({ data: [D("1", "rascunho"), D("2", "enviado")], meta: { transporte: "waha" } });
    wrap(<JuliaDisparos />);
    expect(await screen.findByText("Disp 1")).toBeTruthy();
    expect(screen.getByTestId("transporte-badge").textContent).toBe("Aguardando verificação da Meta");
    expect(screen.getByText("Rascunhos (1)")).toBeTruthy();
    fireEvent.mouseDown(screen.getByText("Enviados (1)"), { button: 0 });
    fireEvent.click(screen.getByText("Enviados (1)"));
    await waitFor(() => expect(screen.queryByText("Disp 1")).toBeNull());
    expect(screen.getByText("Disp 2")).toBeTruthy();
  });
  it("wizard creates a draft", async () => {
    api.get.mockImplementation(async (u: string) => (u.includes("modelos") ? { data: [M] } : { data: [], meta: {} }));
    api.post.mockResolvedValue({ data: D("9", "rascunho") });
    wrap(<JuliaDisparos />);
    fireEvent.click(await screen.findByText("Novo disparo"));
    fireEvent.change(await screen.findByLabelText("Nome do disparo"), { target: { value: "Campanha" } });
    fireEvent.click(screen.getByText("Avançar"));
    fireEvent.click(screen.getByText("Avançar"));
    await screen.findByText("Boas-vindas");
    fireEvent.change(screen.getByLabelText("Modelo de mensagem"), { target: { value: "m1" } });
    fireEvent.click(screen.getByText("Avançar"));
    fireEvent.click(screen.getByText("Salvar rascunho"));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/api/julia/disparos", expect.objectContaining({ nome: "Campanha", tipo: "remarketing", template_id: "m1" })),
    );
  });
  it("send disabled with explanation when not cloud; 409 handled when cloud", async () => {
    mockLista("waha");
    wrap(<JuliaDisparos />);
    fireEvent.click(await screen.findByTestId("disparo-linha"));
    const btn = (await screen.findByText("Enviar agora")) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(screen.getAllByText(/verificação da Meta/).length).toBeGreaterThan(0);
    cleanup();
    mockLista("cloud");
    api.post.mockRejectedValue({ body: { error: { code: "transporte_indisponivel", message: "x" } } });
    wrap(<JuliaDisparos />);
    fireEvent.click(await screen.findByTestId("disparo-linha"));
    const b2 = (await screen.findByText("Enviar agora")) as HTMLButtonElement;
    expect(b2.disabled).toBe(false);
    fireEvent.click(b2);
    const { toast } = await import("sonner");
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringContaining("verificação da Meta")));
  });
});

describe("Proprietários", () => {
  it("lists owners with send disabled when not cloud", async () => {
    api.get.mockResolvedValue({ data: [{ id: "p1", nome: "Dono", imovel_codigo: "AP1", status: "pendente" }], meta: { transporte: "waha" } });
    wrap(<JuliaProprietarios />);
    expect(await screen.findByText("Dono")).toBeTruthy();
    expect((screen.getByText("Solicitar atualização") as HTMLButtonElement).disabled).toBe(true);
  });
});
