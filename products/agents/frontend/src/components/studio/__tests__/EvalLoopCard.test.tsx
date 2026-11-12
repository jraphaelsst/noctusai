/** EvalLoopCard — start form, active loop (alvo/piso, series, overcalls, failures), refusals, ended loop. */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@noctusai/lib";

const mockLoops = vi.fn();
const mockCreate = vi.fn();
const mockRound = vi.fn();
const mockStop = vi.fn();
const mockConfig = vi.fn();
const mockConfigSave = vi.fn();
const mockPlatformAdmin = vi.fn();
const CONFIG = { alvo: 0.95, orcamento_usd: 5, rodadas_max: 10, alterado_por: null, alterado_em: null };
vi.mock("@/hooks/studio/useEvalLoops", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/studio/useEvalLoops")>("@/hooks/studio/useEvalLoops");
  return {
    ...actual,
    useEvalLoops: () => mockLoops(),
    useCreateEvalLoop: () => ({ mutateAsync: mockCreate, isPending: false }),
    useRunLoopRound: () => ({ mutateAsync: mockRound, isPending: false }),
    useLoopConfig: () => mockConfig(),
    useUpdateLoopConfig: () => ({ mutateAsync: mockConfigSave, isPending: false }),
    useStopEvalLoop: () => ({ mutateAsync: mockStop, isPending: false }),
  };
});
vi.mock("@/hooks/useIsPlatformAdmin", () => ({ useIsPlatformAdmin: () => mockPlatformAdmin() }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { EvalLoopCard } from "@/components/studio/EvalLoopCard";

const rodada = (n: number, over: Record<string, unknown> = {}) => ({
  rodada: n, run_id: `r${n}`, status: "concluida", score: 0.6, custo_usd: 1.5, compiled_hash: "h", melhorou: null, overcall: false, falhas: [], ...over,
});
function loop(over: Record<string, unknown> = {}) {
  return {
    id: "l1", agente_chave: "isaia", suite: "comportamento", status: "ativo", motivo_parada: null, detalhe_parada: null,
    rodadas_planejadas: 30, rodadas_feitas: 3, alvo: 0.95, piso: 0.8, orcamento_usd: 20, gasto_usd: 4.5, restante_usd: 15.5,
    melhor_score: 0.7, score_atual: 0.65, acima_do_piso: false, started_at: "2026-11-12T00:00:00Z", stopped_at: null,
    serie: [rodada(1, { score: 0.6 }), rodada(2, { score: 0.7, melhorou: true }), rodada(3, { score: 0.65, overcall: true, falhas: ["caso-a", "caso-b"] })],
    overcalls: [{ rodada: 3, run_id: "r3", score: 0.65, custo_usd: 1.5 }], custo_overcalls_usd: 1.5,
    checkpoints: [{ rodada: 5, atingido: false, score: null, gasto_usd: null }], ...over,
  };
}
const state = (items: unknown[]) => ({ data: items, showSkeleton: false, isRefreshing: false, isError: false, error: null, refetch: vi.fn() });

beforeEach(() => {
  vi.clearAllMocks();
  mockLoops.mockReturnValue(state([]));
  mockConfig.mockReturnValue({ data: CONFIG, showSkeleton: false, isError: false });
  mockPlatformAdmin.mockReturnValue(false);
});
afterEach(cleanup);

describe("EvalLoopCard", () => {
  it("shows a skeleton while loading, never an empty state", () => {
    mockLoops.mockReturnValue({ ...state([]), data: undefined, showSkeleton: true });
    render(<EvalLoopCard agentKey="isaia" versionId="v1" />);
    expect(screen.getByTestId("loop-loading")).toBeTruthy();
    expect(screen.queryByTestId("loop-vazio")).toBeNull();
  });

  it("shows a retryable error", () => {
    const refetch = vi.fn();
    mockLoops.mockReturnValue({ ...state([]), data: undefined, isError: true, error: new Error("x"), refetch });
    render(<EvalLoopCard agentKey="isaia" versionId="v1" />);
    fireEvent.click(screen.getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalled();
  });

  it("empty: fields show the config as placeholder/cap and are omitted when blank (the server applies the config)", async () => {
    mockCreate.mockResolvedValue(loop());
    render(<EvalLoopCard agentKey="isaia" versionId="v1" />);
    expect(screen.getByTestId("loop-vazio")).toBeTruthy();
    const rod = screen.getByTestId("loop-rodadas") as HTMLInputElement;
    const orc = screen.getByTestId("loop-orcamento") as HTMLInputElement;
    expect([rod.placeholder, rod.max, orc.placeholder, orc.max]).toEqual(["10", "10", "5", "5"]);
    expect(screen.getByTestId("loop-config-resumo").textContent).toMatch(/até 10 rodadas e US\$5\.00.*alvo 95%/);
    fireEvent.click(screen.getByText("Iniciar loop de refinamento"));
    await waitFor(() => expect(mockCreate).toHaveBeenCalledWith({ suite: "comportamento", rodadas_planejadas: undefined, orcamento_usd: undefined }));
  });

  it("caps rounds and budget at the config client-side", () => {
    render(<EvalLoopCard agentKey="isaia" versionId="v1" />);
    fireEvent.change(screen.getByTestId("loop-rodadas"), { target: { value: "11" } });
    fireEvent.click(screen.getByText("Iniciar loop de refinamento"));
    expect(screen.getByText("Informe de 1 a 10 rodadas.")).toBeTruthy();
    fireEvent.change(screen.getByTestId("loop-rodadas"), { target: { value: "3" } });
    fireEvent.change(screen.getByTestId("loop-orcamento"), { target: { value: "6" } });
    fireEvent.click(screen.getByText("Iniciar loop de refinamento"));
    expect(screen.getByText(/no máximo US\$5\.00/)).toBeTruthy();
    expect(mockCreate).not.toHaveBeenCalled();
  });

  it("config editor only for platform admins; saves alvo as a fraction", async () => {
    const { rerender } = render(<EvalLoopCard agentKey="isaia" versionId="v1" />);
    expect(screen.queryByTestId("loop-config")).toBeNull();
    mockPlatformAdmin.mockReturnValue(true);
    mockConfigSave.mockResolvedValue({ ...CONFIG, rodadas_max: 8 });
    rerender(<EvalLoopCard agentKey="isaia" versionId="v1" />);
    fireEvent.change(screen.getByTestId("loop-config-rodadas"), { target: { value: "8" } });
    fireEvent.click(screen.getByTestId("loop-config-salvar"));
    await waitFor(() => expect(mockConfigSave).toHaveBeenCalledWith({ alvo: 0.95, orcamento_usd: 5, rodadas_max: 8 }));
  });

  it("surfaces the server's refusal detail when starting (409 loop_ativo_existente)", async () => {
    mockCreate.mockRejectedValue(new ApiError(409, "Já existe um loop ativo para esta suíte.", { detail: "Já existe um loop ativo para esta suíte.", code: "loop_ativo_existente" }));
    render(<EvalLoopCard agentKey="isaia" versionId="v1" />);
    fireEvent.click(screen.getByText("Iniciar loop de refinamento"));
    expect(await screen.findByText(/Já existe um loop ativo/)).toBeTruthy();
  });

  it("active loop: alvo/piso, round x of N, spend, series, overcalls, checkpoints, failing cases", () => {
    mockLoops.mockReturnValue(state([loop()]));
    render(<EvalLoopCard agentKey="isaia" versionId="v1" />);
    expect(screen.getByText(/Alvo 95% \/ piso 80%/)).toBeTruthy();
    expect(screen.getByTestId("loop-contagem").textContent).toBe("Rodada 3 de 30");
    expect(screen.getByTestId("loop-gasto").textContent).toMatch(/US\$4\.50.*US\$15\.50/);
    expect(screen.getByTestId("loop-rodada-3").textContent).toMatch(/65%.*overcall/);
    expect(screen.getByTestId("loop-overcalls").textContent).toMatch(/Rodada 3: 65%/);
    expect(screen.getByTestId("loop-checkpoints").textContent).toMatch(/Rodada 5: ainda não atingido/);
    expect(screen.getByTestId("loop-falhas").textContent).toMatch(/caso-a, caso-b/);
  });

  it("runs the next round with the loop id and the draft version", async () => {
    mockRound.mockResolvedValue({ id: "r4" });
    mockLoops.mockReturnValue(state([loop()]));
    render(<EvalLoopCard agentKey="isaia" versionId="v1" />);
    fireEvent.click(screen.getByTestId("loop-proxima"));
    await waitFor(() => expect(mockRound).toHaveBeenCalledWith({ loopId: "l1", versionId: "v1" }));
  });

  it("hash_inalterado shows the detail and the fix-first instruction", async () => {
    mockRound.mockRejectedValue(new ApiError(409, "O conteúdo do agente não mudou desde a rodada 3.", { detail: "O conteúdo do agente não mudou desde a rodada 3.", code: "hash_inalterado" }));
    mockLoops.mockReturnValue(state([loop()]));
    render(<EvalLoopCard agentKey="isaia" versionId="v1" />);
    fireEvent.click(screen.getByTestId("loop-proxima"));
    expect(await screen.findByText(/não mudou desde a rodada 3/)).toBeTruthy();
    expect(screen.getByTestId("loop-refusal-hash").textContent).toBe("Corrija o conteúdo antes da próxima rodada.");
  });

  it.each([
    ["execucao_em_andamento", "Você já tem uma avaliação em andamento (agente-base · comportamento). Aguarde terminar ou cancele-a antes de iniciar outra."],
    ["loop_ativo_do_usuario", "Você já tem um loop de avaliação ativo (agente-base · mecanismo). Continue as rodadas dele ou pare-o (\"Parar loop\") antes de iniciar rodadas de outro loop."],
  ])("one-run-per-user refusal %s shows the pt-BR detail", async (code, detail) => {
    mockRound.mockRejectedValue(new ApiError(409, detail, { detail, code }));
    mockLoops.mockReturnValue(state([loop()]));
    render(<EvalLoopCard agentKey="isaia" versionId="v1" />);
    fireEvent.click(screen.getByTestId("loop-proxima"));
    expect((await screen.findByTestId("loop-refusal")).textContent).toBe(detail);
  });

  it("disables the next round while one is in flight", () => {
    mockLoops.mockReturnValue(state([loop({ serie: [rodada(1, { status: "executando", score: null })] })]));
    render(<EvalLoopCard agentKey="isaia" versionId="v1" />);
    expect((screen.getByTestId("loop-proxima") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Rodada em andamento…")).toBeTruthy();
  });

  it("stops the loop", async () => {
    mockStop.mockResolvedValue(loop({ status: "parado" }));
    mockLoops.mockReturnValue(state([loop()]));
    render(<EvalLoopCard agentKey="isaia" versionId="v1" />);
    fireEvent.click(screen.getByTestId("loop-parar"));
    await waitFor(() => expect(mockStop).toHaveBeenCalledWith({ loopId: "l1" }));
  });

  it("stopped loop (sem_melhora, same hash): motivo and the warning", () => {
    mockLoops.mockReturnValue(state([loop({ status: "parado", motivo_parada: "sem_melhora", detalhe_parada: { seguidas: 2, conteudo_mudou: false } })]));
    render(<EvalLoopCard agentKey="isaia" versionId="v1" />);
    expect(screen.getByTestId("loop-encerrado").textContent).toMatch(/2 rodadas seguidas sem melhora/);
    expect(screen.getByTestId("loop-hash-warning").textContent).toMatch(/mesmo hash/);
    expect(screen.queryByTestId("loop-proxima")).toBeNull();
  });

  it("stopped loop with changed parts lists what changed", () => {
    mockLoops.mockReturnValue(state([loop({ status: "parado", motivo_parada: "sem_melhora", detalhe_parada: { conteudo_mudou: true, partes_alteradas: ["secao:x", "texto:y"] } })]));
    render(<EvalLoopCard agentKey="isaia" versionId="v1" />);
    expect(screen.getByTestId("loop-detalhe-parada").textContent).toMatch(/secao:x, texto:y/);
  });

  it("concluded loop at target", () => {
    mockLoops.mockReturnValue(state([loop({ status: "concluido", motivo_parada: "alvo_atingido", melhor_score: 1 })]));
    render(<EvalLoopCard agentKey="isaia" versionId="v1" />);
    expect(screen.getByTestId("loop-encerrado").textContent).toMatch(/chegou ao alvo/);
  });

  it("with an active loop on one suite the start form offers only the free suite", () => {
    mockLoops.mockReturnValue(state([loop()]));
    render(<EvalLoopCard agentKey="isaia" versionId="v1" />);
    const select = screen.getByTestId("loop-suite") as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => o.value)).toEqual(["mecanismo"]);
  });
});
