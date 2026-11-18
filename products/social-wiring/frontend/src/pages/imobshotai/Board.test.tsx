/**
 * ImobShotAI board -- loading / empty / error / success against the contract's `GET /api/imobshotai/cards`
 * (mocked at the HTTP boundary, contract-shaped fixtures), the ref-prefix search (`q`), and the board columns.
 */
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";

vi.mock("@noctusai/seed/infra", async () => ({ api: (await import("@/test/imobshotaiApiMock")).api }));
vi.mock("@/hooks/useDebouncedValue", () => ({ useDebouncedValue: (v: string) => v }));

import { api, cardResumo, limparRotas, paginaDeCards, renderComQuery, rota } from "@/test/imobshotaiApiMock";
import Board from "./Board";

beforeEach(limparRotas);
afterEach(cleanup);

describe("ImobShotAI board", () => {
  it("shows a loading state first (no empty-state flash)", async () => {
    rota("GET", "/api/imobshotai/cards", () => new Promise(() => {}));
    renderComQuery(<Board />);
    expect(await screen.findByRole("status", { name: "Carregando quadro" })).toBeInTheDocument();
    expect(screen.queryByTestId("imobshotai-vazio")).toBeNull();
  });

  it("renders the 4 reachable etapas as columns with each card in its column", async () => {
    rota("GET", "/api/imobshotai/cards", () =>
      paginaDeCards([
        cardResumo({ id: "c1", etapa: "fotos_enviadas" }),
        cardResumo({
          id: "c2",
          etapa: "fotos_aprovadas",
          imovel: { org_id: "org-1", codigo: "ONE777", titulo: "Casa", bairro: "Moema" },
          capa_url: "https://cdn/capa.jpg",
          total_fotos: 8,
          fotos_aprovadas: 8,
        }),
      ]),
    );
    renderComQuery(<Board />);
    for (const t of ["Fotos enviadas", "Em edição", "Em revisão", "Fotos aprovadas"]) {
      expect(await screen.findByRole("heading", { name: t })).toBeInTheDocument();
    }
    expect(screen.queryByRole("heading", { name: "Concluído" })).toBeNull();
    const cards = screen.getAllByTestId("imobshotai-card");
    expect(cards).toHaveLength(2);
    expect(screen.getByText("ONE8990")).toBeInTheDocument();
    expect(screen.getByText("Pinheiros")).toBeInTheDocument();
    expect(screen.getByText("0/12 fotos aprovadas")).toBeInTheDocument();
    expect(screen.getByText("8/8 fotos aprovadas")).toBeInTheDocument();
    expect(screen.getByAltText("Capa de ONE777")).toHaveAttribute("src", "https://cdn/capa.jpg");
    expect(screen.getAllByText(/Nesta etapa há/)).toHaveLength(2);
  });

  it("empty: invites the first edição, with a link to the funnel", async () => {
    rota("GET", "/api/imobshotai/cards", () => paginaDeCards([]));
    renderComQuery(<Board />);
    expect(await screen.findByText("Nenhum imóvel no ImobShotAI ainda.")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Nova edição de fotos/ })[0]).toHaveAttribute("href", "/imobshotai/fotos/novo");
  });

  it("error: says what failed and retries", async () => {
    let falhar = true;
    rota("GET", "/api/imobshotai/cards", () => {
      if (falhar) throw new Error("boom");
      return paginaDeCards([cardResumo()]);
    });
    renderComQuery(<Board />);
    expect(await screen.findByText("Não foi possível carregar os imóveis do ImobShotAI.")).toBeInTheDocument();
    falhar = false;
    fireEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(await screen.findByText("ONE8990")).toBeInTheDocument();
  });

  it("search sends the ref prefix as `q` and says so when nothing matches", async () => {
    rota("GET", "/api/imobshotai/cards", (p) => (p.q ? paginaDeCards([]) : paginaDeCards([cardResumo()])));
    renderComQuery(<Board />);
    await screen.findByText("ONE8990");
    fireEvent.change(screen.getByLabelText("Buscar pelo código do imóvel"), { target: { value: "zz" } });
    expect(await screen.findByText("Nenhum imóvel com o código “zz”.")).toBeInTheDocument();
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith("/api/imobshotai/cards", expect.objectContaining({ q: "ZZ", page: 1, page_size: 100 })),
    );
  });

  it("flags when the board holds only part of the total", async () => {
    rota("GET", "/api/imobshotai/cards", () => paginaDeCards([cardResumo()], 230));
    renderComQuery(<Board />);
    expect(await screen.findByText(/Mostrando 1 de 230 imóveis/)).toBeInTheDocument();
  });
});
