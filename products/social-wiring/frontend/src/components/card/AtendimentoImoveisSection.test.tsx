/**
 * AtendimentoImoveisSection — list / pendente warning / add / principal /
 * remove, against contract §3.1–3.4 fixtures (hooks mocked at the boundary).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AtendimentoImovel } from "@/types/atendimentoImoveis";

const m = vi.hoisted(() => ({
  query: vi.fn(),
  adicionar: vi.fn(),
  principal: vi.fn(),
  remover: vi.fn(),
}));
vi.mock("@/hooks/useAtendimentoImoveis", () => ({
  useAtendimentoImoveis: m.query,
  useAtendimentoImoveisMutations: () => ({
    adicionar: { mutate: m.adicionar, isPending: false },
    definirPrincipal: { mutate: m.principal, isPending: false },
    remover: { mutate: m.remover, isPending: false },
  }),
}));
vi.mock("@/components/card/ImovelCodigoPicker", () => ({
  ImovelCodigoPicker: (p: { value: string | null; onChange: (c: string | null) => void }) => (
    <input
      data-testid="picker-stub"
      value={p.value ?? ""}
      onChange={(e) => p.onChange(e.target.value || null)}
    />
  ),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { AtendimentoImoveisSection } from "./AtendimentoImoveisSection";

function item(over: Partial<AtendimentoImovel> = {}): AtendimentoImovel {
  return {
    id: "i1",
    codigo: "ONE9441",
    origem: "lead",
    principal: true,
    em_negociacao: false,
    created_at: "2026-10-01T10:00:00Z",
    created_by: null,
    imovel: {
      codigo: "ONE9441",
      foto_destaque: "https://x/f.jpg",
      endereco: "Rua A, 10 — Centro, Cotia/SP",
      valor: 850000,
      valor_tipo: "venda",
    },
    ...over,
  };
}

function resp(data: unknown, over: Record<string, unknown> = {}) {
  return {
    data,
    showSkeleton: false,
    isRefreshing: false,
    isError: false,
    error: null,
    ...over,
  };
}

beforeEach(() => {
  m.query.mockReturnValue(
    resp({ items: [item()], total: 1, atendimento_id: "at-1", imovel_pendente: false }),
  );
});
afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
  Object.values(m).forEach((f) => f.mockReset());
});

async function abrir() {
  const rtl = await import("@testing-library/react");
  rtl.render(<AtendimentoImoveisSection clienteId="c1" atendimentoId="at-1" />);
  return rtl;
}

describe("AtendimentoImoveisSection", () => {
  it("mostra código, endereço, valor, origem e o selo Principal", async () => {
    const rtl = await abrir();
    const li = rtl.screen.getByTestId("atendimento-imovel-ONE9441");
    expect(li.textContent).toContain("ONE9441");
    expect(li.textContent).toContain("Rua A, 10 — Centro, Cotia/SP");
    expect(li.textContent).toContain("Lead");
    expect(rtl.screen.getByTestId("atendimento-imovel-principal-ONE9441")).toBeTruthy();
    expect(rtl.screen.queryByTestId("imovel-pendente-aviso")).toBeNull();
  });

  it("🔴 sem imóveis: aviso visível 'Imóvel pendente'", async () => {
    m.query.mockReturnValue(
      resp({ items: [], total: 0, atendimento_id: "at-1", imovel_pendente: true }),
    );
    const rtl = await abrir();
    expect(rtl.screen.getByTestId("imovel-pendente-aviso").textContent).toContain("Imóvel pendente");
  });

  it("skeleton só sem dados; refetch sobre dados mantém as linhas", async () => {
    m.query.mockReturnValue(resp(undefined, { showSkeleton: true }));
    let rtl = await abrir();
    expect(rtl.screen.getByTestId("atendimento-imoveis-loading")).toBeTruthy();
    rtl.cleanup();

    m.query.mockReturnValue(
      resp({ items: [item()], total: 1, atendimento_id: "at-1", imovel_pendente: false }, { isRefreshing: true }),
    );
    rtl = await abrir();
    expect(rtl.screen.getByTestId("atendimento-imovel-ONE9441")).toBeTruthy();
    expect(rtl.screen.getByTestId("atendimento-imoveis-refreshing")).toBeTruthy();
  });

  it("erro de carga é exibido", async () => {
    m.query.mockReturnValue(resp(undefined, { isError: true, error: new Error("[500] falhou") }));
    const rtl = await abrir();
    expect(rtl.screen.getByTestId("atendimento-imoveis-erro").textContent).toBe("falhou");
  });

  it("adicionar: picker → POST { codigo, origem:'manual', atendimento_id }", async () => {
    const rtl = await abrir();
    const btn = rtl.screen.getByTestId("atendimento-imovel-adicionar-btn") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    rtl.fireEvent.change(rtl.screen.getByTestId("picker-stub"), { target: { value: "ONE1" } });
    rtl.fireEvent.click(btn);
    expect(m.adicionar.mock.calls[0][0]).toEqual({
      codigo: "ONE1",
      origem: "manual",
      atendimento_id: "at-1",
    });
  });

  it("erro de adicionar mostra a mensagem tipada do backend (409 CONFLICT)", async () => {
    const { toast } = await import("sonner");
    const rtl = await abrir();
    rtl.fireEvent.change(rtl.screen.getByTestId("picker-stub"), { target: { value: "ONE9441" } });
    rtl.fireEvent.click(rtl.screen.getByTestId("atendimento-imovel-adicionar-btn"));
    m.adicionar.mock.calls[0][1].onError(
      new Error("[409] Este imóvel já está vinculado ao atendimento."),
    );
    expect(toast.error).toHaveBeenCalledWith("Este imóvel já está vinculado ao atendimento.");
  });

  it("definir principal só aparece nos não principais; remover chama DELETE por id", async () => {
    m.query.mockReturnValue(
      resp({
        items: [item(), item({ id: "i2", codigo: "ONE2", principal: false, origem: "manual", imovel: { codigo: "ONE2" } })],
        total: 2,
        atendimento_id: "at-1",
        imovel_pendente: false,
      }),
    );
    const rtl = await abrir();
    expect(rtl.screen.queryByTestId("atendimento-imovel-definir-principal-ONE9441")).toBeNull();
    rtl.fireEvent.click(rtl.screen.getByTestId("atendimento-imovel-definir-principal-ONE2"));
    expect(m.principal.mock.calls[0][0]).toEqual({ id: "i2" });
    rtl.fireEvent.click(rtl.screen.getByTestId("atendimento-imovel-remover-ONE2"));
    expect(m.remover.mock.calls[0][0]).toEqual({ id: "i2" });
  });

  it("erro 409 IMOVEL_EM_NEGOCIACAO ao remover é mostrado em pt-BR", async () => {
    const { toast } = await import("sonner");
    const rtl = await abrir();
    rtl.fireEvent.click(rtl.screen.getByTestId("atendimento-imovel-remover-ONE9441"));
    m.remover.mock.calls[0][1].onError(
      new Error("[409] Este imóvel está em negociação neste atendimento — altere a negociação antes de removê-lo."),
    );
    expect(toast.error).toHaveBeenCalledWith(
      "Este imóvel está em negociação neste atendimento — altere a negociação antes de removê-lo.",
    );
  });
});
