/**
 * RevisaoFila.test.tsx — the review queue, this slice's primary deliverable.
 * Asserts: reason codes render, merge/manter-separados wire to the right
 * mutation, a resolved group is filtered out immediately (never reappears),
 * undo is reachable from the merge success toast, and an empty queue reads
 * as SUCCESS (not the generic empty/error look) — PROJECT.md §8's checkpoint.
 *
 * `@noctusai/seed/infra` is stubbed at module scope (same reason as
 * `PortalRoi.test.tsx`: `useClientesRevisao.ts` imports its `api` client at
 * module scope, and `vi.importActual` still executes that import). `sonner`
 * is stubbed to assert the undo toast's `action` prop directly, mirroring
 * `CampanhaManagerDialog.test.tsx`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const mockUseRevisaoFila = vi.fn();
const mockMerge = { mutate: vi.fn(), isPending: false, variables: undefined as any };
const mockManterSeparados = { mutate: vi.fn(), isPending: false, variables: undefined as any };
const mockDesfazer = { mutate: vi.fn(), isPending: false, variables: undefined as any };

vi.mock("@/hooks/useClientesRevisao", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useClientesRevisao")>(
    "@/hooks/useClientesRevisao",
  );
  return {
    ...actual,
    useRevisaoFila: mockUseRevisaoFila,
    useRevisaoMutations: () => ({
      merge: mockMerge,
      manterSeparados: mockManterSeparados,
      desfazer: mockDesfazer,
    }),
  };
});

function grupo(overrides: Partial<any> = {}) {
  return {
    motivo: "C5",
    chave_canonica: "+5511974781330",
    candidatos: [
      { id: "cand1", nome: "Maria Silva", chave_canonica: "+5511974781330", touch_count: 4 },
      { id: "cand2", nome: "João Souza", chave_canonica: "+5511974781330", touch_count: 2 },
    ],
    ...overrides,
  };
}

async function renderPage() {
  const React = (await import("react")).default;
  const { default: RevisaoFila } = await import("./RevisaoFila");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(RevisaoFila)) };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockMerge.isPending = false;
  mockMerge.variables = undefined;
  mockManterSeparados.isPending = false;
  mockManterSeparados.variables = undefined;
});

describe("RevisaoFila — loading", () => {
  it("shows the loading skeleton before any data has arrived", async () => {
    mockUseRevisaoFila.mockReturnValue({
      isPending: true,
      isFetching: true,
      isError: false,
      data: undefined,
      refetch: vi.fn(),
    });
    const { getByTestId } = await renderPage();
    expect(getByTestId("revisao-loading")).toBeTruthy();
  });
});

describe("RevisaoFila — error", () => {
  it("shows the error state with a retry action", async () => {
    mockUseRevisaoFila.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: true,
      data: undefined,
      refetch: vi.fn(),
    });
    const { getByText } = await renderPage();
    expect(getByText("Não foi possível carregar a fila de revisão.")).toBeTruthy();
  });
});

describe("RevisaoFila — empty queue (success, not failure)", () => {
  it("renders the positive success state, not the error/empty-filtered look", async () => {
    mockUseRevisaoFila.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: false,
      data: { items: [], total: 0, page: 1, pages: 1 },
      refetch: vi.fn(),
    });
    const { getByTestId, getByText, queryByText } = await renderPage();
    expect(getByTestId("revisao-empty-success")).toBeTruthy();
    expect(getByText("Fila de revisão vazia — tudo certo!")).toBeTruthy();
    expect(queryByText("Não foi possível carregar a fila de revisão.")).toBeNull();
  });
});

describe("RevisaoFila — groups to review", () => {
  const twoGroups = {
    items: [
      grupo({ motivo: "C5" }),
      grupo({
        motivo: "C4",
        chave_canonica: "+5511900000000",
        candidatos: [
          { id: "cand3", nome: "Ana", chave_canonica: "+5511900000000", touch_count: 1 },
          { id: "cand4", nome: "Ana Paula", chave_canonica: "+5511900000000", touch_count: 3 },
        ],
      }),
    ],
    total: 311,
    page: 1,
    pages: 26,
  };

  beforeEach(() => {
    mockUseRevisaoFila.mockReturnValue({
      isPending: false,
      isFetching: false,
      isError: false,
      data: twoGroups,
      refetch: vi.fn(),
    });
  });

  it("renders every group with its reason code and every candidate", async () => {
    const { getAllByTestId, getByText } = await renderPage();
    expect(getAllByTestId("revisao-grupo-card")).toHaveLength(2);
    expect(getByText(/C5 ·/)).toBeTruthy();
    expect(getByText(/C4 ·/)).toBeTruthy();
    expect(getByText("Maria Silva")).toBeTruthy();
    expect(getByText("Ana Paula")).toBeTruthy();
    expect(getByText(/^311 grupo\(s\) aguardando revisão\.$/)).toBeTruthy();
  });

  it("calls merge.mutate with the clicked group's id", async () => {
    const { getAllByTestId } = await renderPage();
    const { fireEvent } = await import("@testing-library/react");
    const [mesclarBtn] = getAllByTestId("revisao-mesclar-btn");
    fireEvent.click(mesclarBtn);
    expect(mockMerge.mutate).toHaveBeenCalledWith(
      { grupoId: "+5511974781330" },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    );
  });

  it("calls manterSeparados.mutate with the clicked group's id", async () => {
    const { getAllByTestId } = await renderPage();
    const { fireEvent } = await import("@testing-library/react");
    const [manterBtn] = getAllByTestId("revisao-manter-separados-btn");
    fireEvent.click(manterBtn);
    expect(mockManterSeparados.mutate).toHaveBeenCalledWith(
      "+5511974781330",
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("filters a resolved group out immediately (does not reappear) and surfaces an undo toast", async () => {
    const { toast } = await import("sonner");
    const { getAllByTestId, queryByTestId } = await renderPage();
    const { fireEvent } = await import("@testing-library/react");

    // Simulate the mutate call invoking its onSuccess callback, as the real
    // mutation would after a successful POST.
    mockManterSeparados.mutate.mockImplementation((_grupoId: string, opts: any) => {
      opts?.onSuccess?.();
    });

    expect(getAllByTestId("revisao-grupo-card")).toHaveLength(2);
    const [manterBtn] = getAllByTestId("revisao-manter-separados-btn");
    fireEvent.click(manterBtn);

    // g1 is gone from the render; g2 remains — position preserved, no resurface.
    expect(getAllByTestId("revisao-grupo-card")).toHaveLength(1);
    expect(queryByTestId("revisao-grupo-card")?.getAttribute("data-motivo")).toBe("C4");
    expect(toast.success).toHaveBeenCalledWith(
      "Mantidos separados.",
      expect.objectContaining({ description: expect.stringContaining("não vai mais aparecer") }),
    );
  });

  it("wires the merge success toast's 'Desfazer' action to desfazer.mutate with the returned merge_id", async () => {
    const { toast } = await import("sonner");
    mockMerge.mutate.mockImplementation((_vars: any, opts: any) => {
      opts?.onSuccess?.({ merge_id: "m-abc" });
    });

    const { getAllByTestId } = await renderPage();
    const { fireEvent } = await import("@testing-library/react");
    const [mesclarBtn] = getAllByTestId("revisao-mesclar-btn");
    fireEvent.click(mesclarBtn);

    expect(toast.success).toHaveBeenCalledWith(
      "Grupo mesclado.",
      expect.objectContaining({
        action: expect.objectContaining({ label: "Desfazer", onClick: expect.any(Function) }),
      }),
    );

    // Fire the action's onClick — it must call desfazer with the merge_id.
    const call = (toast.success as any).mock.calls[0];
    call[1].action.onClick();
    expect(mockDesfazer.mutate).toHaveBeenCalledWith("m-abc", expect.any(Object));
  });
});
