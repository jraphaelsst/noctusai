/** Guia de documentos page — sections, anchors, search, hash deep link, states (contract fixture). */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const api = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));

import GuiaDocumentos from "./GuiaDocumentos";
import { GUIA_FIXTURE } from "@/components/guia/guiaFixture";

function montar(url = "/guia-documentos") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[url]}>
        <GuiaDocumentos />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  api.get.mockReset();
  api.get.mockResolvedValue(GUIA_FIXTURE);
});
afterEach(cleanup);

describe("Guia de documentos", () => {
  it("shows a skeleton, then the five sections in order", async () => {
    montar();
    expect(screen.getByTestId("guia-carregando")).toBeTruthy();
    await screen.findByTestId("guia-etapas");
    const ids = Array.from(document.querySelectorAll("section")).map((s) => s.id);
    expect(ids).toEqual(["fluxo-do-lead", "dados-obrigatorios", "documentos", "certidoes", "busca-por-dado"]);
  });

  it("Fluxo do lead: ordered stages with bloco, exigências (linked to their anchors) and observação", async () => {
    montar();
    const etapa = await screen.findByTestId("guia-etapa-analise_partes");
    expect(etapa.id).toBe("etapa-analise_partes");
    expect(etapa.textContent).toContain("2");
    expect(etapa.textContent).toContain("Jurídico");
    expect(within(etapa).getByRole("link", { name: "RG" }).getAttribute("href")).toBe("/guia-documentos#documento-rg");
    expect(within(etapa).getByRole("link", { name: "Receita Federal" }).getAttribute("href")).toBe(
      "/guia-documentos#certidao-cnd_federal",
    );
    expect(etapa.textContent).toContain("certidões de todos os vendedores");
  });

  it("Dados obrigatórios list their source documents; Documentos cards show fields + uses", async () => {
    montar();
    const dado = await screen.findByTestId("guia-dado-identidade");
    expect(dado.textContent).toContain("Vem de: RG, CNH");
    expect(dado.textContent).toContain("Um documento basta.");
    expect(screen.getByTestId("guia-dado-celular").textContent).toContain("Preenchido à mão.");
    const rg = screen.getByTestId("guia-documento-rg");
    expect(rg.id).toBe("documento-rg");
    expect(rg.textContent).toContain("Nome completo");
    expect(rg.textContent).toContain("Qualificação no contrato");
    expect(screen.getByTestId("guia-documento-certidao_casamento").textContent).toContain("Nenhum campo lido");
  });

  it("Certidões table: linha, rótulo, fonte, requisitos, credencial", async () => {
    montar();
    const tabela = await screen.findByTestId("guia-certidoes");
    expect(within(tabela).getAllByRole("row")).toHaveLength(4); // header + 3
    const federal = screen.getByTestId("guia-certidao-cnd_federal");
    expect(federal.id).toBe("certidao-cnd_federal");
    expect(federal.textContent).toContain("5.1");
    expect(federal.textContent).toContain("CPF + data de nascimento");
    expect(federal.textContent).toContain("Automática (InfoSimples)");
    expect(screen.getByTestId("guia-certidao-debitos_nao_inscritos").textContent).toContain("Login GOV.BR do escritório");
    const tjsp = screen.getByTestId("guia-certidao-tjsp");
    expect(tjsp.textContent).toContain("Manual");
    expect(tjsp.textContent).toContain("TJSP entrega por e-mail");
  });

  it("Busca por dado: typing 'data de nascimento' lists the documents that supply it", async () => {
    montar();
    const input = await screen.findByTestId("guia-busca-input");
    expect(screen.getByTestId("guia-busca-resultados").children).toHaveLength(3);
    fireEvent.change(input, { target: { value: "data de nascimento" } });
    const resultados = screen.getByTestId("guia-busca-resultados");
    expect(resultados.children).toHaveLength(1);
    const linha = screen.getByTestId("guia-campo-data_nascimento");
    expect(linha.id).toBe("campo-data_nascimento");
    expect(within(linha).getAllByRole("link").map((a) => a.textContent)).toEqual(["RG", "CNH"]);
    fireEvent.change(input, { target: { value: "xyz" } });
    expect(screen.getByText('Nenhum dado encontrado para "xyz".')).toBeTruthy();
  });

  it("a hash deep link scrolls to and highlights its anchor", async () => {
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    montar("/guia-documentos#certidao-tjsp");
    const alvo = await screen.findByTestId("guia-certidao-tjsp");
    expect(scroll).toHaveBeenCalled();
    expect(alvo.className).toContain("ring-2");
    expect(screen.getByTestId("guia-certidao-cnd_federal").className).not.toContain("ring-2");
  });

  it("a refused load is shown with a retry, never as empty sections", async () => {
    api.get.mockRejectedValue(Object.assign(new Error("[500] boom"), { status: 500 }));
    montar();
    expect((await screen.findByTestId("guia-erro")).textContent).toContain("Não foi possível carregar o guia de documentos");
    expect(screen.queryByTestId("guia-etapas")).toBeNull();
  });
});
