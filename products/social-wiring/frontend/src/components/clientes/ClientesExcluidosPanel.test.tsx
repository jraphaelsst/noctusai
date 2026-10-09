/**
 * ClientesExcluidosPanel.test.tsx — admin "Excluídos" list + Restaurar flow.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const { toastSuccess, toastError, navigate } = vi.hoisted(() => ({
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
  navigate: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: toastSuccess, error: toastError, warning: vi.fn() } }));
vi.mock("react-router-dom", async () => ({
  ...(await vi.importActual<object>("react-router-dom")),
  useNavigate: () => navigate,
}));
vi.mock("@noctusai/seed/infra", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { ClientesExcluidosPanel } from "./ClientesExcluidosPanel";

const mGet = api.get as unknown as ReturnType<typeof vi.fn>;
const mPost = api.post as unknown as ReturnType<typeof vi.fn>;

const ROW = {
  cliente_id: "del-1",
  cliente_nome: "Maria Silva",
  excluido_por: "u1",
  excluido_por_nome: "Admin Ana",
  excluido_em: "2026-10-09T12:30:00Z",
  origens: 2,
};

async function mount() {
  const { render } = await import("@testing-library/react");
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const spy = vi.spyOn(qc, "invalidateQueries");
  const ui = render(
    <QueryClientProvider client={qc}>
      <ClientesExcluidosPanel />
    </QueryClientProvider>,
  );
  return { ...ui, spy };
}

beforeEach(() => vi.clearAllMocks());

describe("ClientesExcluidosPanel", () => {
  it("lists name, who deleted, when and origens", async () => {
    mGet.mockResolvedValue({
      items: [ROW, { ...ROW, cliente_id: "del-2", cliente_nome: null, excluido_por_nome: null, origens: 1 }],
      total: 2,
    });
    const { findByText, getAllByTestId, getByText } = await mount();
    await findByText("Maria Silva");
    expect(getByText("Admin Ana")).toBeTruthy();
    expect(getByText("2 lead(s)")).toBeTruthy();
    expect(getByText("Sem nome")).toBeTruthy();
    expect(getByText("—")).toBeTruthy();
    expect(getAllByTestId("excluido-row")).toHaveLength(2);
    expect(mGet).toHaveBeenCalledWith("/api/clientes/excluidos");
  });

  it("shows the empty state", async () => {
    mGet.mockResolvedValue({ items: [], total: 0 });
    const { findByText } = await mount();
    expect(await findByText("Nenhum cliente excluído.")).toBeTruthy();
  });

  it("restores after confirm: warns about unrecovered data, toasts, invalidates, links to the cliente", async () => {
    mGet.mockResolvedValue({ items: [ROW], total: 1 });
    mPost.mockResolvedValue({ origens_restauradas: 2, cliente_id: "new-1" });
    const { findByTestId, getByTestId, getByText, spy } = await mount();
    const { fireEvent, waitFor } = await import("@testing-library/react");
    fireEvent.click(await findByTestId("restaurar-btn"));
    expect(getByText(/reconstruída a partir/)).toBeTruthy();
    expect(getByText(/não serão recuperados/)).toBeTruthy();
    fireEvent.click(getByTestId("restaurar-cliente-confirm"));
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
    expect(mPost).toHaveBeenCalledWith("/api/clientes/excluidos/del-1/restaurar", {});
    const [msg, opts] = toastSuccess.mock.calls[0];
    expect(msg).toBe("Cliente restaurado");
    opts.action.onClick();
    expect(navigate).toHaveBeenCalledWith("/clientes/new-1");
    expect(spy).toHaveBeenCalledWith({ queryKey: ["sw", "clientes"] });
  });

  it("shows the server message on 404 already-restored", async () => {
    mGet.mockResolvedValue({ items: [ROW], total: 1 });
    mPost.mockRejectedValue(
      Object.assign(new Error("[404] x"), {
        body: { error: { code: "CLIENTE_EXCLUIDO_NAO_ENCONTRADO", message: "Este cliente já foi restaurado." } },
      }),
    );
    const { findByTestId, getByTestId } = await mount();
    const { fireEvent, waitFor } = await import("@testing-library/react");
    fireEvent.click(await findByTestId("restaurar-btn"));
    fireEvent.click(getByTestId("restaurar-cliente-confirm"));
    await waitFor(() => expect(toastError).toHaveBeenCalledWith("Este cliente já foi restaurado."));
  });
});
