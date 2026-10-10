/** Possíveis duplicados section + Vinculado banner (S6, CONTRACT §8.6/§8.7). */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const m = vi.hoisted(() => ({
  role: { current: "admin" },
  lista: vi.fn(),
  descartar: vi.fn(),
  vincular: vi.fn(),
  desvincular: vi.fn(),
  toastSuccess: vi.fn(),
  toastWarning: vi.fn(),
  toastError: vi.fn(),
}));
vi.mock("sonner", () => ({
  toast: { success: m.toastSuccess, warning: m.toastWarning, error: m.toastError },
}));
vi.mock("@noctusai/seed/infra", () => ({
  api: {},
  useAuthStore: () => ({ user: { user_metadata: { org_role: m.role.current } } }),
}));
vi.mock("@/hooks/useImovelDuplicatas", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/useImovelDuplicatas")>();
  return {
    ...actual,
    useDuplicatasPendentes: m.lista,
    useDescartarDuplicata: () => ({ mutateAsync: m.descartar, isPending: false }),
    useVincularDuplicata: () => ({ mutateAsync: m.vincular, isPending: false }),
    useDesvincularImovel: () => ({ mutateAsync: m.desvincular, isPending: false }),
  };
});

import ImovelDuplicatasSection from "./ImovelDuplicatasSection";
import ImovelVinculoBanner from "./ImovelVinculoBanner";

const resumo = (codigo: string) => ({
  codigo,
  titulo: `Imóvel ${codigo}`,
  endereco_resumo: "Rua X, 10",
  valor_venda: 500000,
  area_total: 80,
  foto_destaque: null,
});
const par = {
  id: "d1",
  score: 0.95,
  sinais: [
    { sinal: "matricula_cri", detalhe: "1234" },
    { sinal: "endereco" },
  ],
  status: "pendente",
  detectado_em: null,
  manual: resumo("SW-0001"),
  vista: resumo("ONE1234"),
};

function ver(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

beforeEach(() => {
  m.role.current = "admin";
  [m.descartar, m.vincular, m.desvincular, m.toastSuccess, m.toastWarning, m.toastError].forEach(
    (f) => f.mockReset(),
  );
  m.lista.mockReturnValue({ data: [par], isPending: false, isFetching: false, isError: false });
});
afterEach(cleanup);

describe("ImovelDuplicatasSection", () => {
  it("renders the pair with score and pt-BR signal chips", () => {
    const { getByTestId, getAllByTestId } = ver(
      <ImovelDuplicatasSection codigo="SW-0001" temPendentes />,
    );
    expect(getByTestId("duplicata-score").textContent).toBe("95%");
    expect(getAllByTestId("duplicata-sinal").map((e) => e.textContent)).toEqual([
      "Mesma matrícula e cartório",
      "Mesmo endereço",
    ]);
  });

  it("renders nothing without pending pairs", () => {
    const { queryByTestId } = ver(<ImovelDuplicatasSection codigo="SW-0001" temPendentes={false} />);
    expect(queryByTestId("imovel-duplicatas")).toBeNull();
  });

  it("descartar needs a confirmation, then calls the mutation", async () => {
    m.descartar.mockResolvedValue({});
    const { getByTestId } = ver(<ImovelDuplicatasSection codigo="SW-0001" temPendentes />);
    fireEvent.click(getByTestId("duplicata-descartar"));
    expect(m.descartar).not.toHaveBeenCalled();
    fireEvent.click(getByTestId("duplicata-confirmar"));
    await waitFor(() => expect(m.descartar).toHaveBeenCalledWith("d1"));
    await waitFor(() => expect(m.toastSuccess).toHaveBeenCalled());
  });

  it("vincular is admin-only: a member sees no button", () => {
    m.role.current = "member";
    const { queryByTestId, getByTestId } = ver(
      <ImovelDuplicatasSection codigo="SW-0001" temPendentes />,
    );
    expect(queryByTestId("duplicata-vincular")).toBeNull();
    expect(getByTestId("duplicata-descartar")).toBeTruthy();
  });

  it("admin vincula; legal 'erro' shows a warning toast, not an error", async () => {
    m.vincular.mockResolvedValue({
      vinculo: { manual_codigo: "SW-0001", vista_codigo: "ONE1234" },
      legal: { status: "erro", mensagem: "Falha ao conciliar matrícula" },
    });
    const { getByTestId } = ver(<ImovelDuplicatasSection codigo="SW-0001" temPendentes />);
    fireEvent.click(getByTestId("duplicata-vincular"));
    fireEvent.click(getByTestId("duplicata-confirmar"));
    await waitFor(() => expect(m.vincular).toHaveBeenCalledWith("d1"));
    await waitFor(() =>
      expect(m.toastWarning).toHaveBeenCalledWith("Falha ao conciliar matrícula"),
    );
    expect(m.toastError).not.toHaveBeenCalled();
  });

  it("shows a skeleton only on first load", () => {
    m.lista.mockReturnValue({ data: undefined, isPending: true, isFetching: true, isError: false });
    const { queryByTestId } = ver(<ImovelDuplicatasSection codigo="SW-0001" temPendentes />);
    expect(queryByTestId("duplicata-d1")).toBeNull();
  });
});

describe("ImovelVinculoBanner", () => {
  const vinculo = { manual_codigo: "SW-0001", vista_codigo: "ONE1234" };

  it("names both códigos with links", () => {
    const { getByTestId } = ver(<ImovelVinculoBanner vinculo={vinculo} />);
    const b = getByTestId("imovel-vinculo-banner");
    expect(b.textContent).toContain("Cadastro manual SW-0001 vinculado ao anúncio ONE1234");
    expect(b.querySelectorAll("a")).toHaveLength(2);
  });

  it("admin desvincula after confirming", async () => {
    m.desvincular.mockResolvedValue({ vinculo: null, legal: { status: "ok" } });
    const { getByTestId } = ver(<ImovelVinculoBanner vinculo={vinculo} />);
    fireEvent.click(getByTestId("imovel-desvincular"));
    fireEvent.click(getByTestId("imovel-desvincular-confirmar"));
    await waitFor(() => expect(m.desvincular).toHaveBeenCalledWith("SW-0001"));
  });

  it("member sees no Desvincular", () => {
    m.role.current = "member";
    const { queryByTestId } = ver(<ImovelVinculoBanner vinculo={vinculo} />);
    expect(queryByTestId("imovel-desvincular")).toBeNull();
  });
});
