/**
 * TestemunhasSection.test.tsx — the four states plus the 2-witness cap.
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

describe("o limite de 2 testemunhas por organização", () => {
  it("desabilita 'Nova testemunha' quando já há 2", async () => {
    mockUseTestemunhas.mockReturnValue(
      query({
        data: {
          items: [testemunha(), testemunha({ id: "t2", nome: "João Lima" })],
          total: 2,
        },
      }),
    );
    const { getByTestId } = await render();
    expect((getByTestId("testemunha-nova") as HTMLButtonElement).disabled).toBe(
      true,
    );
  });

  it("🔴 o 409 do backend chega ao usuário via toast", async () => {
    mockCreate.mockImplementation(
      (
        _payload: unknown,
        opts?: { onError?: (e: unknown) => void },
      ) => {
        opts?.onError?.({
          message: "[409] máximo de 2 testemunhas por organização",
        });
      },
    );

    const { getByTestId, getByLabelText } = await render();
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("testemunha-nova"));
    fireEvent.change(getByLabelText("Nome"), {
      target: { value: "Nova Pessoa" },
    });
    fireEvent.click(getByTestId("testemunha-salvar"));

    const { toast } = await import("sonner");
    expect(mockCreate).toHaveBeenCalled();
    const call = (toast.error as unknown as { mock: { calls: unknown[][] } })
      .mock.calls[0];
    expect(String(call[0])).toContain("máximo de 2 testemunhas");
  });
});
