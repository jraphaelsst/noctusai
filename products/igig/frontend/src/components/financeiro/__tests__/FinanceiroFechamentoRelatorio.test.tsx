/**
 * Financeiro (Slice F): resumo cards + "Gerar competência", and the Relatório
 * sheet — on-screen preview (json) and authenticated file download (pdf/csv).
 */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

const { api, toast } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn(), upload: vi.fn(), download: vi.fn() },
  toast: { success: vi.fn(), error: vi.fn() },
}));
vi.mock("@noctusai/seed/infra", () => ({ api }));
vi.mock("sonner", () => ({ toast }));

import { FechamentoMes } from "../FechamentoMes";
import { RelatorioSheet } from "../RelatorioSheet";

const RESUMO = { competencia: "2026-09", mrr: 4500, a_receber: 3000, recebido: 1500, inadimplente_valor: 900, inadimplente_qtd: 1 };
const COMERCIAL = {
  tipo: "comercial",
  periodo: { inicio: "2026-09-01", fim: "2026-09-23" },
  financeiro: null,
  comercial: {
    periodo: { inicio: "2026-09-01", fim: "2026-09-23" },
    funil: [{ etapa_id: "s1", etapa_label: "Primeiro contato", entradas: 4, saidas: 3 }],
    negocios_ganhos: 2, negocios_ganhos_valor: 3000, negocios_perdidos: 1, negocios_perdidos_valor: 800,
    motivos_perda: [{ motivo: "sem orçamento", etapa_label: "Proposta", quantidade: 1, valor_total: 800 }],
    dwell_time_medio_dias: 3.5, orcamentos_enviados: 5, orcamentos_aceitos: 2, orcamentos_recusados: 1,
    ticket_medio: 1500, alertas: [],
  },
};

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockImplementation(async (path: string, params?: Record<string, unknown>) => {
    if (path === "/api/financeiro/resumo") return RESUMO; // bare — the router has no envelope today
    if (path === "/api/relatorios/comercial" && params?.formato === "json") return { data: COMERCIAL };
    if (path === "/api/relatorios/financeiro") {
      return {
        data: {
          tipo: "financeiro", periodo: COMERCIAL.periodo, comercial: null,
          financeiro: {
            periodo: COMERCIAL.periodo, faturamento: 3000, recebido: 1500, a_receber: 1500, inadimplencia_valor: 0,
            inadimplencia_qtd: 0, alertas: [],
            clientes: [{ cliente_id: "c1", cliente_nome: "Padaria Sol", faturamento: 1000, recebido: 1000, a_receber: 0, custo: 1200 }],
          },
        },
      };
    }
    throw new Error(`GET inesperado ${path}`);
  });
  api.post.mockResolvedValue({ criadas: [{ id: "f1" }, { id: "f2" }], existentes: [{ id: "f0" }] });
  api.download.mockResolvedValue(new Blob(["a;b"], { type: "text/csv" }));
});
afterEach(cleanup);

describe("FechamentoMes", () => {
  it("shows the resumo of the competência", async () => {
    wrap(<FechamentoMes competencia="2026-09" />);
    const bloco = await screen.findByTestId("fechamento-mes");
    expect(await within(bloco).findByText("MRR")).toBeInTheDocument();
    expect(within(bloco).getByText("1 fatura(s)")).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith("/api/financeiro/resumo", { competencia: "2026-09" });
  });

  it("Gerar competência posts the month and reports created vs existing", async () => {
    wrap(<FechamentoMes competencia="2026-09" />);
    fireEvent.click(await screen.findByTestId("gerar-competencia"));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/api/financeiro/faturas/gerar-competencia", { competencia: "2026-09" }),
    );
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith("2 fatura(s) criada(s) · 1 já existia(m) em 2026-09."),
    );
  });

  it("shows the server's error instead of zeros", async () => {
    api.get.mockRejectedValue(new Error("banco indisponível"));
    wrap(<FechamentoMes competencia="2026-09" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("banco indisponível");
  });
});

describe("RelatorioSheet", () => {
  it("previews the financeiro report, with per-cliente margin recomputed", async () => {
    wrap(<RelatorioSheet open onClose={() => undefined} />);
    const preview = await screen.findByTestId("relatorio-preview");
    expect(within(preview).getByText("Padaria Sol")).toBeInTheDocument();
    // faturamento 1000 − custo 1200 ⇒ negative margin, -20%.
    expect(within(preview).getByText(/-20%/)).toBeInTheDocument();
  });

  it("switching to comercial previews the funnel", async () => {
    wrap(<RelatorioSheet open onClose={() => undefined} />);
    await screen.findByTestId("relatorio-preview");
    fireEvent.change(screen.getByLabelText("Tipo de relatório"), { target: { value: "comercial" } });
    expect(await screen.findByText("Primeiro contato")).toBeInTheDocument();
    expect(screen.getByText("75%")).toBeInTheDocument();
  });

  it("CSV downloads through the authenticated client with the period", async () => {
    // jsdom has no object-URL support (a browser API, not ours) — provide it
    // for this test and put the originals back after.
    const originais = { create: URL.createObjectURL, revoke: URL.revokeObjectURL };
    const createObjectURL = vi.fn(() => "blob:x");
    URL.createObjectURL = createObjectURL;
    URL.revokeObjectURL = vi.fn();
    try {
      wrap(<RelatorioSheet open onClose={() => undefined} />);
      fireEvent.change(screen.getByLabelText("Início do período"), { target: { value: "2026-08-01" } });
      fireEvent.change(screen.getByLabelText("Fim do período"), { target: { value: "2026-08-31" } });
      fireEvent.click(screen.getByRole("button", { name: /CSV/ }));
      await waitFor(() =>
        expect(api.download).toHaveBeenCalledWith("/api/relatorios/financeiro?inicio=2026-08-01&fim=2026-08-31&formato=csv"),
      );
      await waitFor(() => expect(createObjectURL).toHaveBeenCalled());
    } finally {
      URL.createObjectURL = originais.create;
      URL.revokeObjectURL = originais.revoke;
    }
  });

  it("an inverted period is refused before any request", async () => {
    wrap(<RelatorioSheet open onClose={() => undefined} />);
    fireEvent.change(screen.getByLabelText("Início do período"), { target: { value: "2026-09-10" } });
    fireEvent.change(screen.getByLabelText("Fim do período"), { target: { value: "2026-09-01" } });
    expect(await screen.findByText("O fim vem antes do início.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /CSV/ })).toBeDisabled();
  });
});
