/**
 * `/agentes/novo` — the new-agent wizard (agents-unified CONTRACT §6). Real hooks + a real QueryClient, only the
 * HTTP layer is stubbed, so this covers: the steps come from `modelo.assistente.passos` (fixture generated from the
 * backend model), a non-platform caller sees the standard not-found, validation blocks a step, a restored draft
 * says it is unsaved, and "Publicar" POSTs the §6 body, writes the new agent into the listing + page caches and
 * opens `/agentes/:key`.
 */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@noctusai/lib";
import type { AgenteModelo, AgentesPainelResponse } from "@/api/agentes/types";
import modeloJson from "@/api/agentes/__fixtures__/modelo-plataforma.json";
import { AGENTES_PAINEL_KEY, agentePainelKey } from "@/hooks/useAgentesPainel";
import { RASCUNHO_STORAGE_KEY, valoresIniciais } from "@/lib/assistente";
import NovoAgente from "@/pages/agente/NovoAgente";

const MODELO = modeloJson as unknown as AgenteModelo;
const PASSOS = MODELO.assistente!.passos;

const get = vi.fn();
const post = vi.fn();
vi.mock("@/lib/api", () => ({
  api: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) },
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const navigate = vi.fn();
vi.mock("react-router-dom", async (orig) => ({ ...(await orig<typeof import("react-router-dom")>()), useNavigate: () => navigate }));

const PAINEL: AgentesPainelResponse = {
  items: [
    {
      key: "julia", nome: "Julia", descricao: null, papel: "sdr", capacidades: [], origem: "instancia", tipo: "runtime",
      runtime: "llm", owner_product: null, usa_canais: true, ativo: true, estado_externo: null, aviso: null,
      secoes: ["visao-geral"], pode_alternar: false,
    },
  ],
  total: 1,
};

function rotas(modelo: AgenteModelo | Error = MODELO) {
  get.mockImplementation((url: string) => {
    if (url === "/api/studio/modelo") return modelo instanceof Error ? Promise.reject(modelo) : Promise.resolve(modelo);
    if (url === "/api/agents/painel") return Promise.resolve(PAINEL);
    if (url === "/api/studio/agents") return Promise.resolve({ items: [] });
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <NovoAgente />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return qc;
}

function rascunho(over: { modo?: "vazio" | "gerar"; passo?: string; valores?: Record<string, unknown> } = {}) {
  window.localStorage.setItem(
    RASCUNHO_STORAGE_KEY,
    JSON.stringify({
      modo: over.modo ?? "vazio",
      passo: over.passo ?? "identidade",
      chaveTocada: false,
      salvoEm: "2026-10-30T10:00:00.000Z",
      valores: { ...valoresIniciais(PASSOS), ...over.valores },
    }),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  rotas();
});
afterEach(cleanup);

describe("NovoAgente — steps from the model", () => {
  it("renders one rail step per `assistente.passos` entry, in model order, under its category", async () => {
    renderPage();
    const rail = await screen.findByRole("tablist", { name: "Etapas" });
    const tabs = within(rail).getAllByRole("tab");
    expect(tabs.map((t) => t.textContent?.replace(/^\d+/, "").replace("Opcional", ""))).toEqual(PASSOS.map((p) => p.titulo));
    expect(within(rail).getByText("Quem é")).toBeTruthy();
    expect(within(rail).getByText("Fechamento")).toBeTruthy();
    expect(screen.getByText("Etapa 1 de 10")).toBeTruthy();
    // identidade's fields, from the model
    expect(screen.getByTestId("assistente-plataforma-key")).toBeTruthy();
    expect(screen.getByTestId("assistente-plataforma-nome")).toBeTruthy();
  });

  it("a mixed step shows subtabs in AI mode only", async () => {
    rascunho({ passo: "papel", modo: "gerar", valores: { "plataforma.nome": "X" } });
    renderPage();
    const sub = await screen.findByRole("tablist", { name: "Papel" });
    expect(within(sub).getAllByRole("tab").map((t) => t.textContent)).toEqual(["Briefing para a IA", "Definição"]);
    fireEvent.click(screen.getByTestId("novo-agente-modo-vazio"));
    expect(screen.queryByRole("tablist", { name: "Papel" })).toBeNull();
    expect(screen.getByTestId("assistente-plataforma-padrao_qualificacao")).toBeTruthy();
  });

  it("AI mode shows the generation cost cap from the model", async () => {
    renderPage();
    fireEvent.click(await screen.findByTestId("novo-agente-modo-gerar"));
    expect(screen.getByTestId("novo-agente-nota-custo").textContent).toMatch(/US\$ 5,00/);
  });
});

describe("NovoAgente — access", () => {
  it("a caller without the wizard (not a platform admin) gets the standard not-found", async () => {
    rotas({ ...MODELO, tier: "org_admin", assistente: null, areas: [] });
    renderPage();
    expect(await screen.findByText("Pagina nao encontrada")).toBeTruthy();
    expect(screen.queryByRole("tablist", { name: "Etapas" })).toBeNull();
  });

  it("a 403 (not a member) is a not-found too, never a forbidden", async () => {
    rotas(new ApiError(403, "Erro HTTP 403", { detail: "forbidden" }));
    renderPage();
    expect(await screen.findByText("Pagina nao encontrada")).toBeTruthy();
  });

  it("any other failure shows an error with retry", async () => {
    rotas(new ApiError(500, "Erro HTTP 500", {}));
    renderPage();
    expect(await screen.findByRole("button", { name: /tentar/i })).toBeTruthy();
  });
});

describe("NovoAgente — validation", () => {
  it("blocks the step until the model's required fields are valid; the name fills the key", async () => {
    renderPage();
    await screen.findByTestId("assistente-plataforma-nome");
    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));
    expect(screen.getByRole("alert").textContent).toMatch(/obrigatório/);
    expect(screen.getByText("Etapa 1 de 10")).toBeTruthy();

    fireEvent.change(screen.getByTestId("assistente-plataforma-nome"), { target: { value: "Júlia Nova" } });
    expect((screen.getByTestId("assistente-plataforma-key") as HTMLInputElement).value).toBe("julia-nova");
    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));
    expect(await screen.findByText("Etapa 2 de 10")).toBeTruthy();
  });

  it("refuses a key the org already has (the create route is idempotent and would reuse it)", async () => {
    renderPage();
    await screen.findByTestId("assistente-plataforma-nome");
    await waitFor(() => expect(get).toHaveBeenCalledWith("/api/agents/painel"));
    fireEvent.change(screen.getByTestId("assistente-plataforma-nome"), { target: { value: "Julia" } });
    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));
    expect((await screen.findByTestId("assistente-plataforma-key-erro")).textContent).toMatch(/Já existe/);
  });
});

describe("NovoAgente — draft", () => {
  it("restores a local draft, says it is unsaved, and can discard it", async () => {
    rascunho({ passo: "personalidade", valores: { "plataforma.nome": "Estrategista", "plataforma.key": "estrategista" } });
    renderPage();
    expect(await screen.findByText("Etapa 3 de 10")).toBeTruthy();
    expect(screen.getByTestId("novo-agente-preview-nome").textContent).toBe("Estrategista");
    expect(screen.getByTestId("novo-agente-nao-salvo").textContent).toMatch(/Rascunho não publicado/);
    expect(screen.getByTestId("novo-agente-restaurado")).toBeTruthy();

    fireEvent.click(screen.getByTestId("novo-agente-descartar"));
    expect(screen.getByTestId("novo-agente-preview-nome").textContent).toBe("Novo agente");
    expect(screen.queryByTestId("novo-agente-nao-salvo")).toBeNull();
    expect(window.localStorage.getItem(RASCUNHO_STORAGE_KEY)).toBeNull();
  });

  it("keeps the answers in the browser as they are typed", async () => {
    renderPage();
    fireEvent.change(await screen.findByTestId("assistente-plataforma-nome"), { target: { value: "Ana" } });
    await waitFor(() => expect(JSON.parse(window.localStorage.getItem(RASCUNHO_STORAGE_KEY) ?? "{}").valores?.["plataforma.nome"]).toBe("Ana"));
  });
});

describe("NovoAgente — publish", () => {
  it("POSTs the §6 body, writes the new agent into the listing + page caches and opens its page", async () => {
    post.mockImplementation(async () => {
      // Hold the background settle refetch so the assertion reads what the WRITE put in the cache.
      get.mockImplementation(() => new Promise(() => {}));
      return {
        id: "11111111-1111-1111-1111-111111111111", key: "estrategista", org_id: "o", definition_scope: "plataforma",
        conteudo_modo: "linhas", nome: "Estrategista", runtime: "llm", usa_canais: false, instanciavel: true, geracao: null,
      };
    });
    rascunho({
      passo: "publicar",
      valores: { "plataforma.nome": "Estrategista", "plataforma.key": "estrategista", "plataforma.instanciavel": true },
    });
    const qc = renderPage();
    await waitFor(() => expect(qc.getQueryData(AGENTES_PAINEL_KEY)).toBeTruthy());
    fireEvent.click(await screen.findByRole("button", { name: "Publicar" }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post).toHaveBeenCalledWith("/api/studio/plataforma/agents", {
      key: "estrategista",
      nome: "Estrategista",
      runtime: "llm",
      instanciavel: true,
    });
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/agentes/estrategista"));
    const lista = qc.getQueryData<AgentesPainelResponse>(AGENTES_PAINEL_KEY);
    expect(lista?.items.map((a) => a.key)).toContain("estrategista");
    expect(qc.getQueryData(agentePainelKey("estrategista"))).toMatchObject({ key: "estrategista", nome: "Estrategista" });
    expect(window.localStorage.getItem(RASCUNHO_STORAGE_KEY)).toBeNull();
  });

  it("in AI mode sends the briefing; an incomplete one sends nothing and jumps to the step to fix", async () => {
    rascunho({
      modo: "gerar",
      passo: "publicar",
      valores: { "plataforma.nome": "Estrategista", "plataforma.key": "estrategista" },
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Publicar" }));
    expect(await screen.findByText("Etapa 2 de 10")).toBeTruthy();
    expect(post).not.toHaveBeenCalled();
    expect(screen.getByTestId("assistente-briefing-objetivo-erro").textContent).toMatch(/obrigatório/);
  });

  it("a 409 agente_ja_existe sends the user back to the identity step with the refusal on the key", async () => {
    post.mockRejectedValue(
      new ApiError(409, "Erro HTTP 409", { code: "agente_ja_existe", message: "Já existe um agente com a chave 'estrategista'." }),
    );
    rascunho({ passo: "publicar", valores: { "plataforma.nome": "Estrategista", "plataforma.key": "estrategista" } });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Publicar" }));
    expect(await screen.findByText("Etapa 1 de 10")).toBeTruthy();
    expect(screen.getByTestId("assistente-plataforma-key-erro").textContent).toMatch(/Já existe/);
    expect(navigate).not.toHaveBeenCalled();
    // a new key clears it and the step proceeds
    fireEvent.change(screen.getByTestId("assistente-plataforma-key"), { target: { value: "estrategista-2" } });
    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));
    expect(await screen.findByText("Etapa 2 de 10")).toBeTruthy();
  });

  it("labels come from the server's titles", async () => {
    renderPage();
    expect(await screen.findByText("Descrição")).toBeTruthy();
    expect(screen.getByText("Chave")).toBeTruthy();
  });

  it("shows the server's refusal and keeps the draft", async () => {
    post.mockRejectedValue(new ApiError(422, "Erro HTTP 422", { code: "nome_obrigatorio", message: "Informe o nome." }));
    rascunho({ passo: "publicar", valores: { "plataforma.nome": "Estrategista", "plataforma.key": "estrategista" } });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Publicar" }));
    expect((await screen.findByTestId("novo-agente-erro-envio")).textContent).toMatch(/Informe o nome\./);
    expect(navigate).not.toHaveBeenCalled();
    expect(window.localStorage.getItem(RASCUNHO_STORAGE_KEY)).not.toBeNull();
  });
});
