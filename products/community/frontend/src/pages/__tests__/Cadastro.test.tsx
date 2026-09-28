/**
 * Cadastro (public signup) — CONTRACT.md §Identity `POST /api/cadastro`:
 * 409 texts verbatim; success screen with the care line; a paid tier's
 * "Entrar" continues to `/login?plano=<id>` → `/assinar?plano=<id>`.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }));
vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));
vi.mock("@/components/TurnstileWidget", () => ({
  TurnstileWidget: ({ onVerify }: { onVerify: (t: string) => void }) => (
    <button type="button" data-testid="turnstile-mock-verify" onClick={() => onVerify("test-token")}>
      Verificar
    </button>
  ),
}));
vi.mock("@noctusai/seed/infra", () => ({ supabase: {}, api: {}, default: {} }));

import Cadastro from "@/pages/Cadastro";
import { destinoAposLogin } from "@/pages/Login";

const PREMIUM_ID = "3f2a1b4c-0000-4000-8000-000000000002";
const PLANOS = {
  items: [
    { id: PREMIUM_ID, nome: "Premium", descricao: "Assiste e tem vez de fala", preco_centavos: 2700, ciclo: "mensal", beneficios: { feed: true, forum: true, chat: true, eventos: true }, metodos_disponiveis: ["pix"] },
    { id: "3f2a1b4c-0000-4000-8000-000000000000", nome: "Gratuito", descricao: null, preco_centavos: 0, ciclo: "mensal", beneficios: { feed: true, forum: true, chat: true, eventos: true }, metodos_disponiveis: [] },
  ],
  total: 2,
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Cadastro />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function preencher() {
  fireEvent.change(screen.getByLabelText(/Seu nome/), { target: { value: "Ana Souza" } });
  fireEvent.change(screen.getByLabelText(/E-mail/), { target: { value: "ana@x.com" } });
  fireEvent.change(screen.getByLabelText(/Crie uma senha/), { target: { value: "segredo123" } });
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByTestId("turnstile-mock-verify"));
}

beforeEach(() => vi.clearAllMocks());

describe("Cadastro", () => {
  it("renders tier names/prices from the API, free tier pre-selected", async () => {
    mockGet.mockResolvedValue(PLANOS);
    renderPage();
    expect(await screen.findByLabelText(/Gratuito · Gratuito/)).toBeChecked();
    expect(screen.getByLabelText(/Premium · R\$\s?27,00 por mês/)).not.toBeChecked();
    expect(mockGet).toHaveBeenCalledWith("/api/planos/publicos");
  });

  it("shows the 409 existing-email text verbatim", async () => {
    const { ApiError } = await import("@noctusai/lib");
    mockGet.mockResolvedValue(PLANOS);
    mockPost.mockRejectedValue(new ApiError(409, "Este e-mail já tem cadastro. Entre com sua senha."));
    renderPage();
    await screen.findByLabelText(/Gratuito · Gratuito/);
    preencher();
    fireEvent.click(screen.getByRole("button", { name: "Criar minha conta" }));
    expect(await screen.findByText("Este e-mail já tem cadastro. Entre com sua senha.")).toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith("/api/cadastro", {
      nome: "Ana Souza",
      email: "ana@x.com",
      telefone: null,
      senha: "segredo123",
      turnstile_token: "test-token",
      aceite_termos: true,
    });
  });

  it("paid tier: success screen carries the care line and continues to checkout after login", async () => {
    mockGet.mockResolvedValue(PLANOS);
    mockPost.mockResolvedValue({ membro_id: "m1", email: "ana@x.com", proximo_passo: "entrar" });
    renderPage();
    fireEvent.click(await screen.findByLabelText(/Premium/));
    preencher();
    fireEvent.click(screen.getByRole("button", { name: "Criar minha conta" }));
    expect(await screen.findByTestId("cadastro-sucesso")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("CVV 188");
    expect(screen.getByRole("link", { name: "Entrar" })).toHaveAttribute("href", `/login?plano=${PREMIUM_ID}`);
    expect(destinoAposLogin(PREMIUM_ID)).toBe(`/assinar?plano=${PREMIUM_ID}`);
  });

  it("free tier: Entrar goes to plain /login; non-uuid plano is ignored after login", async () => {
    mockGet.mockResolvedValue(PLANOS);
    mockPost.mockResolvedValue({ membro_id: "m1", email: "ana@x.com", proximo_passo: "entrar" });
    renderPage();
    await screen.findByLabelText(/Gratuito · Gratuito/);
    preencher();
    fireEvent.click(screen.getByRole("button", { name: "Criar minha conta" }));
    await waitFor(() => expect(screen.getByRole("link", { name: "Entrar" })).toHaveAttribute("href", "/login"));
    expect(destinoAposLogin("https://evil.example")).toBe("/");
    expect(destinoAposLogin(null)).toBe("/");
  });

  it("blocks submit client-side without accepting the terms", async () => {
    mockGet.mockResolvedValue(PLANOS);
    renderPage();
    await screen.findByLabelText(/Gratuito · Gratuito/);
    fireEvent.change(screen.getByLabelText(/Seu nome/), { target: { value: "Ana" } });
    fireEvent.change(screen.getByLabelText(/E-mail/), { target: { value: "ana@x.com" } });
    fireEvent.change(screen.getByLabelText(/Crie uma senha/), { target: { value: "segredo123" } });
    fireEvent.click(screen.getByTestId("turnstile-mock-verify"));
    fireEvent.click(screen.getByRole("button", { name: "Criar minha conta" }));
    expect(await screen.findByText("É preciso aceitar os termos.")).toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();
  });
});
