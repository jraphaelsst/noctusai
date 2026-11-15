/** "i" popovers — content mapping off the guia-documentos contract (fixture). */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactElement } from "react";

const api = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));

import { CertidaoInfo, DadoObrigatorioInfo, DocumentoInfo } from "./GuiaInfo";
import { GUIA_FIXTURE } from "./guiaFixture";
import { buscarCampos, requisitosCertidao } from "@/lib/guiaDocumentos";

function montar(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  api.get.mockReset();
  api.get.mockResolvedValue(GUIA_FIXTURE);
});
afterEach(cleanup);

describe("selectors", () => {
  it("formats certidão requirements as the owner's sentences", () => {
    const [federal, debitos, tjsp] = GUIA_FIXTURE.certidoes;
    expect(requisitosCertidao(federal)).toEqual(["Precisa de: CPF + data de nascimento"]);
    expect(requisitosCertidao(debitos)).toEqual(["Precisa de: CPF", "Requer login GOV.BR do escritório"]);
    expect(requisitosCertidao(tjsp)).toEqual(["Emissão manual (sem consulta automática)"]);
  });

  it("busca por dado is accent/case-insensitive and word-based", () => {
    expect(buscarCampos(GUIA_FIXTURE, "data de nascimento").map((c) => c.campo)).toEqual(["data_nascimento"]);
    expect(buscarCampos(GUIA_FIXTURE, "NASCIMENTO data").map((c) => c.campo)).toEqual(["data_nascimento"]);
    expect(buscarCampos(GUIA_FIXTURE, "regime de bens").map((c) => c.campo)).toEqual(["regime_bens"]);
    expect(buscarCampos(GUIA_FIXTURE, "")).toHaveLength(3);
    expect(buscarCampos(GUIA_FIXTURE, "inexistente")).toEqual([]);
  });
});

describe("DocumentoInfo", () => {
  it("does not fetch until opened, then lists the fields read, the uses and the guide link", async () => {
    montar(<DocumentoInfo tipo="rg" rotulo="RG" />);
    expect(api.get).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Sobre: RG" }));
    const corpo = await screen.findByTestId("guia-info-documento");
    expect(api.get).toHaveBeenCalledWith("/api/guia-documentos");
    expect(corpo.textContent).toContain("Dados lidos deste documento");
    expect(corpo.textContent).toContain("Data de nascimento");
    expect(corpo.textContent).toContain("Usado em");
    expect(corpo.textContent).toContain("Certidão Receita (data de nascimento)");
    expect(screen.getByRole("link", { name: "Ver no guia" }).getAttribute("href")).toBe("/guia-documentos#documento-rg");
  });

  it("a document with no automatic fields says so and shows its observação", async () => {
    montar(<DocumentoInfo tipo="certidao_casamento" />);
    fireEvent.click(screen.getByRole("button", { name: "Sobre: certidao_casamento" }));
    const corpo = await screen.findByTestId("guia-info-documento");
    expect(corpo.textContent).toContain("Nenhum campo é lido automaticamente.");
    expect(corpo.textContent).toContain("leitura estruturada do regime de bens");
  });

  it("an unknown tipo is stated, not an empty bubble", async () => {
    montar(<DocumentoInfo tipo="desconhecido" />);
    fireEvent.click(screen.getByRole("button", { name: "Sobre: desconhecido" }));
    expect((await screen.findByTestId("guia-info-ausente")).textContent).toContain("ainda não está descrito");
  });

  it("a refused request is shown, never silent", async () => {
    api.get.mockRejectedValue(Object.assign(new Error("[500] boom"), { status: 500 }));
    montar(<DocumentoInfo tipo="rg" />);
    fireEvent.click(screen.getByRole("button", { name: "Sobre: rg" }));
    expect((await screen.findByTestId("guia-info-erro")).textContent).toContain("Não foi possível carregar o guia");
  });
});

describe("CertidaoInfo", () => {
  it("lists requisitos + GOV.BR credential + observação and links to its anchor", async () => {
    montar(<CertidaoInfo tipo="debitos_nao_inscritos" rotulo="Débitos não inscritos" />);
    fireEvent.click(screen.getByRole("button", { name: "Sobre: Débitos não inscritos" }));
    const corpo = await screen.findByTestId("guia-info-certidao");
    expect(corpo.textContent).toContain("5.9 · Débitos não inscritos");
    expect(corpo.textContent).toContain("Precisa de: CPF");
    expect(corpo.textContent).toContain("Requer login GOV.BR do escritório");
    expect(corpo.textContent).toContain("opcional por padrão");
    expect(screen.getByRole("link", { name: "Ver no guia" }).getAttribute("href")).toBe(
      "/guia-documentos#certidao-debitos_nao_inscritos",
    );
  });
});

describe("DadoObrigatorioInfo", () => {
  it("names the documents that supply the item (by label) and the dica/escopo", async () => {
    montar(<DadoObrigatorioInfo chave="identidade" rotulo="Documento de identidade" />);
    fireEvent.click(screen.getByRole("button", { name: "Sobre: Documento de identidade" }));
    const corpo = await screen.findByTestId("guia-info-dado");
    expect(Array.from(corpo.querySelectorAll("li")).map((l) => l.textContent)).toEqual(["RG", "CNH"]);
    expect(corpo.textContent).toContain("Um documento basta.");
    expect(corpo.textContent).toContain("Vale para: pessoa física");
    expect(screen.getByRole("link", { name: "Ver no guia" }).getAttribute("href")).toBe("/guia-documentos#dado-identidade");
  });

  it("an item no document supplies says it is filled by hand", async () => {
    montar(<DadoObrigatorioInfo chave="celular" />);
    fireEvent.click(screen.getByRole("button", { name: "Sobre: celular" }));
    expect((await screen.findByTestId("guia-info-dado")).textContent).toContain("Preenchido à mão");
  });
});
