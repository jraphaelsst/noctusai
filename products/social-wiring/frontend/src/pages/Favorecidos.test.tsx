/**
 * Favorecidos.test.tsx — the org registry page: the four states, LGPD
 * masking (clear values only inside the edit dialog), name-only search
 * (a document-looking term never reaches the hook), create / edit /
 * deactivate / reactivate.
 *
 * Mock-the-hook pattern (`TestemunhasSection.test.tsx`): the registry hooks
 * module is mocked, so no QueryClientProvider is needed.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

// Radix Select is a portal popover jsdom does not model — inline items, same
// convention as `NegociacaoEstruturadaPanel.test.tsx`.
vi.mock("@/components/ui/select", async () => {
  const React = await import("react");
  const Ctx = React.createContext<{ onValueChange?: (v: string) => void }>({});
  return {
    Select: ({ value, onValueChange, children }: any) =>
      React.createElement(
        Ctx.Provider,
        { value: { onValueChange } },
        React.createElement("div", { "data-value": value }, children),
      ),
    SelectTrigger: ({ children, ...rest }: any) =>
      React.createElement("div", { role: "combobox", ...rest }, children),
    SelectValue: () => null,
    SelectContent: ({ children }: any) => React.createElement("div", null, children),
    SelectItem: ({ value, children }: any) => {
      const ctx = React.useContext(Ctx);
      return React.createElement(
        "button",
        { type: "button", onClick: () => ctx.onValueChange?.(value) },
        children,
      );
    },
  };
});

const mockUseFavorecidos = vi.fn();
const mockUseFavorecido = vi.fn();
const mockCreate = vi.fn();
const mockUpdate = vi.fn();
const mockDeactivate = vi.fn();

vi.mock("@/hooks/useFavorecidosRegistro", async () => {
  const actual = await vi.importActual<
    typeof import("@/hooks/useFavorecidosRegistro")
  >("@/hooks/useFavorecidosRegistro");
  return {
    ...actual,
    useFavorecidos: mockUseFavorecidos,
    useFavorecido: mockUseFavorecido,
    useCreateFavorecidoRegistro: () => ({ mutate: mockCreate, isPending: false }),
    useUpdateFavorecidoRegistro: () => ({ mutate: mockUpdate, isPending: false }),
    useDeactivateFavorecidoRegistro: () => ({ mutate: mockDeactivate, isPending: false }),
  };
});

function query(over: Record<string, unknown> = {}) {
  return {
    data: undefined,
    isPending: false,
    isFetching: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...over,
  };
}

const MARIA = {
  id: "f1",
  nome: "Maria da Silva",
  tipo_pessoa: "PF",
  cpf_cnpj_mascarado: "***.456.789-**",
  banco: "Itaú",
  pix_tipo: "cpf",
  pix_mascarado: "***.456.789-**",
  ativo: true,
};
const MARIA_COMPLETA = {
  id: "f1",
  nome: "Maria da Silva",
  tipo_pessoa: "PF",
  cpf_cnpj: "12345678909",
  banco: "Itaú",
  agencia: "0001",
  conta: "98765-4",
  tipo_conta: "corrente",
  pix_tipo: "cpf",
  pix: "12345678909",
  ativo: true,
};
const INATIVO = { ...MARIA, id: "f2", nome: "Antigo Pagador", ativo: false };

async function render() {
  const { render: rtlRender } = await import("@testing-library/react");
  const { default: Favorecidos } = await import("./Favorecidos");
  return rtlRender(<Favorecidos />);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseFavorecidos.mockReturnValue(query({ data: { items: [MARIA] } }));
  mockUseFavorecido.mockReturnValue(query({ data: undefined }));
});

describe("os quatro estados", () => {
  it("esqueleto só antes do primeiro carregamento", async () => {
    mockUseFavorecidos.mockReturnValue(
      query({ data: undefined, isPending: true, isFetching: true }),
    );
    const { getByTestId, queryByTestId } = await render();
    expect(getByTestId("favorecidos-skeleton")).toBeTruthy();
    expect(queryByTestId("favorecidos-vazio")).toBeNull();
  });

  it("🔴 um refetch mantém a lista e só mostra o indicador", async () => {
    mockUseFavorecidos.mockReturnValue(
      query({ data: { items: [MARIA] }, isPending: false, isFetching: true }),
    );
    const { getByTestId, queryByTestId } = await render();
    expect(getByTestId("favorecidos-refreshing")).toBeTruthy();
    expect(getByTestId("favorecido-reg-f1")).toBeTruthy();
    expect(queryByTestId("favorecidos-skeleton")).toBeNull();
  });

  it("erro tem retry e não é confundido com vazio", async () => {
    const refetch = vi.fn();
    mockUseFavorecidos.mockReturnValue(query({ isError: true, refetch }));
    const { getByTestId, queryByTestId, getByText } = await render();
    expect(getByTestId("favorecidos-erro")).toBeTruthy();
    expect(queryByTestId("favorecidos-vazio")).toBeNull();
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalled();
  });

  it("vazio convida a cadastrar", async () => {
    mockUseFavorecidos.mockReturnValue(query({ data: { items: [] } }));
    const { getByTestId } = await render();
    expect(getByTestId("favorecidos-vazio").textContent).toContain("Nenhum favorecido cadastrado");
  });
});

describe("LGPD — a lista só mostra valores mascarados", () => {
  it("🔴 nunca renderiza CPF/conta/PIX em claro na lista", async () => {
    const { getByTestId } = await render();
    const linha = getByTestId("favorecido-reg-f1").textContent ?? "";
    expect(linha).toContain("***.456.789-**");
    expect(linha).not.toContain("12345678909");
    expect(linha).not.toContain("98765");
    // the list never asks for the clear record
    expect(mockUseFavorecido).not.toHaveBeenCalledWith("f1");
  });

  it("🔴 o valor em claro só aparece dentro do diálogo de edição", async () => {
    mockUseFavorecido.mockImplementation((id: string | null) =>
      id === "f1" ? query({ data: MARIA_COMPLETA }) : query({ data: undefined }),
    );
    const { getByTestId } = await render();
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(getByTestId("favorecido-reg-editar-f1"));
    expect((document.getElementById("favreg-doc") as HTMLInputElement).value).toBe(
      "123.456.789-09",
    );
    expect((document.getElementById("favreg-conta") as HTMLInputElement).value).toBe("98765-4");
    expect(getByTestId("favorecido-reg-f1").textContent).not.toContain("12345678909");
  });
});

describe("busca por nome", () => {
  it("🔴 um termo que parece documento não chega ao servidor e mostra o aviso", async () => {
    const { getByTestId } = await render();
    const { fireEvent, waitFor } = await import("@testing-library/react");
    fireEvent.change(getByTestId("favorecidos-busca"), {
      target: { value: "123.456.789-09" },
    });
    expect(getByTestId("favorecidos-busca-documento")).toBeTruthy();
    // wait past the debounce — the applied term is still handed to the hook,
    // which itself drops a document-looking term (see termoDeBuscaSeguro)
    await waitFor(() =>
      expect(mockUseFavorecidos).toHaveBeenCalledWith({
        q: "123.456.789-09",
        ativo: "ativos",
      }),
    );
    const { termoDeBuscaSeguro } = await import("@/hooks/useFavorecidosRegistro");
    expect(termoDeBuscaSeguro("123.456.789-09")).toBeNull();
    expect(termoDeBuscaSeguro("Maria")).toBe("Maria");
    expect(termoDeBuscaSeguro("  ")).toBe("");
  });

  it("um nome é repassado ao hook (com debounce)", async () => {
    const { getByTestId } = await render();
    const { fireEvent, waitFor } = await import("@testing-library/react");
    fireEvent.change(getByTestId("favorecidos-busca"), { target: { value: "Maria" } });
    await waitFor(() =>
      expect(mockUseFavorecidos).toHaveBeenCalledWith({ q: "Maria", ativo: "ativos" }),
    );
  });

  it("o filtro de situação muda o ativo do hook", async () => {
    const { getByText } = await render();
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(getByText("Inativos"));
    expect(mockUseFavorecidos).toHaveBeenLastCalledWith({ q: "", ativo: "inativos" });
  });
});

describe("cadastro", () => {
  it("🔴 'Novo favorecido' cria com o payload completo (documento só dígitos)", async () => {
    const { getByTestId } = await render();
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(getByTestId("favorecidos-novo"));
    expect(getByTestId("favorecido-dialog")).toBeTruthy();

    fireEvent.change(document.getElementById("favreg-nome") as HTMLInputElement, {
      target: { value: "Construtora Alfa" },
    });
    fireEvent.change(document.getElementById("favreg-doc") as HTMLInputElement, {
      target: { value: "11.222.333/0001-81" },
    });
    fireEvent.change(document.getElementById("favreg-banco") as HTMLInputElement, {
      target: { value: "Bradesco" },
    });
    fireEvent.click(getByTestId("favorecido-dialog-salvar"));

    expect(mockCreate).toHaveBeenCalledTimes(1);
    const payload = mockCreate.mock.calls[0][0];
    expect(payload).toMatchObject({
      nome: "Construtora Alfa",
      tipo_pessoa: "PF",
      cpf_cnpj: "11222333000181",
      banco: "Bradesco",
      agencia: null,
      pix: null,
    });
  });

  it("Salvar fica desabilitado sem nome", async () => {
    const { getByTestId } = await render();
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(getByTestId("favorecidos-novo"));
    expect((getByTestId("favorecido-dialog-salvar") as HTMLButtonElement).disabled).toBe(true);
  });

  it("🔴 o erro do servidor aparece NO diálogo, sem eco do payload", async () => {
    mockCreate.mockImplementation((_p: unknown, opts?: { onError?: (e: unknown) => void }) =>
      opts?.onError?.({ body: { error: { message: "CPF/CNPJ inválido." } } }),
    );
    const { getByTestId } = await render();
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(getByTestId("favorecidos-novo"));
    fireEvent.change(document.getElementById("favreg-nome") as HTMLInputElement, {
      target: { value: "X" },
    });
    fireEvent.change(document.getElementById("favreg-doc") as HTMLInputElement, {
      target: { value: "00000000000" },
    });
    fireEvent.click(getByTestId("favorecido-dialog-salvar"));
    expect(getByTestId("favorecido-dialog-erro").textContent).toContain("CPF/CNPJ inválido.");
    expect(getByTestId("favorecido-dialog-erro").textContent).not.toContain("00000000000");
  });

  it("editar envia PATCH com o id e fecha o diálogo", async () => {
    mockUseFavorecido.mockImplementation((id: string | null) =>
      id === "f1" ? query({ data: MARIA_COMPLETA }) : query({ data: undefined }),
    );
    mockUpdate.mockImplementation(
      (_v: unknown, opts?: { onSuccess?: (f: unknown) => void }) =>
        opts?.onSuccess?.(MARIA_COMPLETA),
    );
    const { getByTestId, queryByTestId } = await render();
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(getByTestId("favorecido-reg-editar-f1"));
    fireEvent.change(document.getElementById("favreg-banco") as HTMLInputElement, {
      target: { value: "Santander" },
    });
    fireEvent.click(getByTestId("favorecido-dialog-salvar"));

    expect(mockUpdate).toHaveBeenCalledTimes(1);
    expect(mockUpdate.mock.calls[0][0].id).toBe("f1");
    expect(mockUpdate.mock.calls[0][0].patch.banco).toBe("Santander");
    expect(queryByTestId("favorecido-dialog")).toBeNull();
  });

  it("edição: esqueleto enquanto o registro completo carrega, erro com retry", async () => {
    mockUseFavorecido.mockReturnValue(query({ data: undefined, isPending: true, isFetching: true }));
    const first = await render();
    const { fireEvent, cleanup } = await import("@testing-library/react");
    fireEvent.click(first.getByTestId("favorecido-reg-editar-f1"));
    expect(first.getByTestId("favorecido-dialog-skeleton")).toBeTruthy();
    cleanup();

    const refetch = vi.fn();
    mockUseFavorecido.mockReturnValue(query({ data: undefined, isError: true, refetch }));
    const second = await render();
    fireEvent.click(second.getByTestId("favorecido-reg-editar-f1"));
    expect(second.getByTestId("favorecido-dialog-erro-carga")).toBeTruthy();
  });
});

describe("desativar / reativar (soft delete)", () => {
  it("🔴 desativar pede confirmação e só então chama o DELETE", async () => {
    const { getByTestId } = await render();
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(getByTestId("favorecido-reg-desativar-f1"));
    expect(mockDeactivate).not.toHaveBeenCalled();
    fireEvent.click(getByTestId("favorecidos-desativar-confirmar"));
    expect(mockDeactivate).toHaveBeenCalledTimes(1);
    expect(mockDeactivate.mock.calls[0][0]).toBe("f1");
  });

  it("um inativo mostra o selo e oferece reativar (PATCH ativo:true)", async () => {
    mockUseFavorecidos.mockReturnValue(query({ data: { items: [INATIVO] } }));
    const { getByTestId, queryByTestId } = await render();
    expect(getByTestId("favorecido-reg-inativo-f2")).toBeTruthy();
    expect(queryByTestId("favorecido-reg-desativar-f2")).toBeNull();
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(getByTestId("favorecido-reg-reativar-f2"));
    expect(mockUpdate.mock.calls[0][0]).toEqual({ id: "f2", patch: { ativo: true } });
  });
});
