/**
 * ImovelCodigoPicker — a SOLD imóvel is offered, and labelled.
 *
 * 🔴 The picker names the property of a negociação, and an imóvel leaves the
 * Vista catalog *because it was sold*. A picker that could only offer listed
 * properties could not name the one a closing deal is about — which is exactly
 * what the old mirror-only search did (prod 2026-08-25: 3017 in the registry,
 * 2008 in the mirror).
 *
 * The hook is mocked rather than the fetch: what is under test here is the
 * component's behaviour given a result set, and driving react-query + a
 * debounce timer through it would put neither in the assertions.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

const { mockUseImoveisBusca } = vi.hoisted(() => ({
  mockUseImoveisBusca: vi.fn(),
}));
vi.mock("@/hooks/useCardHub", () => ({ useImoveisBusca: mockUseImoveisBusca }));
vi.mock("@/hooks/useDebouncedValue", () => ({
  useDebouncedValue: (v: string) => v,
}));

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
  mockUseImoveisBusca.mockReset();
});

import { ImovelCodigoPicker } from "./ImovelCodigoPicker";
import type { ImovelBusca } from "@/types/cardHub";

function hit(codigo: string, over: Partial<ImovelBusca> = {}): ImovelBusca {
  return {
    codigo,
    titulo: `Apartamento ${codigo}`,
    empreendimento: null,
    logradouro: null,
    numero: null,
    complemento: null,
    bairro: "Pinheiros",
    cidade: "São Paulo",
    uf: null,
    cep: null,
    foto_destaque: null,
    captacao: null,
    corretores: [],
    ativo_no_vista: true,
    fonte: "imoveis",
    ...over,
  };
}

function busca(items: ImovelBusca[], over: Record<string, unknown> = {}) {
  return { data: { items }, isPending: false, isFetching: false, ...over };
}

async function render(value: string | null = null) {
  const rtl = await import("@testing-library/react");
  const onChange = vi.fn();
  const view = rtl.render(
    <ImovelCodigoPicker value={value} onChange={onChange} />,
  );
  return { ...rtl, ...view, onChange };
}

async function digitar(termo: string) {
  const rtl = await import("@testing-library/react");
  rtl.fireEvent.change(rtl.screen.getByTestId("imovel-picker-input"), {
    target: { value: termo },
  });
}

describe("ImovelCodigoPicker", () => {
  it("offers a delisted imóvel, labelled as out of the catalog", async () => {
    mockUseImoveisBusca.mockReturnValue(
      busca([hit("ONE4770", { ativo_no_vista: false, fonte: "registry" })]),
    );
    const { screen } = await render();

    await digitar("ONE4770");

    const opcao = screen.getByTestId("imovel-picker-opcao-ONE4770");
    expect(opcao).toBeTruthy();
    // Labelled, never filtered out: it is the right answer on a closing deal,
    // and the operator still has to see which of two códigos is the live one.
    expect(opcao.textContent).toContain("fora do catálogo");
  });

  it("does not badge a listed imóvel", async () => {
    mockUseImoveisBusca.mockReturnValue(busca([hit("ONE9001")]));
    const { screen } = await render();

    await digitar("ONE9001");

    expect(
      screen.getByTestId("imovel-picker-opcao-ONE9001").textContent,
    ).not.toContain("fora do catálogo");
  });

  it("reports the chosen código up", async () => {
    mockUseImoveisBusca.mockReturnValue(busca([hit("ONE9001")]));
    const { screen, fireEvent, onChange } = await render();

    await digitar("ONE9");
    fireEvent.click(screen.getByTestId("imovel-picker-opcao-ONE9001"));

    expect(onChange).toHaveBeenCalledWith("ONE9001");
  });

  it("shows the chosen código instead of the search field", async () => {
    mockUseImoveisBusca.mockReturnValue(busca([]));
    const { screen } = await render("ONE9001");

    expect(screen.getByTestId("imovel-picker-escolhido").textContent).toContain(
      "ONE9001",
    );
    expect(screen.queryByTestId("imovel-picker-input")).toBeNull();
  });

  it("clears to null, which is how a deal's property is un-named", async () => {
    mockUseImoveisBusca.mockReturnValue(busca([]));
    const { screen, fireEvent, onChange } = await render("ONE9001");

    fireEvent.click(screen.getByTestId("imovel-picker-limpar"));

    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("asks for two characters before searching", async () => {
    mockUseImoveisBusca.mockReturnValue(busca([]));
    const { screen } = await render();

    await digitar("O");

    expect(screen.getByText(/ao menos 2 caracteres/i)).toBeTruthy();
    expect(screen.queryByTestId("imovel-picker-vazio")).toBeNull();
  });

  it("does not claim 'nenhum imóvel' while a fetch is still in flight", async () => {
    // 🔴 `isPending || isFetching`, never `isLoading`: v5's `isLoading` is
    // false during a background refetch, so an empty branch keyed off it
    // renders "no results" over results that exist.
    mockUseImoveisBusca.mockReturnValue(busca([], { isFetching: true }));
    const { screen } = await render();

    await digitar("ONE9");

    expect(screen.queryByTestId("imovel-picker-vazio")).toBeNull();
    expect(screen.getByTestId("imovel-picker-buscando")).toBeTruthy();
  });

  it("keeps the previous term's results on screen while the next settles", async () => {
    mockUseImoveisBusca.mockReturnValue(
      busca([hit("ONE9001")], { isFetching: true }),
    );
    const { screen } = await render();

    await digitar("ONE90");

    expect(screen.getByTestId("imovel-picker-opcao-ONE9001")).toBeTruthy();
  });
});
