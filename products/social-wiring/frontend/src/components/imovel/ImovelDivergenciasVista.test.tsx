/** ImovelDivergenciasVista — Vista-vs-ours divergences a human decides. */
import { afterEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ query: vi.fn(), resolver: vi.fn(), admin: true }));

vi.mock("@/hooks/useImovelDivergencias", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/useImovelDivergencias")>();
  return {
    ...actual,
    useImovelDivergencias: m.query,
    useResolverDivergencia: () => ({ mutate: m.resolver, isPending: false, error: null }),
  };
});
vi.mock("@noctusai/lib", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@noctusai/lib")>()),
  isOrgAdmin: () => m.admin,
}));
vi.mock("@noctusai/lib/design-system", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@noctusai/lib/design-system")>()),
  useEffectiveSSOContext: () => ({}),
}));

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { DivergenciaCampoBadge, ImovelDivergenciasVista } from "./ImovelDivergenciasVista";

afterEach(() => {
  cleanup();
  m.query.mockReset();
  m.resolver.mockReset();
  m.admin = true;
});

const div = (id: string, over = {}) => ({
  id,
  campo: "area_terreno",
  status: "pendente",
  valor_vista: 280,
  vista_em: "2026-11-01T10:00:00Z",
  valor_nosso: 300,
  nosso_em: "2026-10-20T10:00:00Z",
  nosso_por: { id: "u1", nome: "Ana" },
  origem: { tipo: "julia", contato_id: "c-9", thread_id: "t-1", trecho: "o terreno tem 300 m²" },
  ...over,
});
const ok = (items: unknown[]) => ({ data: items, isPending: false, isError: false });
const doRender = () =>
  render(
    <MemoryRouter>
      <ImovelDivergenciasVista codigo="AP1" />
    </MemoryRouter>,
  );

describe("ImovelDivergenciasVista", () => {
  it("renders nothing while loading and when nothing is pending", () => {
    m.query.mockReturnValue({ data: undefined, isPending: true, isError: false });
    expect(doRender().container.firstChild).toBeNull();
    cleanup();
    m.query.mockReturnValue(ok([div("d1", { status: "resolvido" })]));
    expect(doRender().container.firstChild).toBeNull();
  });

  it("shows an error card with retry when the read failed", () => {
    m.query.mockReturnValue({ data: undefined, isPending: false, isError: true, refetch: vi.fn() });
    doRender();
    expect(screen.getByTestId("imovel-divergencias-erro")).toBeTruthy();
  });

  it("shows both values with dates, the origin link and the count", () => {
    m.query.mockReturnValue(ok([div("d1")]));
    doRender();
    expect(screen.getByTestId("imovel-divergencias-contagem").textContent).toBe("1");
    const valores = screen.getByTestId("divergencia-d1-valores").textContent ?? "";
    expect(valores).toMatch(/Vista:\s*280/);
    expect(valores).toMatch(/Nosso:\s*300/);
    expect(screen.getByTestId("divergencia-d1-conversa").getAttribute("href")).toBe("/julia/conversas/h/c-9");
    expect(screen.getByTestId("divergencia-d1-origem").textContent).toContain("o terreno tem 300 m²");
  });

  it("resolves with Vista / ours / a manual value", () => {
    m.query.mockReturnValue(ok([div("d1")]));
    doRender();
    fireEvent.click(screen.getByTestId("divergencia-d1-usar-vista"));
    expect(m.resolver).toHaveBeenLastCalledWith({ id: "d1", escolha: "vista" });
    fireEvent.click(screen.getByTestId("divergencia-d1-manter-nosso"));
    expect(m.resolver).toHaveBeenLastCalledWith({ id: "d1", escolha: "nosso" });
    fireEvent.click(screen.getByTestId("divergencia-d1-corrigir"));
    fireEvent.change(screen.getByTestId("divergencia-d1-valor"), { target: { value: "295" } });
    fireEvent.click(screen.getByTestId("divergencia-d1-corrigir-salvar"));
    expect(m.resolver).toHaveBeenLastCalledWith({ id: "d1", escolha: "manual", valor: "295" });
  });

  it("hides the actions from a non-admin (the list stays visible)", () => {
    m.admin = false;
    m.query.mockReturnValue(ok([div("d1")]));
    doRender();
    expect(screen.getByTestId("divergencia-d1")).toBeTruthy();
    expect(screen.queryByTestId("divergencia-d1-usar-vista")).toBeNull();
  });

  it("keeps history collapsed until asked", () => {
    m.query.mockReturnValue(ok([div("d1"), div("d2", { status: "resolvido", resolucao: { escolha: "vista" } })]));
    doRender();
    expect(screen.queryByTestId("imovel-divergencias-historico")).toBeNull();
    fireEvent.click(screen.getByTestId("imovel-divergencias-historico-toggle"));
    expect(screen.getByTestId("divergencia-d2-resolucao").textContent).toBe("Usou o Vista");
  });
});

describe("DivergenciaCampoBadge", () => {
  it("counts pending divergences for the field, nothing at zero", () => {
    m.query.mockReturnValue(ok([div("d1"), div("d2", { campo: "vagas" })]));
    render(<DivergenciaCampoBadge codigo="AP1" campos={["area_terreno_m2", "area_terreno"]} />);
    expect(screen.getByTestId("divergencia-badge-area_terreno_m2").textContent).toBe("1");
    cleanup();
    const { container } = render(<DivergenciaCampoBadge codigo="AP1" campos={["testada_m"]} />);
    expect(container.firstChild).toBeNull();
  });
});
