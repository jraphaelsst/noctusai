/**
 * OrcamentoModal — the calculator end to end over a faked backend:
 * catalog picker → item row with weekday toggles → debounced `/calcular`
 * → the server's totals on screen; and the accept / read-only lifecycle.
 *
 * Real TanStack Query (no hook mocks); only the seed `api` client is faked,
 * and the fake `/calcular` applies the CONTRACT formula so the numbers on
 * screen are provably the server's, not a client re-derivation.
 */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { api } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn(), upload: vi.fn() },
}));
vi.mock("@noctusai/seed/infra", () => ({ api }));

import { OrcamentoModal } from "../OrcamentoModal";
import type { Orcamento, OrcamentoItemInput } from "@/types/crm";

const CATALOGO = [
  { id: "p-reels", secao: "criacao_conteudo", nome: "Reels", descricao: null, preco_base: 100, unidade: "unidade", horas_estimadas: 1, ativo: true, ordem: 0 },
  { id: "p-dms", secao: "gestao_conta", nome: "Gestão de DMs", descricao: null, preco_base: 500, unidade: "mês", horas_estimadas: 4, ativo: true, ordem: 0 },
];

const popcount = (m: number) => [1, 2, 4, 8, 16, 32, 64].filter((b) => m & b).length;

/** The contract's server formula — the fake backend, not the component. */
function calcular({ itens, desconto = 0 }: { itens: OrcamentoItemInput[]; desconto?: number }) {
  const linhas = itens.map((i) => {
    const quantidade_mensal = i.recorrente ? popcount(i.dias_semana) * i.qtd_por_dia * 4 : i.quantidade;
    return { ...i, quantidade_mensal, subtotal: i.preco_unitario * quantidade_mensal };
  });
  const soma = (s: string) => linhas.filter((l) => l.secao === s).reduce((a, l) => a + l.subtotal, 0);
  const total = soma("criacao_conteudo") + soma("gestao_conta") - desconto;
  const custo = total * 0.4;
  return {
    subtotal_criacao: soma("criacao_conteudo"),
    subtotal_gestao: soma("gestao_conta"),
    desconto,
    total_mensal: total,
    custo_estimado: custo,
    margem_estimada: total ? ((total - custo) / total) * 100 : 0,
    horas_estimadas: 10,
    itens: linhas,
  };
}

function orcamento(over: Partial<Orcamento> = {}): Orcamento {
  const itens = [
    { id: "i1", produto_servico_id: "p-reels", secao: "criacao_conteudo" as const, descricao: "Reels", preco_unitario: 100, recorrente: true, dias_semana: 1 | 4 | 16, qtd_por_dia: 1, quantidade: 1, quantidade_mensal: 12, subtotal: 1200, ordem: 0 },
  ];
  return {
    id: "o1", negocio_id: "n1", lead_id: "l1", cliente_id: null, versao: 2, titulo: "Social mensal", status: "enviado",
    validade: "2026-10-10", itens, limites_escopo: { revisoes_incluidas: 2, valor_excedente: 80 }, observacoes: null,
    pdf_key: "org/orcamentos/o1/v2.pdf", enviado_em: "2026-09-20T10:00:00Z", respondido_em: null, aceito_em: null,
    recusado_em: null, motivo_recusa: null, created_at: "2026-09-20T09:00:00Z",
    lead: { id: "l1", nome: "Ana", email: "ana@x.com", empresa: "Padaria Ana" },
    negocio: { id: "n1", titulo: "Padaria", etapa_id: "s2", status: "aberto" },
    subtotal_criacao: 1200, subtotal_gestao: 0, desconto: 0, total_mensal: 1200, custo_estimado: 480,
    margem_estimada: 60, horas_estimadas: 12,
    ...over,
  };
}

function renderModal(props: Partial<React.ComponentProps<typeof OrcamentoModal>> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <OrcamentoModal open onClose={vi.fn()} {...props} />
    </QueryClientProvider>,
  );
}

const norm = (s: string | null | undefined) => (s ?? "").replace(/\s/g, " ");

function ultimaCalculo() {
  const chamadas = api.post.mock.calls.filter(([p]) => p === "/api/orcamentos/calcular");
  return chamadas[chamadas.length - 1];
}

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockImplementation(async (path: string) => {
    if (path === "/api/produtos-servicos") return { data: CATALOGO };
    if (path === "/api/orcamentos/o1") return { data: orcamento() };
    if (path === "/api/orcamentos/o1/emails") return { data: [] };
    throw new Error(`GET inesperado ${path}`);
  });
  api.post.mockImplementation(async (path: string, body: any) => {
    if (path === "/api/orcamentos/calcular") return { data: calcular(body) };
    throw new Error(`POST inesperado ${path}`);
  });
});

afterEach(cleanup);

describe("OrcamentoModal — calculator", () => {
  it("adds a catalog item, toggles weekdays and shows the server's /calcular totals", async () => {
    renderModal({ negocioId: "n1" });

    const picker = await screen.findByRole("combobox", { name: "Adicionar item — Criação de conteúdo" });
    await waitFor(() => expect(within(picker).getByRole("option", { name: /Reels/ })).toBeInTheDocument());
    fireEvent.change(picker, { target: { value: "p-reels" } });

    // Default for content: weekdays (Seg–Sex) × 1.
    const segunda = await screen.findByRole("button", { name: "Segunda" });
    expect(segunda).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Sábado" })).toHaveAttribute("aria-pressed", "false");

    // Debounced /calcular with the bitmask 31 → 5 × 1 × 4 = 20 × R$100.
    await waitFor(
      () => expect(norm(screen.getByTestId("total-mensal").textContent)).toBe("R$ 2.000,00"),
      { timeout: 2000 },
    );
    const primeira = api.post.mock.calls.find(([p]) => p === "/api/orcamentos/calcular")!;
    expect(primeira[1].itens[0]).toMatchObject({ produto_servico_id: "p-reels", dias_semana: 31, qtd_por_dia: 1, recorrente: true });
    expect(norm(screen.getByTestId("item-resumo").textContent)).toBe("20/mês · R$ 2.000,00");

    // Toggle Sábado → 6 days → 24 × R$100.
    fireEvent.click(screen.getByRole("button", { name: "Sábado" }));
    await waitFor(
      () => expect(norm(screen.getByTestId("total-mensal").textContent)).toBe("R$ 2.400,00"),
      { timeout: 2000 },
    );
    const ultima = ultimaCalculo();
    expect(ultima[1].itens[0].dias_semana).toBe(63);
    expect(screen.getByTestId("margem-badge")).toHaveAttribute("data-nivel", "boa");
  });

  it("qty/day stepper and a one-off gestão item feed the same /calcular", async () => {
    renderModal({ negocioId: "n1" });
    const criacao = await screen.findByRole("combobox", { name: "Adicionar item — Criação de conteúdo" });
    await waitFor(() => expect(within(criacao).getByRole("option", { name: /Reels/ })).toBeInTheDocument());
    fireEvent.change(criacao, { target: { value: "p-reels" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Adicionar item — Gestão de conta" }), {
      target: { value: "p-dms" },
    });
    const stepper = await screen.findByRole("group", { name: "Quantidade por dia — Reels" });
    fireEvent.click(within(stepper).getByRole("button", { name: "Aumentar" }));

    // Reels 5×2×4=40 × 100 = 4000 ; DMs one-off 1 × 500 = 500.
    await waitFor(
      () => expect(norm(screen.getByTestId("total-mensal").textContent)).toBe("R$ 4.500,00"),
      { timeout: 2000 },
    );
    expect(norm(screen.getByTestId("total-gestao").textContent)).toBe("R$ 500,00");
    const ultima = ultimaCalculo();
    expect(ultima[1].itens.map((i: OrcamentoItemInput) => [i.secao, i.ordem])).toEqual([
      ["criacao_conteudo", 0],
      ["gestao_conta", 1],
    ]);
  });

  it("creating posts the negócio + items and switches to the saved orçamento", async () => {
    api.post.mockImplementation(async (path: string, body: any) => {
      if (path === "/api/orcamentos/calcular") return { data: calcular(body) };
      if (path === "/api/orcamentos") return { data: orcamento({ id: "o1", status: "rascunho", versao: 1 }) };
      throw new Error(`POST inesperado ${path}`);
    });
    const onOrcamentoChange = vi.fn();
    renderModal({ negocioId: "n1", onOrcamentoChange });
    const picker = await screen.findByRole("combobox", { name: "Adicionar item — Criação de conteúdo" });
    await waitFor(() => expect(within(picker).getByRole("option", { name: /Reels/ })).toBeInTheDocument());
    fireEvent.change(picker, { target: { value: "p-reels" } });
    fireEvent.click(screen.getByTestId("orcamento-salvar"));
    await waitFor(() => expect(onOrcamentoChange).toHaveBeenCalled());
    const criar = api.post.mock.calls.find(([p]) => p === "/api/orcamentos")!;
    expect(criar[1]).toMatchObject({ negocio_id: "n1", titulo: "Proposta mensal" });
    expect(criar[1].itens).toHaveLength(1);
    expect(criar[1].itens[0]).not.toHaveProperty("_key");
  });
});

describe("OrcamentoModal — lifecycle", () => {
  it("accept asks for confirmation, then POSTs /aceitar", async () => {
    api.post.mockImplementation(async (path: string, body: any) => {
      if (path === "/api/orcamentos/calcular") return { data: calcular(body) };
      if (path === "/api/orcamentos/o1/aceitar")
        return { data: { orcamento: orcamento({ status: "aceito" }), negocio: { id: "n1", status: "ganho" }, cliente: { id: "c1", nome: "Padaria Ana" }, pautas_criadas: 12 } };
      throw new Error(`POST inesperado ${path}`);
    });
    renderModal({ orcamentoId: "o1" });
    const aceitar = await screen.findByTestId("orcamento-aceitar");
    await waitFor(() => expect(aceitar).not.toBeDisabled());
    fireEvent.click(aceitar);
    expect(screen.getByText(/cria o cliente e gera as pautas/)).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalledWith("/api/orcamentos/o1/aceitar", expect.anything());
    fireEvent.click(screen.getByRole("button", { name: "Confirmar aceite" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/orcamentos/o1/aceitar", {}));
  });

  it("an accepted orçamento is read-only and offers the contract (Digital | Física)", async () => {
    api.get.mockImplementation(async (path: string) => {
      if (path === "/api/produtos-servicos") return { data: CATALOGO };
      if (path === "/api/orcamentos/o1") return { data: orcamento({ status: "aceito" }) };
      if (path === "/api/orcamentos/o1/emails") return { data: [] };
      throw new Error(`GET inesperado ${path}`);
    });
    api.post.mockImplementation(async (path: string) => {
      if (path === "/api/orcamentos/o1/contrato") {
        return {
          data: {
            contrato: {
              id: "k1", modalidade_assinatura: "fisica", valor_mensal: 1200,
              status: "aguardando_assinatura",
            },
            url: "https://igig.example.test/contratos/k1.pdf",
            assinatura: null,
          },
        };
      }
      throw new Error(`POST inesperado ${path}`);
    });
    renderModal({ orcamentoId: "o1" });
    const fisica = await screen.findByRole("radio", { name: /Física/ });
    // Read-only: no save, no accept/reject, weekday toggles disabled, stored totals shown.
    expect(screen.queryByTestId("orcamento-salvar")).toBeNull();
    expect(screen.queryByTestId("orcamento-aceitar")).toBeNull();
    expect(screen.getByRole("button", { name: "Segunda" })).toBeDisabled();
    expect(norm(screen.getByTestId("total-mensal").textContent)).toBe("R$ 1.200,00");
    expect(api.post).not.toHaveBeenCalledWith("/api/orcamentos/calcular", expect.anything());

    fireEvent.click(fisica);
    fireEvent.click(screen.getByRole("button", { name: "Gerar contrato" }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/api/orcamentos/o1/contrato", { modalidade_assinatura: "fisica", dia_vencimento: 10 }),
    );
    expect(await screen.findByTestId("contrato-gerado")).toHaveTextContent("Contrato físico gerado");
  });
});
