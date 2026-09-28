/**
 * Ninho Vazio staff back office (FE-A) — render + wiring tests against the
 * shapes in products/community/projects/ninho-vazio/CONTRACT.md:
 * Grupoterapia page, Fluxo de caixa tab, Membros timeline + Criar acesso,
 * Cobrança section, Planos padrão banner, Assinaturas grace columns.
 *
 * `mockGet` routes by path — each page fires several endpoints.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import "@testing-library/jest-dom";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError } from "@noctusai/lib";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPut = vi.fn();
const mockPatch = vi.fn();
const mockDelete = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, put: mockPut, patch: mockPatch, delete: mockDelete },
}));

const mockUseAuthStore = vi.fn(() => ({ user: { user_metadata: { org_role: "admin" } } as unknown }));

vi.mock("@noctusai/seed/infra", () => {
  const noop = () => {};
  const api = { get: noop, post: noop, patch: noop, delete: noop };
  return {
    api,
    coreApi: api,
    supabase: {},
    appConfig: {},
    useAuthStore: () => mockUseAuthStore(),
    AuthProvider: ({ children }: { children?: unknown }) => children,
    NotificationBell: () => null,
    default: { api },
  };
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function renderPage(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

type Routes = Record<string, unknown>;
function routeGet(routes: Routes) {
  mockGet.mockImplementation((path: string) => {
    if (path in routes) {
      const v = routes[path];
      return v instanceof Error ? Promise.reject(v) : Promise.resolve(v);
    }
    return Promise.resolve({ items: [], total: 0 });
  });
}

const ADMIN = { user: { user_metadata: { org_role: "admin" } } };
const MODERADOR = { user: { user_metadata: { org_role: "moderador" } } };

beforeEach(() => {
  vi.clearAllMocks();
  mockUseAuthStore.mockReturnValue(ADMIN);
});

// ---------------------------------------------------------------- Grupoterapia

const SESSAO = {
  id: "s-1",
  titulo: "Roda de conversa",
  descricao: null,
  inicio: "2026-10-02T22:00:00Z",
  duracao_minutos: 90,
  link_sala: "https://meet.example/abc",
  vagas_fala: 8,
  status: "agendada",
  reservas: 2,
  created_at: "2026-09-20T00:00:00Z",
  updated_at: "2026-09-20T00:00:00Z",
};

describe("Grupoterapia (staff)", () => {
  it("lists sessions, carries the CVV care line, and opens the reservations", async () => {
    routeGet({
      "/api/grupoterapia/sessoes": { items: [SESSAO], total: 1 },
      "/api/grupoterapia/sessoes/s-1/reservas": {
        items: [{ id: "r-1", membro_id: "m-1", membro_nome: "Ana", status: "confirmada", created_at: "2026-09-25T00:00:00Z" }],
        total: 1,
      },
    });
    const Grupoterapia = (await import("../Grupoterapia")).default;
    renderPage(<Grupoterapia />);

    await waitFor(() => expect(screen.getByTestId("sessao-row-s-1")).toBeInTheDocument());
    expect(screen.getByRole("note")).toHaveTextContent("CVV 188");
    const row = screen.getByTestId("sessao-row-s-1");
    expect(within(row).getByText("2 / 8")).toBeInTheDocument();
    // Has reservations → cancel, never delete.
    expect(within(row).getByTestId("sessao-cancelar-s-1")).toBeInTheDocument();
    expect(within(row).queryByTestId("sessao-excluir-s-1")).not.toBeInTheDocument();

    fireEvent.click(within(row).getByTestId("sessao-reservas-s-1"));
    await waitFor(() => expect(screen.getByText("Ana")).toBeInTheDocument());
    expect(screen.getByText("Confirmada")).toBeInTheDocument();
  });

  it("cancels a session via PATCH status=cancelada", async () => {
    routeGet({ "/api/grupoterapia/sessoes": { items: [SESSAO], total: 1 } });
    mockPatch.mockResolvedValue({ ...SESSAO, status: "cancelada" });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const Grupoterapia = (await import("../Grupoterapia")).default;
    renderPage(<Grupoterapia />);

    fireEvent.click(await screen.findByTestId("sessao-cancelar-s-1"));
    await waitFor(() =>
      expect(mockPatch).toHaveBeenCalledWith("/api/grupoterapia/sessoes/s-1", { status: "cancelada" }),
    );
  });

  it("shows the empty state and hides write controls for a moderador", async () => {
    mockUseAuthStore.mockReturnValue(MODERADOR);
    routeGet({ "/api/grupoterapia/sessoes": { items: [], total: 0 } });
    const Grupoterapia = (await import("../Grupoterapia")).default;
    renderPage(<Grupoterapia />);

    await waitFor(() => expect(screen.getByText(/Nenhuma sessão ainda/)).toBeInTheDocument());
    expect(screen.queryByText("+ Nova sessão")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------- Fluxo de caixa

const LANCAMENTOS = {
  items: [
    {
      id: "l-1", tipo: "entrada", categoria: "assinatura", descricao: "Premium — Ana", valor_centavos: 2700,
      data: "2026-09-10", origem: "pagamento", pagamento_id: "pg-1", membro_id: "m-1", membro_nome: "Ana",
      created_at: "2026-09-10T00:00:00Z",
    },
    {
      id: "l-2", tipo: "saida", categoria: "marketing", descricao: "Anúncios", valor_centavos: 5000,
      data: "2026-09-12", origem: "manual", pagamento_id: null, membro_id: null, membro_nome: null,
      created_at: "2026-09-12T00:00:00Z",
    },
  ],
  total: 2,
  totais: { entradas_centavos: 2700, saidas_centavos: 5000, saldo_centavos: -2300 },
};

describe("Financeiro — Fluxo de caixa", () => {
  it("defaults to the current month, shows server totals, and only manual rows are editable", async () => {
    routeGet({
      "/api/lancamentos": LANCAMENTOS,
      "/api/lancamentos/categorias": { items: ["assinatura", "marketing", "outros"] },
    });
    const { default: FluxoDeCaixa, mesCorrente } = await import("../financeiro/FluxoDeCaixa");
    renderPage(<FluxoDeCaixa />);

    await waitFor(() => expect(screen.getByTestId("lancamento-row-l-1")).toBeInTheDocument());
    const { de, ate } = mesCorrente();
    expect(mockGet).toHaveBeenCalledWith("/api/lancamentos", expect.objectContaining({ de, ate, page: 1 }));
    expect(screen.getByText(/-\s?R\$\s?23,00|R\$\s?-23,00|−\s?R\$\s?23,00/)).toBeInTheDocument();

    const automatico = screen.getByTestId("lancamento-row-l-1");
    expect(within(automatico).getByText("Automático")).toBeInTheDocument();
    expect(within(automatico).queryByText("Editar")).not.toBeInTheDocument();
    expect(within(screen.getByTestId("lancamento-row-l-2")).getByTestId("lancamento-editar-l-2")).toBeInTheDocument();
  });

  it("creates a manual entry in centavos", async () => {
    routeGet({ "/api/lancamentos": { items: [], total: 0, totais: { entradas_centavos: 0, saidas_centavos: 0, saldo_centavos: 0 } } });
    mockPost.mockResolvedValue({});
    const { default: FluxoDeCaixa } = await import("../financeiro/FluxoDeCaixa");
    renderPage(<FluxoDeCaixa />);

    await waitFor(() => expect(screen.getByText("Nenhum lançamento neste período.")).toBeInTheDocument());
    fireEvent.click(screen.getByText("+ Novo lançamento"));
    const dialog = await screen.findByRole("dialog");
    const inputs = dialog.querySelectorAll("input");
    fireEvent.change(inputs[0], { target: { value: "equipe" } }); // categoria
    fireEvent.change(inputs[2], { target: { value: "150.5" } }); // valor
    fireEvent.change(inputs[3], { target: { value: "2026-09-15" } }); // data
    fireEvent.click(within(dialog).getByText("Salvar"));

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith("/api/lancamentos", {
        tipo: "saida",
        categoria: "equipe",
        descricao: null,
        valor_centavos: 15050,
        data: "2026-09-15",
      }),
    );
  });
});

// ---------------------------------------------------------------- Assinaturas grace columns

describe("Financeiro — Assinaturas carência", () => {
  it("shows the grace deadline and filters by carencia", async () => {
    routeGet({
      "/api/assinaturas": {
        items: [
          {
            id: "a-1", membro_id: "m-1", membro_nome: "Ana", plano_id: "p-2", plano_nome: "Premium",
            gateway: "asaas", estado: "carencia", metodo: "pix", ciclo: "mensal",
            iniciada_em: "2026-08-01T00:00:00Z", ativa_em: "2026-08-01T00:00:00Z", cancelada_em: null,
            inadimplente_desde: "2026-09-20T12:00:00Z", carencia_ate: "2026-09-25T12:00:00Z",
            pago_ate: "2026-09-20", proxima_cobranca: "2026-09-20", expirada_em: null,
            cancelamento_solicitado_por: null, cancelamento_motivo: null,
          },
        ],
        total: 1,
      },
    });
    const Financeiro = (await import("../Financeiro")).default;
    renderPage(<Financeiro />);

    const cell = await screen.findByTestId("assinatura-ciclo-vida-a-1");
    expect(cell).toHaveTextContent(/Carência até \d{2}\/\d{2}\/2026/);
    expect(cell).toHaveTextContent("Inadimplente desde");
    fireEvent.change(screen.getByLabelText("Filtrar por estado da assinatura"), { target: { value: "carencia" } });
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith("/api/assinaturas", expect.objectContaining({ estado: "carencia" })),
    );
    expect(screen.getByRole("option", { name: "Expirada" })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------- Membros

const MEMBRO = {
  id: "m-1", nome: "Ana", email: "ana@example.com", telefone: null, status: "ativo", plano_id: null,
  plano_nome: null, origem: "cadastro", tags: [], user_id: null, observacoes: null,
  entrou_em: "2026-09-01", created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z",
};

describe("Membros — timeline + Criar acesso", () => {
  function membrosRoutes(eventos: unknown) {
    routeGet({
      "/api/membros": { items: [MEMBRO], total: 1, resumo: { pendente: 0, ativo: 1, atrasado: 0, pausado: 0, cancelado: 0 } },
      "/api/membros/m-1/eventos": eventos,
    });
  }

  it("lists the timeline and adds a nota", async () => {
    membrosRoutes({
      items: [
        { id: "e-1", tipo: "acesso", descricao: "Cadastro realizado pelo site", dados: {}, autor_id: null, autor_nome: null, created_at: "2026-09-01T10:00:00Z" },
      ],
      total: 1,
    });
    mockPost.mockResolvedValue({ id: "e-2", tipo: "nota", descricao: "Ligou", dados: {}, autor_id: "u", autor_nome: "Mônica", created_at: "2026-09-28T10:00:00Z" });
    const Membros = (await import("../Membros")).default;
    renderPage(<Membros />);

    fireEvent.click(await screen.findByTestId("membro-row-m-1"));
    await waitFor(() => expect(screen.getByText("Cadastro realizado pelo site")).toBeInTheDocument());
    expect(mockGet).toHaveBeenCalledWith("/api/membros/m-1/eventos", { page: 1, page_size: 50 });

    fireEvent.change(screen.getByLabelText("Descrição do registro"), { target: { value: "Ligou" } });
    fireEvent.click(screen.getByText("Registrar"));
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith("/api/membros/m-1/eventos", { tipo: "nota", descricao: "Ligou" }),
    );
  });

  it("shows the timeline's empty state", async () => {
    membrosRoutes({ items: [], total: 0 });
    const Membros = (await import("../Membros")).default;
    renderPage(<Membros />);
    fireEvent.click(await screen.findByTestId("membro-row-m-1"));
    await waitFor(() => expect(screen.getByTestId("membro-timeline-vazio")).toBeInTheDocument());
  });

  it("creates access and shows the temporary password once", async () => {
    membrosRoutes({ items: [], total: 0 });
    mockPost.mockResolvedValue({ email: "ana@example.com", senha_temporaria: "Xk9-temp-123" });
    const Membros = (await import("../Membros")).default;
    renderPage(<Membros />);

    fireEvent.click(await screen.findByTestId("membro-row-m-1"));
    fireEvent.click(await screen.findByTestId("membro-criar-acesso"));
    fireEvent.click(await screen.findByTestId("criar-acesso-confirmar"));

    await waitFor(() => expect(screen.getByTestId("senha-temporaria")).toHaveTextContent("Xk9-temp-123"));
    expect(mockPost).toHaveBeenCalledWith("/api/membros/m-1/acesso", {});
    expect(window.localStorage.getItem("senha_temporaria")).toBeNull();
    fireEvent.click(screen.getByText("Concluir"));
    await waitFor(() => expect(screen.queryByText("Xk9-temp-123")).not.toBeInTheDocument());
  });

  it("renders the 409 detail when the member already has access", async () => {
    membrosRoutes({ items: [], total: 0 });
    mockPost.mockRejectedValue(new ApiError(409, "Este membro já tem acesso."));
    const Membros = (await import("../Membros")).default;
    renderPage(<Membros />);

    fireEvent.click(await screen.findByTestId("membro-row-m-1"));
    fireEvent.click(await screen.findByTestId("membro-criar-acesso"));
    fireEvent.click(await screen.findByTestId("criar-acesso-confirmar"));
    await waitFor(() => expect(screen.getByText("Este membro já tem acesso.")).toBeInTheDocument());
  });

  it("does not offer Criar acesso to a moderador", async () => {
    mockUseAuthStore.mockReturnValue(MODERADOR);
    membrosRoutes({ items: [], total: 0 });
    const Membros = (await import("../Membros")).default;
    renderPage(<Membros />);
    fireEvent.click(await screen.findByTestId("membro-row-m-1"));
    await screen.findByTestId("membro-timeline");
    expect(screen.queryByTestId("membro-criar-acesso")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------- Cobrança

describe("Configurações — Cobrança", () => {
  it("loads the grace config, saves it, and shows the routine report", async () => {
    routeGet({
      "/api/cobranca/configuracoes": { dias_carencia: 5, automacoes_ativas: true },
      "/api/settings/api-keys": { items: [], total: 0 },
    });
    mockPut.mockResolvedValue({ dias_carencia: 10, automacoes_ativas: true });
    mockPost.mockResolvedValue({
      relatorios: [{ nome: "carencias", pulado: false, examinadas: 4, alteradas: ["Ana → expirada"], erros: [] }],
    });
    const Configuracoes = (await import("../Configuracoes")).default;
    renderPage(<Configuracoes />);

    const panel = await screen.findByTestId("cobranca-panel");
    const dias = await within(panel).findByDisplayValue("5");
    fireEvent.change(dias, { target: { value: "10" } });
    fireEvent.click(within(panel).getByText("Salvar"));
    await waitFor(() =>
      expect(mockPut).toHaveBeenCalledWith("/api/cobranca/configuracoes", { dias_carencia: 10, automacoes_ativas: true }),
    );

    fireEvent.click(within(panel).getByText("Executar rotina agora"));
    await waitFor(() => expect(screen.getByTestId("cobranca-relatorio")).toHaveTextContent("Ana → expirada"));
    expect(mockPost).toHaveBeenCalledWith("/api/cobranca/executar-rotina", {});
  });

  it("refuses an out-of-range grace window client-side", async () => {
    routeGet({ "/api/cobranca/configuracoes": { dias_carencia: 5, automacoes_ativas: false } });
    const Configuracoes = (await import("../Configuracoes")).default;
    renderPage(<Configuracoes />);
    const panel = await screen.findByTestId("cobranca-panel");
    fireEvent.change(await within(panel).findByDisplayValue("5"), { target: { value: "61" } });
    fireEvent.submit(within(panel).getByText("Salvar").closest("form")!);
    expect(await within(panel).findByRole("alert")).toHaveTextContent("entre 0 e 60");
    expect(mockPut).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------- Planos padrão

describe("Planos — planos padrão", () => {
  it("offers to create the missing tiers and posts to /api/planos/padrao", async () => {
    routeGet({
      "/api/planos": {
        items: [
          {
            id: "p-0", nome: "Gratuito", descricao: null, preco_centavos: 0, ciclo: "mensal",
            entitlements: { feed: true, forum: true, chat: false, eventos: false, conteudo_ids: [], grupos_whatsapp: [], conteudo_todos: false, grupoterapia: "nenhum" },
            ativo: true, ordem: 0, membros_ativos: 3, created_at: "", updated_at: "",
          },
        ],
        total: 1,
      },
    });
    mockPost.mockResolvedValue({ criados: ["Ouvinte", "Premium"], existentes: ["Gratuito"] });
    const Planos = (await import("../Planos")).default;
    renderPage(<Planos />);

    const banner = await screen.findByTestId("planos-padrao-banner");
    expect(banner).toHaveTextContent("Ouvinte, Premium");
    expect(await screen.findByText("Sem grupoterapia")).toBeInTheDocument();
    fireEvent.click(within(banner).getByText("Criar planos padrão"));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith("/api/planos/padrao", {}));
  });
});
