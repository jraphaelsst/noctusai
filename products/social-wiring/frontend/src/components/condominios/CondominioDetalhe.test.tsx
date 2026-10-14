/** CondominioDetalhe — loading / error / data states and admin gating. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const { mockDetalhe, mutate, isAdminRef } = vi.hoisted(() => ({
  mockDetalhe: vi.fn(),
  mutate: vi.fn(),
  isAdminRef: { current: true },
}));

vi.mock("@noctusai/lib/design-system", async () => ({
  ...(await vi.importActual<typeof import("@noctusai/lib/design-system")>("@noctusai/lib/design-system")),
  useEffectiveSSOContext: () => ({}),
}));
vi.mock("@noctusai/lib", () => ({ isOrgAdmin: () => isAdminRef.current }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("@/hooks/useCondominios", async () => {
  const m = () => ({ mutate, isPending: false });
  return {
    ...(await vi.importActual<typeof import("@/hooks/useCondominios")>("@/hooks/useCondominios")),
    useCondominio: (...a: unknown[]) => mockDetalhe(...a),
    useAtualizarCondominio: m, useAcaoCondominio: m, useRenomearCondominio: m,
    useFundirCondominio: m, useAdicionarAlias: m, useRemoverAlias: m,
  };
});

const BASE = {
  id: "c1", nome: "Vila Verde", nome_normalizado: "VILA VERDE", cidade: "Cotia", bairro: null, tipo: null,
  status_validacao: "sugerido", latitude: null, longitude: null, seguranca_nivel: null, portaria_24h: null,
  area_lazer: null, distancia_raposo_km: null, acesso_principal: null, observacoes: null, fundido_em_id: null,
  validado_em: null, imoveis_count: 5, anuncios_venda_count: 5, preco_m2_mediano: null, aliases_count: 1,
  aliases: [{ id: "a1", alias: "VILA VERDE", alias_normalizado: "VILA VERDE", origem: "sugestao", imoveis_count: 5 }],
  eventos: [],
};

async function render() {
  const { render: r } = await import("@testing-library/react");
  const { CondominioDetalhe } = await import("./CondominioDetalhe");
  return r(<CondominioDetalhe condominioId="c1" todos={[]} onClose={() => {}} />);
}

beforeEach(() => {
  vi.clearAllMocks();
  isAdminRef.current = true;
  mockDetalhe.mockReturnValue({ data: BASE, isPending: false, isError: false, error: null });
});

describe("CondominioDetalhe", () => {
  it("skeleton enquanto carrega", async () => {
    mockDetalhe.mockReturnValue({ data: undefined, isPending: true, isError: false, error: null });
    await render();
    expect(document.querySelector('[data-testid="condominio-detalhe-skeleton"]')).toBeTruthy();
  });

  it("erro sem dados", async () => {
    mockDetalhe.mockReturnValue({ data: undefined, isPending: false, isError: true, error: new Error("falhou") });
    await render();
    expect(document.body.textContent).toContain("falhou");
  });

  it("admin vê validar e as grafias; clicar valida", async () => {
    await render();
    const { fireEvent, screen } = await import("@testing-library/react");
    expect(screen.getByText(/Grafias do Vista \(1\)/)).toBeTruthy();
    fireEvent.click(screen.getByText("Validar"));
    expect(mutate).toHaveBeenCalledWith({ id: "c1", acao: "validar" }, expect.anything());
  });

  it("membro comum não vê as ações de admin, só os atributos", async () => {
    isAdminRef.current = false;
    await render();
    const { screen } = await import("@testing-library/react");
    expect(screen.queryByText("Validar")).toBeNull();
    expect(screen.queryByText("Renomear")).toBeNull();
    expect(screen.getByText("Salvar atributos")).toBeTruthy();
  });
});
