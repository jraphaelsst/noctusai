import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@noctusai/lib";

const post = vi.fn();
const get = vi.fn();
const del = vi.fn();
vi.mock("@/lib/api", () => ({ api: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a), delete: (...a: unknown[]) => del(...a) } }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const navigate = vi.fn();
vi.mock("react-router-dom", async (orig) => ({ ...(await orig<typeof import("react-router-dom")>()), useNavigate: () => navigate }));

import { CriarAgentePlataformaDialog } from "../CriarAgentePlataformaDialog";
import { ExcluirAgenteDialog } from "../ExcluirAgenteDialog";
import { studioKeys } from "@/hooks/studio/keys";

function setup(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const spy = vi.spyOn(qc, "invalidateQueries");
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
  return { qc, spy };
}

beforeEach(() => {
  vi.clearAllMocks();
  get.mockResolvedValue({ items: [] });
});
afterEach(cleanup);

describe("CriarAgentePlataformaDialog", () => {
  it("creates by key, refreshes the list and navigates to the new empty agent", async () => {
    post.mockResolvedValue({ id: "1", key: "julia", org_id: "o", definition_scope: "plataforma", conteudo_modo: "linhas" });
    const onClose = vi.fn();
    const { spy } = setup(<CriarAgentePlataformaDialog onClose={onClose} />);
    expect((screen.getByTestId("criar-agente-submit") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByTestId("criar-agente-nome"), { target: { value: "Júlia Vendas" } });
    // the key is derived from the name and stays editable
    expect((screen.getByTestId("criar-agente-key") as HTMLInputElement).value).toBe("julia-vendas");
    fireEvent.change(screen.getByTestId("criar-agente-key"), { target: { value: "Julia" } });
    fireEvent.click(screen.getByTestId("criar-agente-submit"));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/studio/plataforma/agents", { key: "julia", nome: "Júlia Vendas" }));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/agentes/julia"));
    expect(spy).toHaveBeenCalledWith({ queryKey: studioKeys.list() });
  });

  it("surfaces 422 chave_nao_registrada", async () => {
    post.mockRejectedValue(new ApiError(422, "Chave não registrada.", { detail: "Chave não registrada.", code: "chave_nao_registrada" }));
    setup(<CriarAgentePlataformaDialog onClose={vi.fn()} />);
    fireEvent.change(screen.getByTestId("criar-agente-nome"), { target: { value: "Xyz" } });
    fireEvent.click(screen.getByTestId("criar-agente-submit"));
    expect((await screen.findByTestId("criar-agente-erro")).textContent).toMatch(/Chave não registrada/);
    expect(navigate).not.toHaveBeenCalled();
  });
});

describe("CriarAgentePlataformaDialog · gerar com IA", () => {
  const preencher = () => {
    fireEvent.click(screen.getByTestId("criar-modo-gerar"));
    fireEvent.change(screen.getByLabelText(/Nome do agente/), { target: { value: "Atendente Loja" } });
    fireEvent.change(screen.getByLabelText(/Objetivo/), { target: { value: "Atender clientes da loja" } });
    fireEvent.change(screen.getByLabelText(/Público/), { target: { value: "Clientes" } });
    fireEvent.change(screen.getByLabelText(/Canal/), { target: { value: "whatsapp" } });
  };

  it("sends the briefing in the same single POST and shows the cap + draft notice", async () => {
    post.mockResolvedValue({ id: "1", key: "atendente-loja", org_id: "o", definition_scope: "plataforma", conteudo_modo: "linhas", geracao: null });
    setup(<CriarAgentePlataformaDialog onClose={vi.fn()} />);
    fireEvent.click(screen.getByTestId("criar-modo-gerar"));
    expect(screen.getByTestId("criar-agente-aviso-ia").textContent).toMatch(/5\.00/);
    expect(screen.getByTestId("criar-agente-aviso-ia").textContent).toMatch(/rascunho|revise/i);
    preencher();
    expect((screen.getByTestId("criar-agente-key") as HTMLInputElement).value).toBe("atendente-loja");
    fireEvent.click(screen.getByTestId("criar-agente-submit"));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/api/studio/plataforma/agents", {
        key: "atendente-loja",
        nome: "Atendente Loja",
        briefing: { nome: "Atendente Loja", objetivo: "Atender clientes da loja", publico: "Clientes", canal: "whatsapp", idioma: "pt-BR" },
      }),
    );
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/agentes/atendente-loja"));
  });

  it("blocks submit client-side when the briefing breaks the contract limits", async () => {
    setup(<CriarAgentePlataformaDialog onClose={vi.fn()} />);
    fireEvent.click(screen.getByTestId("criar-modo-gerar"));
    fireEvent.change(screen.getByLabelText(/Nome do agente/), { target: { value: "Ab" } });
    fireEvent.change(screen.getByLabelText(/Objetivo/), { target: { value: "curto" } });
    fireEvent.click(screen.getByTestId("criar-agente-submit"));
    expect((await screen.findByTestId("criar-briefing-objetivo-erro")).textContent).toMatch(/mínimo de 10/);
    expect(screen.getByTestId("criar-briefing-canal-erro")).toBeTruthy();
    expect(post).not.toHaveBeenCalled();
  });

  it("sends instanciavel only when ticked (default off) and maps FastAPI 422 arrays", async () => {
    post.mockRejectedValueOnce(
      new ApiError(422, "Erro HTTP 422", { detail: [{ loc: ["body", "briefing", "objetivo"], msg: "String should have at least 10 characters", type: "x" }] }),
    );
    post.mockResolvedValueOnce({ id: "1", key: "ab", org_id: "o", definition_scope: "plataforma", conteudo_modo: "linhas" });
    setup(<CriarAgentePlataformaDialog onClose={vi.fn()} />);
    expect((screen.getByTestId("criar-agente-instanciavel") as HTMLInputElement).checked).toBe(false);
    fireEvent.change(screen.getByTestId("criar-agente-nome"), { target: { value: "Ab" } });
    fireEvent.click(screen.getByTestId("criar-agente-submit"));
    expect((await screen.findByTestId("criar-agente-erro")).textContent).toBe("briefing.objetivo: String should have at least 10 characters");
    expect(post.mock.calls[0][1]).toEqual({ key: "ab", nome: "Ab" });
    fireEvent.click(screen.getByTestId("criar-agente-instanciavel"));
    fireEvent.click(screen.getByTestId("criar-agente-submit"));
    await waitFor(() => expect(post.mock.calls[1][1]).toEqual({ key: "ab", nome: "Ab", instanciavel: true }));
  });

  it("takes key suggestions from the API list, never a literal", async () => {
    get.mockResolvedValue({ items: [{ key: "alfa", nome: "Alfa" }] });
    const { container } = render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <CriarAgentePlataformaDialog onClose={vi.fn()} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(document.querySelector('#criar-agente-chaves option[value="alfa"]')).toBeTruthy());
    expect(document.querySelector('#criar-agente-chaves option[value="julia"]')).toBeNull();
    void container;
  });
});

describe("ExcluirAgenteDialog", () => {
  it("gates the delete on typing the key, then deletes and invalidates the list", async () => {
    del.mockResolvedValue(null);
    const onClose = vi.fn();
    const { spy } = setup(<ExcluirAgenteDialog agentKey="julia" nome="Julia" onClose={onClose} />);
    const btn = screen.getByTestId("excluir-agente-confirm") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    fireEvent.change(screen.getByTestId("excluir-agente-key"), { target: { value: "juli" } });
    expect(btn.disabled).toBe(true);
    fireEvent.change(screen.getByTestId("excluir-agente-key"), { target: { value: "julia" } });
    expect(btn.disabled).toBe(false);
    fireEvent.click(btn);
    await waitFor(() => expect(del).toHaveBeenCalledWith("/api/studio/agents/julia"));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(spy).toHaveBeenCalledWith({ queryKey: studioKeys.list() });
  });

  it("shows the server's 409 reason plus a short hint", async () => {
    del.mockRejectedValue(
      new ApiError(409, "Erro HTTP 409", { code: "ativo", message: "O agente está ativo.", detail: "O agente está ativo." }),
    );
    const onClose = vi.fn();
    setup(<ExcluirAgenteDialog agentKey="julia" nome="Julia" onClose={onClose} />);
    fireEvent.change(screen.getByTestId("excluir-agente-key"), { target: { value: "julia" } });
    fireEvent.click(screen.getByTestId("excluir-agente-confirm"));
    expect((await screen.findByTestId("excluir-agente-erro")).textContent).toMatch(/O agente está ativo\./);
    expect(screen.getByTestId("excluir-agente-dica").textContent).toBe("Desligue o agente antes de excluir.");
    expect(onClose).not.toHaveBeenCalled();
  });
});
