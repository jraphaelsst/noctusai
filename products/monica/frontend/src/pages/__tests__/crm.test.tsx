/**
 * Route tests for the CRM pages: each page mounts its seed organ and talks to monica's endpoints through the
 * product `api` client. Organ behaviour (drag, filters, thread, forms) is covered in `seed/lib`; this pins the
 * WIRING -- the right endpoint, the shared Funil/Lista filter, the `?chat=` deep link, "Ver lead", the Contexto
 * save payload, the settings sub-route and its admin gate.
 */
/// <reference types="@testing-library/jest-dom" />
import * as React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { ConfirmProvider } from "@noctusai/lib";

const state = vi.hoisted(() => ({ isAdmin: true }));
const { api } = vi.hoisted(() => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    upload: vi.fn(),
    download: vi.fn(),
  },
}));
vi.mock("@/lib/api", () => ({ api, getAuthToken: async () => null }));
vi.mock("@noctusai/lib/design-system", async (orig) => ({ ...(await orig<object>()), useIsOrgAdmin: () => state.isAdmin }));

import Configuracoes from "../Configuracoes";
import Contexto from "../Contexto";
import Conversas from "../Conversas";
import Dashboard from "../Dashboard";
import Leads from "../Leads";

const STAGES = [
  { slug: "lead", label: "Lead", color: null },
  { slug: "atendimento", label: "Atendimento", color: null },
  { slug: "negociacao", label: "Negociação", color: null },
  { slug: "fechado", label: "Fechado", color: null },
];
const CONFIG = {
  stages: STAGES,
  origins: [
    { slug: "whatsapp", label: "WhatsApp" },
    { slug: "instagram", label: "Instagram" },
    { slug: "indicacao", label: "Indicação" },
    { slug: "outro", label: "Outro" },
  ],
  whatsapp_origin: "whatsapp",
  default_origin: "outro",
};
const CHAT = "5511994573387@c.us";
const ANA = {
  id: "l1", name: "Ana Souza", phone: "+5511994573387", email: null, origin: "whatsapp", stage: "lead", position: 0,
  notes: null, tags: [], whatsapp_connection_id: "c1", whatsapp_chat_id: CHAT,
  first_contact_at: "2026-10-20T12:00:00+00:00", last_message_at: null, last_message_preview: "Oi, queria marcar uma conversa",
};
const BOARD = STAGES.map((s, i) => ({ etapa: s.slug, stage: s, total: i === 0 ? 1 : 0, exibidos: i === 0 ? 1 : 0, cards: i === 0 ? [ANA] : [] }));
const CONNECTION = {
  id: "c1", label: "Mônica", base_url: "http://waha", session_name: "default", webhook_url: null,
  created_at: "2026-10-20T12:00:00+00:00", updated_at: "2026-10-20T12:00:00+00:00",
};
const INBOX_CHAT = {
  chat_id: CHAT, name: "Ana Souza", phone: "+5511994573387", is_group: false, last_message_preview: "Oi",
  last_message_at: "2026-10-26T10:00:00+00:00", last_message_from_me: false, unread_count: 0,
};
const CONTEXTO = {
  agent_key: "monica-leads", version_id: "v1", versao: 1, faltando: [],
  declaradas: [
    { chave: "quem_sou", rotulo: "Quem sou", descricao: "Em poucas palavras", tipo: "texto_longo", obrigatoria: false, exemplo: null },
    { chave: "instagram", rotulo: "Instagram", descricao: "", tipo: "texto", obrigatoria: false, exemplo: null },
  ],
  valores: [{ chave: "quem_sou", valor: "Psicanalista." }],
};

function route(path: string): unknown {
  const p = path.split("?")[0];
  if (p === "/api/leads/config") return { data: CONFIG };
  if (p === "/api/leads/board") return { data: BOARD };
  if (p === "/api/leads") return { data: [ANA], next_cursor: null };
  if (p === `/api/leads/${ANA.id}`) return { data: ANA };
  if (p === "/api/whatsapp/connections") return [CONNECTION];
  if (p === "/api/whatsapp/connections/c1/chats") return { items: [INBOX_CHAT], next_cursor: null };
  if (p.endsWith("/messages")) return { items: [], has_more: false };
  if (p === "/api/contexto") return CONTEXTO;
  throw new Error(`unrouted GET ${path}`);
}

beforeEach(() => {
  state.isAdmin = true;
  api.get.mockReset().mockImplementation(async (path: string) => route(path));
  api.put.mockReset();
  api.post.mockReset().mockResolvedValue(null);
});
afterEach(cleanup);

function Where() {
  const l = useLocation();
  return <span data-testid="where">{l.pathname + l.search}</span>;
}

function renderAt(path: string, routePath: string, page: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ConfirmProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path={routePath} element={<>{page}<Where /></>} />
            <Route path="*" element={<Where />} />
          </Routes>
        </MemoryRouter>
      </ConfirmProvider>
    </QueryClientProvider>,
  );
}

const getsTo = (prefix: string) => api.get.mock.calls.filter(([p]) => String(p).split("?")[0] === prefix);

describe("Dashboard", () => {
  it("shows the real lead count per stage", async () => {
    renderAt("/", "/", <Dashboard />);
    expect(await screen.findByTestId("dashboard-total")).toHaveTextContent("1 lead no total.");
    expect(screen.getByTestId("dashboard-stage-lead")).toHaveTextContent("1");
    expect(screen.getByTestId("dashboard-stage-fechado")).toHaveTextContent("0");
  });

  it("a failed load says so with a retry -- never '0 leads'", async () => {
    api.get.mockImplementation(async (path: string) => {
      if (path.startsWith("/api/leads/board")) throw new Error("boom");
      return route(path);
    });
    renderAt("/", "/", <Dashboard />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível carregar o funil");
    expect(screen.queryByTestId("dashboard-total")).toBeNull();
  });
});

describe("Leads", () => {
  it("opens on the Funil (board) and switches to the Lista sub-route", async () => {
    renderAt("/leads", "/leads/*", <Leads />);
    expect(await screen.findByTestId("leads-board")).toBeInTheDocument();
    expect(await screen.findByText("Ana Souza")).toBeInTheDocument();
    expect(getsTo("/api/leads/board").length).toBeGreaterThan(0);

    fireEvent.mouseDown(screen.getByTestId("leads-view-lista"));
    fireEvent.click(screen.getByTestId("leads-view-lista"));
    expect(await screen.findByTestId("leads-list")).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent("/leads/lista");
    await waitFor(() => expect(getsTo("/api/leads").length).toBeGreaterThan(0));
  });

  it("Funil and Lista share the filters", async () => {
    renderAt("/leads", "/leads/*", <Leads />);
    const search = await screen.findByPlaceholderText(/buscar/i);
    fireEvent.change(search, { target: { value: "Ana" } });
    await waitFor(() => expect(api.get.mock.calls.some(([p, q]) => p === "/api/leads/board" && q?.q === "Ana")).toBe(true));

    fireEvent.mouseDown(screen.getByTestId("leads-view-lista"));
    fireEvent.click(screen.getByTestId("leads-view-lista"));
    await screen.findByTestId("leads-list");
    await waitFor(() => expect(api.get.mock.calls.some(([p, q]) => p === "/api/leads" && q?.q === "Ana")).toBe(true));
    expect(screen.getByPlaceholderText(/buscar/i)).toHaveValue("Ana");
  });

  it("'abrir conversa' in the lead modal deep-links the inbox on that chat", async () => {
    renderAt("/leads", "/leads/*", <Leads />);
    fireEvent.click(await screen.findByText("Ana Souza"));
    fireEvent.click(await screen.findByTestId("lead-detail-open-chat"));
    expect(screen.getByTestId("where")).toHaveTextContent(`/conversas?chat=${encodeURIComponent(CHAT)}`);
  });
});

describe("Conversas", () => {
  it("mounts the inbox on the first connection and opens the ?chat= deep link with a 'Ver lead' button", async () => {
    renderAt(`/conversas?chat=${encodeURIComponent(CHAT)}`, "/conversas", <Conversas />);
    await waitFor(() => expect(getsTo("/api/whatsapp/connections/c1/chats").length).toBeGreaterThan(0));
    expect(await screen.findByTestId("conversa-ver-lead")).toBeInTheDocument();
    // the lead is looked up by the number and matched on the chat id
    await waitFor(() => expect(api.get.mock.calls.some(([p, q]) => p === "/api/leads" && q?.q === "+5511994573387")).toBe(true));
  });

  it("with no connection it says so and links to the settings, instead of an empty inbox", async () => {
    api.get.mockImplementation(async (path: string) => (path === "/api/whatsapp/connections" ? [] : route(path)));
    renderAt("/conversas", "/conversas", <Conversas />);
    expect(await screen.findByTestId("conversas-sem-conexao")).toHaveTextContent("Nenhum WhatsApp conectado");
    expect(screen.getByRole("link", { name: /conectar um número/i })).toHaveAttribute("href", "/configuracoes/conexoes");
  });
});

describe("Contexto", () => {
  it("renders the declared fields with the saved values and saves EVERY declared key to /api/contexto", async () => {
    api.put.mockResolvedValue(CONTEXTO);
    renderAt("/contexto", "/contexto", <Contexto />);
    const quemSou = await screen.findByLabelText(/quem sou/i);
    expect(quemSou).toHaveValue("Psicanalista.");
    fireEvent.change(screen.getByLabelText(/instagram/i), { target: { value: "@psimonicatangerino" } });
    fireEvent.click(screen.getByRole("button", { name: /salvar/i }));
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    expect(api.put.mock.calls[0][0]).toBe("/api/contexto");
    expect(api.put.mock.calls[0][1]).toEqual({ valores: { quem_sou: "Psicanalista.", instagram: "@psimonicatangerino" } });
  });
});

describe("Configuracoes", () => {
  it("redirects the bare path to Conexões and shows the WhatsApp lines to an admin", async () => {
    renderAt("/configuracoes", "/configuracoes/*", <Configuracoes />);
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/configuracoes/conexoes"));
    expect(await screen.findByText("Mônica")).toBeInTheDocument();
    expect(getsTo("/api/whatsapp/connections").length).toBeGreaterThan(0);
  });

  it("a non-admin gets the restriction message and the connections are never fetched", async () => {
    state.isAdmin = false;
    renderAt("/configuracoes/conexoes", "/configuracoes/*", <Configuracoes />);
    expect(await screen.findByTestId("conexoes-acesso-restrito")).toBeInTheDocument();
    expect(getsTo("/api/whatsapp/connections")).toHaveLength(0);
  });
});
