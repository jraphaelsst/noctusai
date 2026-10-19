import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const get = vi.fn();
vi.mock("@/lib/api", () => ({ api: { get: (...a: unknown[]) => get(...a) } }));

import AvisoPrivacidade from "./AvisoPrivacidade";

function renderPage(slug = "empresa-exemplo") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/privacidade/${slug}`]}>
        <Routes>
          <Route path="/privacidade/:slug" element={<AvisoPrivacidade />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const AVISO = {
  titulo: "Aviso de privacidade",
  empresa_nome: "Empresa Exemplo",
  contato_email: "privacidade@exemplo.test",
  contato_whatsapp: null,
  secoes: [{ n: "1", title: "Quem é o controlador", blocks: [{ p: "Empresa Exemplo." }, { ul: ["x"] }] }],
  versao: 3,
  atualizado_em: "2026-10-14T12:00:00+00:00",
};

describe("AvisoPrivacidade (public)", () => {
  beforeEach(() => {
    get.mockReset();
  });
  afterEach(cleanup);

  it("shows a skeleton, then the org-branded notice", async () => {
    get.mockResolvedValue({ data: AVISO });
    renderPage();
    expect(screen.getByTestId("aviso-loading")).toBeTruthy();
    expect((await screen.findByTestId("consent-brand")).textContent).toBe("Empresa Exemplo");
    expect(screen.getByText("Quem é o controlador")).toBeTruthy();
    expect(screen.queryByText(/NoctusAI/)).toBeNull();
    expect(get).toHaveBeenCalledWith("/api/public/julia/privacidade/empresa-exemplo");
  });

  it("404 shows 'Aviso não encontrado'", async () => {
    get.mockRejectedValue(Object.assign(new Error("[404] nope"), { status: 404 }));
    renderPage("x");
    expect(await screen.findByText("Aviso não encontrado")).toBeTruthy();
  });

  it("other errors show the generic error state", async () => {
    get.mockRejectedValue(Object.assign(new Error("boom"), { status: 500 }));
    renderPage();
    expect(await screen.findByText("Não foi possível carregar o aviso")).toBeTruthy();
  });
});
