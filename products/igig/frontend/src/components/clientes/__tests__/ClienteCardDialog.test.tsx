/**
 * The cliente card — the seed `CardHubDialog` organ with igig's cliente
 * registry (roadmap R9). Real organ + real hooks over a mocked `api`; the
 * three heavyweight tabs that have their own tests (Marcas, Calendário,
 * Esteira) are stubbed to prove they receive THIS cliente's id.
 */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { api } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn(), upload: vi.fn() },
}));
vi.mock("@noctusai/seed/infra", () => ({ api, useAuthStore: () => ({ user: { id: "u1", user_metadata: {} } }) }));
vi.mock("@/components/marca/MarcasSubpage", () => ({
  MarcasSubpage: ({ clienteId }: { clienteId: string }) => <p>marcas de {clienteId}</p>,
}));
vi.mock("@/components/calendario/CalendarioMes", () => ({
  CalendarioMes: ({ clienteId }: { clienteId: string }) => <p>calendário de {clienteId}</p>,
}));
vi.mock("@/components/esteira/EsteiraBoard", () => ({
  EsteiraBoard: ({ clienteId }: { clienteId: string }) => <p>esteira de {clienteId}</p>,
}));

import { ClienteCardDialog } from "../ClienteCardDialog";

const CLIENTE = {
  id: "c1", org_id: "org", nome: "Padaria Sol", nicho: "Alimentação", email: "sol@padaria.com", telefone: null,
  status: "ativo", origem: "indicação", observacoes: null, created_at: "2026-09-01T10:00:00Z", updated_at: null,
};
const RESUMO = {
  tags: [], membros: [], descricao: null,
  datas: { data_inicio: null, data_entrega: null, entrega_concluida: false, lembrete_minutos_antes: null, recorrencia: null },
  badges: { notas: 0, documentos: 0, touches: 0, checklist_total: 0, checklist_concluidos: 0, tem_descricao: false, temperatura: null },
};
const CONTRATO_FISICO = {
  id: "k1", cliente_id: "c1", orcamento_id: "o1", numero: "2026-001", valor_mensal: 1500, posts_por_mes: 12,
  valor_excedente: 80, dia_vencimento: 10, data_inicio: null, data_fim: null, status: "aguardando_assinatura",
  modalidade_assinatura: "fisica", assinado_em: null, assinado_manual_em: null, documento_key: "org/k1.pdf",
  documento_assinado_key: null, link_assinatura: null, created_at: "2026-09-20T10:00:00Z",
};

function renderCard(onClose = vi.fn(), onAbrirOrcamento = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ClienteCardDialog clienteId="c1" onClose={onClose} onAbrirOrcamento={onAbrirOrcamento} />
    </QueryClientProvider>,
  );
  return { onClose, onAbrirOrcamento };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockImplementation(async (path: string, params?: Record<string, unknown>) => {
    if (path === "/api/clientes/c1") return CLIENTE;
    if (path === "/api/clientes/c1/card") return RESUMO;
    if (path.startsWith("/api/clientes/c1/timeline")) return { items: [], total: 0, next_cursor: null };
    if (path === "/api/custos/profissionais") return [];
    if (path === "/api/orcamentos" && params?.cliente_id === "c1") return { data: [] };
    if (path === "/api/contratos" && params?.cliente_id === "c1") return { data: [CONTRATO_FISICO] };
    if (path.startsWith("/api/clientes/")) return { items: [] };
    throw new Error(`GET inesperado ${path}`);
  });
  api.patch.mockImplementation(async (_p: string, body: Record<string, unknown>) => ({ ...CLIENTE, ...body }));
  api.upload.mockResolvedValue({ data: { ...CONTRATO_FISICO, status: "ativo" } });
});
afterEach(cleanup);

/** The seed rail's tab buttons carry `card-subpage-tab-<key>`; the rail
 * renders once the card resumo has loaded (skeleton before). */
async function abrirAba(chave: string) {
  fireEvent.click(await screen.findByTestId(`card-subpage-tab-${chave}`));
}

describe("ClienteCardDialog", () => {
  it("opens the seed card titled with the cliente, Geral first, with the cliente summary", async () => {
    renderCard();
    const card = await screen.findByTestId("cliente-card-dialog");
    expect((await within(card).findAllByText("Padaria Sol")).length).toBeGreaterThan(0);
    expect(await screen.findByTestId("cliente-resumo")).toHaveTextContent("sol@padaria.com");
  });

  it("registers the seven cliente subpages", async () => {
    renderCard();
    await screen.findByTestId("card-subpage-tab-geral");
    for (const chave of ["geral", "dados", "marcas", "orcamentos", "calendario", "esteira", "financeiro"]) {
      expect(screen.getByTestId(`card-subpage-tab-${chave}`)).toBeInTheDocument();
    }
    expect(screen.getByTestId("card-subpage-tab-orcamentos")).toHaveAccessibleName("Orçamentos & Contratos");
  });

  it("Marcas / Calendário / Esteira tabs receive this cliente's id", async () => {
    renderCard();
    await screen.findByTestId("cliente-card-dialog");
    await abrirAba("marcas");
    expect(await screen.findByText("marcas de c1")).toBeInTheDocument();
    await abrirAba("calendario");
    expect(await screen.findByText("calendário de c1")).toBeInTheDocument();
    await abrirAba("esteira");
    expect(await screen.findByText("esteira de c1")).toBeInTheDocument();
  });

  it("Dados edits the cliente through PATCH /api/clientes/{id}", async () => {
    renderCard();
    await screen.findByTestId("cliente-card-dialog");
    await abrirAba("dados");
    const dados = await screen.findByTestId("cliente-dados");
    const nicho = within(dados).getByDisplayValue("Alimentação");
    fireEvent.change(nicho, { target: { value: "Panificação" } });
    fireEvent.click(within(dados).getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith("/api/clientes/c1", expect.objectContaining({ nicho: "Panificação" })),
    );
  });

  it("a física contract is marked signed with the scanned copy (multipart upload)", async () => {
    renderCard();
    await screen.findByTestId("cliente-card-dialog");
    await abrirAba("orcamentos");
    fireEvent.click(await screen.findByTestId("contrato-marcar-assinado"));
    const sheet = await screen.findByTestId("marcar-assinado-sheet");
    const arquivo = new File(["%PDF"], "assinado.pdf", { type: "application/pdf" });
    fireEvent.change(within(sheet).getByLabelText("Via assinada"), { target: { files: [arquivo] } });
    fireEvent.click(within(sheet).getByRole("button", { name: "Confirmar assinatura" }));
    await waitFor(() => expect(api.upload).toHaveBeenCalledTimes(1));
    const [path, form] = api.upload.mock.calls[0] as [string, FormData];
    expect(path).toBe("/api/contratos/k1/marcar-assinado");
    expect((form.get("arquivo") as File).name).toBe("assinado.pdf");
  });
});
