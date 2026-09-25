/**
 * TestemunhasSection.test.tsx — the four states, the migration-168 CPF
 * requirement (registry no longer caps at 2), "CPF pendente" for legacy
 * rows, and the delete confirmation.
 *
 * Follows the established mock-the-hook pattern (see `pages/Permutas.test.tsx`):
 * the hooks module is mocked directly, so no QueryClientProvider is needed.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const mockUseTestemunhas = vi.fn();
const mockCreate = vi.fn();
const mockUpdate = vi.fn();
const mockDelete = vi.fn();

vi.mock("@/hooks/useTestemunhas", async () => {
  const actual =
    await vi.importActual<typeof import("@/hooks/useTestemunhas")>(
      "@/hooks/useTestemunhas",
    );
  return {
    ...actual,
    useTestemunhas: mockUseTestemunhas,
    useCreateTestemunha: () => ({ mutate: mockCreate, isPending: false }),
    useUpdateTestemunha: () => ({ mutate: mockUpdate, isPending: false }),
    useDeleteTestemunha: () => ({ mutate: mockDelete, isPending: false }),
  };
});

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

function testemunha(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: "t1",
    nome: "Maria Souza",
    cpf: "111.222.333-44",
    rg: null,
    celular: null,
    email: null,
    cpf_pendente: false,
    contratos_em_uso: 0,
    created_at: null,
    updated_at: null,
    ...over,
  };
}

async function render() {
  const { render: rtlRender } = await import("@testing-library/react");
  const { TestemunhasSection } = await import("./TestemunhasSection");
  return rtlRender(<TestemunhasSection />);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseTestemunhas.mockReturnValue(query());
});

describe("os quatro estados", () => {
  it("mostra o esqueleto só antes do primeiro carregamento", async () => {
    mockUseTestemunhas.mockReturnValue(
      query({ isPending: true, isFetching: true, data: undefined }),
    );
    const { getByText } = await render();
    expect(getByText("Carregando…")).toBeTruthy();
  });

  it("distingue lista vazia de falha na requisição", async () => {
    mockUseTestemunhas.mockReturnValue(query({ data: { items: [], total: 0 } }));
    const vazio = await render();
    expect(vazio.getByText(/Nenhuma testemunha/)).toBeTruthy();

    (await import("@testing-library/react")).cleanup();

    mockUseTestemunhas.mockReturnValue(
      query({ isError: true, error: { message: "boom" }, data: undefined }),
    );
    const erro = await render();
    expect(erro.getByText(/Não foi possível carregar/)).toBeTruthy();
    expect(erro.queryByText(/Nenhuma testemunha/)).toBeNull();
  });

  it("renderiza testemunhas existentes", async () => {
    mockUseTestemunhas.mockReturnValue(
      query({ data: { items: [testemunha()], total: 1 } }),
    );
    const { getByText } = await render();
    expect(getByText("Maria Souza")).toBeTruthy();
  });

  it("mostra o e-mail cadastrado, quando houver (migration 143)", async () => {
    mockUseTestemunhas.mockReturnValue(
      query({
        data: { items: [testemunha({ email: "maria@exemplo.test" })], total: 1 },
      }),
    );
    const { getByText } = await render();
    expect(getByText(/maria@exemplo\.test/)).toBeTruthy();
  });

  it("🔴 P1/883 (2026-09-25): formata o CPF com máscara, nunca dígitos crus", async () => {
    mockUseTestemunhas.mockReturnValue(
      query({ data: { items: [testemunha({ cpf: "81259815862" })], total: 1 } }),
    );
    const { getByText, queryByText } = await render();
    expect(getByText(/812\.598\.158-62/)).toBeTruthy();
    expect(queryByText(/81259815862/)).toBeNull();
  });

  it("🔴 um refetch não desmonta a lista existente", async () => {
    // isFetching true WITH data present — the lying-loading-state trap.
    mockUseTestemunhas.mockReturnValue(
      query({ data: { items: [testemunha()], total: 1 }, isFetching: true }),
    );
    const { getByTestId, getByText } = await render();
    expect(getByText("Maria Souza")).toBeTruthy();
    expect(getByTestId("testemunhas-refreshing")).toBeTruthy();
  });
});

describe("CPF obrigatório no cadastro (migration 168)", () => {
  it("'Salvar' fica desabilitado sem CPF", async () => {
    const { getByTestId, getByLabelText } = await render();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("testemunha-nova"));
    fireEvent.change(getByLabelText("Nome"), { target: { value: "Nova Pessoa" } });

    expect((getByTestId("testemunha-salvar") as HTMLButtonElement).disabled).toBe(
      true,
    );
    expect(mockCreate).not.toHaveBeenCalled();
  });

  it("envia o CPF e o e-mail digitados no payload de criação", async () => {
    const { getByTestId, getByLabelText } = await render();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("testemunha-nova"));
    fireEvent.change(getByLabelText("Nome"), { target: { value: "Nova Pessoa" } });
    fireEvent.change(getByTestId("testemunha-cpf-input"), {
      target: { value: "111.222.333-44" },
    });
    fireEvent.change(getByLabelText("E-mail"), {
      target: { value: "nova@exemplo.test" },
    });
    fireEvent.click(getByTestId("testemunha-salvar"));

    expect(mockCreate).toHaveBeenCalledWith(
      expect.objectContaining({ cpf: "111.222.333-44", email: "nova@exemplo.test" }),
      expect.anything(),
    );
  });

  it("um e-mail vazio vira null, nunca string vazia", async () => {
    const { getByTestId, getByLabelText } = await render();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("testemunha-nova"));
    fireEvent.change(getByLabelText("Nome"), { target: { value: "Nova Pessoa" } });
    fireEvent.change(getByTestId("testemunha-cpf-input"), {
      target: { value: "111.222.333-44" },
    });
    fireEvent.click(getByTestId("testemunha-salvar"));

    expect(mockCreate).toHaveBeenCalledWith(
      expect.objectContaining({ email: null }),
      expect.anything(),
    );
  });

  it("editar NÃO exige CPF preenchido (permite manter 'pendente')", async () => {
    mockUseTestemunhas.mockReturnValue(
      query({ data: { items: [testemunha({ cpf: null, cpf_pendente: true })], total: 1 } }),
    );
    const { getByTestId, getByLabelText } = await render();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByLabelText("Editar Maria Souza"));
    expect((getByTestId("testemunha-salvar") as HTMLButtonElement).disabled).toBe(
      false,
    );
  });
});

describe("registro sem limite (migration 168 removeu o teto de 2)", () => {
  it("'Nova testemunha' nunca fica desabilitado, mesmo com várias já cadastradas", async () => {
    mockUseTestemunhas.mockReturnValue(
      query({
        data: {
          items: [
            testemunha(),
            testemunha({ id: "t2", nome: "João Lima" }),
            testemunha({ id: "t3", nome: "Ana Paula" }),
          ],
          total: 3,
        },
      }),
    );
    const { getByTestId } = await render();
    expect((getByTestId("testemunha-nova") as HTMLButtonElement).disabled).toBe(
      false,
    );
  });

  it("uma testemunha legada sem CPF mostra 'CPF pendente'", async () => {
    mockUseTestemunhas.mockReturnValue(
      query({
        data: { items: [testemunha({ cpf: null, cpf_pendente: true })], total: 1 },
      }),
    );
    const { getByTestId } = await render();
    expect(getByTestId("testemunha-cpf-pendente-t1")).toBeTruthy();
  });
});

describe("exclusão com confirmação", () => {
  it("clicar em Remover abre um diálogo de confirmação — não exclui direto", async () => {
    mockUseTestemunhas.mockReturnValue(
      query({ data: { items: [testemunha()], total: 1 } }),
    );
    const { getByLabelText, queryByTestId } = await render();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByLabelText("Remover Maria Souza"));
    expect(mockDelete).not.toHaveBeenCalled();
    expect(queryByTestId("testemunha-confirmar-remover")).toBeTruthy();
  });

  it("avisa (sem bloquear) quantos contratos usam a testemunha", async () => {
    mockUseTestemunhas.mockReturnValue(
      query({ data: { items: [testemunha({ contratos_em_uso: 3 })], total: 1 } }),
    );
    const { getByLabelText, getByTestId } = await render();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByLabelText("Remover Maria Souza"));
    expect(getByTestId("testemunha-remover-em-uso").textContent).toContain(
      "3 contratos usam esta testemunha",
    );
    fireEvent.click(getByTestId("testemunha-confirmar-remover"));
    expect(mockDelete).toHaveBeenCalledWith("t1", expect.anything());
  });

  it("sem contratos em uso, não mostra o aviso", async () => {
    mockUseTestemunhas.mockReturnValue(
      query({ data: { items: [testemunha()], total: 1 } }),
    );
    const { getByLabelText, queryByTestId } = await render();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByLabelText("Remover Maria Souza"));
    expect(queryByTestId("testemunha-remover-em-uso")).toBeNull();
  });

  it("confirmar no diálogo chama a exclusão", async () => {
    mockUseTestemunhas.mockReturnValue(
      query({ data: { items: [testemunha()], total: 1 } }),
    );
    const { getByLabelText, getByTestId } = await render();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByLabelText("Remover Maria Souza"));
    fireEvent.click(getByTestId("testemunha-confirmar-remover"));
    expect(mockDelete).toHaveBeenCalledWith("t1", expect.anything());
  });
});
