/**
 * ImobiliariasSection.test.tsx — the four states, create (CNPJ required +
 * mod-11 checked client-side), edit, "Incompleta: …" from `faltando`, and the
 * soft-delete confirmation with `contratos_em_uso`.
 *
 * Mock-the-hook pattern (same as `TestemunhasSection.test.tsx`).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const mockUseImobiliarias = vi.fn();
const mockCreate = vi.fn();
const mockUpdate = vi.fn();
const mockDelete = vi.fn();

vi.mock("@/hooks/useImobiliarias", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useImobiliarias")>(
    "@/hooks/useImobiliarias",
  );
  return {
    ...actual,
    useImobiliarias: mockUseImobiliarias,
    useCreateImobiliaria: () => ({ mutate: mockCreate, isPending: false }),
    useUpdateImobiliaria: () => ({ mutate: mockUpdate, isPending: false }),
    useDeleteImobiliaria: () => ({ mutate: mockDelete, isPending: false }),
  };
});

const CNPJ_VALIDO = "06.057.235/0001-04";

function query(over: Record<string, unknown> = {}) {
  return {
    data: { items: [], total: 0 },
    isPending: false,
    isFetching: false,
    isError: false,
    error: null,
    ...over,
  };
}

function imobiliaria(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: "i1",
    razao_social: "TANGERINO CONSULTORIA IMOBILIÁRIA LTDA",
    nome_fantasia: null,
    cnpj: CNPJ_VALIDO,
    creci_pj: null,
    creci_pj_regiao: null,
    responsavel_nome: "Maria",
    responsavel_creci: "98765",
    responsavel_creci_regiao: null,
    telefone: null,
    email: null,
    endereco_cep: null,
    endereco_logradouro: null,
    endereco_numero: null,
    endereco_complemento: null,
    endereco_bairro: null,
    endereco_cidade: "São Paulo",
    endereco_uf: "SP",
    faltando: [],
    contratos_em_uso: 0,
    created_at: null,
    updated_at: null,
    ...over,
  };
}

async function render() {
  const { render: rtlRender } = await import("@testing-library/react");
  const { ImobiliariasSection } = await import("./ImobiliariasSection");
  return rtlRender(<ImobiliariasSection />);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseImobiliarias.mockReturnValue(query());
});

describe("os quatro estados", () => {
  it("mostra o esqueleto só antes do primeiro carregamento", async () => {
    mockUseImobiliarias.mockReturnValue(
      query({ isPending: true, isFetching: true, data: undefined }),
    );
    const { getByText } = await render();
    expect(getByText("Carregando…")).toBeTruthy();
  });

  it("distingue lista vazia de falha na requisição", async () => {
    const vazio = await render();
    expect(vazio.getByText(/Nenhuma imobiliária cadastrada/)).toBeTruthy();
    (await import("@testing-library/react")).cleanup();

    mockUseImobiliarias.mockReturnValue(query({ isError: true, data: undefined }));
    const erro = await render();
    expect(erro.getByText(/Não foi possível carregar/)).toBeTruthy();
    expect(erro.queryByText(/Nenhuma imobiliária cadastrada/)).toBeNull();
  });

  it("um refetch por cima de dados mostra a lista e o indicador, nunca o esqueleto", async () => {
    mockUseImobiliarias.mockReturnValue(
      query({ isFetching: true, data: { items: [imobiliaria()], total: 1 } }),
    );
    const { getByText, getByTestId, queryByText } = await render();
    expect(getByText(/TANGERINO/)).toBeTruthy();
    expect(getByTestId("imobiliarias-refreshing")).toBeTruthy();
    expect(queryByText("Carregando…")).toBeNull();
  });

  it("lista a imobiliária com CNPJ formatado e marca a incompleta pelo que falta", async () => {
    mockUseImobiliarias.mockReturnValue(
      query({
        data: {
          items: [
            imobiliaria(),
            imobiliaria({
              id: "i2",
              razao_social: "OUTRA LTDA",
              faltando: ["responsavel_creci", "endereco_cidade"],
            }),
          ],
          total: 2,
        },
      }),
    );
    const { getByTestId, queryByTestId } = await render();
    expect(queryByTestId("imobiliaria-incompleta-i1")).toBeNull();
    expect(getByTestId("imobiliaria-incompleta-i2").textContent).toBe(
      "Incompleta: CRECI do responsável, cidade",
    );
  });
});

describe("criar", () => {
  async function abrir() {
    const utils = await render();
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(utils.getByTestId("imobiliaria-nova"));
    return { ...utils, fireEvent };
  }

  it("só habilita Salvar com razão social e CNPJ válido (mod-11)", async () => {
    const { getByTestId, queryByTestId, fireEvent } = await abrir();
    const salvar = getByTestId("imobiliaria-salvar") as HTMLButtonElement;
    expect(salvar.disabled).toBe(true);

    fireEvent.change(getByTestId("imobs-razao_social"), { target: { value: "Nova LTDA" } });
    fireEvent.change(getByTestId("imobs-cnpj"), { target: { value: "11.111.111/1111-11" } });
    expect(getByTestId("imobs-cnpj-invalido")).toBeTruthy();
    expect(salvar.disabled).toBe(true);

    fireEvent.change(getByTestId("imobs-cnpj"), { target: { value: CNPJ_VALIDO } });
    expect(queryByTestId("imobs-cnpj-invalido")).toBeNull();
    expect(salvar.disabled).toBe(false);
  });

  it("envia o payload com opcionais em branco como null", async () => {
    const { getByTestId, fireEvent } = await abrir();
    fireEvent.change(getByTestId("imobs-razao_social"), { target: { value: " Nova LTDA " } });
    fireEvent.change(getByTestId("imobs-cnpj"), { target: { value: CNPJ_VALIDO } });
    fireEvent.change(getByTestId("imobs-creci_pj_regiao"), { target: { value: "CRECI/SP" } });
    fireEvent.click(getByTestId("imobiliaria-salvar"));

    expect(mockCreate).toHaveBeenCalledTimes(1);
    const payload = mockCreate.mock.calls[0][0];
    expect(payload.razao_social).toBe("Nova LTDA");
    expect(payload.cnpj).toBe(CNPJ_VALIDO);
    expect(payload.creci_pj_regiao).toBe("CRECI/SP");
    expect(payload.nome_fantasia).toBeNull();
    expect(payload.endereco_cidade).toBeNull();
  });
});

describe("editar e remover", () => {
  it("editar abre o diálogo preenchido e envia PATCH", async () => {
    mockUseImobiliarias.mockReturnValue(query({ data: { items: [imobiliaria()], total: 1 } }));
    const { getByLabelText, getByTestId } = await render();
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(getByLabelText(/Editar TANGERINO/));
    expect((getByTestId("imobs-cnpj") as HTMLInputElement).value).toBe(CNPJ_VALIDO);
    fireEvent.change(getByTestId("imobs-endereco_cidade"), { target: { value: "Cotia" } });
    fireEvent.click(getByTestId("imobiliaria-salvar"));
    expect(mockUpdate).toHaveBeenCalledTimes(1);
    expect(mockUpdate.mock.calls[0][0].id).toBe("i1");
    expect(mockUpdate.mock.calls[0][0].patch.endereco_cidade).toBe("Cotia");
  });

  it("a confirmação de remoção informa contratos_em_uso e dispara o DELETE", async () => {
    mockUseImobiliarias.mockReturnValue(
      query({ data: { items: [imobiliaria({ contratos_em_uso: 22 })], total: 1 } }),
    );
    const { getByLabelText, getByTestId } = await render();
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(getByLabelText(/Remover TANGERINO/));
    expect(getByTestId("imobiliaria-remover-em-uso").textContent).toContain(
      "22 contratos usam esta imobiliária",
    );
    fireEvent.click(getByTestId("imobiliaria-confirmar-remover"));
    expect(mockDelete).toHaveBeenCalledWith("i1", expect.anything());
  });
});
