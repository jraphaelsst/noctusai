/**
 * CampanhaManagerDialog.test.tsx — the spend-entry CRUD surface + the
 * client-side 409 resolution (PROJECT.md §3.3: "never dead-end the
 * operator" on a duplicate (origem_id, periodo_inicio, periodo_fim)).
 *
 * `@noctusai/seed/infra` is stubbed — `usePortalRoi.ts` imports its `api`
 * client at module scope, and the real module throws without
 * `VITE_SUPABASE_URL` (see `PortalRoi.test.tsx` header for the full trace).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const mockUsePortalRoiCampanhas = vi.fn();
const mockCreate = { mutate: vi.fn(), isPending: false };
const mockUpdate = { mutate: vi.fn(), isPending: false };
const mockRemove = { mutate: vi.fn(), isPending: false };

vi.mock("@/hooks/usePortalRoi", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/usePortalRoi")>(
    "@/hooks/usePortalRoi",
  );
  return {
    ...actual,
    usePortalRoiCampanhas: mockUsePortalRoiCampanhas,
    usePortalRoiCampanhaMutations: () => ({
      create: mockCreate,
      update: mockUpdate,
      remove: mockRemove,
    }),
  };
});

function row(overrides: Partial<any> = {}) {
  return {
    id: "c1",
    origem_id: "o1",
    origem_label: "ZAP",
    periodo_inicio: "2026-07-01",
    periodo_fim: "2026-07-31",
    investimento: 3200,
    impressoes: null,
    cliques: null,
    leads: null,
    visitas_perfil: null,
    engajamento: null,
    cpc: null,
    cpl: 3.94,
    custo_visita: null,
    observacoes: null,
    created_at: "",
    updated_at: null,
    ...overrides,
  };
}

async function renderDialog(props: Partial<any> = {}) {
  const React = (await import("react")).default;
  const { CampanhaManagerDialog } = await import("./CampanhaManagerDialog");
  const rtl = await import("@testing-library/react");
  const rendered = rtl.render(
    React.createElement(CampanhaManagerDialog, {
      open: true,
      onOpenChange: vi.fn(),
      origemId: "o1",
      origemLabel: "ZAP",
      ...props,
    }),
  );
  return { ...rendered, fireEvent: rtl.fireEvent };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUsePortalRoiCampanhas.mockReturnValue({
    data: [row()],
    isPending: false,
    isFetching: false,
    refetch: vi.fn().mockResolvedValue({ data: [row()] }),
  });
});

describe("CampanhaManagerDialog — list view", () => {
  it("lists every recorded period for the origem, formatted in pt-BR currency", async () => {
    const { getAllByTestId, getByText } = await renderDialog();
    expect(getAllByTestId("campanha-row")).toHaveLength(1);
    expect(getByText("R$ 3.200,00")).toBeTruthy();
  });

  it("shows an empty message when the origem has no entries yet", async () => {
    mockUsePortalRoiCampanhas.mockReturnValue({
      data: [],
      isPending: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    const { getByText, queryByTestId } = await renderDialog();
    expect(getByText("Nenhum lançamento registrado para este portal ainda.")).toBeTruthy();
    expect(queryByTestId("campanha-row")).toBeNull();
  });

  it("🔴 keeps the lançamentos table mounted during a background refetch (Cat A regression)", async () => {
    // Every save/delete in this dialog invalidates `campanhas`. The old
    // gate (`campanhas.isPending || campanhas.isFetching`) stayed true
    // through that refetch and swapped the just-saved table back to
    // "Carregando…" every time. The fix reads the RAW `campanhas.data`
    // (undefined until the first successful fetch), not `rows`
    // (`campanhas.data ?? []`, always an array).
    // (KB § PATTERNS/frontend/lying-loading-state.md)
    mockUsePortalRoiCampanhas.mockReturnValue({
      data: [row()],
      isPending: false,
      isFetching: true,
      refetch: vi.fn(),
    });
    const { getAllByTestId, queryByText } = await renderDialog();
    expect(getAllByTestId("campanha-row")).toHaveLength(1);
    expect(queryByText("Carregando…")).toBeNull();
  });

  it("shows the skeleton only on first load (isPending, no data yet)", async () => {
    mockUsePortalRoiCampanhas.mockReturnValue({
      data: undefined,
      isPending: true,
      isFetching: true,
      refetch: vi.fn(),
    });
    const { getByText, queryByTestId } = await renderDialog();
    expect(getByText("Carregando…")).toBeTruthy();
    expect(queryByTestId("campanha-row")).toBeNull();
  });
});

describe("CampanhaManagerDialog — create flow", () => {
  it("opens the form on 'Novo período' and submits a create for a non-conflicting period", async () => {
    const { getByTestId, fireEvent } = await renderDialog();
    fireEvent.click(getByTestId("campanha-new-period-btn"));

    fireEvent.change(getByTestId("campanha-form-periodo-inicio"), {
      target: { value: "2026-08-01" },
    });
    fireEvent.change(getByTestId("campanha-form-periodo-fim"), {
      target: { value: "2026-08-31" },
    });
    fireEvent.change(getByTestId("campanha-form-investimento"), { target: { value: "1500" } });
    fireEvent.click(getByTestId("campanha-form-submit"));

    expect(mockCreate.mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        origem_id: "o1",
        periodo_inicio: "2026-08-01",
        periodo_fim: "2026-08-31",
        investimento: 1500,
      }),
      expect.anything(),
    );
  });

  it("never fires the request when the typed period already has a row — shows the conflict banner instead", async () => {
    const { getByTestId, queryByTestId, fireEvent } = await renderDialog();
    fireEvent.click(getByTestId("campanha-new-period-btn"));

    // Same period as the existing row("c1") — 2026-07-01 .. 2026-07-31.
    fireEvent.change(getByTestId("campanha-form-periodo-inicio"), {
      target: { value: "2026-07-01" },
    });
    fireEvent.change(getByTestId("campanha-form-periodo-fim"), {
      target: { value: "2026-07-31" },
    });
    fireEvent.change(getByTestId("campanha-form-investimento"), { target: { value: "999" } });
    fireEvent.click(getByTestId("campanha-form-submit"));

    expect(mockCreate.mutate).not.toHaveBeenCalled();
    expect(getByTestId("campanha-conflict-banner")).toBeTruthy();
    expect(queryByTestId("campanha-form-submit")).toBeTruthy(); // form still open, not dead-ended
  });

  it("'Atualizar o lançamento existente' switches the form into edit mode for the conflicting row", async () => {
    const { getByTestId, fireEvent } = await renderDialog();
    fireEvent.click(getByTestId("campanha-new-period-btn"));
    fireEvent.change(getByTestId("campanha-form-periodo-inicio"), {
      target: { value: "2026-07-01" },
    });
    fireEvent.change(getByTestId("campanha-form-periodo-fim"), {
      target: { value: "2026-07-31" },
    });
    fireEvent.change(getByTestId("campanha-form-investimento"), { target: { value: "999" } });
    fireEvent.click(getByTestId("campanha-form-submit"));
    fireEvent.click(getByTestId("campanha-use-conflict-btn"));
    fireEvent.click(getByTestId("campanha-form-submit"));

    expect(mockUpdate.mutate).toHaveBeenCalledWith(
      expect.objectContaining({ id: "c1" }),
      expect.anything(),
    );
    expect(mockCreate.mutate).not.toHaveBeenCalled();
  });
});

describe("CampanhaManagerDialog — edit + delete", () => {
  it("opens the form pre-filled when 'edit' is clicked on an existing row", async () => {
    const { getByTestId } = await renderDialog();
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(getByTestId("campanha-edit-btn"));
    expect((getByTestId("campanha-form-investimento") as HTMLInputElement).value).toBe("3200");
  });

  it("delete asks for confirmation before removing", async () => {
    const { getByTestId, fireEvent } = await renderDialog();
    fireEvent.click(getByTestId("campanha-delete-btn"));
    fireEvent.click(getByTestId("campanha-confirm-delete-btn"));
    expect(mockRemove.mutate).toHaveBeenCalledWith("c1", expect.anything());
  });
});
