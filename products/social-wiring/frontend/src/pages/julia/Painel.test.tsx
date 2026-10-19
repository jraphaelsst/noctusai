import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const api = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("recharts", async () => {
  const React = await import("react");
  const Nil = () => null;
  return {
    ResponsiveContainer: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
    BarChart: Nil, Bar: Nil, XAxis: Nil, YAxis: Nil, CartesianGrid: Nil, Tooltip: Nil, Legend: Nil,
  };
});

import LaisPainel from "./Painel";

const BASE = {
  atividades: { consumo: { turnos: 120, custo_usd: 1.5, limite_diario_usd: 5 }, cobrancas: 4, pre_agendamentos: 7 },
  funil: { topo: 200, atendidos: 150, enviados: 50 },
  por_canal: [{ canal: "WhatsApp", total: 120 }],
  status_por_canal: [{ canal: "WhatsApp", enviado: 50, nao_pronto: 10, erro: 2 }],
  por_hora: Array.from({ length: 24 }, (_, i) => i),
  fora_horario_pct: 35,
  por_dia_semana: [1, 2, 3, 4, 5, 6, 7],
  melhor_dia: 6,
  seis_meses: [{ mes: "2026-10", enviado: 5, nao_enviado: 3 }],
};

function setup(data: unknown = BASE) {
  api.get.mockResolvedValue({ data });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<MemoryRouter><QueryClientProvider client={qc}><LaisPainel /></QueryClientProvider></MemoryRouter>);
}

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

describe("Painel", () => {
  it("renders atividades with links and funnel percentages", async () => {
    setup();
    expect(await screen.findByText("120 turnos")).toBeTruthy();
    expect(screen.getByTestId("atividade-cobrancas").getAttribute("href")).toBe("/lais/notificacoes?tipo=cobranca_atendimento");
    expect(screen.getByTestId("atividade-pre-agendamentos").getAttribute("href")).toBe("/lais/visitas");
    expect(screen.getByTestId("funil-topo-pct").textContent).toBe("100%");
    expect(screen.getByTestId("funil-atendidos-pct").textContent).toBe("75%");
    expect(screen.getByTestId("funil-enviados-pct").textContent).toBe("25%");
    expect(screen.getByTestId("dados-por-canal").textContent).toContain("WhatsApp: 120");
    expect(screen.getByText(/35% fora do horário comercial/)).toBeTruthy();
    expect(screen.getByText(/Melhor dia da semana: Domingo/)).toBeTruthy();
  });

  it("shows 'Consumo indisponível' when consumo is null", async () => {
    setup({ ...BASE, atividades: { ...BASE.atividades, consumo: null } });
    expect(await screen.findByText("Consumo indisponível")).toBeTruthy();
  });

  it("shows the empty-month state", async () => {
    setup({ ...BASE, funil: { topo: 0, atendidos: 0, enviados: 0 } });
    expect(await screen.findByTestId("painel-vazio")).toBeTruthy();
    expect(screen.getByTestId("funil-topo-pct").textContent).toBe("0%");
  });

  it("refetches with the new month keeping data on screen", async () => {
    setup();
    await screen.findByText("120 turnos");
    fireEvent.change(screen.getByLabelText("Mês"), { target: { value: "2026-09" } });
    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/api/lais/painel?mes=2026-09"));
    expect(screen.queryByTestId("painel-skeleton")).toBeNull();
  });
});
