/**
 * The Fechado gate (roadmap R4 — no close without an orçamento):
 *  - `useFechadoGate().onBeforeMove` lets every non-fechado move through and
 *    PARKS a fechado move until the picker decides,
 *  - the picker resolves `{extra: {orcamento_id}}` (spread into the
 *    `mover-etapa` body), `false` on cancel, and offers "Gerar orçamento"
 *    when the negócio has no eligible orçamento.
 */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { MoveIntentContext, PipelineStage } from "@noctusai/lib/components";

const { api } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn(), upload: vi.fn() },
}));
vi.mock("@noctusai/seed/infra", () => ({ api }));

import { FechadoOrcamentoPicker, orcamentosElegiveis, useFechadoGate } from "../FechadoOrcamentoPicker";
import type { Negocio, Orcamento } from "@/types/crm";

const stage = (id: string, papel: string | null): PipelineStage => ({
  id, slug: id, label: id, cor: "primary", posicao: 0, papel, ativo: true,
});

const NEGOCIO = {
  id: "n1", org_id: "org", lead_id: "l1", titulo: "Padaria", valor_estimado: 1500, etapa_id: "neg",
  kanban_pos: 0, responsavel_id: null, status: "aberto", stage_entered_at: null, ganho_em: null,
  perdido_em: null, motivo_perda: null, orcamento_aceito_id: null, cliente_id: null, created_at: "",
  lead: { id: "l1", nome: "Ana", empresa: "Padaria Ana", email: null, telefone: null, instagram: null, origem: "manual", status: "novo" },
  responsavel: null,
} as Negocio;

function ctx(to: PipelineStage, from = stage("neg", null)): MoveIntentContext<Negocio> {
  return { card: NEGOCIO, fromStage: from, toStage: to, toIndex: 0, direction: "forward", stepDistance: 1 };
}

const orc = (id: string, status: Orcamento["status"], versao = 1) =>
  ({ id, status, versao, titulo: "Social", total_mensal: 1500, negocio_id: "n1" }) as Orcamento;

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

describe("useFechadoGate", () => {
  it("lets a move to a non-fechado stage straight through", () => {
    const { result } = renderHook(() => useFechadoGate());
    expect(result.current.onBeforeMove(ctx(stage("negociacao", null)))).toBe(true);
    expect(result.current.pendente).toBeNull();
  });

  it("parks a move into the fechado ROLE (whatever its label) and resolves with extra.orcamento_id", async () => {
    const { result } = renderHook(() => useFechadoGate());
    let decisao: unknown;
    act(() => {
      void (result.current.onBeforeMove(ctx(stage("ganhamos!", "fechado"))) as Promise<unknown>).then((d) => {
        decisao = d;
      });
    });
    expect(result.current.pendente?.id).toBe("n1");
    act(() => result.current.decidir({ extra: { orcamento_id: "o2" } }));
    await waitFor(() => expect(decisao).toEqual({ extra: { orcamento_id: "o2" } }));
    expect(result.current.pendente).toBeNull();
  });

  it("cancel resolves false (card snaps back, nothing mutated)", async () => {
    const { result } = renderHook(() => useFechadoGate());
    let decisao: unknown = "pendente";
    act(() => {
      void (result.current.onBeforeMove(ctx(stage("fechado", "fechado"))) as Promise<unknown>).then((d) => {
        decisao = d;
      });
    });
    act(() => result.current.decidir(false));
    await waitFor(() => expect(decisao).toBe(false));
  });

  it("a same-column reorder inside fechado is not gated", () => {
    const f = stage("fechado", "fechado");
    const { result } = renderHook(() => useFechadoGate());
    expect(result.current.onBeforeMove(ctx(f, f))).toBe(true);
  });
});

describe("FechadoOrcamentoPicker", () => {
  it("only offers orçamentos that can still be the accepted one", () => {
    expect(
      orcamentosElegiveis([orc("a", "rascunho"), orc("b", "enviado"), orc("c", "aceito"), orc("d", "recusado"), orc("e", "expirado"), orc("f", "substituido")]).map((o) => o.id),
    ).toEqual(["a", "b", "c"]);
  });

  it("lists the negócio's orçamentos and confirms the chosen id", async () => {
    api.get.mockResolvedValue({ data: [orc("o1", "enviado", 1), orc("o2", "rascunho", 2), orc("o0", "substituido", 0)] });
    const onEscolher = vi.fn();
    wrap(<FechadoOrcamentoPicker negocio={NEGOCIO} onEscolher={onEscolher} onCancelar={vi.fn()} onGerarOrcamento={vi.fn()} />);
    expect(await screen.findByText("Qual orçamento foi aceito?")).toBeInTheDocument();
    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/api/orcamentos", { negocio_id: "n1" }));
    const opcoes = await screen.findAllByRole("radio");
    expect(opcoes).toHaveLength(2);
    const fechar = screen.getByRole("button", { name: "Fechar negócio" });
    expect(fechar).toBeDisabled();
    fireEvent.click(screen.getByRole("radio", { name: /v2/ }));
    fireEvent.click(fechar);
    expect(onEscolher).toHaveBeenCalledWith("o2");
  });

  it("with no eligible orçamento offers Gerar orçamento instead of a close", async () => {
    api.get.mockResolvedValue({ data: [orc("o0", "recusado")] });
    const onGerar = vi.fn();
    wrap(<FechadoOrcamentoPicker negocio={NEGOCIO} onEscolher={vi.fn()} onCancelar={vi.fn()} onGerarOrcamento={onGerar} />);
    fireEvent.click(await screen.findByRole("button", { name: /Gerar orçamento/ }));
    expect(onGerar).toHaveBeenCalledWith(NEGOCIO);
    expect(screen.queryByRole("button", { name: "Fechar negócio" })).toBeNull();
  });

  it("cancel reports upward", async () => {
    api.get.mockResolvedValue({ data: [] });
    const onCancelar = vi.fn();
    wrap(<FechadoOrcamentoPicker negocio={NEGOCIO} onEscolher={vi.fn()} onCancelar={onCancelar} onGerarOrcamento={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Cancelar" }));
    expect(onCancelar).toHaveBeenCalled();
  });
});
