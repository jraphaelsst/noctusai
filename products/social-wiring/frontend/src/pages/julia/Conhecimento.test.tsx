/**
 * Julia › Conhecimento — states, tabs, drawer, dirty-exit confirm, 409 path,
 * admin vs member, preview modal. `@/lib/api` is the seam (contract shapes).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfirmProvider } from "@noctusai/lib/components";

const h = vi.hoisted(() => ({ admin: true }));
const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), patch: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@noctusai/lib/design-system", async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useIsOrgAdmin: () => h.admin,
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import JuliaConhecimento from "./Conhecimento";
import { MSG_SAIR } from "@/components/julia/conhecimento/SecaoDrawer";

const CONHECIMENTO = {
  secoes: {
    politicas: { dados: { assinatura: "digital", chaves: "acompanhado", chaves_outro: "" }, versao: 3, updated_at: "2026-10-15T10:00:00Z" },
    telefones: { dados: [{ setor: "Vendas", telefone: "+5511900000000", principal: true }], versao: 1, updated_at: null },
  },
  preview_md: "# x",
  hash: "h1",
};

function conflict() {
  return Object.assign(new Error("[409] x"), { status: 409, body: { error: { code: "versao_conflito", message: "x" } } });
}

function setup(get?: (url: string) => Promise<unknown>) {
  api.get.mockImplementation(get ?? ((url: string) =>
    url === "/api/julia/conhecimento" ? Promise.resolve({ data: CONHECIMENTO })
      : url === "/api/julia/conhecimento/preview" ? Promise.resolve({ data: { markdown: "## Políticas\nAssinatura digital", hash: "h1" } })
        : Promise.reject(new Error(`unexpected ${url}`))));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><ConfirmProvider><JuliaConhecimento /></ConfirmProvider></QueryClientProvider>);
}

beforeEach(() => { Object.values(api).forEach((f) => f.mockReset()); h.admin = true; });
afterEach(cleanup);

describe("Julia Conhecimento", () => {
  it("shows the skeleton, then the Geral cards with saved + default data", async () => {
    setup();
    expect(screen.getByTestId("conhecimento-skeleton")).toBeTruthy();
    expect(await screen.findByTestId("card-politicas")).toBeTruthy();
    expect(screen.getByTestId("card-politicas").textContent).toContain("Digital");
    expect(screen.getByTestId("card-telefones").textContent).toContain("+5511900000000");
    expect(screen.getByTestId("card-recesso").textContent).toContain("Não"); // default, never saved
    for (const t of ["Geral", "Vendas", "Locação", "Perfil do WhatsApp", "Endereço e IPTU"]) expect(screen.getByRole("tab", { name: t })).toBeTruthy();
  });

  it("shows an error state with retry", async () => {
    setup(() => Promise.reject(new Error("boom")));
    expect(await screen.findByTestId("conhecimento-erro")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Tentar de novo" })).toBeTruthy();
  });

  it("member is read-only: no Editar buttons", async () => {
    h.admin = false;
    setup();
    await screen.findByTestId("card-politicas");
    expect(screen.queryByRole("button", { name: /Editar/ })).toBeNull();
  });

  it("saves with {dados, versao} and closes", async () => {
    api.put.mockResolvedValue({ data: { secao: "politicas", dados: {}, versao: 4 } });
    setup();
    fireEvent.click(await screen.findByRole("button", { name: "Editar Políticas" }));
    fireEvent.click(screen.getByLabelText("Físico"));
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/api/julia/conhecimento/politicas", {
      dados: { assinatura: "fisico", chaves: "acompanhado", chaves_outro: "" }, versao: 3 }));
    await waitFor(() => expect(screen.queryByTestId("secao-drawer")).toBeNull());
  });

  it("dirty exit asks for confirmation; keeping stays open, leaving closes", async () => {
    setup();
    fireEvent.click(await screen.findByRole("button", { name: "Editar Políticas" }));
    fireEvent.click(screen.getByLabelText("Físico"));
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(await screen.findByText(MSG_SAIR)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Continuar editando" }));
    await waitFor(() => expect(screen.queryByText(MSG_SAIR)).toBeNull());
    expect(screen.getByTestId("secao-drawer")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    fireEvent.click(await screen.findByRole("button", { name: "Sair" }));
    await waitFor(() => expect(screen.queryByTestId("secao-drawer")).toBeNull());
  });

  it("clean Cancelar closes without confirming", async () => {
    setup();
    fireEvent.click(await screen.findByRole("button", { name: "Editar Políticas" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    await waitFor(() => expect(screen.queryByTestId("secao-drawer")).toBeNull());
    expect(screen.queryByText(MSG_SAIR)).toBeNull();
  });

  it("409 shows the reload prompt; Recarregar refetches and retries on the new versao", async () => {
    api.put.mockRejectedValueOnce(conflict());
    setup();
    fireEvent.click(await screen.findByRole("button", { name: "Editar Políticas" }));
    fireEvent.click(screen.getByLabelText("Físico"));
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(await screen.findByTestId("conflito")).toBeTruthy();
    api.get.mockImplementation((u: string) => Promise.resolve({ data: u === "/api/julia/conhecimento"
      ? { ...CONHECIMENTO, secoes: { ...CONHECIMENTO.secoes, politicas: { dados: { assinatura: "digital_fisico", chaves: "acompanhado", chaves_outro: "" }, versao: 4, updated_at: null } } }
      : { markdown: "", hash: "" } }));
    fireEvent.click(screen.getByRole("button", { name: "Recarregar" }));
    await waitFor(() => expect(screen.queryByTestId("conflito")).toBeNull());
    api.put.mockResolvedValue({ data: { secao: "politicas", dados: {}, versao: 5 } });
    fireEvent.click(screen.getByLabelText("Físico"));
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(api.put).toHaveBeenLastCalledWith("/api/julia/conhecimento/politicas", expect.objectContaining({ versao: 4 })));
  });

  it("telefones: requires exactly one valid principal before PUT", async () => {
    setup();
    fireEvent.click(await screen.findByRole("button", { name: "Editar Telefones da empresa" }));
    fireEvent.change(screen.getByLabelText("Telefone 1"), { target: { value: "123" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect((await screen.findByTestId("erro-salvar")).textContent).toContain("telefone válido");
    expect(api.put).not.toHaveBeenCalled();
  });

  it("perfil tab: mockup + banner inside the drawer", async () => {
    setup();
    fireEvent.mouseDown(await screen.findByRole("tab", { name: "Perfil do WhatsApp" }), { button: 0 });
    fireEvent.click(await screen.findByRole("button", { name: "Editar Perfil do WhatsApp" }));
    expect(screen.getByTestId("perfil-mockup")).toBeTruthy();
    expect(screen.getByTestId("perfil-banner").textContent).toMatch(/aplicado quando a API oficial estiver ativa/i);
  });

  it("preview modal renders GET /preview markdown", async () => {
    setup();
    fireEvent.click(await screen.findByRole("button", { name: /Ver o que a Julia sabe/ }));
    expect((await screen.findByTestId("preview-md")).textContent).toContain("Assinatura digital");
  });
});
