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
 *
 * Migration 159 — "Cadastrar como imóvel novo" no longer registers on a
 * single click: it reveals a required-address form first (owner rule
 * 2026-09-23), and a "did you mean one of these?" list of near-duplicates
 * (`useImoveisPossiveisDuplicatas`) shows above it when the search's zero
 * result might really be a mis-typed existing property — the EUROVILLE-535
 * duplicate-registration incident this closes.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const {
  mockUseImoveisBusca,
  mockUseImoveisPossiveisDuplicatas,
  mockUseRegistrarImovelManual,
  mockRegistrarMutate,
} = vi.hoisted(() => ({
  mockUseImoveisBusca: vi.fn(),
  mockUseImoveisPossiveisDuplicatas: vi.fn(),
  mockRegistrarMutate: vi.fn(),
  mockUseRegistrarImovelManual: vi.fn(),
}));
vi.mock("@/hooks/useCardHub", () => ({
  useImoveisBusca: mockUseImoveisBusca,
}));
vi.mock("@/hooks/useImovelRegistro", () => ({
  useImoveisPossiveisDuplicatas: mockUseImoveisPossiveisDuplicatas,
  useRegistrarImovelManual: mockUseRegistrarImovelManual,
}));
vi.mock("@/hooks/useDebouncedValue", () => ({
  useDebouncedValue: (v: string) => v,
}));

beforeEach(() => {
  mockUseRegistrarImovelManual.mockReturnValue({
    mutate: mockRegistrarMutate,
    isPending: false,
    isError: false,
  });
  mockUseImoveisPossiveisDuplicatas.mockReturnValue(busca([]));
});

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
  mockUseImoveisBusca.mockReset();
  mockUseImoveisPossiveisDuplicatas.mockReset();
  mockUseRegistrarImovelManual.mockReset();
  mockRegistrarMutate.mockReset();
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

/** Fills the 6 required fields of the "cadastrar novo" address form —
 *  `complemento` stays blank (optional, house/lot has no unit number). */
async function preencherEndereco(screen: Awaited<ReturnType<typeof render>>["screen"]) {
  const rtl = await import("@testing-library/react");
  rtl.fireEvent.change(screen.getByTestId("imovel-picker-novo-logradouro"), {
    target: { value: "Alameda Alemanha" },
  });
  rtl.fireEvent.change(screen.getByTestId("imovel-picker-novo-numero"), {
    target: { value: "535" },
  });
  rtl.fireEvent.change(screen.getByTestId("imovel-picker-novo-bairro"), {
    target: { value: "Euroville - Km 23" },
  });
  rtl.fireEvent.change(screen.getByTestId("imovel-picker-novo-cidade"), {
    target: { value: "Barueri" },
  });
  rtl.fireEvent.change(screen.getByTestId("imovel-picker-novo-uf"), {
    target: { value: "SP" },
  });
  rtl.fireEvent.change(screen.getByTestId("imovel-picker-novo-cep"), {
    target: { value: "06355-465" },
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

  it("labels a manually-registered imóvel as such, not as out of the catalog", async () => {
    mockUseImoveisBusca.mockReturnValue(
      busca([
        hit("EUROVILLE-535", { ativo_no_vista: false, fonte: "registry", origem: "manual" }),
      ]),
    );
    const { screen } = await render();

    await digitar("EUROVILLE-535");

    const opcao = screen.getByTestId("imovel-picker-opcao-EUROVILLE-535");
    expect(opcao.textContent).toContain("cadastrado manualmente");
    expect(opcao.textContent).not.toContain("fora do catálogo");
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

  it("offers to register a new imóvel when the search finds nothing (migration 149)", async () => {
    mockUseImoveisBusca.mockReturnValue(busca([]));
    const { screen } = await render();

    await digitar("OFFMKT01");

    expect(screen.getByTestId("imovel-picker-cadastrar-novo")).toBeTruthy();
  });

  it("clicking 'cadastrar novo' reveals the required-address form, not an immediate register (migration 159)", async () => {
    mockUseImoveisBusca.mockReturnValue(busca([]));
    const { screen, fireEvent } = await render();

    await digitar("OFFMKT01");
    fireEvent.click(screen.getByTestId("imovel-picker-cadastrar-novo"));

    expect(screen.getByTestId("imovel-picker-formulario-cadastro")).toBeTruthy();
    expect(mockRegistrarMutate).not.toHaveBeenCalled();
  });

  it("keeps 'cadastrar imóvel' disabled until every required field is filled", async () => {
    mockUseImoveisBusca.mockReturnValue(busca([]));
    const { screen, fireEvent } = await render();

    await digitar("OFFMKT01");
    fireEvent.click(screen.getByTestId("imovel-picker-cadastrar-novo"));

    expect(
      (screen.getByTestId("imovel-picker-novo-salvar") as HTMLButtonElement).disabled,
    ).toBe(true);

    await preencherEndereco(screen);

    expect(
      (screen.getByTestId("imovel-picker-novo-salvar") as HTMLButtonElement).disabled,
    ).toBe(false);
  });

  it("registering sends the address and picks the newly-given identity as the chosen imóvel", async () => {
    mockUseImoveisBusca.mockReturnValue(busca([]));
    mockRegistrarMutate.mockImplementation(
      (
        _body: { codigo: string; endereco: Record<string, unknown> },
        opts: { onSuccess: (r: { codigo: string }) => void },
      ) => {
        opts.onSuccess({ codigo: _body.codigo });
      },
    );
    const { screen, fireEvent, onChange } = await render();

    await digitar("offmkt01");
    fireEvent.click(screen.getByTestId("imovel-picker-cadastrar-novo"));
    await preencherEndereco(screen);
    fireEvent.click(screen.getByTestId("imovel-picker-novo-salvar"));

    expect(mockRegistrarMutate).toHaveBeenCalledWith(
      {
        codigo: "OFFMKT01",
        endereco: {
          logradouro: "Alameda Alemanha",
          numero: "535",
          complemento: null,
          bairro: "Euroville - Km 23",
          cidade: "Barueri",
          uf: "SP",
          cep: "06355-465",
        },
      },
      expect.anything(),
    );
    expect(onChange).toHaveBeenCalledWith("OFFMKT01");
  });

  it("shows near-duplicates above 'cadastrar novo' when the empty search might be a mis-typed existing property", async () => {
    mockUseImoveisBusca.mockReturnValue(busca([]));
    mockUseImoveisPossiveisDuplicatas.mockReturnValue(
      busca([hit("ONE7515", { empreendimento: "Euroville - Km 23" })]),
    );
    const { screen } = await render();

    await digitar("Euroville");

    expect(screen.getByTestId("imovel-picker-duplicatas")).toBeTruthy();
    expect(screen.getByTestId("imovel-picker-duplicata-ONE7515")).toBeTruthy();
    // Never instead of it — a genuine new property is still the common case.
    expect(screen.getByTestId("imovel-picker-cadastrar-novo")).toBeTruthy();
  });

  it("picking a near-duplicate reports it up, same as a normal search hit", async () => {
    mockUseImoveisBusca.mockReturnValue(busca([]));
    mockUseImoveisPossiveisDuplicatas.mockReturnValue(busca([hit("ONE7515")]));
    const { screen, fireEvent, onChange } = await render();

    await digitar("Euroville");
    fireEvent.click(screen.getByTestId("imovel-picker-duplicata-ONE7515"));

    expect(onChange).toHaveBeenCalledWith("ONE7515");
  });

  it("does not show near-duplicates when the search already found results", async () => {
    mockUseImoveisBusca.mockReturnValue(busca([hit("ONE9001")]));
    const { screen } = await render();

    await digitar("ONE9");

    expect(screen.queryByTestId("imovel-picker-duplicatas")).toBeNull();
    expect(mockUseImoveisPossiveisDuplicatas).toHaveBeenCalledWith("ONE9", false);
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
