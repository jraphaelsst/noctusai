/** DivergenciasAvisos.test.tsx — toggle, picker, no-destination note, refused save surfaced. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockCfg = vi.fn();
const mockUsers = vi.fn();
const mockSalvar = vi.fn();
const salvarState: Record<string, unknown> = { isPending: false, isError: false, error: null };

vi.mock("@/hooks/useVistaDivergenciasConfig", () => ({
  useDivergenciasConfig: mockCfg,
  useSalvarDivergenciasConfig: () => ({ mutate: mockSalvar, ...salvarState }),
}));
vi.mock("@/hooks/useJuliaEquipeWhatsapp", () => ({ useUsuariosDaOrg: mockUsers }));

const USERS = [
  { id: "u1", nome: "Ana", org_role: "admin" },
  { id: "u2", nome: "Bruno", org_role: "member" },
];

function cfg(over: Record<string, unknown> = {}) {
  return {
    data: { ativa: false, destino_user_id: null },
    showSkeleton: false, isRefreshing: false, isError: false, refetch: vi.fn(), ...over,
  };
}

async function render() {
  const { render: r } = await import("@testing-library/react");
  const { DivergenciasAvisos } = await import("./DivergenciasAvisos");
  return r(<DivergenciasAvisos />);
}

beforeEach(() => {
  vi.clearAllMocks();
  Object.assign(salvarState, { isPending: false, isError: false, error: null });
  mockCfg.mockReturnValue(cfg());
  mockUsers.mockReturnValue({ data: USERS, isPending: false, isError: false });
});

describe("DivergenciasAvisos", () => {
  it("skeleton e erro de carregamento", async () => {
    mockCfg.mockReturnValue(cfg({ data: undefined, showSkeleton: true }));
    expect((await render()).getByTestId("divergencias-skeleton")).toBeTruthy();
  });

  it("falha de carregamento oferece tentar de novo", async () => {
    const refetch = vi.fn();
    mockCfg.mockReturnValue(cfg({ data: undefined, isError: true, refetch }));
    const { getByTestId, getByText } = await render();
    expect(getByTestId("divergencias-error")).toBeTruthy();
    (await import("@testing-library/react")).fireEvent.click(getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalled();
  });

  it("sem destino: avisa que os avisos ficam só no app", async () => {
    const { getByTestId } = await render();
    expect(getByTestId("divergencias-sem-destino").textContent).toContain("só no app");
  });

  it("mostra quem recebe hoje", async () => {
    mockCfg.mockReturnValue(cfg({ data: { ativa: true, destino_user_id: "u2" } }));
    const { getByTestId, queryByTestId } = await render();
    expect(getByTestId("divergencias-destino-atual").textContent).toContain("Bruno");
    expect(queryByTestId("divergencias-sem-destino")).toBeNull();
  });

  it("o interruptor salva só `ativa`", async () => {
    const { getByTestId } = await render();
    (await import("@testing-library/react")).fireEvent.click(getByTestId("divergencias-toggle"));
    expect(mockSalvar).toHaveBeenCalledWith({ ativa: true });
  });

  it("escolher e limpar o destino salva só `destino_user_id`", async () => {
    const { getByTestId } = await render();
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(getByTestId("divergencias-destino"), { target: { value: "u1" } });
    expect(mockSalvar).toHaveBeenCalledWith({ destino_user_id: "u1" });
    fireEvent.change(getByTestId("divergencias-destino"), { target: { value: "" } });
    expect(mockSalvar).toHaveBeenCalledWith({ destino_user_id: null });
  });

  it("falha ao carregar pessoas é dita, não escondida", async () => {
    mockUsers.mockReturnValue({ data: undefined, isPending: false, isError: true });
    expect((await render()).getByTestId("divergencias-usuarios-erro")).toBeTruthy();
  });

  it("salvar recusado aparece na tela", async () => {
    Object.assign(salvarState, { isError: true, error: { body: { error: { message: "Só administradores." } } } });
    const { getByTestId } = await render();
    expect(getByTestId("divergencias-erro-salvar").textContent).toBe("Só administradores.");
  });
});
