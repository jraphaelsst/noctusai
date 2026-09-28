/**
 * `<ContratoPanel/>` — leftovers item 7: the "vivo" view (a live contrato
 * already exists) must keep showing "Abrir PDF do contrato" and the
 * simulation warning, sourced from the PERSISTED `useContratos` row so a
 * refetch never makes them vanish (they used to live only on the one-time
 * `gerarContrato` mutation result).
 */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { api } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn(), upload: vi.fn() },
}));
vi.mock("@noctusai/seed/infra", () => ({ api }));

import { ContratoPanel } from "../ContratoPanel";
import type { Orcamento } from "@/types/crm";

const ORCAMENTO = {
  id: "o1", negocio_id: "n1", lead_id: "l1", cliente_id: "c1", versao: 1, titulo: "Social mensal",
  status: "aceito", validade: null, itens: [], limites_escopo: {}, observacoes: null, pdf_key: null,
  enviado_em: null, respondido_em: null, aceito_em: null, recusado_em: null, motivo_recusa: null,
  created_at: "2026-09-01T10:00:00Z",
  lead: { id: "l1", nome: "Ana", email: "ana@padaria.com", empresa: "Padaria Sol" },
  negocio: { id: "n1", titulo: "Padaria", etapa_id: "s2", status: "ganho" },
  subtotal_criacao: 1000, subtotal_gestao: 500, desconto: 0, total_mensal: 1500,
  custo_estimado: 400, margem_estimada: 73.3, horas_estimadas: 10,
} as Orcamento;

const CONTRATO_VIVO_DIGITAL = {
  id: "k1", cliente_id: "c1", orcamento_id: "o1", numero: null, valor_mensal: 1500, posts_por_mes: 12,
  valor_excedente: 80, dia_vencimento: 10, data_inicio: "2026-09-28", data_fim: null,
  status: "aguardando_assinatura", modalidade_assinatura: "digital", assinado_em: null,
  assinado_manual_em: null, documento_key: "contratos/k1.pdf", documento_assinado_key: null,
  link_assinatura: "https://sim.example.test/assinar/k1", created_at: "2026-09-28T10:00:00Z",
};

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

describe("ContratoPanel — vivo view survives a refetch (leftovers item 7)", () => {
  it('shows "Abrir PDF do contrato" and the simulation warning for a LIVE digital contrato, sourced from useContratos (not the one-time gerarContrato result)', async () => {
    api.get.mockImplementation(async (path: string) => {
      if (path === "/api/contratos") return { data: [CONTRATO_VIVO_DIGITAL] };
      throw new Error(`GET inesperado ${path}`);
    });
    wrap(<ContratoPanel orcamento={ORCAMENTO} />);

    expect(await screen.findByText(/Contrato digital gerado/)).toBeInTheDocument();
    expect(screen.getByText(/Simulação \(assinatura digital ainda não integrada\)/)).toBeInTheDocument();
    expect(screen.getByTestId("contrato-vivo-abrir-pdf")).toHaveTextContent("Abrir PDF do contrato");

    // Clicking it fetches the signed URL and opens it — same mechanism the
    // Clientes → Orçamentos & Contratos tab already uses.
    api.get.mockImplementation(async (path: string) => {
      if (path === "/api/contratos") return { data: [CONTRATO_VIVO_DIGITAL] };
      if (path === "/api/contratos/k1/pdf") return { data: { url: "https://signed.example/k1.pdf", url_assinado: null } };
      throw new Error(`GET inesperado ${path}`);
    });
    const abrirSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    fireEvent.click(screen.getByTestId("contrato-vivo-abrir-pdf"));
    await waitFor(() => expect(abrirSpy).toHaveBeenCalledWith("https://signed.example/k1.pdf", "_blank", "noopener,noreferrer"));
  });

  it("hides the simulation warning and the PDF link when there is nothing to show (física, no documento yet)", async () => {
    api.get.mockImplementation(async (path: string) => {
      if (path === "/api/contratos")
        return {
          data: [{ ...CONTRATO_VIVO_DIGITAL, modalidade_assinatura: "fisica", status: "ativo",
                    link_assinatura: null, documento_key: null }],
        };
      throw new Error(`GET inesperado ${path}`);
    });
    wrap(<ContratoPanel orcamento={ORCAMENTO} />);
    await screen.findByText(/Contrato físico gerado/);
    expect(screen.queryByText(/Simulação/)).not.toBeInTheDocument();
    expect(screen.queryByTestId("contrato-vivo-abrir-pdf")).not.toBeInTheDocument();
  });
});
