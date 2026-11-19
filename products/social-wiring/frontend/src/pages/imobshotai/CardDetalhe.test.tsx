/**
 * ImobShotAI card detail -- header, photos by lote (original beside edited), empty videos section, event timeline,
 * and the friendly `404 card_nao_encontrado`. HTTP boundary mocked with contract-shaped fixtures.
 */
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

vi.mock("@noctusai/seed/infra", async () => ({ api: (await import("@/test/imobshotaiApiMock")).api }));

import { cardDetalhe, erroDoContrato, limparRotas, renderComQuery, rota } from "@/test/imobshotaiApiMock";
import CardDetalhePage from "./CardDetalhe";

function renderizar() {
  return renderComQuery(
    <Routes>
      <Route path="/imobshotai/imoveis/:cardId" element={<CardDetalhePage />} />
    </Routes>,
    "/imobshotai/imoveis/card-1",
  );
}

beforeEach(limparRotas);
afterEach(cleanup);

describe("ImobShotAI card detail", () => {
  it("loading first", async () => {
    rota("GET", "/api/imobshotai/cards/card-1", () => new Promise(() => {}));
    renderizar();
    expect(await screen.findByRole("status", { name: "Carregando imóvel" })).toBeInTheDocument();
  });

  it("success: header, photos grouped by lote, videos placeholder, timeline", async () => {
    rota("GET", "/api/imobshotai/cards/card-1", () => cardDetalhe());
    renderizar();
    expect(await screen.findByRole("heading", { name: "ONE8990" })).toBeInTheDocument();
    expect(screen.getByText("Em revisão")).toBeInTheDocument();
    expect(screen.getByText("Apartamento amplo · Pinheiros")).toBeInTheDocument();

    const lote = screen.getByTestId("imobshotai-lote-lote-1");
    expect(within(lote).getAllByTestId("imobshotai-foto")).toHaveLength(2);
    expect(within(lote).getAllByAltText("Foto — original")[0]).toHaveAttribute("src", "https://cdn/f1-o.jpg");
    expect(within(lote).getAllByAltText("Foto — editada")[0]).toHaveAttribute("src", "https://cdn/f1-e.jpg");
    expect(within(lote).getByText("Edição ainda não disponível")).toBeInTheDocument();

    expect(screen.getByText("Vídeo em breve")).toBeInTheDocument();
    const eventos = screen.getAllByTestId("imobshotai-evento").map((e) => e.textContent);
    expect(eventos[0]).toContain("Fotos enviadas → Em revisão");
    expect(eventos[2]).toContain("Imóvel adicionado ao ImobShotAI");
  });

  it("a card with no photos yet says so", async () => {
    rota("GET", "/api/imobshotai/cards/card-1", () => cardDetalhe({ lotes: [], fotos: [], eventos: [] }));
    renderizar();
    expect(await screen.findByTestId("imobshotai-sem-fotos")).toBeInTheDocument();
    expect(screen.getByText("Nenhum evento registrado.")).toBeInTheDocument();
  });

  it("404 card_nao_encontrado renders a friendly not-found", async () => {
    rota("GET", "/api/imobshotai/cards/card-1", () => {
      throw erroDoContrato(404, "card_nao_encontrado", "Card não encontrado.");
    });
    renderizar();
    expect(await screen.findByTestId("imobshotai-card-nao-encontrado")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voltar ao quadro" })).toHaveAttribute("href", "/imobshotai");
  });

  it("any other failure offers a retry", async () => {
    rota("GET", "/api/imobshotai/cards/card-1", () => {
      throw erroDoContrato(500, "erro_interno", "Erro.");
    });
    renderizar();
    expect(await screen.findByText("Não foi possível carregar este imóvel.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
  });
});
