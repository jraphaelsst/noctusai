/**
 * Permutas → "Imóveis em permuta": the registry tab (`PermutaAtivosLista`
 * + `PermutaAtivoDialog`). Four states, then the CRUD paths with the request
 * bodies they send — the backend body is a `StrictHttpModel`, so a key the
 * schema does not declare is a 422, and the PATCH semantics (omitted = keep,
 * null = clear, `interesses` = replace) are asserted rather than assumed.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor, within } from "@testing-library/react";

afterEach(() => cleanup());

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock("@noctusai/lib/design-system", () => ({
  TableSkeleton: () => <div data-testid="skeleton" />,
  Skeleton: () => <div data-testid="skeleton-linha" />,
}));

const { toastSuccess, toastError } = vi.hoisted(() => ({
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: toastSuccess, error: toastError } }));

// The real typeahead fetches /api/imoveis/busca; its own suite covers that.
vi.mock("@/components/interesses/ImovelBuscaTypeahead", () => ({
  ImovelBuscaTypeahead: ({ onSelect }: { onSelect: (i: { codigo: string }) => void }) => (
    <button type="button" onClick={() => onSelect({ codigo: "ONE9265" })}>
      escolher ONE9265
    </button>
  ),
}));

const { mockAtivos, mockCriar, mockAtualizar, mockRemover } = vi.hoisted(() => ({
  mockAtivos: vi.fn(),
  mockCriar: vi.fn(),
  mockAtualizar: vi.fn(),
  mockRemover: vi.fn(),
}));

vi.mock("@/hooks/usePermutas", async () => {
  const actual =
    await vi.importActual<typeof import("@/hooks/usePermutas")>("@/hooks/usePermutas");
  return {
    ...actual,
    usePermutaAtivos: mockAtivos,
    useCriarAtivo: () => ({ mutateAsync: mockCriar, isPending: false }),
    useAtualizarAtivo: () => ({ mutateAsync: mockAtualizar, isPending: false }),
    useRemoverAtivo: () => ({ mutateAsync: mockRemover, isPending: false }),
  };
});

import { PermutaAtivosLista } from "@/components/permutas/PermutaAtivosLista";

function query(over: Record<string, unknown> = {}) {
  return {
    data: [],
    isPending: false,
    isFetching: false,
    isError: false,
    error: null,
    ...over,
  };
}

function ativo(over: Record<string, unknown> = {}) {
  return {
    id: "a1",
    natureza: "imovel",
    imovel_codigo: "ONE9265",
    codigo: null,
    corretor_id: null,
    proprietario_nome: "Maria Souza",
    proprietario_telefone: "11999990000",
    proprietario_email: null,
    tipo_imovel: null,
    cidade: null,
    bairro: null,
    uf: null,
    zona: null,
    valor: null,
    faixa_preco_min: 800000,
    faixa_preco_max: 1000000,
    regiao_preferida: ["Granja Viana"],
    aceita_completar_diferenca: false,
    limite_complemento: null,
    percentual_min: 30,
    percentual_max: 50,
    observacoes: "casa sem escada",
    interesses_descricao: null,
    status: "ativo",
    origem: "permutas_legacy",
    tem_embedding: true,
    tem_embedding_interesses: true,
    interesses: [
      {
        id: "i1",
        tipo: "imovel",
        tipo_imovel: "Casa",
        zona: null,
        cidade: "Cotia",
        bairro: null,
        valor_minimo: null,
        valor_maximo: 900000,
        percentual_min: null,
        percentual_max: null,
        observacoes: "quintal amplo",
      },
    ],
    catalogo: {
      titulo: "Casa na Granja",
      categoria: "Casa",
      bairro: "Granja Viana",
      cidade: "Cotia",
      uf: "SP",
      valor_venda: 1200000,
    },
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockAtivos.mockReturnValue(query());
});

describe("os quatro estados", () => {
  it("esqueleto só antes do primeiro carregamento", () => {
    mockAtivos.mockReturnValue(query({ isPending: true, isFetching: true, data: undefined }));
    const { getByTestId, queryByText } = render(<PermutaAtivosLista />);
    expect(getByTestId("skeleton")).toBeTruthy();
    expect(queryByText(/Nenhum imóvel em permuta/)).toBeNull();
  });

  it("refetch mantém a lista montada", () => {
    mockAtivos.mockReturnValue(query({ data: [ativo()], isFetching: true }));
    const { queryByTestId, getByText } = render(<PermutaAtivosLista />);
    expect(queryByTestId("skeleton")).toBeNull();
    expect(getByText("Casa na Granja")).toBeTruthy();
    expect(queryByTestId("permuta-ativos-refreshing")).toBeTruthy();
  });

  it("vazio", () => {
    const { getByText } = render(<PermutaAtivosLista />);
    expect(getByText(/Nenhum imóvel em permuta/)).toBeTruthy();
  });

  it("erro é distinto de vazio", () => {
    mockAtivos.mockReturnValue(
      query({ isError: true, error: { message: "[500] boom" }, data: undefined }),
    );
    const { getByText, queryByText } = render(<PermutaAtivosLista />);
    expect(getByText(/Não foi possível carregar as permutas/)).toBeTruthy();
    expect(queryByText(/Nenhum imóvel em permuta/)).toBeNull();
  });

  it("mostra os campos-chave, com o catálogo para o imóvel-ponteiro", () => {
    mockAtivos.mockReturnValue(query({ data: [ativo()] }));
    const { getByText } = render(<PermutaAtivosLista />);
    expect(getByText("ONE9265")).toBeTruthy();
    expect(getByText("Casa na Granja")).toBeTruthy();
    expect(getByText("Granja Viana, Cotia, SP")).toBeTruthy();
    expect(getByText(/Maria Souza/)).toBeTruthy();
    expect(getByText(/R\$\s?800\.000 – R\$\s?1\.000\.000/)).toBeTruthy();
    expect(getByText(/casa sem escada/)).toBeTruthy();
  });

  it("sinaliza o imóvel que saiu do catálogo", () => {
    mockAtivos.mockReturnValue(query({ data: [ativo({ catalogo: null })] }));
    const { getByText } = render(<PermutaAtivosLista />);
    expect(getByText("Fora do catálogo")).toBeTruthy();
  });
});

describe("filtros", () => {
  it("a busca filtra por proprietário/descrição sem acento", () => {
    mockAtivos.mockReturnValue(
      query({
        data: [
          ativo(),
          ativo({
            id: "a2",
            imovel_codigo: "ONE1111",
            proprietario_nome: "João",
            observacoes: "apartamento",
            catalogo: { ...ativo().catalogo, titulo: "Apto Centro" },
          }),
        ],
      }),
    );
    const { getByLabelText, queryByText } = render(<PermutaAtivosLista />);
    fireEvent.change(getByLabelText("Buscar permutas"), { target: { value: "joao" } });
    expect(queryByText("Apto Centro")).toBeTruthy();
    expect(queryByText("Casa na Granja")).toBeNull();
  });

  it("a natureza e 'incluir inativos' vão para a consulta", () => {
    const { getByRole, getByLabelText } = render(<PermutaAtivosLista />);
    fireEvent.click(getByRole("button", { name: "Imóvel oferecido em permuta" }));
    expect(mockAtivos).toHaveBeenLastCalledWith("permuta_imovel", { incluirInativos: false });
    fireEvent.click(getByLabelText(/Incluir pausadas/));
    expect(mockAtivos).toHaveBeenLastCalledWith("permuta_imovel", { incluirInativos: true });
  });
});

describe("cadastrar", () => {
  it("permuta de imóvel trazido: envia só campos do schema, sem chaves vazias", async () => {
    mockCriar.mockResolvedValue({ id: "novo" });
    const { getByRole, getByLabelText, queryByTestId } = render(<PermutaAtivosLista />);
    fireEvent.click(getByRole("button", { name: /Nova permuta/ }));

    fireEvent.change(getByLabelText("Natureza"), { target: { value: "permuta_imovel" } });
    fireEvent.change(getByLabelText("Tipo de imóvel"), { target: { value: "Apartamento" } });
    fireEvent.change(getByLabelText("Valor (R$)"), { target: { value: "650000" } });
    fireEvent.change(getByLabelText("Nome"), { target: { value: "Carlos" } });
    fireEvent.change(getByLabelText("Descrição do interesse"), {
      target: { value: "casa térrea com quintal" },
    });
    fireEvent.change(getByLabelText("Regiões preferidas"), {
      target: { value: "Cotia, Granja Viana" },
    });
    fireEvent.click(getByRole("button", { name: /Adicionar critério/ }));
    fireEvent.change(getByLabelText("Interesse 1 — cidade"), { target: { value: "Cotia" } });
    fireEvent.change(getByLabelText("Interesse 1 — valor máximo"), {
      target: { value: "900000" },
    });
    fireEvent.click(getByRole("button", { name: "Cadastrar" }));

    await waitFor(() => expect(mockCriar).toHaveBeenCalledTimes(1));
    expect(mockCriar.mock.calls[0][0]).toEqual({
      natureza: "permuta_imovel",
      status: "ativo",
      tipo_imovel: "Apartamento",
      valor: 650000,
      proprietario_nome: "Carlos",
      observacoes: "casa térrea com quintal",
      regiao_preferida: ["Cotia", "Granja Viana"],
      interesses: [
        {
          tipo: "imovel",
          tipo_imovel: null,
          cidade: "Cotia",
          bairro: null,
          zona: null,
          valor_minimo: null,
          valor_maximo: 900000,
        },
      ],
    });
    // `interesses_descricao` is derived server-side; sending it would 422.
    expect(mockCriar.mock.calls[0][0]).not.toHaveProperty("interesses_descricao");
    expect(toastSuccess).toHaveBeenCalledWith("Permuta cadastrada");
    await waitFor(() => expect(queryByTestId("permuta-ativo-dialog")).toBeNull());
  });

  it("o texto de ajuda diz que a descrição é o que a análise semântica lê", () => {
    const { getByRole, getByText } = render(<PermutaAtivosLista />);
    fireEvent.click(getByRole("button", { name: /Nova permuta/ }));
    expect(getByText(/é o que a análise semântica do matching lê/)).toBeTruthy();
  });

  it("imóvel do catálogo exige o código e o vincula pelo picker", async () => {
    mockCriar.mockResolvedValue({ id: "novo" });
    const { getByRole, getByText } = render(<PermutaAtivosLista />);
    fireEvent.click(getByRole("button", { name: /Nova permuta/ }));

    fireEvent.click(getByRole("button", { name: "Cadastrar" }));
    expect(getByRole("alert").textContent).toMatch(/Escolha o imóvel do catálogo/);
    expect(mockCriar).not.toHaveBeenCalled();

    fireEvent.click(getByText("escolher ONE9265"));
    fireEvent.click(getByRole("button", { name: "Cadastrar" }));
    await waitFor(() => expect(mockCriar).toHaveBeenCalledTimes(1));
    expect(mockCriar.mock.calls[0][0]).toMatchObject({
      natureza: "imovel",
      imovel_codigo: "ONE9265",
    });
    // A catalog pointer carries no location/valor snapshot of its own.
    expect(mockCriar.mock.calls[0][0]).not.toHaveProperty("valor");
  });

  it("🔴 o erro da API aparece no formulário e no toast, e o diálogo fica aberto", async () => {
    mockCriar.mockRejectedValue(
      new Error("[400] Uma intenção de permuta sobre um imóvel do catálogo precisa do código do imóvel."),
    );
    const { getByRole, getByText, getByTestId } = render(<PermutaAtivosLista />);
    fireEvent.click(getByRole("button", { name: /Nova permuta/ }));
    fireEvent.click(getByText("escolher ONE9265"));
    fireEvent.click(getByRole("button", { name: "Cadastrar" }));

    await waitFor(() =>
      expect(getByRole("alert").textContent).toMatch(/precisa do código do imóvel/),
    );
    expect(toastError).toHaveBeenCalledWith(
      "Erro ao cadastrar permuta",
      expect.objectContaining({ description: expect.stringMatching(/\[400\]/) }),
    );
    expect(getByTestId("permuta-ativo-dialog")).toBeTruthy();
  });

  it("valida faixas antes de enviar", () => {
    const { getByRole, getByLabelText, getByText } = render(<PermutaAtivosLista />);
    fireEvent.click(getByRole("button", { name: /Nova permuta/ }));
    fireEvent.click(getByText("escolher ONE9265"));
    fireEvent.change(getByLabelText("Permuta cobre — mínimo (%)"), { target: { value: "60" } });
    fireEvent.change(getByLabelText("Permuta cobre — máximo (%)"), { target: { value: "40" } });
    fireEvent.click(getByRole("button", { name: "Cadastrar" }));
    expect(getByRole("alert").textContent).toMatch(/percentual mínimo é maior/);
    expect(mockCriar).not.toHaveBeenCalled();
  });
});

describe("editar", () => {
  it("prefill + PATCH: vazio vira null, critérios substituem preservando campos ocultos", async () => {
    mockAtualizar.mockResolvedValue({ id: "a1" });
    mockAtivos.mockReturnValue(query({ data: [ativo()] }));
    const { getByRole, getByLabelText } = render(<PermutaAtivosLista />);
    fireEvent.click(getByRole("button", { name: "Editar ONE9265" }));

    expect((getByLabelText("Nome") as HTMLInputElement).value).toBe("Maria Souza");
    expect((getByLabelText("Descrição do interesse") as HTMLTextAreaElement).value).toBe(
      "casa sem escada",
    );

    fireEvent.change(getByLabelText("Nome"), { target: { value: "Maria S. Lima" } });
    fireEvent.change(getByLabelText("Telefone"), { target: { value: "" } });
    fireEvent.click(getByRole("button", { name: "Salvar alterações" }));

    await waitFor(() => expect(mockAtualizar).toHaveBeenCalledTimes(1));
    const { ativoId, body } = mockAtualizar.mock.calls[0][0];
    expect(ativoId).toBe("a1");
    expect(body).toMatchObject({
      natureza: "imovel",
      imovel_codigo: "ONE9265",
      proprietario_nome: "Maria S. Lima",
      proprietario_telefone: null,
      faixa_preco_min: 800000,
      percentual_min: 30,
      percentual_max: 50,
      regiao_preferida: ["Granja Viana"],
    });
    // Fields the form does not show for a catalog pointer are not touched.
    expect(body).not.toHaveProperty("bairro");
    expect(body).not.toHaveProperty("valor");
    // The interest is sent back with its hidden `observacoes`, minus its id.
    expect(body.interesses).toEqual([
      expect.objectContaining({
        tipo: "imovel",
        tipo_imovel: "Casa",
        cidade: "Cotia",
        valor_maximo: 900000,
        observacoes: "quintal amplo",
      }),
    ]);
    expect(body.interesses[0]).not.toHaveProperty("id");
    expect(toastSuccess).toHaveBeenCalledWith("Permuta atualizada", expect.anything());
  });

  it("erro 422 na edição aparece no formulário", async () => {
    mockAtualizar.mockRejectedValue(new Error("[422] Input should be less than or equal to 100"));
    mockAtivos.mockReturnValue(query({ data: [ativo()] }));
    const { getByRole } = render(<PermutaAtivosLista />);
    fireEvent.click(getByRole("button", { name: "Editar ONE9265" }));
    fireEvent.click(getByRole("button", { name: "Salvar alterações" }));
    await waitFor(() =>
      expect(getByRole("alert").textContent).toMatch(/less than or equal to 100/),
    );
    expect(toastError).toHaveBeenCalledWith("Erro ao atualizar permuta", expect.anything());
  });
});

describe("remover", () => {
  it("pede confirmação no diálogo (não `confirm()`) e só então remove", async () => {
    const nativeConfirm = vi.spyOn(window, "confirm");
    mockRemover.mockResolvedValue(undefined);
    mockAtivos.mockReturnValue(query({ data: [ativo()] }));
    const { getByRole, findByRole } = render(<PermutaAtivosLista />);

    fireEvent.click(getByRole("button", { name: "Remover ONE9265" }));
    const dialogo = await findByRole("alertdialog");
    expect(mockRemover).not.toHaveBeenCalled();
    expect(within(dialogo).getByText(/todos os matches deste registro/)).toBeTruthy();

    fireEvent.click(within(dialogo).getByRole("button", { name: "Remover" }));
    await waitFor(() => expect(mockRemover).toHaveBeenCalledWith("a1"));
    expect(toastSuccess).toHaveBeenCalledWith("Permuta removida");
    expect(nativeConfirm).not.toHaveBeenCalled();
  });

  it("cancelar não remove", async () => {
    mockAtivos.mockReturnValue(query({ data: [ativo()] }));
    const { getByRole, findByRole } = render(<PermutaAtivosLista />);
    fireEvent.click(getByRole("button", { name: "Remover ONE9265" }));
    const dialogo = await findByRole("alertdialog");
    fireEvent.click(within(dialogo).getByRole("button", { name: "Cancelar" }));
    expect(mockRemover).not.toHaveBeenCalled();
  });

  it("erro ao remover vira toast com o detalhe", async () => {
    mockRemover.mockRejectedValue(new Error("[404] Permuta não encontrada."));
    mockAtivos.mockReturnValue(query({ data: [ativo()] }));
    const { getByRole, findByRole } = render(<PermutaAtivosLista />);
    fireEvent.click(getByRole("button", { name: "Remover ONE9265" }));
    const dialogo = await findByRole("alertdialog");
    fireEvent.click(within(dialogo).getByRole("button", { name: "Remover" }));
    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith("Erro ao remover permuta", {
        description: "[404] Permuta não encontrada.",
      }),
    );
  });
});
