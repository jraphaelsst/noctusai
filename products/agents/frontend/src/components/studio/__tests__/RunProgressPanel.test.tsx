/** RunProgressPanel — live progress states: loading, error to load, running with ETA, errored run, partial, finished, mechanism (indeterminate). */
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RunProgresso } from "@/api/studio/types-ke";

const mockProgresso = vi.fn();
vi.mock("@/hooks/studio/useEvals", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/studio/useEvals")>("@/hooks/studio/useEvals");
  return { ...actual, useRunProgresso: () => mockProgresso() };
});

import { RunProgressPanel, RunProgressView, formatDuration } from "@/components/studio/RunProgressPanel";

const base: RunProgresso = {
  run_id: "r1", suite: "comportamento", status: "executando", ativo: true, indeterminado: false, total: 46, concluidos: 12,
  aprovados: 9, reprovados: 3, erros: 0, pulados: 0, score_parcial: 0.78, custo_usd: 0.4, limite_usd: 2,
  started_at: "2026-11-17T10:00:00Z", finished_at: null, decorrido_s: 75, eta_s: 210, erro: null, erro_codigo: null,
};
const state = (over: Record<string, unknown>) => ({ data: undefined, showSkeleton: false, isRefreshing: false, isError: false, error: null, ...over });

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

describe("formatDuration", () => {
  it.each([[null, "—"], [5, "5 s"], [75, "1 min 15 s"], [120, "2 min"], [3720, "1 h 2 min"]])("%s -> %s", (s, out) => {
    expect(formatDuration(s as number | null)).toBe(out);
  });
});

describe("RunProgressPanel", () => {
  it("renders nothing without a run id", () => {
    mockProgresso.mockReturnValue(state({}));
    const { container } = render(<RunProgressPanel agentKey="a" suite="comportamento" runId={null} />);
    expect(container.innerHTML).toBe("");
  });

  it("shows a skeleton while there is no data, never numbers", () => {
    mockProgresso.mockReturnValue(state({ showSkeleton: true }));
    render(<RunProgressPanel agentKey="a" suite="comportamento" runId="r1" />);
    expect(screen.getByTestId("run-progress-loading")).toBeTruthy();
    expect(screen.queryByTestId("run-progress")).toBeNull();
  });

  it("shows a red error with the reason when the progress cannot be loaded", () => {
    mockProgresso.mockReturnValue(state({ isError: true, error: new Error("falhou a rede") }));
    render(<RunProgressPanel agentKey="a" suite="comportamento" runId="r1" />);
    expect(screen.getByTestId("run-progress-load-error").textContent).toMatch(/Não foi possível carregar o progresso/);
  });

  it("running: done of total, a progressbar, passed / failed / errored, running score, cost against the limit, elapsed and ETA", () => {
    mockProgresso.mockReturnValue(state({ data: base }));
    render(<RunProgressPanel agentKey="a" suite="comportamento" runId="r1" />);
    expect(screen.getByTestId("run-progress-contagem").textContent).toBe("12 de 46 casos");
    const bar = screen.getByRole("progressbar");
    expect(bar.getAttribute("aria-valuenow")).toBe("26");
    expect(screen.getByTestId("run-progress-aprovados").textContent).toBe("9");
    expect(screen.getByTestId("run-progress-reprovados").textContent).toBe("3");
    expect(screen.getByTestId("run-progress-erros").textContent).toBe("0");
    expect(screen.getByTestId("run-progress-score").textContent).toBe("78%");
    expect(screen.getByTestId("run-progress-tempo").textContent).toMatch(/US\$0\.40 de US\$2\.00.*decorrido 1 min 15 s.*faltam ~3 min 30 s/);
    expect(screen.queryByTestId("run-progress-erro")).toBeNull();
  });

  it("an errored run is red, says no case was measured, has NO score (never 0%) and shows the code and text", () => {
    render(
      <RunProgressView p={{ ...base, status: "erro", ativo: false, concluidos: 46, aprovados: 0, reprovados: 0, erros: 46, score_parcial: null,
        eta_s: null, erro: "46 de 46 casos terminaram em erro. Primeiro erro: O agente não tem padrão de qualificação.",
        erro_codigo: "qualificacao_indisponivel" }} />,
    );
    expect(screen.getByTestId("run-progress-score").textContent).toBe("—");
    expect(screen.getByTestId("run-progress-erros").textContent).toBe("46");
    const erro = screen.getByTestId("run-progress-erro");
    expect(erro.textContent).toMatch(/não conseguiu medir nenhum caso/);
    expect(erro.textContent).toMatch(/O agente não tem padrão de qualificação/);
    expect(erro.textContent).toMatch(/qualificacao_indisponivel/);
    expect(screen.queryByText(/faltam/)).toBeNull();
  });

  it("a partial run says how many cases errored and that the score is over the measured ones", () => {
    render(<RunProgressView p={{ ...base, status: "parcial_com_erros", ativo: false, concluidos: 46, erros: 2, aprovados: 40, reprovados: 4, eta_s: null, erro: "2 de 46 casos terminaram em erro." }} />);
    expect(screen.getByTestId("run-progress-erro").textContent).toMatch(/2 caso\(s\) terminaram em erro.*só dos casos medidos/);
    expect(screen.getByTestId("run-progress-status").textContent).toBe("concluída com erros");
  });

  it("a mechanism run in flight is indeterminate: no invented percentage, an honest note", () => {
    render(<RunProgressView p={{ ...base, suite: "mecanismo", indeterminado: true, concluidos: null, aprovados: null, reprovados: null, erros: null, pulados: null, score_parcial: null, eta_s: null }} />);
    expect(screen.getByTestId("run-progress-contagem").textContent).toBe("Medindo a suíte…");
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBeNull();
    expect(screen.getByTestId("run-progress-indeterminado").textContent).toMatch(/só grava os resultados quando termina/);
    expect(screen.queryByTestId("run-progress-numeros")).toBeNull();
  });

  it("a finished run shows the success state without ETA", () => {
    render(<RunProgressView p={{ ...base, status: "concluida", ativo: false, concluidos: 46, aprovados: 44, reprovados: 2, score_parcial: 0.96, eta_s: null, finished_at: "2026-11-17T10:03:00Z", decorrido_s: 180 }} />);
    expect(screen.getByTestId("run-progress-contagem").textContent).toBe("46 de 46 casos");
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("100");
    expect(screen.getByTestId("run-progress-score").textContent).toBe("96%");
    expect(screen.getByTestId("run-progress-status").textContent).toBe("concluída");
    expect(screen.queryByText(/faltam/)).toBeNull();
  });
});
