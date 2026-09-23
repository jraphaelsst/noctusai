/**
 * ProvenienciaPanel — the "Proveniência" section: per-field data lineage.
 *
 * Presentational: every assertion drives the component with plain props, no
 * query client. Coverage: skeleton/error/empty/success states, the estado
 * chip per value, the source document block (tipo + nome + entrada +
 * "Abrir" link), and the vazio-state `fontes_possiveis` hint
 * ("Envie X em Y") with both a routable and a card-scoped `destino`.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import ProvenienciaPanel from "./ProvenienciaPanel";
import type { ProvenienciaItem } from "@/hooks/useProveniencia";

function item(over: Partial<ProvenienciaItem> = {}): ProvenienciaItem {
  return {
    entidade: "contrato",
    campo: "cpf_comprador",
    rotulo: "CPF do comprador",
    valor: null,
    estado: "vazio",
    origem: null,
    documento: null,
    em: null,
    fontes_possiveis: [],
    ...over,
  };
}

async function render(items: ProvenienciaItem[] | undefined, over: Record<string, unknown> = {}) {
  const rtl = await import("@testing-library/react");
  const { MemoryRouter } = await import("react-router-dom");
  const props = {
    items,
    showSkeleton: false,
    isRefreshing: false,
    isError: false,
    onRetry: vi.fn(),
    ...over,
  };
  rtl.render(
    <MemoryRouter>
      <ProvenienciaPanel {...(props as unknown as Parameters<typeof ProvenienciaPanel>[0])} />
    </MemoryRouter>,
  );
  return { ...rtl, props };
}

describe("ProvenienciaPanel", () => {
  it("shows the skeleton while loading", async () => {
    const { screen } = await render(undefined, { showSkeleton: true });
    expect(screen.getByTestId("proveniencia-skeleton")).toBeTruthy();
  });

  it("shows an error with a retry when the fetch fails", async () => {
    const onRetry = vi.fn();
    const { screen, fireEvent } = await render(undefined, { isError: true, onRetry });
    expect(screen.getByTestId("proveniencia-erro")).toBeTruthy();
    fireEvent.click(screen.getByText("Tentar novamente"));
    expect(onRetry).toHaveBeenCalled();
  });

  it("shows an empty state for a contract with no tracked fields", async () => {
    const { screen } = await render([]);
    expect(screen.getByTestId("proveniencia-vazio")).toBeTruthy();
  });

  it("renders rótulo, valor, and the estado chip for a confirmed field", async () => {
    const { screen } = await render([
      item({
        campo: "cpf_comprador",
        rotulo: "CPF do comprador",
        valor: "123.456.789-00",
        estado: "confirmado",
      }),
    ]);
    const card = screen.getByTestId("proveniencia-item-contrato-cpf_comprador");
    expect(card.textContent).toContain("CPF do comprador");
    expect(screen.getByTestId("proveniencia-valor-cpf_comprador").textContent).toBe(
      "123.456.789-00",
    );
    expect(screen.getByTestId("proveniencia-estado-cpf_comprador").textContent).toBe("Confirmado");
  });

  it("renders every estado's pt-BR label", async () => {
    const { screen } = await render([
      item({ campo: "a", estado: "vazio" }),
      item({ campo: "b", estado: "maquina_pendente" }),
      item({ campo: "c", estado: "manual" }),
      item({ campo: "d", estado: "conflito" }),
    ]);
    expect(screen.getByTestId("proveniencia-estado-a").textContent).toBe("Vazio");
    expect(screen.getByTestId("proveniencia-estado-b").textContent).toBe("Extraído (pendente)");
    expect(screen.getByTestId("proveniencia-estado-c").textContent).toBe("Manual");
    expect(screen.getByTestId("proveniencia-estado-d").textContent).toBe("Conflito");
  });

  it("🔴 shows a placeholder, never a blank line, for a null valor", async () => {
    const { screen } = await render([item({ campo: "cpf_comprador", valor: null })]);
    expect(screen.getByTestId("proveniencia-valor-cpf_comprador").textContent).toBe("—");
  });

  it("renders the source document — tipo + nome + entrada — with an 'Abrir' link for a routable entrada", async () => {
    const { screen } = await render([
      item({
        campo: "cpf_comprador",
        valor: "123",
        estado: "confirmado",
        documento: {
          id: "d1",
          tipo: "RG",
          nome: "rg-frente.pdf",
          entrada: "matriculas",
        },
      }),
    ]);
    const bloco = screen.getByTestId("proveniencia-documento-cpf_comprador");
    expect(bloco.textContent).toContain("RG");
    expect(bloco.textContent).toContain("rg-frente.pdf");
    expect(bloco.textContent).toContain("Extrator de matrículas");
    const link = screen.getByTestId(
      "proveniencia-documento-link-cpf_comprador",
    ) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("/matriculas");
  });

  it("🔴 a card-scoped entrada (cliente_card_upload) renders guidance, never a fabricated deep link", async () => {
    const { screen } = await render([
      item({
        campo: "nome_comprador",
        valor: "Ana",
        estado: "confirmado",
        documento: { id: "d2", tipo: "RG", nome: null, entrada: "cliente_card_upload" },
      }),
    ]);
    const guidance = screen.getByTestId("proveniencia-documento-link-nome_comprador");
    expect(guidance.tagName).not.toBe("A");
    expect(guidance.textContent).toContain("Geral");
  });

  it("an entrada with no known place (vista_mirror) renders the document with no link at all", async () => {
    const { screen } = await render([
      item({
        campo: "endereco",
        valor: "Rua X",
        estado: "confirmado",
        documento: { id: "d3", tipo: "Espelho Vista", nome: null, entrada: "vista_mirror" },
      }),
    ]);
    expect(screen.getByTestId("proveniencia-documento-endereco")).toBeTruthy();
    expect(screen.queryByTestId("proveniencia-documento-link-endereco")).toBeNull();
  });

  it("🔴 shows fontes_possiveis 'Envie X em Y' hints only while estado is vazio, with a routable destino", async () => {
    const { screen } = await render([
      item({
        campo: "rg_comprador",
        estado: "vazio",
        fontes_possiveis: [
          {
            tipo_documento: "RG",
            rotulo: "RG do comprador",
            entradas: ["cliente_card_upload", "parte_painel_upload"],
            destino: "/matriculas",
          },
        ],
      }),
    ]);
    const fontes = screen.getByTestId("proveniencia-fontes-rg_comprador");
    expect(fontes.textContent).toContain("Envie RG");
    const link = screen.getByTestId("proveniencia-fonte-destino-0") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("/matriculas");
  });

  it("a fontes_possiveis destino naming a card subpage renders guidance, not a link", async () => {
    const { screen } = await render([
      item({
        campo: "certidao",
        estado: "vazio",
        fontes_possiveis: [
          {
            tipo_documento: "Certidão de casamento",
            rotulo: "Certidão de casamento",
            entradas: ["parte_painel_upload"],
            destino: "contratos",
          },
        ],
      }),
    ]);
    const hint = screen.getByTestId("proveniencia-fonte-destino-0");
    expect(hint.querySelector("a")).toBeNull();
    expect(hint.textContent).toContain("Contratos");
  });

  it("omits fontes_possiveis hints once a field is no longer vazio", async () => {
    const { screen } = await render([
      item({
        campo: "rg_comprador",
        estado: "confirmado",
        valor: "12.345.678-9",
        fontes_possiveis: [
          { tipo_documento: "RG", rotulo: "RG", entradas: ["matriculas"], destino: "/matriculas" },
        ],
      }),
    ]);
    expect(screen.queryByTestId("proveniencia-fontes-rg_comprador")).toBeNull();
  });

  it("shows the refresh indicator while isRefreshing, alongside the existing list", async () => {
    const { screen } = await render([item({ campo: "a", estado: "confirmado", valor: "x" })], {
      isRefreshing: true,
    });
    expect(screen.getByTestId("proveniencia-lista").textContent).toContain("Atualizando…");
  });
});
